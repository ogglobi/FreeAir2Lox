"""
FreeAir Bridge - Shared Utility Functions
Common helper functions used across multiple modules.
Ported from ioBroker.freeair DataParser.
"""

from typing import List, Optional, Dict, Any, Union


def to_signed(num: int, bits: int) -> int:
    """
    Convert unsigned integer to signed integer.
    
    Args:
        num: Unsigned integer value
        bits: Number of bits for the signed representation
        
    Returns:
        Signed integer value
    """
    max_un = 1 << bits
    if num >= max_un / 2:
        num = num - max_un
    return num


def byte_to_bits(byte_val: int) -> List[int]:
    """
    Convert a byte to array of 8 bits (MSB first, index 7-0).
    
    Args:
        byte_val: Byte value (0-255)
        
    Returns:
        List of 8 bits
    """
    bits = [0] * 8
    power = 128
    for i in range(7, -1, -1):
        if byte_val >= power:
            bits[i] = 1
            byte_val -= power
        power //= 2
    return bits


def divide_byte(divisions: List[int], byte_val: int) -> List[List[int]]:
    """
    Divide a byte into bit segments according to divisions.
    
    Args:
        divisions: List of bit counts for each segment (e.g., [5, 3])
        byte_val: Byte value to divide
        
    Returns:
        List of bit-arrays (e.g., [[b,b,b,b,b], [b,b,b]])
    """
    bits = byte_to_bits(byte_val)
    divided = []
    bit_idx = 0
    for num_bits in divisions:
        segment_bits = []
        for _ in range(num_bits):
            segment_bits.append(bits[bit_idx])
            bit_idx += 1
        divided.append(segment_bits)
    return divided


def get_number_fr_bits(ar_bits: Optional[List[int]]) -> Optional[int]:
    """
    Convert bit array to number (LSB first).
    
    Args:
        ar_bits: Array of bits
        
    Returns:
        Integer value or None if input is None
    """
    if ar_bits is None:
        return None
    if not ar_bits or len(ar_bits) == 0:
        return 0
    potenz = 1
    u_number = 0
    for i in range(len(ar_bits)):
        u_number += ar_bits[i] * potenz
        potenz *= 2
    return u_number


def low_plus_high(
    low: Union[int, List[int]], 
    high: Union[int, List[int]], 
    super_high: Optional[List[int]] = None
) -> int:
    """
    Combine low byte + high bits (from bit-arrays) into one number.
    Ported from ioBroker GitHub (line 464-500 dataParser.ts).
    
    Args:
        low: Can be integer (from data[idx]) or bit-array
        high: Always bit-array (from divide_byte())
        super_high: Optional bit-array for extended values
        
    Returns:
        Combined integer value
    """
    ar_bits_total = [0] * 21
    
    # LSB7: Get 7 bits from low byte
    if isinstance(low, int):
        lsb7 = byte_to_bits(low)
    else:
        lsb7 = low
    
    for i in range(min(7, len(lsb7))):
        ar_bits_total[i] = lsb7[i]
    
    # MSB7: 7 bits from high byte
    if super_high is not None:
        if isinstance(high, int):
            msb7 = byte_to_bits(high)
        else:
            msb7 = high
            
        for i in range(min(7, len(msb7))):
            ar_bits_total[i + 7] = msb7[i]
        
        # SuperHigh bits
        super_high_bit = 0
        for i in range(14, 14 + len(super_high)):
            ar_bits_total[i] = super_high[super_high_bit]
            super_high_bit += 1
    else:
        if isinstance(high, int):
            high = byte_to_bits(high)
            
        high_bit = 0
        for i in range(7, 7 + len(high)):
            ar_bits_total[i] = high[high_bit]
            high_bit += 1
    
    # Convert combined bits to number
    value = 0
    potenz = 1
    for i in range(20):
        value = value + ar_bits_total[i] * potenz
        potenz *= 2
    
    return value


