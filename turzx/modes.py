"""
turzx/modes.py — Display mode controller (static / rotative / reactive)
========================================================================
ModeController lives on the main Qt thread and uses QTimers to
auto-switch layouts.  The render thread already polls
``config.active_layout`` every tick, so no render-thread changes needed.

Modes:
  - **static**: user picks one layout, it stays forever (default behavior).
  - **rotative**: cycle through selected layouts on a timer.
  - **reactive**: switch layout based on the foreground application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QTimer, Signal

if TYPE_CHECKING:
    from .config import ConfigManager


class ModeController(QObject):
    """Automatically switches the active layout based on the current mode."""

    layout_switched = Signal(str)  # emitted with the new layout name

    def __init__(self, config: ConfigManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._sensor_source: Callable[[], dict] | None = None
        self._paused = False

        # Rotative state
        self._rotate_idx = 0
        self._rotate_timer = QTimer(self)
        self._rotate_timer.timeout.connect(self._on_rotate)

        # Reactive state
        self._react_timer = QTimer(self)
        self._react_timer.timeout.connect(self._on_react)

    # ── Public API ──

    def set_sensor_source(self, fn: Callable[[], dict]) -> None:
        """Set callback that returns cached sensor values dict."""
        self._sensor_source = fn

    def start(self) -> None:
        """Start timers according to current mode config."""
        self._apply_mode()

    def stop(self) -> None:
        """Stop all timers."""
        self._rotate_timer.stop()
        self._react_timer.stop()

    def pause(self) -> None:
        """Temporarily suspend auto-switching (e.g. while editor is dirty)."""
        self._paused = True
        self._rotate_timer.stop()
        self._react_timer.stop()

    def resume(self) -> None:
        """Resume auto-switching after a pause."""
        self._paused = False
        self._apply_mode()

    def reload(self) -> None:
        """Re-read mode config and restart timers."""
        self.stop()
        self._apply_mode()

    # ── Internal ──

    def _apply_mode(self) -> None:
        """Start the correct timer(s) for the active mode."""
        if self._paused:
            return

        self._rotate_timer.stop()
        self._react_timer.stop()

        mc = self._config.mode_config

        if mc.mode == "rotative":
            interval_ms = max(mc.rotative.interval, 5) * 1000
            self._rotate_timer.start(interval_ms)
        elif mc.mode == "reactive":
            self._react_timer.start(1000)

    def _on_rotate(self) -> None:
        """Advance to the next layout in the rotation list."""
        mc = self._config.mode_config
        available = self._config.list_layouts()
        # Filter rotation list to only existing layouts
        pool = [name for name in mc.rotative.layouts if name in available]
        if not pool:
            return

        self._rotate_idx = self._rotate_idx % len(pool)
        target = pool[self._rotate_idx]
        self._rotate_idx = (self._rotate_idx + 1) % len(pool)

        if target != self._config.active_name:
            self._config.set_active(target)
            self.layout_switched.emit(target)

    def _on_react(self) -> None:
        """Check foreground app and switch layout if a rule matches."""
        mc = self._config.mode_config
        if not mc.reactive.rules:
            return

        process = self._get_foreground_process()
        if not process:
            return

        proc_lower = process.lower()
        for rule in mc.reactive.rules:
            if rule.process.lower() == proc_lower:
                if rule.layout != self._config.active_name:
                    available = self._config.list_layouts()
                    if rule.layout in available:
                        self._config.set_active(rule.layout)
                        self.layout_switched.emit(rule.layout)
                return

        # No rule matched — use fallback
        fallback = mc.reactive.fallback_layout
        if fallback != self._config.active_name:
            available = self._config.list_layouts()
            if fallback in available:
                self._config.set_active(fallback)
                self.layout_switched.emit(fallback)

    def _get_foreground_process(self) -> str:
        """Read foreground process name from cached sensor values."""
        if self._sensor_source is None:
            return ""
        try:
            values = self._sensor_source()
            reading = values.get("app.process")
            if reading is not None:
                return str(reading.value)
        except Exception:
            pass
        return ""
