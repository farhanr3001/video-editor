"""Visual FX Timing & Range Editor dialog.
Focuses strictly on the selected media item with a dedicated preview,
side effect property inspector, and single-clip ruler range dragger with visual clamping.
"""
from .theme_widgets import set_ui_style
import copy
import math
from .theme_widgets import ui_color
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QFont, QKeySequence, QShortcut, QLinearGradient
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QToolButton, QScrollArea, QFrame, QSizePolicy, QCheckBox, QComboBox
)

from .icons import lucide_icon
from .widgets import PreviewCanvas
from .model import TimelineItem
from .controls import SafeDoubleSpinBox, SafeComboBox
from .visual_fx import (
    evaluate_visual_fx,
    default_visual_fx,
    ZOOM_IN_EFFECTS,
    SUBSECTION_BY_EFFECT,
)


def format_smpte(seconds: float, fps: int = 60) -> str:
    """Format seconds into SMPTE timecode string HH:MM:SS:FF."""
    fps = max(1, fps)
    total_frames = round(max(0.0, seconds) * fps)
    ff = total_frames % fps
    total_seconds = total_frames // fps
    ss = total_seconds % 60
    total_minutes = total_seconds // 60
    mm = total_minutes % 60
    hh = total_minutes // 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


class CompactValueRow(QWidget):
    """Clean, compact value row for dialog controls with spinbox and optional slider."""
    edited = Signal(float)

    def __init__(self, low: float, high: float, default: float = 0.0, step: float = 0.1, parent=None):
        super().__init__(parent)
        self.low = low
        self.high = high
        self.updating = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.spin = SafeDoubleSpinBox()
        self.spin.setRange(low, high)
        self.spin.setDecimals(3 if step < 0.1 else 2 if step < 1 else 0)
        self.spin.setSingleStep(step)
        self.spin.setFixedWidth(78)
        self.spin.setValue(default)
        self.spin.valueChanged.connect(self._on_spin_changed)
        layout.addWidget(self.spin)

    def set_maximum(self, max_val: float):
        self.high = max(self.low + 0.01, float(max_val))
        self.spin.setMaximum(self.high)

    def set_value(self, val: float):
        self.updating = True
        self.spin.setValue(max(self.low, min(self.high, float(val))))
        self.updating = False

    def value(self) -> float:
        return self.spin.value()

    def _on_spin_changed(self, val: float):
        if not self.updating:
            self.edited.emit(val)


