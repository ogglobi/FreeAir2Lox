"""
FreeAir Bridge - Web Admin Interface & HTTP API
Middleware between FreeAir 100 devices and Loxone Smart Home
"""

import json
import logging
import os
import socket
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO
from typing import Optional

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
)

# Import modular components
from crypto_utils import decrypt_freeair_payload
from freeair_parser import parse_freeair_data
from loxone_xml import (
    generate_loxone_command_template,
    generate_loxone_xml,
    get_bridge_ip,
)


# ===== CUSTOM LOG HANDLER FOR UI =====
class LogBufferHandler(logging.Handler):
    """Custom handler to store log records for UI display"""
    def __init__(self, maxlen=500):
        super().__init__()
        self.log_buffer = deque(maxlen=maxlen)
        self._buffer_lock = threading.RLock()  # Use RLock to prevent deadlocks

    def emit(self, record):
        try:
            log_entry = {
                'level': record.levelname,
                'message': self.format(record),
                'timestamp': datetime.now().isoformat()
            }
            with self._buffer_lock:
                self.log_buffer.append(log_entry)

            # ALSO add to advanced log buffer for new API (v1.3.0)
            try:
                log_buffer.add(
                    level=record.levelname,
                    module=record.module or 'app',
                    message=self.format(record),
                    context={}
                )
                # Write to file
                LogFileRotation.write_log({
                    'timestamp': datetime.now().isoformat(),
                    'level': record.levelname,
                    'module': record.module or 'app',
                    'message': self.format(record)
                })
            except Exception:
                pass  # Don't break if advanced logging fails

        except Exception:
            self.handleError(record)

    def get_logs(self, level='all', limit=50):
        """Get logs filtered by level"""
        with self._buffer_lock:
            logs = list(self.log_buffer)

        if level != 'all':
            level_upper = level.upper()
            logs = [l for l in logs if l['level'] == level_upper]

        # Return most recent first
        return list(reversed(logs[-limit:]))

# Filter for repetitive HTTP logs
class HTTPLogFilter(logging.Filter):
    """Filter out repetitive HTTP polling requests"""
    QUIET_PATHS = [
        '/api/status',
        '/api/devices',
        '/api/logs',
        '/api/loxone',
        '/apps/data/blucontrol/',  # General polling
    ]

    def filter(self, record):
        # Only filter HTTP requests (werkzeug logs)
        if 'werkzeug' not in record.name:
            return True

        msg = record.getMessage()

        # Filter out GET requests to quiet paths with 200 status
        for path in self.QUIET_PATHS:
            if f'GET {path}' in msg and '200' in msg:
                return False

        # Allow everything else (errors, POST requests, non-200 responses)
        return True


# ===== ADVANCED LOGGING INFRASTRUCTURE (v1.3.0) =====
class LogBuffer:
    """Circular buffer for structured in-memory log storage"""

    def __init__(self, max_size=500):
        self.buffer = deque(maxlen=max_size)
        self.lock = threading.Lock()
        self.log_id_counter = 0

    def add(self, level, module, message, context=None):
        """Add structured log entry to buffer"""
        with self.lock:
            self.log_id_counter += 1
            entry = {
                'id': f"log_{self.log_id_counter}",
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'level': level,
                'module': module,
                'message': message,
                'context': context or {}
            }
            self.buffer.append(entry)
            return entry

    def get_all(self):
        """Get all logs from buffer (reversed, newest first)"""
        with self.lock:
            return list(reversed(list(self.buffer)))

    def clear(self):
        """Clear buffer"""
        with self.lock:
            self.buffer.clear()
            self.log_id_counter = 0

    def get_filtered(self, level_filter=None, search_text='', device_filter=None, limit=100, offset=0):
        """Get filtered logs"""
        all_logs = self.get_all()

        # Apply filters
        filtered = all_logs
        if level_filter:
            filtered = [l for l in filtered if l['level'] in level_filter]
        if search_text:
            search_lower = search_text.lower()
            filtered = [l for l in filtered if search_lower in l['message'].lower()]
        if device_filter:
            filtered = [l for l in filtered if l['context'].get('device') == device_filter]

        # Pagination
        total = len(filtered)
        paginated = filtered[offset:offset+limit]

        return {
            'total': total,
            'count': len(paginated),
            'offset': offset,
            'logs': paginated
        }


class LogFileRotation:
    """Manage rotating log files with retention policy"""

    LOG_DIR = '/app/logs'
    RETENTION_DAYS = 7

    @staticmethod
    def ensure_dir():
        """Ensure log directory exists"""
        os.makedirs(LogFileRotation.LOG_DIR, exist_ok=True)

    @staticmethod
    def get_current_file():
        """Get today's log file path"""
        LogFileRotation.ensure_dir()
        date_str = datetime.now().strftime('%Y-%m-%d')
        return os.path.join(LogFileRotation.LOG_DIR, f'freeair2lox_{date_str}.log')

    @staticmethod
    def write_log(log_entry):
        """Write log entry to file"""
        try:
            LogFileRotation.ensure_dir()
            with open(LogFileRotation.get_current_file(), 'a', encoding='utf-8') as f:
                f.write(f"[{log_entry['timestamp']}] {log_entry['level']:8} {log_entry['module']:15} {log_entry['message']}\n")
        except Exception:
            pass  # Silently fail to not break logging chain

    @staticmethod
    def cleanup_old_files():
        """Delete logs older than RETENTION_DAYS"""
        try:
            LogFileRotation.ensure_dir()
            cutoff = datetime.now() - timedelta(days=LogFileRotation.RETENTION_DAYS)
            for filename in os.listdir(LogFileRotation.LOG_DIR):
                if filename.startswith('freeair2lox_') and filename.endswith('.log'):
                    try:
                        file_date_str = filename.replace('freeair2lox_', '').replace('.log', '')
                        file_date = datetime.strptime(file_date_str, '%Y-%m-%d')
                        if file_date < cutoff:
                            os.remove(os.path.join(LogFileRotation.LOG_DIR, filename))
                    except ValueError:
                        pass  # Skip files with unexpected names
        except Exception:
            pass  # Silently fail


# ===== UNKNOWN DEVICES TRACKING =====
# Track unknown FreeAir devices that try to connect
unknown_devices = {}  # {serial_no: {'first_seen': timestamp, 'last_seen': timestamp, 'contact_count': N}}
unknown_devices_lock = threading.Lock()

def register_unknown_device(serial_no: str):
    """Register an unknown FreeAir device"""
    global unknown_devices
    with unknown_devices_lock:
        if serial_no not in unknown_devices:
            unknown_devices[serial_no] = {
                'first_seen': datetime.now().isoformat(),
                'last_seen': datetime.now().isoformat(),
                'contact_count': 1
            }
            logger.info(f"🆕 Unknown device detected: {serial_no}")
        else:
            unknown_devices[serial_no]['last_seen'] = datetime.now().isoformat()
            unknown_devices[serial_no]['contact_count'] += 1

# Initialize log buffer handler
log_buffer_handler = LogBufferHandler(maxlen=500)
log_buffer_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))

logger = logging.getLogger(__name__)
app = Flask(__name__)
app.start_time = time.time()  # Track app startup time for uptime calculation

# Initialize advanced logging infrastructure (v1.3.0)
log_buffer = LogBuffer(max_size=500)
LogFileRotation.ensure_dir()  # Ensure log directory exists on startup

# Configure werkzeug logger to use our filter
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.addFilter(HTTPLogFilter())
werkzeug_logger.setLevel(logging.INFO)

# Disable strict JSON content-type checking to allow Loxone XML to send JSON in requests with any Content-Type
app.config['JSON_SORT_KEYS'] = False

# ===== SESSION CONFIGURATION =====
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'freeair2lox-dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'  # HTTPS only in production
app.config['SESSION_COOKIE_HTTPONLY'] = False  # Allow JavaScript/Fetch to access cookies (required for API authentication)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection; Lax allows same-site form submissions and Fetch with credentials: include
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # 7-day session

config_mgr = None
device_values = {}  # Store device values: {device_id: {temp, humidity, etc}}
device_commands = {}  # Store pending commands: {device_id: {'comfort_level': X, 'operating_mode': Y}}
device_last_mode = {}  # CRITICAL: Remember last known operating_mode per device
data_lock = threading.Lock()  # Thread safety
polling_thread = None
polling_active = False
polling_interval = 60  # seconds
loxone_sender = None  # UDP Sender to Loxone

# ============================================================================
# COMMAND LOCK SYSTEM - Prevents race conditions with Loxone
# ============================================================================
# When a command is sent to FreeAir, we lock UDP sending to Loxone for that device
# until we confirm the command was applied (by checking the next FreeAir payload)
# Structure: {device_name: {'expected_comfort': X, 'expected_mode': Y, 'timestamp': datetime, 'retries': 0}}
command_locks = {}
COMMAND_LOCK_TIMEOUT = 60  # seconds - auto-unlock after this time
COMMAND_MAX_RETRIES = 2    # retry command if not confirmed after first FreeAir response

