/**
 * FreeAir Bridge Admin - Simplified JavaScript
 */

console.log('[APP] Script loaded');

// ===== GLOBAL API KEY MANAGEMENT =====
let globalApiKey = null;  // Store API key for Bearer token auth

// Load API key from backend (called after login)
async function loadApiKey() {
    try {
        const res = await fetch('/api/auth/get-api-key');
        if (res.ok) {
            const data = await res.json();
            globalApiKey = data.api_key;
            console.log('[AUTH] API key loaded successfully');
            return true;
        } else if (res.status === 401) {
            // Not authenticated - redirect to login
            console.warn('[AUTH] Not authenticated, redirecting to login');
            window.location.href = '/login';
            return false;
        } else {
            console.error('[AUTH] Failed to load API key:', res.status);
            globalApiKey = null;
            return false;
        }
    } catch (err) {
        console.error('[AUTH] Error loading API key:', err);
        globalApiKey = null;
        return false;
    }
}

// Clear API key on logout
function clearApiKey() {
    globalApiKey = null;
    console.log('[AUTH] API key cleared on logout');
}

// Check if user is still logged in (called on page load)
async function checkSession() {
    // If we're on /login or /first-setup, don't check session
    if (window.location.pathname === '/login' ||
        window.location.pathname === '/first-setup') {
        return;
    }

    try {
        // Try to fetch API to check auth status
        const response = await fetch('/api/status');

        if (response.status === 401) {
            // Unauthorized - redirect to login
            window.location.href = '/login';
        }
    } catch (error) {
        // Network error or other issue - don't redirect
        console.error('Session check error:', error);
    }
}

// Check session when page loads
document.addEventListener('DOMContentLoaded', () => {
    checkSession();
});

let pauseLogRefresh = false;  // Flag to pause log refresh after clearing
let addDeviceFromDiscovery = false;  // Flag: is modal called from auto-discovery?
let addDeviceFromDiscoverySerial = null;  // Serial number from auto-discovery

// ===== UPDATE STATUS INDICATOR =====
let lastUpdateTime = null;           // Timestamp des letzten erfolgreichen Updates
let isPolling = false;               // Ist gerade am Polling?
let updateStatusInterval = null;     // Timer für Status-Update alle 1s

// Global unit mapping for all device fields
const unitMap = {
    'outdoor_temp': '°C',
    'supply_temp': '°C',
    'extract_temp': '°C',
    'exhaust_temp': '°C',
    'temp_virt_sup_exit': '°C',
    'outdoor_humidity': '%',
    'extract_humidity': '%',
    'outdoor_humidity_abs': 'g/m³',
    'extract_humidity_abs': 'g/m³',
    'co2': 'ppm',
    'co2_indicator': '',
    'pressure': 'hPa',
    'air_density': 'kg/m³',
    'supply_fan_rpm': 'RPM',
    'extract_fan_rpm': 'RPM',
    'air_flow': 'm³/h',
    'air_flow_ave': 'm³/h',
    'supply_vent_pos': '%',
    'extract_vent_pos': '%',
    'bypass_vent_pos': '%',
    'outdoor_filter_indicator': '',
    'exhaust_filter_indicator': '',
    'extract_humidity_indicator': '',
    'heat_recovery': '%',
    'power_recovery': '%',
    'filter_hours': 'h',
    'operating_hours': 'h',
    'rssi': 'dBm',
    'board_version': '',
    'error_state': '',
    'has_errors': '',
    'deicing': '',
    'comfort_level': ''
};

// Global label mapping for all device fields (German)
const labelMap = {
    'outdoor_temp': 'Außentemperatur',
    'supply_temp': 'Zulufttemperatur',
    'extract_temp': 'Ablufttemperatur',
    'exhaust_temp': 'Fortlufttemperatur',
    'temp_virt_sup_exit': 'Virt. Zuluft Austritt',
    'outdoor_humidity': 'Außenluftfeuchte',
    'extract_humidity': 'Abluftfeuchte',
    'outdoor_humidity_abs': 'Absolute Außenfeuchte',
    'extract_humidity_abs': 'Absolute Abluftfeuchte',
    'co2': 'CO₂-Gehalt',
    'co2_indicator': 'CO₂-Indikator',
    'pressure': 'Luftdruck',
    'air_density': 'Luftdichte',
    'supply_fan_rpm': 'Zuluftlüfter',
    'extract_fan_rpm': 'Abluftlüfter',
    'air_flow': 'Luftdurchsatz',
    'air_flow_ave': 'Durchschn. Luftdurchsatz',
    'comfort_level': 'Komfortstufe',
    'operating_mode': 'Betriebsmodus',
    'hum_red_mode': 'Feuchte-Reduktion',
    'supply_filter_ful': 'Zuluftfilter Verschmutzung',
    'extract_filter_ful': 'Abluftfilter Verschmutzung',
    'outdoor_filter_indicator': 'Außenluftfilter',
    'exhaust_filter_indicator': 'Fortluftfilter',
    'extract_humidity_indicator': 'Feuchte-Indikator',
    'supply_vent_pos': 'Zuluft-Position',
    'extract_vent_pos': 'Abluft-Position',
    'bypass_vent_pos': 'Bypass-Position',
    'heat_recovery': 'Wärmerückgewinnung',
    'power_recovery': 'Kraftrückgewinnung',
    'filter_hours': 'Filterstunden',
    'operating_hours': 'Betriebsstunden',
    'rssi': 'WLAN-Signalstärke',
    'error_state': 'Fehlerstatus',
    'has_errors': 'Fehler vorhanden',
    'deicing': 'Enteisungsmode',
    'board_version': 'Board-Version'
};

document.addEventListener('DOMContentLoaded', () => {
    console.log('[APP] DOM loaded');

    // Load API key for command authentication
    loadApiKey();

    // Initialize update status indicator
    initUpdateStatusIndicator();

    // Update time every second
    setInterval(() => {
        const el = document.getElementById('current-time');
        if (el) {
            const now = new Date();
            el.textContent = now.toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        }
    }, 1000);

    // Load initial data
    loadStatus();
    loadDashboard();  // Render device status cards
    loadDevices();
    loadMeasurements();
    loadLoxoneConfig();
    loadUnknownDevices();  // Load unknown devices on startup
    // Don't load logs by default - only when a level is selected!

    // Setup log level filters
    document.querySelectorAll('input[name="logLevel"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.checked) {
                // Only load when a level is selected
                loadLogs();
                if (e.target.value !== 'all') {
                    setLogLevel(e.target.value);
                }
            }
        });
    });

    // Modal close on click outside
    window.addEventListener('click', (e) => {
        const addDeviceModal = document.getElementById('addDeviceModal');
        const loxoneModal = document.getElementById('loxoneConfigModal');

        if (e.target === addDeviceModal) {
            closeAddDeviceModal();
        }
        if (e.target === loxoneModal) {
            closeLoxoneEditModal();
        }
    });

    // Auto-refresh every 10 seconds - update all key components
    setInterval(() => {
        loadStatus();
        loadDashboard();  // Update device status cards
        loadDevices();  // Update device list + RSSI values
        loadMeasurements();  // Update measurements display
        loadLoxoneConfig();  // Update Loxone status
        loadUnknownDevices();  // Check for new unknown devices
    }, 10000);

    // Refresh logs only if a level is selected (every 5 seconds)
    // Skip refresh if pauseLogRefresh flag is set
    setInterval(() => {
        if (!pauseLogRefresh) {
            const selectedLevel = document.querySelector('input[name="logLevel"]:checked');
            if (selectedLevel) {
                loadLogs();
            }
        }
    }, 5000);

    console.log('[APP] Initialization complete');
});

// Helper function to escape HTML special characters
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Helper function to generate circle rating HTML
function generateCircleRating(value, maxValue, isIndicator = false) {
    if (value === null || value === undefined) return '';

    const numValue = parseInt(value);
    let html = `<span class="circle-rating${isIndicator ? ` indicator-level-${numValue}` : ''}">`;

    for (let i = 1; i <= maxValue; i++) {
        html += `<span class="circle${i <= numValue ? ' filled' : ' empty'}"></span>`;
    }

    html += '</span>';
    return html;
}

// Load status
async function loadStatus() {
    setPollingStatus(true);
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        setUpdateTime();

        const t = document.getElementById('devices-total');
        const e = document.getElementById('devices-enabled');
        const l = document.getElementById('loxone-status');

        if (t) t.textContent = data.devices_count || 0;
        if (e) e.textContent = data.devices_enabled || 0;
        if (l) l.textContent = data.loxone_enabled ? '✓' : '✗';
    } catch (err) {
        console.error('[STATUS]', err);
    } finally {
        setPollingStatus(false);
    }
}

// Load Dashboard - shows device status cards
async function loadDashboard() {
    setPollingStatus(true);
    try {
        const res = await fetch('/api/devices');
        const devices = await res.json();
        setUpdateTime();
        const el = document.getElementById('devices-dashboard-grid');

        if (!el) return;

        if (!devices || devices.length === 0) {
            el.innerHTML = '<div class="empty-state"><i class="bi bi-inbox"></i><p>Keine Geräte konfiguriert</p></div>';
            return;
        }

        // Render device cards
        el.innerHTML = '';
        devices.forEach(device => {
            const card = createDeviceStatusCard(device);
            el.appendChild(card);
        });
    } catch (err) {
        console.error('[DASHBOARD]', err);
    } finally {
        setPollingStatus(false);
    }
}

function createDeviceStatusCard(device) {
    const card = document.createElement('div');
    const isOnline = device.last_data && device.last_data.is_online;
    const cardClass = isOnline ? 'online' : 'offline';

    // Extract key measurements
    const temp = device.last_data?.supply_temp ?? '-';
    const humidity = device.last_data?.extract_humidity ?? '-';
    const co2 = device.last_data?.co2 ?? '-';
    const comfort = parseInt(device.last_data?.comfort_level) || 0; // Ensure it's a number
    const mode = device.last_data?.operating_mode ?? '-';
    const rssi = device.rssi ?? '-';
    const hasErrors = device.last_data?.has_errors;

    // Determine status message - show initialization message if no data yet
    let statusMessage = '';
    if (!device.last_data || !device.last_data.timestamp) {
        statusMessage = 'wird initialisiert - max. 60sec';
    } else {
        const lastUpdate = new Date(device.last_data.timestamp).toLocaleTimeString('de-DE');
        statusMessage = `Update: ${lastUpdate}`;
    }

    // Escape device name for HTML
    const deviceName = document.createTextNode(device.name).nodeValue;
    const deviceId = document.createTextNode(device.id).nodeValue;

    // Map mode number to text
    const modeText = { 0: 'Comfort', 1: 'Comfort', 2: 'Sleep', 3: 'Turbo', 4: 'Cool' }[mode] || 'Unbekannt';

    // Extract additional data for dashboard
    const airFlow = device.last_data?.air_flow ?? '-';
    const hasErrorsFlag = device.last_data?.has_errors ? 'Ja' : 'Nein';
    const filterHours = device.last_data?.filter_hours ?? '-';

    card.className = `device-status-card ${cardClass}`;
    card.innerHTML = `
        <div class="device-card-header">
            <div>
                <div class="device-card-name">${escapeHtml(device.name)}</div>
                <div class="device-card-status">
                    <span class="device-status-dot ${isOnline ? '' : 'offline'}"></span>
                    <span>${isOnline ? 'Online' : 'Offline'}</span>
                </div>
                <div class="device-last-update">${statusMessage}</div>
            </div>
            ${hasErrors ? '<div style="font-size: 1.5rem; color: var(--accent-red);"><i class="bi bi-exclamation-triangle-fill"></i></div>' : ''}
        </div>

        <div class="device-measurements">
            <div class="measurement-box">
                <div class="measurement-label">Luftdurchsatz</div>
                <div class="measurement-value">${escapeHtml(airFlow.toString())}<span class="measurement-unit">m³/h</span></div>
            </div>
            <div class="measurement-box">
                <div class="measurement-label">Fehler</div>
                <div class="measurement-value">${escapeHtml(hasErrorsFlag.toString())}</div>
            </div>
            <div class="measurement-box">
                <div class="measurement-label">Filterh</div>
                <div class="measurement-value">${escapeHtml(filterHours.toString())}<span class="measurement-unit">h</span></div>
            </div>
            <div class="measurement-box">
                <div class="measurement-label">RSSI</div>
                <div class="measurement-value">${escapeHtml(rssi.toString())}<span class="measurement-unit">dBm</span></div>
            </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 1rem;">
            <div class="measurement-box">
                <div class="measurement-label">Komfortstufe</div>
                <div class="measurement-value" style="font-size: 1.3rem; letter-spacing: 0.2rem;">
                    ${Array(comfort).fill('●').join('')}${Array(5 - comfort).fill('○').join('')}
                </div>
            </div>
            <div class="measurement-box">
                <div class="measurement-label">Betriebsmodus</div>
                <div class="measurement-value">${escapeHtml(modeText)}</div>
            </div>
        </div>

        <div class="device-quick-actions">
            <button class="device-action-btn" onclick="selectDevice('${escapeHtml(device.id)}', '${escapeHtml(device.name)}')" title="Gerät auswählen + steuern">
                <i class="bi bi-sliders"></i> Steuern
            </button>
            <button class="device-action-btn" onclick="openDeviceSettingsModal('${escapeHtml(device.id)}', '${escapeHtml(device.name)}')" title="Geräteeigenschaften bearbeiten">
                <i class="bi bi-gear"></i> Einstellungen
            </button>
        </div>
    `;

    return card;
}

