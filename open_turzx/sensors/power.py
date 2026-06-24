"""
open_turzx/sensors/power.py — Estimated real-time system power draw (watts)
===========================================================================
Cross-platform (Windows + Linux) estimate of the whole-machine power
consumption.  A true wall-socket reading is not obtainable from software
alone, so this backend combines *real* component readings where the OS
exposes them and *estimates* the rest:

    power.system_w = cpu_w + gpu_w + baseline_w

Component sources (best available is used, falling back gracefully):

  CPU package power
    - Linux : Intel/AMD RAPL energy counter delta
              (``/sys/class/powercap/intel-rapl:*/energy_uj``), if readable.
              On many distros this file is root-only (CVE-2020-8694); when
              it is not readable we fall back to the load/TDP estimate.
    - Linux : zenpower/amd_energy hwmon ``power1_input`` if present.
    - Windows: MSI Afterburner shared memory ("CPU Power"), if running.
    - Fallback (any OS): idle + load% * (TDP - idle), curved.

  GPU power
    - NVIDIA (Win/Linux): NVML ``nvmlDeviceGetPowerUsage`` (sum of all GPUs).
    - AMD discrete (Linux): amdgpu hwmon ``power1_average`` / ``power1_input``.
    - Windows: MSI Afterburner shared memory ("GPU Power"), if running.

  Baseline
    - RAM, motherboard, drives, fans and PSU conversion losses.  Constant,
      overridable via ``OPEN_TURZX_POWER_BASELINE``.

Tunables (environment variables):
    OPEN_TURZX_CPU_TDP        CPU sustained power budget in W (default 65)
    OPEN_TURZX_CPU_IDLE       CPU idle power in W            (default 8)
    OPEN_TURZX_POWER_BASELINE rest-of-system power in W      (default 40)

For an accurate CPU figure on Linux without estimation, grant the daemon
read access to RAPL, e.g. a udev rule:
    SUBSYSTEM=="powercap", ACTION=="add", \
      RUN+="/bin/chmod -R g+r,o+r /sys%p" ...
or run ``chmod o+r /sys/class/powercap/intel-rapl:*/energy_uj`` after boot.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import psutil

from .base import SensorBackend, SensorReading


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default


# ── Linux: CPU package power via RAPL energy counter ──


class _RaplCpuPower:
    """Read CPU package power from the powercap RAPL interface.

    Computes instantaneous watts from the delta of the monotonic energy
    counter (micro-joules) between two reads, summing all *package* domains.
    Returns ``None`` when RAPL is absent or not readable by this user.
    """

    def __init__(self) -> None:
        self._domains: list[tuple[Path, int]] = []  # (energy_uj path, wrap range)
        self._prev: dict[Path, tuple[int, float]] = {}
        self._available = False
        self._tdp_hint: float | None = None
        if sys.platform == "win32":
            return
        base = Path("/sys/class/powercap")
        if not base.is_dir():
            return
        for entry in sorted(base.glob("intel-rapl:*")):
            # Top-level package domains only: "intel-rapl:0", not "intel-rapl:0:0"
            if entry.name.count(":") != 1:
                continue
            try:
                name = (entry / "name").read_text().strip()
            except OSError:
                continue
            if not name.startswith("package"):
                continue
            energy = entry / "energy_uj"
            try:
                energy.read_text()  # probe readability (raises PermissionError)
            except OSError:
                continue
            wrap = 0
            try:
                wrap = int((entry / "max_energy_range_uj").read_text().strip())
            except (OSError, ValueError):
                pass
            self._domains.append((energy, wrap))
            # Opportunistic TDP hint from the long-term power constraint
            self._read_tdp_hint(entry)
        self._available = bool(self._domains)

    def _read_tdp_hint(self, domain: Path) -> None:
        for cname in ("constraint_1_power_limit_uw", "constraint_0_power_limit_uw"):
            try:
                uw = int((domain / cname).read_text().strip())
            except (OSError, ValueError):
                continue
            if uw > 0:
                watts = uw / 1_000_000.0
                self._tdp_hint = max(self._tdp_hint or 0.0, watts)
                break

    @property
    def available(self) -> bool:
        return self._available

    @property
    def tdp_hint(self) -> float | None:
        return self._tdp_hint

    def read_watts(self) -> float | None:
        if not self._available:
            return None
        now = time.monotonic()
        total = 0.0
        got = False
        for path, wrap in self._domains:
            try:
                energy = int(path.read_text().strip())
            except (OSError, ValueError):
                continue
            prev = self._prev.get(path)
            self._prev[path] = (energy, now)
            if prev is None:
                continue
            prev_energy, prev_t = prev
            dt = now - prev_t
            if dt <= 0:
                continue
            delta = energy - prev_energy
            if delta < 0:  # counter wrapped
                delta += wrap if wrap > 0 else 0
            if delta < 0:
                continue
            total += (delta / 1_000_000.0) / dt
            got = True
        return round(total, 1) if got else None


# ── Linux: hwmon power sensors (zenpower / amd_energy CPU, amdgpu GPU) ──


def _hwmon_power_w(wanted_names: set[str]) -> float | None:
    """Sum ``power1_average``/``power1_input`` for hwmon devices whose
    ``name`` is in *wanted_names*.  Values are micro-watts."""
    base = Path("/sys/class/hwmon")
    if not base.is_dir():
        return None
    total = 0.0
    got = False
    for hw in base.glob("hwmon*"):
        try:
            name = (hw / "name").read_text().strip()
        except OSError:
            continue
        if name not in wanted_names:
            continue
        for fname in ("power1_average", "power1_input"):
            f = hw / fname
            if not f.exists():
                continue
            try:
                uw = int(f.read_text().strip())
            except (OSError, ValueError):
                continue
            total += uw / 1_000_000.0
            got = True
            break
    return round(total, 1) if got else None


# ── NVIDIA GPU power via NVML (Windows + Linux) ──


class _NvmlGpuPower:
    def __init__(self) -> None:
        self._ok = False
        self._handles: list = []
        try:
            import pynvml

            pynvml.nvmlInit()
            self._pynvml = pynvml
            count = pynvml.nvmlDeviceGetCount()
            self._handles = [
                pynvml.nvmlDeviceGetHandleByIndex(i) for i in range(count)
            ]
            self._ok = bool(self._handles)
        except Exception:
            self._ok = False

    @property
    def available(self) -> bool:
        return self._ok

    def read_watts(self) -> float | None:
        if not self._ok:
            return None
        total = 0.0
        got = False
        for h in self._handles:
            try:
                total += self._pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0
                got = True
            except Exception:
                continue
        return round(total, 1) if got else None


# ── Windows: MSI Afterburner shared memory (MAHM) power entries ──


def _mahm_power(*needles: str) -> float | None:
    """Return the first MAHM entry whose name contains all *needles*
    (case-insensitive) and whose unit is watts.  Requires MSI Afterburner
    running; works without admin rights.  See cpu.py for the layout."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import struct
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.OpenFileMappingW.restype = wintypes.HANDLE
        hmap = kernel32.OpenFileMappingW(0x0004, False, "MAHMSharedMemory")
        if not hmap:
            return None
        try:
            kernel32.MapViewOfFile.restype = ctypes.c_void_p
            view = kernel32.MapViewOfFile(hmap, 0x0004, 0, 0, 0)
            if not view:
                return None
            try:
                hdr = ctypes.string_at(view, 32)
                header_size = int.from_bytes(hdr[8:12], "little")
                num_entries = int.from_bytes(hdr[12:16], "little")
                entry_size = int.from_bytes(hdr[16:20], "little")
                if entry_size < 1304 or num_entries == 0:
                    return None
                needles_l = [n.lower() for n in needles]
                for i in range(num_entries):
                    addr = view + header_size + i * entry_size
                    name = (
                        ctypes.string_at(addr, 260)
                        .split(b"\x00")[0]
                        .decode("ascii", errors="ignore")
                        .lower()
                    )
                    if not name or not all(n in name for n in needles_l):
                        continue
                    units = (
                        ctypes.string_at(addr + 260, 260)
                        .split(b"\x00")[0]
                        .decode("ascii", errors="ignore")
                        .lower()
                    )
                    if "w" not in units:  # expect "W"
                        continue
                    value = struct.unpack("<f", ctypes.string_at(addr + 1300, 4))[0]
                    if 0 < value < 2000:
                        return round(value, 1)
                return None
            finally:
                kernel32.UnmapViewOfFile(ctypes.c_void_p(view))
        finally:
            kernel32.CloseHandle(hmap)
    except Exception:
        return None