# Note: Utility functions (to_signed, byte_to_bits, etc.) are now in utils.py
# Note: parse_freeair_data is now in freeair_parser.py
# Note: Loxone XML generators are now in loxone_xml.py

def init_app():
    global config_mgr, polling_thread
    try:
        from config_manager import ConfigManager
        config_mgr = ConfigManager()
        logger.info("ConfigManager initialized")

        # Start polling thread
        polling_thread = threading.Thread(target=poll_devices, daemon=True)
        polling_thread.start()
        logger.info("Polling thread started")
    except Exception as e:
        logger.error(f"ConfigManager error: {e}")
        import traceback
        traceback.print_exc()
        config_mgr = None


# ============================================================================
# COMMAND LOCK FUNCTIONS
# ============================================================================

def set_command_lock(device_name: str, expected_comfort: Optional[int] = None, expected_mode: Optional[int] = None):
    """
    Set a command lock for a device. While locked, UDP sends to Loxone are blocked.
    The lock is released when FreeAir confirms the expected values or timeout occurs.
    """
    global command_locks
    with data_lock:
        command_locks[device_name] = {
            'expected_comfort': expected_comfort,
            'expected_mode': expected_mode,
            'timestamp': datetime.now(),
            'retries': 0,
            'command_sent': False  # Will be True after command is sent to FreeAir
        }
    logger.info(f"🔒 Command Lock SET for {device_name}: expecting comfort={expected_comfort}, mode={expected_mode}")


def check_command_lock(device_name: str, actual_comfort: int, actual_mode: int) -> bool:
    """
    Check if command was confirmed by FreeAir.
    Returns True if lock should be released, False if still waiting.
    """
    global command_locks

    with data_lock:
        if device_name not in command_locks:
            return True  # No lock, allow send

        lock = command_locks[device_name]

        # Check timeout
        elapsed = (datetime.now() - lock['timestamp']).total_seconds()
        if elapsed > COMMAND_LOCK_TIMEOUT:
            logger.warning(f"🔓 Command Lock TIMEOUT for {device_name} after {elapsed:.1f}s")
            del command_locks[device_name]
            return True

        # Command not yet sent to FreeAir (waiting for control poll)
        if not lock['command_sent']:
            logger.debug(f"🔒 Command Lock WAITING for {device_name} - command not yet sent to FreeAir")
            return False

        # Check if values match expected
        expected_comfort = lock['expected_comfort']
        expected_mode = lock['expected_mode']

        comfort_ok = expected_comfort is None or actual_comfort == expected_comfort
        # Mode 0 and 1 both mean "Comfort" - treat as equivalent
        mode_ok = expected_mode is None or actual_mode == expected_mode or (expected_mode == 1 and actual_mode == 0)

        if comfort_ok and mode_ok:
            logger.info(f"🔓 Command Lock RELEASED for {device_name} - values confirmed: comfort={actual_comfort}, mode={actual_mode}")
            del command_locks[device_name]
            return True

        # Values don't match - increment retry counter
        lock['retries'] += 1
        if lock['retries'] > COMMAND_MAX_RETRIES:
            logger.warning(f"🔓 Command Lock RELEASED for {device_name} after {lock['retries']} retries - values still: comfort={actual_comfort}, mode={actual_mode}")
            del command_locks[device_name]
            return True

        logger.info(f"🔒 Command Lock ACTIVE for {device_name} (retry {lock['retries']}/{COMMAND_MAX_RETRIES}) - got comfort={actual_comfort}, mode={actual_mode}, expected comfort={expected_comfort}, mode={expected_mode}")
        return False


def mark_command_sent(device_name: str):
    """Mark that the command has been sent to FreeAir (via control endpoint)"""
    global command_locks
    with data_lock:
        if device_name in command_locks:
            command_locks[device_name]['command_sent'] = True
            logger.debug(f"🔒 Command marked as SENT for {device_name}")


# ============================================================================
# AUTHENTICATION & SESSION MANAGEMENT
# ============================================================================

