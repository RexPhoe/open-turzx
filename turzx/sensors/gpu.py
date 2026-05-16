"""
turzx/sensors/gpu.py — GPU sensors (NVIDIA via pynvml, Intel/AMD iGPU, AMD discrete)
====================================================================================
Supports:
  - NVIDIA GPUs (via pynvml) - dedicated and integrated
  - Intel integrated GPUs (via lspci, sysfs, intel-gpu-tools)
  - AMD integrated GPUs (via lspci, amdgpu sysfs)
  - AMD discrete GPUs (via amdgpu sysfs, rocm-smi)

Falls back gracefully if specific GPU is not found or drivers not installed.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .base import SensorBackend, SensorReading


class GpuSensors(SensorBackend):
    """Aggregate GPU sensors from available backends."""
    
    def __init__(self) -> None:
        self._backends: list[_GpuBackend] = []
        self._init_backends()

    def _init_backends(self) -> None:
        """Initialize available GPU backends."""
        # NVIDIA first (most common in gaming/workstations)
        try:
            self._backends.append(_NvidiaBackend())
        except Exception:
            pass
        
        # Intel iGPU (very common in laptops)
        try:
            self._backends.append(_IntelIgpuBackend())
        except Exception:
            pass
        
        # AMD (both integrated and discrete)
        try:
            self._backends.append(_AmdBackend())
        except Exception:
            pass

    def read(self) -> list[SensorReading]:
        """Read all available GPU sensors."""
        readings = []
        for backend in self._backends:
            try:
                readings.extend(backend.read())
            except Exception:
                pass
        return readings


# ── Backend implementations ──


class _GpuBackend:
    """Base class for GPU backends."""
    
    def read(self) -> list[SensorReading]:
        """Return list of GPU sensor readings."""
        raise NotImplementedError


class _NvidiaBackend(_GpuBackend):
    """NVIDIA GPU support via pynvml."""
    
    def __init__(self) -> None:
        import pynvml
        pynvml.nvmlInit()
        self.pynvml = pynvml
        # Try to get first GPU - will raise if not available
        self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        self._device_id = 0
        self._gpu_count = pynvml.nvmlDeviceGetCount()

    def read(self) -> list[SensorReading]:
        readings = []
        
        # GPU name
        try:
            name = self.pynvml.nvmlDeviceGetName(self._handle)
            if isinstance(name, bytes):
                name = name.decode()
            readings.append(SensorReading("gpu.name", "GPU", name, "", "gpu"))
        except Exception:
            pass

        # Utilization
        try:
            util = self.pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            readings.append(
                SensorReading("gpu.percent", "GPU Usage", util.gpu, "%", "gpu")
            )
        except Exception:
            pass

        # VRAM
        try:
            mem = self.pynvml.nvmlDeviceGetMemoryInfo(self._handle)
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
        except Exception:
            pass

        # Temperature
        try:
            temp = self.pynvml.nvmlDeviceGetTemperature(
                self._handle, self.pynvml.NVML_TEMPERATURE_GPU
            )
            readings.append(
                SensorReading("gpu.temp", "GPU Temp", temp, "\u00b0C", "gpu")
            )
        except Exception:
            pass

        # Clock speeds
        try:
            clk_core = self.pynvml.nvmlDeviceGetClockInfo(
                self._handle, self.pynvml.NVML_CLOCK_GRAPHICS
            )
            readings.append(
                SensorReading("gpu.clock_mhz", "GPU Clock", clk_core, "MHz", "gpu")
            )
        except Exception:
            pass

        try:
            clk_mem = self.pynvml.nvmlDeviceGetClockInfo(
                self._handle, self.pynvml.NVML_CLOCK_MEM
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
            fan = self.pynvml.nvmlDeviceGetFanSpeed(self._handle)
            readings.append(SensorReading("gpu.fan", "GPU Fan", fan, "%", "gpu"))
        except Exception:
            pass

        # Power draw
        try:
            power_mw = self.pynvml.nvmlDeviceGetPowerUsage(self._handle)
            power_w = round(power_mw / 1000, 1)
            readings.append(
                SensorReading("gpu.power_w", "GPU Power", power_w, "W", "gpu")
            )
        except Exception:
            pass

        return readings


class _IntelIgpuBackend(_GpuBackend):
    """Intel integrated GPU support via lspci and sysfs."""
    
    def __init__(self) -> None:
        self._name = self._detect_intel_igpu()
        if not self._name:
            raise Exception("No Intel iGPU detected")

    def _detect_intel_igpu(self) -> str | None:
        """Detect Intel GPU model via lspci."""
        try:
            result = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            for line in result.stdout.split("\n"):
                if "VGA compatible controller" in line or "3D controller" in line:
                    if "Intel" in line:
                        # Extract GPU name (usually after "Intel")
                        parts = line.split("Intel")
                        if len(parts) > 1:
                            return "Intel" + parts[1].strip()
            return None
        except Exception:
            return None

    def read(self) -> list[SensorReading]:
        """Read Intel iGPU metrics (limited without specific drivers)."""
        readings = []
        
        if self._name:
            readings.append(SensorReading("gpu_igpu.name", "iGPU", self._name, "", "gpu"))
        
        # Try to read usage from sysfs if available
        # Most Intel iGPUs have limited metrics without intel-gpu-tools
        try:
            usage = self._read_intel_usage()
            if usage is not None:
                readings.append(
                    SensorReading("gpu_igpu.percent", "iGPU Usage", usage, "%", "gpu")
                )
        except Exception:
            pass
        
        return readings

    def _read_intel_usage(self) -> int | None:
        """Try to read Intel GPU usage from various sources."""
        # Try intel_gpu_top if available
        try:
            result = subprocess.run(
                ["intel_gpu_top", "-s", "1000", "-o", "-"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            # Parse output - format varies by version
            for line in result.stdout.split("\n"):
                if "Render/3D" in line or "Compute" in line:
                    match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
                    if match:
                        return int(float(match.group(1)))
        except Exception:
            pass
        
        return None


class _AmdBackend(_GpuBackend):
    """AMD GPU support (both integrated and discrete) via lspci and sysfs."""
    
    def __init__(self) -> None:
        self._gpus = self._detect_amd_gpus()
        if not self._gpus:
            raise Exception("No AMD GPU detected")

    def _detect_amd_gpus(self) -> list[dict]:
        """Detect all AMD GPUs via lspci."""
        gpus = []
        try:
            result = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            for line in result.stdout.split("\n"):
                if "AMD" in line or "ATI" in line:
                    if "VGA compatible controller" in line or "3D controller" in line:
                        # Try to extract PCI ID (format: XX:XX.X)
                        match = re.match(r"([0-9a-fA-F:\.]+)", line)
                        if match:
                            pci_id = match.group(1)
                            name = line.split("]")[-1].strip() if "]" in line else "AMD GPU"
                            gpus.append({"pci_id": pci_id, "name": name})
        except Exception:
            pass
        
        return gpus

    def read(self) -> list[SensorReading]:
        """Read AMD GPU metrics."""
        readings = []
        
        # Try rocm-smi for better metrics
        try:
            result = subprocess.run(
                ["rocm-smi", "--json"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                readings.extend(self._parse_rocm_smi(result.stdout))
                return readings
        except Exception:
            pass
        
        # Fallback: report basic GPU names and try sysfs
        for i, gpu in enumerate(self._gpus):
            readings.append(
                SensorReading(f"gpu_amd_{i}.name", "AMD GPU", gpu["name"], "", "gpu")
            )
            
            # Try to read usage from sysfs
            try:
                usage = self._read_amd_usage_from_sysfs(gpu["pci_id"])
                if usage is not None:
                    readings.append(
                        SensorReading(
                            f"gpu_amd_{i}.percent",
                            "AMD GPU Usage",
                            usage,
                            "%",
                            "gpu",
                        )
                    )
            except Exception:
                pass
        
        return readings

    def _parse_rocm_smi(self, json_output: str) -> list[SensorReading]:
        """Parse rocm-smi JSON output."""
        readings = []
        try:
            import json
            data = json.loads(json_output)
            
            for gpu_id, gpu_data in enumerate(data.get("gpu_metrics", [])):
                # GPU name/index
                readings.append(
                    SensorReading(
                        f"gpu_amd_{gpu_id}.name",
                        f"AMD GPU {gpu_id}",
                        gpu_data.get("gpu_sku", f"GPU {gpu_id}"),
                        "",
                        "gpu",
                    )
                )
                
                # Utilization
                if "gpu_load" in gpu_data:
                    readings.append(
                        SensorReading(
                            f"gpu_amd_{gpu_id}.percent",
                            "AMD GPU Usage",
                            int(gpu_data["gpu_load"]),
                            "%",
                            "gpu",
                        )
                    )
                
                # Temperature
                if "temperature_edge" in gpu_data:
                    readings.append(
                        SensorReading(
                            f"gpu_amd_{gpu_id}.temp",
                            "AMD GPU Temp",
                            int(gpu_data["temperature_edge"]),
                            "\u00b0C",
                            "gpu",
                        )
                    )
        except Exception:
            pass
        
        return readings

    def _read_amd_usage_from_sysfs(self, pci_id: str) -> int | None:
        """Try to read AMD GPU usage from sysfs (amdgpu driver)."""
        try:
            # Convert PCI ID to amdgpu path (format varies)
            sysfs_path = Path(f"/sys/class/drm/card0/device/gpu_busy_percent")
            if sysfs_path.exists():
                return int(sysfs_path.read_text().strip())
        except Exception:
            pass
        
        return None
