"""
turzx/daemon.py — Main daemon: render loop, device management, tray
====================================================================
Entry point for the application.  Starts the Qt event loop,
shows a tray icon, and runs the render thread that periodically
sends composed frames to the TURZX screen.

Usage:
    python -m turzx
    turzx              (if installed via pip)
"""

from __future__ import annotations

import sys
import time
import traceback

from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtWidgets import QApplication

from .config import ConfigManager
from .device import TurzxDevice
from .modes import ModeController
from .renderer import Renderer
from .sensors.base import SensorManager
from .tray import TurzxTray


# ── Render thread ──


class RenderThread(QThread):
    """Background thread with two independent pipelines:

    1. **Video pipeline** (60 FPS): read next video frame → composite
       cached overlay → JPEG → send to device.  ~5 ms per frame.

    2. **Sensor pipeline** (refresh_rate, e.g. 1 s): poll sensors →
       rebuild the text/element overlay image.  ~50 ms but infrequent.

    The overlay is a transparent RGBA image cached between sensor reads.
    This decoupling lets the video play smoothly at 60 FPS regardless of
    how often the sensor data refreshes.
    """

    error_occurred = Signal(str)

    def __init__(self, daemon: TurzxDaemon) -> None:
        super().__init__()
        self.daemon = daemon
        self._running = True
        self._cached_values: dict = {}
        self._last_sensor_read: float = 0.0

    def run(self) -> None:
        # Prime sensor cache and build initial overlay
        self._cached_values = self.daemon.sensors.read_all()
        self._last_sensor_read = time.monotonic()
        layout = self.daemon.config.active_layout
        self.daemon.renderer.update_overlay(layout, self._cached_values)

        while self._running:
            try:
                self._tick()
            except Exception as e:
                self.error_occurred.emit(str(e))
                time.sleep(2)

            fps = self.daemon.config.active_layout.screen_fps
            self.msleep(int(1000 / max(fps, 1)))

    def _tick(self) -> None:
        layout = self.daemon.config.active_layout
        now = time.monotonic()

        # Sensor pipeline: poll sensors and rebuild overlay at refresh_rate
        sensor_interval = max(layout.refresh_rate, 0.1)
        if now - self._last_sensor_read >= sensor_interval:
            self._cached_values = self.daemon.sensors.read_all()
            self._last_sensor_read = now
            self.daemon.renderer.update_overlay(layout, self._cached_values)

        # Video pipeline: next background frame + cached overlay → JPEG
        jpeg = self.daemon.renderer.render_frame(layout)

        dev = self.daemon.device
        if dev is None:
            return

        try:
            dev.prepare()
            dev.send_frame(jpeg)
        except Exception:
            # Device disconnected or error — try to reconnect
            self.daemon.reconnect_device()

    def stop(self) -> None:
        self._running = False
        self.wait(5000)


# ── Daemon ──


class TurzxDaemon(QObject):
    """Central coordinator: owns device, sensors, config, renderer, tray."""

    def __init__(self) -> None:
        super().__init__()
        self.config = ConfigManager()
        self.sensors = SensorManager()
        self.sensors.register_defaults()
        self.renderer = Renderer()

        self.device: TurzxDevice | None = None
        self._render_thread: RenderThread | None = None
        self._settings_window = None

        self.mode_controller = ModeController(self.config)
        self.tray = TurzxTray(self)

    @property
    def is_running(self) -> bool:
        return self._render_thread is not None and self._render_thread.isRunning()

    # ── Lifecycle ──

    def start(self) -> None:
        """Show tray, connect device, begin rendering."""
        self.tray.show()
        self._connect_device()
        self.start_render()

    def shutdown(self) -> None:
        """Clean stop: render thread, device, then quit Qt."""
        self.stop_render()
        self.renderer.cleanup()
        self._disconnect_device()
        QApplication.instance().quit()

    # ── Device ──

    def _connect_device(self) -> None:
        try:
            dev = TurzxDevice(verbose=False)
            dev.connect()
            dev.init_sequence()
            self.device = dev
            self.tray.showMessage("TURZX", "Device connected", self.tray.icon())
        except Exception as e:
            self.device = None
            self.tray.showMessage("TURZX", f"Device not found: {e}", self.tray.icon())

    def _disconnect_device(self) -> None:
        if self.device:
            try:
                self.device.shutdown()
                self.device.disconnect()
            except Exception:
                pass
            self.device = None

    def reconnect_device(self) -> None:
        """Attempt to reconnect after a failure."""
        self._disconnect_device()
        time.sleep(1)
        self._connect_device()

    # ── Render ──

    def start_render(self) -> None:
        if self.is_running:
            return
        self._render_thread = RenderThread(self)
        self._render_thread.error_occurred.connect(self._on_render_error)
        self._render_thread.start()
        # Start mode controller with access to cached sensor values
        self.mode_controller.set_sensor_source(
            lambda: self._render_thread._cached_values if self._render_thread else {}
        )
        self.mode_controller.start()

    def stop_render(self) -> None:
        self.mode_controller.stop()
        if self._render_thread:
            self._render_thread.stop()
            self._render_thread = None

    def _on_render_error(self, msg: str) -> None:
        print(f"[TURZX] Render error: {msg}", file=sys.stderr)

    # ── Settings window ──

    def show_settings(self) -> None:
        from .ui.main_window import ConfigWindow

        if self._settings_window is None:
            self._settings_window = ConfigWindow(self)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()


# ── Entry point ──


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("TURZX")
    app.setApplicationDisplayName("TURZX Monitor")

    daemon = TurzxDaemon()
    daemon.start()

    sys.exit(app.exec())
