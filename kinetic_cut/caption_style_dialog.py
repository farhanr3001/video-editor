"""Live caption style preview using the same painter as the timeline viewer."""
import copy
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QElapsedTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
    QDialogButtonBox, QFontComboBox, QFormLayout, QGridLayout, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QTabWidget, QVBoxLayout, QWidget)
from .model import Caption, CaptionStyle, Project
from .visuals import draw_caption
from .icons import resource_path
from .caption_fonts import CaptionFontCombo
from .caption_words import ANIMATIONS, prepare_generated
from .caption_templates import CAPTION_TEMPLATES
from .theme_widgets import set_ui_style


def fit_preview(project,caption,frame):
    """Fit the complete text/emoji composition inside a small preview tile."""
    from .visuals import caption_geometry,caption_emoji_rect
    from .caption_emojis import emojis_for_caption
    def extent():
        geometry=caption_geometry(project,caption,frame); bounds=geometry[2]
        selected=emojis_for_caption(project,caption,2) if project.subtitle_style.animation in ('emoji pop','double emoji') else []
        for index,_ in selected:
            rect=caption_emoji_rect(bounds,geometry[3][index],frame.width()/project.settings.width)
            # Include the largest phase of the unchanged emoji pop animation.
            center=rect.center(); rect.setWidth(rect.width()*1.3); rect.setHeight(rect.height()*1.3); rect.moveCenter(center)
            bounds=bounds.united(rect)
        return bounds
    for _ in range(3):
        bounds=extent(); ratio=min(1,frame.height()*.9/max(1,bounds.height()),frame.width()*.95/max(1,bounds.width()))
        if ratio>=.99:break
        project.subtitle_style.size*=ratio
    bounds=extent()
    project.subtitle_style.position_y+=(frame.center().y()-bounds.center().y())/max(1,frame.height())


