"""
turzx/sensors/fps.py — Game FPS via RTSS shared memory (Windows) or MangoHud (Linux)
=====================================================================================
Windows: reads real-time FPS from RTSS (RivaTuner Statistics Server) shared memory.
Linux: reads FPS from MangoHud log files or shared memory.

If no FPS source is detected, the sensor silently produces no readings.

Linux usage: install mangohud and configure it to write benchmark logs
  MANGOHUD_CONFIG=fps_only,log_interval=100,autostart_log,output_file=/tmp/turzx_fps.log
Or TURZX will auto-detect MangoHud benchmark logs in ~/mangohud_logs/ and /tmp/.
"""

from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

from .base import SensorBackend, SensorReading

# RTSS shared memory constants
_RTSS_SIGNATURE = 0x52545353  # 'RTSS' in little-endian


def _read_rtss_fps() -> tuple[bool, float]:
    """Read FPS from RTSS shared memory.

    First tries the foreground window's PID.  If that isn't tracked by RTSS
    (e.g. TURZX editor is in front), falls back to the entry with the highest
    framerate — that's almost always the game running in the background.

    Returns (rtss_available, fps).  fps=0 when RTSS is active but no 3D app
    is running.  rtss_available=False when RTSS shared memory doesn't exist.
    """
    if sys.platform != "win32":
        return False, 0.0

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    # Get foreground PID
    hwnd = user32.GetForegroundWindow()
    fg_pid = 0
    if hwnd:
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        fg_pid = pid.value

    # Open RTSS shared memory
    FILE_MAP_READ = 0x0004
    kernel32.OpenFileMappingW.restype = wintypes.HANDLE
    hmap = kernel32.OpenFileMappingW(FILE_MAP_READ, False, "RTSSSharedMemoryV2")
    if not hmap:
        return False, 0.0

    result = 0.0
    try:
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        view = kernel32.MapViewOfFile(hmap, FILE_MAP_READ, 0, 0, 0)
        if not view:
            return False, 0.0
        try:
            result = _parse_rtss_view(view, fg_pid)
        finally:
            kernel32.UnmapViewOfFile(ctypes.c_void_p(view))
    finally:
        kernel32.CloseHandle(hmap)

    return True, result


def _entry_fps(data: bytes) -> float:
    """Compute FPS from an RTSS app entry's timing fields (offset 268-283)."""
    time0 = int.from_bytes(data[268:272], "little")
    time1 = int.from_bytes(data[272:276], "little")
    frames = int.from_bytes(data[276:280], "little")
    frametime_us = int.from_bytes(data[280:284], "little")

    dt = time1 - time0
    if dt < 0:
        dt += 0x100000000  # 32-bit wraparound
    if dt > 0 and frames > 0:
        return frames * 1000.0 / dt
    if frametime_us > 0:
        return 1_000_000.0 / frametime_us
    return 0.0


def _parse_rtss_view(view: int, fg_pid: int) -> float:
    """Parse RTSS shared memory and return FPS.

    Priority: foreground PID match → highest-FPS tracked entry.
    """
    import ctypes

    hdr = ctypes.string_at(view, 20)

    sig = int.from_bytes(hdr[0:4], "little")
    if sig != _RTSS_SIGNATURE:
        return 0.0

    entry_size = int.from_bytes(hdr[8:12], "little")
    arr_offset = int.from_bytes(hdr[12:16], "little")
    arr_count = int.from_bytes(hdr[16:20], "little")

    if entry_size == 0 or arr_count == 0:
        return 0.0

    read_size = min(entry_size, 284)
    best_fps = 0.0

    for i in range(arr_count):
        addr = view + arr_offset + i * entry_size

        pid_bytes = ctypes.string_at(addr, 4)
        entry_pid = int.from_bytes(pid_bytes, "little")
        if entry_pid == 0:
            continue

        if read_size < 284:
            continue

        data = ctypes.string_at(addr, 284)
        fps = _entry_fps(data)

        # Foreground PID exact match — return immediately
        if entry_pid == fg_pid and fps > 0:
            return fps

        # Track highest FPS entry as fallback
        if fps > best_fps:
            best_fps = fps

    return best_fps


# ── Linux MangoHud FPS ─────────────────────────────────────────────