def require_login(f):
    """Decorator to protect routes that require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow access to /login and /first-setup without authentication
        if request.path in ['/login', '/first-setup'] or request.path.startswith('/static/'):
            return f(*args, **kwargs)

        # Check if user is logged in (has 'user_id' in session)
        if 'user_id' not in session:
            # If API request, return 401
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            # Otherwise redirect to login
            return redirect('/login')

        return f(*args, **kwargs)

    return decorated_function

@app.after_request
def after_request(response):
    """Add CORS headers to expose Content-Disposition for file downloads"""
    # Expose Content-Disposition header so JavaScript can read the filename
    response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition'
    return response

@app.before_request
def before_request():
    """Check authentication and setup status for all requests"""
    # Make session permanent (7 days)
    session.permanent = True

    # Allow access to static files, login, first-setup, and FreeAir device API without auth
    if (request.path.startswith('/static/') or
        request.path in ['/login', '/first-setup', '/api/setup-check', '/api/setup-complete'] or
        request.path.startswith('/apps/data/blucontrol/') or
        (request.path.startswith('/api/devices/') and request.path.endswith(('/loxone-xml', '/loxone-virtual-outputs')))):  # FreeAir device API
        return

    # Validate API Key for Loxone command endpoints (v1.4.0 - Support ANY assigned server)
    if request.path in ['/api/command', '/api/loxone-command']:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            api_key = auth_header[7:]  # Remove 'Bearer ' prefix
            
            # Check against ALL configured Loxone servers
            if config_mgr:
                for server in config_mgr.get_loxone_servers():
                    if api_key == server.api_key:
                        return  # API Key valid for this server, allow request
                
                # Fallback: Check old single-server config for backward compatibility
                if api_key == config_mgr.config.get('loxone', {}).get('api_key'):
                    return  # Old API key still valid
        
        logger.warning(f"Unauthorized command request from {request.remote_addr}")
        return jsonify({'error': 'Invalid or missing API Key'}), 401

    # Check if first setup is still in progress - allow device and loxone API setup without auth
    if config_mgr and config_mgr.is_first_setup():
        if (request.path in ['/api/devices', '/api/loxone'] or
            request.path == '/first-setup' or
            request.path.startswith('/api/devices/') and request.path.endswith(('/loxone-xml', '/loxone-virtual-outputs'))):
            return

    # Check if password is set
    if config_mgr and not config_mgr.is_password_set():
        # Password not set - redirect to first-setup
        if request.path != '/first-setup':
            return redirect('/first-setup')
        return

    # Check if user is authenticated
    if 'user_id' not in session:
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        else:
            return redirect('/login')

# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    if request.method == 'POST':
        password = request.form.get('password', '').strip()

        if not password:
            return render_template('login.html', error='Passwort erforderlich'), 400

        # Verify password
        if config_mgr.verify_admin_password(password):
            session['user_id'] = 'admin'
            logger.info("✅ Admin logged in")
            return redirect('/')
        else:
            logger.warning("❌ Login attempt with wrong password")
            return render_template('login.html', error='Falsches Passwort'), 401

    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@require_login
def logout():
    """Admin logout"""
    session.clear()
    logger.info("✅ Admin logged out")
    return redirect('/login')

@app.route('/api/auth/get-api-key', methods=['GET'])
@require_login
def get_api_key():
    """Get API key for Loxone commands (only for authenticated users)"""
    try:
        if not config_mgr:
            return jsonify({'error': 'Config not available'}), 500
        
        api_key = config_mgr.config.get('loxone', {}).get('api_key', '')
        if not api_key:
            logger.error('API key not found in config')
            return jsonify({'error': 'API key not configured'}), 500
        
        return jsonify({'api_key': api_key}), 200
    except Exception as e:
        logger.error(f'Error retrieving API key: {e}')
        return jsonify({'error': 'Error retrieving API key'}), 500

@app.route('/api/change-password', methods=['POST'])
@require_login
def change_password_api():
    """Change admin password"""
    try:
        data = request.get_json()
        old_password = data.get('old_password', '').strip()
        new_password = data.get('new_password', '').strip()
        confirm_password = data.get('confirm_password', '').strip()

        if not all([old_password, new_password, confirm_password]):
            return jsonify({'error': 'Alle Felder erforderlich'}), 400

        if new_password != confirm_password:
            return jsonify({'error': 'Neue Passwörter stimmen nicht überein'}), 400

        if len(new_password) < 4:
            return jsonify({'error': 'Neues Passwort muss mindestens 4 Zeichen lang sein'}), 400

        if not config_mgr.verify_admin_password(old_password):
            return jsonify({'error': 'Aktuelles Passwort ist falsch'}), 401

        # Change password
        if config_mgr.change_admin_password(old_password, new_password):
            logger.info("✅ Admin password changed")
            return jsonify({'success': True, 'message': 'Passwort erfolgreich geändert'})
        else:
            return jsonify({'error': 'Fehler beim Ändern des Passworts'}), 500

    except Exception as e:
        logger.error(f"Error changing password: {e}")
        return jsonify({'error': 'Interner Fehler'}), 500


def is_device_locked(device_name: str) -> bool:
    """Check if a device has an active command lock"""
    with data_lock:
        if device_name not in command_locks:
            return False

        lock = command_locks[device_name]
        elapsed = (datetime.now() - lock['timestamp']).total_seconds()

        # Auto-cleanup expired locks
        if elapsed > COMMAND_LOCK_TIMEOUT:
            del command_locks[device_name]
            return False

        return True


def send_to_loxone(device_name, values):
    """
    Send device values to Loxone via UDP (v1.4.0 - Multi-Server Support)
    
    Each device can be assigned to multiple Loxone servers.
    This function sends the data to ALL assigned servers.
    """
    try:
        # CHECK COMMAND LOCK - Don't send if waiting for command confirmation
        actual_comfort = values.get('comfort_level')
        actual_mode = values.get('operating_mode')

        if not check_command_lock(device_name, actual_comfort, actual_mode):
            logger.info(f"⏸️ UDP to Loxone BLOCKED for {device_name} - waiting for command confirmation")
            return

        if not config_mgr:
            logger.error("Config manager not available")
            return

        # Get device configuration to check loxone_fields preference and server assignments
        device = None
        for dev in config_mgr.get_devices():
            if dev.name == device_name:
                device = dev
                break

        if not device:
            logger.warning(f"Device {device_name} not found in config")
            return

        # Get all Loxone servers this device is assigned to
        assigned_servers = config_mgr.get_device_servers(device.id)
        if not assigned_servers:
            logger.debug(f"Device {device_name} not assigned to any Loxone servers")
            return

        # All available fields mapping
        all_fields = {
            'device': device_name,
            'timestamp': values.get('timestamp'),
            'is_online': values.get('is_online', False),
            # Temperatures (in °C)
            'outdoor_temp': values.get('outdoor_temp'),
            'supply_temp': values.get('supply_temp'),
            'extract_temp': values.get('extract_temp'),
            'exhaust_temp': values.get('exhaust_temp'),
            'temp_virt_sup_exit': values.get('temp_virt_sup_exit'),
            # Humidity (in %)
            'outdoor_humidity': values.get('outdoor_humidity'),
            'extract_humidity': values.get('extract_humidity'),
            'outdoor_humidity_abs': values.get('outdoor_humidity_abs'),
            'extract_humidity_abs': values.get('extract_humidity_abs'),
            'extract_humidity_indicator': values.get('extract_humidity_indicator'),  # 1=green, 2=yellow, 3=orange, 4=red
            # Air Quality
            'co2': values.get('co2'),  # in ppm
            'co2_indicator': values.get('co2_indicator'),  # 1=green, 2=yellow, 3=orange, 4=red
            'pressure': values.get('pressure'),
            'air_density': values.get('air_density'),  # in kg/m³
            # Fans & Flow (in m³/h for air_flow_ave)
            'supply_fan_rpm': values.get('supply_fan_rpm'),
            'extract_fan_rpm': values.get('extract_fan_rpm'),
            'air_flow': values.get('air_flow'),
            'air_flow_ave': values.get('air_flow_ave'),  # in m³/h
            'fan_speed': values.get('fan_speed'),
            # Control
            'comfort_level': values.get('comfort_level'),
            'operating_mode': values.get('operating_mode'),
            'hum_red_mode': values.get('hum_red_mode'),
            # Filters (Indicators: 1=green, 2=yellow, 3=orange, 4=red)
            'supply_filter_ful': values.get('supply_filter_ful'),
            'extract_filter_ful': values.get('extract_filter_ful'),
            'outdoor_filter_indicator': values.get('outdoor_filter_indicator'),  # Außenluftfilter
            'exhaust_filter_indicator': values.get('exhaust_filter_indicator'),  # Abluftfilter
            # Vents (in %)
            'supply_vent_pos': values.get('supply_vent_pos'),
            'extract_vent_pos': values.get('extract_vent_pos'),
            'bypass_vent_pos': values.get('bypass_vent_pos'),  # in %
            # Recovery (in %)
            'heat_recovery': values.get('heat_recovery'),
            'power_recovery': values.get('power_recovery'),
            # Status
            'filter_hours': values.get('filter_hours'),
            'operating_hours': values.get('operating_hours'),
            'board_version': values.get('board_version'),
            'rssi': values.get('rssi'),
            'error_state': values.get('error_state'),
            'has_errors': values.get('has_errors'),
            'deicing': values.get('deicing'),
            # Units (for Loxone and UI)
            'air_density_unit': 'kg/m³',
            'air_flow_ave_unit': 'm³/h',
            'bypass_vent_pos_unit': '%',
        }

        # Map operating_mode 0 (internal Comfort) to 1 (user Comfort) for Loxone
        if all_fields.get('operating_mode') == 0:
            all_fields['operating_mode'] = 1

        # Filter fields based on device preferences
        if device and device.loxone_fields and len(device.loxone_fields) > 0:
            # Only send selected fields (always include device, timestamp, is_online)
            selected_fields = {'device', 'timestamp', 'is_online'}
            selected_fields.update(device.loxone_fields)
            message_data = {k: v for k, v in all_fields.items() if k in selected_fields}
            logger.debug(f"Filtering fields for {device_name}: sending {len(message_data)} fields")
        else:
            # Send all fields if no preference set
            message_data = all_fields

        # Use ensure_ascii=False to preserve German umlauts (ä, ö, ü) for Loxone
        message = json.dumps(message_data, ensure_ascii=False)

        # Send to ALL assigned Loxone servers (v1.4.0)
        for lox_server in assigned_servers:
            if not lox_server.enabled:
                logger.debug(f"Loxone server {lox_server.id} is disabled, skipping")
                continue

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(message.encode('utf-8'), (lox_server.ip, int(lox_server.port)))
                sock.close()
                logger.info(f"UDP -> Loxone '{lox_server.name}' ({lox_server.ip}:{lox_server.port}): {device_name}")
            except Exception as e:
                logger.error(f"Error sending to Loxone server {lox_server.id}: {e}")

    except Exception as e:
        logger.error(f"Error sending to Loxone: {e}")

def poll_devices():
    """Monitor for device values from FreeAir Bridge"""
    global polling_active, device_values, device_commands, polling_interval
    polling_active = True

    # This thread no longer POLLS devices - devices PUSH data via HTTP
    # Instead, we wait for data to arrive and update the UI
    # The actual FreeAir device communication happens in the HTTP handler below

    while polling_active:
        time.sleep(5)  # Just keep the thread alive for monitoring

@app.route('/apps/data/blucontrol/', methods=['GET', 'POST'])
def freeair_data_handler():
    """FreeAir Device Data Handler - receives encrypted device data"""
    global device_values, device_commands
    try:
        # Extract query parameters
        s_value = request.args.get('s', '')
        b_value = request.args.get('b', '')

        if not s_value or not b_value:
            logger.warning("FreeAir: Missing s or b parameters")
            return "Missing parameters", 400

        # Parse serial number from s parameter (format: XXXy<serial>y<version>)
        try:
            parts = s_value.split('y')
            if len(parts) < 2:
                logger.warning(f"FreeAir: Invalid s parameter format: {s_value}")
                return "Bad Request", 400

            # parts[0] = "ABC123x456..." (contains serial in middle)
            # Extract serial - it's the last part of parts[0] split by 'x'
            serial_parts = parts[0].split('x')
            serial_no = serial_parts[-1] if len(serial_parts) > 1 else serial_parts[0]

            if not serial_no:
                logger.warning(f"FreeAir: Could not parse serial from s={s_value}")
                return "Bad Request", 400
        except Exception as e:
            logger.error(f"FreeAir: Error parsing s parameter: {e}")
            return "Bad Request", 400

        # Find device by serial number in config
        if not config_mgr:
            logger.error("FreeAir: ConfigManager not available")
            return "Server Error", 500

        devices = config_mgr.get_devices()
        device = None
        for dev in devices:
            # Match serial - handle both "35076" and "FA10035076" formats
            if dev.serial_no == serial_no:
                device = dev
                break
            # Try matching: if configured serial is just digits, check if HTTP serial ends with it
            if dev.serial_no.isdigit() and serial_no.endswith(dev.serial_no):
                device = dev
                break
            # Try matching: if HTTP serial is just digits, check if configured serial ends with it
            if serial_no.isdigit() and dev.serial_no.endswith(serial_no):
                device = dev
                break

        if not device:
            logger.warning(f"FreeAir: Unknown device serial {serial_no} (configured: {[d.serial_no for d in devices]})")
            # Register as unknown device for Auto-Discovery
            register_unknown_device(serial_no)
            return "Unknown Device", 400

        # Decrypt payload with device password
        decrypted = decrypt_freeair_payload(b_value, device.password)
        if not decrypted:
            logger.warning(f"FreeAir: Could not decrypt payload for {device.name}")
            return "Decryption Failed", 400

        # Parse binary data
        parsed_data = parse_freeair_data(decrypted)
        if not parsed_data:
            logger.warning(f"FreeAir: Could not parse payload for {device.name}")
            return "Parse Failed", 400

        # Store ALL parsed fields with proper locking
        with data_lock:
            device_values[device.name] = {
                'timestamp': datetime.now().isoformat(),
                'is_online': True,
                **parsed_data  # Include all 45+ fields from parsing
            }
            # CRITICAL: Remember last known operating_mode for this device
            # This is used when sending commands if user doesn't specify mode
            # IMPORTANT: Only store NON-ZERO modes! Mode=0 means "no change" and should be ignored
            # This prevents overwriting last known mode with a transient "no change" value
            if 'operating_mode' in parsed_data and parsed_data['operating_mode'] > 0:
                device_last_mode[device.name] = parsed_data['operating_mode']
                logger.debug(f"✓ Updated last_mode for {device.name}: {parsed_data['operating_mode']}")
        logger.debug(f"FreeAir: Stored {len(parsed_data)} fields for {device.name}")
        logger.info(f"✓ FreeAir Data: Device '{device.name}' ({serial_no}) - Temp:{parsed_data['outdoor_temp']}C CO2:{parsed_data['co2']}ppm")

        # Send updated values to Loxone
        send_to_loxone(device.name, device_values[device.name])

        # DATA endpoint: Always return "OK" (no encryption!)
        # Commands are sent via the separate CONTROL endpoint
        # Per FreeAir protocol: DATA endpoint receives data, CONTROL endpoint sends commands
        return "OK", 200

    except Exception as e:
        logger.error(f"FreeAir handler error: {e}", exc_info=True)
        return "Server Error", 500

@app.route('/apps/data/blucontrol/control/', methods=['GET', 'POST'])
def freeair_control_handler():
    """FreeAir Control Handler - Device polls for commands

    Per FreeAir protocol:
    - Device sends GET request asking "any commands for me?"
    - If command in queue: respond with "heart__beat11{comfort}{mode}\n"
    - If no command: respond with "OK"
    - Response is PLAINTEXT (NOT encrypted!)
    """
    global device_commands
    try:
        # Parse serial from s parameter
        s_value = request.args.get('s', '')

        if not s_value:
            return "OK", 200

        # Extract serial number: Format 1x1x35076y2x14x0
        parts = s_value.split('y')
        serial_parts = parts[0].split('x')
        serial_no = serial_parts[-1] if len(serial_parts) > 1 else serial_parts[0]

        if not serial_no:
            return "OK", 200

        # Find device
        if not config_mgr:
            return "OK", 200

        devices = config_mgr.get_devices()
        device = None
        for dev in devices:
            if dev.serial_no == serial_no:
                device = dev
                break
            # Flexible matching
            if dev.serial_no.isdigit() and serial_no.endswith(dev.serial_no):
                device = dev
                break
            if serial_no.isdigit() and dev.serial_no.endswith(serial_no):
                device = dev
                break

        if not device:
            logger.debug(f"Control: Unknown device {serial_no}")
            # Register as unknown device for Auto-Discovery
            register_unknown_device(serial_no)
            return "OK", 200

        # Update last seen
        device_last_seen = time.time()

        # Check for pending commands in memory (device_commands dict)
        if device.name in device_commands:
            cmd = device_commands[device.name]
            comfort = cmd.get('comfort_level', 2)
            mode = cmd.get('operating_mode', 1)

            # Validate: comfort 1-5, mode 1-4
            if comfort < 1 or comfort > 5:
                comfort = 2
            if mode < 1 or mode > 4:
                mode = 1

            response = f"heart__beat11{comfort}{mode}\n"
            logger.info(f"✓ Sending command to {device.name}: comfort={comfort}, mode={mode}")

            # IMPORTANT: Update last_mode after sending command!
            # This ensures that subsequent commands without explicit mode use the latest sent mode
            device_last_mode[device.name] = mode
            logger.debug(f"✓ Updated last_mode after command: {device.name} = {mode}")

            # MARK COMMAND AS SENT - This allows the lock checker to verify on next FreeAir response
            mark_command_sent(device.name)

            # Delete command after sending (single-use)
            del device_commands[device.name]

            return response, 200

        # Also check file-based command queue
        command_file = '/app/config/pending_command.json'
        if os.path.exists(command_file):
            try:
                with open(command_file, 'r') as f:
                    cmd = json.load(f)

                # IMPORTANT: Only send command if it's for THIS device!
                cmd_device_name = cmd.get('device_name')
                cmd_device_serial = cmd.get('device_serial')

                if cmd_device_name != device.name and cmd_device_serial != device.serial_no:
                    # Command is for a different device, don't send it
                    logger.debug(f"Ignoring command for {cmd_device_name} (current device: {device.name})")
                    return "OK", 200

                comfort = cmd.get('comfort_level', 2)
                mode = cmd.get('operating_mode', 1)

                # Use fallbacks if not specified
                if comfort == 0:
                    comfort = cmd.get('device_fallback_comfort', 2)
                if mode == 0:
                    mode = cmd.get('device_fallback_mode', 1)

                # Validate: comfort 1-5, mode 1-4
                if comfort < 1 or comfort > 5:
                    comfort = 2
                if mode < 1 or mode > 4:
                    mode = 1

                response = f"heart__beat11{comfort}{mode}\n"
                logger.info(f"✓ Sending command from file to {device.name}: comfort={comfort}, mode={mode}")

                # IMPORTANT: Update last_mode after sending command!
                # This ensures that subsequent commands without explicit mode use the latest sent mode
                device_last_mode[device.name] = mode
                logger.debug(f"✓ Updated last_mode after file command: {device.name} = {mode}")

                # MARK COMMAND AS SENT - This allows the lock checker to verify on next FreeAir response
                mark_command_sent(device.name)

                # Delete file after reading (only if it was for this device)
                os.remove(command_file)

                return response, 200

            except Exception as e:
                logger.warning(f"Failed to read command file: {e}")

        # No command pending
        return "OK", 200

    except Exception as e:
        logger.error(f"Control handler error: {e}", exc_info=True)
        return "OK", 200

# ===== AUTO-DISCOVERY ENDPOINTS =====
@app.route('/api/discovery/unknown-devices', methods=['GET'])
def api_unknown_devices():
    """Get list of unknown FreeAir devices trying to connect"""
    try:
        with unknown_devices_lock:
            return jsonify({
                'unknown_devices': unknown_devices,
                'count': len(unknown_devices)
            })
    except Exception as e:
        logger.error(f"Unknown devices error: {e}")
        return jsonify({'error': str(e), 'unknown_devices': {}, 'count': 0}), 500

@app.route('/api/discovery/add', methods=['POST'])
def api_discovery_add():
    """Add unknown device to configuration"""
    try:
        if not config_mgr:
            return jsonify({'success': False, 'error': 'No config'}), 503

        data = json.loads(request.data.decode('utf-8'))

        # Required fields
        name = data.get('name')
        serial_no = data.get('serial_no')
        password = data.get('password')

        if not all([name, serial_no, password]):
            return jsonify({
                'success': False,
                'error': 'Missing: name, serial_no, password'
            }), 400

        from config_manager import FreeAirDevice
        device = FreeAirDevice(
            id=name.lower().replace(' ', '_'),
            name=name,
            serial_no=serial_no,
            password=password,
            enabled=True,
            loxone_fields=[]
        )

        success = config_mgr.add_device(device)
        if success:
            # Remove from unknown list
            with unknown_devices_lock:
                if serial_no in unknown_devices:
                    del unknown_devices[serial_no]

            logger.info(f"✓ Added device from Auto-Discovery: {name}")
            return jsonify({'success': True, 'device_id': device.id, 'message': 'Gerät hinzugefügt'})
        else:
            return jsonify({'success': False, 'error': 'Device ID already exists'}), 400
    except Exception as e:
        logger.error(f"Discovery add error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

# ===== CONFIG BACKUP/RESTORE ENDPOINTS =====

@app.route('/api/config/backup', methods=['GET'])
@require_login
def api_config_backup():
    """Download current config as JSON file"""
    try:
        # Load current config
        config_path = os.getenv('CONFIG_FILE', 'config/FreeAir2Lox_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Create filename: FreeAir2Lox-config_2026-01-28_143025.json
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        filename = f'FreeAir2Lox-config_{timestamp}.json'

        # Serialize with proper formatting
        config_json = json.dumps(config, indent=2, ensure_ascii=False)

        return send_file(
            BytesIO(config_json.encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Backup error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/config/restore', methods=['POST'])
@require_login
def api_config_restore():
    """Restore config from uploaded JSON file"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "Keine Datei bereitgestellt"}), 400

        uploaded_file = request.files['file']

        if not uploaded_file.filename or not uploaded_file.filename.endswith('.json'):
            return jsonify({"error": "Datei muss im JSON-Format sein"}), 400

        # Read & parse JSON
        try:
            file_content = uploaded_file.read().decode('utf-8')
            new_config_data = json.loads(file_content)
        except json.JSONDecodeError as e:
            return jsonify({"error": f"Ungültiges JSON-Format: {str(e)}"}), 400

        # Minimal validation
        if 'devices' not in new_config_data:
            return jsonify({"error": "Konfiguration fehlt 'devices' Sektion"}), 400

        if not isinstance(new_config_data['devices'], list):
            return jsonify({"error": "'devices' muss eine Liste sein"}), 400

        # Save config
        config_path = os.getenv('CONFIG_FILE', 'config/FreeAir2Lox_config.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(new_config_data, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ Config restored from {uploaded_file.filename}")

        return jsonify({
            "status": "restored",
            "message": "Konfiguration erfolgreich wiederhergestellt",
            "file": uploaded_file.filename
        }), 200

    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return jsonify({"error": f"Restore fehlgeschlagen: {str(e)}"}), 500

@app.route('/first-setup')
def first_setup():
    """First setup page for new installations"""
    try:
        # Absolute path for Docker compatibility
        template_path = os.path.join(os.path.dirname(__file__), 'templates', 'first-setup.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError as e:
        logger.error(f"First setup template not found: {e}")
        return "First setup template not found", 404

@app.route('/api/setup-check', methods=['POST', 'GET'])
def setup_check():
    """Check if first setup is needed, or set admin password"""
    global config_mgr

    # POST: Set admin password during first setup
    if request.method == 'POST':
        try:
            data = request.get_json()
            password = data.get('password', '').strip()
            confirm = data.get('confirm_password', '').strip()

            if not password or not confirm:
                return jsonify({'error': 'Alle Felder erforderlich'}), 400

            if password != confirm:
                return jsonify({'error': 'Passwörter stimmen nicht überein'}), 400

            if len(password) < 4:
                return jsonify({'error': 'Passwort muss mindestens 4 Zeichen lang sein'}), 400

            # Set password
            if config_mgr.set_admin_password(password):
                logger.info("✅ Admin password set during setup")
                return jsonify({'status': 'success'})
            else:
                return jsonify({'error': 'Fehler beim Speichern des Passworts'}), 500
        except Exception as e:
            logger.error(f"Error setting admin password: {e}")
            return jsonify({'error': str(e)}), 500

    # GET: Check if first setup is needed
    try:
        is_first_setup = config_mgr.is_first_setup()
        return jsonify({
            "is_first_setup": is_first_setup,
            "devices_count": len(config_mgr.get_devices()),
            "loxone_ip": config_mgr.get_loxone_config().ip
        })
    except Exception as e:
        logger.error(f"Error checking setup status: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/setup-complete', methods=['POST'])
def setup_complete():
    """Mark setup as complete"""
    global config_mgr
    try:
        config_mgr.mark_setup_complete()
        logger.info("First setup marked as complete")
        return jsonify({"status": "complete"})
    except Exception as e:
        logger.error(f"Error marking setup complete: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/')
@require_login
def index():
    """Main dashboard - redirect to first-setup if needed"""
    global config_mgr
    try:
        # Check if first setup is needed
        if config_mgr.is_first_setup():
            return redirect('/first-setup')
    except Exception as e:
        logger.error(f"Error checking setup status: {e}")

    # Render the new Loxone-style dashboard
    return render_template('index.html')


# Note: Loxone XML functions (generate_loxone_xml, get_bridge_ip, generate_loxone_command_template)
# are imported from loxone_xml.py module


@app.route('/api/loxone/command-template', methods=['POST'])
def api_loxone_command_template():
    """
    Generate and download Loxone VirtualOut command template
    Expected POST data: {
        "device_name": "Musik",
        "device_id": "musik"
    }
    """
    try:
        # Parse request data directly - works with any Content-Type
        data = {}
        if request.data:
            try:
                data = json.loads(request.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                data = {}

        device_name = data.get('device_name', 'FreeAir Bridge')
        device_id = data.get('device_id', device_name.lower())

        logger.info(f"Command template request: device={device_name}, id={device_id}")

        # Get Bridge IP
        bridge_ip = get_bridge_ip()

        # Generate template
        template_content = generate_loxone_command_template(device_name, device_id, bridge_ip)

        if not template_content:
            return jsonify({'error': 'Template generation failed'}), 500

        # Return as downloadable XML file
        filename = f"FreeAir2Lox_Commands_{device_name.replace(' ', '_')}.xml"
        logger.info(f"Returning command template: {filename}")
        return send_file(
            BytesIO(template_content.encode('utf-8')),
            mimetype='application/xml',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Command template error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ============================================================================
# LOXONE SERVER MANAGEMENT ENDPOINTS (v1.4.0 - Multi-Server Support)
# ============================================================================

@app.route('/api/loxone/servers', methods=['GET'])
@require_login
def get_loxone_servers_api():
    """List all configured Loxone servers"""
    try:
        servers = config_mgr.get_loxone_servers()
        return jsonify([s.to_dict() for s in servers]), 200
    except Exception as e:
        logger.error(f"Error retrieving servers: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/loxone/servers', methods=['POST'])
@require_login
def add_loxone_server_api():
    """Add new Loxone server"""
    try:
        from config_manager import LoxoneServer
        data = request.get_json()
        
        if not data.get('id') or not data.get('name') or not data.get('ip'):
            return jsonify({'error': 'Missing required fields: id, name, ip'}), 400
        
        server = LoxoneServer(
            id=data.get('id'),
            name=data.get('name'),
            ip=data.get('ip'),
            port=data.get('port', 5555),
            enabled=data.get('enabled', True),
            api_key=data.get('api_key', str(uuid.uuid4()))
        )
        
        if config_mgr.add_loxone_server(server):
            return jsonify({'status': 'added', 'server': server.to_dict()}), 201
        else:
            return jsonify({'error': 'Server ID already exists'}), 400
    except Exception as e:
        logger.error(f"Error adding server: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/loxone/servers/<server_id>', methods=['GET'])
@require_login
def get_loxone_server_api(server_id):
    """Get specific Loxone server"""
    try:
        server = config_mgr.get_loxone_server(server_id)
        if server:
            return jsonify(server.to_dict()), 200
        return jsonify({'error': 'Server not found'}), 404
    except Exception as e:
        logger.error(f"Error retrieving server {server_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/loxone/servers/<server_id>', methods=['PUT'])
@require_login
def update_loxone_server_api(server_id):
    """Update existing Loxone server"""
    try:
        from config_manager import LoxoneServer
        data = request.get_json()
        
        server = LoxoneServer(
            id=server_id,
            name=data.get('name'),
            ip=data.get('ip'),
            port=data.get('port', 5555),
            enabled=data.get('enabled', True),
            api_key=data.get('api_key', '')
        )
        
        if config_mgr.update_loxone_server(server_id, server):
            return jsonify({'status': 'updated', 'server': server.to_dict()}), 200
        else:
            return jsonify({'error': 'Server not found'}), 404
    except Exception as e:
        logger.error(f"Error updating server {server_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/loxone/servers/<server_id>', methods=['DELETE'])
@require_login
def delete_loxone_server_api(server_id):
    """Delete Loxone server"""
    try:
        if config_mgr.delete_loxone_server(server_id):
            return jsonify({'status': 'deleted'}), 200
        else:
            return jsonify({'error': 'Server not found or cannot delete'}), 404
    except Exception as e:
        logger.error(f"Error deleting server {server_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/loxone/servers/<server_id>/test', methods=['POST'])
@require_login
def test_loxone_server_api(server_id):
    """Test connection to Loxone server by sending test UDP packet"""
    try:
        server = config_mgr.get_loxone_server(server_id)
        if not server:
            return jsonify({'error': 'Server not found'}), 404
        
        try:
            # Send test UDP packet
            test_payload = json.dumps({'test': True, 'timestamp': datetime.now().isoformat()}, ensure_ascii=False)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            sock.sendto(test_payload.encode('utf-8'), (server.ip, int(server.port)))
            sock.close()
            logger.info(f"Test packet sent to {server.name} ({server.ip}:{server.port})")
            return jsonify({'status': 'sent', 'message': f'Test packet sent to {server.ip}:{server.port}'}), 200
        except Exception as e:
            logger.error(f"Failed to send test packet to {server_id}: {e}")
            return jsonify({'status': 'failed', 'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Error testing server {server_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/loxone/servers/<server_id>/regenerate-key', methods=['POST'])
@require_login
def regenerate_server_key_api(server_id):
    """Regenerate API key for Loxone server"""
    try:
        from config_manager import LoxoneServer
        server = config_mgr.get_loxone_server(server_id)
        if not server:
            return jsonify({'error': 'Server not found'}), 404
        
        # Generate new API key
        server.api_key = str(uuid.uuid4())
        if config_mgr.update_loxone_server(server_id, server):
            logger.warning(f"Regenerated API key for server {server_id}")
            return jsonify({'status': 'regenerated', 'api_key': server.api_key}), 200
        else:
            return jsonify({'error': 'Failed to update server'}), 500
    except Exception as e:
        logger.error(f"Error regenerating key for server {server_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/loxone/config', methods=['POST'])
def api_loxone_config():
    """
    Generate and download Loxone XML configuration
    Expected POST data: {
        "device_name": "Wohnzimmer",
        "selected_fields": ["outdoor_temp", "supply_temp", "co2", ...]
    }
    """
    try:
        # Parse request data directly - works with any Content-Type
        data = {}
        if request.data:
            try:
                data = json.loads(request.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                data = {}

        device_name = data.get('device_name', 'FreeAir Bridge')
        selected_fields = data.get('selected_fields', [])

        logger.info(f"Loxone XML request: device={device_name}, fields={len(selected_fields)}")

        if not selected_fields or len(selected_fields) == 0:
            return jsonify({'error': 'No fields selected'}), 400

        # Get Loxone configuration from config
        loxone_config = config_mgr.get_loxone_config()
        loxone_port = loxone_config.port if loxone_config else 5555

        # Get Bridge IP dynamically through multiple methods
        bridge_ip = get_bridge_ip()
        logger.info(f"Using Loxone port: {loxone_port}, Bridge IP: {bridge_ip}")

        # Generate XML with configured port and Bridge IP
        xml_content = generate_loxone_xml(device_name, selected_fields, port=loxone_port, loxone_ip=bridge_ip)

        if not xml_content:
            return jsonify({'error': 'XML generation failed'}), 500

        # Return as downloadable file
        filename = f"FreeAir_Loxone_{device_name.replace(' ', '_')}.xml"
        logger.info(f"Returning XML file: {filename}")
        return send_file(
            BytesIO(xml_content.encode('utf-8')),
            mimetype='application/xml',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Loxone config error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# API Routes

@app.route('/api/status')
def api_status():
    try:
        dev_count = 0
        dev_enabled = 0
        lox_enabled = False
        if config_mgr:
            devices = config_mgr.get_devices()
            dev_count = len(devices)
            # Count only devices that have RSSI values (actually online), not just enabled
            dev_enabled = len([d for d in devices if d.enabled and device_values.get(d.name, {}).get('rssi') is not None])
        return jsonify({
            'devices_count': dev_count,
            'devices_enabled': dev_enabled,
            'loxone_enabled': lox_enabled
        })
    except Exception as e:
        logger.error(f"Status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/devices')
def api_devices():
    try:
        devices = []
        if config_mgr:
            for dev in config_mgr.get_devices():
                # Get last measurement data for this device
                last_data = device_values.get(dev.name, {})
                rssi = last_data.get('rssi', None)

                devices.append({
                    'id': dev.id,
                    'name': dev.name,
                    'serial_no': dev.serial_no,
                    'password': dev.password,
                    'enabled': dev.enabled,
                    'loxone_fields': dev.loxone_fields,
                    'rssi': rssi,
                    'last_data': last_data
                })
        return jsonify(devices)
    except Exception as e:
        logger.error(f"Devices error: {e}")
        return jsonify([])

@app.route('/api/devices', methods=['POST'])
def api_add_device():
    try:
        if not config_mgr:
            return jsonify({'success': False, 'error': 'No config'}), 503
        data = json.loads(request.data.decode('utf-8'))
        if not data.get('name') or not data.get('serial_no') or not data.get('password'):
            return jsonify({'success': False, 'error': 'Missing fields'}), 400
        from config_manager import FreeAirDevice
        device = FreeAirDevice(
            id=data.get('name'),
            name=data.get('name'),
            serial_no=data.get('serial_no'),
            password=data.get('password'),
            enabled=data.get('enabled', True)
        )
        config_mgr.add_device(device)
        config_mgr.save_config()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Add device error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/devices/<device_id>', methods=['PUT'])
def api_update_device(device_id):
    try:
        if not config_mgr:
            return jsonify({'success': False, 'error': 'No config'}), 503
        data = json.loads(request.data.decode('utf-8'))
        devices = config_mgr.config.get('devices', [])
        for dev in devices:
            if dev.get('name') == device_id or dev.get('id') == device_id:
                dev['name'] = data.get('name', dev['name'])
                dev['serial_no'] = data.get('serial_no', dev['serial_no'])
                dev['password'] = data.get('password', dev['password'])
                dev['enabled'] = data.get('enabled', dev.get('enabled', True))
                # Support loxone_servers array (v1.4.0)
                if 'loxone_servers' in data:
                    dev['loxone_servers'] = data.get('loxone_servers', [])
                config_mgr.save_config()
                return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Not found'}), 404
    except Exception as e:
        logger.error(f"Update error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/devices/<device_id>/loxone-fields', methods=['PUT'])
def api_update_loxone_fields(device_id):
    try:
        if not config_mgr:
            return jsonify({'success': False, 'error': 'No config'}), 503
        data = json.loads(request.data.decode('utf-8'))
        logger.info(f"Update Loxone fields for device {device_id}: {data.get('loxone_fields', [])}")
        devices = config_mgr.config.get('devices', [])
        for dev in devices:
            if dev.get('name') == device_id or dev.get('id') == device_id:
                dev['loxone_fields'] = data.get('loxone_fields', [])
                logger.info(f"Saved Loxone fields for {dev.get('name')}: {dev['loxone_fields']}")
                config_mgr.save_config()
                return jsonify({'success': True})
        logger.warning(f"Device {device_id} not found. Available: {[d.get('id') + '/' + d.get('name') for d in devices]}")
        return jsonify({'success': False, 'error': 'Not found'}), 404
    except Exception as e:
        logger.error(f"Loxone fields update error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/devices/<device_id>/loxone-xml')
def api_get_loxone_xml(device_id):
    """Generate and return Loxone XML for a device (v1.4.0: per-server support)"""
    try:
        if not config_mgr:
            return jsonify({'error': 'No config'}), 503

        devices = config_mgr.config.get('devices', [])
        device = None
        for dev in devices:
            if dev.get('name') == device_id or dev.get('id') == device_id:
                device = dev
                break

        if not device:
            logger.error(f"[XML] Device '{device_id}' not found. Available: {[d.get('name') for d in devices]}")
            return jsonify({'error': 'Device not found'}), 404

        # Get server_id from query params (v1.4.0)
        server_id = request.args.get('server_id', None)
        
        # Get bridge IP and port
        bridge_ip = get_bridge_ip()
        port = 5555
        
        # If server_id provided, use server-specific settings
        if server_id:
            try:
                server = config_mgr.get_loxone_server(server_id)
                if server:
                    bridge_ip = server.ip
                    port = server.port
            except Exception as e:
                logger.warning(f"[XML] Could not look up server {server_id}: {e}, using default settings")

        # Generate XML
        selected_fields = device.get('loxone_fields', [])
        xml_content = generate_loxone_xml(
            device.get('name'),
            selected_fields,
            port=port,
            bridge_ip=bridge_ip,
            server_id=server_id,
            config_mgr=config_mgr
        )

        if not xml_content:
            return jsonify({'error': 'Failed to generate XML'}), 400

        device_name = device.get('name', 'device')
        logger.info(f"[XML] Generating Inputs XML for device '{device_name}' (server_id={server_id})")
        xml_bytes = BytesIO(xml_content.encode('utf-8'))
        return send_file(
            xml_bytes,
            mimetype='application/xml',
            as_attachment=True,
            download_name=f"FreeAir2Lox_{device_name.replace(' ', '_')}-Inputs.xml"
        )
    except Exception as e:
        logger.error(f"Loxone XML error: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/devices/<device_id>/loxone-virtual-outputs')
def api_get_loxone_virtual_outputs(device_id):
    """Generate and return Loxone VirtualOut XML for a device (v1.4.0: per-server support)"""
    try:
        if not config_mgr:
            return jsonify({'error': 'No config'}), 503

        devices = config_mgr.config.get('devices', [])
        device = None
        for dev in devices:
            if dev.get('name') == device_id or dev.get('id') == device_id:
                device = dev
                break

        if not device:
            logger.error(f"[XML] Device '{device_id}' not found. Available: {[d.get('name') for d in devices]}")
            return jsonify({'error': 'Device not found'}), 404

        # Get server_id from query params (v1.4.0)
        server_id = request.args.get('server_id', None)
        
        # Get bridge IP and API Key
        bridge_ip = get_bridge_ip()
        api_key = config_mgr.config.get('loxone', {}).get('api_key', '')
        
        # If server_id provided, use server-specific settings
        if server_id:
            try:
                server = config_mgr.get_loxone_server(server_id)
                if server:
                    bridge_ip = server.ip
                    api_key = server.api_key
            except Exception as e:
                logger.warning(f"[XML] Could not look up server {server_id}: {e}, using default settings")

        # Generate VirtualOut XML
        from loxone_xml import generate_loxone_command_template
        xml_content = generate_loxone_command_template(
            device.get('name'),
            device.get('id'),
            bridge_ip=bridge_ip,
            bridge_port=80,
            api_key=api_key,
            server_id=server_id,
            config_mgr=config_mgr
        )

        if not xml_content:
            return jsonify({'error': 'Failed to generate VirtualOut XML'}), 400

        # Return as XML file download
        xml_bytes = BytesIO(xml_content.encode('utf-8'))
        device_name = device.get('name', 'device')
        logger.info(f"[XML] Generating Outputs XML for device '{device_name}' (server_id={server_id})")
        return send_file(
            xml_bytes,
            mimetype='application/xml',
            as_attachment=True,
            download_name=f"FreeAir2Lox_{device_name.replace(' ', '_')}-Outputs.xml"
        )
    except Exception as e:
        logger.error(f"VirtualOut XML error: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/api/devices/<device_id>', methods=['DELETE'])
def api_delete_device(device_id):
    try:
        if not config_mgr:
            return jsonify({'success': False, 'error': 'No config'}), 503
        devices = config_mgr.config.get('devices', [])
        for i, dev in enumerate(devices):
            if dev.get('name') == device_id or dev.get('id') == device_id:
                devices.pop(i)
                config_mgr.save_config()
                return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Not found'}), 404
    except Exception as e:
        logger.error(f"Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/device-values/<device_id>')
def api_get_device_values(device_id):
    try:
        if device_id in device_values:
            return jsonify(device_values[device_id])
        return jsonify({'is_online': False, 'error': 'No data'})
    except Exception as e:
        logger.error(f"Device values error: {e}")
        return jsonify({'is_online': False})

@app.route('/api/device-control', methods=['POST'])
def api_device_control():
    """Store pending control command for device"""
    global device_commands
    try:
        # Parse request data directly - works with any Content-Type
        data = {}
        if request.data:
            try:
                data = json.loads(request.data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                data = {}

        device_id = data.get('device_id')
        comfort_level = data.get('comfort_level')
        operating_mode = data.get('operating_mode')

        if not device_id:
            return jsonify({'success': False, 'error': 'device_id missing'})

        # Store the command to be sent on next poll
        device_commands[device_id] = {
            'comfort_level': int(comfort_level) if comfort_level else 0,
            'operating_mode': int(operating_mode) if operating_mode else 0
        }

        logger.info(f"Stored control command for device {device_id}: {device_commands[device_id]}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error storing device control: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/polling-interval', methods=['POST'])
def api_set_polling_interval():
    global polling_interval
    try:
        data = json.loads(request.data.decode('utf-8'))
        interval = int(data.get('interval', 60))

        # Validate: min 60 seconds, max 3600 seconds (60 minutes)
        if interval < 60:
            interval = 60
        elif interval > 3600:
            interval = 3600

        polling_interval = interval
        logger.info(f"Polling interval changed to {interval} seconds")
        return jsonify({'success': True, 'interval': interval})
    except Exception as e:
        logger.error(f"Polling interval error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/command', methods=['POST'])
@app.route('/api/loxone-command', methods=['POST'])
def api_loxone_command():
    """Queue command for FreeAir device from Loxone VirtualOut.

    Accepts Loxone VirtualOut format with ANY Content-Type:
    {
        "device_id": "Musik",
        "command": "set_comfort_level" or "set_operating_mode",
        "value": "3"
    }

    This endpoint is Loxone-specific and ignores Content-Type header.
    """
    global device_commands, device_values, device_last_mode

    try:
        # DEBUG: Print raw request for troubleshooting (visible in stdout)
        import sys
        print(f"\n=== LOXONE COMMAND DEBUG ===", file=sys.stderr)
        print(f"Raw body: {request.data}", file=sys.stderr)
        print(f"Content-Type: {request.headers.get('Content-Type', 'none')}", file=sys.stderr)
        print(f"All headers: {dict(request.headers)}", file=sys.stderr)

        # Parse request data directly - works with ANY Content-Type
        data = {}
        if request.data:
            try:
                data = json.loads(request.data.decode('utf-8'))
                print(f"Parsed JSON: {data}", file=sys.stderr)
                print(f"  device_id={data.get('device_id')}, command={data.get('command')}, value={data.get('value')}", file=sys.stderr)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                print(f"JSON parse error: {e}", file=sys.stderr)
                data = {}

        # ===== Detect input format =====
        is_loxone_format = 'device_id' in data and 'command' in data

        # Extract parameters based on format
        if is_loxone_format:
            # Loxone format: convert to Web UI format
            serial = data.get('device_id', '')
            command = data.get('command', '')
            value = data.get('value', '')

            # Parse command to extract comfort/mode
            comfort = None
            mode = None
            if command == 'set_comfort_level':
                try:
                    comfort = int(value)
                except (ValueError, TypeError):
                    return jsonify({'error': f'Invalid comfort level value: {value}'}), 400
            elif command == 'set_operating_mode':
                try:
                    mode = int(value)
                except (ValueError, TypeError):
                    return jsonify({'error': f'Invalid operating mode value: {value}'}), 400
            else:
                return jsonify({'error': f'Unknown command: {command}'}), 400
        else:
            # Web UI format
            serial = data.get('serial') or data.get('serialNo')
            comfort = data.get('comfortLevel') or data.get('comfort_level')
            mode = data.get('operatingMode') or data.get('operating_mode')

            # Convert to int (None if not provided)
            try:
                comfort = int(comfort) if comfort is not None and comfort != '' else None
                mode = int(mode) if mode is not None and mode != '' else None
            except (ValueError, TypeError):
                return jsonify({'error': 'comfortLevel and operatingMode must be numbers'}), 400

        # At least one value must be provided
        if comfort is None and mode is None:
            return jsonify({'error': 'At least one of comfortLevel or operatingMode must be provided'}), 400

        # Find device by serial OR by name/id
        device_name = None
        device_serial = None
        if config_mgr:
            devices = config_mgr.get_devices()
            if serial:
                # First try to find by name/id (UI sends device ID as "serial")
                for dev in devices:
                    if dev.name == serial or dev.id == serial:
                        device_name = dev.name
                        device_serial = dev.serial_no
                        break
                # If not found by name, try by serial number
                if not device_name:
                    for dev in devices:
                        if dev.serial_no == serial:
                            device_name = dev.name
                            device_serial = dev.serial_no
                            break
            elif devices:
                # Use first device
                device_name = devices[0].name
                device_serial = devices[0].serial_no

        if not device_name:
            return jsonify({'error': 'Device not found'}), 404

        # Get current device state to fill missing values
        current_data = device_values.get(device_name, {})
        current_comfort = current_data.get('comfort_level', 2)  # Default 2 if unknown
        current_mode = device_last_mode.get(device_name, 1)  # Use last known mode, default 1

        # IMPORTANT: Check for existing pending command and merge!
        # If a command is already queued, use its values as defaults for missing parameters
        pending_cmd = device_commands.get(device_name, {})
        if pending_cmd:
            # If user didn't specify comfort, use pending comfort
            if comfort is None:
                comfort = pending_cmd.get('comfort_level', current_comfort)
            # If user didn't specify mode, use pending mode (NOT device_last_mode!)
            if mode is None:
                mode = pending_cmd.get('operating_mode', current_mode)

        # Fill missing values from device state (only if no pending command)
        final_comfort = comfort if comfort is not None else current_comfort
        final_mode = mode if mode is not None else current_mode

        # Validate comfort (1-5)
        if final_comfort < 1 or final_comfort > 5:
            final_comfort = max(1, min(5, final_comfort))
            logger.warning(f"Comfort level adjusted to valid range: {final_comfort}")

        # Validate mode (1-4, NEVER 0!)
        if final_mode < 1 or final_mode > 4:
            final_mode = 1  # Default to Comfort mode
            logger.warning(f"Operating mode adjusted to valid range: {final_mode}")

        # Queue command (in-memory)
        device_commands[device_name] = {
            'comfort_level': final_comfort,
            'operating_mode': final_mode
        }

        # SET COMMAND LOCK - Block UDP to Loxone until FreeAir confirms
        set_command_lock(device_name, expected_comfort=final_comfort, expected_mode=final_mode)

        # Also save to file for persistence (include device name!)
        command_file = '/app/config/pending_command.json'
        try:
            os.makedirs('/app/config', exist_ok=True)
            with open(command_file, 'w') as f:
                json.dump({
                    'timestamp': time.time(),
                    'device_name': device_name,
                    'device_serial': device_serial,
                    'comfort_level': final_comfort,
                    'operating_mode': final_mode
                }, f)
        except Exception as e:
            logger.warning(f"Could not save command to file: {e}")

        logger.info(f"✓ Command queued for {device_name}: comfort={final_comfort}, mode={final_mode}")

        return jsonify({
            'status': 'queued',
            'serial': device_serial,
            'comfortLevel': final_comfort,
            'operatingMode': final_mode
        })

    except Exception as e:
        logger.error(f"Command API error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/get-pending-command', methods=['GET'])
def api_get_pending_command():
    """Get pending command for freeair_bridge (internal API)

    This endpoint is called by freeair_bridge.py to get the next command
    to send to the FreeAir device. After reading, the command file is DELETED.
    This solves race conditions by allowing freeair_bridge to fetch the command
    only when it's ready to send it.
    """
    try:
        command_file = '/app/config/pending_command.json'

        if os.path.exists(command_file):
            try:
                with open(command_file, 'r') as f:
                    command_data = json.load(f)

                # Delete the file IMMEDIATELY after reading
                os.remove(command_file)
                logger.debug(f"🔄 Bridge fetched command: C={command_data.get('comfort_level')}, M={command_data.get('operating_mode')}")

                return jsonify({
                    'success': True,
                    'command': command_data
                }), 200
            except Exception as e:
                logger.error(f"Error reading/deleting command file: {e}")
                return jsonify({'success': False, 'command': None}), 200
        else:
            # No pending command
            return jsonify({'success': False, 'command': None}), 200

    except Exception as e:
        logger.error(f"Error in get_pending_command: {e}", exc_info=True)
        return jsonify({'success': False, 'command': None}), 200

@app.route('/api/loxone')
def api_get_loxone():
    try:
        if not config_mgr:
            return jsonify({})
        lox = config_mgr.config.get('loxone', {})
        return jsonify({
            'ip': lox.get('ip', ''),
            'port': lox.get('port', 5555),
            'enabled': lox.get('enabled', False)
        })
    except Exception as e:
        logger.error(f"Loxone error: {e}")
        return jsonify({})

@app.route('/api/loxone', methods=['POST'])
def api_save_loxone():
    try:
        if not config_mgr:
            return jsonify({'success': False, 'error': 'No config'}), 503
        data = json.loads(request.data.decode('utf-8'))
        config_mgr.config['loxone'] = {
            'ip': data.get('ip', ''),
            'port': int(data.get('port', 5555)),
            'enabled': data.get('enabled', False)
        }
        config_mgr.save_config()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Save loxone error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 400

# ===== ADVANCED LOGGING API ENDPOINTS (v1.3.0) =====

@app.route('/api/logs', methods=['GET'])
def api_get_logs():
    """Fetch logs with filtering and pagination

    Query Parameters:
    - level: Comma-separated log levels (INFO,WARNING,ERROR,DEBUG)
    - search: Text search in message
    - device: Filter by device serial or name
    - limit: Max entries (default: 100, max: 1000)
    - offset: For pagination (default: 0)
    - time_range: '1h', '24h', '7d' (default: '24h')
    """
    try:
        # Get filters from query params
        level_filter = request.args.get('level', '').split(',') if request.args.get('level') else []
        search_text = request.args.get('search', '').lower()
        device_filter = request.args.get('device', '')
        limit = min(int(request.args.get('limit', 100)), 1000)
        offset = int(request.args.get('offset', 0))

        # Get all logs from buffer
        all_logs = log_buffer.get_all()

        # Apply filters
        filtered = all_logs
        if level_filter and level_filter[0]:  # Only filter if level_filter has content
            filtered = [l for l in filtered if l['level'] in level_filter]
        if search_text:
            filtered = [l for l in filtered if search_text in l['message'].lower()
                       or search_text in l.get('module', '').lower()]
        if device_filter:
            filtered = [l for l in filtered if l.get('context', {}).get('device') == device_filter]

        # Pagination
        total = len(filtered)
        paginated = filtered[offset:offset+limit]

        return jsonify({
            'success': True,
            'total': total,
            'count': len(paginated),
            'offset': offset,
            'logs': paginated
        }), 200

    except Exception as e:
        logger.error(f"Error getting logs: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/stream', methods=['GET'])
def api_logs_stream():
    """Server-Sent Events (SSE) for real-time log streaming

    Returns: Stream of log entries as JSON objects
    """
    try:
        # Read request args BEFORE creating generator (inside request context)
        last_id = int(request.args.get('last_id', 0))

        def generate_stream(last_id_val):
            """Generator for SSE stream"""
            last_id = last_id_val

            while True:
                try:
                    all_logs = log_buffer.get_all()
                    # Only send new logs
                    for log in all_logs:
                        try:
                            log_num = int(log['id'].split('_')[1])
                        except (ValueError, IndexError):
                            continue

                        if log_num > last_id:
                            yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
                            last_id = log_num

                    time.sleep(0.5)  # Check every 500ms
                except Exception as e:
                    logger.error(f"Error in SSE stream: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    break

        return Response(generate_stream(last_id), mimetype='text/event-stream'), 200

    except Exception as e:
        logger.error(f"Error in logs stream: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs/stats', methods=['GET'])
def api_logs_stats():
    """Get logging statistics

    Returns: Error count, warning count, avg response time, uptime, etc.
    """
    try:
        all_logs = log_buffer.get_all()
        errors = [l for l in all_logs if l['level'] == 'ERROR']
        warnings = [l for l in all_logs if l['level'] == 'WARNING']

        # Calculate avg response time from context
        response_times = [l.get('context', {}).get('response_time_ms', 0)
                         for l in all_logs if 'response_time_ms' in l.get('context', {})]
        avg_time = sum(response_times) / len(response_times) if response_times else 0

        # Calculate disk usage
        disk_usage_mb = 0
        try:
            log_dir = '/app/logs'
            if os.path.exists(log_dir):
                disk_usage_mb = sum(
                    os.path.getsize(os.path.join(log_dir, f))
                    for f in os.listdir(log_dir) if os.path.isfile(os.path.join(log_dir, f))
                ) / (1024 * 1024)
        except Exception as e:
            logger.debug(f"Error calculating disk usage: {e}")

        return jsonify({
            'total_logs': len(all_logs),
            'errors_24h': len(errors),
            'warnings_24h': len(warnings),
            'avg_response_time_ms': round(avg_time, 2),
            'uptime_seconds': int(time.time() - app.start_time) if hasattr(app, 'start_time') else 0,
            'disk_usage_mb': round(disk_usage_mb, 2),
            'retention_days': 7
        }), 200

    except Exception as e:
        logger.error(f"Error getting log stats: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs/export', methods=['POST'])
def api_logs_export():
    """Export logs as file (CSV, JSON, or TXT)

    POST body:
    {
        "level": "INFO,ERROR",
        "time_range": "7d",
        "format": "csv|json|txt"
    }
    """
    try:
        data = request.get_json() if request.is_json else {}
        level_filter = data.get('level', '').split(',') if data.get('level') else []
        format_type = data.get('format', 'txt').lower()  # txt, csv, json

        if format_type not in ['txt', 'csv', 'json']:
            return jsonify({'error': f'Invalid format: {format_type}'}), 400

        all_logs = log_buffer.get_all()
        if level_filter and level_filter[0]:
            all_logs = [l for l in all_logs if l['level'] in level_filter]

        # Generate file content
        if format_type == 'json':
            content = json.dumps(all_logs, indent=2, ensure_ascii=False)
            mime = 'application/json'
            ext = 'json'
        elif format_type == 'csv':
            import csv
            from io import StringIO
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['Timestamp', 'Level', 'Module', 'Message', 'Context'])
            for log in all_logs:
                writer.writerow([
                    log['timestamp'],
                    log['level'],
                    log.get('module', ''),
                    log['message'],
                    json.dumps(log.get('context', {}), ensure_ascii=False)
                ])
            content = output.getvalue()
            mime = 'text/csv'
            ext = 'csv'
        else:  # txt
            lines = [
                f"[{log['timestamp']}] {log['level']:8} {log.get('module', 'unknown'):15} {log['message']}"
                for log in all_logs
            ]
            content = '\n'.join(lines)
            mime = 'text/plain'
            ext = 'txt'

        filename = f"freeair2lox-logs_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.{ext}"

        return send_file(
            BytesIO(content.encode('utf-8')),
            mimetype=mime,
            as_attachment=True,
            download_name=filename
        ), 200

    except Exception as e:
        logger.error(f"Error exporting logs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/logs/clear', methods=['POST'])
def api_clear_logs():
    """Clear in-memory log buffer (does NOT delete log files)"""
    try:
        log_buffer.clear()
        logger.info("Log buffer cleared by user")
        return jsonify({'success': True}), 200

    except Exception as e:
        logger.error(f"Error clearing logs: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Read environment variables for logging configuration
    log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Set timezone (tzset is available on Unix-like systems in time module)
    tz_str = os.getenv('TZ', 'UTC')
    try:
        os.environ['TZ'] = tz_str
        # Note: tzset() only available on Unix-like systems
        if hasattr(time, 'tzset'):
            time.tzset()
        logger_msg = f"Timezone set to {tz_str}"
    except Exception as e:
        logger_msg = f"Could not set timezone {tz_str}: {e}"

    # Configure logging with timestamp in configured timezone
    logging.basicConfig(
        level=log_level,
        format='[%(asctime)s] [%(levelname)s] %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Add our custom log buffer handler to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(log_buffer_handler)

    # Log startup information
    logger = logging.getLogger(__name__)
    logger.info(f"[STARTUP] LOG_LEVEL={log_level_str}, {logger_msg}")
    logger.info(f"[STARTUP] PUID={os.getenv('PUID', 'N/A')}, PGID={os.getenv('PGID', 'N/A')}, UMASK={os.getenv('UMASK', 'N/A')}")

    # DO NOT suppress werkzeug logs during debugging
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.DEBUG)  # Changed from WARNING to DEBUG

    init_app()

    # Flask runs on port 80 internally (inside container)
    # docker-compose maps:
    # - Port 80:80 for FreeAir device data (internal HTTP)
    # - Port 8080:80 for Web-UI access (external)
    ui_port = int(os.getenv('HTTP_PORT', 80))
    logger.info(f"Starting Flask on port {ui_port}")
    app.run(host='0.0.0.0', port=ui_port, debug=False)