// Navigation: Edit device from dashboard card - scrolls to config section
function editDeviceFromDashboard(deviceId) {
    // Scroll to devices list and select device
    const devicesSection = document.querySelector('[data-device-id="' + deviceId + '"]');
    if (devicesSection) {
        devicesSection.scrollIntoView({ behavior: 'smooth' });
        selectDevice(deviceId, deviceId);
    }
}

// Load devices
let selectedDeviceId = null;  // Track selected device
let selectedDeviceName = null; // Track selected device name
let currentSettingsDeviceId = null; // Track device being edited in settings modal

async function loadDevices() {
    try {
        const res = await fetch('/api/devices');
        const devices = await res.json();
        const el = document.getElementById('devices-list');

        if (!el) return;

        if (!devices || devices.length === 0) {
            el.innerHTML = '<div class="empty-state"><i class="bi bi-inbox"></i><p>Keine Geräte konfiguriert</p></div>';
            updateBridgeControlUI(null, null);
            return;
        }

        // If no device selected, select the first one
        if (!selectedDeviceId && devices.length > 0) {
            selectDevice(devices[0].id, devices[0].name);
        }

        let html = '';
        devices.forEach(d => {
            const rssiValue = d.rssi !== null && d.rssi !== undefined ? d.rssi : 'N/A';
            const rssiClass = rssiValue !== 'N/A' ? (rssiValue > -70 ? 'success' : rssiValue > -80 ? 'warning' : 'danger') : 'secondary';
            const isSelected = d.id === selectedDeviceId ? 'style="border-left: 4px solid var(--accent-green);"' : '';

            html += `
            <div class="device-item" ${isSelected} onclick="selectDevice('${d.id}', '${d.name}')">
                <div class="device-info">
                    <div class="device-name">${d.name || 'Device'}</div>
                    <div class="device-meta">ID: ${d.id} | S/N: ${d.serial_no}</div>
                </div>
                <div class="device-status" style="display: flex; align-items: center; gap: 1rem;">
                    <div>
                        <div style="text-align: right; font-size: 0.85rem; margin-bottom: 0.5rem;">
                            <span style="padding: 4px 8px; border-radius: 4px; background-color: ${d.enabled ? 'var(--accent-green)' : 'var(--accent-red)'}; color: white; font-weight: 600; font-size: 0.75rem;">
                                ${d.enabled ? '✓ Aktiv' : '✗ Inaktiv'}
                            </span>
                        </div>
                        ${rssiValue !== 'N/A' ? `<div style="text-align: right; font-size: 0.8rem; color: var(--text-muted);">WLAN: ${rssiValue} dBm</div>` : ''}
                    </div>
                    <div style="display: flex; gap: 0.5rem;">
                        <button class="btn-icon" onclick="viewDeviceDetails('${d.id}', '${d.name}')" title="Messwerte anzeigen" onclick="event.stopPropagation()">
                            <i class="bi bi-info-circle"></i>
                        </button>
                        <button class="btn-icon" onclick="editDevice('${d.id}')" title="Gerät bearbeiten" onclick="event.stopPropagation()">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn-icon" onclick="deleteDevice('${d.id}')" title="Gerät löschen" style="color: var(--accent-red);" onclick="event.stopPropagation()">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
            `;
        });
        el.innerHTML = html;

        // Update control button active states
        updateActiveControlButtonsFromDevices(devices);
    } catch (err) {
        console.error('[DEVICES]', err);
    } finally {
        setPollingStatus(false);
    }
}

// Select a device and update Bridge Control
function selectDevice(deviceId, deviceName) {
    selectedDeviceId = deviceId;
    selectedDeviceName = deviceName;
    loadDevices(); // Refresh to show selection (will also update control buttons)

    // Open control modal after a short delay
    setTimeout(() => {
        openControlModal(deviceId, deviceName);
    }, 300);
}

// Update active state of comfort and mode buttons based on device values
// Can be called with devices array directly to avoid extra API call
function updateActiveControlButtonsFromDevices(devices) {
    if (!selectedDeviceName) return;

    // Find selected device
    const device = devices.find(d => d.name === selectedDeviceName || d.id === selectedDeviceId);
    if (!device || !device.last_data) return;

    const data = device.last_data;
    const comfortLevel = data.comfort_level;
    let operatingMode = data.operating_mode;

    // Map mode 0 to 1 (both mean Comfort)
    if (operatingMode === 0) operatingMode = 1;

    // Remove active class from all comfort buttons
    for (let i = 1; i <= 5; i++) {
        const btn = document.getElementById(`comfort-${i}`);
        if (btn) btn.classList.remove('active');
    }

    // Remove active class from all mode buttons
    for (let i = 1; i <= 4; i++) {
        const btn = document.getElementById(`mode-${i}`);
        if (btn) btn.classList.remove('active');
    }

    // Add active class to current comfort level
    if (comfortLevel >= 1 && comfortLevel <= 5) {
        const activeComfortBtn = document.getElementById(`comfort-${comfortLevel}`);
        if (activeComfortBtn) activeComfortBtn.classList.add('active');
    }

    // Add active class to current operating mode
    if (operatingMode >= 1 && operatingMode <= 4) {
        const activeModeBtn = document.getElementById(`mode-${operatingMode}`);
        if (activeModeBtn) activeModeBtn.classList.add('active');
    }
}

// Update Bridge Control UI based on selected device
// Load Loxone config
async function loadLoxoneConfig() {
    setPollingStatus(true);
    try {
        const res = await fetch('/api/loxone');
        const loxone = await res.json();
        setUpdateTime();

        const ipEl = document.getElementById('loxone-ip');
        const portEl = document.getElementById('loxone-port');
        const enabledEl = document.getElementById('loxone-enabled');

        if (ipEl && loxone.ip) ipEl.value = loxone.ip;
        if (portEl && loxone.port) portEl.value = loxone.port;
        if (enabledEl && loxone.enabled !== undefined) enabledEl.checked = loxone.enabled;
    } catch (err) {
        console.error('[LOXONE]', err);
    } finally {
        setPollingStatus(false);
    }
}

// Load measurements from last data
async function loadMeasurements() {
    setPollingStatus(true);
    try {
        const res = await fetch('/api/devices');
        const devices = await res.json();
        setUpdateTime();
        const el = document.getElementById('measurements-list');

        if (!el || !devices || devices.length === 0) return;

        // Use first device's data
        const device = devices[0];
        const data = device.last_data || {};

        if (!data || Object.keys(data).length === 0) {
            el.innerHTML = '<p style="text-align: center; color: #999;">Keine Messdaten vorhanden</p>';
            return;
        }

        // Group measurements by category
        const measurements = {
            'Temperaturen': ['outdoor_temp', 'supply_temp', 'extract_temp', 'exhaust_temp', 'temp_virt_sup_exit'],
            'Luftfeuchte': ['outdoor_humidity', 'extract_humidity', 'outdoor_humidity_abs', 'extract_humidity_abs'],
            'Luftqualität': ['co2', 'co2_indicator', 'pressure', 'air_density'],
            'Lüfter & Durchsatz': ['supply_fan_rpm', 'extract_fan_rpm', 'air_flow', 'air_flow_ave'],
            'Steuerung': ['comfort_level', 'operating_mode', 'hum_red_mode'],
            'Filter & Belüftung': ['supply_filter_ful', 'extract_filter_ful', 'outdoor_filter_indicator', 'exhaust_filter_indicator', 'extract_humidity_indicator', 'supply_vent_pos', 'extract_vent_pos', 'bypass_vent_pos'],
            'Effizienz': ['heat_recovery', 'power_recovery'],
            'Status': ['filter_hours', 'operating_hours', 'rssi', 'error_state', 'has_errors', 'deicing']
        };

        let html = '';

        for (const [category, fields] of Object.entries(measurements)) {
            let categoryHtml = `<div style="margin-bottom: 20px;">
                <h6 style="background: linear-gradient(135deg, #2c3e50, #3498db); color: white; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                    ${category}
                </h6>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px;">
            `;

            fields.forEach(field => {
                const value = data[field];
                if (value !== null && value !== undefined && value !== '') {
                    const label = labelMap[field] || field;
                    const unit = unitMap[field] || '';
                    const displayValue = typeof value === 'boolean' ? (value ? 'Ja' : 'Nein') : value;

                    // Check if this is a comfort level or indicator field
                    let valueDisplay = displayValue;
                    if (field === 'comfort_level' && !isNaN(displayValue)) {
                        valueDisplay = generateCircleRating(displayValue, 5, false);
                    } else if (['co2_indicator', 'outdoor_filter_indicator', 'exhaust_filter_indicator', 'extract_humidity_indicator'].includes(field) && !isNaN(displayValue)) {
                        valueDisplay = generateCircleRating(displayValue, 4, true);
                    }

                    // Format: value with unit (if available)
                    const valueWithUnit = unit ? `${valueDisplay} ${unit}` : valueDisplay;

                    categoryHtml += `
                    <div style="padding: 12px; background: #f0f4f8; border-left: 4px solid #3498db; border-radius: 5px;">
                        <div style="font-size: 0.85rem; color: #666; margin-bottom: 5px;">${label}</div>
                        <div style="font-size: 1.4rem; font-weight: 700; color: #2c3e50;">
                            ${valueWithUnit}
                        </div>
                    </div>
                    `;
                }
            });

            categoryHtml += `</div></div>`;
            html += categoryHtml;
        }

        if (html) {
            el.innerHTML = html;
        }
    } catch (err) {
        console.error('[MEASUREMENTS]', err);
    } finally {
        setPollingStatus(false);
    }
}

// Load logs
async function loadLogs() {
    setPollingStatus(true);
    try {
        const level = document.querySelector('input[name="logLevel"]:checked')?.value || 'all';
        const res = await fetch(`/api/logs?level=${level}&limit=50`);
        const data = await res.json();
        setUpdateTime();
        const el = document.getElementById('log-viewer');

        if (!el) return;

        if (!data.logs || data.logs.length === 0) {
            el.innerHTML = '<div style="color: #999;">Keine Logs</div>';
            return;
        }

        // Reverse the logs so newest is at bottom
        let html = '';
        data.logs.reverse().forEach(log => {
            const color = {
                'DEBUG': '#888',
                'INFO': '#0f0',
                'WARNING': '#fa0',
                'ERROR': '#f44',
                'CRITICAL': '#f00'
            }[log.level] || '#0f0';

            html += `
            <div style="color: ${color}; font-family: monospace; font-size: 12px; margin: 2px 0; border-left: 3px solid ${color}; padding-left: 5px;">
                [${log.level}] ${log.message}
            </div>
            `;
        });
        el.innerHTML = html;
        // Auto-scroll to bottom
        setTimeout(() => {
            el.scrollTop = el.scrollHeight;
        }, 0);
    } catch (err) {
        console.error('[LOGS]', err);
    } finally {
        setPollingStatus(false);
    }
}

