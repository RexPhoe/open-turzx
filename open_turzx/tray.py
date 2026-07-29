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

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .i18n import _

_ASSETS_DIR = Path(__file__).parent / "assets" / "tray"

if TYPE_CHECKING:
    from .daemon import TurzxDaemon


def _make_icon() -> QIcon:
    """Load the Open-Turzx tray icon from the bundled brand assets.

    Two variants ship, swapped by pixel size:
      - "simple" (flat navy circle + bold "OT", no fine detail): used for
        16/20px, the sizes most desktop panels actually request for tray
        icons. The full brand mark's thin strokes/glow turn to mush there.
      - "full" (the approved brand mark: OT monogram + sensor-wave motif):
        used from 24px up, where it still reads correctly.

    Bundled as static PNGs rather than drawn via QPainter, because the
    full mark's soft glow/gradient isn't practical to reproduce
    procedurally. Qt picks whichever size best matches what the panel/DPI
    actually requests.
    """
    icon = QIcon()

    for size in (16, 20):
        path = _ASSETS_DIR / f"icon_simple_{size}.png"
        icon.addFile(str(path), QSize(size, size))

    for size in (24, 32, 48, 64, 128):
        path = _ASSETS_DIR / f"icon_full_{size}.png"
        icon.addFile(str(path), QSize(size, size))

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
