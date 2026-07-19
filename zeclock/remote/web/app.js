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
            pollDiscovery();
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

async function pollDiscovery() {
    const data = await api('/api/discovery');
    if (!data || !data.data) return;

    const disc = data.data;
    const log = document.getElementById('discovery-log');
    const bannerText = document.querySelector('.banner-text');

    // Update banner text
    if (disc.status === 'found') {
        bannerText.textContent = `✅ ${disc.message}`;
    } else if (disc.message) {
        bannerText.textContent = disc.message;
    }

    // Update discovery log with steps
    if (disc.steps && disc.steps.length > 0) {
        const lastShown = log.dataset.lastCount || 0;
        if (disc.steps.length > lastShown) {
            log.innerHTML = disc.steps.map((step, i) => {
                const cls = i === disc.steps.length - 1 ? 'step active' :
                           step.includes('found') || step.includes('connected') ? 'step found' : 'step';
                return `<div class="${cls}">${step}</div>`;
            }).join('');
            log.dataset.lastCount = disc.steps.length;
            log.scrollTop = log.scrollHeight;
        }
    }

    // Keep polling fast while discovery is active
    if (disc.status !== 'found' && disc.status !== 'idle') {
        setTimeout(pollDiscovery, 2000);
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

    // Load and render auto-generated plugin config forms
    await loadPluginConfigForms(pluginsResp && pluginsResp.data);

    // Initialize location autocomplete for global settings
    initLocationAutocomplete();
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

// --- Plugin Configuration Forms (auto-generated from schema) ---

async function loadPluginConfigForms(currentPluginsConfig) {
    const schemaResp = await api('/api/plugins/config-schema');
    if (!schemaResp || !schemaResp.plugins) return;

    const container = document.getElementById('plugin-config-forms');
    const plugins = schemaResp.plugins.filter(p => p.schema && p.schema.length > 0);

    if (plugins.length === 0) {
        container.innerHTML = '';
        return;
    }

    // Get current settings from plugins.yaml for pre-filling form values
    const currentSettings = {};
    if (currentPluginsConfig && currentPluginsConfig.plugins) {
        currentPluginsConfig.plugins.forEach(p => {
            if (p.name && p.settings) {
                currentSettings[p.name] = p.settings;
            }
        });
    }

    container.innerHTML = plugins.map(plugin => {
        const settings = currentSettings[plugin.name] || {};
        const fieldsHtml = plugin.schema.map(field => renderPluginField(plugin.name, field, settings)).join('');

        return `
            <div class="plugin-config-card" data-plugin="${plugin.name}">
                <h2>${capitalize(plugin.name)}</h2>
                <p class="plugin-description">${plugin.description || ''}</p>
                ${fieldsHtml}
                <button class="btn btn-accent btn-save-plugin" onclick="savePluginConfig('${plugin.name}')">Save ${capitalize(plugin.name)} Settings</button>
            </div>
        `;
    }).join('');

    // Initialize location autocomplete handlers after forms are rendered
    initLocationAutocomplete();
    initBooleanToggles();
}

function renderPluginField(pluginName, field, settings) {
    const currentValue = settings[field.name] || field.default || '';
    const requiredAttr = field.required ? 'required' : '';
    const fieldId = `plugin-cfg-${pluginName}-${field.name}`;
    let inputHtml = '';
    let hintHtml = '';

    // Special handling for gif_dirs field
    if (pluginName === 'gif' && field.name === 'gif_dirs') {
        return renderGifDirsField(fieldId, currentValue, field);
    }

    switch (field.field_type) {
        case 'boolean':
            const isChecked = parseBoolValue(currentValue);
            inputHtml = `
                <label class="toggle-switch" for="${fieldId}">
                    <input type="checkbox" id="${fieldId}" ${isChecked ? 'checked' : ''} data-plugin="${pluginName}" data-field="${field.name}" data-field-type="boolean">
                    <span class="toggle-slider"></span>
                    <span class="toggle-label">${isChecked ? 'Oui' : 'Non'}</span>
                </label>`;
            break;
        case 'number':
            inputHtml = `<input type="number" id="${fieldId}" value="${currentValue}" ${requiredAttr} data-plugin="${pluginName}" data-field="${field.name}">`;
            break;
        case 'list':
            inputHtml = `<input type="text" id="${fieldId}" value="${Array.isArray(currentValue) ? currentValue.join(', ') : currentValue}" ${requiredAttr} data-plugin="${pluginName}" data-field="${field.name}">`;
            hintHtml = `<div class="field-hint">Comma-separated values</div>`;
            break;
        case 'city':
            inputHtml = `<div class="location-input-wrapper"><input type="text" id="${fieldId}" value="${getLocationDisplayValue(currentValue)}" ${requiredAttr} data-plugin="${pluginName}" data-field="${field.name}" data-field-type="city" class="location-autocomplete-input" autocomplete="off"><div class="location-coords" id="${fieldId}-coords">${getLocationCoordsText(currentValue)}</div></div>`;
            break;
        case 'location':
            inputHtml = `<div class="location-input-wrapper"><input type="text" id="${fieldId}" value="${getLocationDisplayValue(currentValue)}" ${requiredAttr} data-plugin="${pluginName}" data-field="${field.name}" data-field-type="location" class="location-autocomplete-input" autocomplete="off" placeholder="Start typing a city or address..."><div class="location-coords" id="${fieldId}-coords">${getLocationCoordsText(currentValue)}</div></div>`;
            break;
        default: // text
            inputHtml = `<input type="text" id="${fieldId}" value="${currentValue}" ${requiredAttr} data-plugin="${pluginName}" data-field="${field.name}">`;
            break;
    }

    const descriptionHtml = field.description ? `<div class="field-description">${field.description}</div>` : '';

    return `
        <div class="form-group">
            <label for="${fieldId}">${field.label}${field.required ? ' *' : ''}</label>
            ${inputHtml}
            ${hintHtml}
            ${descriptionHtml}
        </div>
    `;
}

function parseBoolValue(value) {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
        return ['yes', 'true', '1', 'on'].includes(value.toLowerCase().trim());
    }
    return false;
}

// --- GIF Directories Editor ---

function renderGifDirsField(fieldId, currentValue, field) {
    const dirs = Array.isArray(currentValue) ? currentValue : [];

    return `
        <div class="form-group gif-dirs-editor" id="${fieldId}" data-plugin="gif" data-field="gif_dirs" data-field-type="gif_dirs">
            <label>${field.label} *</label>
            <div class="field-description">${field.description || ''}</div>
            <div id="gif-dirs-list" class="gif-dirs-list">
                ${dirs.map((dir, i) => renderGifDirEntry(dir, i)).join('')}
            </div>
            <div class="gif-dirs-actions">
                <button type="button" class="btn btn-secondary" onclick="addGifDirEntry()">+ Add Directory</button>
                <button type="button" class="btn btn-secondary" onclick="showNewDirDialog()">📁 Create New Directory</button>
                <button type="button" class="btn btn-secondary" onclick="refreshGifDirs()">🔄 Refresh</button>
            </div>
            <div id="gif-dirs-status" class="muted" style="margin-top: 0.5rem;"></div>
        </div>
    `;
}

function renderGifDirEntry(dir, index) {
    const path = dir.path || '';
    const weight = dir.weight || 50;
    const recursive = dir.recursive !== false; // default true

    return `
        <div class="gif-dir-entry" data-index="${index}">
            <div class="gif-dir-header">
                <span class="gif-dir-title">${path ? path.split('/').pop() || path : 'New directory'}</span>
                <button type="button" class="btn btn-danger btn-small" onclick="removeGifDirEntry(${index})" title="Remove">✕</button>
            </div>
            <div class="gif-dir-fields">
                <div class="gif-dir-field">
                    <label>Path</label>
                    <div class="gif-dir-path-row">
                        <input type="text" class="gif-dir-path" value="${escapeHtml(path)}" placeholder="/path/to/gif/directory" data-index="${index}">
                        <button type="button" class="btn btn-secondary btn-small" onclick="browseGifDirs(${index})" title="Browse existing directories">📂</button>
                    </div>
                </div>
                <div class="gif-dir-field gif-dir-field-inline">
                    <div class="gif-dir-weight">
                        <label>Weight: <span class="weight-value">${weight}</span></label>
                        <input type="range" class="gif-dir-weight-slider" min="1" max="100" value="${weight}" data-index="${index}" oninput="updateGifDirWeightLabel(this)">
                    </div>
                    <div class="gif-dir-recursive">
                        <label><input type="checkbox" class="gif-dir-recursive-cb" ${recursive ? 'checked' : ''} data-index="${index}"> Recursive</label>
                    </div>
                </div>
            </div>
            <div class="gif-dir-upload">
                <div class="gif-upload-area" data-index="${index}" onclick="triggerGifUpload(${index})" ondragover="handleDragOver(event)" ondrop="handleDrop(event, ${index})">
                    <span class="upload-icon">📤</span>
                    <span class="upload-text">Drop GIF files here or click to upload</span>
                    <input type="file" class="gif-file-input" data-index="${index}" accept=".gif" multiple onchange="handleGifFileSelect(event, ${index})" style="display:none">
                </div>
                <div class="gif-upload-progress" data-index="${index}"></div>
            </div>
        </div>
    `;
}

function updateGifDirWeightLabel(slider) {
    const label = slider.closest('.gif-dir-weight').querySelector('.weight-value');
    label.textContent = slider.value;
}

function addGifDirEntry() {
    const list = document.getElementById('gif-dirs-list');
    const index = list.children.length;
    const html = renderGifDirEntry({ path: '', weight: 50, recursive: true }, index);
    list.insertAdjacentHTML('beforeend', html);
}

function removeGifDirEntry(index) {
    const entry = document.querySelector(`.gif-dir-entry[data-index="${index}"]`);
    if (entry) entry.remove();
    // Re-index remaining entries
    reindexGifDirEntries();
}

function reindexGifDirEntries() {
    const entries = document.querySelectorAll('.gif-dir-entry');
    entries.forEach((entry, i) => {
        entry.dataset.index = i;
        entry.querySelectorAll('[data-index]').forEach(el => el.dataset.index = i);
        // Update onclick handlers
        const removeBtn = entry.querySelector('.btn-danger');
        if (removeBtn) removeBtn.setAttribute('onclick', `removeGifDirEntry(${i})`);
        const browseBtn = entry.querySelector('[title="Browse existing directories"]');
        if (browseBtn) browseBtn.setAttribute('onclick', `browseGifDirs(${i})`);
        const uploadArea = entry.querySelector('.gif-upload-area');
        if (uploadArea) {
            uploadArea.setAttribute('onclick', `triggerGifUpload(${i})`);
            uploadArea.setAttribute('ondrop', `handleDrop(event, ${i})`);
        }
        const fileInput = entry.querySelector('.gif-file-input');
        if (fileInput) fileInput.setAttribute('onchange', `handleGifFileSelect(event, ${i})`);
    });
}

// --- GIF Upload handlers ---

function triggerGifUpload(index) {
    const input = document.querySelector(`.gif-file-input[data-index="${index}"]`);
    if (input) input.click();
}

function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.add('drag-over');
}

