const pollInterval = Number(document.body.dataset.pollInterval || 750);
let lastLogSequence = 0;
let visibleLogs = [];
let activeMode = null;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function showToast(message, isError = false) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("visible");
    window.setTimeout(() => toast.classList.remove("visible"), 2600);
}

async function api(path, options = {}) {
    const response = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || `Request failed: ${response.status}`);
    }
    return data;
}

function boolText(value, yes = "Yes", no = "No") {
    return value ? yes : no;
}

async function loadModes() {
    const data = await api("/api/modes");
    const container = $("#mode-buttons");
    container.replaceChildren();
    for (const mode of data.modes) {
        const button = document.createElement("button");
        button.className = "mode-button";
        button.disabled = !mode.enabled;
        button.dataset.mode = mode.name;
        button.innerHTML = `<strong>${mode.label}</strong><small>${mode.enabled ? mode.description : mode.disabled_reason}</small>`;
        button.addEventListener("click", () => sendMode(mode.name));
        container.appendChild(button);
    }
}

async function loadMedia() {
    const data = await api("/api/media");
    const select = $("#media-select");
    select.replaceChildren();
    if (!data.media.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No .mp3 or .wav files found";
        select.appendChild(option);
        return;
    }
    for (const filename of data.media) {
        const option = document.createElement("option");
        option.value = filename;
        option.textContent = filename;
        select.appendChild(option);
    }
}

async function sendMode(mode) {
    try {
        await api(`/api/mode/${encodeURIComponent(mode)}`, { method: "POST" });
    } catch (error) {
        showToast(error.message, true);
    }
}

async function post(path, body) {
    try {
        await api(path, {
            method: "POST",
            body: body === undefined ? undefined : JSON.stringify(body),
        });
    } catch (error) {
        showToast(error.message, true);
    }
}

function renderStatus(status) {
    activeMode = status.mode;
    $("#mode").textContent = status.mode_label || status.mode;
    $("#state").textContent = status.state;
    $("#message").textContent = status.message;
    $("#expects-input").textContent = boolText(status.expects_input, "Expecting input", "Not expecting input");
    $("#microphone").textContent = `Microphone: ${boolText(status.microphone_active, "active", "inactive")}`;

    const bt = status.bluetooth;
    const btState = bt.connected ? "Connected" : bt.pairing ? "Pairing" : bt.enabled ? "Enabled" : "Off";
    $("#bluetooth-state").textContent = btState;
    $("#bluetooth-device").textContent = `Device: ${bt.device || "—"}`;

    $("#internet").textContent = `Internet: ${boolText(status.system.internet, "online", "offline")}`;
    $("#battery").textContent = `Battery: ${status.system.battery_percent ?? "not available on PC"}`;
    $("#audio-status").textContent = status.audio.playing
        ? `Audio: simulating ${status.audio.track}`
        : "Audio: stopped";

    const pill = $("#engine-pill");
    pill.textContent = status.engine_running ? "Engine running" : "Engine stopped";
    pill.className = `pill ${status.engine_running ? "ok" : "error"}`;

    $$(".mode-button").forEach((button) => {
        button.classList.toggle("active", button.dataset.mode === activeMode);
    });
}

async function pollStatus() {
    try {
        renderStatus(await api("/api/status"));
    } catch (error) {
        showToast(error.message, true);
    }
}

async function pollLogs() {
    try {
        const data = await api(`/api/logs?after=${lastLogSequence}&limit=200`);
        if (data.entries.length) {
            lastLogSequence = data.entries.at(-1).sequence;
            visibleLogs.push(...data.entries.map((entry) => entry.message));
            visibleLogs = visibleLogs.slice(-400);
            const logs = $("#logs");
            logs.textContent = visibleLogs.join("\n");
            logs.scrollTop = logs.scrollHeight;
        }
    } catch (error) {
        console.error(error);
    }
}

$$('[data-command="force-next"]').forEach((button) =>
    button.addEventListener("click", () => post("/api/force-next"))
);
$$('[data-command="reset-mode"]').forEach((button) =>
    button.addEventListener("click", () => post("/api/reset-mode"))
);
$$('[data-button-id]').forEach((button) =>
    button.addEventListener("click", () => post(`/api/simulate/button/${button.dataset.buttonId}`))
);

$("#connect-bluetooth").addEventListener("click", () =>
    post("/api/simulate/bluetooth/connect", { device: $("#device-name").value || "Test phone" })
);
$("#disconnect-bluetooth").addEventListener("click", () =>
    post("/api/simulate/bluetooth/disconnect")
);
$("#play-media").addEventListener("click", () => {
    const track = $("#media-select").value;
    if (!track) return showToast("Add an .mp3 or .wav file to the media folder first", true);
    post("/api/audio/play", { track });
});
$("#stop-media").addEventListener("click", () => post("/api/audio/stop"));
$("#clear-visible-logs").addEventListener("click", () => {
    visibleLogs = [];
    $("#logs").textContent = "";
});

Promise.all([loadModes(), loadMedia(), pollStatus(), pollLogs()]).catch((error) => showToast(error.message, true));
window.setInterval(pollStatus, pollInterval);
window.setInterval(pollLogs, pollInterval);
