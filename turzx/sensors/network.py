"""
turzx/sensors/network.py — Network throughput sensors via psutil
"""

from __future__ import annotations

import time

import psutil

from .base import SensorBackend, SensorReading

_MB = 1024 * 1024


class NetworkSensors(SensorBackend):
    def __init__(self) -> None:
        counters = psutil.net_io_counters()
        self._prev_sent = counters.bytes_sent
        self._prev_recv = counters.bytes_recv
        self._prev_time = time.monotonic()

    def read(self) -> list[SensorReading]:
        counters = psutil.net_io_counters()
        now = time.monotonic()
        dt = now - self._prev_time
        if dt <= 0:
            dt = 1.0

        up_speed = (counters.bytes_sent - self._prev_sent) / dt / _MB
        down_speed = (counters.bytes_recv - self._prev_recv) / dt / _MB

        self._prev_sent = counters.bytes_sent
        self._prev_recv = counters.bytes_recv
        self._prev_time = now

        return [
            SensorReading("net.up_mbps", "Upload", round(up_speed, 2), "MB/s", "network"),
            SensorReading("net.down_mbps", "Download", round(down_speed, 2), "MB/s", "network"),
        ]
