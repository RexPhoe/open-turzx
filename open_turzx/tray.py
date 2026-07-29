"""
open_turzx/tray.py — System tray icon and context menu (PySide6)
===========================================================
Provides the always-visible tray icon with:
  - Start / Pause toggle
  - Settings (opens config window)
  - Quit
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter, QFont
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .i18n import _

if TYPE_CHECKING:
    from .daemon import TurzxDaemon


def _make_icon() -> QIcon:
    """Generate the Open-Turzx tray icon programmatically (brand mark: "OT" monogram).

    Drawn vectorially at a few sizes so Qt always has a crisp pixmap to pick
    from regardless of panel DPI/scale, instead of shipping a bundled raster
    asset. Kept deliberately simple (flat circle + bold two-letter mark, no
    fine detail) because system tray icons typically render at 16-24px,
    where thin strokes/glows/gradients turn to mush.
    """
    icon = QIcon()
    # Brand palette (matches the social/avatar mark): dark navy badge,
    # muted light-blue "OT" monogram.
    bg_color = QColor(23, 36, 52)
    outline_color = QColor(17, 26, 39)
    text_color = QColor(127, 158, 200)

    for size in (64, 32, 24, 16):
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = max(1, size // 32)
        painter.setBrush(bg_color)
        painter.setPen(outline_color)
        painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)

        painter.setPen(text_color)
        font = QFont("Arial", max(6, int(size * 0.40)), QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "OT")
        painter.end()

        icon.addPixmap(pixmap)

    return icon


class TurzxTray(QSystemTrayIcon):
    def __init__(self, daemon: TurzxDaemon) -> None:
        super().__init__()
        self.daemon = daemon
        self.setIcon(_make_icon())
        self.setToolTip(_("Open-Turzx"))
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()
        # Keep references to prevent garbage collection (PySide6 quirk)
        self._menu = menu

        self._action_toggle = QAction(_("Pause"), menu)
        self._action_toggle.triggered.connect(self._toggle_render)
        menu.addAction(self._action_toggle)

        self._action_pause_mode = QAction(_("Pause Mode"), menu)
        self._action_pause_mode.triggered.connect(self._toggle_mode_pause)
        self._action_pause_mode.setVisible(False)
        menu.addAction(self._action_pause_mode)

        menu.addSeparator()

        self._action_settings = QAction(_("Settings"), menu)
        self._action_settings.triggered.connect(self._open_settings)
        menu.addAction(self._action_settings)

        menu.addSeparator()

        self._action_quit = QAction(_("Quit"), menu)
        self._action_quit.triggered.connect(self._quit)
        menu.addAction(self._action_quit)

        self.setContextMenu(menu)

        # Listen for mode switches to update tooltip
        self.daemon.mode_controller.layout_switched.connect(self._update_mode_tooltip)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.MiddleClick,
        ):
            self._open_settings()

    def _toggle_render(self) -> None:
        if self.daemon.is_running:
            self.daemon.stop_render()
            self._action_toggle.setText(_("Start"))
            self.setToolTip(_("Open-Turzx (paused)"))
        else:
            self.daemon.start_render()
            self._action_toggle.setText(_("Pause"))
            self._update_mode_tooltip()

    def _toggle_mode_pause(self) -> None:
        mc = self.daemon.mode_controller
        if mc._paused:
            mc.resume()
            self._action_pause_mode.setText(_("Pause Mode"))
        else:
            mc.pause()
            self._action_pause_mode.setText(_("Resume Mode"))
        self._update_mode_tooltip()

    def _update_mode_tooltip(self, _name: str = "") -> None:
        """Update tooltip to reflect current mode."""
        mode = self.daemon.config.mode_config.mode
        mode_labels = {"static": "Static", "rotative": "Rotative", "reactive": "Reactive"}
        label = mode_labels.get(mode, mode.capitalize())
        is_non_static = mode != "static"
        self._action_pause_mode.setVisible(is_non_static)
        self.setToolTip(f"Open-Turzx ({label})")

    def _open_settings(self) -> None:
        self.daemon.show_settings()

    def _quit(self) -> None:
        self.daemon.shutdown()
