"""
turzx/sensors/base.py — Sensor abstraction layer
=================================================
Defines the contract for sensor backends and the manager that
aggregates readings from all registered backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SensorReading:
    """A single sensor value."""

    sensor_id: str  # unique key, e.g. "cpu.percent"
    name: str  # human label, e.g. "CPU Usage"
    value: float | int | str
    unit: str  # "%", "C", "GB", "MB/s", ...
    category: str  # "cpu", "memory", "gpu", "disk", "network", "system"


class SensorBackend(ABC):
    """Base class for a group of related sensors (CPU, RAM, ...)."""

    @abstractmethod
    def read(self) -> list[SensorReading]:
        """Return current readings. Called once per render cycle."""
        ...


class SensorManager:
    """Registers backends and collects all readings into a flat dict."""

    def __init__(self) -> None:
        self._backends: list[SensorBackend] = []

    def register(self, backend: SensorBackend) -> None:
        self._backends.append(backend)

    def register_defaults(self) -> None:
        """Register all available platform sensors."""
        from .cpu import CpuSensors
        from .memory import MemorySensors
        from .disk import DiskSensors
        from .network import NetworkSensors
        from .system import SystemSensors
        from .gpu import GpuSensors
        from .foreground import ForegroundSensor
        from .fps import FpsSensor

        for cls in [
            CpuSensors,
            MemorySensors,
            DiskSensors,
            NetworkSensors,
            SystemSensors,
            GpuSensors,
            ForegroundSensor,
            FpsSensor,
        ]:
            try:
                self.register(cls())
            except Exception:
                pass  # backend not available on this platform

    def read_all(self) -> dict[str, SensorReading]:
        """Poll every backend, return {sensor_id: SensorReading}."""
        result: dict[str, SensorReading] = {}
        for backend in self._backends:
            try:
                for reading in backend.read():
                    result[reading.sensor_id] = reading
            except Exception:
                continue
        return result

    def list_available(self) -> list[str]:
        """Return all sensor IDs currently readable."""
        return list(self.read_all().keys())
