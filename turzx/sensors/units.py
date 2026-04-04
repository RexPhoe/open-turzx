"""
turzx/sensors/units.py — Sensor unit conversion
=================================================
Defines which units are available for each sensor and the
conversion functions between them.  The renderer calls
``convert()`` to transform a native reading into the
user-chosen display unit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnitOption:
    """A selectable display unit."""

    unit: str  # display suffix, e.g. "GHz"
    multiplier: float  # native_value * multiplier = display_value
    decimals: int  # suggested decimal places


# Map: native_unit -> list of alternative UnitOptions
# The first entry is always the native (identity) option.
UNIT_MAP: dict[str, list[UnitOption]] = {
    # Frequency
    "GHz": [
        UnitOption("GHz", 1.0, 2),
        UnitOption("MHz", 1000.0, 0),
    ],
    "MHz": [
        UnitOption("MHz", 1.0, 0),
        UnitOption("GHz", 0.001, 2),
    ],
    # Temperature
    "\u00b0C": [
        UnitOption("\u00b0C", 1.0, 1),
        UnitOption("\u00b0F", 1.0, 1),  # special: needs offset, handled in convert()
    ],
    # Memory / storage
    "GB": [
        UnitOption("GB", 1.0, 1),
        UnitOption("MB", 1024.0, 0),
        UnitOption("TB", 1.0 / 1024.0, 2),
    ],
    # Percentage — no conversion, but listed for completeness
    "%": [
        UnitOption("%", 1.0, 1),
    ],
    # Power
    "W": [
        UnitOption("W", 1.0, 1),
        UnitOption("kW", 0.001, 3),
    ],
    # Network speed
    "MB/s": [
        UnitOption("MB/s", 1.0, 2),
        UnitOption("KB/s", 1024.0, 0),
        UnitOption("Gb/s", 8.0 / 1024.0, 3),
    ],
}

# ── Date/time format presets ──
# Keys are the sensor's native unit marker; values are label→strftime pairs.
# The renderer uses the display_unit value as a strftime format string.

TIME_FORMATS: dict[str, str] = {
    "HH:MM:SS": "%H:%M:%S",
    "HH:MM": "%H:%M",
    "hh:mm:ss AM": "%I:%M:%S %p",
    "hh:mm AM": "%I:%M %p",
}

DATE_FORMATS: dict[str, str] = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD Mon YYYY": "%d %b %Y",
    "Mon DD, YYYY": "%b %d, %Y",
    "Weekday, DD Mon": "%A, %d %b",
    "DD/MM/YY": "%d/%m/%y",
    "MM/DD/YY": "%m/%d/%y",
}


def available_time_formats() -> list[str]:
    """Return display labels for time format presets."""
    return list(TIME_FORMATS.keys())


def available_date_formats() -> list[str]:
    """Return display labels for date format presets."""
    return list(DATE_FORMATS.keys())


def get_strftime(sensor_id: str, display_unit: str) -> str | None:
    """Return strftime format for a clock/date sensor, or None if not applicable."""
    if sensor_id == "sys.clock":
        return TIME_FORMATS.get(display_unit)
    if sensor_id == "sys.date":
        return DATE_FORMATS.get(display_unit)
    return None


def available_units(native_unit: str) -> list[str]:
    """Return the list of display unit strings for a given native unit."""
    opts = UNIT_MAP.get(native_unit)
    if not opts:
        return [native_unit] if native_unit else []
    return [o.unit for o in opts]


def convert(
    value: float | int, native_unit: str, target_unit: str
) -> tuple[float, str]:
    """Convert *value* from *native_unit* to *target_unit*.

    Returns ``(converted_value, target_unit)``.
    If the conversion is unknown, returns the value unchanged.
    """
    if not target_unit or target_unit == native_unit:
        return (value, native_unit)

    # Special case: Celsius ↔ Fahrenheit (linear + offset)
    if native_unit == "\u00b0C" and target_unit == "\u00b0F":
        return (round(value * 9.0 / 5.0 + 32, 1), "\u00b0F")
    if native_unit == "\u00b0F" and target_unit == "\u00b0C":
        return (round((value - 32) * 5.0 / 9.0, 1), "\u00b0C")

    opts = UNIT_MAP.get(native_unit)
    if not opts:
        return (value, native_unit)

    for opt in opts:
        if opt.unit == target_unit:
            converted = value * opt.multiplier
            return (round(converted, opt.decimals), target_unit)

    return (value, native_unit)
