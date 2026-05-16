"""
turzx/sensors/fps.py — Game FPS via RTSS shared memory (Windows) or MangoHud (Linux)
=====================================================================================
Windows: reads real-time FPS from RTSS (RivaTuner Statistics Server) shared memory.
Linux: reads FPS from MangoHud log files or shared memory.

If no FPS source is detected, the sensor silently produces no readings.

Linux usage: install mangohud and configure it to write benchmark logs
  MANGOHUD_CONFIG=fps_only,log_interval=100,autostart_log,output_folder=/tmp/turzx_logs
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
_TURZX_MANGOHUD_DIR = Path("/tmp/turzx_logs")
_MANGOHUD_CONFIG = (
    "fps_only,alpha=0,background_alpha=0,font_size=1,"
    "log_interval=100,autostart_log,output_folder=/tmp/turzx_logs"
)


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
    _ensure_mangohud_log_dir()

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


def _find_recent_mangohud_csv(search_dir: Path) -> Path | None:
    """Return the most recently modified MangoHud CSV log in a directory.

    MangoHud v0.8.3+ names logs as `{program}_{YYYY-MM-DD}_{HH-MM-SS}.csv`.
    We match files ending with the timestamp pattern and sort by mtime.
    """
    if not search_dir.is_dir():
        return None
    csv_files: list[Path] = []
    try:
        for f in search_dir.iterdir():
            if not f.is_file():
                continue
            if f.suffix != ".csv":
                continue
            if f.stat().st_size == 0:
                continue
            csv_files.append(f)
    except OSError:
        return None
    if not csv_files:
        return None
    csv_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return csv_files[0]


def _ensure_mangohud_log_dir() -> None:
    """Create the log folder used by TURZX launcher configs if possible."""
    try:
        _TURZX_MANGOHUD_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _read_mangohud_log() -> float:
    """Parse MangoHud benchmark log for latest FPS value.

    MangoHud v0.8.0+ writes CSV logs to $HOME by default (when output_folder
    is not set).  The naming convention is: {program}_{timestamp}.csv

    Search order:
    1. Dedicated /tmp/turzx_fps.log (legacy output_file, pre-0.8.3)
    2. /tmp/turzx_logs/ (recommended output_folder for TURZX)
    3. MangoHud default: ~/mangohud_logs/
    4. $HOME (MangoHud >=0.8.3 default when output_folder is empty)
    5. /tmp/ fallback CSV files
    """
    log_candidates: list[Path] = []

    # 1. Legacy dedicated log file (output_file parameter, pre-0.8.3)
    legacy = Path("/tmp/turzx_fps.log")
    if legacy.exists():
        log_candidates.append(legacy)

    # 2. TURZX recommended output_folder
    recent = _find_recent_mangohud_csv(_TURZX_MANGOHUD_DIR)
    if recent:
        log_candidates.append(recent)

    # 3. MangoHud legacy log directory (~/mangohud_logs/)
    mangohud_dir = Path.home() / "mangohud_logs"
    recent = _find_recent_mangohud_csv(mangohud_dir)
    if recent:
        log_candidates.append(recent)

    # 4. $HOME (MangoHud >=0.8.3 default when output_folder not set)
    recent = _find_recent_mangohud_csv(Path.home())
    if recent:
        log_candidates.append(recent)

    # 5. /tmp loose CSV files (e.g. mangohud_fps.log, mangohud.csv)
    for tmp_name in ["mangohud_fps.log", "mangohud.csv"]:
        p = Path("/tmp") / tmp_name
        if p.exists():
            log_candidates.append(p)
    recent = _find_recent_mangohud_csv(Path("/tmp"))
    if recent:
        log_candidates.append(recent)

    for log_path in log_candidates:
        try:
            fps = _parse_mangohud_csv(log_path)
            if fps > 0:
                return fps
        except Exception:
            continue

    return 0.0


def _parse_mangohud_csv(path: Path, max_age_seconds: int = 10) -> float:
    """Parse a MangoHud CSV log and return the latest FPS value.

    Handles two MangoHud CSV formats:
    - v0.7.x: First row = column headers (fps,frametime,...)
    - v0.8.x: Three header rows (system info, then fps,frametime,...)
      The third row contains the actual column names.

    Only considers entries written in the last max_age_seconds.
    """
    if not path.exists():
        return 0.0

    file_age = time.time() - path.stat().st_mtime
    if file_age > max_age_seconds:
        return 0.0

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if len(lines) < 2:
            return 0.0

        # MangoHud v0.8.x: third line is the actual header row
        # MangoHud v0.7.x: first line is the header row
        header_line = 0
        for i, line in enumerate(lines[:4]):
            if "fps" in line.lower() and "frametime" in line.lower():
                header_line = i
                break

        if header_line == 0 and len(lines) <= 2:
            return 0.0

        # Parse with csv.DictReader, skipping lines before the header
        import io
        csv_data = "".join(lines[header_line:])
        reader = csv.DictReader(io.StringIO(csv_data))
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


def _mangohud_installed() -> bool:
    """Check if mangohud binary is installed on the system."""
    import shutil
    return shutil.which("mangohud") is not None


def fps_diagnose() -> dict:
    """Return a diagnostic dict of the FPS setup on Linux.

    Returns keys: installed, running, log_found, log_path, fps, suggestion.
    """
    result: dict = {
        "installed": False,
        "running": False,
        "log_found": False,
        "log_path": "",
        "fps": 0.0,
        "suggestion": "",
    }

    if sys.platform != "win32" and not sys.platform.startswith("linux"):
        result["suggestion"] = "FPS sensor is platform-specific (Windows/RTSS, Linux/MangoHud)"
        return result

    _ensure_mangohud_log_dir()

    result["installed"] = _mangohud_installed()
    result["running"] = _mangohud_is_running()

    # Check the same sources used by the live reader.
    candidates = [
        Path("/tmp/turzx_fps.log"),
        _find_recent_mangohud_csv(_TURZX_MANGOHUD_DIR),
        _find_recent_mangohud_csv(Path.home() / "mangohud_logs"),
        _find_recent_mangohud_csv(Path.home()),
        _find_recent_mangohud_csv(Path("/tmp")),
    ]
    for candidate in candidates:
        if candidate is None or not candidate.exists():
            continue
        result["log_found"] = True
        result["log_path"] = str(candidate)
        result["fps"] = _parse_mangohud_csv(candidate, max_age_seconds=60)
        break

    if not result["installed"]:
        result["suggestion"] = (
            "MangoHud is not installed. Install it with your package manager:\n"
            "  Arch:   sudo pacman -S mangohud\n"
            "  Ubuntu: sudo apt install mangohud\n"
            "  Fedora: sudo dnf install mangohud\n"
            "Then set in Lutris/Steam launch options:\n"
            f"  MANGOHUD=1 MANGOHUD_CONFIG={_MANGOHUD_CONFIG}"
        )
    elif not result["log_found"]:
        result["suggestion"] = (
            "MangoHud is installed but no log file was found. "
            "Launch a game with MangoHud logging enabled:\n"
            f"  MANGOHUD=1 MANGOHUD_CONFIG={_MANGOHUD_CONFIG}\n"
            "Note: MangoHud >=0.8.3 ignores 'output_file'. Use 'output_folder' instead."
        )
    elif result["fps"] == 0.0:
        result["suggestion"] = (
            "MangoHud log found but FPS is 0. Make sure a game is actually rendering frames."
        )
    else:
        result["suggestion"] = "FPS sensor is working correctly."

    return result


class FpsSensor(SensorBackend):
    """Reads game FPS via RTSS (Windows) or MangoHud (Linux)."""

    def __init__(self) -> None:
        super().__init__()
        self._diagnosed = False

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
            if not self._diagnosed:
                self._diagnosed = True
                diag = fps_diagnose()
                if not diag["installed"] or not diag["log_found"]:
                    import sys as _sys
                    print(f"[TURZX FPS] {diag['suggestion']}", file=_sys.stderr)

        # Always report the sensor so it appears in the sensor list.
        # Keep sys.fps for existing layouts and expose the documented fps.current.
        value = round(fps)
        return [
            SensorReading("fps.current", "Game FPS", value, "FPS", "system"),
            SensorReading("sys.fps", "Game FPS", value, "FPS", "system"),
        ]