// Show Command Modal
function showCommandModal(comfort, mode) {
    const modal = document.getElementById('commandModal');
    if (!modal) {
        console.error('Command modal not found');
        return;
    }

    const modeNames = {1: 'Comfort', 2: 'Sleep', 3: 'Turbo', 4: 'Turbo Cool'};

    const content = modal.querySelector('.modal-content');
    content.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div style="font-size: 2.5rem; margin-bottom: 1rem;">⏳</div>
            <h2 style="color: var(--accent-green); margin-bottom: 1rem;">Befehl wird gesendet...</h2>
            <div style="background: var(--bg-tertiary); padding: 1.5rem; border-radius: 8px; margin-bottom: 1.5rem; border-left: 4px solid var(--accent-green);">
                <div style="margin-bottom: 1rem;">
                    <div style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem;">Betriebsmodus:</div>
                    <div style="font-size: 1.3rem; font-weight: 600; color: var(--accent-green);">${modeNames[mode] || 'Unbekannt'}</div>
                </div>
                <div>
                    <div style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem;">Komfortstufe:</div>
                    <div style="font-size: 1.3rem; font-weight: 600; color: var(--accent-green);">${comfort}/5</div>
                </div>
            </div>
            <div style="color: var(--text-muted); font-size: 0.9rem; font-style: italic;">
                Dies kann ein paar Sekunden dauern...
            </div>
        </div>
    `;

    modal.style.display = 'flex';
}

// Close Command Modal
function closeCommandModal() {
    const modal = document.getElementById('commandModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Show Command Success Modal
function showCommandSuccess(comfort, mode) {
    const modal = document.getElementById('commandModal');
    if (!modal) return;

    const modeNames = {1: 'Comfort', 2: 'Sleep', 3: 'Turbo', 4: 'Turbo Cool'};

    const content = modal.querySelector('.modal-content');
    content.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div style="font-size: 3rem; margin-bottom: 1rem;">✓</div>
            <h2 style="color: var(--accent-green); margin-bottom: 1.5rem;">Befehl erfolgreich gesendet!</h2>
            <div style="background: var(--bg-tertiary); padding: 1.5rem; border-radius: 8px; margin-bottom: 1.5rem; border-left: 4px solid var(--accent-green);">
                <div style="margin-bottom: 1rem;">
                    <div style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem;">Betriebsmodus:</div>
                    <div style="font-size: 1.3rem; font-weight: 600; color: var(--accent-green);">${modeNames[mode] || 'Unbekannt'}</div>
                </div>
                <div>
                    <div style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.5rem;">Komfortstufe:</div>
                    <div style="font-size: 1.3rem; font-weight: 600; color: var(--accent-green);">${comfort}/5</div>
                </div>
            </div>
            <button onclick="closeCommandModal()" style="padding: 0.75rem 1.5rem; background: var(--accent-green); color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600;">
                OK
            </button>
        </div>
    `;
}

// Show Command Error Modal
function showCommandError(errorMsg) {
    const modal = document.getElementById('commandModal');
    if (!modal) return;

    const content = modal.querySelector('.modal-content');
    content.innerHTML = `
        <div style="text-align: center; padding: 2rem;">
            <div style="font-size: 3rem; margin-bottom: 1rem;">✗</div>
            <h2 style="color: var(--accent-red); margin-bottom: 1.5rem;">Fehler beim Senden</h2>
            <div style="background: var(--bg-tertiary); padding: 1.5rem; border-radius: 8px; margin-bottom: 1.5rem; border-left: 4px solid var(--accent-red); text-align: left;">
                <div style="color: var(--text-secondary);">${errorMsg}</div>
            </div>
            <button onclick="closeCommandModal()" style="padding: 0.75rem 1.5rem; background: var(--accent-red); color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 600;">
                OK
            </button>
        </div>
    `;
}


// Clear all logs
async function clearLogs() {
    try {
        // Pause auto-refresh to prevent immediate reload
        pauseLogRefresh = true;

        const res = await fetch('/api/logs/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        if (data.success) {
            // Reset log viewer
            const el = document.getElementById('log-viewer');
            if (el) {
                el.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 1rem;">Logs gelöscht</div>';
            }
            // Resume auto-refresh after 7 seconds (after next refresh cycle completes)
            setTimeout(() => {
                pauseLogRefresh = false;
            }, 7000);
        }
    } catch (err) {
        console.error('[LOGS] Clear error:', err);
        // Resume auto-refresh on error too
        pauseLogRefresh = false;
    }
}

async function setLogLevel(level) {
    try {
        const res = await fetch('/api/logs/level', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ level })
        });
        const data = await res.json();
        if (data.success) {
            console.log('[LOGLEVEL] Changed to', level);
            loadLogs();
        }
    } catch (err) {
        console.error('[LOGLEVEL]', err);
    }
}

// Show alert
function showAlert(msg, type = 'info') {
    const el = document.getElementById('alert-container');
    if (el) {
        const id = 'alert-' + Date.now();
        el.innerHTML += `<div id="${id}" style="padding: 10px; margin: 10px 0; background: ${type === 'error' ? '#ffcccc' : '#ccffcc'}; border: 1px solid ${type === 'error' ? '#ff0000' : '#00cc00'}; border-radius: 5px;">${msg}</div>`;
        setTimeout(() => document.getElementById(id)?.remove(), 5000);
    }
}
// View device details and measurements
async function viewDeviceDetails(deviceId, deviceName) {
    try {
        const res = await fetch(`/api/devices`);
        const devices = await res.json();
        const device = devices.find(d => d.id === deviceId);

        if (!device) {
            showAlert('Gerät nicht gefunden', 'error');
            return;
        }

        // Build measurements display
        let measurementsHtml = '';
        let measurementFields = [];
        if (device.last_data && Object.keys(device.last_data).length > 0) {
            const data = device.last_data;

            // Get selected fields for Loxone
            const selectedFields = device.loxone_fields || [];

            // Build list from all available data
            const measurements = [];
            for (const [key, value] of Object.entries(data)) {
                let label = labelMap[key] || key.replace(/_/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                let unit = unitMap[key] || '';
                let displayValue = value;

                // Format operating_mode with readable names
                if (key === 'operating_mode') {
                    const modeNames = {
                        0: 'Comfort',
                        1: 'Comfort',
                        2: 'Sleep',
                        3: 'Turbo',
                        4: 'Turbo Cool',
                        5: 'Service',
                        6: 'Test',
                        7: 'Manufacturer',
                        8: 'Dehumidification'
                    };
                    displayValue = modeNames[value] || `Unbekannt (${value})`;
                }

                // Format boolean values
                if (typeof displayValue === 'boolean') {
                    displayValue = displayValue ? 'Ja' : 'Nein';
                }

                // Format comfort level with circle rating
                if (key === 'comfort_level' && !isNaN(value)) {
                    displayValue = generateCircleRating(value, 5, false);
                }

                // Format indicator fields with circle rating
                if (['co2_indicator', 'outdoor_filter_indicator', 'exhaust_filter_indicator', 'extract_humidity_indicator'].includes(key) && !isNaN(value)) {
                    displayValue = generateCircleRating(value, 4, true);
                }

                measurements.push({
                    key: key,
                    label: label,
                    value: displayValue,
                    unit: unit
                });
            }

            measurementFields = measurements;
            measurementsHtml = measurements.map(m => {
                return `
                <div class="measurement-item" style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 0; border-bottom: 1px solid var(--bg-secondary);">
                    <div style="flex: 1;">
                        <div class="measurement-label">${m.label}</div>
                        <div class="measurement-value">${m.value !== null && m.value !== undefined ? m.value : 'N/A'} ${m.unit || ''}</div>
                    </div>
                    <div style="margin-left: 1rem;">
                        <input type="checkbox" id="loxone-field-${m.key}" data-field-key="${m.key}" ${selectedFields.includes(m.key) ? 'checked' : ''} style="cursor: pointer; width: 18px; height: 18px;">
                    </div>
                </div>
            `;
            }).join('');
        } else {
            measurementsHtml = '<div style="text-align: center; color: var(--text-muted); padding: 1rem;">Keine Messdaten verfügbar<br><small>(kann bis zu 60sec dauern)</small></div>';
        }

        // Show modal
        const modal = document.getElementById('addDeviceModal');
        if (modal) {
            const actionButtons = measurementFields.length > 0 ? `
                <div style="display: flex; gap: 0.5rem; padding-top: 1rem; border-top: 1px solid var(--bg-secondary); flex-wrap: wrap;">
                    <button onclick="saveLoxoneFields('${deviceId}')" style="flex: 1; min-width: 140px; padding: 0.5rem 1rem; background-color: var(--accent-blue); color: white; border: none; border-radius: 4px; cursor: pointer;">Speichern</button>
                    <button onclick="downloadLoxoneXML('${deviceId}', '${deviceName}')" style="flex: 1; min-width: 140px; padding: 0.5rem 1rem; background-color: var(--accent-green); color: white; border: none; border-radius: 4px; cursor: pointer;">📥 XML Download</button>
                    <button onclick="downloadLoxoneCommandTemplate('${deviceId}', '${deviceName}')" style="flex: 1; min-width: 140px; padding: 0.5rem 1rem; background-color: #f59e0b; color: white; border: none; border-radius: 4px; cursor: pointer;">📤 Command Template</button>
                    <button onclick="closeAddDeviceModal()" style="flex: 1; min-width: 140px; padding: 0.5rem 1rem; background-color: var(--bg-secondary); color: var(--text-primary); border: none; border-radius: 4px; cursor: pointer;">Schließen</button>
                </div>
            ` : '';
            modal.querySelector('.modal-content').innerHTML = `
                <div class="modal-header-text">
                    Messwerte: ${deviceName}
                    <button class="modal-close" onclick="closeAddDeviceModal()">×</button>
                </div>
                <div style="padding: 1.5rem;">
                    ${measurementsHtml}
                    ${actionButtons}
                </div>
            `;
            modal.classList.add('active');
        }
    } catch (err) {
        console.error('[DEVICE_DETAILS]', err);
        showAlert('Fehler beim Laden der Messwerte', 'error');
    }
}

// Download Loxone XML configuration
async function downloadLoxoneXML(deviceId, deviceName) {
    try {
        // Collect all checked fields
        const checkboxes = document.querySelectorAll('input[type="checkbox"][id^="loxone-field-"]');
        const selectedFields = [];

        checkboxes.forEach(cb => {
            if (cb.checked) {
                const fieldKey = cb.getAttribute('data-field-key');
                if (fieldKey) {
                    selectedFields.push(fieldKey);
                }
            }
        });

        if (selectedFields.length === 0) {
            showAlert('Bitte mindestens ein Feld auswählen', 'error');
            return;
        }

        console.log('[LOXONE_XML] Selected fields:', selectedFields);

        // Send to backend for XML generation
        const response = await fetch('/api/loxone/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_name: deviceName,
                selected_fields: selectedFields
            })
        });

        if (!response.ok) {
            const errData = await response.json();
            showAlert(`XML-Fehler: ${errData.error || 'Unbekannter Fehler'}`, 'error');
            return;
        }

        // Download the XML file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `FreeAir_Loxone_${deviceName.replace(/\s+/g, '_')}.xml`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showAlert('✓ XML erfolgreich heruntergeladen!', 'success');
        console.log('[LOXONE_XML] Download complete');

    } catch (err) {
        console.error('[LOXONE_XML]', err);
        showAlert('Fehler beim XML-Download', 'error');
    }
}

// Download Loxone Command Template
async function downloadLoxoneCommandTemplate(deviceId, deviceName) {
    try {
        console.log('[LOXONE_CMD] Request for device:', deviceId, deviceName);

        // Send to backend for command template generation
        const response = await fetch('/api/loxone/command-template', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_name: deviceName,
                device_id: deviceId
            })
        });

        if (!response.ok) {
            const errData = await response.json();
            showAlert(`Template-Fehler: ${errData.error || 'Unbekannter Fehler'}`, 'error');
            return;
        }

        // Download the command template file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `FreeAir2Lox_Commands_${deviceName.replace(/\s+/g, '_')}.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showAlert('✓ Command Template erfolgreich heruntergeladen!', 'success');
        console.log('[LOXONE_CMD] Download complete');

    } catch (err) {
        console.error('[LOXONE_CMD]', err);
        showAlert('Fehler beim Command Template Download', 'error');
    }
}

