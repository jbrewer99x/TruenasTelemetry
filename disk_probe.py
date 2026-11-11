"""Executed on TrueNAS over SSH; never issue reads or START STOP UNIT.

Discovery uses cached sysfs metadata. ATA CHECK POWER MODE and SCSI REQUEST
SENSE do not start the spindle. Unsupported probes fail closed (unknown).
"""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess


def run(args):
    prefix = [] if os.geteuid() == 0 else ['sudo', '-n']
    return subprocess.run(prefix + args, capture_output=True, timeout=5,
                          env={**os.environ, 'LC_ALL': 'C',
                               'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'})


def command_error(status, label):
    detail = status.stderr.decode('utf-8', errors='replace').strip()
    return f"{label} failed (exit {status.returncode}): {detail or 'no diagnostic output'}"


def scsi_state(data):
    if not data:
        return 'unknown'
    response = data[0] & 0x7f
    if response == 0x70 and len(data) >= 14 and data[7] >= 6:
        key, asc, ascq = data[2] & 15, data[12], data[13]
    elif response == 0x72 and len(data) >= 8:
        key, asc, ascq = data[1] & 15, data[2], data[3]
    else:
        return 'unknown'
    if asc == 0x5e:
        if ascq in (2, 4):
            return 'standby'
        if ascq in (1, 3, 5, 6, 7, 8):
            return 'idle'
        # STANDBY_Y may retain spindle rotation; don't call it spun down.
        return 'low_power'
    if (key, asc, ascq) == (0, 0, 0):
        return 'active'
    return 'unknown'


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def ata_fallback(device, result):
    """Use the existing guarded SMART query when hdparm cannot decode the mode."""
    status = run(['smartctl', '-d', 'ata', '-n', 'standby,3,5', '-A', '-j', device])
    data = json.loads(status.stdout)
    messages = ' '.join(m.get('string', '') for m in
                        data.get('smartctl', {}).get('messages', []))
    if status.returncode == 3:
        # Exit codes alone are ambiguous (smartctl also uses a bitmask).
        mode = re.search(r'Device is in (STANDBY_Y|STANDBY|SLEEP) mode', messages)
        if mode:
            result['power_state'] = {'STANDBY_Y': 'low_power',
                                     'STANDBY': 'standby', 'SLEEP': 'sleep'}[mode[1]]
            result['spun_down'] = None if mode[1] == 'STANDBY_Y' else True
            return result
    if status.returncode >= 0 and not (status.returncode & 7) and data.get('ata_smart_attributes'):
        # 7.4 omits power_mode in JSON. Successful guarded collection means
        # it passed the standby/unsupported checks, not an unguarded SMART read.
        result['power_state'] = 'active'
        result['spun_down'] = False
        result['temperature_c'] = data.get('temperature', {}).get('current')
        return result
    result['error'] = messages or command_error(status, 'Guarded ATA check')
    return result


def probe(path):
    name = path.name
    device = '/dev/' + name
    vendor = read(path / 'device/vendor')
    rotational = read(path / 'queue/rotational')
    protocol = 'nvme' if name.startswith('nvme') else 'ata' if vendor == 'ATA' else 'scsi'
    result = {'name': name, 'protocol': protocol, 'power_state': 'unknown',
              'spun_down': None, 'temperature_c': None}
    status = None
    try:
        if rotational == '0':
            result['power_state'] = 'solid_state'
        elif protocol == 'ata':
            status = run(['hdparm', '-C', device])
            match = re.search(rb'drive state is:\s*(active/idle|standby|sleeping)\b', status.stdout)
            if status.returncode == 0 and match:
                result['power_state'] = {'active/idle': 'active', 'standby': 'standby',
                                         'sleeping': 'sleep'}[match[1].decode()]
        elif protocol == 'scsi':
            # Older TrueNAS sg3_utils lacks --timeout; run() bounds execution.
            status = run(['sg_requests', '--raw', device])
            if status.returncode == 0:
                result['power_state'] = scsi_state(status.stdout)
        if protocol == 'ata' and result['power_state'] == 'unknown' and status is not None and status.returncode == 0:
            return ata_fallback(device, result)
        state = result['power_state']
        if state in ('standby', 'sleep'):
            result['spun_down'] = True
        elif state in ('active', 'idle'):
            result['spun_down'] = False
        if state == 'unknown':
            result['error'] = (command_error(status, 'Power check')
                               if status is not None and status.returncode else
                               'Power check returned an unsupported or unrecognized state')
            if status is not None and status.returncode == 0:
                detail = (status.stdout.decode('utf-8', errors='replace').strip()
                          if protocol == 'ata' else status.stdout.hex(' '))
                stderr = status.stderr.decode('utf-8', errors='replace').strip()
                result['error'] += ': ' + (detail + ' ' + stderr).strip()[:1000]
        # Never request temperatures from sleeping or unclassified HDDs.
        if state in ('active', 'idle', 'solid_state'):
            if protocol in ('ata', 'nvme'):
                # Explicit type avoids probing/autodetection. Guard against a
                # SATA disk entering standby between status and temperature.
                cmd = ['smartctl', '-d', protocol, '-n', 'standby,3,5', '-A', '-j', device]
                temp = run(cmd)
                if not (temp.returncode & 7):
                    result['temperature_c'] = json.loads(temp.stdout).get('temperature', {}).get('current')
                else:
                    result['error'] = command_error(temp, 'Temperature check')
            else:
                # Only LOG SENSE; -xx suppresses even the INQUIRY command.
                temp = run(['sg_logs', '--readonly', '-xx', '--page=0x0d', device])
                match = re.search(rb'Current (?:drive )?temperature\s*[:=]\s*(\d+)', temp.stdout, re.I)
                if temp.returncode == 0 and match and int(match[1]) < 255:
                    result['temperature_c'] = int(match[1])
                elif temp.returncode:
                    result['error'] = command_error(temp, 'Temperature check')
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        result['error'] = str(exc)
    return result


def collect():
    paths = [p for p in Path('/sys/block').iterdir()
             if re.fullmatch(r'(sd[a-z]+|hd[a-z]+|nvme\d+n\d+)', p.name)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        drives = list(pool.map(probe, sorted(paths)))
    temperatures = {d['name']: d['temperature_c'] for d in drives
                    if isinstance(d['temperature_c'], (int, float))}
    values = list(temperatures.values())
    return {'drives': drives, 'temperatures': temperatures, 'count': len(values),
            'total_count': len(drives), 'minimum_c': min(values) if values else None,
            'maximum_c': max(values) if values else None,
            'average_c': sum(values) / len(values) if values else None}


if __name__ == '__main__':
    print(json.dumps(collect()))
