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

import os
import sys
import threading
import time
import traceback

from PySide6.QtCore import QThread, Signal, QObject, QTimer
from PySide6.QtWidgets import QApplication

from .config import ConfigManager
from .device import TurzxDevice
from .images import to_jpeg
from .modes import ModeController
from .renderer import Renderer
from .sensors.base import SensorManager
from .transitions import apply as apply_transition, resolve as resolve_transition
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

    **Transitions**: when the active layout name changes (rotative/reactive
    mode switch), the thread blends the old frame into the new one over a
    configurable duration using the selected transition effect.
    """

    error_occurred = Signal(str)

    def __init__(self, daemon: TurzxDaemon) -> None:
        super().__init__()
        self.daemon = daemon
        self._running = True
        self._cached_values: dict = {}

        # Transition state
        self._last_layout_name: str = ""
        self._transition_old_frame = None  # PIL Image
        self._transition_start: float = 0.0
        self._transition_duration: float = 0.0
        self._transition_type: str = "none"

    def run(self) -> None:
        # Prime sensor cache and build initial overlay
        self._cached_values = self.daemon.sensors.read_all()
        layout = self.daemon.config.active_layout
        self._last_layout_name = self.daemon.config.active_name
        self.daemon.renderer.update_overlay(layout, self._cached_values)

        # Sensor updates run in a dedicated thread so they never block
        # the video pipeline — even if read_all() takes 50 ms, the render
        # loop keeps sending frames at full frame rate.
        sensor_thread = threading.Thread(
            target=self._sensor_loop, daemon=True, name="turzx-sensors"
        )
        sensor_thread.start()

        while self._running:
            frame_start = time.monotonic()
            try:
                self._tick()
            except Exception as e:
                self.error_occurred.emit(str(e))
                time.sleep(2)

            # Sleep only the time remaining before the next frame deadline
            fps = self.daemon.config.active_layout.screen_fps
            frame_budget_ms = 1000 / max(fps, 1)
            elapsed_ms = (time.monotonic() - frame_start) * 1000
            sleep_ms = max(0, frame_budget_ms - elapsed_ms)
            self.msleep(int(sleep_ms))

    def _sensor_loop(self) -> None:
        """Dedicated thread: poll sensors and rebuild overlay at refresh_rate.

        Runs independently of the render loop so a slow sensor read (50 ms+)
        never causes a dropped video frame.
        """
        while self._running:
            interval = max(self.daemon.config.active_layout.refresh_rate, 0.1)
            time.sleep(interval)
            if not self._running:
                break
            try:
                self._cached_values = self.daemon.sensors.read_all()
                layout = self.daemon.config.active_layout
                self.daemon.renderer.update_overlay(layout, self._cached_values)
            except Exception:
                pass

    def _tick(self) -> None:
        layout = self.daemon.config.active_layout
        current_name = self.daemon.config.active_name
        now = time.monotonic()

        # Detect layout switch → start transition and force overlay rebuild
        if current_name != self._last_layout_name:
            self._start_transition(now)
            self._last_layout_name = current_name
            self.daemon.renderer.update_overlay(layout, self._cached_values)

        # Video pipeline: compose frame as PIL Image
        new_frame = self.daemon.renderer._compose_frame(layout)

        # Apply transition blending if active
        if self._transition_old_frame is not None:
            elapsed = now - self._transition_start
            duration = max(self._transition_duration, 0.1)
            progress = min(elapsed / duration, 1.0)
            if progress >= 1.0:
                # Transition complete
                self._transition_old_frame = None
            else:
                new_frame = apply_transition(
                    self._transition_old_frame,
                    new_frame,
                    progress,
                    self._transition_type,
                )

        # Encode to JPEG
        jpeg = to_jpeg(
            new_frame,
            self.daemon.renderer.width,
            self.daemon.renderer.height,
            rotate=layout.rotation,
        )

        # Cache the frame for next transition
        self._last_frame = new_frame

        dev = self.daemon.device
        if dev is None:
            return

        try:
            dev.prepare()
            dev.send_frame(jpeg)
        except Exception:
            # Device disconnected or error — try to reconnect
            self.daemon.reconnect_device()

    def _start_transition(self, now: float) -> None:
        """Capture old frame and read transition settings from mode config."""
        old = getattr(self, "_last_frame", None)
        if old is None:
            return
        mc = self.daemon.config.mode_config
        if mc.mode == "rotative":
            self._transition_type = mc.rotative.transition
            self._transition_duration = mc.rotative.transition_duration
        elif mc.mode == "reactive":
            self._transition_type = mc.reactive.transition
            self._transition_duration = mc.reactive.transition_duration
        else:
            return
        if self._transition_type == "none":
            return
        self._transition_type = resolve_transition(self._transition_type)
        self._transition_old_frame = old.copy()
        self._transition_start = now

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
        
        # Tray is only available if a display server is present
        self._headless = (
            sys.platform in ("linux", "linux2")
            and not os.environ.get("DISPLAY")
            and not os.environ.get("WAYLAND_DISPLAY")
        )
        self.tray = TurzxTray(self) if not self._headless else None

    @property
    def is_running(self) -> bool:
        return self._render_thread is not None and self._render_thread.isRunning()

    # ── Lifecycle ──

    def start(self) -> None:
        """Show tray, connect device, begin rendering."""
        if self.tray:
            self.tray.show()
        else:
            print("[TURZX] Running in headless mode (no display server detected)")
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
            msg = "Device connected"
            print(f"[TURZX] {msg}")
            if self.tray:
                self.tray.showMessage("TURZX", msg, self.tray.icon())
        except Exception as e:
            self.device = None
            msg = f"Device not found: {e}"
            print(f"[TURZX] {msg}")
            if self.tray:
                self.tray.showMessage("TURZX", msg, self.tray.icon())

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
        try:
            from .ui.main_window import ConfigWindow

            if self._settings_window is None:
                self._settings_window = ConfigWindow(self)
            self._settings_window.show()
            self._settings_window.raise_()
            self._settings_window.activateWindow()
        except Exception as exc:
            import traceback
            print(f"[TURZX] Error opening settings: {exc}", file=sys.stderr)
            traceback.print_exc()
            if self.tray:
                self.tray.showMessage(
                    "TURZX", f"Error opening settings: {exc}", self.tray.icon()
                )


# ── Entry point ──


def main() -> None:
    # Linux: Detect if running with a display server or headless
    # Use offscreen platform if no display is available
    if sys.platform == "linux" or sys.platform == "linux2":
        has_display = bool(os.environ.get("DISPLAY")) or bool(
            os.environ.get("WAYLAND_DISPLAY")
        )
        if not has_display:
            # Try to use offscreen platform for headless operation
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("TURZX")
    app.setApplicationDisplayName("TURZX Monitor")

    daemon = TurzxDaemon()
    daemon.start()

    if "--settings" in sys.argv:
        QTimer.singleShot(0, daemon.show_settings)

    sys.exit(app.exec())
