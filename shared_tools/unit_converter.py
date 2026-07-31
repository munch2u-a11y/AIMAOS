"""Unit conversion, shared by every AIMAOS agent. Pure stdlib, no credentials.

Covers the categories most likely to come up in office work: length, mass,
volume, time, and temperature (which needs formulas, not factors).
"""
TOOL_DEFINITION = {
    "name": "unit_converter",
    "description": "Converts a numeric value between units of length, mass, volume, time, or temperature.",
    "parameters": {
        "type": "object",
        "properties": {
            "value": {
                "type": "number",
                "description": "The numeric value to convert."
            },
            "from_unit": {
                "type": "string",
                "description": "Source unit, e.g. 'mi', 'kg', 'gal', 'hr', 'F'."
            },
            "to_unit": {
                "type": "string",
                "description": "Target unit, e.g. 'km', 'lb', 'l', 'min', 'C'."
            }
        },
        "required": ["value", "from_unit", "to_unit"]
    }
}

# Each category maps unit -> factor to the category's base unit.
_LENGTH_M = {"m": 1, "km": 1000, "cm": 0.01, "mm": 0.001, "mi": 1609.344,
             "yd": 0.9144, "ft": 0.3048, "in": 0.0254}
_MASS_KG = {"kg": 1, "g": 0.001, "mg": 1e-6, "lb": 0.45359237, "oz": 0.028349523125}
_VOLUME_L = {"l": 1, "ml": 0.001, "gal": 3.785411784, "qt": 0.946352946,
             "pt": 0.473176473, "cup": 0.2365882365, "floz": 0.0295735295625}
_TIME_S = {"s": 1, "min": 60, "hr": 3600, "day": 86400, "week": 604800}

_CATEGORIES = {"length": _LENGTH_M, "mass": _MASS_KG, "volume": _VOLUME_L, "time": _TIME_S}
_TEMP_UNITS = {"c", "f", "k"}


def _to_celsius(value, unit):
    unit = unit.lower()
    if unit == "c":
        return value
    if unit == "f":
        return (value - 32) * 5 / 9
    if unit == "k":
        return value - 273.15
    raise ValueError(unit)


def _from_celsius(value, unit):
    unit = unit.lower()
    if unit == "c":
        return value
    if unit == "f":
        return value * 9 / 5 + 32
    if unit == "k":
        return value + 273.15
    raise ValueError(unit)


def execute(value, from_unit, to_unit):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return f"Error: value must be numeric, got {value!r}."

    fu, tu = from_unit.strip(), to_unit.strip()
    if fu.lower() in _TEMP_UNITS and tu.lower() in _TEMP_UNITS:
        result = _from_celsius(_to_celsius(value, fu), tu)
        return f"{value} {from_unit} = {result:.4g} {to_unit}"

    for name, factors in _CATEGORIES.items():
        if fu in factors and tu in factors:
            base = value * factors[fu]
            result = base / factors[tu]
            return f"{value} {from_unit} = {result:.6g} {to_unit} ({name})"

    return (f"Error: don't know how to convert '{from_unit}' to '{to_unit}'. "
           f"Supported: temperature (C/F/K), length ({', '.join(_LENGTH_M)}), "
           f"mass ({', '.join(_MASS_KG)}), volume ({', '.join(_VOLUME_L)}), "
           f"time ({', '.join(_TIME_S)}).")
