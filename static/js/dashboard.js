let previousCpuTotal = null;
let previousCpuIdle = null;

function setText(id, value) {
    const element = document.getElementById(id);

    if (element) {
        element.textContent = value;
    }
}

function clearTemperatureClasses(element) {
    if (!element) {
        return;
    }

    element.classList.remove(
        "temp-green",
        "temp-yellow",
        "temp-red"
    );
}

function setTemperature(id, temperature, thresholds) {
    const element = document.getElementById(id);
    const value = Number(temperature);

    if (!element) {
        return;
    }

    clearTemperatureClasses(element);

    if (temperature == null || !Number.isFinite(value)) {
        element.textContent = "Unavailable";
        return;
    }

    element.textContent = `${Math.round(value)} °C`;

    if (value >= thresholds.red) {
        element.classList.add("temp-red");
    } else if (value >= thresholds.yellow) {
        element.classList.add("temp-yellow");
    } else {
        element.classList.add("temp-green");
    }
}

function updateCpuUtilization(cpu) {
    const currentTotal = Number(cpu.cpu_total_ticks);
    const currentIdle = Number(cpu.cpu_idle_ticks);

    if (
        !Number.isFinite(currentTotal) ||
        !Number.isFinite(currentIdle)
    ) {
        setText("cpuUtil", "Unavailable");
        return;
    }

    if (
        previousCpuTotal !== null &&
        previousCpuIdle !== null
    ) {
        const totalDelta = currentTotal - previousCpuTotal;
        const idleDelta = currentIdle - previousCpuIdle;

        if (totalDelta > 0) {
            const utilization =
                (1 - idleDelta / totalDelta) * 100;

            const boundedUtilization = Math.max(
                0,
                Math.min(100, utilization)
            );

            setText(
                "cpuUtil",
                `${boundedUtilization.toFixed(1)}%`
            );
        }
    }

    previousCpuTotal = currentTotal;
    previousCpuIdle = currentIdle;
}

function diskTemperatureClass(temperature) {
    const value = Number(temperature);

    if (!Number.isFinite(value)) {
        return "";
    }

    if (value >= 50) {
        return "temp-red";
    }

    if (value >= 45) {
        return "temp-yellow";
    }

    return "temp-green";
}

function updateCoreClocks(clocks) {
    const container = document.getElementById("cpuCores");

    if (!container) {
        return;
    }

    container.innerHTML = "";

    if (!Array.isArray(clocks) || clocks.length === 0) {
        container.textContent =
            "Per-thread clock data unavailable";
        return;
    }

    clocks.forEach((clock, index) => {
        const item = document.createElement("div");
        item.className = "coreItem";

        const label = document.createElement("span");
        label.className = "coreLabel";
        label.textContent = `CPU ${index}`;

        const value = document.createElement("span");
        value.className = "coreClock";
        value.textContent =
            `${Math.round(Number(clock) || 0)} MHz`;

        item.appendChild(label);
        item.appendChild(value);
        container.appendChild(item);
    });
}

function updateCaseFans(caseFans) {
    const container = document.getElementById("caseFans");

    if (!container) {
        return;
    }

    container.innerHTML = "";

    const entries = Object.entries(caseFans || {});

    if (entries.length === 0) {
        container.textContent =
            "Case fan data unavailable";
        return;
    }

    entries.forEach(([name, rpm]) => {
        const item = document.createElement("div");
        item.className = "coreItem";

        const label = document.createElement("span");
        label.className = "coreLabel";
        label.textContent = name;

        const value = document.createElement("span");
        value.className = "coreClock";

        const numericRpm = Number(rpm);

        value.textContent =
            Number.isFinite(numericRpm)
                ? `${Math.round(numericRpm)} RPM`
                : "Unavailable";

        item.appendChild(label);
        item.appendChild(value);
        container.appendChild(item);
    });
}