class VFXDialogPropertiesPanel(QWidget):
    """Full effects property inspector embedded inside the timing dialog."""
    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.updating = False
        self._setup_ui()

    def _emit_edit(self, key: str, val):
        if not self.updating:
            self.dialog.on_property_edited(key, val)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(10)

        # 1. Timing & Easing Section
        timing_box = QFrame()
        timing_box.setObjectName("dialogPropSection")
        set_ui_style(timing_box, '\n            QFrame#dialogPropSection {\n                background-color: @bg_panel;\n                border: 1px solid @border_subtle;\n                border-radius: 6px;\n            }\n        ')
        timing_vbox = QVBoxLayout(timing_box)
        timing_vbox.setContentsMargins(8, 8, 8, 8)
        timing_vbox.setSpacing(6)

        t_header = QLabel("Timing & Easing")
        t_header.setFont(QFont("Segoe UI", 9, QFont.Bold))
        set_ui_style(t_header, 'color: @info;')
        timing_vbox.addWidget(t_header)

        timing_form = QFormLayout()
        timing_form.setContentsMargins(0, 4, 0, 0)
        timing_form.setHorizontalSpacing(8)
        timing_form.setVerticalSpacing(6)
        timing_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.timing_mode = SafeComboBox()
        self.timing_mode.addItems(["At Clip Start", "At Clip End", "Custom / Playhead", "Entire Clip"])
        self.timing_mode.currentTextChanged.connect(self._on_timing_mode_changed)
        timing_form.addRow("Trigger", self.timing_mode)

        self.start_offset = CompactValueRow(0.0, self.dialog.item.duration, 0.0, 0.05)
        self.start_offset.edited.connect(lambda v: self._emit_edit("start_time", v))
        timing_form.addRow("Start Offset", self.start_offset)

        self.duration_row = CompactValueRow(0.05, self.dialog.item.duration, 1.0, 0.05)
        self.duration_row.edited.connect(lambda v: self._emit_edit("duration", v))
        timing_form.addRow("Duration (s)", self.duration_row)

        self.easing_combo = SafeComboBox()
        self.easing_combo.addItems(["Smooth", "Ease Out", "Ease In", "Linear", "Snap", "Bounce"])
        self.easing_combo.currentTextChanged.connect(lambda v: self._emit_edit("easing", v))
        timing_form.addRow("Curve", self.easing_combo)

        self.zoom_return_check = QCheckBox("Return to Normal (Ease Out)")
        self.zoom_return_check.setToolTip("Return to 1.0x neutral scale by easing out after zoom peak")
        self.zoom_return_check.toggled.connect(lambda v: self._emit_edit("zoom_return", v))
        timing_form.addRow("", self.zoom_return_check)

        self.zoom_hold_row = CompactValueRow(0.0, 5.0, 0.15, 0.05)
        self.zoom_hold_row.edited.connect(lambda v: self._emit_edit("zoom_hold_duration", v))
        timing_form.addRow("Hold (s)", self.zoom_hold_row)

        self.zoom_attack_row = CompactValueRow(0.01, 5.0, 0.25, 0.05)
        self.zoom_attack_row.edited.connect(lambda v: self._emit_edit("zoom_attack_duration", v))
        timing_form.addRow("Attack (s)", self.zoom_attack_row)

        timing_vbox.addLayout(timing_form)
        root.addWidget(timing_box)

        # 2. Zoom Settings Section
        self.zoom_box = QFrame()
        self.zoom_box.setObjectName("dialogPropSection")
        set_ui_style(self.zoom_box, timing_box._theme_style_template)
        zoom_vbox = QVBoxLayout(self.zoom_box)
        zoom_vbox.setContentsMargins(8, 8, 8, 8)
        zoom_vbox.setSpacing(6)

        z_header = QLabel("Zoom Parameters")
        z_header.setFont(QFont("Segoe UI", 9, QFont.Bold))
        set_ui_style(z_header, 'color: @success;')
        zoom_vbox.addWidget(z_header)

        zoom_form = QFormLayout()
        zoom_form.setContentsMargins(0, 4, 0, 0)
        zoom_form.setHorizontalSpacing(8)
        zoom_form.setVerticalSpacing(6)
        zoom_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.zoom_start = CompactValueRow(0.1, 5.0, 1.0, 0.05)
        self.zoom_start.edited.connect(lambda v: self._emit_edit("zoom_start", v))
        zoom_form.addRow("Start Scale", self.zoom_start)

        self.zoom_target = CompactValueRow(0.1, 5.0, 1.35, 0.05)
        self.zoom_target.edited.connect(lambda v: self._emit_edit("zoom_target", v))
        zoom_form.addRow("Target Scale", self.zoom_target)

        self.center_x = CompactValueRow(0.0, 1.0, 0.5, 0.01)
        self.center_x.edited.connect(lambda v: self._emit_edit("center_x", v))
        zoom_form.addRow("Focal X", self.center_x)

        self.center_y = CompactValueRow(0.0, 1.0, 0.5, 0.01)
        self.center_y.edited.connect(lambda v: self._emit_edit("center_y", v))
        zoom_form.addRow("Focal Y", self.center_y)

        # Focal preset chips
        chips = QWidget()
        chip_layout = QHBoxLayout(chips)
        chip_layout.setContentsMargins(0, 0, 0, 0)
        chip_layout.setSpacing(4)
        for label, (fx, fy) in [("Center", (0.5, 0.5)), ("Face", (0.5, 0.35)), ("Left", (0.3, 0.5)), ("Right", (0.7, 0.5))]:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda _, px=fx, py=fy: self._set_focal(px, py))
            chip_layout.addWidget(btn)
        zoom_form.addRow("Presets", chips)

        self.bounce_amp = CompactValueRow(0.0, 1.0, 0.25, 0.02)
        self.bounce_amp.edited.connect(lambda v: self._emit_edit("bounce_amplitude", v))
        zoom_form.addRow("Bounce", self.bounce_amp)

        self.shake_int = CompactValueRow(0.0, 80.0, 15.0, 1.0)
        self.shake_int.edited.connect(lambda v: self._emit_edit("shake_intensity", v))
        zoom_form.addRow("Arrival Shake", self.shake_int)

        zoom_vbox.addLayout(zoom_form)
        root.addWidget(self.zoom_box)

        # 3. Camera Movement Section
        self.cam_box = QFrame()
        self.cam_box.setObjectName("dialogPropSection")
        set_ui_style(self.cam_box, timing_box._theme_style_template)
        cam_vbox = QVBoxLayout(self.cam_box)
        cam_vbox.setContentsMargins(8, 8, 8, 8)
        cam_vbox.setSpacing(6)

        c_header = QLabel("Camera Movement")
        c_header.setFont(QFont("Segoe UI", 9, QFont.Bold))
        set_ui_style(c_header, 'color: @warning;')
        cam_vbox.addWidget(c_header)

        cam_form = QFormLayout()
        cam_form.setContentsMargins(0, 4, 0, 0)
        cam_form.setHorizontalSpacing(8)
        cam_form.setVerticalSpacing(6)
        cam_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.pan_x_start = CompactValueRow(-1.0, 1.0, 0.0, 0.01)
        self.pan_x_start.edited.connect(lambda v: self._emit_edit("pan_x_start", v))
        cam_form.addRow("Pan X Start", self.pan_x_start)

        self.pan_x_end = CompactValueRow(-1.0, 1.0, 0.15, 0.01)
        self.pan_x_end.edited.connect(lambda v: self._emit_edit("pan_x_end", v))
        cam_form.addRow("Pan X End", self.pan_x_end)

        self.pan_y_start = CompactValueRow(-1.0, 1.0, 0.0, 0.01)
        self.pan_y_start.edited.connect(lambda v: self._emit_edit("pan_y_start", v))
        cam_form.addRow("Pan Y Start", self.pan_y_start)

        self.pan_y_end = CompactValueRow(-1.0, 1.0, 0.0, 0.01)
        self.pan_y_end.edited.connect(lambda v: self._emit_edit("pan_y_end", v))
        cam_form.addRow("Pan Y End", self.pan_y_end)

        self.tilt_angle = CompactValueRow(-45.0, 45.0, 0.0, 0.5)
        self.tilt_angle.edited.connect(lambda v: self._emit_edit("tilt_angle", v))
        cam_form.addRow("Tilt (°)", self.tilt_angle)

        self.rot_angle = CompactValueRow(-180.0, 180.0, 0.0, 1.0)
        self.rot_angle.edited.connect(lambda v: self._emit_edit("rotation_angle", v))
        cam_form.addRow("Rotation (°)", self.rot_angle)

        self.handheld_speed = CompactValueRow(0.1, 5.0, 1.2, 0.1)
        self.handheld_speed.edited.connect(lambda v: self._emit_edit("handheld_speed", v))
        cam_form.addRow("Speed", self.handheld_speed)

        self.handheld_amt = CompactValueRow(1.0, 50.0, 14.0, 1.0)
        self.handheld_amt.edited.connect(lambda v: self._emit_edit("handheld_amount", v))
        cam_form.addRow("Wobble (px)", self.handheld_amt)

        self.whip_dir = SafeComboBox()
        self.whip_dir.addItems(["Right", "Left", "Up", "Down"])
        self.whip_dir.currentTextChanged.connect(lambda v: self._emit_edit("whip_direction", v))
        cam_form.addRow("Whip Dir", self.whip_dir)

        cam_vbox.addLayout(cam_form)
        root.addWidget(self.cam_box)

        # 4. Shake / Impact Section
        self.shake_box = QFrame()
        self.shake_box.setObjectName("dialogPropSection")
        set_ui_style(self.shake_box, timing_box._theme_style_template)
        shake_vbox = QVBoxLayout(self.shake_box)
        shake_vbox.setContentsMargins(8, 8, 8, 8)
        shake_vbox.setSpacing(6)

        s_header = QLabel("Shake & Impact")
        s_header.setFont(QFont("Segoe UI", 9, QFont.Bold))
        set_ui_style(s_header, 'color: @danger;')
        shake_vbox.addWidget(s_header)

        shake_form = QFormLayout()
        shake_form.setContentsMargins(0, 4, 0, 0)
        shake_form.setHorizontalSpacing(8)
        shake_form.setVerticalSpacing(6)
        shake_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.amp_x = CompactValueRow(0.0, 100.0, 20.0, 1.0)
        self.amp_x.edited.connect(lambda v: self._emit_edit("shake_amplitude_x", v))
        shake_form.addRow("Amp X", self.amp_x)

        self.amp_y = CompactValueRow(0.0, 100.0, 15.0, 1.0)
        self.amp_y.edited.connect(lambda v: self._emit_edit("shake_amplitude_y", v))
        shake_form.addRow("Amp Y", self.amp_y)

        self.amp_rot = CompactValueRow(0.0, 20.0, 2.0, 0.2)
        self.amp_rot.edited.connect(lambda v: self._emit_edit("shake_rotation", v))
        shake_form.addRow("Rot Shake", self.amp_rot)

        self.freq = CompactValueRow(1.0, 40.0, 15.0, 1.0)
        self.freq.edited.connect(lambda v: self._emit_edit("shake_frequency", v))
        shake_form.addRow("Freq (Hz)", self.freq)

        self.decay_combo = SafeComboBox()
        self.decay_combo.addItems(["Exponential", "Linear", "Constant"])
        self.decay_combo.currentTextChanged.connect(lambda v: self._emit_edit("shake_decay", v))
        shake_form.addRow("Decay", self.decay_combo)

        shake_vbox.addLayout(shake_form)
        root.addWidget(self.shake_box)

        # 5. Reset to defaults button
        btn_reset = QPushButton("Reset Effect Defaults")
        btn_reset.setFixedHeight(26)
        btn_reset.setIcon(lucide_icon("rotate-ccw", "#96989f", 13))
        btn_reset.clicked.connect(self.dialog.reset_to_defaults)
        root.addWidget(btn_reset)
        root.addStretch()

        self.sync_from_effect()

    def _set_focal(self, fx: float, fy: float):
        self.center_x.set_value(fx)
        self.center_y.set_value(fy)
        self._emit_edit("center_x", fx)
        self._emit_edit("center_y", fy)

    def _on_timing_mode_changed(self, text: str):
        if self.updating:
            return
        mapping = {"At Clip Start": "clip_start", "At Clip End": "clip_end", "Custom / Playhead": "playhead", "Entire Clip": "entire_clip"}
        mode = mapping.get(text, "clip_start")
        self._emit_edit("timing_mode", mode)
        self.start_offset.setEnabled(mode == "playhead")
        self.duration_row.setEnabled(mode != "entire_clip")

    def sync_from_effect(self):
        """Populate controls from dialog effect state."""
        self.updating = True
        effect = self.dialog.effect
        name = effect.get("name", "")
        sub = effect.get("subsection", SUBSECTION_BY_EFFECT.get(name, "Zooms"))

        # Visible section groups
        self.zoom_box.setVisible(sub == "Zooms")
        self.cam_box.setVisible(sub == "Camera Movement")
        self.shake_box.setVisible(sub == "Shake / Impact Effects" or "Shake" in name)

        # Return to Normal is strictly for zoom-in effects
        is_zoom_in = (sub == "Zooms" and name in ZOOM_IN_EFFECTS)
        has_ret = is_zoom_in and bool(effect.get("zoom_return", False))
        self.zoom_return_check.setVisible(is_zoom_in)
        self.zoom_hold_row.setVisible(has_ret)
        self.zoom_attack_row.setVisible(has_ret)

        # Clamp max duration to media length
        clip_dur = self.dialog.item.duration
        self.start_offset.set_maximum(clip_dur)
        self.duration_row.set_maximum(clip_dur)

        dur_val = float(effect.get("duration", 1.0))
        self.zoom_hold_row.set_maximum(dur_val)
        self.zoom_attack_row.set_maximum(dur_val)

        mode_map = {"clip_start": "At Clip Start", "clip_end": "At Clip End", "playhead": "Custom / Playhead", "entire_clip": "Entire Clip"}
        self.timing_mode.setCurrentText(mode_map.get(effect.get("timing_mode", "clip_start"), "At Clip Start"))
        self.start_offset.set_value(float(effect.get("start_time", 0.0)))
        self.duration_row.set_value(float(effect.get("duration", 1.0)))
        self.easing_combo.setCurrentText(effect.get("easing", "Smooth"))

        if is_zoom_in:
            self.zoom_return_check.setChecked(bool(effect.get("zoom_return", False)))
            hold_v = float(effect.get("zoom_hold_duration", 0.15))
            self.zoom_hold_row.set_value(hold_v)
            def_att = round(max(0.01, (dur_val - hold_v) / 2.0), 3)
            self.zoom_attack_row.set_value(float(effect.get("zoom_attack_duration", def_att)))

        if sub == "Zooms":
            self.zoom_start.set_value(float(effect.get("zoom_start", 1.0)))
            self.zoom_target.set_value(float(effect.get("zoom_target", 1.35)))
            self.center_x.set_value(float(effect.get("center_x", 0.5)))
            self.center_y.set_value(float(effect.get("center_y", 0.5)))
            self.bounce_amp.set_value(float(effect.get("bounce_amplitude", 0.25)))
            self.shake_int.set_value(float(effect.get("shake_intensity", 15.0)))

        elif sub == "Camera Movement":
            self.pan_x_start.set_value(float(effect.get("pan_x_start", 0.0)))
            self.pan_x_end.set_value(float(effect.get("pan_x_end", 0.15)))
            self.pan_y_start.set_value(float(effect.get("pan_y_start", 0.0)))
            self.pan_y_end.set_value(float(effect.get("pan_y_end", 0.0)))
            self.tilt_angle.set_value(float(effect.get("tilt_angle", 0.0)))
            self.rot_angle.set_value(float(effect.get("rotation_angle", 0.0)))
            self.handheld_speed.set_value(float(effect.get("handheld_speed", 1.2)))
            self.handheld_amt.set_value(float(effect.get("handheld_amount", 14.0)))
            self.whip_dir.setCurrentText(effect.get("whip_direction", "Right"))

        elif sub == "Shake / Impact Effects" or "Shake" in name:
            self.amp_x.set_value(float(effect.get("shake_amplitude_x", 20.0)))
            self.amp_y.set_value(float(effect.get("shake_amplitude_y", 15.0)))
            self.amp_rot.set_value(float(effect.get("shake_rotation", 2.0)))
            self.freq.set_value(float(effect.get("shake_frequency", 15.0)))
            self.decay_combo.setCurrentText(effect.get("shake_decay", "Exponential"))

        self.updating = False


