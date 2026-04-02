"""
turzx/ui/main_window.py — Configuration window
===============================================
Phase 1: Shows current layout, sensor list, and refresh rate control.
Phase 2 will add the full visual drag-and-drop editor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QSlider,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QSplitter,
)

if TYPE_CHECKING:
    from ..daemon import TurzxDaemon


class ConfigWindow(QMainWindow):
    def __init__(self, daemon: TurzxDaemon) -> None:
        super().__init__()
        self.daemon = daemon
        self.setWindowTitle("TURZX - Settings")
        self.setMinimumSize(700, 500)
        self._build_ui()
        self._refresh_preview()

        # Live preview timer
        self._preview_timer = QTimer(self)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_timer.start(2000)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # Left panel: controls
        left = QWidget()
        left_layout = QVBoxLayout(left)

        # Layout selector
        layout_group = QGroupBox("Layout")
        layout_vbox = QVBoxLayout(layout_group)
        self._combo_layout = QComboBox()
        self._combo_layout.addItems(self.daemon.config.list_layouts())
        self._combo_layout.currentTextChanged.connect(self._on_layout_changed)
        layout_vbox.addWidget(self._combo_layout)
        left_layout.addWidget(layout_group)

        # Refresh rate
        rate_group = QGroupBox("Refresh Rate")
        rate_vbox = QVBoxLayout(rate_group)
        self._label_rate = QLabel("1.0 FPS")
        self._slider_rate = QSlider(Qt.Orientation.Horizontal)
        self._slider_rate.setRange(1, 50)  # 0.1 to 5.0 FPS (value / 10)
        self._slider_rate.setValue(10)
        self._slider_rate.valueChanged.connect(self._on_rate_changed)
        rate_vbox.addWidget(self._label_rate)
        rate_vbox.addWidget(self._slider_rate)
        left_layout.addWidget(rate_group)

        # Available sensors
        sensors_group = QGroupBox("Available Sensors")
        sensors_vbox = QVBoxLayout(sensors_group)
        self._list_sensors = QListWidget()
        self._populate_sensors()
        sensors_vbox.addWidget(self._list_sensors)
        left_layout.addWidget(sensors_group)

        left_layout.addStretch()
        splitter.addWidget(left)

        # Right panel: preview
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Preview (live)"))
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("background: #111; border: 1px solid #333;")
        self._preview_label.setMinimumSize(300, 300)
        right_layout.addWidget(self._preview_label, stretch=1)
        splitter.addWidget(right)

        splitter.setSizes([300, 400])

    def _populate_sensors(self) -> None:
        self._list_sensors.clear()
        values = self.daemon.sensors.read_all()
        for sid, reading in sorted(values.items()):
            item = QListWidgetItem(f"{sid}  ->  {reading.name}: {reading.value}{reading.unit}")
            self._list_sensors.addItem(item)

    def _on_layout_changed(self, name: str) -> None:
        self.daemon.config.set_active(name)
        self._refresh_preview()

    def _on_rate_changed(self, value: int) -> None:
        rate = value / 10.0
        self._label_rate.setText(f"{rate:.1f} FPS")
        layout = self.daemon.config.active_layout
        layout.refresh_rate = rate

    def _refresh_preview(self) -> None:
        """Render current layout and show as preview."""
        try:
            layout = self.daemon.config.active_layout
            values = self.daemon.sensors.read_all()
            jpeg = self.daemon.renderer.render(layout, values)

            qimg = QImage.fromData(jpeg, "JPEG")
            if not qimg.isNull():
                pixmap = QPixmap.fromImage(qimg)
                scaled = pixmap.scaled(
                    self._preview_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._preview_label.setPixmap(scaled)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        # Just hide, don't destroy — daemon keeps running
        event.ignore()
        self.hide()
