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

function updateGpuProcesses(processes) {
    const container = document.getElementById("gpuProcesses");

    if (!container) {
        return;
    }

    container.replaceChildren();

    if (!Array.isArray(processes)) {
        container.textContent = "GPU process data unavailable";
        return;
    }

    if (processes.length === 0) {
        container.textContent = "No GPU processes running";
        return;
    }

    processes.forEach(process => {
        // Show just the executable; the full path is on hover.
        const name = process.process_name.split("/").pop() || process.process_name;
        const memory = Number(process.used_memory_mib);

        const item = gridItem(
            `${name} · PID ${process.pid}`,
            process.used_memory_mib != null && Number.isFinite(memory)
                ? `${Math.round(memory)} MiB`
                : "N/A"
        );
        item.title = process.process_name;
        container.appendChild(item);
    });
}

function formatPercent(value) {
    const number = Number(value);
    return value != null && Number.isFinite(number)
        ? `${number.toFixed(1)}%`
        : "Unavailable";
}

function gridItem(labelText, valueText, valueClass = "coreClock") {
    const item = document.createElement("div");
    item.className = "coreItem";

    const label = document.createElement("span");
    label.className = "coreLabel";
    label.textContent = labelText;

    const value = document.createElement("span");
    value.className = valueClass;
    value.textContent = valueText;

    item.append(label, value);
    return item;
}

const macTemperatureLimits = {
    SSD: {yellow: 60, red: 70},
    Battery: {yellow: 40, red: 45},
    default: {yellow: 80, red: 95}
};

function formatGiB(bytes) {
    const number = Number(bytes);
    return bytes != null && Number.isFinite(number)
        ? `${(number / 1024 ** 3).toFixed(1)} GiB`
        : "Unavailable";
}

function updateMacMemory(memory) {
    const breakdown = document.getElementById("macMemory");
    const pressure = document.getElementById("macMemPressure");
    breakdown.replaceChildren();
    pressure.classList.remove("temp-green", "temp-yellow", "temp-red");

    if (!memory) {
        setText("macMemUsed", "Unavailable");
        setText("macMemPressure", "Unavailable");
        setText("macSwap", "Unavailable");
        breakdown.textContent = "Memory data unavailable";
        return;
    }

    const percent = Number(memory.used_percent);
    setText(
        "macMemUsed",
        `${formatGiB(memory.used_bytes).replace(" GiB", "")} / ${formatGiB(memory.total_bytes)}` +
            (Number.isFinite(percent) ? ` (${Math.round(percent)}%)` : "")
    );

    const pressureClasses = {normal: "temp-green", warning: "temp-yellow", critical: "temp-red"};
    if (memory.pressure in pressureClasses) {
        pressure.textContent = memory.pressure[0].toUpperCase() + memory.pressure.slice(1);
        pressure.classList.add(pressureClasses[memory.pressure]);
    } else {
        pressure.textContent = "Unavailable";
    }

    setText("macSwap", formatGiB(memory.swap_used_bytes));

    [
        ["App", memory.app_bytes],
        ["Wired", memory.wired_bytes],
        ["Compressed", memory.compressed_bytes],
        ["Cached files", memory.cached_bytes]
    ].forEach(([label, bytes]) => breakdown.appendChild(gridItem(label, formatGiB(bytes))));
}

function updateMac(mac) {
    const card = document.getElementById("mac-card");
    if (!card) {
        return;
    }
    card.hidden = false;

    if (!mac) {
        setText("macCpu", "Unavailable");
        setText("macGpu", "Unavailable");
        setText("macGpuMem", "Unavailable");
        updateMacMemory(null);
        document.getElementById("macTemps").textContent = "Temperature data unavailable";
        document.getElementById("macStorage").textContent = "Storage I/O data unavailable";
        document.getElementById("macCores").replaceChildren();
        return;
    }

    setText("macTitle", mac.hostname ? `Mac · ${mac.hostname}` : "Mac");
    setText("macCpu", formatPercent(mac.cpu?.average_percent));
    setText("macGpu", formatPercent(mac.gpu?.device_util));

    const gpuMemory = Number(mac.gpu?.memory_in_use_bytes);
    setText(
        "macGpuMem",
        Number.isFinite(gpuMemory)
            ? `${(gpuMemory / 1024 / 1024).toFixed(0)} MiB`
            : "Unavailable"
    );

    updateMacMemory(mac.memory);

    const temps = document.getElementById("macTemps");
    temps.replaceChildren();
    const groups = mac.temperatures || [];
    if (groups.length === 0) {
        temps.textContent = "Temperature data unavailable";
    }
    groups.forEach(group => {
        // Show the group average; colour by its hottest sensor.
        const limits = macTemperatureLimits[group.label] || macTemperatureLimits.default;
        const hottest = Number(group.maximum_c);
        const item = gridItem(
            group.label,
            `${Math.round(group.average_c)} °C`,
            hottest >= limits.red ? "temp-red" : hottest >= limits.yellow ? "temp-yellow" : "temp-green"
        );
        item.title = `${group.sensors} sensor(s), hottest ${group.maximum_c.toFixed(1)} °C`;
        temps.appendChild(item);
    });

    const storage = document.getElementById("macStorage");
    storage.replaceChildren();
    const disks = Object.entries(mac.storage || {});
    if (disks.length === 0) {
        storage.textContent = "Storage I/O data unavailable";
    }
    disks.forEach(([name, disk]) => {
        const pool = document.createElement("div");
        pool.className = "poolItem";

        const title = document.createElement("h3");
        title.className = "poolName";
        title.textContent = `${name} · ${disk.model}`;
        pool.appendChild(title);

        [["Read", disk.read_bps], ["Write", disk.write_bps]].forEach(([labelText, bps]) => {
            const metric = document.createElement("div");
            metric.className = "metric";
            const label = document.createElement("span");
            label.textContent = labelText;
            const value = document.createElement("span");
            value.textContent = formatBytesPerSecond(bps);
            metric.append(label, value);
            pool.appendChild(metric);
        });

        storage.appendChild(pool);
    });

    const clusters = (mac.cpu?.clusters || [])
        .map(cluster => `${cluster.cores} ${cluster.name}`)
        .join(" · ");
    setText("macCoresTitle", clusters ? `Per-Core Utilization (${clusters})` : "Per-Core Utilization");

    const cores = document.getElementById("macCores");
    cores.replaceChildren();
    (mac.cpu?.per_cpu_percent || []).forEach((percent, index) => {
        cores.appendChild(gridItem(`CPU ${index}`, formatPercent(percent)));
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

        updateGpuProcesses(data.gpu_processes?.processes);

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

        // The key is absent when no Mac is configured; null means it failed.
        if ("mac" in data) {
            updateMac(data.mac);
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