function updateDiskTemperatures(drives) {
    const container = document.getElementById("diskTemps");
    container.replaceChildren();
    if (!drives || !drives.length) {
        container.textContent = "Disk status unavailable";
        return;
    }
    const labels = {active: "Spinning", idle: "Spinning (idle)",
        standby: "Spun down (standby)", sleep: "Spun down (sleep)",
        low_power: "Low power (rotation unknown)",
        solid_state: "SSD (no spindle)", unknown: "Unknown"};
    drives.forEach(drive => {
        const item = document.createElement("div");
        item.className = "coreItem diskItem";
        const label = document.createElement("span");
        label.className = "coreLabel";
        label.textContent = `${drive.name} · ${drive.protocol.toUpperCase()}`;
        const power = document.createElement("span");
        power.className = `diskPower power-${drive.power_state}`;
        power.textContent = labels[drive.power_state] || "Unknown";
        power.title = drive.error || "Current drive power state";
        const temperature = document.createElement("span");
        const available = typeof drive.temperature_c === "number";
        temperature.className = available ? diskTemperatureClass(drive.temperature_c) : "coreLabel";
        temperature.textContent = available ? `${Math.round(drive.temperature_c)} °C` : "Temperature unavailable";
        item.append(label, power, temperature);
        if (drive.error) {
            const diagnostic = document.createElement("span");
            diagnostic.className = "diskError";
            diagnostic.textContent = drive.error;
            item.appendChild(diagnostic);
        }
        container.appendChild(item);
    });
}

function formatBytesPerSecond(value) {
    const bps = Number(value);

    if (!Number.isFinite(bps) || bps < 0) {
        return "Unavailable";
    }

    const units = [
        "B/s",
        "KB/s",
        "MB/s",
        "GB/s",
        "TB/s"
    ];

    let scaled = bps;
    let unitIndex = 0;

    while (
        scaled >= 1024 &&
        unitIndex < units.length - 1
    ) {
        scaled /= 1024;
        unitIndex += 1;
    }

    if (unitIndex === 0) {
        return `${Math.round(scaled)} ${units[unitIndex]}`;
    }

    if (scaled >= 100) {
        return `${scaled.toFixed(0)} ${units[unitIndex]}`;
    }

    if (scaled >= 10) {
        return `${scaled.toFixed(1)} ${units[unitIndex]}`;
    }

    return `${scaled.toFixed(2)} ${units[unitIndex]}`;
}

function updatePoolIo(poolData) {
    const container = document.getElementById("poolIo");

    if (!container) {
        return;
    }

    container.innerHTML = "";

    const pools = poolData?.pools || {};
    const entries = Object.entries(pools);

    if (entries.length === 0) {
        container.textContent =
            "Pool I/O data unavailable";
        return;
    }

    entries.forEach(([poolName, metrics]) => {
        const pool = document.createElement("div");
        pool.className = "poolItem";

        const title = document.createElement("h3");
        title.className = "poolName";
        title.textContent = poolName;

        const readMetric = document.createElement("div");
        readMetric.className = "metric";

        const readLabel = document.createElement("span");
        readLabel.textContent = "Read";

        const readValue = document.createElement("span");
        readValue.textContent =
            formatBytesPerSecond(metrics.read_bps);

        readMetric.appendChild(readLabel);
        readMetric.appendChild(readValue);

        const writeMetric = document.createElement("div");
        writeMetric.className = "metric";

        const writeLabel = document.createElement("span");
        writeLabel.textContent = "Write";

        const writeValue = document.createElement("span");
        writeValue.textContent =
            formatBytesPerSecond(metrics.write_bps);

        writeMetric.appendChild(writeLabel);
        writeMetric.appendChild(writeValue);

        pool.appendChild(title);
        pool.appendChild(readMetric);
        pool.appendChild(writeMetric);

        container.appendChild(pool);
    });
}