def get_pressure(
    pressure5_msb: Optional[Union[int, List[int]]], 
    pressure4_lsb: Optional[Union[int, List[int]]]
) -> Optional[int]:
    """
    Calculate pressure from 5 MSB bits + 4 LSB bits.
    
    Args:
        pressure5_msb: 5 MSB bits (int or bit-array)
        pressure4_lsb: 4 LSB bits (int or bit-array)
        
    Returns:
        Pressure value + 700 offset, or None if inputs are invalid
    """
    if pressure5_msb is None or pressure4_lsb is None:
        return None
    
    if isinstance(pressure4_lsb, int):
        pressure4_lsb = byte_to_bits(pressure4_lsb)[:4]
    if isinstance(pressure5_msb, int):
        pressure5_msb = byte_to_bits(pressure5_msb)[:5]
    
    ar_bits_total = [0] * 21
    for i in range(min(4, len(pressure4_lsb))):
        ar_bits_total[i] = pressure4_lsb[i]
    for i in range(min(5, len(pressure5_msb))):
        ar_bits_total[i + 4] = pressure5_msb[i]
    
    value = 0
    potenz = 1
    for i in range(20):
        value = value + ar_bits_total[i] * potenz
        potenz *= 2
    
    return value + 700


def get_abs_hum(rel_hum: Optional[float], temp: Optional[float]) -> Optional[float]:
    """
    Calculate absolute humidity from relative humidity and temperature.
    
    Args:
        rel_hum: Relative humidity in %
        temp: Temperature in °C
        
    Returns:
        Absolute humidity in g/m³, or None if inputs are invalid
    """
    if rel_hum is None or temp is None:
        return None
    vapor_pressure = (rel_hum / 100.0) * 6.1078 * pow(10, (7.45 * temp) / (235 + temp))
    abs_hum = (216.7 * vapor_pressure) / (273.15 + temp)
    return round(abs_hum, 2)


def get_air_density(pressure: Optional[float], temp_extract: Optional[float]) -> Optional[float]:
    """
    Calculate air density.
    
    Args:
        pressure: Air pressure in hPa
        temp_extract: Extract temperature in °C
        
    Returns:
        Air density in kg/m³, or None if inputs are invalid
    """
    if pressure is None or temp_extract is None:
        return None
    density = (pressure * 100) / ((temp_extract + 273.15) * 287.058)
    return round(density, 3)


def get_indicator_level(value: float, levels: List[Dict[str, Any]]) -> Optional[int]:
    """
    Get indicator level based on value and thresholds.
    
    Args:
        value: Value to check
        levels: List of level definitions with 'min', 'max', and 'level' keys
        
    Returns:
        Level value or None if no match
    """
    for level_def in levels:
        min_val = level_def.get('min', -float('inf'))
        max_val = level_def.get('max', float('inf'))
        if min_val <= value <= max_val:
            return level_def['level']
    return None


# Filter RPM lookup tables
FAN_SUPPLY_RPMS: Dict[int, List[int]] = {
    0: [20, 870, 1510],
    1: [30, 1000, 1640],
    2: [40, 1230, 1870],
    3: [50, 1460, 2100],
    4: [60, 1690, 2410],
    5: [70, 1910, 2630],
    6: [85, 2230, 2950],
    7: [100, 2540, 3260],
    8: [0, 0, 0]
}

FAN_EXTRACT_RPMS: Dict[int, List[int]] = {
    0: [20, 920, 1560],
    1: [30, 1040, 1680],
    2: [40, 1260, 1900],
    3: [50, 1480, 2200],
    4: [60, 1700, 2420],
    5: [70, 1910, 2710],
    6: [85, 2210, 2930],
    7: [100, 2480, 3200],
    8: [0, 0, 0]
}