// Edit device
async function editDevice(deviceId) {
    try {
        const res = await fetch(`/api/devices`);
        const devices = await res.json();
        const device = devices.find(d => d.id === deviceId);

        if (!device) {
            showAlert('Gerät nicht gefunden', 'error');
            return;
        }

        // Show edit modal
        const modal = document.getElementById('addDeviceModal');
        if (modal) {
            modal.querySelector('.modal-content').innerHTML = `
                <div class="modal-header-text">
                    Gerät bearbeiten: ${device.name}
                    <button class="modal-close" onclick="closeAddDeviceModal()">×</button>
                </div>
                <div class="form-group">
                    <label>Geräte-Name</label>
                    <input type="text" id="edit-device-name" value="${device.name}" placeholder="z.B. Wohnzimmer">
                </div>
                <div class="form-group">
                    <label>Seriennummer</label>
                    <input type="text" id="edit-device-serial" value="${device.serial_no}" placeholder="z.B. FA100XXXX">
                </div>
                <div class="form-group">
                    <label>Passwort</label>
                    <input type="password" id="edit-device-password" value="${device.password || ''}" placeholder="FreeAir Passwort">
                </div>
                <div class="form-group" style="padding: 1rem; background-color: rgba(88, 166, 255, 0.05); border: 1px solid var(--border-color); border-radius: 4px; margin-bottom: 1.25rem;">
                    <label style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0; cursor: pointer;">
                        <input type="checkbox" id="edit-device-enabled" ${device.enabled ? 'checked' : ''} style="width: 18px; height: 18px; cursor: pointer;">
                        <span>Gerät aktivieren</span>
                    </label>
                </div>
                <div class="form-group" style="display: flex; gap: 0.75rem;">
                    <button class="btn-secondary" onclick="closeAddDeviceModal()" style="flex: 1;">Abbrechen</button>
                    <button class="btn-primary" onclick="saveEditDevice('${deviceId}')" style="flex: 1;">Speichern</button>
                </div>
            `;
            modal.classList.add('active');
        }
    } catch (err) {
        console.error('[EDIT_DEVICE]', err);
        showAlert('Fehler beim Laden des Geräts', 'error');
    }
}

// Save edited device
async function saveEditDevice(deviceId) {
    try {
        const name = document.getElementById('edit-device-name').value;
        const serial = document.getElementById('edit-device-serial').value;
        const password = document.getElementById('edit-device-password').value;
        const enabled = document.getElementById('edit-device-enabled').checked;

        if (!name || !serial || !password) {
            showAlert('Bitte alle Felder ausfüllen', 'error');
            return;
        }

        const res = await fetch(`/api/devices/${deviceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                serial_no: serial,
                password: password,
                enabled: enabled
            })
        });

        if (res.ok) {
            showAlert('Gerät aktualisiert', 'success');
            closeAddDeviceModal();
            loadDevices();
        } else {
            showAlert('Fehler beim Speichern', 'error');
        }
    } catch (err) {
        console.error('[SAVE_EDIT]', err);
        showAlert('Fehler beim Speichern', 'error');
    }
}

// Add new device
async function addDevice() {
    try {
        const name = document.getElementById('device-name')?.value;
        const serial = document.getElementById('device-serial')?.value;
        const password = document.getElementById('device-password')?.value;

        if (!name || !serial || !password) {
            showAlert('Bitte alle Felder ausfüllen', 'warning');
            return;
        }

        // Check if serial was in the unknown devices list (from discovery)
        let isFromDiscovery = false;
        try {
            const discoveryRes = await fetch('/api/discovery/unknown-devices');
            const discoveryData = await discoveryRes.json();
            isFromDiscovery = !!(discoveryData.unknown_devices && discoveryData.unknown_devices[serial]);
        } catch (e) {
            console.warn('[ADD_DEVICE] Could not check discovery list:', e);
        }

        let endpoint = '/api/devices';
        let body = {
            name: name,
            serial_no: serial,
            password: password,
            enabled: true
        };

        // For normal add, include id
        if (!isFromDiscovery) {
            body.id = name.toLowerCase().replace(/\s+/g, '_');
            endpoint = '/api/devices';
        } else {
            // From Auto-Discovery - use special endpoint
            endpoint = '/api/discovery/add';
        }

        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (res.ok) {
            showAlert('Gerät hinzugefügt', 'success');
            closeAddDeviceModal();
            // Refresh both lists
            await loadDevices();
            await loadDashboard();
            if (isFromDiscovery) {
                // Small delay to ensure backend has processed the removal
                await new Promise(resolve => setTimeout(resolve, 500));
                await loadUnknownDevices(); // Remove from unknown list
            }
        } else {
            const error = await res.text();
            showAlert('Fehler: ' + error, 'error');
        }
    } catch (err) {
        console.error('[ADD_DEVICE]', err);
        showAlert('Fehler: ' + err.message, 'error');
    }
}

// Delete device
function deleteDevice(deviceId) {
    if (confirm('Gerät wirklich löschen?')) {
        fetch(`/api/devices/${deviceId}`, { method: 'DELETE' })
            .then(() => {
                showAlert('Gerät gelöscht', 'success');
                loadDevices();
            })
            .catch(err => {
                console.error('[DELETE]', err);
                showAlert('Fehler beim Löschen', 'error');
            });
    }
}

// Save Loxone field preferences
async function saveLoxoneFields(deviceId) {
    try {
        console.log('[SAVE_LOXONE_FIELDS] Starting for deviceId:', deviceId);

        // Get all checkboxes
        const checkboxes = document.querySelectorAll('input[id^="loxone-field-"]');

        const selectedFields = [];
        checkboxes.forEach(cb => {
            if (cb.checked) {
                const fieldKey = cb.id.replace('loxone-field-', '');
                selectedFields.push(fieldKey);
            }
        });

        const url = `/api/devices/${deviceId}/loxone-fields`;
        const payload = { loxone_fields: selectedFields };

        // Send to backend
        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        // Read response body
        const responseText = await res.text();

        if (res.ok) {
            showAlert('Loxone-Felder gespeichert', 'success');
            try {
                await loadDevices();
            } catch (e) {
                console.error('[SAVE_LOXONE_FIELDS] Error loading devices:', e);
            }
            try {
                closeAddDeviceModal();
            } catch (e) {
                console.error('[SAVE_LOXONE_FIELDS] Error closing modal:', e);
            }
        } else {
            console.error('[SAVE_LOXONE_FIELDS] Server error:', res.status, responseText);
            showAlert('Fehler beim Speichern: ' + res.status, 'error');
        }
    } catch (err) {
        console.error('[SAVE_LOXONE_FIELDS] Exception:', err);
        showAlert('Fehler beim Speichern: ' + err.message, 'error');
    }
}

// Set Comfort Level
async function setComfortLevel(level) {
    try {
        // ===== VALIDATION: Only allow 1-5 =====
        if (typeof level !== 'number' || level < 1 || level > 5) {
            console.error('[SET_COMFORT_LEVEL] SECURITY: Invalid comfort level:', level, '(must be 1-5)');
            showCommandError(`Ungültige Komfortstufe: ${level}. Erlaubt sind nur 1-5!`);
            return;  // BLOCK invalid command
        }

        // Check if device is selected
        if (!selectedDeviceId) {
            showCommandError('Bitte zuerst ein Gerät auswählen');
            return;
        }

        // Check if API key is available
        if (!globalApiKey) {
            console.error('[SET_COMFORT_LEVEL] API key not available, reloading...');
            const keyLoaded = await loadApiKey();
            if (!keyLoaded) {
                showCommandError('Authentifizierung erforderlich - bitte neu anmelden');
                return;
            }
        }

        console.log('[SET_COMFORT_LEVEL] Setting comfort level to:', level, 'for device:', selectedDeviceId);

        // Close the control modal first
        closeControlModal();

        // Show loading modal
        showCommandModal(level, 1); // Default mode 1 (Comfort)

        const res = await fetch('/api/command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${globalApiKey}`
            },
            body: JSON.stringify({
                comfortLevel: level,
                serial: selectedDeviceId  // Send selected device
            })
        });

        if (res.ok) {
            const data = await res.json();
            // Show success modal with actual values (don't close first!)
            showCommandSuccess(data.comfortLevel, data.operatingMode);
            // Auto-close after 3 seconds
            setTimeout(() => closeCommandModal(), 3000);
        } else {
            console.error('[SET_COMFORT_LEVEL] API Error:', res.status);
            try {
                const err = await res.json();
                if (res.status === 401) {
                    // API key invalid - reload it
                    console.warn('[SET_COMFORT_LEVEL] Unauthorized (401) - API key may have expired');
                    globalApiKey = null;
                    showCommandError('Sitzung abgelaufen - bitte neu anmelden');
                } else {
                    showCommandError('Fehler: ' + (err.error || 'Unbekannt'));
                }
            } catch {
                showCommandError('Fehler: HTTP ' + res.status);
            }
        }
    } catch (err) {
        console.error('[SET_COMFORT_LEVEL]', err);
        showCommandError('Fehler: ' + err.message);
    }
}

