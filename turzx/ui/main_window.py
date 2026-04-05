"""
turzx/ui/main_window.py — Configuration window with visual editor
=================================================================
Integrates the drag-and-drop canvas editor, properties panel,
toolbox, and live preview.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QCheckBox,
    QComboBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QLineEdit,
    QGroupBox,
    QRadioButton,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QColorDialog,
    QFileDialog,
    QScrollArea,
    QInputDialog,
    QMessageBox,
)

from ..config import Layout, LayoutElement, Background, ModeConfig, ReactiveRule, RotativeConfig, ReactiveConfig
from ..protocol import SCREEN_W, SCREEN_H
from ..sensors.units import available_units
from ..sensors.units import available_time_formats, available_date_formats
from ..i18n import _
from .editor import EditorScene, LayoutCanvas, ElementListPanel
from .preview import PreviewWidget

if TYPE_CHECKING:
    from ..daemon import TurzxDaemon


# ── Color button helper ───────────────────────────────────────


class ColorButton(QPushButton):
    """Small swatch that opens QColorDialog on click."""

    color_changed = Signal(list)

    def __init__(self, color=None, parent=None):
        super().__init__(parent)
        self._color = list(color or [255, 255, 255])
        self.setFixedSize(36, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply()
        self.clicked.connect(self._pick)

    def _apply(self):
        r, g, b = self._color[:3]
        self.setStyleSheet(
            f"background:rgb({r},{g},{b}); border:1px solid #888; border-radius:3px;"
        )

    def _pick(self):
        c = QColorDialog.getColor(QColor(*self._color[:3]), self.window())
        if c.isValid():
            self._color = [c.red(), c.green(), c.blue()]
            self._apply()
            self.color_changed.emit(self._color)

    def set_color(self, rgb):
        self._color = list(rgb[:3])
        self._apply()

    def get_color(self):
        return self._color[:]


# ── Available fonts (runtime detection) ──────────────────────

def _get_system_fonts() -> list[str]:
    """Return sorted list of installed font family names via Qt."""
    try:
        return sorted(QFontDatabase.families())
    except Exception:
        return ["Arial", "DejaVu Sans", "Liberation Sans"]

# ── Properties panel ──────────────────────────────────────────


class PropertiesPanel(QScrollArea):
    """Right-side panel: element properties + background settings."""

    property_changed = Signal(object)  # emits LayoutElement
    background_changed = Signal(object)  # emits Background
    delete_requested = Signal()
    duplicate_requested = Signal()

    def __init__(self, sensor_ids: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._element: LayoutElement | None = None
        self._updating = False
        self._sensor_units: dict[str, str] = {}  # sensor_id -> native unit
        self.setWidgetResizable(True)
        self.setMinimumWidth(310)
        self.setMaximumWidth(400)
        self._build(sensor_ids or [])

    # ── build ──

    def _build(self, sensor_ids: list[str]):
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ── Element: Position ─────────────────────────
        self._grp_elem = QGroupBox(_("Element"))
        eg = QVBoxLayout(self._grp_elem)
        eg.setSpacing(4)

        common = QFormLayout()
        common.setSpacing(3)
        self._lbl_type = QLabel("-")
        common.addRow(_("Type:"), self._lbl_type)

        pos_w = QWidget()
        pos_l = QHBoxLayout(pos_w)
        pos_l.setContentsMargins(0, 0, 0, 0)
        pos_l.setSpacing(2)
        self._sp_x = QSpinBox()
        self._sp_x.setRange(-SCREEN_W, SCREEN_W * 2)
        self._sp_y = QSpinBox()
        self._sp_y.setRange(-SCREEN_H, SCREEN_H * 2)
        self._sp_z = QSpinBox()
        self._sp_z.setRange(-100, 100)
        for label, sp in [("X", self._sp_x), ("Y", self._sp_y), ("Z", self._sp_z)]:
            pos_l.addWidget(QLabel(label))
            pos_l.addWidget(sp)
        common.addRow(_("Pos:"), pos_w)
        eg.addLayout(common)

        # -- text fields --
        self._w_text = QWidget()
        tf = QFormLayout(self._w_text)
        tf.setContentsMargins(0, 0, 0, 0)
        tf.setSpacing(3)
        self._ed_text = QLineEdit()
        tf.addRow(_("Text:"), self._ed_text)
        eg.addWidget(self._w_text)

        # -- sensor fields --
        self._w_sensor = QWidget()
        sf = QFormLayout(self._w_sensor)
        sf.setContentsMargins(0, 0, 0, 0)
        sf.setSpacing(3)
        self._cb_sensor = QComboBox()
        self._cb_sensor.setEditable(True)
        self._cb_sensor.addItems(sorted(sensor_ids))
        sf.addRow(_("Sensor:"), self._cb_sensor)
        self._ed_label = QLineEdit()
        sf.addRow(_("Label:"), self._ed_label)
        self._ed_fmt = QLineEdit()
        sf.addRow(_("Format:"), self._ed_fmt)
        self._cb_unit = QComboBox()
        sf.addRow(_("Unit:"), self._cb_unit)
        eg.addWidget(self._w_sensor)

        # -- image fields --
        self._w_img = QWidget()
        imf = QFormLayout(self._w_img)
        imf.setContentsMargins(0, 0, 0, 0)
        imf.setSpacing(3)
        imc = QWidget()
        iml = QHBoxLayout(imc)
        iml.setContentsMargins(0, 0, 0, 0)
        self._ed_img = QLineEdit()
        self._btn_img = QPushButton("...")
        self._btn_img.setFixedWidth(30)
        iml.addWidget(self._ed_img)
        iml.addWidget(self._btn_img)
        imf.addRow(_("Path:"), imc)
        eg.addWidget(self._w_img)

        # -- shape fields --
        self._w_shape = QWidget()
        shf = QFormLayout(self._w_shape)
        shf.setContentsMargins(0, 0, 0, 0)
        shf.setSpacing(3)
        self._cb_shape = QComboBox()
        self._cb_shape.addItems(["rect", "circle", "ellipse", "line"])
        shf.addRow(_("Shape:"), self._cb_shape)
        self._btn_fill_color = ColorButton([255, 255, 255])
        shf.addRow(_("Fill:"), self._btn_fill_color)
        self._sp_fill_alpha = QSpinBox()
        self._sp_fill_alpha.setRange(0, 255)
        self._sp_fill_alpha.setValue(255)
        shf.addRow(_("Opacity:"), self._sp_fill_alpha)
        eg.addWidget(self._w_shape)

        # -- bar / arc_bar fields (sensor-linked) --
        self._w_bar = QWidget()
        brf = QFormLayout(self._w_bar)
        brf.setContentsMargins(0, 0, 0, 0)
        brf.setSpacing(3)
        self._cb_bar_sensor = QComboBox()
        self._cb_bar_sensor.setEditable(True)
        self._cb_bar_sensor.addItems(sorted(sensor_ids))
        brf.addRow(_("Sensor:"), self._cb_bar_sensor)
        self._btn_bar_fg = ColorButton([0, 200, 255])
        brf.addRow(_("FG color:"), self._btn_bar_fg)
        self._btn_bar_bg = ColorButton([40, 40, 60])
        brf.addRow(_("BG color:"), self._btn_bar_bg)
        self._chk_bar_grad = QCheckBox(_("FG gradient"))
        brf.addRow("", self._chk_bar_grad)
        self._btn_bar_fg2 = ColorButton([255, 80, 80])
        brf.addRow(_("FG end:"), self._btn_bar_fg2)
        self._sp_bar_max = QSpinBox()
        self._sp_bar_max.setRange(1, 10000)
        self._sp_bar_max.setValue(100)
        brf.addRow(_("Max:"), self._sp_bar_max)
        self._sp_bar_thick = QSpinBox()
        self._sp_bar_thick.setRange(1, 100)
        self._sp_bar_thick.setValue(8)
        brf.addRow(_("Thickness:"), self._sp_bar_thick)
        # Direction (bar only, not arc_bar)
        self._w_bar_dir = QWidget()
        bdf = QFormLayout(self._w_bar_dir)
        bdf.setContentsMargins(0, 0, 0, 0)
        bdf.setSpacing(3)
        self._cb_bar_dir = QComboBox()
        self._cb_bar_dir.addItems(["right", "left", "down", "up"])
        bdf.addRow(_("Direction:"), self._cb_bar_dir)
        eg.addWidget(self._w_bar_dir)
        eg.addWidget(self._w_bar)

        # -- arc_bar extra fields --
        self._w_arc = QWidget()
        arf = QFormLayout(self._w_arc)
        arf.setContentsMargins(0, 0, 0, 0)
        arf.setSpacing(3)
        self._sp_arc_start = QSpinBox()
        self._sp_arc_start.setRange(0, 359)
        self._sp_arc_start.setValue(135)
        self._sp_arc_start.setSuffix("\u00b0")
        arf.addRow(_("Start:"), self._sp_arc_start)
        self._sp_arc_sweep = QSpinBox()
        self._sp_arc_sweep.setRange(1, 360)
        self._sp_arc_sweep.setValue(270)
        self._sp_arc_sweep.setSuffix("\u00b0")
        arf.addRow(_("Sweep:"), self._sp_arc_sweep)
        eg.addWidget(self._w_arc)

        # -- size (w/h) for shape, bar, arc_bar, image --
        self._w_size = QWidget()
        szf = QFormLayout(self._w_size)
        szf.setContentsMargins(0, 0, 0, 0)
        szf.setSpacing(3)
        self._sp_w = QSpinBox()
        self._sp_w.setRange(0, SCREEN_W * 2)
        self._sp_h = QSpinBox()
        self._sp_h.setRange(0, SCREEN_H * 2)
        size_row = QWidget()
        szl = QHBoxLayout(size_row)
        szl.setContentsMargins(0, 0, 0, 0)
        szl.setSpacing(2)
        szl.addWidget(QLabel("W"))
        szl.addWidget(self._sp_w)
        szl.addWidget(QLabel("H"))
        szl.addWidget(self._sp_h)
        szf.addRow(_("Size:"), size_row)
        eg.addWidget(self._w_size)

        self._grp_elem.setVisible(False)
        root.addWidget(self._grp_elem)

        # ── Style (text / sensor only) ────────────────
        self._grp_style = QGroupBox(_("Style"))
        stl = QVBoxLayout(self._grp_style)
        stl.setSpacing(4)

        stf = QFormLayout()
        stf.setSpacing(3)

        # Font family
        self._cb_font_family = QComboBox()
        self._cb_font_family.setEditable(True)
        self._cb_font_family.addItem("(default)")
        for f in _get_system_fonts():
            self._cb_font_family.addItem(f)
        stf.addRow(_("Font:"), self._cb_font_family)

        self._sp_font = QSpinBox()
        self._sp_font.setRange(6, 120)
        stf.addRow(_("Size:"), self._sp_font)

        self._btn_color = ColorButton()
        stf.addRow(_("Color:"), self._btn_color)

        self._cb_anchor = QComboBox()
        self._cb_anchor.addItems(["lt", "mt", "rt", "lm", "mm", "rm", "lb", "mb", "rb"])
        stf.addRow(_("Anchor:"), self._cb_anchor)

        stl.addLayout(stf)

        # Gradient sub-section
        self._chk_gradient = QCheckBox(_("Gradient fill"))
        stl.addWidget(self._chk_gradient)

        self._w_gradient = QWidget()
        gl = QFormLayout(self._w_gradient)
        gl.setContentsMargins(16, 0, 0, 0)
        gl.setSpacing(3)
        self._btn_grad_color = ColorButton([255, 255, 255])
        gl.addRow(_("End color:"), self._btn_grad_color)
        self._sp_grad_angle = QSpinBox()
        self._sp_grad_angle.setRange(0, 359)
        self._sp_grad_angle.setSuffix("\u00b0")
        gl.addRow(_("Angle:"), self._sp_grad_angle)
        self._w_gradient.setVisible(False)
        stl.addWidget(self._w_gradient)

        # Stroke sub-section
        self._chk_stroke = QCheckBox(_("Text stroke"))
        stl.addWidget(self._chk_stroke)

        self._w_stroke = QWidget()
        skl = QFormLayout(self._w_stroke)
        skl.setContentsMargins(16, 0, 0, 0)
        skl.setSpacing(3)
        self._sp_stroke_w = QSpinBox()
        self._sp_stroke_w.setRange(1, 10)
        self._sp_stroke_w.setValue(1)
        skl.addRow(_("Width:"), self._sp_stroke_w)
        self._btn_stroke_color = ColorButton([0, 0, 0])
        skl.addRow(_("Color:"), self._btn_stroke_color)
        self._w_stroke.setVisible(False)
        stl.addWidget(self._w_stroke)

        self._grp_style.setVisible(False)
        root.addWidget(self._grp_style)

        # ── Actions ──────────────────────────────────
        self._w_actions = QWidget()
        al = QHBoxLayout(self._w_actions)
        al.setContentsMargins(0, 4, 0, 4)
        self._btn_del = QPushButton(_("Delete"))
        self._btn_dup = QPushButton(_("Duplicate"))
        self._btn_del.clicked.connect(lambda: self.delete_requested.emit())
        self._btn_dup.clicked.connect(lambda: self.duplicate_requested.emit())
        al.addWidget(self._btn_del)
        al.addWidget(self._btn_dup)
        self._w_actions.setVisible(False)
        root.addWidget(self._w_actions)

        # ── Background ───────────────────────────────
        grp_bg = QGroupBox(_("Background"))
        bgl = QVBoxLayout(grp_bg)
        bgl.setSpacing(4)

        type_row = QHBoxLayout()
        self._r_solid = QRadioButton(_("Solid"))
        self._r_image = QRadioButton(_("Image"))
        self._r_video = QRadioButton(_("Video"))
        self._r_solid.setChecked(True)
        type_row.addWidget(self._r_solid)
        type_row.addWidget(self._r_image)
        type_row.addWidget(self._r_video)
        bgl.addLayout(type_row)

        bf = QFormLayout()
        bf.setSpacing(3)
        self._btn_bg_col = ColorButton([15, 15, 25])
        bf.addRow(_("Color:"), self._btn_bg_col)

        bpc = QWidget()
        bpl = QHBoxLayout(bpc)
        bpl.setContentsMargins(0, 0, 0, 0)
        self._ed_bg_path = QLineEdit()
        self._btn_bg_browse = QPushButton("...")
        self._btn_bg_browse.setFixedWidth(30)
        bpl.addWidget(self._ed_bg_path)
        bpl.addWidget(self._btn_bg_browse)
        bf.addRow(_("Path:"), bpc)
        bgl.addLayout(bf)

        root.addWidget(grp_bg)
        root.addStretch()
        self.setWidget(container)

        # ── Signals ──────────────────────────────────
        for sp in (self._sp_x, self._sp_y, self._sp_z, self._sp_font):
            sp.valueChanged.connect(self._on_elem)
        self._ed_text.textChanged.connect(self._on_elem)
        self._cb_sensor.currentTextChanged.connect(self._on_sensor_id_changed)
        self._ed_label.textChanged.connect(self._on_elem)
        self._ed_fmt.textChanged.connect(self._on_elem)
        self._cb_unit.currentTextChanged.connect(self._on_elem)
        self._ed_img.textChanged.connect(self._on_elem)
        self._btn_color.color_changed.connect(self._on_elem)
        self._cb_anchor.currentTextChanged.connect(self._on_elem)
        self._cb_font_family.currentTextChanged.connect(self._on_elem)
        self._btn_img.clicked.connect(self._pick_img)

        # Gradient signals
        self._chk_gradient.toggled.connect(self._on_gradient_toggle)
        self._btn_grad_color.color_changed.connect(self._on_elem)
        self._sp_grad_angle.valueChanged.connect(self._on_elem)

        # Stroke signals
        self._chk_stroke.toggled.connect(self._on_stroke_toggle)
        self._sp_stroke_w.valueChanged.connect(self._on_elem)
        self._btn_stroke_color.color_changed.connect(self._on_elem)

        # Shape signals
        self._cb_shape.currentTextChanged.connect(self._on_elem)
        self._btn_fill_color.color_changed.connect(self._on_elem)
        self._sp_fill_alpha.valueChanged.connect(self._on_elem)

        # Size signals
        self._sp_w.valueChanged.connect(self._on_elem)
        self._sp_h.valueChanged.connect(self._on_elem)

        # Bar signals
        self._cb_bar_sensor.currentTextChanged.connect(self._on_elem)
        self._btn_bar_fg.color_changed.connect(self._on_elem)
        self._btn_bar_bg.color_changed.connect(self._on_elem)
        self._chk_bar_grad.toggled.connect(self._on_bar_grad_toggle)
        self._btn_bar_fg2.color_changed.connect(self._on_elem)
        self._sp_bar_max.valueChanged.connect(self._on_elem)
        self._sp_bar_thick.valueChanged.connect(self._on_elem)
        self._cb_bar_dir.currentTextChanged.connect(self._on_elem)

        # Arc signals
        self._sp_arc_start.valueChanged.connect(self._on_elem)
        self._sp_arc_sweep.valueChanged.connect(self._on_elem)

        # Background signals
        self._r_solid.toggled.connect(lambda c: self._on_bg() if c else None)
        self._r_image.toggled.connect(lambda c: self._on_bg() if c else None)
        self._r_video.toggled.connect(lambda c: self._on_bg() if c else None)
        self._btn_bg_col.color_changed.connect(lambda _: self._on_bg())
        self._ed_bg_path.textChanged.connect(self._on_bg)
        self._btn_bg_browse.clicked.connect(self._pick_bg)

    def _on_gradient_toggle(self, checked: bool):
        self._w_gradient.setVisible(checked)
        self._on_elem()

    def _on_stroke_toggle(self, checked: bool):
        self._w_stroke.setVisible(checked)
        self._on_elem()

    def _on_bar_grad_toggle(self, checked: bool):
        self._btn_bar_fg2.setVisible(checked)
        self._on_elem()

    def _on_sensor_id_changed(self, sensor_id: str):
        """Sensor combo changed — refresh available units and emit."""
        self._refresh_unit_combo(sensor_id)
        self._on_elem()

    def _refresh_unit_combo(self, sensor_id: str):
        """Populate the unit combo based on the sensor's native unit or date/time formats."""
        self._cb_unit.blockSignals(True)
        self._cb_unit.clear()

        # Date/time sensors get format presets instead of unit conversion
        if sensor_id == "sys.clock":
            self._cb_unit.addItem("(native)")
            self._cb_unit.addItems(available_time_formats())
            self._cb_unit.blockSignals(False)
            return
        if sensor_id == "sys.date":
            self._cb_unit.addItem("(native)")
            self._cb_unit.addItems(available_date_formats())
            self._cb_unit.blockSignals(False)
            return

        native = self._sensor_units.get(sensor_id, "")
        units = available_units(native)
        if units:
            self._cb_unit.addItem("(native)")
            self._cb_unit.addItems(units)
        self._cb_unit.blockSignals(False)

    # ── public API ──

    def set_element(self, element: LayoutElement | None) -> None:
        self._updating = True
        self._element = element
        vis = element is not None
        self._grp_elem.setVisible(vis)
        self._w_actions.setVisible(vis)

        if element:
            self._lbl_type.setText(element.type.capitalize())
            self._sp_x.setValue(element.x)
            self._sp_y.setValue(element.y)
            self._sp_z.setValue(element.z)

            is_t = element.type == "text"
            is_s = element.type == "sensor"
            is_i = element.type == "image"
            is_sh = element.type == "shape"
            is_bar = element.type == "bar"
            is_arc = element.type == "arc_bar"
            has_text_style = is_t or is_s  # font/color/anchor
            has_size = is_sh or is_bar or is_arc or is_i

            self._w_text.setVisible(is_t)
            self._w_sensor.setVisible(is_s)
            self._w_img.setVisible(is_i)
            self._w_shape.setVisible(is_sh)
            self._w_bar.setVisible(is_bar or is_arc)
            self._w_bar_dir.setVisible(is_bar)
            self._w_arc.setVisible(is_arc)
            self._w_size.setVisible(has_size)
            self._grp_style.setVisible(has_text_style or is_sh)

            if is_t:
                self._ed_text.setText(element.text)
            elif is_s:
                idx = self._cb_sensor.findText(element.sensor_id)
                if idx >= 0:
                    self._cb_sensor.setCurrentIndex(idx)
                else:
                    self._cb_sensor.setEditText(element.sensor_id)
                self._ed_label.setText(element.label)
                self._ed_fmt.setText(element.format)
                # Unit combo
                self._refresh_unit_combo(element.sensor_id)
                if element.display_unit:
                    uidx = self._cb_unit.findText(element.display_unit)
                    if uidx >= 0:
                        self._cb_unit.setCurrentIndex(uidx)
                else:
                    self._cb_unit.setCurrentIndex(0)  # (native)
            elif is_i:
                self._ed_img.setText(element.text)
            elif is_sh:
                idx = self._cb_shape.findText(element.shape)
                if idx >= 0:
                    self._cb_shape.setCurrentIndex(idx)
                self._btn_fill_color.set_color(element.fill_color)
                self._sp_fill_alpha.setValue(element.fill_alpha)
            if is_bar or is_arc:
                idx = self._cb_bar_sensor.findText(element.sensor_id)
                if idx >= 0:
                    self._cb_bar_sensor.setCurrentIndex(idx)
                else:
                    self._cb_bar_sensor.setEditText(element.sensor_id)
                self._btn_bar_fg.set_color(element.bar_fg_color)
                self._btn_bar_bg.set_color(element.bar_bg_color)
                self._chk_bar_grad.setChecked(element.bar_fg_gradient)
                self._btn_bar_fg2.setVisible(element.bar_fg_gradient)
                self._btn_bar_fg2.set_color(element.bar_fg_color2)
                self._sp_bar_max.setValue(int(element.bar_max))
                self._sp_bar_thick.setValue(element.bar_thickness)
            if is_bar:
                idx = self._cb_bar_dir.findText(element.bar_direction or "right")
                if idx >= 0:
                    self._cb_bar_dir.setCurrentIndex(idx)
            if is_arc:
                self._sp_arc_start.setValue(element.bar_start_angle)
                self._sp_arc_sweep.setValue(element.bar_sweep_angle)
            if has_size:
                self._sp_w.setValue(element.w)
                self._sp_h.setValue(element.h)

            if has_text_style or is_sh:
                self._sp_font.setValue(element.font_size)
                self._btn_color.set_color(element.color)
                idx = self._cb_anchor.findText(element.anchor)
                if idx >= 0:
                    self._cb_anchor.setCurrentIndex(idx)

                # Font family
                fam = element.font_family
                if fam:
                    idx = self._cb_font_family.findText(fam)
                    if idx >= 0:
                        self._cb_font_family.setCurrentIndex(idx)
                    else:
                        self._cb_font_family.setEditText(fam)
                else:
                    self._cb_font_family.setCurrentIndex(0)  # (default)

                # Gradient
                self._chk_gradient.setChecked(element.gradient)
                self._w_gradient.setVisible(element.gradient)
                self._btn_grad_color.set_color(element.gradient_color)
                self._sp_grad_angle.setValue(element.gradient_angle)

                # Stroke
                has_stroke = element.stroke_width > 0
                self._chk_stroke.setChecked(has_stroke)
                self._w_stroke.setVisible(has_stroke)
                self._sp_stroke_w.setValue(max(element.stroke_width, 1))
                self._btn_stroke_color.set_color(element.stroke_color)
        else:
            self._grp_style.setVisible(False)

        self._updating = False

    def set_background(self, bg: Background) -> None:
        self._updating = True
        {"solid": self._r_solid, "image": self._r_image, "video": self._r_video}.get(
            bg.type, self._r_solid
        ).setChecked(True)
        self._btn_bg_col.set_color(bg.color)
        self._ed_bg_path.setText(bg.path)
        self._updating = False

    def update_sensors(self, ids: list[str]) -> None:
        cur = self._cb_sensor.currentText()
        self._cb_sensor.clear()
        self._cb_sensor.addItems(sorted(ids))
        idx = self._cb_sensor.findText(cur)
        if idx >= 0:
            self._cb_sensor.setCurrentIndex(idx)
        # Also update bar sensor combo
        cur_bar = self._cb_bar_sensor.currentText()
        self._cb_bar_sensor.clear()
        self._cb_bar_sensor.addItems(sorted(ids))
        idx = self._cb_bar_sensor.findText(cur_bar)
        if idx >= 0:
            self._cb_bar_sensor.setCurrentIndex(idx)

    def update_sensor_units(self, unit_map: dict[str, str]) -> None:
        """Update the sensor_id → native_unit mapping."""
        self._sensor_units = unit_map

    # ── private handlers ──

    def _on_elem(self, *_):
        if self._updating or not self._element:
            return
        el = self._element
        el.x = self._sp_x.value()
        el.y = self._sp_y.value()
        el.z = self._sp_z.value()
        if el.type == "text":
            el.text = self._ed_text.text()
        elif el.type == "sensor":
            el.sensor_id = self._cb_sensor.currentText()
            el.label = self._ed_label.text()
            el.format = self._ed_fmt.text()
            # Unit: "(native)" or empty means use native unit
            unit_text = self._cb_unit.currentText()
            el.display_unit = "" if unit_text == "(native)" else unit_text
        elif el.type == "image":
            el.text = self._ed_img.text()
        elif el.type == "shape":
            el.shape = self._cb_shape.currentText()
            el.fill_color = self._btn_fill_color.get_color()
            el.fill_alpha = self._sp_fill_alpha.value()
        if el.type in ("bar", "arc_bar"):
            el.sensor_id = self._cb_bar_sensor.currentText()
            el.bar_fg_color = self._btn_bar_fg.get_color()
            el.bar_bg_color = self._btn_bar_bg.get_color()
            el.bar_fg_gradient = self._chk_bar_grad.isChecked()
            el.bar_fg_color2 = self._btn_bar_fg2.get_color()
            el.bar_max = float(self._sp_bar_max.value())
            el.bar_thickness = self._sp_bar_thick.value()
        if el.type == "bar":
            el.bar_direction = self._cb_bar_dir.currentText()
        if el.type == "arc_bar":
            el.bar_start_angle = self._sp_arc_start.value()
            el.bar_sweep_angle = self._sp_arc_sweep.value()
        if el.type in ("shape", "bar", "arc_bar", "image"):
            el.w = self._sp_w.value()
            el.h = self._sp_h.value()
        if el.type in ("text", "sensor", "shape"):
            el.font_size = self._sp_font.value()
            el.color = self._btn_color.get_color()
            el.anchor = self._cb_anchor.currentText()
            # Font family
            fam = self._cb_font_family.currentText()
            el.font_family = "" if fam == "(default)" else fam
            # Gradient
            el.gradient = self._chk_gradient.isChecked()
            el.gradient_color = self._btn_grad_color.get_color()
            el.gradient_angle = self._sp_grad_angle.value()
            # Stroke
            if self._chk_stroke.isChecked():
                el.stroke_width = self._sp_stroke_w.value()
                el.stroke_color = self._btn_stroke_color.get_color()
            else:
                el.stroke_width = 0
        self.property_changed.emit(el)

    def _on_bg(self, *_):
        if self._updating:
            return
        bg_type = "solid"
        if self._r_image.isChecked():
            bg_type = "image"
        elif self._r_video.isChecked():
            bg_type = "video"
        bg = Background(
            type=bg_type,
            color=self._btn_bg_col.get_color(),
            path=self._ed_bg_path.text(),
        )
        self.background_changed.emit(bg)

    def _pick_img(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if p:
            self._ed_img.setText(p)

    def _pick_bg(self):
        p, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp);;"
            "Videos (*.mp4 *.avi *.mkv *.mov *.gif);;"
            "All (*)",
        )
        if p:
            # Auto-select the right radio based on file extension
            ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
            if ext in ("mp4", "avi", "mkv", "mov", "webm"):
                self._r_video.setChecked(True)
            elif ext in ("png", "jpg", "jpeg", "bmp", "gif"):
                self._r_image.setChecked(True)
            self._ed_bg_path.setText(p)


