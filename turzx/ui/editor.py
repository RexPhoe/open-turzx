"""
turzx/ui/editor.py — Visual drag-and-drop layout editor
========================================================
QGraphicsScene-based editor where users can add, drag, and
configure elements on a 480x480 canvas.
"""

from __future__ import annotations

import copy
import sys

from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPen,
    QBrush,
    QPainter,
    QPixmap,
    QImage,
)
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
    QLabel,
    QSplitter,
)

from ..config import Layout, LayoutElement, Background
from ..protocol import SCREEN_W, SCREEN_H


def _log(msg: str) -> None:
    """Debug log for video pipeline — prints to stderr."""
    print(f"[TURZX video] {msg}", file=sys.stderr, flush=True)


# ── Draggable element ─────────────────────────────────────────


class ElementItem(QGraphicsItem):
    """Draggable visual representation of a LayoutElement."""

    def __init__(self, element: LayoutElement) -> None:
        super().__init__()
        self.element = element
        self._text_rect = QRectF()
        self._bounds = QRectF(0, 0, 80, 24)
        self._pixmap: QPixmap | None = None

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.refresh()

    # ── helpers ──

    def _font(self) -> QFont:
        f = QFont()
        f.setPixelSize(max(self.element.font_size, 8))
        return f

    def display_text(self) -> str:
        if self.element.type == "text":
            return self.element.text or "(text)"
        if self.element.type == "sensor":
            try:
                return self.element.format.format(
                    label=self.element.label or self.element.sensor_id,
                    value=42.0,
                    unit="%",
                )
            except (KeyError, ValueError, IndexError):
                return f"{self.element.label or self.element.sensor_id}: --"
        return ""

    # ── geometry ──

    def refresh(self) -> None:
        """Recalculate geometry after property changes."""
        self.prepareGeometryChange()

        if self.element.type in ("text", "sensor"):
            fm = QFontMetricsF(self._font())
            text = self.display_text()
            tw, th = fm.horizontalAdvance(text), fm.height()

            anchor = self.element.anchor or "lt"
            ha = anchor[0] if len(anchor) >= 1 else "l"
            va = anchor[1] if len(anchor) >= 2 else "t"
            dx = {"l": 0.0, "m": -tw / 2, "r": -tw}.get(ha, 0.0)
            dy = {"t": 0.0, "m": -th / 2, "b": -th, "a": -th}.get(va, 0.0)

            self._text_rect = QRectF(dx, dy, tw, th)
            self._bounds = self._text_rect.adjusted(-4, -4, 4, 4)

        elif self.element.type == "image":
            path = self.element.text
            self._pixmap = QPixmap(path) if path else None
            if self._pixmap and not self._pixmap.isNull():
                w = self.element.w or min(self._pixmap.width(), SCREEN_W)
                h = self.element.h or min(self._pixmap.height(), SCREEN_H)
            else:
                w, h = 80, 80
            self._bounds = QRectF(0, 0, w, h)

        elif self.element.type == "shape":
            w = self.element.w or 80
            h = self.element.h or 60
            self._bounds = QRectF(0, 0, w, h)

        elif self.element.type == "bar":
            w = self.element.w or 120
            h = self.element.h or self.element.bar_thickness or 12
            self._bounds = QRectF(0, 0, w, h)

        elif self.element.type == "arc_bar":
            w = self.element.w or 80
            h = self.element.h or 80
            self._bounds = QRectF(0, 0, w, h)

        # Sync movable flag and cursor based on lock state
        locked = getattr(self.element, "locked", False)
        flags = (
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        if not locked:
            flags |= QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        self.setFlags(flags)
        self.setCursor(
            Qt.CursorShape.ForbiddenCursor if locked
            else Qt.CursorShape.SizeAllCursor
        )

        self.setPos(self.element.x, self.element.y)
        self.setZValue(self.element.z)
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    # ── painting ──

    def paint(self, painter: QPainter, option, widget=None) -> None:
        # Real-render mode: the rendered bitmap shows all content.
        # Only draw the selection indicator.
        if self.isSelected():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            locked = getattr(self.element, "locked", False)
            color = QColor(255, 80, 80) if locked else QColor(0, 170, 255)
            painter.setPen(QPen(color, 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 25)))
            painter.drawRect(self._bounds)

    # ── interaction ──

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if getattr(self.element, "locked", False):
                return self.pos()
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.element.x = int(value.x())
            self.element.y = int(value.y())
        return super().itemChange(change, value)


# ── cv2 frame → QPixmap helper ────────────────────────────────


