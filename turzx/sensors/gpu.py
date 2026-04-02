"""
turzx/sensors/gpu.py — GPU sensors (NVIDIA via pynvml, AMD stub)
================================================================
Optional: works only if pynvml is installed and an NVIDIA GPU is present.
AMD/Intel GPU support is planned for a future phase.
"""

from __future__ import annotations

from .base import SensorBackend, SensorReading


class GpuSensors(SensorBackend):
    def __init__(self) -> None:
        self._available = False
        self._handle = None
        try:
            import pynvml

            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._available = True
        except Exception:
            pass

    def read(self) -> list[SensorReading]:
        if not self._available or self._handle is None:
            return []

        readings = []
        try:
            import pynvml

            util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            readings.append(
                SensorReading("gpu.percent", "GPU Usage", util.gpu, "%", "gpu")
            )

            mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            used_gb = round(mem.used / (1024**3), 1)
            readings.append(
                SensorReading("gpu.mem_gb", "VRAM Used", used_gb, "GB", "gpu")
            )

            temp = pynvml.nvmlDeviceGetTemperature(self._handle, pynvml.NVML_TEMPERATURE_GPU)
            readings.append(
                SensorReading("gpu.temp", "GPU Temp", temp, "\u00b0C", "gpu")
            )
        except Exception:
            pass

        return readings
