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
        if (tab.dataset.tab === 'settings') {
            loadConfig();
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

        // Update backend connection banner
        const banner = document.getElementById('backend-banner');
        if (data.data.backend && !data.data.backend.connected) {
            banner.classList.remove('hidden');
        } else {
            banner.classList.add('hidden');
        }

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

// --- Configuration ---

async function loadConfig() {
    const [configResp, pluginsResp] = await Promise.all([
        api('/api/config'),
        api('/api/config/plugins'),
    ]);

    if (configResp && configResp.data) {
        const cfg = configResp.data;

        // ZeDMD
        if (cfg.zedmd) {
            document.getElementById('cfg-wifi-addr').value = cfg.zedmd.wifi_addr || '';
            document.getElementById('cfg-brightness').value = cfg.zedmd.brightness || '10';
        }
        // Display
        if (cfg.display) {
            document.getElementById('cfg-font').value = cfg.display.font || 'STANDARD';
        }
        // Location
        if (cfg.location) {
            document.getElementById('cfg-latitude').value = cfg.location.latitude || '';
            document.getElementById('cfg-longitude').value = cfg.location.longitude || '';
            document.getElementById('cfg-city').value = cfg.location.city_name || '';
        }
        // Brightness schedule
        if (cfg.brightness_schedule) {
            document.getElementById('cfg-max-brightness').value = cfg.brightness_schedule.max_brightness || '7';
            document.getElementById('cfg-schedule-default').value = cfg.brightness_schedule.default || '';
            document.getElementById('cfg-sunrise-brightness').value = cfg.brightness_schedule.sunrise_brightness || '';
            document.getElementById('cfg-sunset-brightness').value = cfg.brightness_schedule.sunset_brightness || '';
        }
        // REST API
        if (cfg.rest_api) {
            document.getElementById('cfg-rest-enabled').checked = cfg.rest_api.enabled === 'true';
            document.getElementById('cfg-rest-port').value = cfg.rest_api.port || '8080';
        }
    }

    if (pluginsResp && pluginsResp.data) {
        const pCfg = pluginsResp.data;
        document.getElementById('cfg-clock-seconds').value = pCfg.clock_display_seconds || 5;
        renderPluginEntries(pCfg.plugins || []);
    }
}

function renderPluginEntries(plugins) {
    const container = document.getElementById('cfg-plugins-list');
    container.innerHTML = plugins.map((p, i) => `
        <div class="plugin-config-entry" data-index="${i}">
            <div class="form-row">
                <input type="text" class="plugin-name-input" value="${p.name || ''}" placeholder="Plugin name">
                <input type="number" class="plugin-freq-input" value="${p.frequency || 20}" min="0" max="100" title="Frequency %">
                <button class="btn btn-danger btn-small" onclick="removePluginEntry(${i})">✕</button>
            </div>
        </div>
    `).join('');
}

function addPluginEntry() {
    const container = document.getElementById('cfg-plugins-list');
    const i = container.children.length;
    const div = document.createElement('div');
    div.className = 'plugin-config-entry';
    div.dataset.index = i;
    div.innerHTML = `
        <div class="form-row">
            <input type="text" class="plugin-name-input" value="" placeholder="Plugin name">
            <input type="number" class="plugin-freq-input" value="20" min="0" max="100" title="Frequency %">
            <button class="btn btn-danger btn-small" onclick="removePluginEntry(${i})">✕</button>
        </div>
    `;
    container.appendChild(div);
}

function removePluginEntry(index) {
    const container = document.getElementById('cfg-plugins-list');
    const entry = container.querySelector(`[data-index="${index}"]`);
    if (entry) entry.remove();
}

async function saveConfig() {
    const statusEl = document.getElementById('config-status');
    statusEl.textContent = 'Saving...';

    // Build zeclock.ini structure
    const config = {};

    // ZeDMD section
    const wifiAddr = document.getElementById('cfg-wifi-addr').value.trim();
    const brightness = document.getElementById('cfg-brightness').value;
    if (wifiAddr || brightness) {
        config.zedmd = {};
        if (wifiAddr) config.zedmd.wifi_addr = wifiAddr;
        if (brightness) config.zedmd.brightness = brightness;
    }

    // Display section
    const font = document.getElementById('cfg-font').value;
    if (font) config.display = { font };

    // Location section
    const lat = document.getElementById('cfg-latitude').value.trim();
    const lng = document.getElementById('cfg-longitude').value.trim();
    const city = document.getElementById('cfg-city').value.trim();
    if (lat || lng || city) {
        config.location = {};
        if (lat) config.location.latitude = lat;
        if (lng) config.location.longitude = lng;
        if (city) config.location.city_name = city;
    }

    // Brightness schedule
    const maxBr = document.getElementById('cfg-max-brightness').value;
    const schedDefault = document.getElementById('cfg-schedule-default').value.trim();
    const sunriseBr = document.getElementById('cfg-sunrise-brightness').value.trim();
    const sunsetBr = document.getElementById('cfg-sunset-brightness').value.trim();
    if (maxBr || schedDefault || sunriseBr || sunsetBr) {
        config.brightness_schedule = {};
        if (maxBr) config.brightness_schedule.max_brightness = maxBr;
        if (schedDefault) config.brightness_schedule.default = schedDefault;
        if (sunriseBr) config.brightness_schedule.sunrise_brightness = sunriseBr;
        if (sunsetBr) config.brightness_schedule.sunset_brightness = sunsetBr;
    }

    // REST API
    const restEnabled = document.getElementById('cfg-rest-enabled').checked;
    const restPort = document.getElementById('cfg-rest-port').value;
    config.rest_api = {
        enabled: restEnabled ? 'true' : 'false',
        host: '0.0.0.0',
        port: restPort,
    };

    // Build plugins.yaml structure
    const pluginsConfig = {
        clock_display_seconds: parseInt(document.getElementById('cfg-clock-seconds').value) || 5,
        plugins: [],
    };

    document.querySelectorAll('.plugin-config-entry').forEach(entry => {
        const name = entry.querySelector('.plugin-name-input').value.trim();
        const freq = parseInt(entry.querySelector('.plugin-freq-input').value) || 20;
        if (name) {
            pluginsConfig.plugins.push({ name, frequency: freq, settings: {} });
        }
    });

    // Save both configs
    const [configResult, pluginsResult] = await Promise.all([
        api('/api/config', 'POST', config),
        api('/api/config/plugins', 'POST', pluginsConfig),
    ]);

    if (configResult?.success && pluginsResult?.success) {
        statusEl.textContent = '✅ Configuration saved. Restart zeClock to apply.';
        statusEl.style.color = '#4caf50';
    } else {
        const msg = configResult?.message || pluginsResult?.message || 'Unknown error';
        statusEl.textContent = '❌ Error: ' + msg;
        statusEl.style.color = '#f44336';
    }
}

init();
