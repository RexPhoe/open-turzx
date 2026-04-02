"""
TURZX — Dashboard and driver for the TURZX 2.8" USB screen.

A system tray daemon that displays sensor data, custom layouts,
and (future) dynamic content on the 480x480 USB display.
"""

__version__ = "1.0.0"

from .protocol import Response, VID, PID
from .device import TurzxDevice
from .images import solid, test_pattern, from_file, to_jpeg

__all__ = [
    "TurzxDevice",
    "Response",
    "solid",
    "test_pattern",
    "from_file",
    "to_jpeg",
    "__version__",
]