// Set Operating Mode
async function setOperatingMode(mode) {
    try {
        const modeNames = {1: 'Comfort', 2: 'Sleep', 3: 'Turbo', 4: 'Turbo Cool'};

        // ===== VALIDATION: Only allow 1-4 =====
        if (typeof mode !== 'number' || mode < 1 || mode > 4) {
            console.error('[SET_OPERATING_MODE] SECURITY: Invalid operating mode:', mode, '(must be 1-4)');
            showCommandError(`Ungültiger Betriebsmodus: ${mode}. Erlaubt sind nur 1-4!`);
            return;  // BLOCK invalid command
        }

        // Check if device is selected
        if (!selectedDeviceId) {
            showCommandError('Bitte zuerst ein Gerät auswählen');
            return;
        }

        // Check if API key is available
        if (!globalApiKey) {
            console.error('[SET_OPERATING_MODE] API key not available, reloading...');
            const keyLoaded = await loadApiKey();
            if (!keyLoaded) {
                showCommandError('Authentifizierung erforderlich - bitte neu anmelden');
                return;
            }
        }

        console.log('[SET_OPERATING_MODE] Setting operating mode to:', mode, `(${modeNames[mode]}) for device:`, selectedDeviceId);

        // Close the control modal first
        closeControlModal();

        // Show loading modal
        showCommandModal(2, mode); // Default comfort 2

        const res = await fetch('/api/command', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${globalApiKey}`
            },
            body: JSON.stringify({
                operatingMode: mode,
                serial: selectedDeviceId  // Send selected device
            })
        });

        if (res.ok) {
            const data = await res.json();
            // Show success modal with actual values (don't close first!)
            showCommandSuccess(data.comfortLevel, data.operatingMode);
            // Auto-close after 3 seconds
            setTimeout(() => closeCommandModal(), 3000);
        } else {
            console.error('[SET_OPERATING_MODE] API Error:', res.status);
            try {
                const err = await res.json();
                if (res.status === 401) {
                    // API key invalid - reload it
                    console.warn('[SET_OPERATING_MODE] Unauthorized (401) - API key may have expired');
                    globalApiKey = null;
                    showCommandError('Sitzung abgelaufen - bitte neu anmelden');
                } else {
                    showCommandError('Fehler: ' + (err.error || 'Unbekannt'));
                }
            } catch {
                showCommandError('Fehler: HTTP ' + res.status);
            }
        }
    } catch (err) {
        console.error('[SET_OPERATING_MODE]', err);
        showCommandError('Fehler: ' + err.message);
    }
}

// Open Add Device Modal
function showAddDeviceModal() {
    // Close the Device List Modal first
    closeDeviceListModal();

    // Small delay to ensure modal closes before opening the next one
    setTimeout(() => {
        const modal = document.getElementById('addDeviceModal');
        if (modal) {
            // Reset form to default state
            modal.querySelector('.modal-content').innerHTML = `
            <form onsubmit="event.preventDefault(); addDevice();">
                <div class="modal-header-text">
                    Neues Gerät hinzufügen
                    <button class="modal-close" onclick="closeAddDeviceModal()" type="button">×</button>
                </div>

                <div class="form-group">
                    <label>Geräte-Name</label>
                    <input type="text" id="device-name" placeholder="z.B. Wohnzimmer" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>Seriennummer</label>
                    <input type="text" id="device-serial" placeholder="z.B. FA100XXXX" ${addDeviceFromDiscovery ? 'data-from-discovery="true"' : ''} autocomplete="off">
                </div>
                <div class="form-group">
                    <label>Passwort</label>
                    <input type="password" id="device-password" placeholder="FreeAir Passwort" autocomplete="current-password">
                </div>

                <div class="form-group" style="display: flex; gap: 0.75rem;">
                    <button class="btn-secondary" onclick="closeAddDeviceModal()" type="button" style="flex: 1;">Abbrechen</button>
                    <button class="btn-primary" type="submit" style="flex: 1;">Hinzufügen</button>
                </div>
            </form>
        `;

            // Pre-fill serial if from discovery
            setTimeout(() => {
                const serialInput = document.getElementById('device-serial');
                if (serialInput && addDeviceFromDiscovery && addDeviceFromDiscoverySerial) {
                    serialInput.value = addDeviceFromDiscoverySerial;
                    console.log('[SHOW_ADD_MODAL] Pre-filled serial from discovery:', addDeviceFromDiscoverySerial);
                }
            }, 50);

            modal.style.display = 'flex';
            modal.classList.add('active');
        }
    }, 50);
}

// Close Add Device Modal
function closeAddDeviceModal() {
    const modal = document.getElementById('addDeviceModal');
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => {
            modal.style.display = 'none';
            // Clear form fields
            const deviceNameEl = document.getElementById('device-name');
            const deviceSerialEl = document.getElementById('device-serial');
            const devicePasswordEl = document.getElementById('device-password');

            if (deviceNameEl) deviceNameEl.value = '';
            if (deviceSerialEl) deviceSerialEl.value = '';
            if (devicePasswordEl) devicePasswordEl.value = '';

            // Reset discovery flags
            addDeviceFromDiscovery = false;
            addDeviceFromDiscoverySerial = null;
            if (deviceSerialEl) deviceSerialEl.removeAttribute('data-from-discovery');
        }, 300);
    }
}

// Show Loxone Edit Modal
async function showLoxoneEditModal() {
    try {
        // Fetch current Loxone configuration
        const res = await fetch('/api/loxone');
        if (res.ok) {
            const data = await res.json();
            document.getElementById('loxone-ip-modal').value = data.ip || '';
            document.getElementById('loxone-port-modal').value = data.port || '';
        }

        // Show modal
        const modal = document.getElementById('loxoneConfigModal');
        if (modal) {
            modal.style.display = 'flex';
        }
    } catch (err) {
        console.error('[SHOW_LOXONE_MODAL]', err);
        showAlert('Fehler beim Laden der Konfiguration', 'error');
    }
}

// Close Loxone Edit Modal
function closeLoxoneEditModal() {
    const modal = document.getElementById('loxoneConfigModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Control Modal Functions
function openControlModal(deviceId, deviceName) {
    const modal = document.getElementById('controlModal');
    const titleEl = document.getElementById('control-modal-title');

    if (titleEl) {
        titleEl.textContent = `FreeAir Steuerung - ${escapeHtml(deviceName)}`;
    }

    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');

        // Refresh button states immediately
        loadDevices().then(() => {
            updateControlModalButtons(deviceId, deviceName);
        });
    }
}

function closeControlModal() {
    const modal = document.getElementById('controlModal');
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }
}

function updateControlModalButtons(deviceId, deviceName) {
    // Fetch latest device data to update button states
    fetch('/api/devices')
        .then(res => res.json())
        .then(devices => {
            const device = devices.find(d => d.id === deviceId || d.name === deviceName);
            if (!device || !device.last_data) return;

            const data = device.last_data;
            const comfortLevel = data.comfort_level;
            let operatingMode = data.operating_mode;

            // Map mode 0 to 1 (both mean Comfort)
            if (operatingMode === 0) operatingMode = 1;

            // Update comfort buttons
            for (let i = 1; i <= 5; i++) {
                const btn = document.getElementById(`control-comfort-${i}`);
                if (btn) {
                    btn.classList.remove('active');
                    if (i === comfortLevel) {
                        btn.classList.add('active');
                    }
                }
            }

            // Update mode buttons
            for (let i = 1; i <= 4; i++) {
                const btn = document.getElementById(`control-mode-${i}`);
                if (btn) {
                    btn.classList.remove('active');
                    if (i === operatingMode) {
                        btn.classList.add('active');
                    }
                }
            }
        })
        .catch(err => console.error('[CONTROL_MODAL]', err));
}

// Device List Modal Functions
function openDeviceListModal() {
    const modal = document.getElementById('deviceListModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
        loadDeviceListContent();
    }
}

function closeDeviceListModal() {
    const modal = document.getElementById('deviceListModal');
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }
}

async function deleteDeviceFromList(deviceId, deviceName) {
    if (!confirm(`Soll das Gerät "${deviceName}" wirklich gelöscht werden?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/devices/${deviceId}`, {
            method: 'DELETE'
        });

        if (!res.ok) {
            const data = await res.json();
            showAlert(`Löschen fehlgeschlagen: ${data.error}`, 'error');
            return;
        }

        showAlert(`Gerät "${deviceName}" wurde gelöscht`, 'success');
        loadDeviceListContent(); // Refresh the list
    } catch (err) {
        console.error('[DELETE_DEVICE]', err);
        showAlert(`Fehler beim Löschen: ${err.message}`, 'error');
    }
}

async function loadDeviceListContent() {
    try {
        const res = await fetch('/api/devices');
        const devices = await res.json();
        const contentEl = document.getElementById('device-list-content');

        if (!devices || devices.length === 0) {
            contentEl.innerHTML = '<div class="empty-state"><i class="bi bi-inbox"></i><p>Keine Geräte konfiguriert</p></div>';
            return;
        }

        let html = '<div style="display: flex; flex-direction: column; gap: 1rem;">';
        devices.forEach(device => {
            const isOnline = device.last_data && device.last_data.is_online;
            const airFlow = device.last_data?.air_flow ?? '-';
            const hasErrors = device.last_data?.has_errors ? 'Ja' : 'Nein';
            const filterHours = device.last_data?.filter_hours ?? '-';
            const rssi = device.last_data?.rssi ?? '-';
            const comfortLevel = device.last_data?.comfort_level ?? '-';
            const operatingMode = device.last_data?.operating_mode ?? '-';

            html += `
                <div style="padding: 1rem; background-color: rgba(0, 0, 0, 0.2); border-radius: 4px; border-left: 3px solid ${isOnline ? 'var(--accent-green)' : 'var(--accent-red)'};">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem;">
                        <div>
                            <div style="font-weight: 600; color: var(--text-primary);">${escapeHtml(device.name)}</div>
                            <div style="font-size: 0.85rem; color: var(--text-muted);">Serial: ${escapeHtml(device.serial_no)}</div>
                            <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.25rem;">
                                <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: ${isOnline ? 'var(--accent-green)' : 'var(--accent-red)'}; margin-right: 0.25rem;"></span>
                                ${isOnline ? 'Online' : 'Offline'}
                            </div>
                        </div>
                        <div style="display: flex; gap: 0.5rem;">
                            <button class="btn-icon" onclick="openDeviceEditModal('${escapeHtml(device.id)}', '${escapeHtml(device.name)}')" title="Bearbeiten">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn-icon" onclick="deleteDeviceFromList('${escapeHtml(device.id)}', '${escapeHtml(device.name)}')" title="Löschen" style="color: var(--accent-red);">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        contentEl.innerHTML = html;
    } catch (err) {
        console.error('[DEVICE_LIST]', err);
    }
}

// Device Settings Modal Functions
function openDeviceSettingsModal(deviceId, deviceName) {
    const modal = document.getElementById('deviceSettingsModal');
    const titleEl = document.getElementById('settings-modal-title');

    currentSettingsDeviceId = deviceId;
    window.selectedDeviceIdForEdit = deviceId;

    if (titleEl) {
        titleEl.textContent = `Loxone-Felder: ${escapeHtml(deviceName)}`;
    }

    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
        loadDeviceSettingsContent(deviceId);
    }
}

// Open Device Edit Modal (for device management)
function openDeviceEditModal(deviceId, deviceName) {
    const modal = document.getElementById('deviceEditModal');
    const titleEl = document.getElementById('edit-modal-title');

    window.selectedDeviceIdForEdit = deviceId;

    if (titleEl) {
        titleEl.textContent = `Gerät bearbeiten: ${escapeHtml(deviceName)}`;
    }

    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('active');
        loadDeviceEditContent(deviceId);
    }
}

function closeDeviceSettingsModal() {
    const modal = document.getElementById('deviceSettingsModal');
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }
    currentSettingsDeviceId = null;
}

async function saveLoxoneFieldsFromModal() {
    if (!currentSettingsDeviceId) {
        showAlert('Keine Gerät-ID gefunden', 'error');
        return;
    }

    try {
        // Get all checked checkboxes
        const checkboxes = document.querySelectorAll('[id^="loxone-field-"]:checked');
        const selectedFields = Array.from(checkboxes).map(cb => cb.getAttribute('data-field-key'));

        console.log('[SAVE_LOXONE_FIELDS] Saving for device:', currentSettingsDeviceId);
        console.log('[SAVE_LOXONE_FIELDS] Selected fields:', selectedFields);

        const url = `/api/devices/${currentSettingsDeviceId}/loxone-fields`;
        const payload = { loxone_fields: selectedFields };

        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            showAlert('Loxone-Felder gespeichert', 'success');
            console.log('[SAVE_LOXONE_FIELDS] Saved successfully');

            // Reload and close
            await loadDevices();
            await loadDashboard();
            closeDeviceSettingsModal();
        } else {
            const errorText = await res.text();
            console.error('[SAVE_LOXONE_FIELDS] Error:', res.status, errorText);
            showAlert('Fehler beim Speichern: ' + res.status, 'error');
        }
    } catch (err) {
        console.error('[SAVE_LOXONE_FIELDS] Exception:', err);
        showAlert('Fehler: ' + err.message, 'error');
    }
}

