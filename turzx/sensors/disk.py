"""
turzx/sensors/disk.py — Disk sensors via psutil
"""

from __future__ import annotations

import sys

import psutil

from .base import SensorBackend, SensorReading

_GB = 1024**3


class DiskSensors(SensorBackend):
    def __init__(self) -> None:
        self._root = "C:\\" if sys.platform == "win32" else "/"

    def read(self) -> list[SensorReading]:
        readings = []

        try:
            usage = psutil.disk_usage(self._root)
            readings.append(
                SensorReading("disk.percent", "Disk Usage", usage.percent, "%", "disk")
            )
            readings.append(
                SensorReading("disk.used_gb", "Disk Used", round(usage.used / _GB, 1), "GB", "disk")
            )
            readings.append(
                SensorReading("disk.total_gb", "Disk Total", round(usage.total / _GB, 1), "GB", "disk")
            )
        except OSError:
            pass

        return readings
