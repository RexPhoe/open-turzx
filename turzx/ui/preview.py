"""
turzx/ui/preview.py — Live screen preview widget
=================================================
Shows the rendered output exactly as it appears on the device.
Applies a circular mask to simulate the round 2.8" screen shape.
"""

from __future__ import annotations

import io

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import (
    QImage,
    QPixmap,
    QTransform,
    QPainter,
    QPainterPath,
    QBrush,
    QColor,
    QPen,
)
from PySide6.QtWidgets import QWidget


class PreviewWidget(QWidget):
    """Displays a correctly-oriented preview with circular mask."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(160, 160)
        self.setMaximumHeight(260)
        self._pixmap: QPixmap | None = None

    def update_from_pil(self, pil_image) -> None:
        """Update from a PIL Image (already in correct orientation)."""
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
        buf = io.BytesIO()
        pil_image.save(buf, format="JPEG", quality=85)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue(), "JPEG")
        self._pixmap = pixmap
        self.update()

    def update_from_jpeg(self, jpeg_bytes: bytes) -> None:
        """Update from device JPEG bytes (rotated), compensating rotation."""
        qimg = QImage.fromData(jpeg_bytes, "JPEG")
        if qimg.isNull():
            return
        qimg = qimg.transformed(QTransform().rotate(180))
        self._pixmap = QPixmap.fromImage(qimg)
        self.update()

    def paintEvent(self, event) -> None:
        """Draw the preview image clipped to a circle with a border ring."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Compute the largest square that fits centered in the widget
        side = min(self.width(), self.height()) - 4  # 2px margin each side
        x = (self.width() - side) // 2
        y = (self.height() - side) // 2
        rect = QRect(x, y, side, side)

        # Dark background behind the circle
        painter.fillRect(self.rect(), QColor(17, 17, 17))

        # Clip to circle
        path = QPainterPath()
        path.addEllipse(rect.x(), rect.y(), rect.width(), rect.height())
        painter.setClipPath(path)

        if self._pixmap:
            scaled = self._pixmap.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Center the scaled pixmap within the square
            px = rect.x() + (rect.width() - scaled.width()) // 2
            py = rect.y() + (rect.height() - scaled.height()) // 2
            painter.drawPixmap(px, py, scaled)
        else:
            painter.fillRect(rect, QColor(30, 30, 40))

        # Remove clip to draw border ring
        painter.setClipping(False)

        # Draw circular border
        pen = QPen(QColor(60, 60, 70), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        painter.end()