async function loadDeviceSettingsContent(deviceId) {
    try {
        const res = await fetch('/api/devices');
        const devices = await res.json();
        const device = devices.find(d => d.id === deviceId);
        const contentEl = document.getElementById('device-settings-content');

        if (!device) {
            contentEl.innerHTML = '<p style="color: var(--text-muted); text-align: center;">Gerät nicht gefunden</p>';
            return;
        }

        const data = device.last_data || {};
        const selectedFields = device.loxone_fields || [];

        // Build field list with checkboxes
        let fieldsHtml = '';
        let hasFields = false;

        if (data && Object.keys(data).length > 0) {
            hasFields = true;
            const measurements = [];

            // Map labels for fields
            const labelMap = {
                outdoor_temp: 'Außentemperatur',
                supply_temp: 'Zuluft-Temperatur',
                extract_humidity: 'Abluft-Feuchte',
                outdoor_humidity: 'Außen-Feuchte',
                co2: 'CO₂-Konzentration',
                co2_indicator: 'CO₂ Indikator',
                comfort_level: 'Komfortstufe',
                operating_mode: 'Betriebsmodus',
                supply_fan_rpm: 'Zuluft-Lüfter (RPM)',
                extract_fan_rpm: 'Abluft-Lüfter (RPM)',
                outdoor_filter_indicator: 'Außenfilter Status',
                exhaust_filter_indicator: 'Abluftfilter Status',
                extract_filter_indicator: 'Extraktionsfilter Status',
                rssi: 'Signalstärke (RSSI)',
                filter_runtime: 'Filterablaufzeit',
                is_online: 'Online-Status'
            };

            const unitMap = {
                outdoor_temp: '°C',
                supply_temp: '°C',
                extract_humidity: '%',
                outdoor_humidity: '%',
                co2: 'ppm',
                supply_fan_rpm: 'rpm',
                extract_fan_rpm: 'rpm',
                rssi: 'dBm'
            };

            for (const [key, value] of Object.entries(data)) {
                let label = labelMap[key] || key.replace(/_/g, ' ').split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                let unit = unitMap[key] || '';

                measurements.push({ key, label, value, unit });
            }

            fieldsHtml = measurements.map(m => {
                let displayValue = m.value;

                // Format operating_mode
                if (m.key === 'operating_mode') {
                    const modeNames = { 0: 'Comfort', 1: 'Comfort', 2: 'Sleep', 3: 'Turbo', 4: 'Cool', 5: 'Service' };
                    displayValue = modeNames[m.value] || m.value;
                }

                // Format boolean
                if (typeof displayValue === 'boolean') {
                    displayValue = displayValue ? 'Ja' : 'Nein';
                }

                return `
                    <div style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background-color: rgba(0, 0, 0, 0.1); border-radius: 4px; margin-bottom: 0.5rem;">
                        <input type="checkbox" id="loxone-field-${m.key}" data-field-key="${m.key}" ${selectedFields.includes(m.key) ? 'checked' : ''} style="cursor: pointer; width: 18px; height: 18px; flex-shrink: 0;">
                        <div style="flex: 1; min-width: 0;">
                            <label for="loxone-field-${m.key}" style="cursor: pointer; display: block; margin-bottom: 0.25rem;">
                                <span style="font-weight: 600; color: var(--text-primary);">${m.label}</span>
                                <span style="color: var(--text-muted); margin-left: 0.5rem;">${m.unit}</span>
                            </label>
                            <div style="font-size: 0.85rem; color: var(--text-muted);">Wert: <span style="color: var(--accent-green); font-weight: 600;">${displayValue}</span></div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        let html = `
            <div>
                <h4 style="font-weight: 600; color: var(--text-primary); margin-bottom: 0.75rem; font-size: 0.95rem;">
                    <i class="bi bi-diagram-3" style="margin-right: 0.5rem;"></i>Loxone-Felder auswählen
                </h4>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem;">
                    Wählen Sie die Messwerte aus, die zu Loxone übertragen werden sollen:
                </p>
                ${hasFields ? fieldsHtml : '<div style="color: var(--text-muted); text-align: center; padding: 1rem;">Noch keine Messdaten verfügbar</div>'}
            </div>
        `;
        contentEl.innerHTML = html;
    } catch (err) {
        console.error('[DEVICE_SETTINGS]', err);
    }
}

// Close Device Settings Modal (Loxone Fields)
function closeDeviceSettingsModal() {
    const modal = document.getElementById('deviceSettingsModal');
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }
    currentSettingsDeviceId = null;
}

// Select All Loxone Fields
function selectAllLoxoneFields() {
    const checkboxes = document.querySelectorAll('input[id^="loxone-field-"]');
    checkboxes.forEach(checkbox => {
        checkbox.checked = true;
    });
}

// Deselect All Loxone Fields
function deselectAllLoxoneFields() {
    const checkboxes = document.querySelectorAll('input[id^="loxone-field-"]');
    checkboxes.forEach(checkbox => {
        checkbox.checked = false;
    });
}

// Load Device Edit Content (FreeAir Configuration)
async function loadDeviceEditContent(deviceId) {
    try {
        const res = await fetch('/api/devices');
        const devices = await res.json();
        const device = devices.find(d => d.id === deviceId);
        const contentEl = document.getElementById('device-edit-content');

        if (!device) {
            contentEl.innerHTML = '<p style="color: var(--text-muted); text-align: center;">Gerät nicht gefunden</p>';
            return;
        }

        let html = `
            <div style="display: flex; flex-direction: column; gap: 1.5rem;">
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" id="edit-device-name" placeholder="z.B. Wohnzimmer" value="${escapeHtml(device.name)}" style="width: 100%;">
                </div>

                <div class="form-group">
                    <label>Seriennummer</label>
                    <input type="text" id="edit-device-serial" placeholder="z.B. 1234567890" value="${escapeHtml(device.serial_no)}" style="width: 100%;">
                </div>

                <div class="form-group">
                    <label>FreeAir Passwort</label>
                    <input type="password" id="edit-device-password" placeholder="FreeAir Passwort" value="${escapeHtml(device.password)}" style="width: 100%;">
                </div>

                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                        <input type="checkbox" id="edit-device-enabled" ${device.enabled ? 'checked' : ''} style="width: 18px; height: 18px;">
                        <span>Gerät aktiviert</span>
                    </label>
                </div>
            </div>
        `;
        
        // Load and add server checkboxes (v1.4.0)
        const serverCheckboxes = await loadServerCheckboxesForDevice(deviceId);
        html += serverCheckboxes;
        
        contentEl.innerHTML = html;
        document.getElementById('edit-modal-title').textContent = `Gerät bearbeiten: ${device.name}`;
    } catch (err) {
        console.error('[DEVICE_EDIT]', err);
    }
}

// Close Device Edit Modal
function closeDeviceEditModal() {
    const modal = document.getElementById('deviceEditModal');
    if (modal) {
        modal.classList.remove('active');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }
}

// Save Device Edit Modal
async function saveDeviceEditModal() {
    try {
        const name = document.getElementById('edit-device-name')?.value;
        const serial = document.getElementById('edit-device-serial')?.value;
        const password = document.getElementById('edit-device-password')?.value;
        const enabled = document.getElementById('edit-device-enabled')?.checked;

        if (!name || !serial || !password) {
            showAlert('Name, Seriennummer und Passwort sind erforderlich', 'warning');
            return;
        }

        const deviceId = window.selectedDeviceIdForEdit;

        const res = await fetch(`/api/devices/${deviceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                serial_no: serial,
                password: password,
                enabled: enabled
            })
        });

        if (res.ok) {
            // Also save server assignments (v1.4.0)
            await saveDeviceServerAssignments(deviceId);
            
            showAlert('Gerät aktualisiert', 'success');
            closeDeviceEditModal();
            setTimeout(() => {
                loadDevices();
                loadDeviceListContent();
            }, 500);
        } else {
            showAlert('Fehler beim Speichern', 'error');
        }
    } catch (err) {
        console.error('[SAVE_DEVICE_EDIT]', err);
        showAlert('Fehler: ' + err.message, 'error');
    }
}

// Save Loxone Config from Modal
async function saveLoxoneConfigModal() {
    try {
        const ip = document.getElementById('loxone-ip-modal')?.value;
        const port = document.getElementById('loxone-port-modal')?.value;

        if (!ip || !port) {
            showAlert('IP und Port sind erforderlich', 'warning');
            return;
        }

        const res = await fetch('/api/loxone', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ip: ip,
                port: parseInt(port),
                enabled: true
            })
        });

        if (res.ok) {
            showAlert('Loxone Konfiguration gespeichert', 'success');
            closeLoxoneEditModal();
            // Reload Loxone status
            setTimeout(loadLoxoneConfig, 500);
        } else {
            showAlert('Fehler beim Speichern', 'error');
        }
    } catch (err) {
        console.error('[SAVE_LOXONE_CONFIG_MODAL]', err);
        showAlert('Fehler: ' + err.message, 'error');
    }
}

// Savve Loxone Config (legacy)
async function saveLoxoneConfig() {
    try {
        const ip = document.getElementById('loxone-ip')?.value;
        const port = document.getElementById('loxone-port')?.value;

        if (!ip || !port) {
            showAlert('IP und Port sind erforderlich', 'warning');
            return;
        }

        const res = await fetch('/api/loxone', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ip: ip,
                port: parseInt(port),
                enabled: true
            })
        });

        if (res.ok) {
            showAlert('Loxone Konfiguration gespeichert', 'success');
        } else {
            showAlert('Fehler beim Speichern', 'error');
        }
    } catch (err) {
        console.error('[SAVE_LOXONE_CONFIG]', err);
        showAlert('Fehler: ' + err.message, 'error');
    }
}

// ===== AUTO-DISCOVERY FUNCTIONS =====

async function loadUnknownDevices() {
    try {
        const res = await fetch('/api/discovery/unknown-devices');
        const data = await res.json();

        const alertEl = document.getElementById('unknown-devices-alert');
        const listEl = document.getElementById('unknown-devices-list');


        if (!alertEl || !listEl) {
            return;
        }

        const unknownDevices = data.unknown_devices || {};
        const count = data.count || 0;

        if (count === 0) {
            alertEl.style.display = 'none';
            return;
        }

        // Show alert
        alertEl.style.display = 'block';
        listEl.innerHTML = '';

        // Display each unknown device
        Object.entries(unknownDevices).forEach(([serial, info]) => {
            const deviceEl = document.createElement('div');
            deviceEl.style.cssText = `
                padding: 0.75rem;
                background-color: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: 4px;
                margin-bottom: 0.5rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
            `;

            const contactCount = info.contact_count || 0;
            const lastSeen = info.last_seen ? new Date(info.last_seen).toLocaleTimeString('de-DE') : 'unbekannt';

            deviceEl.innerHTML = `
                <div>
                    <div style="color: var(--text-primary); font-weight: 600;">Serial: ${serial}</div>
                    <div style="color: var(--text-muted); font-size: 0.85rem;">
                        ${contactCount} Verbindung(en) | Zuletzt: ${lastSeen}
                    </div>
                </div>
                <button class="btn-icon" onclick="showAddUnknownDeviceModal('${serial}')" style="padding: 0.4rem 0.8rem; font-size: 0.85rem;">
                    <i class="bi bi-plus-lg"></i> Hinzufügen
                </button>
            `;

            listEl.appendChild(deviceEl);
        });
    } catch (err) {
        console.error('[UNKNOWN_DEVICES]', err);
    }
}

function showAddUnknownDeviceModal(serialNo) {
    // Set flags for the modal
    addDeviceFromDiscovery = true;
    addDeviceFromDiscoverySerial = serialNo;

    // Open modal from unknown device discovery
    showAddDeviceModal();

    // Pre-fill the name field and focus on it
    setTimeout(() => {
        const nameInput = document.getElementById('device-name');
        if (nameInput) {
            nameInput.focus();
        }
    }, 100);
}

/**
 * Download Loxone XML configuration for the current device
 */
async function downloadLoxoneXml() {
    if (!currentSettingsDeviceId) {
        showAlert('Gerät nicht gefunden', 'error');
        return;
    }

    try {
        const url = `/api/devices/${currentSettingsDeviceId}/loxone-xml`;
        const response = await fetch(url);

        if (!response.ok) {
            const data = await response.json();
            showAlert(`XML-Download fehlgeschlagen: ${data.error}`, 'error');
            return;
        }

        // Get filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('content-disposition');
        let filename = `FreeAir2Lox-Inputs.xml`;
        if (contentDisposition) {
            // Match filename with or without quotes: filename="xxx" or filename=xxx
            const match = contentDisposition.match(/filename="?([^"\s;]+)"?/);
            if (match) filename = match[1];
        }

        // Download file
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(downloadUrl);

        showAlert(`XML erfolgreich heruntergeladen: ${filename}`, 'success');
    } catch (error) {
        logger.error('XML download error:', error);
        showAlert(`XML-Download fehlgeschlagen: ${error.message}`, 'error');
    }
}

/**
 * Download Loxone VirtualOut XML for commands to the current device
 */
async function downloadLoxoneVirtualOut() {
    if (!currentSettingsDeviceId) {
        showAlert('Gerät nicht gefunden', 'error');
        return;
    }

    try {
        const url = `/api/devices/${currentSettingsDeviceId}/loxone-virtual-outputs`;
        const response = await fetch(url);

        if (!response.ok) {
            const data = await response.json();
            showAlert(`VirtualOut-Download fehlgeschlagen: ${data.error}`, 'error');
            return;
        }

        // Get filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('content-disposition');
        let filename = `FreeAir2Lox-Outputs.xml`;
        if (contentDisposition) {
            // Match filename with or without quotes: filename="xxx" or filename=xxx
            const match = contentDisposition.match(/filename="?([^"\s;]+)"?/);
            if (match) filename = match[1];
        }

        // Download file
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(downloadUrl);

        showAlert(`VirtualOut erfolgreich heruntergeladen: ${filename}`, 'success');
    } catch (error) {
        logger.error('VirtualOut download error:', error);
        showAlert(`VirtualOut-Download fehlgeschlagen: ${error.message}`, 'error');
    }
}

// ============================================================================
// UPDATE STATUS INDICATOR FUNCTIONS
// ============================================================================

function initUpdateStatusIndicator() {
    // Starte Timer wenn nicht aktiv
    if (!updateStatusInterval) {
        updateStatusInterval = setInterval(updateStatusDisplay, 1000);
    }
    // Initial update
    updateStatusDisplay();
}