class VFXRangeTimelineWidget(QWidget):
    """Single-clip timeline ruler and track with draggable handles, range body, and visual clamping for ease-out."""
    rangeChanged = Signal(float, float)  # start_time, duration
    seekRequested = Signal(float)        # local_time

    def __init__(self, dialog, parent=None):
        super().__init__(parent)
        self.dialog = dialog
        self.setMinimumHeight(125)
        self.setFixedHeight(130)
        self.setMouseTracking(True)
        self.drag_mode = None  # None, "in", "out", "range", "playhead"
        self.drag_start_x = 0.0
        self.drag_start_t = 0.0
        self.drag_offset_t = 0.0

    @property
    def clip_duration(self) -> float:
        return max(0.05, float(self.dialog.item.duration))

    @property
    def start_time(self) -> float:
        return max(0.0, float(self.dialog.effect.get("start_time", 0.0)))

    @property
    def duration(self) -> float:
        return max(0.05, min(self.clip_duration, float(self.dialog.effect.get("duration", 1.0))))

    @property
    def end_time(self) -> float:
        return min(self.clip_duration, self.start_time + self.duration)

    @property
    def has_return_clamping(self) -> bool:
        effect = self.dialog.effect
        name = effect.get("name", "")
        sub = effect.get("subsection", SUBSECTION_BY_EFFECT.get(name, "Zooms"))
        return bool(effect.get("zoom_return", False)) and sub == "Zooms" and name in ZOOM_IN_EFFECTS

    def x_margin(self) -> float:
        return 96.0

    def time_to_x(self, t: float) -> float:
        m = self.x_margin()
        w = max(1.0, self.width() - m - 18.0)
        return m + (max(0.0, min(self.clip_duration, t)) / self.clip_duration) * w

    def x_to_time(self, x: float) -> float:
        m = self.x_margin()
        w = max(1.0, self.width() - m - 18.0)
        ratio = (x - m) / w
        return max(0.0, min(self.clip_duration, ratio * self.clip_duration))

    @property
    def attack_time(self) -> float:
        dur = self.duration
        hold_s = self.hold_time
        r_avail = max(0.02, dur - hold_s)
        val = self.dialog.effect.get("zoom_attack_duration")
        if val is not None:
            return max(0.01, min(r_avail - 0.01, float(val)))
        return r_avail / 2.0

    @property
    def hold_time(self) -> float:
        dur = self.duration
        val = max(0.0, float(self.dialog.effect.get("zoom_hold_duration", 0.15)))
        return min(val, max(0.0, dur - 0.02))

    def in_handle_rect(self) -> QRectF:
        x = self.time_to_x(self.start_time)
        return QRectF(x - 5.0, 22.0, 10.0, 13.0)

    def out_handle_rect(self) -> QRectF:
        x = self.time_to_x(self.end_time)
        return QRectF(x - 5.0, 22.0, 10.0, 13.0)

    def range_bar_rect(self) -> QRectF:
        x1 = self.time_to_x(self.start_time)
        x2 = self.time_to_x(self.end_time)
        return QRectF(x1, 26.0, max(0.0, x2 - x1), 7.0)

    def hold_pill_rect(self) -> QRectF:
        if not self.has_return_clamping:
            return QRectF()
        x1 = self.time_to_x(self.start_time + self.attack_time)
        x2 = self.time_to_x(self.start_time + self.attack_time + self.hold_time)
        return QRectF(x1, 21.0, max(12.0, x2 - x1), 14.0)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        m = self.x_margin()

        # Background
        p.fillRect(0, 0, w, h, ui_color('bg_main'))

        # Left Header Sidebar
        p.fillRect(0, 0, int(m), h, ui_color('bg_panel'))
        p.setPen(QPen(ui_color('border_subtle'), 1))
        p.drawLine(int(m), 0, int(m), h)

        # Current local playhead timecode
        fps = self.dialog.project.settings.fps
        curr_t = getattr(self.dialog, "position", 0.0)
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        p.setPen(ui_color('text_main'))
        p.drawText(QRectF(8, 6, m - 16, 22), Qt.AlignLeft | Qt.AlignVCenter, format_smpte(curr_t, fps))

        # Track V1 header badge
        p.setPen(QPen(QColor("#3d8cff"), 1))
        p.setBrush(QColor(61, 140, 255, 30))
        p.drawRoundedRect(QRectF(8, 48, 28, 20), 3, 3)
        p.setFont(QFont("Segoe UI", 8, QFont.Bold))
        p.setPen(ui_color('info'))
        p.drawText(QRectF(8, 48, 28, 20), Qt.AlignCenter, "V1")

        # Track A1 header badge if audio exists
        has_audio = bool(self.dialog.media and (self.dialog.media.has_audio or self.dialog.media.kind == "audio"))
        if has_audio:
            p.setPen(QPen(QColor("#50df74"), 1))
            p.setBrush(QColor(80, 223, 116, 30))
            p.drawRoundedRect(QRectF(8, 96, 28, 20), 3, 3)
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.setPen(ui_color('success'))
            p.drawText(QRectF(8, 96, 28, 20), Qt.AlignCenter, "A1")

        # Ruler Area (0 to 35) - Upper part (0..24) is clear for scrubbing playhead
        ruler_bg = ui_color('bg_panel')
        p.fillRect(QRectF(m, 0, w - m, 35), ruler_bg)
        p.setPen(QPen(ui_color('border_subtle'), 1))
        p.drawLine(int(m), 35, w, 35)

        # Draw Ruler Ticks
        dur = self.clip_duration
        step = 0.5 if dur <= 3.0 else 1.0 if dur <= 10.0 else 2.0 if dur <= 30.0 else 5.0
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(ui_color('text_sub'))
        t = 0.0
        while t <= dur + 1e-5:
            x = self.time_to_x(t)
            is_major = (round(t / step) % 2 == 0) or (dur <= 4.0)
            tick_h = 10 if is_major else 5
            p.drawLine(QPointF(x, 35 - tick_h), QPointF(x, 35))
            if is_major:
                p.drawText(QPointF(x + 3, 15), f"{t:.1f}s")
            t += step

        # Draggable Thin Clamper Bar on Ruler Bottom Line (y: 26 to 33)
        x_in = self.time_to_x(self.start_time)
        x_out = self.time_to_x(self.end_time)
        range_w = max(0.0, x_out - x_in)

        # Visual Clamping calculation for Return to Normal
        is_return = self.has_return_clamping
        if is_return and range_w > 12:
            x_peak1 = self.time_to_x(self.start_time + self.attack_time)
            x_peak2 = self.time_to_x(self.start_time + self.attack_time + self.hold_time)

            # Phase 1: Attack / Zoom In (Thin blue strip along bottom line)
            p.setPen(QPen(QColor("#3d8cff"), 1.0))
            p.setBrush(QColor(61, 140, 255, 170))
            p.drawRoundedRect(QRectF(x_in, 26, max(2.0, x_peak1 - x_in), 7), 2, 2)

            # Phase 2: Peak Hold (Vibrant Green Draggable Pill at y: 21 to 34)
            p.setPen(QPen(QColor("#ffffff"), 1.2))
            p.setBrush(QColor(80, 223, 116, 230))
            hold_rect = self.hold_pill_rect()
            p.drawRoundedRect(hold_rect, 3, 3)
            if hold_rect.width() >= 32:
                p.setFont(QFont("Segoe UI", 7, QFont.Bold))
                p.setPen(QColor("#082210"))
                p.drawText(hold_rect, Qt.AlignCenter, "HOLD")
            elif hold_rect.width() >= 14:
                # Grip lines
                p.setPen(QPen(QColor("#082210"), 1.2))
                cx = hold_rect.center().x()
                p.drawLine(QPointF(cx - 2, 24), QPointF(cx - 2, 31))
                p.drawLine(QPointF(cx + 2, 24), QPointF(cx + 2, 31))

            # Phase 3: Ease Out Return to 1.0x (Thin blue strip along bottom line)
            p.setPen(QPen(QColor("#3d8cff"), 1.0))
            p.setBrush(QColor(61, 140, 255, 140))
            p.drawRoundedRect(QRectF(x_peak2, 26, max(2.0, x_out - x_peak2), 7), 2, 2)
        else:
            # Standard connecting thin bar along bottom line of ruler
            p.setPen(QPen(QColor("#3d8cff"), 1.2))
            p.setBrush(QColor(61, 140, 255, 180))
            p.drawRoundedRect(QRectF(x_in, 26, range_w, 7), 2, 2)

        # IN Handle (Left Tab at y: 22 to 35)
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.setBrush(QColor("#3d8cff"))
        p.drawRoundedRect(QRectF(x_in - 4.0, 22.0, 8.0, 13.0), 2.5, 2.5)
        p.setPen(QColor("#ffffff"))
        p.drawLine(QPointF(x_in, 25), QPointF(x_in, 32))

        # OUT Handle (Right Tab at y: 22 to 35)
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.setBrush(QColor("#3d8cff"))
        p.drawRoundedRect(QRectF(x_out - 4.0, 22.0, 8.0, 13.0), 2.5, 2.5)
        p.setPen(QColor("#ffffff"))
        p.drawLine(QPointF(x_out, 25), QPointF(x_out, 32))

        # -------------------------------------------------------------
        # V1 Clip Track Lane (Separated into Top Filename Band & Bottom Effect Band)
        # -------------------------------------------------------------
        clip_x1 = self.time_to_x(0.0)
        clip_x2 = self.time_to_x(dur)
        clip_w = max(1.0, clip_x2 - clip_x1)

        # Base track lane bounding box
        track_rect = QRectF(clip_x1, 38, clip_w, 48)
        p.setPen(QPen(ui_color('border_subtle'), 1))
        p.setBrush(ui_color('bg_panel'))
        p.drawRoundedRect(track_rect, 4, 4)

        # 1. TOP BAND (y: 39 to 55): Media filename in crisp muted text with film icon
        top_header_rect = QRectF(clip_x1 + 1, 39, clip_w - 2, 16)
        p.fillRect(top_header_rect, ui_color('bg_surface'))
        clip_name = self.dialog.media.name if self.dialog.media else "Media Clip"
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(ui_color('text_sub'))
        p.drawText(top_header_rect.adjusted(8, 0, -8, 0), Qt.AlignLeft | Qt.AlignVCenter, f"🎬  {clip_name}")

        # 2. BOTTOM BAND (y: 57 to 83): Visual FX Active Clamp Pill
        effect_name = self.dialog.effect.get("name", "Visual FX")
        fx_pill_rect = QRectF(x_in, 57, range_w, 26)

        if is_return and range_w > 20:
            x_p1 = self.time_to_x(self.start_time + self.attack_time)
            x_p2 = self.time_to_x(self.start_time + self.attack_time + self.hold_time)

            # Attack section
            p.setPen(QPen(QColor(61, 140, 255, 220), 1))
            p.setBrush(QColor(61, 140, 255, 60))
            p.drawRoundedRect(QRectF(x_in, 57, max(1.0, x_p1 - x_in), 26), 3, 3)

            # Peak hold section
            p.setPen(QPen(QColor(80, 223, 116, 220), 1.5))
            p.setBrush(QColor(80, 223, 116, 80))
            p.drawRoundedRect(QRectF(x_p1, 57, max(1.0, x_p2 - x_p1), 26), 3, 3)

            # Ease out section
            p.setPen(QPen(QColor(61, 140, 255, 200), 1, Qt.DashLine))
            p.setBrush(QColor(61, 140, 255, 45))
            p.drawRoundedRect(QRectF(x_p2, 57, max(1.0, x_out - x_p2), 26), 3, 3)

            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.setPen(ui_color('text_main'))
            p.drawText(fx_pill_rect.adjusted(8, 0, -8, 0), Qt.AlignLeft | Qt.AlignVCenter,
                       f"★ {effect_name}  ↗ Peak Hold ↘ 1.0x")
        else:
            # Solid standard visual FX pill
            p.setPen(QPen(QColor(61, 140, 255, 200), 1.2))
            p.setBrush(ui_color('bg_selected'))
            p.drawRoundedRect(fx_pill_rect, 4, 4)
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.setPen(ui_color('text_selected'))
            p.drawText(fx_pill_rect.adjusted(8, 0, -8, 0), Qt.AlignLeft | Qt.AlignVCenter,
                       f"★ {effect_name} ({self.duration:.2f}s)")

        # -------------------------------------------------------------
        # A1 Audio Track Lane (if present)
        # -------------------------------------------------------------
        if has_audio:
            aud_rect = QRectF(clip_x1, 90, clip_w, 32)
            p.setPen(QPen(ui_color('border_subtle'), 1))
            p.setBrush(ui_color('success_bg'))
            p.drawRoundedRect(aud_rect, 4, 4)
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(ui_color('success'))
            p.drawText(aud_rect.adjusted(8, 0, -8, 0), Qt.AlignLeft | Qt.AlignVCenter, "Audio Track")

        # Playhead Line spanning Ruler and Tracks
        px = self.time_to_x(curr_t)
        p.setPen(QPen(QColor("#ed3545"), 1.5))
        p.drawLine(QPointF(px, 0), QPointF(px, h))

        # Playhead Head Marker on Ruler (y: 0 to 14)
        poly = QPolygonF([
            QPointF(px - 5, 0),
            QPointF(px + 5, 0),
            QPointF(px + 5, 8),
            QPointF(px, 14),
            QPointF(px - 5, 8)
        ])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ed3545"))
        p.drawPolygon(poly)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.position()
        x = pos.x()
        y = pos.y()
        self.drag_start_x = x
        self.drag_start_t = self.x_to_time(x)

        # Upper ruler area (y < 22) is dedicated to playhead scrubbing with zero interference
        if y < 22:
            self.drag_mode = "playhead"
            self.seekRequested.emit(self.drag_start_t)
            return

        # Check IN handle
        if self.in_handle_rect().adjusted(-3, -3, 3, 3).contains(pos):
            self.drag_mode = "in"
            return

        # Check OUT handle
        if self.out_handle_rect().adjusted(-3, -3, 3, 3).contains(pos):
            self.drag_mode = "out"
            return

        # Check HOLD pill on ruler (drags hold location within effect)
        if self.has_return_clamping and self.hold_pill_rect().adjusted(-2, -3, 2, 3).contains(pos):
            self.drag_mode = "hold"
            self.drag_offset_t = self.drag_start_t - (self.start_time + self.attack_time)
            return

        # Check Range body (thin clamper bar on bottom line of ruler)
        if y <= 36 and self.range_bar_rect().adjusted(-2, -3, 2, 3).contains(pos):
            self.drag_mode = "range"
            self.drag_offset_t = self.drag_start_t - self.start_time
            return

        # Anywhere else: seek playhead
        self.drag_mode = "playhead"
        self.seekRequested.emit(self.drag_start_t)

    def mouseMoveEvent(self, event):
        pos = event.position()
        x = pos.x()
        y = pos.y()

        if self.drag_mode:
            t = self.x_to_time(x)
            clip_dur = self.clip_duration
            if self.drag_mode == "in":
                max_in = max(0.0, self.end_time - 0.05)
                new_in = max(0.0, min(max_in, t))
                new_dur = max(0.05, self.end_time - new_in)
                self.rangeChanged.emit(new_in, new_dur)
            elif self.drag_mode == "out":
                new_end = max(self.start_time + 0.05, min(clip_dur, t))
                new_dur = max(0.05, new_end - self.start_time)
                self.rangeChanged.emit(self.start_time, new_dur)
            elif self.drag_mode == "hold":
                new_hold_start = t - self.drag_offset_t
                max_att = max(0.01, self.duration - self.hold_time - 0.01)
                new_att = max(0.01, min(max_att, new_hold_start - self.start_time))
                new_att = round(new_att, 3)
                self.dialog.on_property_edited("zoom_attack_duration", new_att)
                if getattr(self.dialog, "props_panel", None):
                    self.dialog.props_panel.sync_from_effect()
            elif self.drag_mode == "range":
                curr_dur = self.duration
                new_in = max(0.0, min(clip_dur - curr_dur, t - self.drag_offset_t))
                self.rangeChanged.emit(new_in, curr_dur)
            elif self.drag_mode == "playhead":
                self.seekRequested.emit(t)
            self.update()
            return

        # Hover Cursor Feedback
        if self.in_handle_rect().contains(pos) or self.out_handle_rect().contains(pos):
            self.setCursor(Qt.SizeHorCursor)
            self.setToolTip("Drag handle to adjust effect timing")
        elif self.has_return_clamping and self.hold_pill_rect().contains(pos):
            self.setCursor(Qt.SizeAllCursor)
            self.setToolTip("Drag to position Hold section within effect")
        elif y >= 22 and y <= 36 and self.range_bar_rect().contains(pos):
            self.setCursor(Qt.SizeAllCursor)
            self.setToolTip("Drag to slide effect range")
        elif y <= 36:
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip("Click or drag to scrub playhead")
        else:
            self.setCursor(Qt.ArrowCursor)
            self.setToolTip("")

    def mouseReleaseEvent(self, event):
        self.drag_mode = None
        self.update()