function handleDrop(event, index) {
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.classList.remove('drag-over');
    const files = event.dataTransfer.files;
    if (files.length > 0) {
        uploadGifFiles(files, index);
    }
}

function handleGifFileSelect(event, index) {
    const files = event.target.files;
    if (files.length > 0) {
        uploadGifFiles(files, index);
    }
}

async function uploadGifFiles(files, index) {
    const entry = document.querySelector(`.gif-dir-entry[data-index="${index}"]`);
    const pathInput = entry.querySelector('.gif-dir-path');
    const progressEl = entry.querySelector('.gif-upload-progress');

    // Determine target directory from path or create one
    let dirPath = pathInput.value.trim();
    let dirName = '';

    if (dirPath) {
        // Extract directory name from path
        dirName = dirPath.split('/').pop() || '';
    }

    const formData = new FormData();
    if (dirName) {
        formData.append('directory', dirName);
    }

    let gifCount = 0;
    for (const file of files) {
        if (file.name.toLowerCase().endsWith('.gif')) {
            formData.append('files', file);
            gifCount++;
        }
    }

    if (gifCount === 0) {
        progressEl.innerHTML = '<span style="color: var(--danger);">No valid GIF files selected</span>';
        setTimeout(() => progressEl.innerHTML = '', 3000);
        return;
    }

    progressEl.innerHTML = `<span style="color: var(--accent);">Uploading ${gifCount} file(s)...</span>`;

    try {
        const resp = await fetch(API_BASE + '/api/gif/upload', {
            method: 'POST',
            body: formData,
        });
        const result = await resp.json();

        if (result.success) {
            progressEl.innerHTML = `<span style="color: var(--success);">✅ ${result.message}</span>`;
            // If path was empty, set it from the upload result
            if (!pathInput.value.trim() && result.data && result.data.uploaded && result.data.uploaded.length > 0) {
                const uploadedPath = result.data.uploaded[0].path;
                const dir = uploadedPath.substring(0, uploadedPath.lastIndexOf('/'));
                pathInput.value = dir;
                // Update title
                entry.querySelector('.gif-dir-title').textContent = dir.split('/').pop();
            }
        } else {
            progressEl.innerHTML = `<span style="color: var(--danger);">❌ ${result.message}</span>`;
        }

        if (result.data && result.data.errors && result.data.errors.length > 0) {
            progressEl.innerHTML += `<br><span style="color: var(--warning); font-size: 0.8rem;">${result.data.errors.join(', ')}</span>`;
        }
    } catch (err) {
        progressEl.innerHTML = `<span style="color: var(--danger);">❌ Upload failed: ${err.message}</span>`;
    }

    setTimeout(() => {
        if (progressEl) progressEl.innerHTML = '';
    }, 5000);
}

