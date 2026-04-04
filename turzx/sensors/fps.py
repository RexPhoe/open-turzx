"""
turzx/sensors/fps.py — Game FPS via RTSS (RivaTuner Statistics Server) shared memory
=====================================================================================
Reads real-time FPS from the foreground application when RTSS is running.
RTSS is bundled with MSI Afterburner and is the de-facto standard for in-game
FPS monitoring. No admin privileges required.

If RTSS is not running, the sensor silently produces no readings.
"""

from __future__ import annotations

import sys

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


class FpsSensor(SensorBackend):
    """Reads game FPS via RTSS shared memory (MSI Afterburner / RTSS)."""

    def read(self) -> list[SensorReading]:
        if sys.platform != "win32":
            return []

        try:
            available, fps = _read_rtss_fps()
        except Exception:
            return []

        if not available:
            return []

        # Always report the sensor so it shows in the sensor list.
        # Shows 0 if RTSS is running but no 3D app is active.
        return [SensorReading("sys.fps", "Game FPS", round(fps), "FPS", "system")]