def _cv2_frame_to_pixmap(frame) -> QPixmap | None:
    """Convert a BGR cv2 numpy frame to QPixmap safely.

    The key issue: QImage wraps external memory (frame.data).
    If frame is freed before QImage is used, we get garbage or crash.
    Solution: copy the numpy bytes first, then create QImage from the copy.
    """
    try:
        import cv2

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = frame.shape
        # Make a contiguous copy of the bytes — this is critical
        data = bytes(frame.data)
        qimg = QImage(data, w, h, ch * w, QImage.Format.Format_RGB888)
        # .copy() creates a deep copy that owns its own pixel data
        pm = QPixmap.fromImage(qimg.copy())
        return pm if not pm.isNull() else None
    except Exception as e:
        _log(f"frame_to_pixmap error: {e}")
        return None


def _pil_to_qpixmap(pil_image) -> QPixmap:
    """Convert a PIL Image (RGB/RGBA) to QPixmap without JPEG roundtrip."""
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")
    data = pil_image.tobytes("raw", "BGRA")
    qimg = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_ARGB32)
    return QPixmap.fromImage(qimg.copy())


# ── Video background player ───────────────────────────────────


class _VideoBgPlayer:
    """Manages cv2 video playback for the editor canvas background.

    Keeps the VideoCapture open and reads one frame per tick.
    Loops back to start when reaching EOF.
    """

    def __init__(self) -> None:
        self._cap = None
        self._path: str | None = None
        self._fps: float = 24.0
        self._ok = False

    @property
    def is_open(self) -> bool:
        return self._ok and self._cap is not None

    @property
    def fps(self) -> float:
        return self._fps

    def open(self, path: str) -> bool:
        """Open a video file. Returns True on success."""
        try:
            import cv2
        except ImportError:
            _log("cv2 not installed")
            return False

        norm = path.replace("\\", "/")
        # If already open on same file, keep it
        if self._path == norm and self._cap is not None:
            if self._cap.isOpened():
                return True
            # Cap died, reopen below

        self.close()
        try:
            cap = cv2.VideoCapture(norm)
            if not cap.isOpened():
                _log(f"VideoCapture failed to open: {norm}")
                return False
            self._cap = cap
            self._path = norm
            self._fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            self._ok = True
            _log(f"Opened video: {norm} ({self._fps:.0f} FPS)")
            return True
        except Exception as e:
            _log(f"open error: {e}")
            return False

    def next_frame_pixmap(self) -> QPixmap | None:
        """Read next frame, loop on EOF, return as QPixmap."""
        if not self._ok or self._cap is None:
            return None
        try:
            import cv2

            ret, frame = self._cap.read()
            if not ret:
                # Loop — try seek first
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self._cap.read()
            if not ret:
                # Seek failed (H.265, VP9, etc.) — reopen from scratch
                self._cap.release()
                self._cap = cv2.VideoCapture(self._path)
                if self._cap.isOpened():
                    ret, frame = self._cap.read()
                else:
                    self._ok = False
            if not ret:
                _log("Failed to read frame even after reopen")
                return None
            return _cv2_frame_to_pixmap(frame)
        except Exception as e:
            _log(f"next_frame error: {e}")
            return None

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        self._cap = None
        self._path = None
        self._ok = False


# ── Scene ──────────────────────────────────────────────────────