function updateStatusDisplay() {
    const indicator = document.getElementById('update-status-indicator');
    const icon = document.getElementById('update-status-icon');

    if (!indicator || !icon) return;

    // Wenn gerade am Polling
    if (isPolling) {
        indicator.className = 'status-loading';
        icon.textContent = '⟳';
        indicator.setAttribute('data-tooltip', 'wird aktualisiert...');
        return;
    }

    // Falls noch nie aktualisiert
    if (!lastUpdateTime) {
        indicator.className = 'status-loading';
        icon.textContent = '⟳';
        indicator.setAttribute('data-tooltip', 'Laden...');
        return;
    }

    // Berechne Sekunden seit letztem Update
    const secondsAgo = Math.floor((Date.now() - lastUpdateTime) / 1000);

    // Entferne alte Classes
    indicator.className = '';

    // Setze Status basierend auf Alter
    if (secondsAgo < 30) {
        indicator.classList.add('status-ok');
        icon.textContent = '🟢';
    } else if (secondsAgo < 60) {
        indicator.classList.add('status-warning');
        icon.textContent = '🟡';
    } else {
        indicator.classList.add('status-error');
        icon.textContent = '🔴';
    }

    // Formatiere Text für Tooltip
    let timeText;
    if (secondsAgo < 60) {
        timeText = `vor ${secondsAgo} Sekunde${secondsAgo !== 1 ? 'n' : ''} aktualisiert`;
    } else if (secondsAgo < 3600) {
        const minutes = Math.floor(secondsAgo / 60);
        timeText = `vor ${minutes} Minute${minutes !== 1 ? 'n' : ''} aktualisiert`;
    } else {
        const hours = Math.floor(secondsAgo / 3600);
        timeText = `vor ${hours} Stunde${hours !== 1 ? 'n' : ''} aktualisiert`;
    }

    indicator.setAttribute('data-tooltip', timeText);
}

function setUpdateTime() {
    lastUpdateTime = Date.now();
    updateStatusDisplay();
}

function setPollingStatus(active) {
    isPolling = active;
    updateStatusDisplay();
}

// ============================================================================
// ADMIN CONTROL FUNCTIONS
// ============================================================================

function showAdminControlModal() {
    const modal = document.getElementById('adminControlModal');
    if (!modal) {
        console.error('Admin Control Modal nicht gefunden');
        return;
    }

    // Clear form
    document.getElementById('admin-old-password').value = '';
    document.getElementById('admin-new-password').value = '';
    document.getElementById('admin-confirm-password').value = '';
    document.getElementById('admin-control-alert').style.display = 'none';

    modal.style.display = 'flex';
}

function closeAdminControlModal() {
    const modal = document.getElementById('adminControlModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function changeAdminPassword() {
    const oldPassword = document.getElementById('admin-old-password').value.trim();
    const newPassword = document.getElementById('admin-new-password').value.trim();
    const confirmPassword = document.getElementById('admin-confirm-password').value.trim();
    const alertDiv = document.getElementById('admin-control-alert');

    // Validation
    if (!oldPassword || !newPassword || !confirmPassword) {
        showAdminAlert('Alle Felder müssen ausgefüllt sein', 'error', alertDiv);
        return;
    }

    if (newPassword.length < 4) {
        showAdminAlert('Neues Passwort muss mindestens 4 Zeichen lang sein', 'error', alertDiv);
        return;
    }

    if (newPassword !== confirmPassword) {
        showAdminAlert('Neue Passwörter stimmen nicht überein', 'error', alertDiv);
        return;
    }

    if (oldPassword === newPassword) {
        showAdminAlert('Neues Passwort muss sich vom alten unterscheiden', 'error', alertDiv);
        return;
    }

    try {
        const response = await fetch('/api/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_password: oldPassword,
                new_password: newPassword,
                confirm_password: confirmPassword
            })
        });

        if (!response.ok) {
            const data = await response.json();
            showAdminAlert(data.error || 'Fehler beim Ändern des Passworts', 'error', alertDiv);
            return;
        }

        showAdminAlert('✓ Passwort erfolgreich geändert', 'success', alertDiv);

        // Clear inputs
        document.getElementById('admin-old-password').value = '';
        document.getElementById('admin-new-password').value = '';
        document.getElementById('admin-confirm-password').value = '';

        // Close modal after 2 seconds
        setTimeout(() => {
            closeAdminControlModal();
        }, 2000);

    } catch (error) {
        console.error('Password change error:', error);
        showAdminAlert('Fehler: ' + error.message, 'error', alertDiv);
    }
}

async function logoutAdmin() {
    if (!confirm('Wirklich abmelden?')) {
        return;
    }

    try {
        clearApiKey();  // Clear API key before logout
        await fetch('/logout', { method: 'POST' });
        window.location.href = '/login';
    } catch (error) {
        console.error('Logout error:', error);
        showAlert('Abmeldung fehlgeschlagen', 'error');
    }
}

// ===== ADMIN MODAL TAB SWITCHING =====

function switchAdminTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.admin-tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });

    // Show selected tab
    const selectedTab = document.getElementById(`admin-tab-${tabName}`);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }

    // Mark button as active
    event.target.classList.add('active');
}

// ===== CONFIG BACKUP =====

async function downloadBackup() {
    try {
        showAlert('⏳ Backup wird heruntergeladen...', 'info');

        const response = await fetch('/api/config/backup', {
            method: 'GET',
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error('Backup fehlgeschlagen');
        }

        // Get filename from Content-Disposition header
        const contentDisposition = response.headers.get('content-disposition');
        let filename = 'FreeAir2Lox-config.json';

        if (contentDisposition) {
            const match = contentDisposition.match(/filename[^;=\n]*=([^;\n]*)/);
            if (match) {
                filename = match[1].replace(/"/g, '').trim();
            }
        }

        // Download file
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showAlert(`✓ Config heruntergeladen: ${filename}`, 'success');

    } catch (err) {
        console.error('Backup error:', err);
        showAlert('✗ Backup fehlgeschlagen', 'error');
    }
}

// ===== CONFIG RESTORE =====

function selectRestoreFile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';

    input.onchange = async (e) => {
        const file = e.target.files[0];

        if (!file) return;

        // Confirm with user
        if (!confirm(`Überschreibe aktuelle Konfiguration mit:\n${file.name}?\n\nDies kann nicht rückgängig gemacht werden!`)) {
            return;
        }

        try {
            showAlert('⏳ Konfiguration wird wiederhergestellt...', 'info');

            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/config/restore', {
                method: 'POST',
                credentials: 'include',
                body: formData
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Restore fehlgeschlagen');
            }

            const result = await response.json();

            showAlert('✓ Konfiguration wiederhergestellt! App wird neu geladen...', 'success');

            // Reload app after 2 seconds
            setTimeout(() => {
                location.reload();
            }, 2000);

        } catch (err) {
            console.error('Restore error:', err);
            showAlert(`✗ ${err.message}`, 'error');
        }
    };

    input.click();
}

function showAdminAlert(message, type, alertDiv) {
    alertDiv.style.display = 'block';
    alertDiv.className = 'alert alert-' + type;
    alertDiv.textContent = message;

    // Auto-hide success messages
    if (type === 'success') {
        setTimeout(() => {
            alertDiv.style.display = 'none';
        }, 3000);
    }
}

// ===== ADVANCED LOGS (v1.3.0) =====

window.logState = {
    allLogs: [],
    filteredLogs: [],
    selectedLevels: ['DEBUG', 'INFO', 'WARNING', 'ERROR'],
    searchText: '',
    timeRange: '24h',
    isPaused: false,
    eventSource: null,
    updateInterval: null
};

function openAdvancedLogs() {
    const container = document.getElementById('advanced-logs-container');
    container.classList.add('visible');

    // Set 24h as active time range button
    document.querySelectorAll('.time-range-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('data-range') === '24h') {
            btn.classList.add('active');
        }
    });

    updateLogsFromAPI();
    updateLogStats();
    initLogStreaming();

    // Update stats every 5 seconds
    if (window.logState.updateInterval) clearInterval(window.logState.updateInterval);
    window.logState.updateInterval = setInterval(() => {
        if (!window.logState.isPaused) {
            updateLogStats();
        }
    }, 5000);
}

function closeAdvancedLogs() {
    const container = document.getElementById('advanced-logs-container');
    container.classList.remove('visible');
    if (window.logState.eventSource) {
        window.logState.eventSource.close();
    }
    if (window.logState.updateInterval) {
        clearInterval(window.logState.updateInterval);
    }
}

function updateLogsFromAPI() {
    const levels = document.querySelectorAll('input[id^="filter-"]:checked');
    const selectedLevels = Array.from(levels).map(el => {
        const id = el.id;
        return id.replace('filter-', '').toUpperCase();
    });

    const search = document.getElementById('search-logs-input')?.value || '';
    const params = new URLSearchParams({
        level: selectedLevels.join(','),
        search: search,
        limit: 500,
        time_range: window.logState.timeRange
    });

    fetch(`/api/logs?${params}`, {
        credentials: 'include'
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                window.logState.allLogs = data.logs;
                filterLogs();
            }
        })
        .catch(e => console.error('Error fetching logs:', e));
}

function filterLogs() {
    const levels = [];
    document.querySelectorAll('input[id^="filter-"]:checked').forEach(el => {
        levels.push(el.id.replace('filter-', '').toUpperCase());
    });

    const search = document.getElementById('search-logs-input')?.value.toLowerCase() || '';

    window.logState.filteredLogs = window.logState.allLogs.filter(log => {
        let match = true;

        if (levels.length > 0 && !levels.includes(log.level)) match = false;
        if (search && !log.message.toLowerCase().includes(search) && !log.module.toLowerCase().includes(search)) match = false;

        return match;
    });

    renderLogs();
}

let filterTimeout;
function debouncedFilterLogs() {
    clearTimeout(filterTimeout);
    filterTimeout = setTimeout(filterLogs, 300);
}

