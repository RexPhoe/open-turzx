"""
turzx/sensors/memory.py — RAM sensors via psutil
"""

from __future__ import annotations

import psutil

from .base import SensorBackend, SensorReading

_GB = 1024**3


class MemorySensors(SensorBackend):
    def read(self) -> list[SensorReading]:
        mem = psutil.virtual_memory()
        return [
            SensorReading("mem.percent", "RAM Usage", mem.percent, "%", "memory"),
            SensorReading("mem.used_gb", "RAM Used", round(mem.used / _GB, 1), "GB", "memory"),
            SensorReading("mem.total_gb", "RAM Total", round(mem.total / _GB, 1), "GB", "memory"),
        ]
