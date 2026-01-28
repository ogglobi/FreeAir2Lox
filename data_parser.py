"""
FreeAir 100 Protocol Data Parser
Parses binary sensor data and control requests from FreeAir devices
"""

import struct
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# Operating Modes
OPERATING_MODES = {
    0: "Comfort (Internal)",
    1: "Comfort",
    2: "Sleep",
    3: "Turbo",
    4: "Turbo Cool",
    5: "Service",
    6: "Test",
    7: "Manufacturer",
    8: "Dehumidification",
}

# Comfort Programs
PROGRAMS = {
    0: "Minimum ventilation",
    1: "Dehumidification (rel)",
    2: "Dehumidification (abs)",
    3: "Active cooling",
    4: "CO2 reduction",
    5: "Water input",
    6: "Outside air < -22°C",
    7: "Humidity entry",
}


def parse_freeair_payload(payload: bytes) -> Optional[Dict]:
    """
    Parse FreeAir 100 binary payload (decrypted).
    
    Parses approximately 49 bytes of binary sensor data containing:
    - Temperatures (outdoor, supply, extract, exhaust)
    - Humidity (absolute, relative)
    - Air quality (CO2, pressure)
    - Air flow (current, average)
    - Fan speeds and valve positions
    - Operating state (mode, program, comfort level)
    - Maintenance info (filter hours, errors)
    
    Args:
        payload (bytes): Decrypted FreeAir payload
        
    Returns:
        dict: Parsed data with all fields, or None if parsing fails
    """
    if not payload or len(payload) < 49:
        logger.warning(f"Payload too short: {len(payload)} bytes")
        return None
    
    try:
        # Unpack binary data (big-endian)
        # This is a 1:1 port from ioBroker.freeair DataParser
        (
            outdoor_temp_raw,           # 0: i8
            outdoor_hum,                # 1: u8
            outdoor_hum_abs_raw,        # 2: u8
            extract_temp_raw,           # 3: i8
            extract_hum,                # 4: u8
            extract_hum_abs_raw,        # 5: u8
            exhaust_temp_raw,           # 6: i8
            supply_temp_raw,            # 7: i8
            temp_virt_sup_exit_raw,     # 8: i8
            co2_hi,                     # 9: u8
            co2_lo,                     # 10: u8
            pressure_hi,                # 11: u8
            pressure_lo,                # 12: u8
            air_density_raw,            # 13: u8
            air_flow_hi,                # 14: u8
            air_flow_lo,                # 15: u8
            air_flow_ave_hi,            # 16: u8
            air_flow_ave_lo,            # 17: u8
            fan_speed,                  # 18: u8
            supply_fan_rpm_hi,          # 19: u8
            supply_fan_rpm_lo,          # 20: u8
            extract_fan_rpm_hi,         # 21: u8
            extract_fan_rpm_lo,         # 22: u8
            supply_vent_pos,            # 23: u8
            extract_vent_pos,           # 24: u8
            bypass_vent_pos,            # 25: u8
            bath_vent_pos,              # 26: u8
            comfort_level,              # 27: u8 (bit 0-2)
            operating_mode,             # 28: u8 (bit 3-5)
            program,                    # 29: u8 (bit 6-7 + 0-1)
            operating_hours_hi,         # 30: u8
            operating_hours_mid,        # 31: u8
            operating_hours_lo,         # 32: u8
            filter_hours_hi,            # 33: u8
            filter_hours_mid,           # 34: u8
            filter_hours_lo,            # 35: u8
            supply_filter_full,         # 36: u8
            extract_filter_full,        # 37: u8
            has_errors,                 # 38: u8
            error_state,                # 39: u8
            deicing,                    # 40: u8
            sum_cooling,                # 41: u8
            room_area_hi,               # 42: u8
            room_area_lo,               # 43: u8
            second_room_flow_hi,        # 44: u8
            second_room_flow_lo,        # 45: u8
            rssi_raw,                   # 46: i8 (signed for dBm)
            board_version,              # 47: u8
            version,                    # 48: u8
        ) = struct.unpack('>49B', payload[:49])
        
        # Extract bit fields
        comfort_level = comfort_level & 0x07  # Bits 0-2
        operating_mode = (operating_mode >> 3) & 0x07  # Bits 3-5
        program = ((program & 0x03) << 1) | ((program >> 6) & 0x01)  # Bits 6-7 + 0-1
        
        # Reconstruct multi-byte values
        co2 = (co2_hi << 8) | co2_lo
        pressure = (pressure_hi << 8) | pressure_lo
        air_flow = (air_flow_hi << 8) | air_flow_lo
        air_flow_ave = (air_flow_ave_hi << 8) | air_flow_ave_lo
        supply_fan_rpm = (supply_fan_rpm_hi << 8) | supply_fan_rpm_lo
        extract_fan_rpm = (extract_fan_rpm_hi << 8) | extract_fan_rpm_lo
        operating_hours = (operating_hours_hi << 16) | (operating_hours_mid << 8) | operating_hours_lo
        filter_hours = (filter_hours_hi << 16) | (filter_hours_mid << 8) | filter_hours_lo
        room_area = (room_area_hi << 8) | room_area_lo
        second_room_flow = (second_room_flow_hi << 8) | second_room_flow_lo
        
        # Float conversions (1 decimal place = divide by 10)
        outdoor_temp = outdoor_temp_raw / 10.0
        extract_temp = extract_temp_raw / 10.0
        exhaust_temp = exhaust_temp_raw / 10.0
        supply_temp = supply_temp_raw / 10.0
        temp_virt_sup_exit = temp_virt_sup_exit_raw / 10.0
        outdoor_hum_abs = outdoor_hum_abs_raw / 10.0
        extract_hum_abs = extract_hum_abs_raw / 10.0
        air_density = air_density_raw / 100.0
        
        # dBm (signed, keep as is)
        rssi = rssi_raw
        
        return {
            "outdoor_temp": outdoor_temp,
            "outdoor_hum": outdoor_hum,
            "outdoor_hum_abs": outdoor_hum_abs,
            "extract_temp": extract_temp,
            "extract_hum": extract_hum,
            "extract_hum_abs": extract_hum_abs,
            "exhaust_temp": exhaust_temp,
            "supply_temp": supply_temp,
            "temp_virt_sup_exit": temp_virt_sup_exit,
            "co2": co2,
            "pressure": pressure,
            "air_density": air_density,
            "air_flow": air_flow,
            "air_flow_ave": air_flow_ave,
            "fan_speed": fan_speed,
            "supply_fan_rpm": supply_fan_rpm,
            "extract_fan_rpm": extract_fan_rpm,
            "supply_vent_pos": supply_vent_pos,
            "extract_vent_pos": extract_vent_pos,
            "bypass_vent_pos": bypass_vent_pos,
            "bath_vent_pos": bath_vent_pos,
            "comfort_level": comfort_level,
            "operating_mode": operating_mode,
            "operating_mode_name": OPERATING_MODES.get(operating_mode, f"Unknown ({operating_mode})"),
            "program": program,
            "program_name": PROGRAMS.get(program, f"Unknown ({program})"),
            "operating_hours": operating_hours,
            "filter_hours": filter_hours,
            "supply_filter_full": bool(supply_filter_full),
            "extract_filter_full": bool(extract_filter_full),
            "has_errors": bool(has_errors),
            "error_state": error_state,
            "deicing": bool(deicing),
            "sum_cooling": bool(sum_cooling),
            "room_area": room_area,
            "second_room_flow": second_room_flow,
            "rssi": rssi,
            "board_version": board_version,
            "version": version,
        }
        
    except struct.error as e:
        logger.error(f"Parse failed: {e}", exc_info=True)
        return None


def format_command_response(comfort_level: int, operating_mode: int) -> str:
    """
    Format FreeAir command response.
    
    CRITICAL: Always send Mode=1 for Comfort (not Mode=0)
    See: Dokumentation - "Das Gerät kann Mode 0 oder 1 für 'Comfort' melden. Beim Senden wird immer 1 verwendet."
    
    Args:
        comfort_level (int): 1-5
        operating_mode (int): 1-4 (0 is invalid for sending)
        
    Returns:
        str: Command string, e.g., "heart__beat1151\n"
    """
    # CRITICAL FIX: Validate mode
    if operating_mode == 0:
        logger.warning(f"Mode=0 detected in format_command_response! Using safe default Mode=1")
        operating_mode = 1
    
    # Validate ranges
    if comfort_level < 1 or comfort_level > 5:
        comfort_level = max(1, min(5, comfort_level))
    if operating_mode < 1 or operating_mode > 4:
        operating_mode = max(1, min(4, operating_mode))
    
    return f"heart__beat11{comfort_level}{operating_mode}\n"
