"""
turzx/sensors/cpu.py — CPU sensors via psutil
"""

from __future__ import annotations

import sys

import psutil

from .base import SensorBackend, SensorReading


# ── Windows: CPU temperature via MSI Afterburner shared memory (MAHM) ──


def _mahm_cpu_temp() -> float | None:
    """Read max CPU core temperature from MSI Afterburner shared memory.

    MSI Afterburner (with RivaTuner) exposes hardware monitoring data via
    the MAHMSharedMemory segment.  This is available without admin rights
    as long as Afterburner is running.

    MAHM v2 entry layout (entry_size = 1324):
      5 × char[MAX_PATH]  (5 × 260 = 1300 bytes)  — srcName, srcUnits,
        recommendedFormat, localizedName, localizedUnits
      +1300: float data
      +1304: float minLimit
      +1308: float maxLimit
      +1312: DWORD dwFlags
    """
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

                best = 0.0
                for i in range(num_entries):
                    addr = view + header_size + i * entry_size
                    name_raw = ctypes.string_at(addr, 260)
                    name = name_raw.split(b"\x00")[0].decode("ascii", errors="ignore")
                    if not name:
                        continue
                    name_lower = name.lower()
                    if "cpu" in name_lower and "temperature" in name_lower:
                        data_raw = ctypes.string_at(addr + 1300, 4)
                        temp = struct.unpack("<f", data_raw)[0]
                        if 0 < temp < 150 and temp > best:
                            best = temp
                return best if best > 0 else None
            finally:
                kernel32.UnmapViewOfFile(ctypes.c_void_p(view))
        finally:
            kernel32.CloseHandle(hmap)
    except Exception:
        return None


# ── Windows: real-time freq via PDH ──


class _PdhFreqHelper:
    """Uses Windows Performance Data Helper to get real-time CPU frequency.

    Reads "% Processor Performance" counter which includes turbo/boost.
    Multiply by base MHz to get actual frequency.
    Latency: ~0.3ms per read, zero external dependencies.
    """

    def __init__(self) -> None:
        self._query = None
        self._counter = None
        self._base_mhz: float = 0
        self._ready = False
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            self._ctypes = ctypes
            self._wintypes = wintypes
            self._pdh = ctypes.windll.pdh  # type: ignore[attr-defined]

            # Read base clock from registry
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            mhz, _ = winreg.QueryValueEx(key, "~MHz")
            winreg.CloseKey(key)
            self._base_mhz = float(mhz)

            # Open PDH query
            query = ctypes.c_void_p()
            counter = ctypes.c_void_p()
            self._pdh.PdhOpenQueryW(None, 0, ctypes.byref(query))
            path = r"\Processor Information(_Total)\% Processor Performance"
            self._pdh.PdhAddEnglishCounterW(query, path, 0, ctypes.byref(counter))
            self._query = query
            self._counter = counter
            # First collect is needed to prime the counter
            self._pdh.PdhCollectQueryData(query)
            self._ready = True
        except Exception:
            self._ready = False

    def read_mhz(self) -> float | None:
        """Return actual current frequency in MHz (including turbo)."""
        if not self._ready or self._query is None:
            return None
        try:
            ctypes = self._ctypes
            wintypes = self._wintypes

            self._pdh.PdhCollectQueryData(self._query)

            class PDH_FMT_COUNTERVALUE(ctypes.Structure):
                _fields_ = [
                    ("CStatus", wintypes.DWORD),
                    ("doubleValue", ctypes.c_double),
                ]

            val = PDH_FMT_COUNTERVALUE()
            PDH_FMT_DOUBLE = 0x00000200
            status = self._pdh.PdhGetFormattedCounterValue(
                self._counter, PDH_FMT_DOUBLE, None, ctypes.byref(val)
            )
            if status != 0 or val.CStatus != 0:
                return None

            pct = val.doubleValue
            if pct <= 0:
                return None
            return self._base_mhz * pct / 100.0
        except Exception:
            return None

    def close(self) -> None:
        if self._query is not None:
            try:
                self._pdh.PdhCloseQuery(self._query)
            except Exception:
                pass
            self._query = None
            self._ready = False


def _win32_base_mhz() -> float | None:
    """Read base clock from Windows registry (~MHz)."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        mhz, _ = winreg.QueryValueEx(key, "~MHz")
        winreg.CloseKey(key)
        return float(mhz)
    except Exception:
        return None


class CpuSensors(SensorBackend):
    def __init__(self) -> None:
        psutil.cpu_percent(interval=None)
        self._pdh = _PdhFreqHelper() if sys.platform == "win32" else None
        self._mahm_temp: float | None = None
        self._mahm_temp_time: float = 0.0

    def read(self) -> list[SensorReading]:
        readings = []

        # Usage
        usage = psutil.cpu_percent(interval=None)
        readings.append(SensorReading("cpu.percent", "CPU Usage", usage, "%", "cpu"))

        # Real-time frequency
        got_freq = False

        if self._pdh:
            mhz = self._pdh.read_mhz()
            if mhz and mhz > 0:
                got_freq = True
                readings.append(
                    SensorReading(
                        "cpu.freq_ghz", "CPU Freq", round(mhz / 1000, 2), "GHz", "cpu"
                    )
                )
                readings.append(
                    SensorReading("cpu.freq_mhz", "CPU Freq", round(mhz), "MHz", "cpu")
                )

        if not got_freq:
            freq = psutil.cpu_freq()
            if freq and freq.current:
                readings.append(
                    SensorReading(
                        "cpu.freq_ghz",
                        "CPU Freq",
                        round(freq.current / 1000, 2),
                        "GHz",
                        "cpu",
                    )
                )
                readings.append(
                    SensorReading(
                        "cpu.freq_mhz", "CPU Freq", round(freq.current), "MHz", "cpu"
                    )
                )

        # Base clock
        base = self._base_mhz()
        if base is not None:
            readings.append(
                SensorReading("cpu.base_mhz", "CPU Base", round(base), "MHz", "cpu")
            )

        # Core count
        readings.append(
            SensorReading(
                "cpu.cores", "CPU Cores", psutil.cpu_count(logical=True), "", "cpu"
            )
        )

        # Temperature (max across all cores)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key in ["coretemp", "k10temp", "cpu_thermal", "acpitz"]:
                    if key in temps and temps[key]:
                        t_max = max(e.current for e in temps[key] if e.current > 0)
                        if t_max > 0:
                            readings.append(
                                SensorReading(
                                    "cpu.temp", "CPU Temp", round(t_max, 1), "\u00b0C", "cpu"
                                )
                            )
                            break
        except (AttributeError, OSError, ValueError):
            pass

        # Windows fallback: MSI Afterburner shared memory (cached, poll every 3s)
        if not any(r.sensor_id == "cpu.temp" for r in readings) and sys.platform == "win32":
            import time as _time
            now = _time.monotonic()
            if now - self._mahm_temp_time >= 3.0:
                self._mahm_temp = _mahm_cpu_temp()
                self._mahm_temp_time = now
            if self._mahm_temp is not None:
                readings.append(
                    SensorReading("cpu.temp", "CPU Temp", round(self._mahm_temp, 1), "\u00b0C", "cpu")
                )

        return readings

    @staticmethod
    def _base_mhz() -> float | None:
        freq = psutil.cpu_freq()
        if freq and freq.max:
            return freq.max
        if sys.platform == "win32":
            return _win32_base_mhz()
        return None
