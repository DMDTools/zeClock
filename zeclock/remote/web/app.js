// zeClock Web UI - Application logic

const API_BASE = window.location.origin;
let timerInterval = null;
let statusInterval = null;

// --- Tab navigation ---

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('tab-' + tab.dataset.tab).classList.add('active');

        // Start/stop polling based on active tab
        if (tab.dataset.tab === 'speaker-timer') {
            startTimerPolling();
        } else {
            stopTimerPolling();
        }
    });
});

// --- Generic API call ---

async function api(endpoint, method = 'GET', body = null) {
    const opts = { method };
    if (body) {
        opts.headers = { 'Content-Type': 'application/json' };
        opts.body = JSON.stringify(body);
    }
    try {
        const resp = await fetch(API_BASE + endpoint, opts);
        const data = await resp.json();
        updateConnectionStatus(true);
        return data;
    } catch (err) {
        console.error('API error:', err);
        updateConnectionStatus(false);
        return null;
    }
}

function updateConnectionStatus(connected) {
    const dot = document.getElementById('connection-status');
    dot.classList.toggle('connected', connected);
    dot.title = connected ? 'Connected' : 'Disconnected';
}

// --- Dashboard ---

async function refreshStatus() {
    const data = await api('/api/status');
    if (data && data.data) {
        document.getElementById('status-display').textContent = JSON.stringify(data.data, null, 2);
        // Update brightness display
        const br = data.data.brightness;
        if (br) {
            const mode = br.override !== null ? `manual (${br.override}/15)` : 'auto';
            document.getElementById('brightness-mode').textContent = `Mode: ${mode}`;
            if (br.override !== null) {
                document.getElementById('brightness-slider').value = br.override;
                document.getElementById('brightness-value').textContent = br.override;
            }
        }
    }
}

function updateBrightnessLabel(val) {
    document.getElementById('brightness-value').textContent = val;
}

async function setBrightness() {
    const val = parseInt(document.getElementById('brightness-slider').value);
    await api('/api/brightness', 'POST', { brightness: val });
    refreshStatus();
}

async function setBrightnessAuto() {
    await api('/api/brightness/auto', 'POST');
    refreshStatus();
}

async function refreshPlugins() {
    const data = await api('/api/plugins');
    if (!data || !data.data) return;

    const container = document.getElementById('plugins-list');
    const plugins = data.data.plugins;
    const activePlugin = data.data.active_plugin;
    const forcedPlugin = data.data.forced_plugin;

    if (!plugins.length) {
        container.innerHTML = '<p class="muted">No plugins available</p>';
        return;
    }

    container.innerHTML = plugins.map(p => {
        const isActive = p.name === activePlugin || p.name === forcedPlugin;
        return `
            <div class="plugin-btn ${isActive ? 'active' : ''}" onclick="forcePlugin('${p.name}')">
                <span class="plugin-name">${p.name}</span>
                <span class="plugin-desc">${p.description || ''}</span>
            </div>
        `;
    }).join('');
}

async function forcePlugin(name) {
    await api('/api/plugin/force', 'POST', { plugin: name });
    setTimeout(refreshPlugins, 500);
}

// --- Speaker Timer ---

async function timerStart() {
    await api('/api/speaker-timer/start', 'POST');
    refreshTimerStatus();
}

async function timerPause() {
    await api('/api/speaker-timer/pause', 'POST');
    refreshTimerStatus();
}

async function timerReset() {
    await api('/api/speaker-timer/reset', 'POST');
    refreshTimerStatus();
}

async function timerSet(seconds) {
    await api('/api/speaker-timer/set', 'POST', { seconds });
    refreshTimerStatus();
}

function timerSetCustom() {
    const minutes = parseInt(document.getElementById('custom-minutes').value);
    if (minutes > 0) {
        timerSet(minutes * 60);
    }
}

async function refreshTimerStatus() {
    const data = await api('/api/speaker-timer/status');
    if (!data || !data.data) return;

    const timer = data.data;
    const display = document.getElementById('timer-display');
    const stateEl = document.getElementById('timer-state');

    display.textContent = timer.formatted;
    stateEl.textContent = timer.state.toUpperCase();

    // Update color class
    display.className = 'timer-display';
    if (timer.state === 'idle') {
        display.classList.add('idle');
    } else if (timer.remaining <= 0) {
        display.classList.add('red');
    } else if (timer.remaining <= timer.red_threshold) {
        display.classList.add('red');
    } else if (timer.remaining <= timer.yellow_threshold) {
        display.classList.add('yellow');
    } else {
        display.classList.add('green');
    }

    // Update presets from server
    if (timer.presets && timer.presets.length) {
        const presetsContainer = document.getElementById('timer-presets');
        presetsContainer.innerHTML = timer.presets.map(p => {
            const label = p.duration >= 3600
                ? `${Math.floor(p.duration / 3600)}h${p.duration % 3600 ? Math.floor((p.duration % 3600) / 60) + 'm' : ''}`
                : `${Math.floor(p.duration / 60)} min`;
            return `<button class="btn btn-secondary" onclick="timerSet(${p.duration})">${p.name} (${label})</button>`;
        }).join('');
    }
}

function startTimerPolling() {
    stopTimerPolling();
    refreshTimerStatus();
    timerInterval = setInterval(refreshTimerStatus, 1000);
}

function stopTimerPolling() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
}

// --- Message ---

async function sendMessage() {
    const text = document.getElementById('message-text').value.trim();
    const duration = parseInt(document.getElementById('message-duration').value) || 10;

    if (!text) {
        alert('Please enter a message');
        return;
    }

    await api('/api/text', 'POST', { text, duration });
    document.getElementById('message-text').value = '';
}

async function quickMessage(text) {
    const duration = parseInt(document.getElementById('message-duration').value) || 10;
    await api('/api/text', 'POST', { text, duration });
}

// --- Speaker Message (from timer tab) ---

async function sendSpeakerMessage() {
    const text = document.getElementById('speaker-message-text').value.trim();
    if (!text) return;
    await api('/api/text', 'POST', { text, duration: 10 });
    document.getElementById('speaker-message-text').value = '';
}

async function quickSpeakerMessage(text) {
    await api('/api/text', 'POST', { text, duration: 10 });
}

// --- Initialization ---

async function init() {
    await refreshStatus();
    await refreshPlugins();

    // Refresh status every 10 seconds
    statusInterval = setInterval(() => {
        refreshStatus();
        refreshPlugins();
    }, 10000);
}

// Handle Enter key in message inputs
document.getElementById('message-text').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
});
document.getElementById('speaker-message-text').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendSpeakerMessage();
});

init();
