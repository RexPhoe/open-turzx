"""
turzx/autostart.py — Cross-platform autostart management
=========================================================
Manages running TURZX at system startup.

Linux:   XDG Autostart spec — creates/removes ~/.config/autostart/turzx.desktop
Windows: Registry Run key — adds/removes HKCU/.../Run entry
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _autostart_dir() -> Path:
    """Return the platform-specific autostart directory."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    else:
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"


def _desktop_path() -> Path:
    """Return the full path to the autostart desktop entry."""
    return _autostart_dir() / "turzx.desktop"


def _exec_command() -> str:
    """Determine the best command to launch TURZX."""
    # Prefer the module approach (works for both pip-installed and source)
    # Use sys.executable to match the current Python
    return f"{sys.executable} -m turzx"


def is_enabled() -> bool:
    """Check if TURZX is set to run at startup."""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, "TURZX")
                return bool(value)
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False
    else:
        return _desktop_path().exists()


def enable() -> bool:
    """Enable TURZX to run at system startup. Returns True on success."""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            try:
                winreg.SetValueEx(key, "TURZX", 0, winreg.REG_SZ, _exec_command())
                return True
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False
    else:
        return _create_linux_desktop_entry()


def disable() -> bool:
    """Disable TURZX from running at system startup. Returns True on success."""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, "TURZX")
                return True
            except FileNotFoundError:
                return True  # already removed
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False
    else:
        try:
            path = _desktop_path()
            if path.exists():
                path.unlink()
            return True
        except Exception:
            return False


def _create_linux_desktop_entry() -> bool:
    """Create a .desktop file for XDG autostart."""
    try:
        autostart_dir = _autostart_dir()
        autostart_dir.mkdir(parents=True, exist_ok=True)

        desktop_content = f"""[Desktop Entry]
Type=Application
Name=TURZX Monitor
Comment=TURZX 2.8" USB Screen Monitor
Exec={_exec_command()}
StartupNotify=false
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"""

        desktop_path = _desktop_path()
        desktop_path.write_text(desktop_content, encoding="utf-8")
        desktop_path.chmod(0o755)
        return True
    except Exception:
        return False