// --- Browse/Refresh GIF directories ---

async function browseGifDirs(index) {
    const data = await api('/api/gif/directories');
    if (!data || !data.data) return;

    const dirs = data.data.directories || [];
    const entry = document.querySelector(`.gif-dir-entry[data-index="${index}"]`);
    const pathInput = entry.querySelector('.gif-dir-path');

    if (dirs.length === 0) {
        showGifDirsStatus('No existing directories found. Upload some GIFs first!');
        return;
    }

    // Show a simple dropdown-style picker
    const existing = entry.querySelector('.gif-dir-browse-dropdown');
    if (existing) { existing.remove(); return; }

    const dropdown = document.createElement('div');
    dropdown.className = 'gif-dir-browse-dropdown';
    dropdown.innerHTML = dirs.map(d =>
        `<div class="gif-dir-browse-item" data-path="${escapeHtml(d.path)}">
            <span class="dir-name">${escapeHtml(d.name)}</span>
            <span class="dir-count">${d.gif_count} GIF${d.gif_count !== 1 ? 's' : ''}</span>
        </div>`
    ).join('');

    dropdown.querySelectorAll('.gif-dir-browse-item').forEach(item => {
        item.addEventListener('click', () => {
            pathInput.value = item.dataset.path;
            entry.querySelector('.gif-dir-title').textContent = item.querySelector('.dir-name').textContent;
            dropdown.remove();
        });
    });

    pathInput.closest('.gif-dir-path-row').appendChild(dropdown);

    // Close on outside click
    setTimeout(() => {
        document.addEventListener('click', function closeDropdown(e) {
            if (!dropdown.contains(e.target)) {
                dropdown.remove();
                document.removeEventListener('click', closeDropdown);
            }
        });
    }, 0);
}