# ── Backend ──


class PowerSensors(SensorBackend):
    """Estimated whole-system power draw (CPU + GPU + baseline)."""

    def __init__(self) -> None:
        self._cpu_tdp = _env_float("OPEN_TURZX_CPU_TDP", 65.0)
        self._cpu_idle = _env_float("OPEN_TURZX_CPU_IDLE", 8.0)
        self._baseline = _env_float("OPEN_TURZX_POWER_BASELINE", 40.0)

        self._rapl = _RaplCpuPower()
        if self._rapl.tdp_hint:
            self._cpu_tdp = self._rapl.tdp_hint
        self._nvml = _NvmlGpuPower()

        # For the CPU load estimate, track our own cpu_times delta so we do
        # not interfere with CpuSensors' global psutil.cpu_percent() state.
        self._prev_cpu_times = psutil.cpu_times()

    # -- CPU --------------------------------------------------------------

    def _cpu_busy_fraction(self) -> float:
        cur = psutil.cpu_times()
        prev = self._prev_cpu_times
        self._prev_cpu_times = cur

        def _idle(t) -> float:
            return getattr(t, "idle", 0.0) + getattr(t, "iowait", 0.0)

        idle_d = _idle(cur) - _idle(prev)
        total_d = sum(cur) - sum(prev)
        if total_d <= 0:
            return 0.0
        busy = 1.0 - (idle_d / total_d)
        return min(1.0, max(0.0, busy))

    def _cpu_watts(self) -> tuple[float, bool]:
        """Return (watts, is_real). *is_real* is False for the estimate."""
        watts = self._rapl.read_watts()
        if watts is not None and watts > 0:
            return watts, True
        watts = _hwmon_power_w({"zenpower", "amd_energy"})
        if watts is not None and watts > 0:
            return watts, True
        watts = _mahm_power("cpu", "power")
        if watts is not None and watts > 0:
            return watts, True
        # Estimate from load curve.
        frac = self._cpu_busy_fraction()
        est = self._cpu_idle + (self._cpu_tdp - self._cpu_idle) * (frac**1.3)
        return round(est, 1), False

    # -- GPU --------------------------------------------------------------

    def _gpu_watts(self) -> float | None:
        watts = self._nvml.read_watts()
        if watts is not None and watts > 0:
            return watts
        watts = _hwmon_power_w({"amdgpu"})
        if watts is not None and watts > 0:
            return watts
        return _mahm_power("gpu", "power")

    # -- read -------------------------------------------------------------

    def read(self) -> list[SensorReading]:
        readings: list[SensorReading] = []

        cpu_w, _cpu_real = self._cpu_watts()
        readings.append(SensorReading("power.cpu_w", "CPU Power", cpu_w, "W", "power"))

        gpu_w = self._gpu_watts()
        if gpu_w is not None:
            readings.append(
                SensorReading("power.gpu_w", "GPU Power", round(gpu_w, 1), "W", "power")
            )

        system_w = cpu_w + (gpu_w or 0.0) + self._baseline
        readings.append(
            SensorReading(
                "power.system_w", "System Power", round(system_w), "W", "power"
            )
        )

        return readings
