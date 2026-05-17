"""
turzx/sensors/foreground.py — Foreground application sensor
============================================================
Detects which window/application is currently in the foreground.
Windows: uses win32gui (pywin32) or ctypes fallback.
Linux: uses Hyprland's hyprctl on Wayland, or xdotool on X11.
"""

from __future__ import annotations

import os
import sys

from .base import SensorBackend, SensorReading


def _get_foreground_window_title() -> str:
    """Get the title of the foreground window."""
    if sys.platform == "win32":
        return _win32_foreground_title()
    info = _linux_foreground_info()
    return info.get("title", "")


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


def _process_name_from_pid(pid: int | str) -> str:
    try:
        pid_text = str(pid).strip()
        if not pid_text.isdigit():
            return ""
        with open(f"/proc/{pid_text}/comm", "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _hyprland_foreground_info() -> dict[str, str]:
    """Return active window details on Hyprland/Wayland."""
    try:
        import json
        import subprocess

        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        data = json.loads(result.stdout)
        pid = str(data.get("pid") or "")
        proc = _process_name_from_pid(pid)
        window_class = str(data.get("class") or data.get("initialClass") or "")
        return {
            "title": str(data.get("title") or data.get("initialTitle") or ""),
            "process": proc or window_class,
            "class": window_class,
            "pid": pid,
        }
    except Exception:
        return {}


def _x11_foreground_info() -> dict[str, str]:
    """Return active window details on X11 via xdotool."""
    try:
        import subprocess

        title_result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        pid_result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowpid"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        pid = pid_result.stdout.strip() if pid_result.returncode == 0 else ""
        return {
            "title": title_result.stdout.strip() if title_result.returncode == 0 else "",
            "process": _process_name_from_pid(pid),
            "class": "",
            "pid": pid,
        }
    except Exception:
        return {}


def _linux_foreground_info() -> dict[str, str]:
    """Return active app details using the best available Linux backend."""
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        info = _hyprland_foreground_info()
        if info:
            return info
    return _x11_foreground_info()


def _linux_foreground_process() -> str:
    """Get the process name of the active Linux window."""
    return _linux_foreground_info().get("process", "")


class ForegroundSensor(SensorBackend):
    def read(self) -> list[SensorReading]:
        readings = []
        linux_info = _linux_foreground_info() if sys.platform != "win32" else {}

        title = _win32_foreground_title() if sys.platform == "win32" else linux_info.get("title", "")
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
        else:
            proc = linux_info.get("process", "")
            if proc:
                readings.append(SensorReading("app.process", "App", proc, "", "system"))
            window_class = linux_info.get("class", "")
            if window_class:
                readings.append(
                    SensorReading("app.window_class", "App Class", window_class, "", "system")
                )
            pid = linux_info.get("pid", "")
            if pid:
                readings.append(SensorReading("app.pid", "App PID", pid, "", "system"))

        return readings
