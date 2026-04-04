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
        self._name = ""
        try:
            import pynvml

            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._available = True
            try:
                self._name = pynvml.nvmlDeviceGetName(self._handle)
                if isinstance(self._name, bytes):
                    self._name = self._name.decode()
            except Exception:
                pass
        except Exception:
            pass

    def read(self) -> list[SensorReading]:
        if not self._available or self._handle is None:
            return []

        readings = []
        try:
            import pynvml

            # GPU name
            if self._name:
                readings.append(SensorReading("gpu.name", "GPU", self._name, "", "gpu"))

            # Utilization
            util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            readings.append(
                SensorReading("gpu.percent", "GPU Usage", util.gpu, "%", "gpu")
            )

            # VRAM
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            used_gb = round(mem.used / (1024**3), 1)
            total_gb = round(mem.total / (1024**3), 1)
            readings.append(
                SensorReading("gpu.mem_gb", "VRAM Used", used_gb, "GB", "gpu")
            )
            readings.append(
                SensorReading("gpu.mem_total_gb", "VRAM Total", total_gb, "GB", "gpu")
            )
            if mem.total > 0:
                mem_pct = round(mem.used / mem.total * 100, 1)
                readings.append(
                    SensorReading("gpu.mem_percent", "VRAM", mem_pct, "%", "gpu")
                )

            # Temperature
            temp = pynvml.nvmlDeviceGetTemperature(
                self._handle, pynvml.NVML_TEMPERATURE_GPU
            )
            readings.append(
                SensorReading("gpu.temp", "GPU Temp", temp, "\u00b0C", "gpu")
            )

            # Clock speeds
            try:
                clk_core = pynvml.nvmlDeviceGetClockInfo(
                    self._handle, pynvml.NVML_CLOCK_GRAPHICS
                )
                readings.append(
                    SensorReading("gpu.clock_mhz", "GPU Clock", clk_core, "MHz", "gpu")
                )
            except Exception:
                pass

            try:
                clk_mem = pynvml.nvmlDeviceGetClockInfo(
                    self._handle, pynvml.NVML_CLOCK_MEM
                )
                readings.append(
                    SensorReading(
                        "gpu.mem_clock_mhz", "VRAM Clock", clk_mem, "MHz", "gpu"
                    )
                )
            except Exception:
                pass

            # Fan speed
            try:
                fan = pynvml.nvmlDeviceGetFanSpeed(self._handle)
                readings.append(SensorReading("gpu.fan", "GPU Fan", fan, "%", "gpu"))
            except Exception:
                pass

            # Power draw
            try:
                power_mw = pynvml.nvmlDeviceGetPowerUsage(self._handle)
                power_w = round(power_mw / 1000, 1)
                readings.append(
                    SensorReading("gpu.power_w", "GPU Power", power_w, "W", "gpu")
                )
            except Exception:
                pass

        except Exception:
            pass

        return readings