class CaptionPreview(QWidget):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setMinimumSize(370, 160)
        self.setObjectName("captionStylePreview")
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)
        self.elapsed = QElapsedTimer()

    def play(self, enabled):
        if enabled:
            self.elapsed.start()
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#13161c"))
        project = Project()
        project.settings.width = 1080
        project.settings.height = 400
        style = self.owner.selected_style()
        style.position_x = 0.5
        style.position_y = 0.62 if style.animation in ("emoji pop", "double emoji") else 0.5
        project.subtitle_style = style
        project.playhead = (self.elapsed.elapsed() / 1000) % 2.8 if self.timer.isActive() else 0.8
        selected_tmpl = getattr(self.owner, "selected_template", None)
        sample = "Curious about incredible moments with your own caption style and creative words"
        if selected_tmpl and selected_tmpl.get("preview_text"):
            sample=selected_tmpl['preview_text']+' '+sample
        words_count=max(1,self.owner.words.value())
        text=" ".join(sample.split()[:words_count])
        caption = Caption("sample", 0, 2.8, text)
        prepare_generated([caption], style)
        frame=QRectF(self.rect()).adjusted(8,8,-8,-8)
        fit_preview(project,caption,frame)
        draw_caption(painter, project, caption, frame)
        painter.setPen(QColor("#50545e"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


class TemplateCardWidget(QWidget):
    clicked = Signal(dict)

    def __init__(self, template: dict, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.template = template
        self.is_selected = is_selected
        self.is_hovered = False
        self.setFixedSize(140, 110)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName(f"template_card_{template.get('id', '')}")
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update)
        self.elapsed = QElapsedTimer()

    def set_selected(self, selected: bool):
        if self.is_selected != selected:
            self.is_selected = selected
            self.update()

    def enterEvent(self, event):
        self.is_hovered = True
        self.elapsed.start()
        self.timer.start()
        self.update()
        try:
            super().enterEvent(event)
        except TypeError:
            pass

    def leaveEvent(self, event):
        self.is_hovered = False
        self.timer.stop()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.template)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Outer Card Rect & Background
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 8.0

        if self.is_selected:
            bg_color = QColor("#172132")
            border_pen = QPen(QColor("#00F0FF"), 2.0)
        elif self.is_hovered:
            bg_color = QColor("#1a1e2b")
            border_pen = QPen(QColor("#38BDF8"), 1.5)
        else:
            bg_color = QColor("#13161f")
            border_pen = QPen(QColor("#262a36"), 1.0)

        painter.setBrush(bg_color)
        painter.setPen(border_pen)
        painter.drawRoundedRect(rect, radius, radius)

        if self.template.get("is_none"):
            # Prohibition / disable icon matching user's Image 5
            cx = self.width() / 2.0
            cy = self.height() / 2.0 - 10.0
            r = 18.0
            icon_color = QColor("#DC2626")  # Bold red
            icon_pen = QPen(icon_color, 4.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(icon_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r, r)

            # Diagonal slash from top-left to bottom-right (45 degrees)
            offset = r * 0.7071
            painter.drawLine(QPointF(cx - offset, cy - offset), QPointF(cx + offset, cy + offset))

            # Centered text label "No Template" below the icon
            label_font = QFont("Segoe UI", 9, QFont.Bold)
            painter.setFont(label_font)
            label_color = QColor("#00F0FF") if self.is_selected else QColor("#F1F5F9") if self.is_hovered else QColor("#94A3B8")
            painter.setPen(label_color)
            painter.drawText(QRectF(0, cy + r + 5, self.width(), 20), Qt.AlignCenter, "No Template")
            return

        # Badge (top left)
        badge = self.template.get("badge", "")
        if badge:
            badge_font = QFont("Segoe UI", 7, QFont.Bold)
            painter.setFont(badge_font)
            metrics = QFontMetricsF(badge_font)
            bw = max(34.0, metrics.horizontalAdvance(badge) + 10.0)
            badge_rect = QRectF(7, 7, bw, 15)

            badge_bg = QColor(0, 240, 255, 45) if self.is_selected else QColor(255, 255, 255, 25)
            badge_ink = QColor("#00F0FF") if self.is_selected else QColor("#D1D5DB")
            painter.setPen(Qt.NoPen)
            painter.setBrush(badge_bg)
            painter.drawRoundedRect(badge_rect, 3.0, 3.0)
            painter.setPen(badge_ink)
            painter.drawText(badge_rect, Qt.AlignCenter, badge)

        # Indicator (bottom right): Checkmark if selected, Download icon if unselected
        ind_cx = self.width() - 15.0
        ind_cy = self.height() - 15.0
        ind_r = 7.0
        if self.is_selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#00F0FF"))
            painter.drawEllipse(QPointF(ind_cx, ind_cy), ind_r, ind_r)
            # draw white checkmark
            painter.setPen(QPen(QColor("#050B14"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(QPointF(ind_cx - 3.5, ind_cy), QPointF(ind_cx - 1.0, ind_cy + 2.5))
            painter.drawLine(QPointF(ind_cx - 1.0, ind_cy + 2.5), QPointF(ind_cx + 3.5, ind_cy - 2.5))
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#222734"))
            painter.drawEllipse(QPointF(ind_cx, ind_cy), ind_r, ind_r)
            # draw subtle download arrow
            painter.setPen(QPen(QColor("#94A3B8"), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(QPointF(ind_cx, ind_cy - 3.5), QPointF(ind_cx, ind_cy + 2.0))
            painter.drawLine(QPointF(ind_cx - 2.5, ind_cy - 0.5), QPointF(ind_cx, ind_cy + 2.0))
            painter.drawLine(QPointF(ind_cx + 2.5, ind_cy - 0.5), QPointF(ind_cx, ind_cy + 2.0))
            painter.drawLine(QPointF(ind_cx - 3.0, ind_cy + 3.8), QPointF(ind_cx + 3.0, ind_cy + 3.8))

        # Center Preview using draw_caption
        preview_rect = QRectF(6, 6, self.width() - 12, self.height() - 12)

        project = Project()
        project.settings.width = 360
        project.settings.height = 200

        style = CaptionStyle()
        for k, v in self.template.items():
            if hasattr(style, k):
                setattr(style, k, v)
        style.position_x = 0.5
        style.position_y = 0.72 if style.animation in ("emoji pop", "double emoji") else 0.55
        text = self.template.get("preview_text", "QUICK")
        word_count = len(text.split())
        if word_count > 1:
            style.size = min(style.size, 52)
        else:
            style.size = min(style.size, 60)
        project.subtitle_style = style

        # Calculate playhead
        if self.is_hovered and self.timer.isActive():
            playhead = (self.elapsed.elapsed() / 1000.0) % 2.5
        else:
            playhead = 0.8

        project.playhead = playhead
        caption = Caption("card", 0, 2.5, text)
        prepare_generated([caption], style)

        painter.save()
        painter.setClipRect(preview_rect)
        fit_preview(project,caption,preview_rect)
        draw_caption(painter, project, caption, preview_rect)
        painter.restore()


from .caption_presets import CAPTION_PRESETS

PRESET_NAMES = [
    ("Custom / Current", ""),
    ("Crime Red Alert", "crime_red"),
    ("Viral TikTok Yellow", "viral_yellow"),
    ("Cyber Neon Cyan", "cyber_cyan"),
    ("MrBeast Gold", "mrbeast_gold"),
    ("Clean Minimal Card", "clean_card"),
]


class CaptionStyleDialog(QDialog):
    def __init__(self, style, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto Caption Style")
        self.base = copy.deepcopy(style)
        self.selected_template_id = getattr(style, "id", None)
        self.selected_template = next((t for t in CAPTION_TEMPLATES if t.get("id") == self.selected_template_id), None)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)
        self.resize(500, min(800, self.screen().availableGeometry().height() - 60))
        self.setMinimumWidth(480)

        # Top preview & Play button
        self.preview = CaptionPreview(self)
        outer.addWidget(self.preview)

        play = QPushButton("Play animation preview")
        play.setCheckable(True)
        play.toggled.connect(self.preview.play)
        play.toggled.connect(lambda on: play.setText("Stop animation preview" if on else "Play animation preview"))
        outer.addWidget(play)

        # Main Tab Widget: "Caption Setup" | "Choose Template"
        self.tabs = QTabWidget()
        self.tabs.setObjectName("captionStyleTabs")
        set_ui_style(self.tabs,"""
            QTabWidget::pane {
                border: 1px solid @border;
                background: @bg_panel;
                border-radius: 6px;
                padding: 4px;
            }
            QTabBar::tab {
                background: @bg_surface;
                color: @text_sub;
                padding: 8px 24px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                font-weight: 600;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: @bg_selected;
                color: @text_selected;
                border-bottom: 2px solid @accent;
            }
            QTabBar::tab:hover:!selected {
                background: @bg_hover;
                color: @text_main;
            }
        """)

        # Tab 1: Caption Setup
        setup_tab = QWidget()
        setup_layout = QVBoxLayout(setup_tab)
        setup_layout.setContentsMargins(2, 2, 2, 2)
        setup_scroll = QScrollArea()
        setup_scroll.setWidgetResizable(True)
        setup_scroll.setFrameShape(QScrollArea.NoFrame)
        setup_content = QWidget()
        form = QFormLayout(setup_content)
        self.form = form
        form.setContentsMargins(6, 6, 6, 6)
        form.setSpacing(8)

        self.hover_font = ''
        self.font = CaptionFontCombo()
        self.font.setObjectName("captionFontPicker")
        self.font.setEditable(False)
        self.font.setCurrentFont(QFont(style.font))
        set_ui_style(self.font, 'QComboBox::down-arrow {image:url("@arrow_combo");width:14px;height:14px;} QComboBox::drop-down {width:26px;border-left:1px solid @border_subtle;}')

        # Keep self.preset attribute for backwards compatibility with tests, but omit from visible layout
        self.preset = QComboBox()
        self.preset.setObjectName("captionStylePreset")
        set_ui_style(self.preset, 'QComboBox::down-arrow {image:url("@arrow_combo");width:14px;height:14px;} QComboBox::drop-down {width:26px;border-left:1px solid @border_subtle;}')
        for label, key in PRESET_NAMES:
            self.preset.addItem(label, key)
        initial_preset_idx = 0
        for idx, (label, key) in enumerate(PRESET_NAMES):
            if key and (getattr(style, "name", "") == label or getattr(style, "name", "") == key):
                initial_preset_idx = idx
                break
        self.preset.setCurrentIndex(initial_preset_idx)

        self.face = QComboBox()
        self.face.addItems(["Regular", "Bold", "Italic", "Bold Italic"])
        self.face.setCurrentText(style.font_face)

        self.size = QSpinBox()
        self.size.setRange(8, 200)
        self.size.setValue(style.size)

        self.animation = QComboBox()
        self.animation.addItems(ANIMATIONS)
        self.animation.setCurrentText(style.animation)
        self.animation.setToolTip('Word animations use speech-recognizer word timings. "karaoke" highlights the active spoken word in highlight colour. "emoji pop" and "double emoji" pop animated emojis above the spoken words.')

        self.words = QSpinBox()
        self.words.setRange(1, 12)
        self.words.setValue(int(settings.get("caption_words_per_card", 3)))

        self.upper = QCheckBox("Uppercase")
        self.upper.setChecked(style.uppercase)

        self.background = QCheckBox("Background card")
        self.background.setChecked(style.background_enabled)

        self.censor = QCheckBox("Censor curse words")
        self.censor.setChecked(bool(settings.get("caption_censor", False)))
        self.censor.setToolTip("Mask common English curse words in generated text. Review captions for recognition mistakes.")

        self.remove_periods = QCheckBox("Remove periods at word endings")
        self.remove_periods.setChecked(bool(settings.get('caption_remove_periods', False)))
        self.remove_periods.setToolTip('Hello there. → Hello there. Decimal points and punctuation inside words are retained.')

        self.glow = QCheckBox('Glow')
        self.glow.setChecked(style.glow_enabled)

        self.glow_follow = QCheckBox('Use text colour')
        self.glow_follow.setChecked(style.glow_follow_color)

        self.glow_radius = QSpinBox()
        self.glow_radius.setRange(1, 40)
        self.glow_radius.setValue(round(style.glow_radius))

        # Local arrows override platform/style defaults and refresh with themes.
        for spin in (self.words,self.size,self.glow_radius):
            spin.setButtonSymbols(QSpinBox.UpDownArrows)
            spin.setMinimumHeight(28)
            set_ui_style(spin,'''
                QSpinBox {padding-right:26px;}
                QSpinBox::up-button {subcontrol-origin:border;subcontrol-position:top right;width:22px;height:13px;background:@bg_panel;border-left:1px solid @border;}
                QSpinBox::down-button {subcontrol-origin:border;subcontrol-position:bottom right;width:22px;height:13px;background:@bg_panel;border-left:1px solid @border;}
                QSpinBox::up-arrow {image:url("@arrow_up");width:12px;height:12px;}
                QSpinBox::down-arrow {image:url("@arrow_down");width:12px;height:12px;}
            ''')

        self.colors = {key: getattr(style, key) for key in ("color", "outline", "background_color", "highlight", "glow_color")}
        self.color_buttons = {}

        # Add controls to setup form (Preset dropdown is removed from visible UI)
        form.addRow("Words per caption", self.words)
        form.addRow("Font", self.font)
        form.addRow("Font Face", self.face)
        form.addRow("Size", self.size)
        form.addRow("Text Colour", self.color_button("color", "Text Colour"))
        form.addRow("Outline Colour", self.color_button("outline", "Outline Colour"))
        form.addRow("Animation", self.animation)
        form.addRow(self.upper)
        form.addRow(self.background)
        form.addRow("Background Colour", self.color_button("background_color", "Background Colour"))
        form.addRow("Word Highlight Colour", self.color_button("highlight", "Word Highlight Colour"))
        form.addRow(self.censor)
        form.addRow(self.remove_periods)
        form.addRow(self.glow)
        form.addRow('Glow colour', self.glow_follow)
        form.addRow('Custom glow colour', self.color_button('glow_color', 'Glow Colour'))
        form.addRow('Glow radius', self.glow_radius)

        setup_scroll.setWidget(setup_content)
        setup_layout.addWidget(setup_scroll)
        self.tabs.addTab(setup_tab, "Caption Setup")

        # Tab 2: Choose Template
        template_tab = QWidget()
        template_layout = QVBoxLayout(template_tab)
        template_layout.setContentsMargins(2, 2, 2, 2)
        template_scroll = QScrollArea()
        template_scroll.setWidgetResizable(True)
        template_scroll.setFrameShape(QScrollArea.NoFrame)
        template_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        template_content = QWidget()
        grid = QGridLayout(template_content)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(10)

        self.template_cards = []
        cols = 3
        for idx, t in enumerate(CAPTION_TEMPLATES):
            is_sel = (t.get("id") == self.selected_template_id)
            card = TemplateCardWidget(t, is_selected=is_sel)
            card.clicked.connect(self.on_template_selected)
            self.template_cards.append(card)
            grid.addWidget(card, idx // cols, idx % cols)

        template_scroll.setWidget(template_content)
        template_layout.addWidget(template_scroll)
        self.tabs.addTab(template_tab, "Choose Template")

        outer.addWidget(self.tabs)

        self._applying_preset = False
        self.preset.currentIndexChanged.connect(self.on_preset_selected)
        self.glow.toggled.connect(self.refresh)
        self.glow_follow.toggled.connect(self.refresh)
        self.glow_radius.valueChanged.connect(self.refresh)
        self.font.previewFontChanged.connect(self.hover_preview)
        self.font.currentFontChanged.connect(self.refresh)
        self.face.currentTextChanged.connect(self.refresh)
        self.size.valueChanged.connect(self.refresh)
        self.animation.currentTextChanged.connect(self.refresh)
        self.words.valueChanged.connect(self.refresh)
        self.upper.toggled.connect(self.refresh)
        self.background.toggled.connect(self.refresh)

        for control_signal in (
            self.font.currentFontChanged, self.face.currentTextChanged, self.size.valueChanged,
            self.animation.currentTextChanged, self.upper.toggled, self.background.toggled,
            self.glow.toggled, self.glow_follow.toggled, self.glow_radius.valueChanged
        ):
            control_signal.connect(self._on_control_customized)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Generate Captions")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.finished.connect(lambda _: self.preview.play(False))
        self.refresh()

    def on_template_selected(self, template_data):
        is_none = template_data.get("is_none", False) or template_data.get("id") == "none"
        self.selected_template_id = "none" if is_none else template_data.get("id")
        self.selected_template = None if is_none else template_data
        for card in self.template_cards:
            card.set_selected(card.template.get("id") == self.selected_template_id or (is_none and card.template.get("is_none")))

        self._applying_preset = True
        try:
            if is_none:
                default_style = CaptionStyle()
                self.font.setCurrentFont(QFont(default_style.font))
                self.hover_font = ''
                self.face.setCurrentText(default_style.font_face)
                self.size.setValue(int(default_style.size))
                self.animation.setCurrentText(default_style.animation)
                self.upper.setChecked(bool(default_style.uppercase))
                self.background.setChecked(bool(default_style.background_enabled))
                self.glow.setChecked(bool(default_style.glow_enabled))
                self.glow_follow.setChecked(bool(default_style.glow_follow_color))
                self.glow_radius.setValue(round(float(default_style.glow_radius)))
                self.colors["color"] = default_style.color
                self.colors["outline"] = default_style.outline
                self.colors["highlight"] = default_style.highlight
                self.colors["background_color"] = default_style.background_color
                self.colors["glow_color"] = default_style.glow_color
                for extra_key in ("outline_width", "shadow_enabled", "shadow_color", "shadow_x", "shadow_y",
                                  "shadow_blur", "shadow_opacity", "glow_opacity", "background_opacity",
                                  "background_radius", "background_outline", "background_outline_width",
                                  "background_override", "position_x", "position_y"):
                    setattr(self.base, extra_key, getattr(default_style, extra_key))
                self.base.name = "Default"
                self.base.id = None
            else:
                font_family = template_data.get("font", "Arial")
                self.font.setCurrentFont(QFont(font_family))
                self.hover_font = ''
                self.face.setCurrentText(template_data.get("font_face", "Regular"))
                self.size.setValue(int(template_data.get("size", 64)))
                anim = template_data.get("animation", "pop")
                if anim in ANIMATIONS:
                    self.animation.setCurrentText(anim)
                self.upper.setChecked(bool(template_data.get("uppercase", False)))
                self.background.setChecked(bool(template_data.get("background_enabled", False)))
                self.glow.setChecked(bool(template_data.get("glow_enabled", False)))
                self.glow_follow.setChecked(bool(template_data.get("glow_follow_color", False)))
                self.glow_radius.setValue(round(float(template_data.get("glow_radius", 12))))
                if "color" in template_data:
                    self.colors["color"] = template_data["color"]
                if "outline" in template_data:
                    self.colors["outline"] = template_data["outline"]
                if "highlight" in template_data:
                    self.colors["highlight"] = template_data["highlight"]
                if "background_color" in template_data:
                    self.colors["background_color"] = template_data["background_color"]
                if "glow_color" in template_data:
                    self.colors["glow_color"] = template_data["glow_color"]
                for extra_key in ("outline_width", "shadow_enabled", "shadow_color", "shadow_x", "shadow_y",
                                  "shadow_blur", "shadow_opacity", "glow_opacity", "background_opacity",
                                  "background_radius", "background_outline", "background_outline_width",
                                  "background_override", "position_x", "position_y"):
                    if extra_key in template_data:
                        setattr(self.base, extra_key, template_data[extra_key])
                if "name" in template_data:
                    self.base.name = template_data["name"]
                self.base.id = template_data.get("id")
        finally:
            self._applying_preset = False
        self.refresh()

    def _on_control_customized(self, *_):
        if not getattr(self, "_applying_preset", False) and hasattr(self, "preset") and self.preset.currentIndex() != 0:
            self.preset.blockSignals(True)
            self.preset.setCurrentIndex(0)
            self.preset.blockSignals(False)

    def on_preset_selected(self, index):
        if self._applying_preset:
            return
        key = self.preset.itemData(index)
        if not key or key not in CAPTION_PRESETS:
            return
        p = CAPTION_PRESETS[key]
        self._applying_preset = True
        try:
            font_family = p.get("font", "Arial")
            self.font.setCurrentFont(QFont(font_family))
            self.hover_font = ''
            self.face.setCurrentText(p.get("font_face", "Regular"))
            self.size.setValue(int(p.get("size", 64)))
            anim = p.get("animation", "pop")
            if anim in ANIMATIONS:
                self.animation.setCurrentText(anim)
            self.upper.setChecked(bool(p.get("uppercase", False)))
            self.background.setChecked(bool(p.get("background_enabled", False)))
            self.glow.setChecked(bool(p.get("glow_enabled", False)))
            self.glow_follow.setChecked(bool(p.get("glow_follow_color", False)))
            self.glow_radius.setValue(round(float(p.get("glow_radius", 12))))
            if "color" in p:
                self.colors["color"] = p["color"]
            if "outline" in p:
                self.colors["outline"] = p["outline"]
            if "highlight" in p:
                self.colors["highlight"] = p["highlight"]
            if "background_color" in p:
                self.colors["background_color"] = p["background_color"]
            if "glow_color" in p:
                self.colors["glow_color"] = p["glow_color"]
            for extra_key in ("outline_width", "shadow_enabled", "shadow_color", "shadow_x", "shadow_y",
                              "shadow_blur", "shadow_opacity", "glow_opacity", "background_opacity",
                              "background_radius", "background_outline", "background_outline_width",
                              "background_override", "position_x", "position_y"):
                if extra_key in p:
                    setattr(self.base, extra_key, p[extra_key])
            if "name" in p:
                self.base.name = p["name"]
        finally:
            self._applying_preset = False
        self.refresh()

    def color_button(self, key, label):
        button = QPushButton(label)
        self.color_buttons[key] = button
        def pick():
            value = QColorDialog.getColor(QColor(self.colors[key]), self, "Select " + label)
            if value.isValid():
                self.colors[key] = value.name()
                self._on_control_customized()
                self.refresh()
        button.clicked.connect(pick)
        return button

    def refresh(self, *_):
        minimum = 3 if self.animation.currentText() == 'fade every word' else 2 if self.animation.currentText() == 'word highlight 2' else 1
        self.words.setMinimum(minimum)
        self.words.setSuffix(" word" if self.words.value() == 1 else " words")
        self.form.setRowVisible(self.color_buttons["background_color"], self.background.isChecked())
        is_highlight_anim = self.animation.currentText() in ('word highlight', 'word highlight 2', 'karaoke', 'emoji pop', 'double emoji')
        self.form.setRowVisible(self.color_buttons["highlight"], is_highlight_anim)
        self.form.setRowVisible(self.glow_follow, self.glow.isChecked())
        self.form.setRowVisible(self.glow_radius, self.glow.isChecked())
        self.form.setRowVisible(self.color_buttons['glow_color'], self.glow.isChecked() and not self.glow_follow.isChecked())
        for key, button in self.color_buttons.items():
            color = self.colors[key]
            ink = "#16181d" if QColor(color).lightnessF() > 0.5 else "#f3f5f8"
            button.setStyleSheet(f"background:{color};color:{ink};border:1px solid #777")
        self.preview.update()

    def hover_preview(self, name):
        self.hover_font = name
        self.preview.update()

    def selected_style(self):
        style = copy.deepcopy(self.base)
        style.font = self.font.currentFont().family()
        style.font_face = self.face.currentText()
        if self.hover_font:
            style.font = self.hover_font
        style.glow_enabled = self.glow.isChecked()
        style.glow_follow_color = self.glow_follow.isChecked()
        style.glow_radius = self.glow_radius.value()
        style.size = self.size.value()
        style.animation = self.animation.currentText()
        style.uppercase = self.upper.isChecked()
        style.background_enabled = self.background.isChecked()
        for key, value in self.colors.items():
            setattr(style, key, value)
        if getattr(self, "selected_template_id", None):
            style.id = self.selected_template_id if self.selected_template_id != "none" else None
        return style