def _read_mangohud_fps() -> tuple[bool, float]:
    """Read FPS from MangoHud on Linux.

    Tries multiple methods:
    1. MangoHud log file (CSV benchmark) — most reliable
    2. MangoHud shared memory — fallback

    Returns (mangohud_available, fps).
    """
    fps = _read_mangohud_log()
    if fps > 0:
        return True, fps

    fps = _read_mangohud_shm()
    if fps > 0:
        return True, fps

    # MangoHud might be running but no 3D app active, or logs not found
    if _mangohud_is_running():
        return True, 0.0

    return False, 0.0


def _read_mangohud_log() -> float:
    """Parse MangoHud benchmark log for latest FPS value.

    MangoHud benchmark logs are CSV files with headers like:
        frametime,fps,cpu_load,...
        16.6,60.2,45,...

    Search paths (in order): TURZX's dedicated path, MangoHud's default dir, /tmp.
    """
    log_candidates: list[Path] = []

    # Dedicated TURZX FPS log file (user-configured)
    dedicated = Path("/tmp/turzx_fps.log")
    if dedicated.exists():
        log_candidates.append(dedicated)

    # MangoHud default log directory
    mangohud_dir = Path.home() / "mangohud_logs"
    if mangohud_dir.is_dir():
        try:
            for f in sorted(mangohud_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if f.suffix == ".csv" and f.stat().st_size > 0:
                    log_candidates.append(f)
                    break
        except OSError:
            pass

    # Additional /tmp paths
    for tmp_name in ["mangohud_fps.log", "mangohud.csv"]:
        p = Path("/tmp") / tmp_name
        if p.exists():
            log_candidates.append(p)

    for log_path in log_candidates:
        try:
            fps = _parse_mangohud_csv(log_path)
            if fps > 0:
                return fps
        except Exception:
            continue

    return 0.0


def _parse_mangohud_csv(path: Path, max_age_seconds: int = 5) -> float:
    """Parse a MangoHud CSV log and return the latest FPS value.

    Only considers entries written in the last max_age_seconds.
    Expects CSV with headers containing 'fps' column.
    """
    if not path.exists():
        return 0.0

    file_age = time.time() - path.stat().st_mtime
    if file_age > max_age_seconds:
        return 0.0

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                return 0.0

            fps_col = None
            for col in reader.fieldnames:
                if col.strip().lower() == "fps":
                    fps_col = col
                    break

            if fps_col is None:
                return 0.0

            last_fps = 0.0
            for row in reader:
                try:
                    last_fps = float(row[fps_col])
                except (ValueError, KeyError):
                    continue

            return last_fps
    except Exception:
        return 0.0


def _read_mangohud_shm() -> float:
    """Try to read FPS from MangoHud shared memory.

    Some MangoHud versions create POSIX shared memory segments.
    """
    try:
        import mmap

        shm_names = ["mangohud_fps", "MangoHudSM", "mangohud-sm"]
        for name in shm_names:
            shm_path = Path("/dev/shm") / name
            if not shm_path.exists():
                continue
            # Try opening via shm_open-like mechanism
            try:
                fd = os.open(f"/dev/shm/{name}", os.O_RDONLY)
                try:
                    data = mmap.mmap(fd, 4096, access=mmap.ACCESS_READ)
                    # Simple format: first 4 bytes = fps as float
                    value = float(int.from_bytes(data[0:4], "little", signed=True))
                    if 0 < value < 1000:
                        return value
                finally:
                    os.close(fd)
            except Exception:
                continue
    except Exception:
        pass
    return 0.0


def _mangohud_is_running() -> bool:
    """Check if any process has MangoHud loaded via /proc/*/maps."""
    try:
        for proc_dir in Path("/proc").iterdir():
            if not proc_dir.name.isdigit():
                continue
            maps_path = proc_dir / "maps"
            if not maps_path.exists():
                continue
            try:
                with open(maps_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(65536)  # read first 64KB
                    if "mangohud" in content.lower() or "libMangoHud" in content:
                        return True
            except Exception:
                continue
    except Exception:
        pass
    return False


class FpsSensor(SensorBackend):
    """Reads game FPS via RTSS (Windows) or MangoHud (Linux)."""

    def read(self) -> list[SensorReading]:
        fps: float = 0.0

        if sys.platform == "win32":
            try:
                _, fps = _read_rtss_fps()
            except Exception:
                pass
        elif sys.platform.startswith("linux"):
            try:
                _, fps = _read_mangohud_fps()
            except Exception:
                pass

        # Always report the sensor so it appears in the sensor list.
        # Shows 0 when no FPS source is detected / no 3D app is active.
        return [SensorReading("sys.fps", "Game FPS", round(fps), "FPS", "system")]
