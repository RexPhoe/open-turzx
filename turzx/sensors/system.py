"""
turzx/sensors/system.py — System-level sensors (battery, uptime) via psutil
"""

from __future__ import annotations

import time

import psutil

from .base import SensorBackend, SensorReading


class SystemSensors(SensorBackend):
    def read(self) -> list[SensorReading]:
        readings = []

        # Uptime
        uptime_s = time.time() - psutil.boot_time()
        hours = int(uptime_s // 3600)
        minutes = int((uptime_s % 3600) // 60)
        readings.append(
            SensorReading("sys.uptime_h", "Uptime", hours, f"h {minutes:02d}m", "system")
        )

        # Battery (laptops)
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                readings.append(
                    SensorReading("sys.battery", "Battery", round(bat.percent, 0), "%", "system")
                )
                state = "Charging" if bat.power_plugged else "Battery"
                readings.append(
                    SensorReading("sys.power_state", "Power", 1 if bat.power_plugged else 0, state, "system")
                )
        except (AttributeError, OSError):
            pass

        return readings
