from __future__ import annotations
import json
import os
import threading
import time
from pathlib import Path
from typing import Any
import paramiko
from flask import Flask, jsonify, render_template

app = Flask(__name__)

@app.get("/api/gpus")
async def gpu_summary_processes():
    import subprocess, re
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=process_id,process_name,process_start_time",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True
        )
        lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
        out = []
        for line in lines:
            m = re.match(r"(\d+),([^,]+),(.*)", line)
            if m:
                pid, name, start = m.groups()
                out.append({
                    "pid": int(pid.strip()),
                    "process_name": name.strip(),
                    "process_start_time": start.strip()
                })
    except Exception as e:
        raise HTTPException(503, f"nvidia-smi failed: {e}")
    return {"gpus": out}

@app.get("/api/gpu/{gpu_id}")
async def gpu_info(gpu_id: int):
    import subprocess, re
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free,"
             "utilization.gpu,utilization.memory,processes.count,"
             "process_id,process_name",
             f"--query-gpu=processes.count,process_id,process_name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True
        )
        lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
        out = []
        for line in lines:
            m = re.match(r"(\d+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),(.*)", line)
            if m:
                pid, name, start = m.groups()
                out.append({
                    "pid": int(pid.strip()),
                    "process_name": name.strip(),
                    "process_start_time": start.strip()
                })
    except Exception as e:
        raise HTTPException(503, f"nvidia-smi failed: {e}")
    return {"gpu_id": gpu_id, "processes": out}

@app.get("/api/gpu/processes")
async def gpu_processes():
    """
    Returns a list of all GPU processes currently using the GPU(s).
    Output format:
    [
      {
        "pid": <int>,
        "process_name": "<str>",
        "process_start_time": "<ISO-8601 timestamp>",
        "process_id": "<nvidia-smi process ID>",
        "gpu_id": <int>
      },
      ...
    ]
    """
    import subprocess, re, json
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=process_id,process_name,process_start_time,gpu_index",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True, text=True, check=True
        )
        lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
        out = []
        for line in lines:
            m = re.match(r"(.*),(.*)", line)
            if m:
                parts = m.groups()
                if len(parts) != 2:
                    continue
                fields = [f.strip() for f in parts[0].split(",")]
                pid, name, start = [f.strip() for f in fields[1].split(",")]
                gpu_idx = fields[0].strip()
                out.append({
                    "process_id": int(pid.strip()) if pid.strip() else None,
                    "process_name": name.strip() or "<unknown>",
                    "process_start_time": start.strip() or None,
                    "gpu_id": int(gpu_idx) if gpu_idx.strip() else None,
                })
    except subprocess.CalledProcessError:
        raise HTTPException(503, "nvidia-smi command failed")
    except Exception as e:
        raise HTTPException(503, f"nvidia-smi failed: {e}")
    return {"processes": out}

@app.get("/api/gpu/{gpu_id}/processes")
async def gpu_processes_by_gpu(gpu_id: int):
    """
    Returns GPU processes for a specific GPU ID.
    Example: /api/gpu/0/processes
    """
    import subprocess, re, json
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=process_id,process_name,process_start_time,gpu_index",
                "--format=csv,noheader,nounits",
                f"--query-gpu=process_id,process_name,process_start_time,gpu_index",
            ],
            capture_output=True, text=True, check=True
        )
        lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
        out = []
        for line in lines:
            m = re.match(r"(.*),(.*)", line)
            if m:
                parts = m.groups()
                if len(parts) != 2:
                    continue
                fields = [f.strip() for f in parts[0].split(",")]
                pid, name, start = [f.strip() for f in fields[1].split(",")]
                gpu_idx = fields[0].strip()
                if int(gpu_idx) != gpu_id:
                    continue
                out.append({
                    "process_id": int(pid.strip()) if pid.strip() else None,
                    "process_name": name.strip() or "<unknown>",
                    "process_start_time": start.strip() or None,
                })
    except subprocess.CalledProcessError:
        raise HTTPException(503, "nvidia-smi command failed")
    except Exception as e:
        raise HTTPException(503, f"nvidia-smi failed: {e}")
    return {"gpu_id": gpu_id, "processes": out}



SSH_HOST = os.environ.get("SSH_HOST", "10.0.0.10")
SSH_PORT = int(os.environ.get("SSH_PORT", "22"))
SSH_USER = os.environ.get("SSH_USER", "truenas_admin")
SSH_KEY = os.environ.get("SSH_KEY", "/run/secrets/dashboard_key")


