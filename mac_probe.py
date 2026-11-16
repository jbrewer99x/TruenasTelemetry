"""Executed on the Mac over SSH with /usr/bin/python3; needs no root.

Stays compatible with the Python 3.9 that ships with the Xcode command line
tools. CPU ticks come from host_processor_info, GPU utilization and disk byte
counters from the I/O Registry, and temperatures from the IOHID sensor
services that Apple Silicon exposes to unprivileged users.
"""
import ctypes
import ctypes.util
import json
import plistlib
import re
import subprocess
import time

SAMPLE_SECONDS = 1.0
IOREG = '/usr/sbin/ioreg'


def ioreg(*args):
    output = subprocess.run([IOREG, '-a', '-r'] + list(args),
                            capture_output=True, check=True, timeout=10).stdout
    return plistlib.loads(output) if output.strip() else []


# --- CPU ----------------------------------------------------------------

def cpu_ticks():
    """Per-CPU (busy, total) ticks."""
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    libc.mach_host_self.restype = ctypes.c_uint
    count = ctypes.c_uint()
    info = ctypes.POINTER(ctypes.c_uint)()
    info_count = ctypes.c_uint()
    # PROCESSOR_CPU_LOAD_INFO: user, system, idle, nice ticks per CPU.
    status = libc.host_processor_info(libc.mach_host_self(), 2, ctypes.byref(count),
                                      ctypes.byref(info), ctypes.byref(info_count))
    if status != 0:
        raise RuntimeError(f'host_processor_info failed ({status})')
    try:
        ticks = []
        for cpu in range(count.value):
            user, system, idle, nice = info[cpu * 4:cpu * 4 + 4]
            ticks.append((user + system + nice, user + system + idle + nice))
        return ticks
    finally:
        task = ctypes.c_uint.in_dll(libc, 'mach_task_self_')
        libc.vm_deallocate(task, ctypes.cast(info, ctypes.c_void_p),
                           ctypes.c_size_t(info_count.value * 4))


def cpu_usage(before, after):
    """Average and per-CPU busy percentage between two cpu_ticks() samples."""
    wrap = 1 << 32  # Mach tick counters are 32-bit.
    per_cpu, busy_sum, total_sum = [], 0, 0
    for (busy0, total0), (busy1, total1) in zip(before, after):
        busy, total = (busy1 - busy0) % wrap, (total1 - total0) % wrap
        busy_sum, total_sum = busy_sum + busy, total_sum + total
        per_cpu.append(100.0 * busy / total if total else 0.0)
    return {
        'average_percent': 100.0 * busy_sum / total_sum if total_sum else 0.0,
        'per_cpu_percent': per_cpu,
    }


def sysctl(name):
    return subprocess.run(['/usr/sbin/sysctl', '-n', name], capture_output=True,
                          text=True, timeout=5).stdout.strip()


def core_clusters():
    """[{'name': 'Performance', 'cores': 4}, ...] for each CPU performance level."""
    clusters = []
    for level in range(int(sysctl('hw.nperflevels') or 0)):
        clusters.append({'name': sysctl(f'hw.perflevel{level}.name'),
                         'cores': int(sysctl(f'hw.perflevel{level}.logicalcpu') or 0)})
    return clusters


# Device-tree cluster types, fastest first. They don't match the perflevel
# names: on a three-level chip P is "Super" and M is "Performance".
CLUSTER_TYPE_RANK = ['P', 'M', 'E']


def core_types(cpus, clusters):
    """Initial of each CPU's performance level ('S', 'P', 'E'), indexed by CPU.

    cpus are the IODeviceTree children of the 'cpus' node; clusters come from
    core_clusters(), which lists perflevels fastest first.
    """
    kinds = {}
    for cpu in cpus:
        kind = cpu.get('cluster-type', b'').rstrip(b'\0').decode('ascii', errors='replace')
        if 'logical-cpu-id' in cpu and kind:
            kinds[cpu['logical-cpu-id']] = kind
    present = sorted(set(kinds.values()),
                     key=lambda kind: CLUSTER_TYPE_RANK.index(kind)
                     if kind in CLUSTER_TYPE_RANK else len(CLUSTER_TYPE_RANK))
    if len(present) != len(clusters):
        return []
    initials = {kind: cluster['name'][:1].upper() for kind, cluster in zip(present, clusters)}
    return [initials.get(kinds.get(index)) for index in range(max(kinds) + 1)] if kinds else []