async function refreshGifDirs() {
    const data = await api('/api/gif/directories');
    if (!data || !data.data) return;
    showGifDirsStatus(`Found ${data.data.directories.length} director${data.data.directories.length === 1 ? 'y' : 'ies'} in ${data.data.base_path}`);
}

async function showNewDirDialog() {
    const name = prompt('Enter a name for the new GIF directory:');
    if (!name || !name.trim()) return;

    const result = await api('/api/gif/directories/create', 'POST', { name: name.trim() });
    if (result && result.success) {
        showGifDirsStatus(`✅ Directory '${result.data.name}' created at ${result.data.path}`);
        // Add an entry for this new directory
        const list = document.getElementById('gif-dirs-list');
        const index = list.children.length;
        const html = renderGifDirEntry({ path: result.data.path, weight: 50, recursive: true }, index);
        list.insertAdjacentHTML('beforeend', html);
    } else {
        showGifDirsStatus(`❌ ${result?.message || 'Failed to create directory'}`);
    }
}

function showGifDirsStatus(message) {
    const el = document.getElementById('gif-dirs-status');
    if (el) {
        el.textContent = message;
        setTimeout(() => el.textContent = '', 5000);
    }
}

// --- Collect gif_dirs data for saving ---

function collectGifDirsData() {
    const entries = document.querySelectorAll('.gif-dir-entry');
    const dirs = [];
    entries.forEach(entry => {
        const path = entry.querySelector('.gif-dir-path').value.trim();
        if (!path) return; // skip empty entries
        const weight = parseInt(entry.querySelector('.gif-dir-weight-slider').value) || 50;
        const recursive = entry.querySelector('.gif-dir-recursive-cb').checked;
        dirs.push({ path, weight, recursive });
    });
    return dirs;
}