# One shared connection: opening a new SSH client per command (4 per poll)
# churns transport threads and crypto state, which steadily grows memory.
_ssh_client: paramiko.SSHClient | None = None
_ssh_lock = threading.Lock()


def get_ssh_client() -> paramiko.SSHClient:
    global _ssh_client

    with _ssh_lock:
        if _ssh_client is not None:
            transport = _ssh_client.get_transport()
            if transport is not None and transport.is_active():
                return _ssh_client
            _ssh_client.close()
            _ssh_client = None

        key_path = Path(SSH_KEY)
        if not key_path.is_file():
            raise RuntimeError(
                f"SSH private key is missing or is not a file: {SSH_KEY}. "
                "Restore the private key and check the container secret/bind mount."
            )
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            client.connect(
                hostname=SSH_HOST,
                port=SSH_PORT,
                username=SSH_USER,
                key_filename=SSH_KEY,
                timeout=5,
                banner_timeout=5,
                auth_timeout=5,
            )
        except Exception:
            client.close()
            raise

        client.get_transport().set_keepalive(30)
        _ssh_client = client
        return client


def reset_ssh_client(client: paramiko.SSHClient) -> None:
    global _ssh_client

    with _ssh_lock:
        if _ssh_client is client:
            _ssh_client = None
    client.close()


def ssh_command(command: str, timeout: int = 15) -> str:
    client = get_ssh_client()

    try:
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
    except (paramiko.SSHException, EOFError, OSError):
        # Connection went stale; the next call reconnects.
        reset_ssh_client(client)
        raise

    try:
        output = stdout.read().decode(
            "utf-8",
            errors="replace"
        ).strip()

        error = stderr.read().decode(
            "utf-8",
            errors="replace"
        ).strip()

        exit_code = stdout.channel.recv_exit_status()

        if exit_code != 0:
            raise RuntimeError(
                f"Command failed ({exit_code}): "
                f"{command}\n{error}"
            )

        return output

    finally:
        stdout.channel.close()


def parse_cpu() -> dict[str, Any]:
    command = r"""
python3 - <<'PYCPU'
import glob
import json
import os
import re

with open('/proc/cpuinfo', encoding='utf-8') as f:
    text = f.read()

clocks = [
    float(value)
    for value in re.findall(
        r'^cpu MHz\s*:\s*([\d.]+)',
        text,
        re.MULTILINE
    )
]

with open('/proc/loadavg', encoding='utf-8') as f:
    load = [float(x) for x in f.read().split()[:3]]

with open('/proc/stat', encoding='utf-8') as f:
    first = f.readline().split()[1:]

values = list(map(int, first))

idle = values[3] + values[4]
total = sum(values)

cpu_temp_c = None

for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
    try:
        with open(
            os.path.join(hwmon, 'name'),
            encoding='utf-8'
        ) as f:
            sensor_name = f.read().strip()
    except OSError:
        continue

    if sensor_name != 'k10temp':
        continue

    candidates = []

    for input_path in glob.glob(
        os.path.join(hwmon, 'temp*_input')
    ):
        base = input_path[:-6]
        label_path = base + '_label'

        try:
            with open(
                input_path,
                encoding='utf-8'
            ) as f:
                value = (
                    float(f.read().strip()) / 1000.0
                )
        except (OSError, ValueError):
            continue

        label = ''

        try:
            with open(
                label_path,
                encoding='utf-8'
            ) as f:
                label = f.read().strip()
        except OSError:
            pass

        priority = 2

        if label == 'Tctl':
            priority = 0
        elif label == 'Tdie':
            priority = 1

        candidates.append(
            (priority, value)
        )

    if candidates:
        candidates.sort(
            key=lambda item: item[0]
        )
        cpu_temp_c = candidates[0][1]
        break


fan_data = {
    'cpu_fan_rpm': None,
    'cpu_fan_pwm': None,
    'case_fans': {}
}

for hwmon in glob.glob('/sys/class/hwmon/hwmon*'):
    try:
        with open(
            os.path.join(hwmon, 'name'),
            encoding='utf-8'
        ) as f:
            sensor_name = f.read().strip()
    except OSError:
        continue

    if sensor_name not in ('nct6683', 'nct6687'):
        continue

    def read_int(filename):
        path = os.path.join(hwmon, filename)

        try:
            with open(
                path,
                encoding='utf-8'
            ) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    cpu_rpm = read_int('fan1_input')
    cpu_pwm_raw = read_int('pwm1')

    fan_data['cpu_fan_rpm'] = cpu_rpm

    if cpu_pwm_raw is not None:
        fan_data['cpu_fan_pwm'] = (
            cpu_pwm_raw / 255.0 * 100.0
        )

    case_mapping = {
        'Case Fan 1': 'fan3_input',
        'Case Fan 2': 'fan5_input',
        'Case Fan 3': 'fan8_input',
    }

    for label, filename in case_mapping.items():
        rpm = read_int(filename)

        if rpm is not None:
            fan_data['case_fans'][label] = rpm

    break


print(json.dumps({
    'clock_avg_mhz':
        sum(clocks) / len(clocks)
        if clocks else 0,

    'clock_max_mhz':
        max(clocks)
        if clocks else 0,

    'clocks_mhz': clocks,

    'temperature_c': cpu_temp_c,

    'logical_cpus': os.cpu_count(),

    'load_1': load[0],
    'load_5': load[1],
    'load_15': load[2],

    'cpu_total_ticks': total,
    'cpu_idle_ticks': idle,

    'cpu_fan_rpm':
        fan_data['cpu_fan_rpm'],

    'cpu_fan_pwm':
        fan_data['cpu_fan_pwm'],

    'case_fans':
        fan_data['case_fans']
}))
PYCPU
"""

    return json.loads(
        ssh_command(command)
    )


