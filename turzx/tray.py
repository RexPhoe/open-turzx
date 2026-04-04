"""
turzx/tray.py — System tray icon and context menu (PySide6)
===========================================================
Provides the always-visible tray icon with:
  - Start / Pause toggle
  - Settings (opens config window)
  - Quit
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QPainter, QFont
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .i18n import _

if TYPE_CHECKING:
    from .daemon import TurzxDaemon


def _make_icon() -> QIcon:
    """Generate a simple tray icon programmatically."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(0, 180, 255))
    painter.setPen(QColor(0, 120, 200))
    painter.drawRoundedRect(4, 4, size - 8, size - 8, 10, 10)
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(QFont("Arial", 28, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), 0x0084, "T")  # AlignCenter
    painter.end()
    return QIcon(pixmap)


class TurzxTray(QSystemTrayIcon):
    def __init__(self, daemon: TurzxDaemon) -> None:
        super().__init__()
        self.daemon = daemon
        self.setIcon(_make_icon())
        self.setToolTip(_("TURZX Monitor"))
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()
        # Keep references to prevent garbage collection (PySide6 quirk)
        self._menu = menu

        self._action_toggle = QAction(_("Pause"), menu)
        self._action_toggle.triggered.connect(self._toggle_render)
        menu.addAction(self._action_toggle)

        menu.addSeparator()

        self._action_settings = QAction(_("Settings"), menu)
        self._action_settings.triggered.connect(self._open_settings)
        menu.addAction(self._action_settings)

        menu.addSeparator()

        self._action_quit = QAction(_("Quit"), menu)
        self._action_quit.triggered.connect(self._quit)
        menu.addAction(self._action_quit)

        self.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._open_settings()

    def _toggle_render(self) -> None:
        if self.daemon.is_running:
            self.daemon.stop_render()
            self._action_toggle.setText(_("Start"))
            self.setToolTip(_("TURZX Monitor (paused)"))
        else:
            self.daemon.start_render()
            self._action_toggle.setText(_("Pause"))
            self.setToolTip(_("TURZX Monitor"))

    def _open_settings(self) -> None:
        self.daemon.show_settings()

    def _quit(self) -> None:
        self.daemon.shutdown()