function getLocationDisplayValue(value) {
    if (!value) return '';
    if (typeof value === 'object' && value.display_name) return value.display_name;
    if (typeof value === 'string') return value;
    return '';
}

function getLocationCoordsText(value) {
    if (!value) return '';
    if (typeof value === 'object' && value.latitude != null && value.longitude != null) {
        return `📍 ${value.latitude.toFixed(4)}, ${value.longitude.toFixed(4)}${value.country ? ' — ' + value.country : ''}`;
    }
    return '';
}

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

async function savePluginConfig(pluginName) {
    // First, get the current plugins.yaml content
    const pluginsResp = await api('/api/config/plugins');
    if (!pluginsResp || !pluginsResp.data) {
        showPluginSaveStatus(pluginName, false, 'Failed to load current config');
        return;
    }

    const pluginsConfig = pluginsResp.data;
    if (!pluginsConfig.plugins) {
        pluginsConfig.plugins = [];
    }

    // Find the plugin entry or create one
    let pluginEntry = pluginsConfig.plugins.find(p => p.name === pluginName);
    if (!pluginEntry) {
        pluginEntry = { name: pluginName, frequency: 20, settings: {} };
        pluginsConfig.plugins.push(pluginEntry);
    }
    if (!pluginEntry.settings) {
        pluginEntry.settings = {};
    }

    // Collect form values for this plugin
    const card = document.querySelector(`.plugin-config-card[data-plugin="${pluginName}"]`);
    const inputs = card.querySelectorAll('[data-field]');

    inputs.forEach(input => {
        const fieldName = input.dataset.field;
        const fieldType = input.dataset.fieldType;

        // Skip child elements inside gif-dirs-editor (they don't have data-field directly)
        if (input.closest('.gif-dirs-editor') && !input.classList.contains('gif-dirs-editor')) {
            return;
        }

        if (fieldType === 'gif_dirs') {
            // gif_dirs is handled separately via collectGifDirsData()
            pluginEntry.settings[fieldName] = collectGifDirsData();
        } else if (fieldType === 'boolean') {
            // Boolean toggle: store as "yes"/"no"
            pluginEntry.settings[fieldName] = input.checked ? 'yes' : 'no';
        } else {
            let value = (input.value || '').trim();
            if (fieldType === 'city' || fieldType === 'location') {
                // For location/city fields, store the full location object with coordinates
                if (input._locationData) {
                    pluginEntry.settings[fieldName] = input._locationData;
                } else if (input._cityData) {
                    pluginEntry.settings[fieldName] = input._cityData;
                } else {
                    pluginEntry.settings[fieldName] = value;
                }
            } else if (input.type === 'number') {
                pluginEntry.settings[fieldName] = value ? Number(value) : null;
            } else {
                pluginEntry.settings[fieldName] = value || null;
            }
        }
    });

    // Save via POST /api/config/plugins
    const result = await api('/api/config/plugins', 'POST', pluginsConfig);

    if (result && result.success) {
        showPluginSaveStatus(pluginName, true, 'Settings saved and applied.');
    } else {
        const msg = result?.message || 'Unknown error';
        showPluginSaveStatus(pluginName, false, msg);
    }
}

// --- Boolean Toggle Switches ---

function initBooleanToggles() {
    const toggleInputs = document.querySelectorAll('.toggle-switch input[type="checkbox"]');
    toggleInputs.forEach(input => {
        input.addEventListener('change', function() {
            const label = this.closest('.toggle-switch').querySelector('.toggle-label');
            if (label) {
                label.textContent = this.checked ? 'Oui' : 'Non';
            }
        });
    });
}

// --- Location Autocomplete (shared service for "location" field type) ---

let locationAutocompleteTimeout = null;
let _locationAutocompleteDocClickBound = false;

function initLocationAutocomplete() {
    const locationInputs = document.querySelectorAll('.location-autocomplete-input');
    locationInputs.forEach(input => {
        // Prevent duplicate listeners by marking initialized inputs
        if (input._locationAutocompleteInit) return;
        input._locationAutocompleteInit = true;
        input.addEventListener('input', handleLocationInput);
        input.addEventListener('keydown', handleLocationKeydown);
    });

    // Close dropdowns when clicking outside — bind only once
    if (!_locationAutocompleteDocClickBound) {
        _locationAutocompleteDocClickBound = true;
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.location-input-wrapper')) {
                closeLocationDropdowns();
            }
        });
    }
}