def cpu_nodes():
    nodes = plistlib.loads(subprocess.run(
        [IOREG, '-a', '-l', '-r', '-p', 'IODeviceTree', '-n', 'cpus', '-d', '2'],
        capture_output=True, check=True, timeout=10).stdout or b'<plist><array/></plist>')
    return nodes[0].get('IORegistryEntryChildren', []) if nodes else []


# --- Memory -------------------------------------------------------------

PRESSURE_LEVELS = {1: 'normal', 2: 'warning', 4: 'critical'}


def parse_vm_stat(text):
    """Page size and {'Pages free': n, ...} from vm_stat output."""
    match = re.search(r'page size of (\d+) bytes', text)
    pages = {}
    for line in text.splitlines()[1:]:
        name, _, value = line.rpartition(':')
        value = value.strip().rstrip('.')
        if value.isdigit():
            pages[name.strip().strip('"')] = int(value)
    return (int(match.group(1)) if match else 4096), pages


def parse_swap_used(text):
    """Bytes used from sysctl vm.swapusage, e.g. 'total = 1024.00M  used = 3.25M ...'."""
    match = re.search(r'used = ([\d.]+)([KMGT])', text)
    if not match:
        return None
    scale = 1024 ** ('KMGT'.index(match.group(2)) + 1)
    return int(float(match.group(1)) * scale)


def memory_summary(page_size, pages, total_bytes):
    """Breakdown matching Activity Monitor's Memory Used."""
    def size(*names):
        return sum(pages.get(name, 0) for name in names) * page_size

    app = max(0, size('Anonymous pages') - size('Pages purgeable'))
    wired = size('Pages wired down')
    compressed = size('Pages occupied by compressor')
    used = app + wired + compressed
    return {
        'total_bytes': total_bytes,
        'used_bytes': used,
        'used_percent': 100.0 * used / total_bytes if total_bytes else None,
        'app_bytes': app,
        'wired_bytes': wired,
        'compressed_bytes': compressed,
        'cached_bytes': size('File-backed pages', 'Pages purgeable'),
    }


def memory_stats():
    vm_stat = subprocess.run(['/usr/bin/vm_stat'], capture_output=True, text=True,
                             check=True, timeout=5).stdout
    memory = memory_summary(*parse_vm_stat(vm_stat), int(sysctl('hw.memsize')))
    memory['swap_used_bytes'] = parse_swap_used(sysctl('vm.swapusage'))
    pressure = sysctl('kern.memorystatus_vm_pressure_level')
    memory['pressure'] = PRESSURE_LEVELS.get(int(pressure) if pressure.isdigit() else 0)
    return memory


# --- GPU ----------------------------------------------------------------

def gpu_stats(accelerators):
    for accelerator in accelerators:
        stats = accelerator.get('PerformanceStatistics') or {}
        if 'Device Utilization %' in stats:
            return {
                'model': accelerator.get('model'),
                'cores': accelerator.get('gpu-core-count'),
                'device_util': stats.get('Device Utilization %'),
                'renderer_util': stats.get('Renderer Utilization %'),
                'tiler_util': stats.get('Tiler Utilization %'),
                'memory_in_use_bytes': stats.get('In use system memory'),
            }
    return None


def average_gpu(first, second):
    if not first or not second:
        return second or first
    merged = dict(second)
    for key in ('device_util', 'renderer_util', 'tiler_util'):
        if first.get(key) is not None and second.get(key) is not None:
            merged[key] = (first[key] + second[key]) / 2
    return merged


# --- Storage I/O --------------------------------------------------------