# ── Main window ───────────────────────────────────────────────


class ConfigWindow(QMainWindow):
    """Settings / editor window."""

    def __init__(self, daemon: TurzxDaemon) -> None:
        super().__init__()
        self.daemon = daemon
        self._dirty = False
        self.setWindowTitle(_("TURZX - Editor"))
        self.setMinimumSize(1100, 750)

        sensor_ids = list(self.daemon.sensors.read_all().keys())

        # Build sensor_id -> native_unit map for unit conversion UI
        readings = self.daemon.sensors.read_all()
        sensor_unit_map = {sid: r.unit for sid, r in readings.items()}

        self._scene = EditorScene()
        self._canvas = LayoutCanvas(self._scene)
        self._elem_list = ElementListPanel(self._scene)
        self._props = PropertiesPanel(sensor_ids)
        self._props.update_sensor_units(sensor_unit_map)
        self._preview = PreviewWidget()

        self._build_ui(sensor_ids)
        self._connect_signals()

        # live preview timer (must exist before _load_layout -> _adjust_preview_timer)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_preview)
        self._timer.start(2000)

        self._load_layout()

    # ── UI construction ──

    def _build_ui(self, sensor_ids: list[str]):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ── Left panel: toolbox ──
        left = QWidget()
        left.setFixedWidth(200)
        ll = QVBoxLayout(left)

        # Layout selector
        lg = QGroupBox(_("Layout"))
        lgl = QVBoxLayout(lg)
        self._combo_layout = QComboBox()
        self._combo_layout.addItems(self.daemon.config.list_layouts())
        # Sync combo to the persisted active layout
        active = self.daemon.config.active_name
        idx = self._combo_layout.findText(active)
        if idx >= 0:
            self._combo_layout.setCurrentIndex(idx)
        lgl.addWidget(self._combo_layout)
        save_row = QHBoxLayout()
        self._btn_save = QPushButton(_("Save"))
        self._btn_save_as = QPushButton(_("Save As..."))
        save_row.addWidget(self._btn_save)
        save_row.addWidget(self._btn_save_as)
        lgl.addLayout(save_row)
        ll.addWidget(lg)

        # Display Mode
        mg = QGroupBox(_("Display Mode"))
        mgl = QVBoxLayout(mg)

        mode_row = QHBoxLayout()
        self._r_static = QRadioButton(_("Static"))
        self._r_rotative = QRadioButton(_("Rotative"))
        self._r_reactive = QRadioButton(_("Reactive"))
        self._r_static.setChecked(True)
        mode_row.addWidget(self._r_static)
        mode_row.addWidget(self._r_rotative)
        mode_row.addWidget(self._r_reactive)
        mgl.addLayout(mode_row)

        # Rotative config (hidden by default)
        self._w_rotative = QWidget()
        rot_l = QVBoxLayout(self._w_rotative)
        rot_l.setContentsMargins(4, 4, 4, 4)
        rot_l.addWidget(QLabel(_("Layouts to rotate:")))
        self._list_rotate = QListWidget()
        self._list_rotate.setMaximumHeight(120)
        for name in self.daemon.config.list_layouts():
            item = QListWidgetItem(name)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list_rotate.addItem(item)
        rot_l.addWidget(self._list_rotate)
        intv_row = QHBoxLayout()
        intv_row.addWidget(QLabel(_("Interval (s):")))
        self._sp_rotate_interval = QSpinBox()
        self._sp_rotate_interval.setRange(5, 600)
        self._sp_rotate_interval.setValue(30)
        intv_row.addWidget(self._sp_rotate_interval)
        rot_l.addLayout(intv_row)
        self._w_rotative.setVisible(False)
        mgl.addWidget(self._w_rotative)

        # Reactive config (hidden by default)
        self._w_reactive = QWidget()
        react_l = QVBoxLayout(self._w_reactive)
        react_l.setContentsMargins(4, 4, 4, 4)
        react_l.addWidget(QLabel(_("Process → Layout rules:")))
        self._list_rules = QListWidget()
        self._list_rules.setMaximumHeight(120)
        react_l.addWidget(self._list_rules)
        rule_btn_row = QHBoxLayout()
        self._btn_add_rule = QPushButton(_("+ Rule"))
        self._btn_del_rule = QPushButton(_("- Rule"))
        rule_btn_row.addWidget(self._btn_add_rule)
        rule_btn_row.addWidget(self._btn_del_rule)
        react_l.addLayout(rule_btn_row)
        fb_row = QHBoxLayout()
        fb_row.addWidget(QLabel(_("Fallback:")))
        self._combo_fallback = QComboBox()
        self._combo_fallback.addItems(self.daemon.config.list_layouts())
        fb_row.addWidget(self._combo_fallback)
        react_l.addLayout(fb_row)
        self._w_reactive.setVisible(False)
        mgl.addWidget(self._w_reactive)

        self._btn_apply_mode = QPushButton(_("Apply Mode"))
        mgl.addWidget(self._btn_apply_mode)
        ll.addWidget(mg)

        # Sensor update interval
        rg = QGroupBox(_("Sensor Update"))
        rgl = QVBoxLayout(rg)
        self._lbl_rate = QLabel("1.0 s")
        self._slider_rate = QSlider(Qt.Orientation.Horizontal)
        self._slider_rate.setRange(2, 50)  # value / 10 → 0.2 – 5.0 seconds
        self._slider_rate.setValue(10)
        rgl.addWidget(self._lbl_rate)
        rgl.addWidget(self._slider_rate)
        ll.addWidget(rg)

        # Device rotation
        rotg = QGroupBox(_("Device Rotation"))
        rotgl = QVBoxLayout(rotg)
        self._combo_rotation = QComboBox()
        self._combo_rotation.addItems(["0°", "90°", "180°", "270°"])
        self._combo_rotation.setCurrentIndex(2)  # default 180°
        rotgl.addWidget(self._combo_rotation)
        ll.addWidget(rotg)

        # Add element buttons
        ag = QGroupBox(_("Add Element"))
        agl = QVBoxLayout(ag)
        self._btn_add_text = QPushButton(_("+ Text"))
        self._btn_add_sensor = QPushButton(_("+ Sensor"))
        self._btn_add_image = QPushButton(_("+ Image"))
        self._btn_add_shape = QPushButton(_("+ Shape"))
        self._btn_add_bar = QPushButton(_("+ Bar"))
        self._btn_add_arc = QPushButton(_("+ Arc Bar"))
        agl.addWidget(self._btn_add_text)
        agl.addWidget(self._btn_add_sensor)
        agl.addWidget(self._btn_add_image)
        agl.addWidget(self._btn_add_shape)
        agl.addWidget(self._btn_add_bar)
        agl.addWidget(self._btn_add_arc)
        ll.addWidget(ag)

        # Available sensors
        sg = QGroupBox(_("Sensors (double-click to add)"))
        sgl = QVBoxLayout(sg)
        self._list_sensors = QListWidget()
        for sid in sorted(sensor_ids):
            self._list_sensors.addItem(QListWidgetItem(sid))
        sgl.addWidget(self._list_sensors)
        ll.addWidget(sg)

        ll.addStretch()
        splitter.addWidget(left)

        # ── Center: canvas + element list + preview ──
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.addWidget(QLabel(_("Canvas")))
        cl.addWidget(self._canvas, stretch=1)
        cl.addWidget(self._elem_list, stretch=0)
        cl.addWidget(QLabel(_("Live Preview")))
        cl.addWidget(self._preview, stretch=0)
        splitter.addWidget(center)

        # ── Right: properties ──
        splitter.addWidget(self._props)

        splitter.setSizes([200, 540, 360])

    # ── Signals ──

    def _connect_signals(self):
        # layout selector
        self._combo_layout.currentTextChanged.connect(self._on_layout_changed)
        self._btn_save.clicked.connect(self._save_layout)
        self._btn_save_as.clicked.connect(self._save_layout_as)
        self._slider_rate.valueChanged.connect(self._on_rate)
        self._combo_rotation.currentIndexChanged.connect(self._on_rotation)

        # add element buttons
        self._btn_add_text.clicked.connect(self._add_text)
        self._btn_add_sensor.clicked.connect(self._add_sensor)
        self._btn_add_image.clicked.connect(self._add_image)
        self._btn_add_shape.clicked.connect(self._add_shape)
        self._btn_add_bar.clicked.connect(self._add_bar)
        self._btn_add_arc.clicked.connect(self._add_arc_bar)
        self._list_sensors.itemDoubleClicked.connect(self._add_sensor_from_list)

        # scene ↔ properties
        self._scene.element_selected.connect(self._props.set_element)
        self._scene.layout_modified.connect(self._mark_dirty)
        self._props.property_changed.connect(self._on_element_changed)
        self._props.background_changed.connect(self._on_background_changed)
        self._props.delete_requested.connect(self._scene.remove_selected)
        self._props.duplicate_requested.connect(self._scene.duplicate_selected)

        # display mode
        self._r_static.toggled.connect(self._on_mode_radio)
        self._r_rotative.toggled.connect(self._on_mode_radio)
        self._r_reactive.toggled.connect(self._on_mode_radio)
        self._btn_apply_mode.clicked.connect(self._apply_mode)
        self._btn_add_rule.clicked.connect(self._add_reactive_rule)
        self._btn_del_rule.clicked.connect(self._del_reactive_rule)

        # mode controller → UI sync
        self.daemon.mode_controller.layout_switched.connect(self._on_mode_layout_switched)

    # ── Layout management ──

    def _load_layout(self):
        layout = self.daemon.config.active_layout
        self._scene.load_layout(layout)
        self._props.set_background(layout.background)
        self._elem_list.refresh()
        # sensor update rate
        rate_val = int(layout.refresh_rate * 10)
        self._slider_rate.blockSignals(True)
        self._slider_rate.setValue(max(2, min(50, rate_val)))
        self._slider_rate.blockSignals(False)
        self._lbl_rate.setText(f"{layout.refresh_rate:.1f} s")
        # rotation
        rot_map = {0: 0, 90: 1, 180: 2, 270: 3}
        self._combo_rotation.blockSignals(True)
        self._combo_rotation.setCurrentIndex(rot_map.get(layout.rotation, 2))
        self._combo_rotation.blockSignals(False)
        self._adjust_preview_timer()
        self._load_mode_ui()
        self._dirty = False
        self._update_title()

    def _on_layout_changed(self, name: str):
        if self._dirty:
            reply = QMessageBox.question(
                self, _("Unsaved Changes"),
                _("Save changes before switching layout?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                # Revert combo without triggering signal
                self._combo_layout.blockSignals(True)
                idx = self._combo_layout.findText(self.daemon.config.active_name)
                if idx >= 0:
                    self._combo_layout.setCurrentIndex(idx)
                self._combo_layout.blockSignals(False)
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save_layout()
        self.daemon.config.set_active(name)
        self._load_layout()
        self._dirty = False
        self._update_title()

    def _on_rate(self, val: int):
        rate = val / 10.0
        self._lbl_rate.setText(f"{rate:.1f} s")
        layout = self.daemon.config.active_layout
        layout.refresh_rate = rate
        self._mark_dirty()

    def _on_rotation(self, idx: int):
        degrees = [0, 90, 180, 270][idx]
        layout = self.daemon.config.active_layout
        layout.rotation = degrees
        self._mark_dirty()

    def _save_layout(self):
        layout = self.daemon.config.active_layout
        self.daemon.config.save_layout(layout, self.daemon.config.active_name)
        self._dirty = False
        self._update_title()

    def _mark_dirty(self):
        """Mark layout as having unsaved changes."""
        if not self._dirty:
            self._dirty = True
            self._update_title()

    def _update_title(self):
        name = self.daemon.config.active_name
        prefix = "* " if self._dirty else ""
        self.setWindowTitle(f"{prefix}TURZX - {name}")

    def _save_layout_as(self):
        name, ok = QInputDialog.getText(self, _("Save Layout As"), _("Name:"))
        if ok and name:
            layout = self.daemon.config.active_layout
            layout.name = name
            fname = name.lower().replace(" ", "_")
            self.daemon.config.save_layout(layout, fname)
            # Update active to the new layout
            self.daemon.config.set_active(fname)
            self._combo_layout.blockSignals(True)
            self._combo_layout.clear()
            self._combo_layout.addItems(self.daemon.config.list_layouts())
            self._combo_layout.setCurrentText(fname)
            self._combo_layout.blockSignals(False)
            self._dirty = False
            self._update_title()

    # ── Display mode ──

    def _on_mode_radio(self, checked: bool):
        if not checked:
            return
        self._w_rotative.setVisible(self._r_rotative.isChecked())
        self._w_reactive.setVisible(self._r_reactive.isChecked())

    def _apply_mode(self):
        """Build ModeConfig from UI and apply it."""
        if self._r_static.isChecked():
            mode = "static"
        elif self._r_rotative.isChecked():
            mode = "rotative"
        else:
            mode = "reactive"

        # Rotative config
        rot_layouts = []
        for i in range(self._list_rotate.count()):
            item = self._list_rotate.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                rot_layouts.append(item.text())
        rot_interval = self._sp_rotate_interval.value()

        # Reactive config
        rules = []
        for i in range(self._list_rules.count()):
            text = self._list_rules.item(i).text()
            if " → " in text:
                proc, layout = text.split(" → ", 1)
                rules.append(ReactiveRule(process=proc.strip(), layout=layout.strip()))
        fallback = self._combo_fallback.currentText() or "default"

        mc = ModeConfig(
            mode=mode,
            rotative=RotativeConfig(layouts=rot_layouts, interval=rot_interval),
            reactive=ReactiveConfig(rules=rules, fallback_layout=fallback),
        )
        self.daemon.config.save_mode_config(mc)
        self.daemon.mode_controller.reload()

    def _add_reactive_rule(self):
        """Add a new process → layout rule via input dialogs."""
        process, ok = QInputDialog.getText(self, _("Add Rule"), _("Process name (e.g. Code.exe):"))
        if not ok or not process:
            return
        layouts = self.daemon.config.list_layouts()
        layout, ok = QInputDialog.getItem(self, _("Add Rule"), _("Layout:"), layouts, 0, False)
        if not ok or not layout:
            return
        self._list_rules.addItem(QListWidgetItem(f"{process} → {layout}"))

    def _del_reactive_rule(self):
        """Remove selected rule."""
        row = self._list_rules.currentRow()
        if row >= 0:
            self._list_rules.takeItem(row)

    def _on_mode_layout_switched(self, name: str):
        """Mode controller auto-switched the layout — sync UI."""
        if self._dirty:
            # Don't interrupt unsaved work — controller should be paused,
            # but guard defensively
            return
        self._combo_layout.blockSignals(True)
        idx = self._combo_layout.findText(name)
        if idx >= 0:
            self._combo_layout.setCurrentIndex(idx)
        self._combo_layout.blockSignals(False)
        self._load_layout()

    def _load_mode_ui(self):
        """Populate mode UI from config."""
        mc = self.daemon.config.mode_config
        {"static": self._r_static, "rotative": self._r_rotative, "reactive": self._r_reactive}.get(
            mc.mode, self._r_static
        ).setChecked(True)
        self._w_rotative.setVisible(mc.mode == "rotative")
        self._w_reactive.setVisible(mc.mode == "reactive")

        # Rotative: check layouts
        rot_set = set(mc.rotative.layouts)
        for i in range(self._list_rotate.count()):
            item = self._list_rotate.item(i)
            item.setCheckState(
                Qt.CheckState.Checked if item.text() in rot_set else Qt.CheckState.Unchecked
            )
        self._sp_rotate_interval.setValue(mc.rotative.interval)

        # Reactive: build rule list
        self._list_rules.clear()
        for rule in mc.reactive.rules:
            self._list_rules.addItem(QListWidgetItem(f"{rule.process} → {rule.layout}"))
        idx = self._combo_fallback.findText(mc.reactive.fallback_layout)
        if idx >= 0:
            self._combo_fallback.setCurrentIndex(idx)

    # ── Add elements ──

    def _add_text(self):
        el = LayoutElement(
            type="text",
            text="New Text",
            x=SCREEN_W // 2,
            y=SCREEN_H // 2,
            font_size=20,
            color=[255, 255, 255],
            anchor="mm",
        )
        self._scene.add_element(el)

    def _add_sensor(self):
        ids = list(self.daemon.sensors.read_all().keys())
        sid = ids[0] if ids else "cpu.percent"
        self._add_sensor_element(sid)

    def _add_sensor_from_list(self, item: QListWidgetItem):
        self._add_sensor_element(item.text())

    def _add_sensor_element(self, sensor_id: str):
        el = LayoutElement(
            type="sensor",
            sensor_id=sensor_id,
            x=SCREEN_W // 2,
            y=SCREEN_H // 2,
            font_size=18,
            color=[200, 220, 255],
            anchor="mm",
        )
        self._scene.add_element(el)

    def _add_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if path:
            el = LayoutElement(
                type="image", text=path, x=SCREEN_W // 2, y=SCREEN_H // 2
            )
            self._scene.add_element(el)

    def _add_shape(self):
        el = LayoutElement(
            type="shape",
            shape="rect",
            x=SCREEN_W // 2 - 40,
            y=SCREEN_H // 2 - 30,
            w=80,
            h=60,
            fill_color=[0, 200, 255],
            fill_alpha=200,
            stroke_width=2,
            stroke_color=[255, 255, 255],
        )
        self._scene.add_element(el)

    def _add_bar(self):
        ids = list(self.daemon.sensors.read_all().keys())
        sid = "cpu.percent" if "cpu.percent" in ids else (ids[0] if ids else "cpu.percent")
        el = LayoutElement(
            type="bar",
            sensor_id=sid,
            x=SCREEN_W // 2 - 80,
            y=SCREEN_H // 2,
            w=160,
            h=12,
            bar_fg_color=[0, 200, 255],
            bar_bg_color=[40, 40, 60],
            bar_thickness=12,
        )
        self._scene.add_element(el)

    def _add_arc_bar(self):
        ids = list(self.daemon.sensors.read_all().keys())
        sid = "cpu.percent" if "cpu.percent" in ids else (ids[0] if ids else "cpu.percent")
        el = LayoutElement(
            type="arc_bar",
            sensor_id=sid,
            x=SCREEN_W // 2 - 50,
            y=SCREEN_H // 2 - 50,
            w=100,
            h=100,
            bar_fg_color=[0, 200, 255],
            bar_bg_color=[40, 40, 60],
            bar_thickness=8,
            bar_start_angle=135,
            bar_sweep_angle=270,
        )
        self._scene.add_element(el)

    # ── Live preview ──

    def _on_element_changed(self, element) -> None:
        """Element property edited in panel — refresh visual."""
        self._scene.refresh_item(element)
        self._mark_dirty()

    def _on_background_changed(self, bg) -> None:
        """Handle background change: update scene and adjust preview speed."""
        self._scene.set_background(bg)
        self._adjust_preview_timer()
        self._mark_dirty()

    def _adjust_preview_timer(self) -> None:
        """Adjust preview timer speed.

        Preview is a visual aid — it doesn't need full screen_fps.
        Cap at ~10 FPS for video (enough to see motion), 0.5 FPS for static.
        Running heavier (sensor reads + full render + renderer's VideoCapture)
        at 60 FPS in the main thread would freeze the UI and race with the
        daemon's RenderThread over the same cv2.VideoCapture.
        """
        layout = self.daemon.config.active_layout
        if layout.background.type == "video" and layout.background.path:
            self._timer.setInterval(100)  # ~10 FPS — smooth enough for preview
        else:
            self._timer.setInterval(2000)  # 0.5 FPS for static backgrounds

    def _tick_preview(self):
        try:
            layout = self.daemon.config.active_layout
            # Use cached sensor values from the render thread when available,
            # avoiding a full sensor read (PDH+pynvml+psutil) every tick.
            rt = self.daemon._render_thread
            if rt is not None and rt._cached_values:
                values = rt._cached_values
            else:
                values = self.daemon.sensors.read_all()
            img = self.daemon.renderer.render_image(layout, values)
            self._preview.update_from_pil(img)
        except Exception:
            pass

    # ── Window lifecycle ──

    def showEvent(self, event):
        super().showEvent(event)

    def closeEvent(self, event):
        if self._dirty:
            reply = QMessageBox.question(
                self, _("Unsaved Changes"),
                _("Save changes before closing?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._save_layout()
            else:
                # User discarded changes
                self._dirty = False
        event.ignore()
        self.hide()