async function refresh() {
    try {
        const response = await fetch("/api/metrics", {
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.cpu) {
            setText(
                "cpuAvg",
                `${Math.round(data.cpu.clock_avg_mhz)} MHz`
            );

            setText(
                "cpuMax",
                `${Math.round(data.cpu.clock_max_mhz)} MHz`
            );

            setTemperature(
                "cpuTemp",
                data.cpu.temperature_c,
                {
                    yellow: 50,
                    red: 71
                }
            );

            updateCpuUtilization(data.cpu);

            const cpuFanRpm = Number(data.cpu.cpu_fan_rpm);

            setText(
                "cpuFanRpm",
                Number.isFinite(cpuFanRpm)
                    ? `${Math.round(cpuFanRpm)} RPM`
                    : "Unavailable"
            );

            const cpuFanPwm = Number(data.cpu.cpu_fan_pwm);

            setText(
                "cpuFanPwm",
                Number.isFinite(cpuFanPwm)
                    ? `${Math.round(cpuFanPwm)}%`
                    : "Unavailable"
            );

            updateCaseFans(data.cpu.case_fans);

            updateCoreClocks(data.cpu.clocks_mhz);
        }

        if (data.gpu_processes) {
            updateGpuProcesses(data.gpu_processes.processes);
        }

        if (data.gpu) {
            setText(
                "gpuUtil",
                `${Math.round(data.gpu.gpu_util)}%`
            );

            setText(
                "gpuClock",
                `${Math.round(data.gpu.core_clock_mhz)} MHz`
            );

            setText(
                "vramClock",
                `${Math.round(data.gpu.memory_clock_mhz)} MHz`
            );

            setText(
                "vramUsage",
                `${Math.round(data.gpu.vram_used_mib)} / ` +
                `${Math.round(data.gpu.vram_total_mib)} MiB`
            );

            setText(
                "gpuMemUtil",
                `${Math.round(
                    data.gpu.memory_controller_util
                )}%`
            );

            setTemperature(
                "gpuTemp",
                data.gpu.temperature_c,
                {
                    yellow: 50,
                    red: 71
                }
            );

            setText(
                "gpuFan",
                `${Math.round(data.gpu.fan_percent)}%`
            );

            setText(
                "gpuPower",
                `${data.gpu.power_w.toFixed(1)} W`
            );
        }

        if (data.disks) {
            setText(
                "diskCount",
                `${data.disks.count} / ` +
                `${data.disks.total_count} drives`
            );

            setTemperature(
                "diskMin",
                data.disks.minimum_c,
                {
                    yellow: 45,
                    red: 50
                }
            );

            setTemperature(
                "diskAvg",
                data.disks.average_c,
                {
                    yellow: 45,
                    red: 50
                }
            );

            setTemperature(
                "diskMax",
                data.disks.maximum_c,
                {
                    yellow: 45,
                    red: 50
                }
            );

            updateDiskTemperatures(
                data.disks.drives
            );
        }

        if (!data.disks) updateDiskTemperatures([]);

        if (data.pools) {
            updatePoolIo(data.pools);
        }

        const errors = data.errors || [];

        setText(
            "status",
            errors.length
                ? `Updated ${new Date().toLocaleTimeString()} — ` +
                  `${errors.length} error(s): ${errors.join("; ")}`
                : `Updated ${new Date().toLocaleTimeString()}`
        );
    } catch (error) {
        console.error(error);
        updateDiskTemperatures([]);

        setText(
            "status",
            `Connection error: ${error.message}`
        );
    }
}

const pollingStorageKey = "telemetryPollingSeconds";
let pollingSeconds = 2;
let pollingTimer = null;
let pollingInFlight = false;

function validPollingSeconds(value) {
    return Number.isFinite(value) && value >= 1 && value <= 3600;
}

try {
    const saved = Number(localStorage.getItem(pollingStorageKey));
    if (validPollingSeconds(saved)) pollingSeconds = saved;
} catch (_) {
    // Polling still works when browser storage is unavailable.
}

const pollingInput = document.getElementById("pollingSeconds");
function displayPollingInterval() {
    if (pollingInput) pollingInput.value = String(pollingSeconds);
    setText("pollingStatus", `Current polling interval: ${pollingSeconds} seconds for all telemetry commands, after each update completes.`);
}
displayPollingInterval();

function schedulePoll() {
    clearTimeout(pollingTimer);
    pollingTimer = setTimeout(poll, pollingSeconds * 1000);
}

async function poll() {
    if (pollingInFlight) return;
    pollingInFlight = true;
    try {
        await refresh();
    } finally {
        pollingInFlight = false;
        schedulePoll();
    }
}

pollingInput?.addEventListener("input", () => pollingInput.setCustomValidity(""));
document.getElementById("pollingForm")?.addEventListener("submit", event => {
    event.preventDefault();
    const value = Number(pollingInput.value.trim());
    if (!validPollingSeconds(value)) {
        pollingInput.setCustomValidity("Enter a number from 1 to 3600 seconds.");
        pollingInput.reportValidity();
        return;
    }
    pollingInput.setCustomValidity("");
    pollingSeconds = value;
    try {
        localStorage.setItem(pollingStorageKey, String(value));
    } catch (_) {
        // Apply for this page even if the preference cannot be saved.
    }
    displayPollingInterval();
    // Let an existing collection finish; its next delay uses the new value.
    if (!pollingInFlight) schedulePoll();
});

poll();