def disk_counters():
    """Cumulative byte counters per whole disk, keyed by BSD name."""
    names = {media['IORegistryEntryID']: media
             for media in ioreg('-c', 'IOMedia', '-d', '1')
             if media.get('Whole') and media.get('BSD Name')}
    counters = {}
    for driver in ioreg('-c', 'IOBlockStorageDriver', '-d', '2'):
        stats = driver.get('Statistics') or {}
        for child in driver.get('IORegistryEntryChildren', []):
            media = names.get(child.get('IORegistryEntryID'))
            if media is None or 'disk image' in child.get('IORegistryEntryName', ''):
                continue
            counters[media['BSD Name']] = {
                'model': child.get('IORegistryEntryName', '').replace(' Media', ''),
                'read_bytes': stats.get('Bytes (Read)', 0),
                'write_bytes': stats.get('Bytes (Write)', 0),
            }
    return counters


def disk_rates(before, after, elapsed):
    disks = {}
    for name, current in sorted(after.items()):
        previous = before.get(name)
        if previous is None or elapsed <= 0:
            continue
        disks[name] = {
            'model': current['model'],
            'read_bps': max(0, current['read_bytes'] - previous['read_bytes']) / elapsed,
            'write_bps': max(0, current['write_bytes'] - previous['write_bytes']) / elapsed,
        }
    return disks


# --- Temperatures -------------------------------------------------------

def read_sensors():
    """(name, celsius) for every IOHID temperature sensor."""
    cf = ctypes.CDLL(ctypes.util.find_library('CoreFoundation'))
    iokit = ctypes.CDLL(ctypes.util.find_library('IOKit'))
    vp = ctypes.c_void_p
    cf.CFStringCreateWithCString.restype = vp
    cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFNumberCreate.restype = vp
    cf.CFNumberCreate.argtypes = [vp, ctypes.c_int, vp]
    cf.CFDictionaryCreate.restype = vp
    cf.CFDictionaryCreate.argtypes = [vp, vp, vp, ctypes.c_long, vp, vp]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetCount.argtypes = [vp]
    cf.CFArrayGetValueAtIndex.restype = vp
    cf.CFArrayGetValueAtIndex.argtypes = [vp, ctypes.c_long]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFRelease.argtypes = [vp]
    iokit.IOHIDEventSystemClientCreate.restype = vp
    iokit.IOHIDEventSystemClientCreate.argtypes = [vp]
    iokit.IOHIDEventSystemClientSetMatching.argtypes = [vp, vp]
    iokit.IOHIDEventSystemClientCopyServices.restype = vp
    iokit.IOHIDEventSystemClientCopyServices.argtypes = [vp]
    iokit.IOHIDServiceClientCopyProperty.restype = vp
    iokit.IOHIDServiceClientCopyProperty.argtypes = [vp, vp]
    iokit.IOHIDServiceClientCopyEvent.restype = vp
    iokit.IOHIDServiceClientCopyEvent.argtypes = [vp, ctypes.c_int64, ctypes.c_int32, ctypes.c_int64]
    iokit.IOHIDEventGetFloatValue.restype = ctypes.c_double
    iokit.IOHIDEventGetFloatValue.argtypes = [vp, ctypes.c_int32]

    utf8 = 0x08000100
    temperature_event = 15

    def cfstr(text):
        return cf.CFStringCreateWithCString(None, text.encode(), utf8)

    def cfint(value):
        number = ctypes.c_int32(value)
        return cf.CFNumberCreate(None, 3, ctypes.byref(number))  # kCFNumberSInt32Type

    # Apple vendor usage page 0xff00, usage 5 = temperature sensors.
    keys = (vp * 2)(cfstr('PrimaryUsagePage'), cfstr('PrimaryUsage'))
    values = (vp * 2)(cfint(0xff00), cfint(5))
    matching = cf.CFDictionaryCreate(
        None, keys, values, 2,
        ctypes.addressof(vp.in_dll(cf, 'kCFTypeDictionaryKeyCallBacks')),
        ctypes.addressof(vp.in_dll(cf, 'kCFTypeDictionaryValueCallBacks')))
    client = iokit.IOHIDEventSystemClientCreate(None)
    if not client:
        return []
    iokit.IOHIDEventSystemClientSetMatching(client, matching)
    services = iokit.IOHIDEventSystemClientCopyServices(client)
    product = cfstr('Product')
    readings = []
    buffer = ctypes.create_string_buffer(256)
    for index in range(cf.CFArrayGetCount(services) if services else 0):
        service = cf.CFArrayGetValueAtIndex(services, index)
        name_ref = iokit.IOHIDServiceClientCopyProperty(service, product)
        name = None
        if name_ref:
            if cf.CFStringGetCString(name_ref, buffer, len(buffer), utf8):
                name = buffer.value.decode('utf-8', errors='replace')
            cf.CFRelease(name_ref)
        event = iokit.IOHIDServiceClientCopyEvent(service, temperature_event, 0, 0)
        if name and event:
            readings.append((name, iokit.IOHIDEventGetFloatValue(event, temperature_event << 16)))
        if event:
            cf.CFRelease(event)
    for ref in (services, client, matching, product) + tuple(keys) + tuple(values):
        if ref:
            cf.CFRelease(ref)
    return readings


