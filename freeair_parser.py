"""
FreeAir Bridge - Data Parser Module
Parses binary sensor data from FreeAir 100 devices.
Complete port from ioBroker.freeair DataParser.
"""

import logging
from typing import Dict, Optional, Any, List

from utils import (
    to_signed, byte_to_bits, divide_byte, get_number_fr_bits,
    low_plus_high, get_pressure, get_abs_hum, get_air_density,
    get_indicator_level, filter_supply_status, filter_extract_status,
    get_heat_recovery, get_power_recovery
)

logger = logging.getLogger(__name__)


def parse_freeair_data(payload: bytes) -> Optional[Dict[str, Any]]:
    """
    Parse decrypted FreeAir payload (48 bytes).
    Complete port from ioBroker GitHub src/lib/dataParser.ts lines 65-455.
    
    Args:
        payload: Decrypted FreeAir binary payload (minimum 48 bytes)
        
    Returns:
        Dictionary with all parsed sensor values, or None if parsing fails
    """
    try:
        if len(payload) < 48:
            logger.warning(f"Payload too short: {len(payload)} bytes")
            return None
        
        data = payload
        
        # Hex dump for debugging
        hex_dump = ' '.join(f'{b:02x}' for b in data[:48])
        logger.debug(f"PAYLOAD HEX: {hex_dump}")
        
        # Bit mappings from Working Tool (data_parser.py)
        bit_mappings = {
            23: ["uErrorFileNr", "uDeicing"],
            24: ["uErrorState", "uDefrostExhaust"],
            25: ["uVentPosSupply", "uCtrlSetSupVent"],
            26: ["uVentPosExtract", "uCtrlSetExtVent"],
            27: ["uVentPosBath", "uCtrlSet2ndVent"],
            28: ["uVentPosBypass", "uCtrlSetBypVent"],
            29: ["uTempSupplyHigh", "uComfortLevel"],
            30: ["uTempExtractHigh", "uState"],
            31: ["uTempExhaustHigh", "uControlAuto"],
            32: ["uTempOutdoorHigh", "uDummy1"],
            33: ["uTempVirtSupExitHigh", "uDummy2"],
            34: ["uPressure4LSB", "uCFAHigh", "uFilterSupplyFul", "uFilterExtractFul"],
            35: ["uAirFlowAve", "u2ndRoomOnly20", "uFanLim2ndRoom"],
            36: ["uFanExtractRPMHigh", "uCO2High", "uDIPSwitchHigh"],
            37: ["uFanSupplyRPMHigh", "uHumRedMode", "uSumCooling"],
            38: ["uFanSpeed", "uFSCHigh", "uFECHigh", "uCSUHigh"],
            39: ["uPressure5MSB", "uErrorLineNrSuperHigh"],
            40: ["uOperatingHoursSuperHigh", "uFilterHoursSuperHigh", "uErrorCodeHigh"],
        }
        
        # Divisions for bit extraction
        divisions = {
            23: [6, 1],
            24: [5, 2],
            25: [5, 2],
            26: [5, 2],
            27: [5, 2],
            28: [5, 2],
            29: [4, 3],
            30: [4, 3],
            31: [4, 3],
            32: [4, 3],
            33: [4, 3],
            34: [4, 1, 1, 1],
            35: [5, 1, 1],
            36: [5, 1, 1],
            37: [5, 1, 1],
            38: [4, 1, 1, 1],
            39: [5, 1, 1],
            40: [4, 2, 1],
        }
        
        # Collect values from bit-mapped bytes
        values: Dict[str, Any] = {}
        for idx_str, div in divisions.items():
            idx = int(idx_str)
            parts = divide_byte(div, data[idx])
            fields = bit_mappings[idx]
            for f, i in zip(fields, range(len(fields))):
                if i < len(parts):
                    values[f] = parts[i]
        
        # Direct byte values
        values['uTempSupplyLow'] = data[2]
        values['uTempOutdoorLow'] = data[3]
        values['uTempExhaustLow'] = data[4]
        values['uTempExtractLow'] = data[5]
        values['uTempVirtSupExitLow'] = data[6]
        values['uFanExtractRPMLow'] = data[7]
        values['uDIPSwitchLow'] = data[8]
        values['uFanSupplyRPMLow'] = data[9]
        values['uErrorLineNrHigh'] = data[10]
        values['uErrorLineNrLow'] = data[11]
        values['uErrorCodeLow'] = data[12]
        values['uCO2Low'] = data[13]
        values['uOperatingHoursLow'] = data[14]
        values['uOperatingHoursHigh'] = data[15]
        values['uFilterHoursLow'] = data[16]
        values['uFilterHoursHigh'] = data[17]
        values['uFSCLow'] = data[18]
        values['uFECLow'] = data[19]
        values['uCSULow'] = data[20]
        values['uCFALow'] = data[21]
        values['uRSSILow'] = data[47]
        
        # Set defaults for potentially missing keys
        default_keys = [
            'uTempSupplyHigh', 'uTempOutdoorHigh', 'uTempExhaustHigh', 'uTempExtractHigh',
            'uTempVirtSupExitHigh', 'uComfortLevel', 'uState', 'uControlAuto',
            'uPressure4LSB', 'uCFAHigh', 'uFilterSupplyFul', 'uFilterExtractFul',
            'uAirFlowAve', 'u2ndRoomOnly20', 'uFanLim2ndRoom',
            'uFanExtractRPMHigh', 'uCO2High', 'uDIPSwitchHigh',
            'uFanSupplyRPMHigh', 'uHumRedMode', 'uSumCooling',
            'uFanSpeed', 'uFSCHigh', 'uFECHigh', 'uCSUHigh',
            'uPressure5MSB', 'uErrorLineNrSuperHigh',
            'uOperatingHoursSuperHigh', 'uFilterHoursSuperHigh', 'uErrorCodeHigh',
            'uVentPosSupply', 'uVentPosExtract', 'uVentPosBath', 'uVentPosBypass',
            'uDeicing', 'uDefrostExhaust', 'uErrorState', 'uErrorFileNr'
        ]
        for key in default_keys:
            if key not in values:
                values[key] = []
        
        # Parse humidity (direct bytes)
        outdoor_hum = data[0]
        extract_hum = data[1]
        
        # Parse temperatures (11-bit signed, scaled 1/8)
        i_temp_supply = low_plus_high(values['uTempSupplyLow'], values['uTempSupplyHigh'])
        supply_temp = to_signed(i_temp_supply, 11) / 8.0
        
        i_temp_outdoor = low_plus_high(values['uTempOutdoorLow'], values['uTempOutdoorHigh'])
        outdoor_temp = to_signed(i_temp_outdoor, 11) / 8.0
        
        i_temp_exhaust = low_plus_high(values['uTempExhaustLow'], values['uTempExhaustHigh'])
        exhaust_temp = to_signed(i_temp_exhaust, 11) / 8.0
        
        i_temp_extract = low_plus_high(values['uTempExtractLow'], values['uTempExtractHigh'])
        extract_temp_val = to_signed(i_temp_extract, 11) / 8.0
        
        i_temp_virt_sup_exit = low_plus_high(values['uTempVirtSupExitLow'], values['uTempVirtSupExitHigh'])
        temp_virt_sup_exit = to_signed(i_temp_virt_sup_exit, 11) / 8.0
        
        # CO2
        co2 = low_plus_high(values['uCO2Low'], values['uCO2High']) * 16
        
        # Pressure
        pressure = get_pressure(values['uPressure5MSB'], values['uPressure4LSB'])
        
        # Comfort level
        comfort_level = get_number_fr_bits(values['uComfortLevel'])
        if comfort_level is not None:
            comfort_level += 1
        
        # Operating mode / state
        state = get_number_fr_bits(values['uState'])
        
        # Fan RPM
        supply_fan_rpm = low_plus_high(values['uFanSupplyRPMLow'], values['uFanSupplyRPMHigh'])
        extract_fan_rpm = low_plus_high(values['uFanExtractRPMLow'], values['uFanExtractRPMHigh'])
        
        # Air flow
        air_flow_ave = get_number_fr_bits(values['uAirFlowAve'])
        
        # Filter status
        supply_filter_ful = get_number_fr_bits(values['uFilterSupplyFul'])
        extract_filter_ful = get_number_fr_bits(values['uFilterExtractFul'])
        
        # Vent positions
        extract_vent_pos = get_number_fr_bits(values['uVentPosExtract'])
        supply_vent_pos = get_number_fr_bits(values['uVentPosSupply'])
        bypass_vent_pos = get_number_fr_bits(values['uVentPosBypass'])
        
        # Other values
        control_auto = get_number_fr_bits(values['uControlAuto'])
        dip_switch = low_plus_high(values['uDIPSwitchLow'], values['uDIPSwitchHigh'])
        exhaust_defrost = get_number_fr_bits(values['uDefrostExhaust'])
        
        # Operating hours
        operating_hours = low_plus_high(
            values['uOperatingHoursLow'], 
            values['uOperatingHoursHigh'], 
            values['uOperatingHoursSuperHigh']
        )
        
        # Board version
        board_version = data[22]
        
        # Deicing
        deicing = get_number_fr_bits(values['uDeicing'])
        
        # FSC / FEC / CSU / CFA
        fsc = low_plus_high(values['uFSCLow'], values['uFSCHigh'])
        fec = low_plus_high(values['uFECLow'], values['uFECHigh'])
        csu = low_plus_high(values['uCSULow'], values['uCSUHigh'])
        cfa = low_plus_high(values['uCFALow'], values['uCFAHigh'])
        
        # Filter hours
        filter_hours = low_plus_high(
            values['uFilterHoursLow'], 
            values['uFilterHoursHigh'], 
            values['uFilterHoursSuperHigh']
        )
        
        # Other flags
        hum_red_mode = get_number_fr_bits(values['uHumRedMode'])
        fan_speed = get_number_fr_bits(values['uFanSpeed'])
        sum_cooling = get_number_fr_bits(values['uSumCooling'])
        error_state = get_number_fr_bits(values['uErrorState'])
        
        # Calculated values
        outdoor_hum_abs = get_abs_hum(outdoor_hum, outdoor_temp)
        extract_hum_abs = get_abs_hum(extract_hum, extract_temp_val)
        air_density = get_air_density(pressure, extract_temp_val)
        
        # Air flow (derived from fan speed)
        air_flow = fan_speed * 10 if fan_speed is not None and fan_speed > 2 else air_flow_ave
        
        # Humidity indicator
        extract_humidity_indicator = get_indicator_level(extract_hum, [
            {'min': 30, 'max': 60, 'level': 1},
            {'min': 20, 'max': 70, 'level': 2},
            {'min': 10, 'max': 85, 'level': 3},
            {'min': -float('inf'), 'max': float('inf'), 'level': 4}
        ])
        
        # CO2 indicator
        co2_indicator = get_indicator_level(co2, [
            {'max': 1000, 'level': 1},
            {'max': 1700, 'level': 2},
            {'max': 2500, 'level': 3},
            {'max': float('inf'), 'level': 4}
        ])
        
        # Filter indicators
        outdoor_filter_indicator = filter_supply_status(supply_fan_rpm, fan_speed)
        exhaust_filter_indicator = filter_extract_status(extract_fan_rpm, fan_speed)
        
        # Recovery efficiency
        heat_recovery = get_heat_recovery(extract_temp_val, outdoor_temp, supply_temp, air_flow)
        power_recovery = get_power_recovery(extract_temp_val, outdoor_temp, supply_temp, air_flow)
        
        # Error status
        has_errors = error_state not in [0, "0", 22, "22", None]
        
        # Deicing status
        is_deicing = deicing == 1 or exhaust_defrost == 1 or exhaust_defrost == 2
        
        logger.info(
            f"Parsed: TAU={outdoor_temp:.1f}C, TZU={supply_temp:.1f}C, "
            f"TAB={extract_temp_val:.1f}C, TFO={exhaust_temp:.1f}C, "
            f"CO2={int(co2)}ppm, CL={comfort_level}, Err={error_state}"
        )
        
        return {
            'outdoor_temp': outdoor_temp,
            'supply_temp': supply_temp,
            'extract_temp': extract_temp_val,
            'exhaust_temp': exhaust_temp,
            'temp_virt_sup_exit': temp_virt_sup_exit,
            'outdoor_humidity': outdoor_hum,
            'extract_humidity': extract_hum,
            'outdoor_humidity_abs': outdoor_hum_abs,
            'extract_humidity_abs': extract_hum_abs,
            'co2': int(co2),
            'co2_indicator': co2_indicator,
            'supply_fan_rpm': supply_fan_rpm,
            'extract_fan_rpm': extract_fan_rpm,
            'air_flow': air_flow,
            'air_flow_ave': air_flow_ave,
            'fan_speed': fan_speed,
            'comfort_level': comfort_level,
            'operating_mode': state,
            'hum_red_mode': hum_red_mode,
            'filter_hours': filter_hours,
            'operating_hours': operating_hours,
            'pressure': pressure,
            'air_density': air_density,
            'supply_vent_pos': supply_vent_pos,
            'extract_vent_pos': extract_vent_pos,
            'bypass_vent_pos': bypass_vent_pos,
            'supply_filter_ful': supply_filter_ful,
            'extract_filter_ful': extract_filter_ful,
            'extract_humidity_indicator': extract_humidity_indicator,
            'outdoor_filter_indicator': outdoor_filter_indicator,
            'exhaust_filter_indicator': exhaust_filter_indicator,
            'heat_recovery': heat_recovery,
            'power_recovery': power_recovery,
            'rssi': to_signed(values['uRSSILow'], 8),
            'error_state': error_state,
            'has_errors': has_errors,
            'deicing': is_deicing,
            'board_version': board_version,
        }
        
    except Exception as e:
        logger.error(f"Parse failed: {e}", exc_info=True)
        return None
