"""
turzx/sensors/foreground.py — Foreground application sensor
============================================================
Detects which window/application is currently in the foreground.
Windows: uses win32gui (pywin32) or ctypes fallback.
Linux: uses xdotool or /proc.
"""

from __future__ import annotations

import os
import sys

from .base import SensorBackend, SensorReading


def _get_foreground_window_title() -> str:
    """Get the title of the foreground window."""
    if sys.platform == "win32":
        return _win32_foreground_title()
    return _linux_foreground_title()


def _win32_foreground_title() -> str:
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def _win32_foreground_process() -> str:
    """Get the process name of the foreground window."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ""

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not handle:
            return ""

        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(260)
            kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            path = buf.value
            return os.path.basename(path) if path else ""
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def _linux_foreground_title() -> str:
    try:
        import subprocess

        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


class ForegroundSensor(SensorBackend):
    def read(self) -> list[SensorReading]:
        readings = []

        title = _get_foreground_window_title()
        if title:
            # Truncate long titles for display
            display = title if len(title) <= 40 else title[:37] + "..."
            readings.append(
                SensorReading("app.window_title", "Window", display, "", "system")
            )

        if sys.platform == "win32":
            proc = _win32_foreground_process()
            if proc:
                readings.append(SensorReading("app.process", "App", proc, "", "system"))

        return readings
