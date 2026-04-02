"""
turzx/sensors/cpu.py — CPU sensors via psutil
"""

from __future__ import annotations

import psutil

from .base import SensorBackend, SensorReading


class CpuSensors(SensorBackend):
    def __init__(self) -> None:
        # Prime the first cpu_percent call (non-blocking after this)
        psutil.cpu_percent(interval=None)

    def read(self) -> list[SensorReading]:
        readings = []

        # Usage
        usage = psutil.cpu_percent(interval=None)
        readings.append(SensorReading("cpu.percent", "CPU Usage", usage, "%", "cpu"))

        # Frequency
        freq = psutil.cpu_freq()
        if freq:
            readings.append(
                SensorReading("cpu.freq_ghz", "CPU Freq", round(freq.current / 1000, 2), "GHz", "cpu")
            )

        # Core count
        readings.append(
            SensorReading("cpu.cores", "CPU Cores", psutil.cpu_count(logical=True), "", "cpu")
        )

        # Temperature (Linux primarily, some Windows support)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Try common keys
                for key in ["coretemp", "k10temp", "cpu_thermal", "acpitz"]:
                    if key in temps and temps[key]:
                        t = temps[key][0].current
                        readings.append(SensorReading("cpu.temp", "CPU Temp", round(t, 1), "\u00b0C", "cpu"))
                        break
        except (AttributeError, OSError):
            pass

        return readings