TEMPERATURE_GROUPS = [
    # (label, predicate on sensor name)
    ('SoC die', lambda name: 'tdie' in name),
    ('SoC package', lambda name: 'tdev' in name),
    ('SSD', lambda name: name.startswith('NAND')),
    ('Battery', lambda name: 'battery' in name.lower()),
]


def temperature_summary(readings):
    """Collapse raw sensors into labelled groups with average and maximum."""
    groups = []
    for label, matches in TEMPERATURE_GROUPS:
        # tcal is a fixed calibration constant, not a live reading.
        values = [value for name, value in readings
                  if matches(name) and 'tcal' not in name and 0 < value < 150]
        if values:
            groups.append({
                'label': label,
                'average_c': sum(values) / len(values),
                'maximum_c': max(values),
                'sensors': len(values),
            })
    return groups


# --- Collection ---------------------------------------------------------

def collect():
    errors = []

    def attempt(label, function, *args):
        try:
            return function(*args)
        except Exception as exc:  # Report partial data rather than nothing.
            errors.append(f'{label}: {exc}')
            return None

    ticks0 = attempt('cpu', cpu_ticks)
    disks0 = attempt('storage', disk_counters)
    gpu0 = attempt('gpu', lambda: gpu_stats(ioreg('-c', 'IOAccelerator', '-d', '1')))
    start = time.monotonic()
    time.sleep(SAMPLE_SECONDS)
    ticks1 = attempt('cpu', cpu_ticks) if ticks0 else None
    disks1 = attempt('storage', disk_counters) if disks0 is not None else None
    elapsed = time.monotonic() - start
    gpu1 = attempt('gpu', lambda: gpu_stats(ioreg('-c', 'IOAccelerator', '-d', '1')))
    readings = attempt('temperatures', read_sensors) or []
    memory = attempt('memory', memory_stats)

    cpu = cpu_usage(ticks0, ticks1) if ticks0 and ticks1 else None
    if cpu is not None:
        cpu['clusters'] = attempt('cpu clusters', core_clusters) or []
        cpu['core_types'] = attempt('core types', lambda: core_types(cpu_nodes(), cpu['clusters'])) or []

    return {
        'hostname': subprocess.run(['/bin/hostname', '-s'], capture_output=True,
                                   text=True, timeout=5).stdout.strip(),
        'cpu': cpu,
        'gpu': average_gpu(gpu0, gpu1),
        'memory': memory,
        'temperatures': temperature_summary(readings),
        'storage': disk_rates(disks0, disks1, elapsed) if disks0 is not None and disks1 is not None else {},
        'errors': errors,
    }


if __name__ == '__main__':
    print(json.dumps(collect()))