function setTimeRange(range) {
    window.logState.timeRange = range;
    document.querySelectorAll('.time-range-btn').forEach(btn => {
        // Mark button as active if its data-range matches the selected range
        if (btn.getAttribute('data-range') === range) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    updateLogsFromAPI();
}

function togglePauseLogs() {
    window.logState.isPaused = !window.logState.isPaused;
    const btn = document.getElementById('pause-btn-logs');
    const indicator = document.getElementById('live-indicator');
    const text = document.getElementById('live-text');

    if (window.logState.isPaused) {
        btn.textContent = '▶ Resume';
        indicator.style.background = '#ffaa00';
        text.textContent = '⏸ PAUSED';
    } else {
        btn.textContent = '⏸ Pause';
        indicator.style.background = '#00ff41';
        text.textContent = '● LIVE';
    }
}

function initLogStreaming() {
    if (window.logState.eventSource) {
        window.logState.eventSource.close();
    }

    // EventSource automatisch mit credentials (nur wenn same-origin)
    window.logState.eventSource = new EventSource('/api/logs/stream');

    window.logState.eventSource.onmessage = (event) => {
        if (window.logState.isPaused) return;

        try {
            const newLog = JSON.parse(event.data);
            window.logState.allLogs.unshift(newLog);

            if (window.logState.allLogs.length > 500) {
                window.logState.allLogs.pop();
            }

            filterLogs();
        } catch (e) {
            console.error('Error parsing log:', e);
        }
    };

    window.logState.eventSource.onerror = (error) => {
        console.error('Log streaming error:', error);
        // Versuche neu zu verbinden nach 3 Sekunden
        if (window.logState.eventSource) {
            window.logState.eventSource.close();
        }
        setTimeout(() => {
            if (!window.logState.isPaused && document.getElementById('advanced-logs-container').style.display !== 'none') {
                console.log('Reconnecting SSE...');
                initLogStreaming();
            }
        }, 3000);
    };
}

function renderLogs() {
    const container = document.getElementById('log-entries-container');
    if (!container) return;

    if (window.logState.filteredLogs.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); text-align: center; padding: 2rem;">Keine Logs gefunden</div>';
        return;
    }

    container.innerHTML = window.logState.filteredLogs
        .map(log => `
            <div class="log-entry">
                <div class="log-time">${log.timestamp.substring(11, 19)}</div>
                <div class="log-level ${log.level}">${log.level}</div>
                <div class="log-message">${escapeHtml(log.message)}</div>
            </div>
        `)
        .join('');

    container.scrollTop = container.scrollHeight;
}

function updateLogStats() {
    fetch('/api/logs/stats', {
        credentials: 'include'
    })
        .then(r => r.json())
        .then(stats => {
            if (stats.error) {
                console.error('Stats error:', stats.error);
                return;
            }
            document.getElementById('stat-errors').textContent = stats.errors_24h || 0;
            document.getElementById('stat-warnings').textContent = stats.warnings_24h || 0;
            document.getElementById('stat-avg-response').textContent = (stats.avg_response_time_ms || 0).toFixed(1) + 'ms';
            document.getElementById('stat-uptime').textContent = formatUptime(stats.uptime_seconds || 0);
        })
        .catch(e => console.error('Error fetching stats:', e));
}

function formatUptime(seconds) {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);

    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${mins}m`;
    return `${mins}m`;
}

function exportLogs() {
    const format = prompt('Export format? (txt/csv/json)', 'txt');
    if (!format) return;

    const levels = Array.from(document.querySelectorAll('input[id^="filter-"]:checked'))
        .map(el => el.id.replace('filter-', '').toUpperCase())
        .join(',');

    fetch('/api/logs/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
            level: levels,
            time_range: window.logState.timeRange,
            format: format
        })
    })
    .then(r => r.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `freeair2lox-logs_${new Date().toISOString().split('T')[0]}.${format}`;
        a.click();
        window.URL.revokeObjectURL(url);
    })
    .catch(e => alert('Export fehlgeschlagen: ' + e));
}

function clearLogsAdvanced() {
    if (confirm('Alle Logs wirklich löschen? (nur In-Memory Buffer)')) {
        fetch('/api/logs/clear', {
            method: 'POST',
            credentials: 'include'
        })
            .then(() => {
                window.logState.allLogs = [];
                window.logState.filteredLogs = [];
                renderLogs();
                alert('Logs gelöscht');
            })
            .catch(e => alert('Löschen fehlgeschlagen: ' + e));
    }
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// ===== LOXONE SERVER MANAGEMENT (v1.4.0) =====

// Open Server Management Modal
async function openLoxoneServersModal() {
    const modal = document.getElementById('loxoneServersModal');
    if (modal) {
        modal.style.display = 'flex';
        await loadServersForModal();
    }
}

// Close Server Management Modal
function closeLoxoneServersModal() {
    const modal = document.getElementById('loxoneServersModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Load all servers and display them
async function loadServersForModal() {
    try {
        const res = await fetch('/api/loxone/servers');
        if (!res.ok) throw new Error('Failed to fetch servers');
        
        const servers = await res.json();
        const listEl = document.getElementById('servers-list');
        
        if (!listEl) return;
        
        if (servers.length === 0) {
            listEl.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 1rem;">Noch keine Server konfiguriert</div>';
            return;
        }
        
        let html = '';
        for (const server of servers) {
            const statusIcon = server.enabled ? '🟢' : '🔴';
            html += `
                <div style="border: 1px solid var(--border-color); border-radius: 0.5rem; padding: 1rem; background-color: var(--bg-tertiary);">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.75rem;">
                        <div>
                            <h5 style="color: var(--accent-green); margin: 0 0 0.25rem 0;">${statusIcon} ${escapeHtml(server.name)}</h5>
                            <div style="font-size: 0.85rem; color: var(--text-muted);">${escapeHtml(server.ip)}:${server.port}</div>
                            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">ID: ${escapeHtml(server.id)}</div>
                        </div>
                        <div style="display: flex; gap: 0.5rem;">
                            <button class="btn-icon" onclick="editServer('${escapeHtml(server.id)}')" title="Bearbeiten">
                                <i class="bi bi-pencil"></i>
                            </button>
                            <button class="btn-icon" onclick="testServer('${escapeHtml(server.id)}')" title="Verbindung testen">
                                <i class="bi bi-lightning"></i>
                            </button>
                            <button class="btn-icon" onclick="regenerateServerKey('${escapeHtml(server.id)}')" title="API-Key neugenerieren">
                                <i class="bi bi-arrow-clockwise"></i>
                            </button>
                            ${server.id !== 'default' ? `<button class="btn-icon" onclick="deleteServer('${escapeHtml(server.id)}')" title="Löschen" style="color: var(--accent-red);">
                                <i class="bi bi-trash"></i>
                            </button>` : ''}
                        </div>
                    </div>
                </div>
            `;
        }
        listEl.innerHTML = html;
    } catch (err) {
        console.error('[SERVERS_MODAL]', err);
        document.getElementById('servers-list').innerHTML = `<div style="color: var(--accent-red);">Fehler beim Laden: ${escapeHtml(err.message)}</div>`;
    }
}

// Open Add Server Modal
function openAddServerModal() {
    document.getElementById('server-modal-title').textContent = 'Neuen Loxone Server hinzufügen';
    document.getElementById('server-id-input').disabled = false;
    document.getElementById('server-id-input').value = '';
    document.getElementById('server-name-input').value = '';
    document.getElementById('server-ip-input').value = '';
    document.getElementById('server-port-input').value = '5555';
    document.getElementById('server-enabled-input').checked = true;
    document.getElementById('server-edit-alert').style.display = 'none';
    document.getElementById('server-save-button').onclick = () => saveNewServer();
    
    const modal = document.getElementById('serverEditModal');
    if (modal) modal.style.display = 'flex';
}

// Open Edit Server Modal
async function editServer(serverId) {
    try {
        const res = await fetch(`/api/loxone/servers/${serverId}`);
        if (!res.ok) throw new Error('Server nicht gefunden');
        
        const server = await res.json();
        
        document.getElementById('server-modal-title').textContent = `Server "${escapeHtml(server.name)}" bearbeiten`;
        document.getElementById('server-id-input').value = server.id;
        document.getElementById('server-id-input').disabled = true;
        document.getElementById('server-name-input').value = server.name;
        document.getElementById('server-ip-input').value = server.ip;
        document.getElementById('server-port-input').value = server.port;
        document.getElementById('server-enabled-input').checked = server.enabled;
        document.getElementById('server-edit-alert').style.display = 'none';
        document.getElementById('server-save-button').onclick = () => saveEditedServer(serverId);
        
        const modal = document.getElementById('serverEditModal');
        if (modal) modal.style.display = 'flex';
    } catch (err) {
        console.error('[EDIT_SERVER]', err);
        showAlert('Fehler beim Laden des Servers: ' + err.message, 'error');
    }
}

// Close Server Edit Modal
function closeServerEditModal() {
    const modal = document.getElementById('serverEditModal');
    if (modal) modal.style.display = 'none';
}

// Save New Server
async function saveNewServer() {
    try {
        const id = document.getElementById('server-id-input').value.trim();
        const name = document.getElementById('server-name-input').value.trim();
        const ip = document.getElementById('server-ip-input').value.trim();
        const port = parseInt(document.getElementById('server-port-input').value) || 5555;
        const enabled = document.getElementById('server-enabled-input').checked;
        
        if (!id || !name || !ip) {
            showAlert('Bitte füllen Sie alle Pflichtfelder aus', 'warning');
            return;
        }
        
        const res = await fetch('/api/loxone/servers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, name, ip, port, enabled })
        });
        
        if (res.ok) {
            showAlert('Server hinzugefügt', 'success');
            closeServerEditModal();
            await loadServersForModal();
        } else {
            const err = await res.json();
            showAlert('Fehler: ' + (err.error || 'Unbekannter Fehler'), 'error');
        }
    } catch (err) {
        console.error('[SAVE_NEW_SERVER]', err);
        showAlert('Fehler beim Speichern: ' + err.message, 'error');
    }
}

// Save Edited Server
async function saveEditedServer(serverId) {
    try {
        const name = document.getElementById('server-name-input').value.trim();
        const ip = document.getElementById('server-ip-input').value.trim();
        const port = parseInt(document.getElementById('server-port-input').value) || 5555;
        const enabled = document.getElementById('server-enabled-input').checked;
        
        if (!name || !ip) {
            showAlert('Bitte füllen Sie alle Pflichtfelder aus', 'warning');
            return;
        }
        
        const res = await fetch(`/api/loxone/servers/${serverId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, ip, port, enabled })
        });
        
        if (res.ok) {
            showAlert('Server aktualisiert', 'success');
            closeServerEditModal();
            await loadServersForModal();
        } else {
            const err = await res.json();
            showAlert('Fehler: ' + (err.error || 'Unbekannter Fehler'), 'error');
        }
    } catch (err) {
        console.error('[SAVE_EDITED_SERVER]', err);
        showAlert('Fehler beim Speichern: ' + err.message, 'error');
    }
}

// Delete Server
async function deleteServer(serverId) {
    if (!confirm('Diesen Server wirklich löschen? Geräte-Zuweisungen werden entfernt.')) {
        return;
    }
    
    try {
        const res = await fetch(`/api/loxone/servers/${serverId}`, {
            method: 'DELETE'
        });
        
        if (res.ok) {
            showAlert('Server gelöscht', 'success');
            await loadServersForModal();
        } else {
            const err = await res.json();
            showAlert('Fehler: ' + (err.error || 'Unbekannter Fehler'), 'error');
        }
    } catch (err) {
        console.error('[DELETE_SERVER]', err);
        showAlert('Fehler beim Löschen: ' + err.message, 'error');
    }
}

// Test Server Connection
async function testServer(serverId) {
    try {
        const res = await fetch(`/api/loxone/servers/${serverId}/test`, {
            method: 'POST'
        });
        
        const data = await res.json();
        if (res.ok) {
            showAlert('Test-Paket gesendet ✓', 'success');
        } else {
            showAlert('Fehler: ' + (data.error || 'Verbindung fehlgeschlagen'), 'error');
        }
    } catch (err) {
        console.error('[TEST_SERVER]', err);
        showAlert('Fehler beim Testen: ' + err.message, 'error');
    }
}

// Regenerate Server API Key
async function regenerateServerKey(serverId) {
    if (!confirm('API-Key wirklich neu generieren? Dies wird den aktuellen Key ungültig machen.')) {
        return;
    }
    
    try {
        const res = await fetch(`/api/loxone/servers/${serverId}/regenerate-key`, {
            method: 'POST'
        });
        
        const data = await res.json();
        if (res.ok) {
            showAlert('Neuer API-Key generiert ✓', 'success');
            console.log('New API Key:', data.api_key);
            await loadServersForModal();
        } else {
            showAlert('Fehler: ' + (data.error || 'Unbekannter Fehler'), 'error');
        }
    } catch (err) {
        console.error('[REGENERATE_KEY]', err);
        showAlert('Fehler beim Neugenerieren: ' + err.message, 'error');
    }
}

// Load server checkboxes in device edit modal
async function loadServerCheckboxesForDevice(deviceId) {
    try {
        // Get all servers
        const serversRes = await fetch('/api/loxone/servers');
        if (!serversRes.ok) return '';
        const servers = await serversRes.json();
        
        // Get assigned servers for this device
        const assignedRes = await fetch(`/api/devices/${deviceId}`);
        if (!assignedRes.ok) return '';
        const device = await assignedRes.json();
        const assignedServers = device.loxone_servers || [];
        
        let html = `
            <div style="border-top: 1px solid var(--border-color); padding-top: 1rem; margin-top: 1rem;">
                <h5 style="color: var(--accent-green); margin-bottom: 0.75rem;">
                    <i class="bi bi-server"></i> Zugewiesene Loxone Server
                </h5>
                <div style="display: grid; gap: 0.5rem;">
        `;
        
        if (servers.length === 0) {
            html += '<div style="color: var(--text-muted); font-size: 0.9rem;">Noch keine Server konfiguriert</div>';
        } else {
            for (const server of servers) {
                const isAssigned = assignedServers.includes(server.id);
                const checkId = `server-check-${deviceId}-${server.id}`;
                html += `
                    <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; padding: 0.5rem; border-radius: 0.25rem; background-color: rgba(0,0,0,0.2); transition: background-color 0.2s;">
                        <input type="checkbox" id="${checkId}" data-server-id="${server.id}" ${isAssigned ? 'checked' : ''} style="cursor: pointer;">
                        <div>
                            <div style="font-weight: 500;">${escapeHtml(server.name)}</div>
                            <div style="font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(server.ip)}:${server.port}</div>
                        </div>
                    </label>
                `;
            }
        }
        
        html += '</div></div>';
        return html;
    } catch (err) {
        console.error('[LOAD_SERVER_CHECKBOXES]', err);
        return '<div style="color: var(--accent-red);">Fehler beim Laden der Server</div>';
    }
}

// Save device server assignments
async function saveDeviceServerAssignments(deviceId) {
    try {
        // Get all checked server checkboxes
        const checkboxes = document.querySelectorAll(`input[id^="server-check-${deviceId}-"]`);
        const assignedServers = [];
        
        checkboxes.forEach(cb => {
            if (cb.checked) {
                assignedServers.push(cb.getAttribute('data-server-id'));
            }
        });
        
        // Save to config
        const res = await fetch(`/api/devices/${deviceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ loxone_servers: assignedServers })
        });
        
        if (!res.ok) {
            console.warn('Could not save server assignments');
        }
    } catch (err) {
        console.error('[SAVE_DEVICE_SERVERS]', err);
    }
}