def filter_status(
    fan_rpm: Optional[int], 
    fan_speed: Optional[int], 
    filter_rpms: Dict[int, List[int]]
) -> Optional[int]:
    """
    Calculate filter status based on RPM.
    
    Args:
        fan_rpm: Current fan RPM
        fan_speed: Fan speed setting (0-10)
        filter_rpms: RPM lookup table
        
    Returns:
        Filter status (1-4 or 100 for clogged), or None
    """
    if fan_rpm is None or fan_speed is None:
        return None
    fan_speed = fan_speed * 10
    for i in range(len(filter_rpms)):
        if i not in filter_rpms:
            break
        if filter_rpms[i][0] < fan_speed:
            continue
        n_diff = filter_rpms[i][2] - filter_rpms[i][1]
        if fan_rpm < filter_rpms[i][1] - n_diff / 2:
            return 100
        if fan_rpm < filter_rpms[i][1] + n_diff * 0.4:
            return 1
        if fan_rpm < filter_rpms[i][1] + n_diff * 0.7:
            return 2
        if fan_rpm < filter_rpms[i][1] + n_diff * 0.95:
            return 3
        return 4
    return None


def filter_supply_status(fan_supply_rpm: Optional[int], fan_speed: Optional[int]) -> Optional[int]:
    """Calculate supply filter status."""
    return filter_status(fan_supply_rpm, fan_speed, FAN_SUPPLY_RPMS)


def filter_extract_status(fan_extract_rpm: Optional[int], fan_speed: Optional[int]) -> Optional[int]:
    """Calculate extract filter status."""
    return filter_status(fan_extract_rpm, fan_speed, FAN_EXTRACT_RPMS)


def get_heat_recovery(
    temp_extract: Optional[float], 
    temp_outdoor: Optional[float], 
    temp_supply: Optional[float], 
    air_flow: Optional[int]
) -> int:
    """
    Calculate heat recovery efficiency.
    
    Args:
        temp_extract: Extract air temperature in °C
        temp_outdoor: Outdoor temperature in °C
        temp_supply: Supply air temperature in °C
        air_flow: Air flow in m³/h
        
    Returns:
        Heat recovery efficiency in %
    """
    if None in [temp_extract, temp_outdoor, temp_supply, air_flow] or air_flow <= 0:
        return 0
    try:
        temp_diff = temp_extract - temp_outdoor
        if temp_diff <= 0:
            return 0
        return int((temp_supply - temp_outdoor) / temp_diff * 100)
    except:
        return 0


def get_power_recovery(
    temp_extract: Optional[float], 
    temp_outdoor: Optional[float], 
    temp_supply: Optional[float], 
    air_flow: Optional[int]
) -> int:
    """Calculate power recovery (heat recovery * 0.85)."""
    recovery = get_heat_recovery(temp_extract, temp_outdoor, temp_supply, air_flow)
    if recovery == 0:
        return 0
    return int(recovery * 0.85)


def get_cooling_power(
    air_flow: Optional[int], 
    temp_extract: Optional[float], 
    temp_supply: Optional[float]
) -> int:
    """
    Calculate cooling power in Watts.
    
    Args:
        air_flow: Air flow in m³/h
        temp_extract: Extract air temperature in °C
        temp_supply: Supply air temperature in °C
        
    Returns:
        Cooling power in Watts
    """
    if None in [air_flow, temp_extract, temp_supply] or air_flow <= 0:
        return 0
    try:
        temp_diff = temp_extract - temp_supply
        if temp_diff <= 0:
            return 0
        power = (air_flow / 3600.0) * 1.2 * 1000 * 1005 * temp_diff
        return int(power)
    except:
        return 0


# Operating Modes
OPERATING_MODES: Dict[int, str] = {
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
PROGRAMS: Dict[int, str] = {
    0: "Minimum ventilation",
    1: "Dehumidification (rel)",
    2: "Dehumidification (abs)",
    3: "Active cooling",
    4: "CO2 reduction",
    5: "Water input",
    6: "Outside air < -22°C",
    7: "Humidity entry",
}


def get_operating_mode_name(mode: int) -> str:
    """Get human-readable operating mode name."""
    return OPERATING_MODES.get(mode, f"Unknown ({mode})")


def get_program_name(program: int) -> str:
    """Get human-readable program name."""
    return PROGRAMS.get(program, f"Unknown ({program})")