class VFXTimingDialog(QDialog):
    """Popout modal dialog providing focused media timeline scrubbing, range dragging, video preview,
    and a dedicated side effect properties inspector."""
    def __init__(self, owner, item: TimelineItem, effect: dict, parent=None):
        super().__init__(parent or owner)
        self.owner = owner
        self.original_effect_backup = copy.deepcopy(effect)
        self.original_start = float(effect.get("start_time", 0.0))
        self.original_dur = float(effect.get("duration", 1.0))
        self.effect = effect
        self.position = 0.0
        self.loop_range = False
        self.timeline_widget = None
        self.props_panel = None

        # Isolated project copy for this single clip
        self.project = copy.copy(owner.project)
        self.project.settings = copy.deepcopy(owner.project.settings)
        self.item = copy.deepcopy(item)
        self.item.start = 0.0
        self.item.muted = False
        self.media = copy.deepcopy(owner.project.media_by_id(item.media_id))
        self.project.timeline = [self.item]
        self.project.captions = []
        self.project.media = [self.media] if self.media else []
        self.project.playhead = 0.0
        self.project.video_tracks = [item.track]
        self.project.audio_tracks = ["__source_audio"]
        self.project.track_states = {item.track: {"visible": True}, "__source_audio": {"visible": True}}

        if self.media and self.media.has_audio:
            self.project.timeline.append(
                TimelineItem("__source_audio", item.media_id, "__source_audio", 0, item.duration,
                             item.in_point, speed=item.speed, gain_db=item.gain_db)
            )

        self.settings = getattr(owner, "settings", {})
        self.proxies = getattr(owner, "proxies", {})

        effect_name = effect.get("name", "Visual FX")
        self.setWindowTitle(f"Visual FX Timing & Range · {effect_name} · {self.media.name if self.media else 'Clip'}")
        self.resize(980, 680)
        self.setMinimumSize(820, 560)
        set_ui_style(self, '\n            QDialog {\n                background-color: @bg_panel;\n                color: @text_main;\n            }\n            QLabel {\n                color: @text_main;\n            }\n            QPushButton, QToolButton {\n                background-color: @bg_panel;\n                color: @text_main;\n                border: 1px solid @border_subtle;\n                border-radius: 4px;\n                padding: 4px 10px;\n            }\n            QPushButton:hover, QToolButton:hover {\n                background-color: @bg_hover;\n                border-color: @border_subtle;\n            }\n            QPushButton:pressed, QToolButton:pressed {\n                background-color: @accent;\n                color: @accent_text;\n            }\n            QPushButton:checked, QToolButton:checked {\n                background-color: @bg_selected;\n                border-color: @accent;\n            }\n            QScrollArea {\n                border: none;\n                background-color: transparent;\n            }\n        ')

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(8)

        # 1. Top Header Info Bar (IN, OUT, DURATION timecodes)
        header = QFrame()
        set_ui_style(header, 'background-color: @bg_panel; border-radius: 6px; padding: 6px 14px;')
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(18)

        self.label_in = QLabel("IN 00:00:00:00")
        self.label_in.setFont(QFont("Consolas", 11, QFont.Bold))
        set_ui_style(self.label_in, 'color: @info;')

        self.label_out = QLabel("OUT 00:00:01:00")
        self.label_out.setFont(QFont("Consolas", 11, QFont.Bold))
        set_ui_style(self.label_out, 'color: @info;')

        self.label_duration = QLabel("DURATION 00:00:01:00")
        self.label_duration.setFont(QFont("Consolas", 11, QFont.Bold))
        set_ui_style(self.label_duration, 'color: @success;')

        header_layout.addWidget(self.label_in)
        header_layout.addWidget(self.label_out)
        header_layout.addStretch()

        badge_sub = effect.get("subsection", SUBSECTION_BY_EFFECT.get(effect_name, "Visual FX"))
        sub_label = QLabel(f"{effect_name} · {badge_sub}")
        sub_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        set_ui_style(sub_label, 'color: @text_sub;')
        header_layout.addWidget(sub_label)
        header_layout.addSpacing(12)
        header_layout.addWidget(self.label_duration)

        root.addWidget(header)

        # 2. Middle Split: Video Preview + Transport on Left, Properties Panel on Right
        middle_split = QHBoxLayout()
        middle_split.setContentsMargins(0, 0, 0, 0)
        middle_split.setSpacing(10)

        # Left Column: Preview Canvas & Transport
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(6)

        self.preview = PreviewCanvas()
        self.preview.set_project(self.project)
        self.preview.set_read_only(True)
        self.preview.set_transform_controls_visible(False)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_col.addWidget(self.preview, 1)

        # Transport Bar beneath preview
        transport_bar = QHBoxLayout()
        transport_bar.setContentsMargins(4, 2, 4, 2)
        transport_bar.setSpacing(6)

        self.label_curr_pos = QLabel("00:00:00:00")
        self.label_curr_pos.setFont(QFont("Consolas", 10, QFont.Bold))
        self.label_curr_pos.setMinimumWidth(86)
        set_ui_style(self.label_curr_pos, 'color: @text_main;')
        transport_bar.addWidget(self.label_curr_pos)
        transport_bar.addSpacing(10)

        self.btn_jump_in = QToolButton()
        self.btn_jump_in.setIcon(lucide_icon("skip-back", "#ffffff", 14))
        self.btn_jump_in.setToolTip("Jump to Range IN Point")
        self.btn_jump_in.clicked.connect(self.jump_to_in)
        transport_bar.addWidget(self.btn_jump_in)

        self.btn_step_back = QToolButton()
        self.btn_step_back.setIcon(lucide_icon("chevron-left", "#ffffff", 14))
        self.btn_step_back.setToolTip("Step Back 1 Frame")
        self.btn_step_back.clicked.connect(lambda: self.step_frame(-1))
        transport_bar.addWidget(self.btn_step_back)

        self.btn_play = QPushButton()
        self.btn_play.setIcon(lucide_icon("play", "#ffffff", 14))
        self.btn_play.setText(" Play")
        self.btn_play.setFixedWidth(78)
        self.btn_play.clicked.connect(self.toggle_play)
        transport_bar.addWidget(self.btn_play)

        self.btn_step_fwd = QToolButton()
        self.btn_step_fwd.setIcon(lucide_icon("chevron-right", "#ffffff", 14))
        self.btn_step_fwd.setToolTip("Step Forward 1 Frame")
        self.btn_step_fwd.clicked.connect(lambda: self.step_frame(1))
        transport_bar.addWidget(self.btn_step_fwd)

        self.btn_jump_out = QToolButton()
        self.btn_jump_out.setIcon(lucide_icon("skip-forward", "#ffffff", 14))
        self.btn_jump_out.setToolTip("Jump to Range OUT Point")
        self.btn_jump_out.clicked.connect(self.jump_to_out)
        transport_bar.addWidget(self.btn_jump_out)

        self.btn_loop = QToolButton()
        self.btn_loop.setIcon(lucide_icon("repeat", "#ffffff", 14))
        self.btn_loop.setCheckable(True)
        self.btn_loop.setToolTip("Toggle Loop Range Playback")
        self.btn_loop.toggled.connect(self.set_loop_range)
        transport_bar.addWidget(self.btn_loop)

        self.btn_play_range = QPushButton("Play Range")
        self.btn_play_range.setIcon(lucide_icon("play-circle", "#50df74", 14))
        self.btn_play_range.setToolTip("Play strictly within the In/Out Visual FX range")
        self.btn_play_range.clicked.connect(self.play_in_out_range)
        transport_bar.addWidget(self.btn_play_range)

        transport_bar.addStretch()

        # Quick preset buttons
        preset_bar = QHBoxLayout()
        preset_bar.setSpacing(6)
        preset_bar.addWidget(QLabel("Duration presets:"))
        for dur_val, txt in [(0.2, "0.2s"), (0.5, "0.5s"), (1.0, "1.0s"), (2.0, "2.0s"), (self.item.duration, "Entire Clip")]:
            btn = QPushButton(txt)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, s=dur_val: self.apply_preset_duration(s))
            preset_bar.addWidget(btn)

        preset_bar.addStretch()
        left_col.addLayout(transport_bar)
        left_col.addLayout(preset_bar)
        middle_split.addLayout(left_col, 1)

        # 3. Timeline Ruler & Dragger Widget (instantiated early so callbacks have access)
        self.timeline_widget = VFXRangeTimelineWidget(self)
        self.timeline_widget.rangeChanged.connect(self.on_range_changed)
        self.timeline_widget.seekRequested.connect(self.seek)

        # Right Column: Side Effect Properties Inspector Panel
        self.props_panel = VFXDialogPropertiesPanel(self)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFixedWidth(340)
        right_scroll.setWidget(self.props_panel)
        middle_split.addWidget(right_scroll)

        root.addLayout(middle_split, 1)
        root.addWidget(self.timeline_widget)

        # 4. Footer Bar with Explicit Working Apply & Cancel Buttons
        footer = QHBoxLayout()
        hint_label = QLabel("Drag handles on ruler to adjust timing · Set any property in the right panel · Click Apply & Close to save")
        set_ui_style(hint_label, 'color: @text_sub; font-size: 11px;')
        footer.addWidget(hint_label)
        footer.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton("Apply & Close")
        self.btn_apply.setFixedHeight(30)
        set_ui_style(self.btn_apply, '\n            QPushButton {\n                background-color: @accent;\n                color: @accent_text;\n                font-weight: bold;\n                border: 1px solid @accent;\n                border-radius: 4px;\n                padding: 4px 18px;\n            }\n            QPushButton:hover {\n                background-color: @accent;\n            }\n            QPushButton:pressed {\n                background-color: @accent;\n            }\n        ')
        self.btn_apply.clicked.connect(self.accept)
        footer.addWidget(self.btn_apply)

        root.addLayout(footer)

        # Transport initialization
        from .transport import TimelineTransport
        self.transport = TimelineTransport(self)
        self.transport.changed.connect(self.on_position_changed)
        self.transport.stateChanged.connect(self.on_playback_state_changed)

        # Shortcuts
        self.space_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.space_shortcut.setContext(Qt.WindowShortcut)
        self.space_shortcut.activated.connect(self.toggle_play)

        self.update_header_readouts()
        QTimer.singleShot(0, lambda: self.seek(self.original_start))

    def start_worker(self, worker):
        if hasattr(self.owner, "start_worker"):
            self.owner.start_worker(worker)

    def statusBar(self):
        return self.owner.statusBar() if hasattr(self.owner, "statusBar") else None

    def toggle_play(self):
        if self.transport.playing:
            self.transport.pause()
        else:
            if self.position >= self.item.duration:
                self.seek(0.0)
            self.transport.play()

    def play_in_out_range(self):
        start_t = float(self.effect.get("start_time", 0.0))
        self.seek(start_t)
        if not self.transport.playing:
            self.transport.play()

    def set_loop_range(self, checked: bool):
        self.loop_range = checked

    def seek(self, t: float):
        t = max(0.0, min(self.item.duration, t))
        self.transport.seek(t)

    def step_frame(self, delta_frames: int):
        fps = self.project.settings.fps
        self.seek(self.position + (delta_frames / fps))

    def jump_to_in(self):
        self.seek(float(self.effect.get("start_time", 0.0)))

    def jump_to_out(self):
        start_t = float(self.effect.get("start_time", 0.0))
        dur = float(self.effect.get("duration", 1.0))
        self.seek(min(self.item.duration, start_t + dur))

    def apply_preset_duration(self, new_duration: float):
        start_t = float(self.effect.get("start_time", 0.0))
        new_dur = max(0.05, min(self.item.duration - start_t, new_duration))
        if start_t + new_dur > self.item.duration:
            start_t = max(0.0, self.item.duration - new_dur)
        self.on_range_changed(start_t, new_dur)

    def on_position_changed(self, t: float):
        self.position = t
        self.project.playhead = t
        fps = self.project.settings.fps
        self.label_curr_pos.setText(format_smpte(t, fps))

        # Check loop range boundary
        if self.loop_range and self.transport.playing:
            start_t = float(self.effect.get("start_time", 0.0))
            end_t = start_t + float(self.effect.get("duration", 1.0))
            if t >= end_t or t < start_t:
                self.seek(start_t)

        if getattr(self, "timeline_widget", None) is not None:
            self.timeline_widget.update()
        self.preview.update()

    def on_playback_state_changed(self, playing: bool):
        self.btn_play.setIcon(lucide_icon("pause" if playing else "play", "#ffffff", 14))
        self.btn_play.setText(" Pause" if playing else " Play")

    def on_property_edited(self, key: str, value):
        """Called when any control in the right-side properties panel is edited."""
        self.effect[key] = value

        # Sync local preview item effects copy
        if getattr(self.item, "effects", None):
            for e in self.item.effects:
                if e.get("id") == self.effect.get("id") or e.get("name") == self.effect.get("name"):
                    e[key] = value

        # If timing or return values changed, update timeline widget and header readouts
        if key in ("start_time", "duration", "zoom_return", "zoom_hold_duration", "zoom_attack_duration", "timing_mode"):
            self.update_header_readouts()
            if getattr(self, "timeline_widget", None) is not None:
                self.timeline_widget.update()

        inspector = getattr(self.owner, "inspector", None)
        if inspector:
            if key == "start_time" and hasattr(inspector, "vfx_start_time"):
                inspector.vfx_start_time.set_values([value])
            elif key == "duration" and hasattr(inspector, "vfx_duration"):
                inspector.vfx_duration.set_values([value])

        # Update preview canvas immediately
        self.preview.update()

    def on_range_changed(self, new_start: float, new_dur: float):
        new_start = round(max(0.0, min(self.item.duration - 0.05, new_start)), 3)
        new_dur = round(max(0.05, min(self.item.duration - new_start, new_dur)), 3)

        self.effect["start_time"] = new_start
        self.effect["duration"] = new_dur

        # Synchronize local item effects so preview renders active timing
        if getattr(self.item, "effects", None):
            for e in self.item.effects:
                if e.get("id") == self.effect.get("id") or e.get("name") == self.effect.get("name"):
                    e["start_time"] = new_start
                    e["duration"] = new_dur

        # Update right-side panel without triggering loops
        if getattr(self, "props_panel", None) is not None:
            self.props_panel.sync_from_effect()

        inspector = getattr(self.owner, "inspector", None)
        if inspector:
            if hasattr(inspector, "vfx_start_time"):
                inspector.vfx_start_time.set_values([new_start])
            if hasattr(inspector, "vfx_duration"):
                inspector.vfx_duration.set_values([new_dur])

        self.update_header_readouts()
        if getattr(self, "timeline_widget", None) is not None:
            self.timeline_widget.update()
        self.preview.update()

    def reset_to_defaults(self):
        """Reset all parameters of the current effect to default."""
        d = default_visual_fx(self.effect.get("name", ""))
        for k, v in d.items():
            if k not in ("name", "category", "subsection"):
                self.effect[k] = v
                if getattr(self.item, "effects", None):
                    for e in self.item.effects:
                        if e.get("id") == self.effect.get("id") or e.get("name") == self.effect.get("name"):
                            e[k] = v
        if getattr(self, "props_panel", None) is not None:
            self.props_panel.sync_from_effect()
        self.update_header_readouts()
        if getattr(self, "timeline_widget", None) is not None:
            self.timeline_widget.update()
        self.preview.update()

    def update_header_readouts(self):
        fps = self.project.settings.fps
        start_t = float(self.effect.get("start_time", 0.0))
        dur_t = float(self.effect.get("duration", 1.0))
        end_t = min(self.item.duration, start_t + dur_t)

        self.label_in.setText(f"IN {format_smpte(start_t, fps)}")
        self.label_out.setText(f"OUT {format_smpte(end_t, fps)}")
        self.label_duration.setText(f"DURATION {format_smpte(dur_t, fps)}")

    def accept(self):
        """Save all changes into the project and history."""
        # 1. Update the original effect dictionary and the timeline item in owner.project
        real_item = self.owner.project.item_by_id(self.item.id) if hasattr(self.owner, "project") else None
        if real_item and getattr(real_item, "effects", None):
            for e in real_item.effects:
                if e is self.effect or e.get("id") == self.effect.get("id") or (e.get("name") == self.effect.get("name") and e.get("category") == "Visual FX"):
                    e.update(self.effect)

        # 2. Update inspector on main window
        inspector = getattr(self.owner, "inspector", None)
        if inspector:
            inspector.refresh_effect()

        # 3. Commit changes to project & undo history
        if hasattr(self.owner, "model_changed"):
            self.owner.model_changed()
        if hasattr(self.owner, "commit_history"):
            self.owner.commit_history()
        if hasattr(self.owner, "preview") and hasattr(self.owner.preview, "update"):
            self.owner.preview.update()

        super().accept()

    def reject(self):
        """Restore all original parameters on Cancel."""
        self.effect.clear()
        self.effect.update(self.original_effect_backup)

        real_item = self.owner.project.item_by_id(self.item.id) if hasattr(self.owner, "project") else None
        if real_item and getattr(real_item, "effects", None):
            for e in real_item.effects:
                if e is self.effect or e.get("id") == self.effect.get("id") or (e.get("name") == self.effect.get("name") and e.get("category") == "Visual FX"):
                    e.clear()
                    e.update(self.original_effect_backup)

        inspector = getattr(self.owner, "inspector", None)
        if inspector:
            inspector.refresh_effect()
        if hasattr(self.owner, "model_changed"):
            self.owner.model_changed()
        if hasattr(self.owner, "preview") and hasattr(self.owner.preview, "update"):
            self.owner.preview.update()

        super().reject()

    def done(self, result):
        if hasattr(self, "transport") and self.transport:
            self.transport.shutdown()
        super().done(result)
        if hasattr(self.owner, "activateWindow"):
            self.owner.activateWindow()
