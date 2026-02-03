"""
FreeAir Bridge - Loxone XML Generator Module
Generates XML configurations for Loxone integration.
"""

import logging
import os
import socket
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Field definitions for Loxone XML generation
LOXONE_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    'timestamp': {'type': 'string', 'label': 'Zeitstempel', 'unit': ''},
    'device': {'type': 'string', 'label': 'Gerät', 'unit': ''},
    'outdoor_temp': {'type': 'analog', 'label': 'Außentemperatur', 'min': -20, 'max': 60, 'unit': '&lt;v.1&gt; °C', 'decimals': 1},
    'supply_temp': {'type': 'analog', 'label': 'Zulufttemperatur', 'min': -20, 'max': 60, 'unit': '&lt;v.1&gt; °C', 'decimals': 1},
    'extract_temp': {'type': 'analog', 'label': 'Ablufttemperatur', 'min': -20, 'max': 60, 'unit': '&lt;v.1&gt; °C', 'decimals': 1},
    'exhaust_temp': {'type': 'analog', 'label': 'Fortlufttemperatur', 'min': -20, 'max': 60, 'unit': '&lt;v.1&gt; °C', 'decimals': 1},
    'virtual_supply_exit_temp': {'type': 'analog', 'label': 'Virtuelle Zuluftaustritt', 'min': -20, 'max': 60, 'unit': '&lt;v.1&gt; °C', 'decimals': 1},
    'outdoor_humidity': {'type': 'analog', 'label': 'Außenfeuchte', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'extract_humidity': {'type': 'analog', 'label': 'Abluftfeuchte', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'absolute_humidity_outdoor': {'type': 'analog', 'label': 'Absolute Außenfeuchte', 'min': 0, 'max': 30, 'unit': '&lt;v.2&gt; g/m³', 'decimals': 2},
    'absolute_humidity_extract': {'type': 'analog', 'label': 'Absolute Abluftfeuchte', 'min': 0, 'max': 30, 'unit': '&lt;v.2&gt; g/m³', 'decimals': 2},
    'co2': {'type': 'analog', 'label': 'CO2', 'min': 0, 'max': 5000, 'unit': '&lt;v&gt; ppm'},
    'co2_indicator': {'type': 'analog', 'label': 'CO2 Indikator', 'min': 1, 'max': 4, 'unit': '&lt;v&gt;'},
    'pressure': {'type': 'analog', 'label': 'Luftdruck', 'min': 900, 'max': 1050, 'unit': '&lt;v&gt; hPa'},
    'air_density': {'type': 'analog', 'label': 'Luftdichte', 'min': 0.8, 'max': 1.3, 'unit': '&lt;v.3&gt; kg/m³', 'decimals': 3},
    'comfort_level': {'type': 'analog', 'label': 'Komfortstufe', 'min': 1, 'max': 5, 'unit': '&lt;v&gt;'},
    'operating_mode': {'type': 'analog', 'label': 'Betriebsmodus', 'min': 0, 'max': 8, 'unit': '&lt;v&gt;'},
    'dehumidification_level': {'type': 'analog', 'label': 'Entfeuchtungsstufe', 'min': 0, 'max': 3, 'unit': '&lt;v&gt;'},
    'supply_fan_rpm': {'type': 'analog', 'label': 'Zuluftlüfter RPM', 'min': 0, 'max': 3000, 'unit': '&lt;v&gt; rpm'},
    'extract_fan_rpm': {'type': 'analog', 'label': 'Abluftlüfter RPM', 'min': 0, 'max': 3000, 'unit': '&lt;v&gt; rpm'},
    'air_flow_average': {'type': 'analog', 'label': 'Luftdurchsatz Durchschnitt', 'min': 0, 'max': 500, 'unit': '&lt;v&gt; m³/h'},
    'air_flow': {'type': 'analog', 'label': 'Luftdurchsatz', 'min': 0, 'max': 500, 'unit': '&lt;v&gt; m³/h'},
    'outdoor_filter_pollution': {'type': 'analog', 'label': 'Außenluftfilter Verschmutzung', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'exhaust_filter_pollution': {'type': 'analog', 'label': 'Fortluftfilter Verschmutzung', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'outdoor_filter_indicator': {'type': 'analog', 'label': 'Außenluftfilter Ampel', 'min': 1, 'max': 4, 'unit': '&lt;v&gt;'},
    'exhaust_filter_indicator': {'type': 'analog', 'label': 'Fortluftfilter Ampel', 'min': 1, 'max': 4, 'unit': '&lt;v&gt;'},
    'extract_humidity_indicator': {'type': 'analog', 'label': 'Feuchte Indikator', 'min': 1, 'max': 4, 'unit': '&lt;v&gt;'},
    'supply_vent_position': {'type': 'analog', 'label': 'Zuluft Position', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'extract_vent_position': {'type': 'analog', 'label': 'Abluft Position', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'bypass_vent_position': {'type': 'analog', 'label': 'Bypass Position', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'heat_recovery': {'type': 'analog', 'label': 'Wärmerückgewinnung', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'power_recovery': {'type': 'analog', 'label': 'Kraftrückgewinnung', 'min': 0, 'max': 100, 'unit': '&lt;v&gt; %'},
    'filter_hours': {'type': 'analog', 'label': 'Filterstunden', 'min': 0, 'max': 10000, 'unit': '&lt;v&gt;'},
    'operating_hours': {'type': 'analog', 'label': 'Betriebsstunden', 'min': 0, 'max': 100000, 'unit': '&lt;v&gt;'},
    'wifi_rssi': {'type': 'analog', 'label': 'WLAN Signalstärke', 'min': -100, 'max': 0, 'unit': '&lt;v&gt; dBm'},
    'error_status': {'type': 'analog', 'label': 'Fehlerstatus', 'min': 0, 'max': 255, 'unit': '&lt;v&gt;'},
    'error_present': {'type': 'digital', 'label': 'Fehler vorhanden', 'unit': ''},
    'deicing_mode': {'type': 'digital', 'label': 'Enteisungsmodus', 'unit': ''},
    'board_version': {'type': 'string', 'label': 'Board Version', 'unit': ''},
}


def generate_loxone_xml(
    device_name: str,
    selected_fields: List[str],
    port: int = 5555,
    bridge_ip: str = "192.168.10.122",
    device_data: Optional[Dict] = None,
    server_id: Optional[str] = None,
    config_mgr = None
) -> Optional[str]:
    """
    Generate Loxone-compatible XML for Virtual UDP Inputs (v1.4.0 - Per-Server Support).

    Args:
        device_name: Name of the device
        selected_fields: List of field keys to include
        port: Loxone Miniserver UDP port
        bridge_ip: FreeAir2Lox Bridge IP address (source of UDP data)
        device_data: Optional device data for future extensions
        server_id: Optional specific Loxone server ID (v1.4.0)
        config_mgr: Optional ConfigManager instance for server lookup (v1.4.0)

    Returns:
        XML string for Loxone configuration, or None on error
    """
    try:
        # If server_id and config_mgr provided, use server-specific port
        if server_id and config_mgr:
            try:
                server = config_mgr.get_loxone_server(server_id)
                if server:
                    port = server.port
                    logger.info(f"Using server-specific port: {port} for server {server_id}")
            except Exception as e:
                logger.warning(f"Could not get server {server_id}: {e}")
        
        xml_lines = ['<?xml version="1.0" encoding="utf-8"?>']
        xml_lines.append(f'<VirtualInUdp Title="FreeAir2Lox-{device_name}" Address="{bridge_ip}" Port="{port}">')

        for field_key in selected_fields:
            if field_key in LOXONE_FIELD_DEFINITIONS:
                field_def = LOXONE_FIELD_DEFINITIONS[field_key]
                check_str = f'&quot;device&quot;: &quot;{device_name}&quot;\\i&quot;{field_key}&quot;: \\i\\v'
                title = field_def['label']
                unit = field_def.get('unit', '')

                if field_def['type'] == 'analog':
                    min_val = str(field_def.get('min', 0))
                    max_val = str(field_def.get('max', 100))
                    line = (
                        f'\t<VirtualInUdpCmd Title="{title}" Check="{check_str}" '
                        f'Signed="false" Analog="true" SourceValLow="0" DestValLow="0" '
                        f'SourceValHigh="0" DestValHigh="0" DefVal="0" '
                        f'MinVal="{min_val}" MaxVal="{max_val}" Unit="{unit}" HintText=""/>'
                    )
                else:
                    line = f'\t<VirtualInUdpCmd Title="{title}" Check="{check_str}" Analog="false" HintText=""/>'
                xml_lines.append(line)

        xml_lines.append('</VirtualInUdp>')
        return '\n'.join(xml_lines)

    except Exception as e:
        logger.error(f"XML generation error: {e}")
        return None


def generate_loxone_command_template(
    device_name: str,
    device_id: str,
    bridge_ip: str = "192.168.10.122",
    bridge_port: int = 80,
    api_key: str = "",
    server_id: Optional[str] = None,
    config_mgr = None
) -> str:
    """
    Generate Loxone VirtualOut XML configuration for sending commands to the Bridge.

    Args:
        device_name: Human readable device name (e.g., "Musik")
        device_id: Device identifier (e.g., "musik")
        bridge_ip: Bridge IP address
        bridge_port: Bridge HTTP port
        api_key: API Key for Bearer token authentication (fallback if server_id not provided)
        server_id: Loxone server ID for per-server API key lookup (v1.4.0)
        config_mgr: ConfigManager instance for server lookup (v1.4.0)

    Returns:
        XML string for Loxone VirtualOut configuration
    """
    # Use server-specific API key if server_id provided
    final_api_key = api_key
    if server_id and config_mgr:
        try:
            server = config_mgr.get_loxone_server(server_id)
            if server:
                final_api_key = server.api_key
        except Exception as e:
            logger.warning(f"Could not look up server {server_id}: {e}, using provided api_key")

    address = f"http://{bridge_ip}:{bridge_port}"
    api_path = "/api/command"

    # Build JSON POST bodies with Loxone <v> variable for value
    # CRITICAL: <v> must be UNQUOTED (no quotes) for numeric Analog values
    # It will be escaped to &lt;v&gt; in the XML output
    comfort_post = '{"device_id": "' + device_id + '", "command": "set_comfort_level", "value": <v>}'
    operating_mode_post = '{"device_id": "' + device_id + '", "command": "set_operating_mode", "value": <v>}'

    # XML-escape: quotes to &quot;, < to &lt;, > to &gt;
    comfort_post_xml = comfort_post.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
    operating_mode_post_xml = operating_mode_post.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

    # Build HTTP Header with API Key authentication
    # CRITICAL: HTTP headers must use \r\n (CRLF) not just \n (LF)
    http_header = f"Authorization: Bearer {final_api_key}\r\nContent-Type: application/json"

    xml_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<VirtualOut Title="FreeAir2Lox-{device_name}" Address="{address}" CmdInit="" HintText="" CloseAfterSend="true" CmdSep="">',
        '\t<Info templateType="3" minVersion="16011106"/>',
        f'\t<VirtualOutCmd Title="Komfortstufe (1-5)" Comment="FreeAir Comfort Level" CmdOnMethod="POST" CmdOn="{api_path}" CmdOnHTTP="{http_header}" CmdOnPost="{comfort_post_xml}" Analog="true" Repeat="0" RepeatRate="0" HintText="Komfort Level 1-5"/>',
        f'\t<VirtualOutCmd Title="Betriebsmodus" Comment="FreeAir Operating Mode" CmdOnMethod="POST" CmdOn="{api_path}" CmdOnHTTP="{http_header}" CmdOnPost="{operating_mode_post_xml}" Analog="true" Repeat="0" RepeatRate="0" HintText="Operating Mode"/>',
        '</VirtualOut>'
    ]

    return '\n'.join(xml_lines)


def get_bridge_ip(config_mgr=None) -> str:
    """
    Get the Bridge IP address through multiple methods.

    Priority:
    1. HTTP request context (request.host) - most reliable
    2. Environment variable BRIDGE_IP
    3. Outbound socket detection
    4. Config file fallback

    Args:
        config_mgr: Optional ConfigManager instance for fallback

    Returns:
        Bridge IP address string
    """
    # Method 1: From HTTP request context (most reliable)
    try:
        from flask import request
        host = request.host  # e.g., "192.168.10.122:80" or "192.168.10.122"
        ip = host.split(':')[0]  # Remove port if present

        # Skip localhost/127.0.0.1 (Docker container context) and try next method
        if ip not in ('localhost', '127.0.0.1'):
            logger.info(f"Got Bridge IP from HTTP request: {ip}")
            return ip
        else:
            logger.debug("HTTP request returned localhost/127.0.0.1, trying next method")
    except Exception as e:
        logger.debug(f"HTTP request method failed: {e}")

    # Method 2: Environment variable
    env_bridge_ip = os.getenv('BRIDGE_IP')
    if env_bridge_ip:
        logger.info(f"Got Bridge IP from environment variable: {env_bridge_ip}")
        return env_bridge_ip

    # Method 3: Socket detection
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        logger.info(f"Got Bridge IP from socket connection: {ip}")
        return ip
    except Exception as e:
        logger.debug(f"Socket method failed: {e}")

    # Method 4: Default fallback
    fallback_ip = '192.168.10.122'
    logger.warning(f"Could not detect Bridge IP, using hardcoded fallback: {fallback_ip}")
    return fallback_ip