def parse_gpu() -> dict[str, Any]:
    query = (
        "utilization.gpu,"
        "utilization.memory,"
        "clocks.current.graphics,"
        "clocks.current.memory,"
        "memory.used,"
        "memory.total,"
        "temperature.gpu,"
        "power.draw,"
        "utilization.encoder,"
        "utilization.decoder,"
        "fan.speed"
    )

    command = (
        f"nvidia-smi --query-gpu={query} "
        "--format=csv,noheader,nounits | head -1"
    )

    fields = [
        field.strip()
        for field in ssh_command(command).split(",")
    ]

    if len(fields) != 11:
        raise RuntimeError(
            f"Unexpected nvidia-smi output: {fields}"
        )

    def number(value: str) -> float:
        try:
            return float(value)
        except ValueError:
            return 0.0

    return {
        "gpu_util":
            number(fields[0]),

        "memory_controller_util":
            number(fields[1]),

        "core_clock_mhz":
            number(fields[2]),

        "memory_clock_mhz":
            number(fields[3]),

        "vram_used_mib":
            number(fields[4]),

        "vram_total_mib":
            number(fields[5]),

        "temperature_c":
            number(fields[6]),

        "power_w":
            number(fields[7]),

        "encoder_util":
            number(fields[8]),

        "decoder_util":
            number(fields[9]),

        "fan_percent":
            number(fields[10]),
    }


def parse_disk_temperatures() -> dict[str, Any]:
    source = Path(__file__).with_name("disk_probe.py").read_text()
    return json.loads(ssh_command("python3 - <<'PYDISKS'\n" + source + "\nPYDISKS", timeout=90))


def parse_pool_io() -> dict[str, Any]:
    output = ssh_command(
        "zpool iostat -Hp 1 2",
        timeout=20,
    )

    pools: dict[
        str,
        dict[str, float]
    ] = {}

    for line in output.splitlines():
        fields = line.split()

        if len(fields) < 7:
            continue

        pool_name = fields[0]

        try:
            read_bps = float(fields[5])
            write_bps = float(fields[6])
        except ValueError:
            continue

        pools[pool_name] = {
            "read_bps": read_bps,
            "write_bps": write_bps,
        }

    return {
        "pools": pools,
        "count": len(pools),
    }


@app.get("/")
def index():
    return render_template(
        "index.html"
    )


@app.get("/api/metrics")
def metrics():
    result: dict[str, Any] = {
        "timestamp": time.time(),
        "errors": [],
    }

    collectors = {
        "cpu":
            parse_cpu,

        "gpu":
            parse_gpu,

        "disks":
            parse_disk_temperatures,

        "pools":
            parse_pool_io,
    }

    for name, collector in collectors.items():
        try:
            result[name] = collector()
        except Exception as exc:
            result[name] = None
            result["errors"].append(
                f"{name}: {exc}"
            )

    return jsonify(result)


@app.get("/health")
def health():
    return jsonify({
        "status": "ok"
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8080,
        debug=False
    )