class EditorScene(QGraphicsScene):
    """480x480 canvas that holds background + draggable elements."""

    element_selected = Signal(object)  # LayoutElement | None
    layout_modified = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSceneRect(0, 0, SCREEN_W, SCREEN_H)
        self._layout: Layout | None = None
        self._bg_item: QGraphicsPixmapItem | None = None
        self._render_bg: QGraphicsPixmapItem | None = None
        self._items: list[ElementItem] = []

        # Video background player + timer
        self._video_player = _VideoBgPlayer()
        self._video_timer = QTimer()
        self._video_timer.timeout.connect(self._tick_video)

        self.setBackgroundBrush(QBrush(QColor(15, 15, 25)))
        self.selectionChanged.connect(self._on_selection)

    # ── layout management ──

    def load_layout(self, layout: Layout) -> None:
        # Stop video before clearing
        self._video_timer.stop()
        self._video_player.close()

        self._layout = layout
        self.clear()
        self._items.clear()
        self._bg_item = None
        self._render_bg = None

        self._apply_background()
        for el in layout.elements:
            self._mk(el)

    @property
    def current_layout(self) -> Layout | None:
        return self._layout

    def _mk(self, el: LayoutElement) -> ElementItem:
        item = ElementItem(el)
        self.addItem(item)
        self._items.append(item)
        return item

    def add_element(self, el: LayoutElement) -> ElementItem:
        if self._layout:
            self._layout.elements.append(el)
        item = self._mk(el)
        self.clearSelection()
        item.setSelected(True)
        self.layout_modified.emit()
        return item

    def remove_selected(self) -> None:
        for item in list(self.selectedItems()):
            if isinstance(item, ElementItem):
                if self._layout and item.element in self._layout.elements:
                    self._layout.elements.remove(item.element)
                if item in self._items:
                    self._items.remove(item)
                self.removeItem(item)
        self.element_selected.emit(None)
        self.layout_modified.emit()

    def duplicate_selected(self) -> None:
        for item in list(self.selectedItems()):
            if isinstance(item, ElementItem):
                new_el = copy.deepcopy(item.element)
                new_el.x += 20
                new_el.y += 20
                self.add_element(new_el)

    # ── background ──

    def _apply_background(self) -> None:
        if not self._layout:
            return
        bg = self._layout.background

        # Remove old background item if present
        if self._bg_item is not None:
            self.removeItem(self._bg_item)
            self._bg_item = None

        # Stop video playback
        self._video_timer.stop()
        self._video_player.close()

        if bg.type == "image" and bg.path:
            pm = QPixmap(bg.path)
            if not pm.isNull():
                pm = pm.scaled(
                    SCREEN_W,
                    SCREEN_H,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._bg_item = QGraphicsPixmapItem(pm)
                self._bg_item.setZValue(-10000)
                self.addItem(self._bg_item)
                self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
            else:
                _log(f"QPixmap failed to load image: {bg.path}")
                self.setBackgroundBrush(QBrush(QColor(*bg.color)))

        elif bg.type == "video" and bg.path:
            _log(f"Applying video background: {bg.path}")
            if self._video_player.open(bg.path):
                # Read first frame to show immediately
                pm = self._video_player.next_frame_pixmap()
                if pm is not None:
                    pm = pm.scaled(
                        SCREEN_W,
                        SCREEN_H,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    self._bg_item = QGraphicsPixmapItem(pm)
                    self._bg_item.setZValue(-10000)
                    self.addItem(self._bg_item)
                    self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
                    _log(f"First frame OK: {pm.width()}x{pm.height()}")
                else:
                    _log("First frame returned None")
                    self.setBackgroundBrush(QBrush(QColor(*bg.color)))

                # Start playback timer — cap at ~15 FPS for editor
                interval = max(66, int(1000 / self._video_player.fps))
                self._video_timer.start(interval)
                _log(f"Video timer started: {interval}ms interval")
            else:
                _log("Video player failed to open, falling back to solid color")
                self.setBackgroundBrush(QBrush(QColor(*bg.color)))
        else:
            # Solid color or unknown type
            self.setBackgroundBrush(QBrush(QColor(*bg.color)))

    def _tick_video(self) -> None:
        """Timer callback: advance one video frame on the canvas."""
        if not self._video_player.is_open:
            self._video_timer.stop()
            return

        pm = self._video_player.next_frame_pixmap()
        if pm is None:
            return

        pm = pm.scaled(
            SCREEN_W,
            SCREEN_H,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        if self._bg_item is not None:
            self._bg_item.setPixmap(pm)
        else:
            self._bg_item = QGraphicsPixmapItem(pm)
            self._bg_item.setZValue(-10000)
            self.addItem(self._bg_item)

    def set_background(self, bg: Background) -> None:
        if self._layout:
            self._layout.background = bg
            self._apply_background()
            self.layout_modified.emit()

    def update_render_pixmap(self, pixmap: QPixmap) -> None:
        """Replace the full-scene rendered bitmap (from Renderer)."""
        if self._render_bg is None:
            self._render_bg = QGraphicsPixmapItem(pixmap)
            self._render_bg.setZValue(-9999)
            self.addItem(self._render_bg)
        else:
            self._render_bg.setPixmap(pixmap)

    # ── refresh ──

    def refresh_all(self) -> None:
        for item in self._items:
            item.refresh()

    def refresh_item(self, element) -> None:
        for item in self._items:
            if item.element is element:
                item.refresh()
                return

    # ── selection ──

    def _on_selection(self) -> None:
        sel = [i for i in self.selectedItems() if isinstance(i, ElementItem)]
        self.element_selected.emit(sel[0].element if sel else None)

    def select_element(self, element: LayoutElement | None) -> None:
        """Select a specific element programmatically (from element list panel)."""
        self.blockSignals(True)
        self.clearSelection()
        if element is not None:
            for item in self._items:
                if item.element is element:
                    item.setSelected(True)
                    break
        self.blockSignals(False)
        self.element_selected.emit(element)

    def get_elements(self) -> list[LayoutElement]:
        """Return current element list in z-order."""
        if self._layout:
            return list(sorted(self._layout.elements, key=lambda e: e.z))
        return []

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected()
        else:
            super().keyPressEvent(event)


# ── View ───────────────────────────────────────────────────────


class LayoutCanvas(QGraphicsView):
    """Zoomable view for the editor scene."""

    def __init__(self, scene: EditorScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMinimumSize(300, 300)
        self.setStyleSheet("border: 1px solid #444;")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        # Re-sync properties panel with current position after drag
        scene = self.scene()
        if isinstance(scene, EditorScene):
            sel = [i for i in scene.selectedItems() if isinstance(i, ElementItem)]
            if sel:
                scene.element_selected.emit(sel[0].element)
                scene.layout_modified.emit()


# ── Element list panel ─────────────────────────────────────────


def _element_display_name(el: LayoutElement) -> str:
    """Return a short display name for an element in the list."""
    if el.type == "text":
        txt = el.text or "(text)"
        return f"Text: {txt[:20]}"
    elif el.type == "sensor":
        return f"Sensor: {el.sensor_id}"
    elif el.type == "image":
        name = el.text.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] if el.text else "(image)"
        return f"Image: {name[:20]}"
    elif el.type == "shape":
        return f"Shape: {el.shape}"
    elif el.type == "bar":
        return f"Bar: {el.sensor_id}"
    elif el.type == "arc_bar":
        return f"Arc: {el.sensor_id}"
    return el.type


class ElementListPanel(QWidget):
    """Panel listing all elements for easy selection regardless of Z-order."""

    def __init__(self, scene: EditorScene, parent=None) -> None:
        super().__init__(parent)
        self._scene = scene
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        lbl = QLabel("Elements")
        lbl.setStyleSheet("font-weight: bold; padding: 2px 4px;")
        layout.addWidget(lbl)

        self._list = QListWidget()
        self._list.setMaximumHeight(180)
        layout.addWidget(self._list)

        # Connect signals
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemChanged.connect(self._on_item_changed)
        scene.element_selected.connect(self._on_scene_selection)
        scene.layout_modified.connect(self.refresh)

    def refresh(self) -> None:
        """Rebuild the list from the scene's current elements."""
        self._updating = True
        current_el = None
        # Remember current selection
        row = self._list.currentRow()
        elements = self._scene.get_elements()
        if 0 <= row < len(elements):
            current_el = elements[row]

        self._list.clear()
        elements = self._scene.get_elements()
        new_row = -1
        for i, el in enumerate(elements):
            name = _element_display_name(el)
            locked = getattr(el, "locked", False)
            lock_icon = "\U0001f512 " if locked else ""
            item = QListWidgetItem(f"[z={el.z}] {lock_icon}{name}")
            item.setData(Qt.ItemDataRole.UserRole, id(el))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if locked else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
            if el is current_el:
                new_row = i

        if new_row >= 0:
            self._list.setCurrentRow(new_row)
        self._updating = False

    def _on_row_changed(self, row: int) -> None:
        """User clicked an element in the list — select it on canvas."""
        if self._updating:
            return
        elements = self._scene.get_elements()
        if 0 <= row < len(elements):
            self._scene.select_element(elements[row])
        else:
            self._scene.select_element(None)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Handle checkbox toggle to lock/unlock an element."""
        if self._updating:
            return
        row = self._list.row(item)
        elements = self._scene.get_elements()
        if 0 <= row < len(elements):
            el = elements[row]
            locked = item.checkState() == Qt.CheckState.Checked
            el.locked = locked
            self._scene.refresh_item(el)
            # Update list text to show/hide lock icon
            self._updating = True
            name = _element_display_name(el)
            lock_icon = "\U0001f512 " if locked else ""
            item.setText(f"[z={el.z}] {lock_icon}{name}")
            self._updating = False
            self._scene.layout_modified.emit()

    def _on_scene_selection(self, element) -> None:
        """Scene selection changed — sync list highlight."""
        if self._updating:
            return
        self._updating = True
        if element is None:
            self._list.setCurrentRow(-1)
        else:
            elements = self._scene.get_elements()
            for i, el in enumerate(elements):
                if el is element:
                    self._list.setCurrentRow(i)
                    break
        self._updating = False
