"""
turzx/sensors/system.py — System-level sensors (battery, uptime, clock, date, FPS)
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

import psutil

from .base import SensorBackend, SensorReading


# ── Display refresh rate (Windows) ──

def _get_display_refresh_rate() -> int:
    """Return the primary monitor's current refresh rate in Hz via EnumDisplaySettings."""
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        from ctypes import Structure, c_wchar, c_ushort, c_ulong, c_long, c_short

        class DEVMODE(Structure):
            _fields_ = [
                ("dmDeviceName", c_wchar * 32),
                ("dmSpecVersion", c_ushort),
                ("dmDriverVersion", c_ushort),
                ("dmSize", c_ushort),
                ("dmDriverExtra", c_ushort),
                ("dmFields", c_ulong),
                ("dmPositionX", c_long),
                ("dmPositionY", c_long),
                ("dmDisplayOrientation", c_ulong),
                ("dmDisplayFixedOutput", c_ulong),
                ("dmColor", c_short),
                ("dmDuplex", c_short),
                ("dmYResolution", c_short),
                ("dmTTOption", c_short),
                ("dmCollate", c_short),
                ("dmFormName", c_wchar * 32),
                ("dmLogPixels", c_ushort),
                ("dmBitsPerPel", c_ulong),
                ("dmPelsWidth", c_ulong),
                ("dmPelsHeight", c_ulong),
                ("dmDisplayFlags", c_ulong),
                ("dmDisplayFrequency", c_ulong),
            ]

        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):
            return dm.dmDisplayFrequency
    except Exception:
        pass
    return 0


class SystemSensors(SensorBackend):
    def __init__(self) -> None:
        self._display_hz = 0
        self._hz_time = 0.0

    def read(self) -> list[SensorReading]:
        readings = []

        # Uptime
        uptime_s = time.time() - psutil.boot_time()
        hours = int(uptime_s // 3600)
        minutes = int((uptime_s % 3600) // 60)
        readings.append(
            SensorReading(
                "sys.uptime_h", "Uptime", hours, f"h {minutes:02d}m", "system"
            )
        )

        # Clock (HH:MM:SS)
        now = datetime.now()
        readings.append(
            SensorReading("sys.clock", "Clock", now.strftime("%H:%M:%S"), "", "system")
        )

        # Date (YYYY-MM-DD)
        readings.append(
            SensorReading("sys.date", "Date", now.strftime("%Y-%m-%d"), "", "system")
        )

        # Display refresh rate (monitor Hz) — polled every 5s
        t_now = time.monotonic()
        if t_now - self._hz_time >= 5.0:
            self._display_hz = _get_display_refresh_rate()
            self._hz_time = t_now
        if self._display_hz > 0:
            readings.append(
                SensorReading(
                    "sys.refresh_rate", "Refresh Rate", self._display_hz, "Hz", "system"
                )
            )

        # Battery (laptops)
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                readings.append(
                    SensorReading(
                        "sys.battery", "Battery", round(bat.percent, 0), "%", "system"
                    )
                )
                state = "Charging" if bat.power_plugged else "Battery"
                readings.append(
                    SensorReading(
                        "sys.power_state",
                        "Power",
                        1 if bat.power_plugged else 0,
                        state,
                        "system",
                    )
                )
        except (AttributeError, OSError):
            pass

        return readings