function handleLocationInput(e) {
    const input = e.target;
    const query = input.value.trim();

    // Clear any pending debounce
    if (locationAutocompleteTimeout) {
        clearTimeout(locationAutocompleteTimeout);
        locationAutocompleteTimeout = null;
    }

    // Clear stored location data when user types (selection invalidated)
    input._locationData = null;
    input._cityData = null;
    // Clear coordinates display
    const coordsEl = input.closest('.location-input-wrapper')?.querySelector('.location-coords');
    if (coordsEl) coordsEl.textContent = '';

    // Only search if 3+ characters
    if (query.length < 3) {
        removeLocationDropdown(input);
        return;
    }

    // Debounce: wait 300ms after last keystroke
    locationAutocompleteTimeout = setTimeout(() => {
        searchLocations(input, query);
    }, 300);
}

function handleLocationKeydown(e) {
    if (e.key === 'Escape') {
        removeLocationDropdown(e.target);
    }
}

async function searchLocations(input, query) {
    const data = await api(`/api/geocode/search?q=${encodeURIComponent(query)}`);

    if (!data || !data.results) {
        showLocationDropdown(input, []);
        return;
    }

    showLocationDropdown(input, data.results);
}

function showLocationDropdown(input, results) {
    const wrapper = input.closest('.location-input-wrapper');
    if (!wrapper) return;

    // Remove existing dropdown
    removeLocationDropdown(input);

    const dropdown = document.createElement('div');
    dropdown.className = 'location-autocomplete-dropdown';

    if (results.length === 0) {
        dropdown.innerHTML = '<div class="location-autocomplete-no-results">No results found</div>';
    } else {
        const items = results.slice(0, 5);
        dropdown.innerHTML = items.map((result, index) => `
            <div class="location-autocomplete-item" data-index="${index}">
                <span class="location-item-name">${escapeHtml(result.display_name)}</span>
                <span class="location-item-coords">${result.latitude.toFixed(4)}, ${result.longitude.toFixed(4)}</span>
            </div>
        `).join('');

        // Attach click handlers to items
        dropdown.querySelectorAll('.location-autocomplete-item').forEach((item, index) => {
            item.addEventListener('click', () => {
                selectLocation(input, items[index]);
            });
        });
    }

    wrapper.appendChild(dropdown);
}

function selectLocation(input, result) {
    input.value = result.display_name;
    const locationData = {
        display_name: result.display_name,
        latitude: result.latitude,
        longitude: result.longitude,
        country: result.country
    };
    input._locationData = locationData;
    input._cityData = locationData;

    // Update coordinates display
    const coordsEl = input.closest('.location-input-wrapper')?.querySelector('.location-coords');
    if (coordsEl) {
        coordsEl.textContent = `📍 ${result.latitude.toFixed(4)}, ${result.longitude.toFixed(4)}${result.country ? ' — ' + result.country : ''}`;
    }

    // If this is the global location field, auto-fill lat/lon/city fields
    if (input.id === 'cfg-location-search') {
        document.getElementById('cfg-latitude').value = result.latitude.toFixed(6);
        document.getElementById('cfg-longitude').value = result.longitude.toFixed(6);
        document.getElementById('cfg-city').value = result.display_name.split(',')[0].trim();
    }

    removeLocationDropdown(input);
}

function removeLocationDropdown(input) {
    const wrapper = input.closest('.location-input-wrapper');
    if (!wrapper) return;
    const existing = wrapper.querySelector('.location-autocomplete-dropdown');
    if (existing) existing.remove();
}

function closeLocationDropdowns() {
    document.querySelectorAll('.location-autocomplete-dropdown').forEach(d => d.remove());
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showPluginSaveStatus(pluginName, success, message) {
    const card = document.querySelector(`.plugin-config-card[data-plugin="${pluginName}"]`);
    if (!card) return;

    // Remove any existing status message
    const existing = card.querySelector('.plugin-save-status');
    if (existing) existing.remove();

    const statusEl = document.createElement('div');
    statusEl.className = 'plugin-save-status muted';
    statusEl.style.marginTop = '0.5rem';
    statusEl.style.color = success ? '#4caf50' : '#f44336';
    statusEl.textContent = (success ? '✅ ' : '❌ ') + message;
    card.appendChild(statusEl);

    // Auto-remove after 5 seconds
    setTimeout(() => statusEl.remove(), 5000);
}

init();
