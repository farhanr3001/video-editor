"""Context-sensitive inspector with reusable numeric slider/reset rows."""
from .theme_widgets import set_ui_style, set_ui_icon
from .editing import edit_only
import copy
import math
from dataclasses import asdict
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QColor, QFontDatabase,QTextCursor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from .media_source import set_media_source
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QGridLayout,QLabel,QSlider,
    QToolButton,QTabWidget,QStackedWidget,QScrollArea,QCheckBox,QPlainTextEdit,
    QTableWidget,QTableWidgetItem,QTableWidgetSelectionRange,QColorDialog,QPushButton,QProgressBar,QLayout,QMenu,QLineEdit)
from .controls import SafeDoubleSpinBox, SafeComboBox, SafeSlider, InspectorSection
from .icons import lucide_icon
from .model import Caption, CaptionStyle, Crop, TimelineItem, Transform, uid
from .emoji import EmojiTextEdit
from .tts import VOICES, DEFAULT_VOICE, synthesize_speech
from .media import probe
from .transitions import Transition, default_transition_properties, TRANSITION_ICONS
from .caption_templates import CAPTION_TEMPLATES
from .caption_style_dialog import TemplateCardWidget


class ValueRow(QWidget):
    edited=Signal(float,float)
    def __init__(self,low,high,default=0,step=.1,slider=True):
        super().__init__(); self.updating=False; self.previous=default; self.mixed=False
        self.setFixedHeight(28)
        layout=QHBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(5)
        # A visible parentless control is a native top-level window, even if a
        # layout adopts it immediately afterwards. Own it before visibility.
        self.slider=SafeSlider(Qt.Horizontal,self); self.slider.setRange(0,1000); self.slider.setVisible(slider)
        self.spin=SafeDoubleSpinBox(); self.spin.setRange(low,high); self.spin.setDecimals(3 if step<.1 else 2 if step<1 else 0); self.spin.setSingleStep(step); self.spin.setFixedWidth(81)
        layout.addWidget(self.slider,1); layout.addWidget(self.spin)
        reset=QToolButton(); self.reset=reset; reset.setIcon(lucide_icon("rotate-ccw","#96989f",13)); reset.setToolTip("Reset to default"); layout.addWidget(reset)
        self.low=low; self.high=high; self.default=default
        self.spin.valueChanged.connect(self.change); self.slider.valueChanged.connect(lambda v:self.spin.setValue(self.slider_to_value(v)))
        self.spin.scrubStarted.connect(lambda:self.scrub_history(True)); self.spin.scrubFinished.connect(lambda:self.scrub_history(False))
        self.slider.sliderPressed.connect(lambda:self.scrub_history(True)); self.slider.sliderReleased.connect(lambda:self.scrub_history(False))
        reset.clicked.connect(lambda:self.change(default,True)); self.set_values([default])
    def set_maximum(self, max_val: float):
        max_val = max(self.low + 0.01, float(max_val))
        self.high = max_val
        self.spin.setMaximum(max_val)
        if self.default > max_val:
            self.default = max_val
        if self.spin.value() > max_val:
            self.spin.setValue(max_val)
    def scrub_history(self,active):
        window=self.window()
        if hasattr(window,"commit_history"):
            window._property_scrubbing=active
            if not active:window.commit_history(); window.inspector.select(window.inspector.item_id)
    def set_values(self,values):
        values=values or [self.default]; self.mixed=max(values)-min(values)>.00001
        value=sum(values)/len(values); self.previous=value; self.updating=True
        self.spin.blockSignals(True); self.slider.blockSignals(True)
        self.spin.setValue(value); self.slider.setValue(self.value_to_slider(value))
        self.spin.blockSignals(False); self.slider.blockSignals(False); self.updating=False
        if self.mixed:self.spin.lineEdit().setText("…")
    def change(self,value,reset=False):
        if self.updating:return
        delta=value-self.previous; self.previous=value
        self.slider.blockSignals(True); self.slider.setValue(self.value_to_slider(value)); self.slider.blockSignals(False)
        self.edited.emit(value,float("nan") if reset else delta)

    def value_to_slider(self,value):
        if self.low<self.default<self.high:
            return round(500*(value-self.low)/(self.default-self.low)) if value<=self.default else round(500+500*(value-self.default)/(self.high-self.default))
        return round(1000*(value-self.low)/(self.high-self.low))

    def slider_to_value(self,position):
        if self.low<self.default<self.high:
            return self.low+(self.default-self.low)*position/500 if position<=500 else self.default+(self.high-self.default)*(position-500)/500
        return self.low+(self.high-self.low)*position/1000


def scroll(widget):
    if widget.layout():widget.layout().setSizeConstraint(QLayout.SetMinimumSize)
    area=QScrollArea(); area.setWidgetResizable(True); area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); area.setWidget(widget); return area


class PropertiesPanel(QWidget):
    changed=Signal(); requestCrop=Signal(str)
    def __init__(self,window):
        super().__init__(); self.window=window; self.item_id=""; self.caption_id=""; self.transition_id=""; self.updating=False
        self.bindings=[]; self.audio_bindings=[]; self.color_bindings=[]; self.style_bindings=[]; self.style_colors=[]; self.style_combos=[]
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        self.filename=QLabel("No clip selected"); self.filename.setObjectName("inspectorFilename"); root.addWidget(self.filename)
        self.tabs=QTabWidget(); self.tabs.setDocumentMode(True); self.tabs.setIconSize(__import__('PySide6.QtCore',fromlist=['QSize']).QSize(18,18)); root.addWidget(self.tabs)
        self.tabs.tabBar().setObjectName('inspectorTabs')
        self.video_stack=QStackedWidget(); self.video=self.build_video(); self.subtitle=self.build_subtitle(); self.title=self.build_title(); self.graphic=self.build_graphic(); self.transition_panel=self.build_transition()
        self.video_stack.addWidget(scroll(self.video)); self.video_stack.addWidget(self.subtitle); self.video_stack.addWidget(scroll(self.title)); self.video_stack.addWidget(scroll(self.graphic)); self.video_stack.addWidget(scroll(self.transition_panel))
        self.tabs.addTab(self.video_stack,lucide_icon("layers",'@tab_icon'),"Video")
        self.audio_subtabs=QTabWidget(); self.audio_subtabs.setDocumentMode(True)
        self.audio=self.build_audio(); self.audio_subtabs.addTab(scroll(self.audio),"Controls")
        self.audio_subtabs.addTab(self.build_audio_levels(),"Levels")
        self.tabs.addTab(self.audio_subtabs,lucide_icon("music-2",'@tab_icon'),"Audio")
        self.effects=self.build_effects(); self.tabs.addTab(scroll(self.effects),lucide_icon("wand-sparkles",'@tab_icon'),"Effects")
        self.colors=self.build_colors(); self.tabs.addTab(scroll(self.colors),lucide_icon("palette",'@tab_icon'),"Colours")
        self.tabs.currentChanged.connect(lambda _: getattr(self.window, "preview", None) and self.window.preview.update())
        self.select("")

    def section(self,root,title,reset=None,enabled_attr=None):
        body=QWidget(); form=QFormLayout(body); form.setContentsMargins(12,8,8,12); form.setHorizontalSpacing(8); form.setVerticalSpacing(7)
        form.setLabelAlignment(Qt.AlignRight|Qt.AlignVCenter)
        section=InspectorSection(title,body,reset_callback=reset,enabled_callback=(lambda value:self.edit_style(enabled_attr,value)) if enabled_attr else None)
        if enabled_attr:self.style_combos.append((enabled_attr,section.enabled_button))
        root.addWidget(section); return form

    def numeric(self,form,label,attribute,low,high,default=0,step=.1,slider=True,audio=False):
        row=ValueRow(low,high,default,step,slider); form.addRow(label,row)
        (self.audio_bindings if audio else self.bindings).append((attribute,row))
        row.edited.connect(lambda value,delta,a=attribute,r=row:self.edit_property(a,value,delta,r.mixed))
        return row

    def build_video(self):
        panel=QWidget(); root=QVBoxLayout(panel); root.setContentsMargins(0,0,0,0)
        from .video_presets import VideoPresetStrip, HIDDEN_KEY
        self.video_presets=VideoPresetStrip(self)
        self.video_preset_section=InspectorSection('Presets',self.video_presets,expanded=not bool(self.window.settings.get(HIDDEN_KEY,False)))
        self.video_preset_section.reset_button.hide()
        self.video_preset_section.toggle.setToolTip('Show or hide video preset controls')
        self.video_preset_section.toggle.toggled.connect(self.video_presets.expansion_changed)
        root.addWidget(self.video_preset_section)
        transform_body=QWidget(); grid=QGridLayout(transform_body); grid.setContentsMargins(8,7,7,10); grid.setHorizontalSpacing(4); grid.setVerticalSpacing(7)
        grid.setColumnMinimumWidth(1,12); grid.setColumnMinimumWidth(2,66); grid.setColumnMinimumWidth(3,28); grid.setColumnMinimumWidth(4,12); grid.setColumnMinimumWidth(5,66); grid.setColumnMinimumWidth(6,24); grid.setColumnStretch(0,1)
        root.addWidget(InspectorSection("Transform",transform_body,reset_callback=lambda:self.reset_clip_section("transform")))
        def compact(low,high,default=0,step=.01):
            value=ValueRow(low,high,default,step,False); value.spin.setFixedWidth(66); value.reset.hide(); value.setFixedWidth(66); return value
        def pair(row,label,attr_x,attr_y,low,high):
            x=compact(low,high); y=compact(low,high); label_widget=QLabel(label); label_widget.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            grid.addWidget(label_widget,row,0); grid.addWidget(QLabel("X"),row,1,alignment=Qt.AlignRight|Qt.AlignVCenter); grid.addWidget(x,row,2); grid.addWidget(QLabel("Y"),row,4,alignment=Qt.AlignRight|Qt.AlignVCenter); grid.addWidget(y,row,5)
            reset=QToolButton(); reset.setIcon(lucide_icon("rotate-ccw","#96989f",13)); reset.setToolTip("Reset "+label); reset.clicked.connect(lambda:[value.change(0,True) for value in (x,y)]); grid.addWidget(reset,row,6)
            for attr,value in ((attr_x,x),(attr_y,y)):
                self.bindings.append((attr,value)); value.edited.connect(lambda v,d,a=attr,r=value:self.edit_property(a,v,d,r.mixed))
            return x,y
        def slider_row(row,label,attr,low,high,default=0,step=.1):
            label_widget=QLabel(label); label_widget.setAlignment(Qt.AlignRight|Qt.AlignVCenter); grid.addWidget(label_widget,row,0)
            value=ValueRow(low,high,default,step,True); value.spin.setFixedWidth(66); grid.addWidget(value,row,1,1,6); self.bindings.append((attr,value)); value.edited.connect(lambda v,d,a=attr,r=value:self.edit_property(a,v,d,r.mixed)); return value
        self.zoom_x=compact(.01,10,1,.01); self.zoom_y=compact(.01,10,1,.01); grid.addWidget(QLabel("Zoom",alignment=Qt.AlignRight|Qt.AlignVCenter),0,0); grid.addWidget(QLabel("X"),0,1,alignment=Qt.AlignRight|Qt.AlignVCenter); grid.addWidget(self.zoom_x,0,2)
        self.link=QToolButton(); self.link.setCheckable(True); self.link.setChecked(True); self.link.setIcon(lucide_icon("link")); self.link.setToolTip("Link Zoom X/Y"); grid.addWidget(self.link,0,3); grid.addWidget(QLabel("Y"),0,4,alignment=Qt.AlignRight|Qt.AlignVCenter); grid.addWidget(self.zoom_y,0,5)
        zoom_reset=QToolButton(); zoom_reset.setIcon(lucide_icon("rotate-ccw","#96989f",13)); zoom_reset.setToolTip("Reset Zoom"); zoom_reset.clicked.connect(self.reset_zoom); grid.addWidget(zoom_reset,0,6)
        self.bindings.extend([("transform.scale",self.zoom_x),("transform.scale_y",self.zoom_y)]); self.zoom_x.edited.connect(lambda v,d:self.edit_zoom("scale",v)); self.zoom_y.edited.connect(lambda v,d:self.edit_zoom("scale_y",v)); self.link.toggled.connect(self.set_link)
        pair(1,"Position","position_x","position_y",-10000,10000); slider_row(2,"Rotation Angle","transform.rotation",-180,180,0,.1); pair(3,"Anchor Point","transform.anchor_x","transform.anchor_y",-4000,4000); slider_row(4,"Pitch","transform.pitch",-80,80,0,.1); slider_row(5,"Yaw","transform.yaw",-80,80,0,.1)
        flips=QWidget(); row=QHBoxLayout(flips); row.setContentsMargins(0,0,0,0); row.setSpacing(7)
        self.flip_h=QToolButton(); self.flip_v=QToolButton()
        for button,icon,attr in [(self.flip_h,"flip-horizontal-2","flip_horizontal"),(self.flip_v,"flip-vertical-2","flip_vertical")]:
            button.setIcon(lucide_icon(icon)); button.setCheckable(True); button.clicked.connect(lambda checked,a=attr:self.toggle_transform(a,checked)); row.addWidget(button)
        row.addStretch(); grid.addWidget(QLabel("Flip",alignment=Qt.AlignRight|Qt.AlignVCenter),6,0); grid.addWidget(flips,6,1,1,6)
        crop=self.section(root,"Cropping",lambda:self.reset_clip_section("cropping"))
        for label,attr in [("Crop Left","crop_left"),("Crop Right","crop_right"),("Crop Top","crop_top"),("Crop Bottom","crop_bottom")]:self.numeric(crop,label,attr,0,8192,0,1)
        self.numeric(crop,"Softness","crop_softness",0,100,0,.1)
        self.retain=QCheckBox("Retain Image Position"); self.retain.toggled.connect(lambda v:self.edit_bool("retain_image_position",v)); crop.addRow("",self.retain)
        background=self.section(root,"Background Blur",lambda:self.edit_background_blur(False))
        self.background_blur_enabled=QCheckBox("Enabled"); background.addRow(self.background_blur_enabled)
        self.background_blur_strength=ValueRow(0,100,12,.1); background.addRow("Strength",self.background_blur_strength)
        self.background_blur_enabled.toggled.connect(self.edit_background_blur)
        self.background_blur_strength.edited.connect(lambda value,delta:self.edit_background_blur(None,value))
        composite=self.section(root,"Composite",lambda:self.reset_clip_section("composite")); self.mode=SafeComboBox(); self.mode.addItems(["Normal","Add","Multiply","Screen"]); self.mode.currentTextChanged.connect(lambda v:self.edit_bool("composite_mode",v)); composite.addRow("Composite Mode",self.mode)
        self.numeric(composite,"Opacity","opacity",0,100,100,.1); root.addStretch(); return panel

    def pair(self,form,label,attr_x,attr_y,low,high):
        host=QWidget(); layout=QHBoxLayout(host); layout.setContentsMargins(0,0,0,0); layout.setSpacing(3)
        rows=[]
        for axis,attr in [("X",attr_x),("Y",attr_y)]:
            row=ValueRow(low,high,0,.01,False); row.spin.setFixedWidth(66); row.reset.hide(); row.setFixedWidth(66)
            layout.addWidget(QLabel(axis)); layout.addWidget(row); rows.append(row); self.bindings.append((attr,row))
            row.edited.connect(lambda v,d,a=attr,r=row:self.edit_property(a,v,d,r.mixed))
        reset=QToolButton(); reset.setIcon(lucide_icon("rotate-ccw","#96989f",13)); reset.setToolTip("Reset "+label); layout.addWidget(reset)
        reset.clicked.connect(lambda:[row.change(0,True) for row in rows]); form.addRow(label,host)

    def reset_clip_section(self,section):
        for item in self.targets(False):
            if section=="transform":
                shape=item.transform.shape; item.transform=Transform(.5,.5,1); item.transform.shape=shape
            elif section=="cropping":item.crop=Crop(); item.crop_softness=0.; item.retain_image_position=False
            elif section=="composite":item.composite_mode="Normal"; item.opacity=100.
            elif section=="colour":item.grayscale=False; item.brightness=0.; item.contrast=1.; item.saturation=1.; item.sharpen=0.
        self.changed.emit()

    def reset_audio_section(self,*attrs):
        for item in self.targets(True):
            for attr in attrs:setattr(item,attr,0.)
        self.changed.emit()

    def edit_background_blur(self,enabled=None,strength=None):
        if self.updating:return
        for item in self.targets(False):
            effect=next((e for e in item.effects if e.get("inspector_background_blur")),None)
            if effect is None:
                if enabled is False:continue
                effect=dict(name="Gaussian Blur",inspector_background_blur=True,enabled=True,horizontal=12.,vertical=12.,linked=True,border="Reflect",blend=100.)
                item.effects.append(effect)
            if enabled is not None:effect["enabled"]=bool(enabled)
            if strength is not None:effect["horizontal"]=effect["vertical"]=strength
        self.changed.emit()

    def build_audio(self):
        panel=QWidget(); root=QVBoxLayout(panel); root.setContentsMargins(0,0,0,0)
        self.volume=self.numeric(self.section(root,"Volume",lambda:self.reset_audio_section("gain_db")),"Volume","gain_db",-60,18,0,.1,audio=True)
        self.numeric(self.section(root,"Pan",lambda:self.reset_audio_section("pan")),"Pan","pan",-1,1,0,.01,audio=True)
        form=self.section(root,"Pitch",lambda:self.reset_audio_section("pitch_semitones","pitch_cents")); self.numeric(form,"Semi Tones","pitch_semitones",-24,24,0,1,audio=True); self.numeric(form,"Cents","pitch_cents",-100,100,0,1,audio=True)
        root.addStretch(); return panel

    def build_audio_levels(self):
        panel=QWidget(); layout=QVBoxLayout(panel); layout.setContentsMargins(12,12,12,12); layout.setSpacing(8)
        title=QLabel("Selected audio track · live preview peak"); layout.addWidget(title)
        self.level_bars=[]
        for channel in ("L", "R"):
            row=QHBoxLayout(); row.addWidget(QLabel(channel))
            bar=QProgressBar(); bar.setRange(0,1000); bar.setValue(0); bar.setFormat("−∞ dBFS"); row.addWidget(bar,1)
            layout.addLayout(row); self.level_bars.append(bar)
        self.level_clip=QLabel("● No clipping detected"); layout.addWidget(self.level_clip)
        reset=QPushButton("Reset clip indicator"); reset.clicked.connect(lambda:self.window.transport.reset_meter_clips()); layout.addWidget(reset)
        self.level_mix=QLabel("Mix headroom: —"); layout.addWidget(self.level_mix)
        note=QLabel("Meters read decoded preview audio before the monitoring-volume slider. Mix headroom is a conservative peak-sum warning, not an exact export measurement.")
        note.setWordWrap(True); layout.addWidget(note); layout.addStretch()
        return panel

    def set_audio_levels(self,levels):
        if not hasattr(self,"level_bars") or not getattr(self.window,"project",None):return
        item=self.window.project.item_by_id(self.item_id)
        track=item.track if item and item.track in self.window.project.audio_tracks else ""
        left,right,clipped=levels.get(track,(0.,0.,False))
        from .audio_levels import peak_db
        for bar,peak in zip(self.level_bars,(left,right)):
            bar.setValue(round(max(0.,min(1000.,(peak_db(peak)+60)*1000/60))))
            bar.setFormat(f"{peak_db(peak):.1f} dBFS" if peak>1e-6 else "−∞ dBFS")
            colour='#4cbd72' if peak<.89 else '#e1c052' if peak<.999 else '#e45a51'
            bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {colour}; }}")
        self.level_clip.setText("● CLIP · reset after checking gain" if clipped else "● No clipping detected")
        self.level_clip.setStyleSheet("color: #e45a51" if clipped else "")
        potential=sum(max(values[:2]) for values in levels.values())
        self.level_mix.setText("Mix headroom: possible overload" if potential>=1 else f"Mix headroom: {peak_db(potential):.1f} dBFS peak-sum" if potential>1e-6 else "Mix headroom: —")

    def build_effects(self):
        panel=QWidget(); root=QVBoxLayout(panel); root.setContentsMargins(0,0,0,0)
        header=QHBoxLayout(); self.effect_picker=SafeComboBox(); self.effect_picker.currentIndexChanged.connect(self.refresh_effect); header.addWidget(self.effect_picker,1)
        remove=QToolButton(); remove.setIcon(lucide_icon("trash-2","#d6d7da",15)); remove.setToolTip("Remove selected effect"); remove.clicked.connect(self.remove_effect); header.addWidget(remove); root.addLayout(header)
        self.effect_enabled=QCheckBox("Effect enabled"); self.effect_enabled.setChecked(True); self.effect_enabled.toggled.connect(lambda v:self.edit_effect("enabled",v)); root.addWidget(self.effect_enabled)
        self.effect_detail=QWidget(); detail=QVBoxLayout(self.effect_detail); detail.setContentsMargins(0,0,0,0); form=self.section(detail,"Gaussian Blur",self.reset_effect_section)
        self.blur_h=ValueRow(0,100,12,.1); self.blur_v=ValueRow(0,100,12,.1)
        form.addRow("Horizontal Strength",self.blur_h); form.addRow("Vertical Strength",self.blur_v)
        self.blur_link=QCheckBox("Same Horizontal / Vertical"); self.blur_link.setChecked(True); form.addRow("",self.blur_link)
        self.blur_h.edited.connect(lambda v,d:self.edit_effect("horizontal",v)); self.blur_v.edited.connect(lambda v,d:self.edit_effect("vertical",v)); self.blur_link.toggled.connect(lambda v:self.edit_effect("linked",v))
        self.border=SafeComboBox(); self.border.addItems(["Reflect","Replicate"]); self.border.currentTextChanged.connect(lambda v:self.edit_effect("border",v)); form.addRow("Border Type",self.border)
        self.blend=ValueRow(0,100,100,.1); form.addRow("Global Blend",self.blend); self.blend.edited.connect(lambda v,d:self.edit_effect("blend",v))
        root.addWidget(self.effect_detail)
        self.key_panel=QWidget(); key_form=QFormLayout(self.key_panel)
        self.key_color=QPushButton("Key colour"); self.key_color.clicked.connect(self.pick_key_color); key_form.addRow("Colour",self.key_color)
        eyedropper=QPushButton("Pick colour in video…"); eyedropper.setToolTip("Eyedropper: scrub the original clip and click a pixel")
        eyedropper.setIcon(lucide_icon("pipette"))
        eyedropper.clicked.connect(self.sample_key_color); key_form.addRow(eyedropper)
        self.key_similarity=ValueRow(.1,100,15,.1); self.key_softness=ValueRow(0,100,8,.1)
        self.key_similarity.edited.connect(lambda value,delta:self.edit_effect("similarity",value)); self.key_softness.edited.connect(lambda value,delta:self.edit_effect("softness",value))
        key_form.addRow("Similarity (%)",self.key_similarity); key_form.addRow("Edge softness (%)",self.key_softness); root.addWidget(self.key_panel)
        self.effect_amount_panel=QWidget(); amount_layout=QFormLayout(self.effect_amount_panel)
        self.effect_amount=ValueRow(0,100,100,1); self.effect_amount.edited.connect(lambda value,delta:self.edit_effect("amount",value)); amount_layout.addRow("Strength (%)",self.effect_amount); root.addWidget(self.effect_amount_panel)

        # Visual FX dedicated controls
        self.vfx_panel=QWidget(); vfx_root=QVBoxLayout(self.vfx_panel); vfx_root.setContentsMargins(0,0,0,0); vfx_root.setSpacing(6)
        
        # 1. Timing & Easing
        timing_form=self.section(vfx_root,"Timing & Easing",self.reset_vfx_timing)
        self.vfx_timing_mode=SafeComboBox(); self.vfx_timing_mode.addItems(["At Clip Start","At Clip End","Custom / Playhead","Entire Clip"])
        self.vfx_timing_mode.currentTextChanged.connect(self.on_vfx_timing_mode_changed); timing_form.addRow("Trigger Point",self.vfx_timing_mode)
        start_host=QWidget(); start_hlayout=QHBoxLayout(start_host); start_hlayout.setContentsMargins(0,0,0,0); start_hlayout.setSpacing(4)
        self.vfx_start_time=ValueRow(0.0,3600.0,0.0,0.05,False); self.vfx_start_time.edited.connect(lambda v,d:self.edit_effect("start_time",v))
        self.vfx_timing_popout_start=QToolButton()
        self.vfx_timing_popout_start.setIcon(lucide_icon("external-link","#ffffff",13))
        self.vfx_timing_popout_start.setToolTip("Open Visual FX Timing & Range Editor")
        self.vfx_timing_popout_start.setFixedSize(26,26)
        self.vfx_timing_popout_start.clicked.connect(self.open_vfx_timing_dialog)
        start_hlayout.addWidget(self.vfx_start_time,1); start_hlayout.addWidget(self.vfx_timing_popout_start)
        timing_form.addRow("Start Offset (s)",start_host)
        dur_host=QWidget(); dur_hlayout=QHBoxLayout(dur_host); dur_hlayout.setContentsMargins(0,0,0,0); dur_hlayout.setSpacing(4)
        self.vfx_duration=ValueRow(0.05,30.0,1.0,0.05,True); self.vfx_duration.edited.connect(lambda v,d:self.edit_effect("duration",v))
        self.vfx_timing_popout=QToolButton()
        self.vfx_timing_popout.setIcon(lucide_icon("external-link","#ffffff",13))
        self.vfx_timing_popout.setToolTip("Open Visual FX Timing & Range Editor")
        self.vfx_timing_popout.setFixedSize(26,26)
        self.vfx_timing_popout.clicked.connect(self.open_vfx_timing_dialog)
        dur_hlayout.addWidget(self.vfx_duration,1); dur_hlayout.addWidget(self.vfx_timing_popout)
        timing_form.addRow("Duration (s)",dur_host)
        dur_chips=QWidget(); dur_layout=QHBoxLayout(dur_chips); dur_layout.setContentsMargins(0,0,0,0); dur_layout.setSpacing(4)
        for label,sec in [("0.2s",0.2),("0.5s",0.5),("1.0s",1.0),("2.0s",2.0)]:
            btn=QPushButton(label); btn.setFixedHeight(22); btn.setProperty('compact',True); btn.clicked.connect(lambda _,s=sec:[self.vfx_duration.change(s,True),self.edit_effect("duration",s)]); dur_layout.addWidget(btn)
        timing_form.addRow("Quick Presets",dur_chips)
        self.vfx_easing=SafeComboBox(); self.vfx_easing.addItems(["Smooth","Ease Out","Ease In","Linear","Snap","Bounce"])
        self.vfx_easing.currentTextChanged.connect(lambda v:self.edit_effect("easing",v)); timing_form.addRow("Motion Curve",self.vfx_easing)
        self.vfx_zoom_return=QCheckBox("Return to Normal (Ease Out)")
        self.vfx_zoom_return.setToolTip("Return to 1.0x neutral scale by easing out after zoom peak")
        self.vfx_zoom_return.toggled.connect(lambda v:[self.edit_effect("zoom_return",v),self.refresh_effect()])
        timing_form.addRow("",self.vfx_zoom_return)
        self.vfx_zoom_hold=ValueRow(0.0,5.0,0.15,0.05,True); self.vfx_zoom_hold.edited.connect(lambda v,d:self.edit_effect("zoom_hold_duration",v))
        timing_form.addRow("Hold Duration (s)",self.vfx_zoom_hold)
        self.vfx_zoom_attack=ValueRow(0.01,5.0,0.25,0.05,True); self.vfx_zoom_attack.edited.connect(lambda v,d:self.edit_effect("zoom_attack_duration",v))
        timing_form.addRow("Attack / Zoom In (s)",self.vfx_zoom_attack)
        self.vfx_show_overlay=QCheckBox("Show Timeline Overlay")
        self.vfx_show_overlay.setToolTip("Display visual effect duration and hold clamper overlay along the top of the media item on the timeline")
        self.vfx_show_overlay.toggled.connect(lambda v:self.edit_effect("show_timeline_overlay",v))
        timing_form.addRow("",self.vfx_show_overlay)

        # 2. Zooms Group
        self.vfx_zoom_panel=QWidget(); zoom_vbox=QVBoxLayout(self.vfx_zoom_panel); zoom_vbox.setContentsMargins(0,0,0,0)
        zoom_form=self.section(zoom_vbox,"Zoom Settings",self.reset_vfx_zoom)
        self.vfx_zoom_start=ValueRow(0.1,5.0,1.0,0.05,True); self.vfx_zoom_start.edited.connect(lambda v,d:self.edit_effect("zoom_start",v)); zoom_form.addRow("Start Scale",self.vfx_zoom_start)
        self.vfx_zoom_target=ValueRow(0.1,5.0,1.35,0.05,True); self.vfx_zoom_target.edited.connect(lambda v,d:self.edit_effect("zoom_target",v)); zoom_form.addRow("Target Scale",self.vfx_zoom_target)
        self.vfx_center_x=ValueRow(0.0,1.0,0.5,0.01,True); self.vfx_center_x.edited.connect(lambda v,d:self.edit_effect("center_x",v)); zoom_form.addRow("Focal Point X",self.vfx_center_x)
        self.vfx_center_y=ValueRow(0.0,1.0,0.5,0.01,True); self.vfx_center_y.edited.connect(lambda v,d:self.edit_effect("center_y",v)); zoom_form.addRow("Focal Point Y",self.vfx_center_y)
        focal_chips=QWidget(); focal_layout=QHBoxLayout(focal_chips); focal_layout.setContentsMargins(0,0,0,0); focal_layout.setSpacing(4)
        for label,(fx,fy) in [("Center",(0.5,0.5)),("Face",(0.5,0.35)),("Left",(0.3,0.5)),("Right",(0.7,0.5))]:
            b=QPushButton(label); b.setFixedHeight(22); b.setProperty('compact',True); b.clicked.connect(lambda _,px=fx,py=fy:[self.vfx_center_x.change(px,True),self.edit_effect("center_x",px),self.vfx_center_y.change(py,True),self.edit_effect("center_y",py)]); focal_layout.addWidget(b)
        zoom_form.addRow("Focal Presets",focal_chips)
        self.vfx_bounce_amp=ValueRow(0.0,1.0,0.25,0.02,True); self.vfx_bounce_amp.edited.connect(lambda v,d:self.edit_effect("bounce_amplitude",v)); zoom_form.addRow("Bounce Spring",self.vfx_bounce_amp)
        self.vfx_shake_int=ValueRow(0.0,80.0,15.0,1.0,True); self.vfx_shake_int.edited.connect(lambda v,d:self.edit_effect("shake_intensity",v)); zoom_form.addRow("Arrival Shake",self.vfx_shake_int)
        vfx_root.addWidget(self.vfx_zoom_panel)

        # 3. Camera Movement Group
        self.vfx_cam_panel=QWidget(); cam_vbox=QVBoxLayout(self.vfx_cam_panel); cam_vbox.setContentsMargins(0,0,0,0)
        cam_form=self.section(cam_vbox,"Camera Movement",self.reset_vfx_cam)
        self.vfx_pan_x_start=ValueRow(-1.0,1.0,0.0,0.01,True); self.vfx_pan_x_start.edited.connect(lambda v,d:self.edit_effect("pan_x_start",v)); cam_form.addRow("Pan X Start",self.vfx_pan_x_start)
        self.vfx_pan_x_end=ValueRow(-1.0,1.0,0.15,0.01,True); self.vfx_pan_x_end.edited.connect(lambda v,d:self.edit_effect("pan_x_end",v)); cam_form.addRow("Pan X End",self.vfx_pan_x_end)
        self.vfx_pan_y_start=ValueRow(-1.0,1.0,0.0,0.01,True); self.vfx_pan_y_start.edited.connect(lambda v,d:self.edit_effect("pan_y_start",v)); cam_form.addRow("Pan Y Start",self.vfx_pan_y_start)
        self.vfx_pan_y_end=ValueRow(-1.0,1.0,0.0,0.01,True); self.vfx_pan_y_end.edited.connect(lambda v,d:self.edit_effect("pan_y_end",v)); cam_form.addRow("Pan Y End",self.vfx_pan_y_end)
        self.vfx_tilt_angle=ValueRow(-45.0,45.0,0.0,0.5,True); self.vfx_tilt_angle.edited.connect(lambda v,d:self.edit_effect("tilt_angle",v)); cam_form.addRow("Tilt Angle (°)",self.vfx_tilt_angle)
        self.vfx_rot_angle=ValueRow(-180.0,180.0,0.0,1.0,True); self.vfx_rot_angle.edited.connect(lambda v,d:self.edit_effect("rotation_angle",v)); cam_form.addRow("Rotation (°)",self.vfx_rot_angle)
        self.vfx_handheld_speed=ValueRow(0.1,5.0,1.2,0.1,True); self.vfx_handheld_speed.edited.connect(lambda v,d:self.edit_effect("handheld_speed",v)); cam_form.addRow("Motion Speed",self.vfx_handheld_speed)
        self.vfx_handheld_amount=ValueRow(1.0,50.0,14.0,1.0,True); self.vfx_handheld_amount.edited.connect(lambda v,d:self.edit_effect("handheld_amount",v)); cam_form.addRow("Wobble (px)",self.vfx_handheld_amount)
        self.vfx_kb_swap=QPushButton("Reverse Start / End Framing"); self.vfx_kb_swap.setIcon(lucide_icon("repeat")); self.vfx_kb_swap.clicked.connect(self.swap_ken_burns); cam_form.addRow("",self.vfx_kb_swap)
        self.vfx_whip_dir=SafeComboBox(); self.vfx_whip_dir.addItems(["Right","Left","Up","Down"]); self.vfx_whip_dir.currentTextChanged.connect(lambda v:self.edit_effect("whip_direction",v)); cam_form.addRow("Whip Direction",self.vfx_whip_dir)
        vfx_root.addWidget(self.vfx_cam_panel)

        # 4. Shake & Impact Group
        self.vfx_shake_panel=QWidget(); shake_vbox=QVBoxLayout(self.vfx_shake_panel); shake_vbox.setContentsMargins(0,0,0,0)
        shake_form=self.section(shake_vbox,"Shake & Impact",self.reset_vfx_shake)
        self.vfx_amp_x=ValueRow(0.0,120.0,20.0,1.0,True); self.vfx_amp_x.edited.connect(lambda v,d:self.edit_effect("shake_amplitude_x",v)); shake_form.addRow("Horizontal (px)",self.vfx_amp_x)
        self.vfx_amp_y=ValueRow(0.0,120.0,15.0,1.0,True); self.vfx_amp_y.edited.connect(lambda v,d:self.edit_effect("shake_amplitude_y",v)); shake_form.addRow("Vertical (px)",self.vfx_amp_y)
        self.vfx_amp_rot=ValueRow(0.0,25.0,2.0,0.2,True); self.vfx_amp_rot.edited.connect(lambda v,d:self.edit_effect("shake_rotation",v)); shake_form.addRow("Roll Twitch (°)",self.vfx_amp_rot)
        self.vfx_freq=ValueRow(1.0,50.0,15.0,0.5,True); self.vfx_freq.edited.connect(lambda v,d:self.edit_effect("shake_frequency",v)); shake_form.addRow("Frequency (Hz)",self.vfx_freq)
        self.vfx_decay=SafeComboBox(); self.vfx_decay.addItems(["Exponential","Linear","Constant"]); self.vfx_decay.currentTextChanged.connect(lambda v:self.edit_effect("shake_decay",v)); shake_form.addRow("Decay Type",self.vfx_decay)
        vfx_root.addWidget(self.vfx_shake_panel)

        # 5. Keyframe Action Buttons
        actions_box=QHBoxLayout()
        self.vfx_bake_btn=QPushButton("Convert to Keyframes"); self.vfx_bake_btn.setIcon(lucide_icon("sliders-horizontal")); self.vfx_bake_btn.setToolTip("Bake this procedural effect into timeline keyframe curves for fine-tuning"); self.vfx_bake_btn.clicked.connect(self.bake_vfx_effect); actions_box.addWidget(self.vfx_bake_btn)
        self.vfx_reset_btn=QPushButton("Reset Defaults"); self.vfx_reset_btn.setIcon(lucide_icon("rotate-ccw")); self.vfx_reset_btn.setToolTip("Restore default parameters for this Visual FX effect"); self.vfx_reset_btn.clicked.connect(self.reset_vfx_defaults); actions_box.addWidget(self.vfx_reset_btn)
        vfx_root.addLayout(actions_box)
        root.addWidget(self.vfx_panel)

        self.effect_note=QLabel(); self.effect_note.setWordWrap(True); self.effect_note.setObjectName("emptyState"); root.addWidget(self.effect_note)
        from .tracking_ui import TrackingPanel
        self.tracking_panel=TrackingPanel(self); root.addWidget(self.tracking_panel); self.tracking_panel.hide()
        self.vision_reanalyse=QPushButton('Re-analyse current crop'); self.vision_reanalyse.clicked.connect(self.reanalyse_vision); root.addWidget(self.vision_reanalyse); self.vision_reanalyse.hide()
        self.vision_customize=QPushButton('Customize Face…'); self.vision_customize.clicked.connect(self.customize_vision); root.addWidget(self.vision_customize); self.vision_customize.hide()
        root.addStretch(); return panel

    def reanalyse_vision(self):
        from .vision_ui import begin
        begin(self.window,reanalyse=True)

    def customize_vision(self):
        from .vision_ui import customize
        customize(self.window)

    def build_colors(self):
        panel=QWidget(); root=QVBoxLayout(panel); root.setContentsMargins(0,0,0,0)
        presets=QHBoxLayout(); presets.addWidget(QLabel("Presets"))
        for label,values in [("Neutral",(False,0,1,1,0)),("HD Pop",(False,.04,1.16,1.12,.35)),("Cinematic",(False,-.03,1.12,.82,.18)),("B&W",(True,0,1.08,0,.2))]:
            button=QPushButton(label); button.clicked.connect(lambda _,v=values:self.apply_color_preset(v)); presets.addWidget(button)
        root.addLayout(presets); form=self.section(root,"Colour",lambda:self.reset_clip_section("colour"))
        self.grayscale=QCheckBox("Black & White"); self.grayscale.toggled.connect(lambda v:self.edit_color("grayscale",v)); form.addRow("",self.grayscale)
        for label,attr,lo,hi,default,step in [("Brightness","brightness",-.5,.5,0,.01),("Contrast","contrast",0,2,1,.01),("Saturation","saturation",0,2,1,.01),("Sharpen","sharpen",0,2,0,.01)]:
            row=ValueRow(lo,hi,default,step); form.addRow(label,row); self.color_bindings.append((attr,row)); row.edited.connect(lambda value,delta,a=attr,r=row:self.edit_color(a,value,delta,r.mixed))
        root.addStretch(); return panel

    def edit_color(self,attr,value,delta=float("nan"),mixed=False):
        if self.updating:return
        self.window.flush_text_edit()
        for item in self.targets(False):setattr(item,attr,value)
        self.changed.emit()

    def apply_color_preset(self,values):
        for item in self.targets(False):item.grayscale,item.brightness,item.contrast,item.saturation,item.sharpen=values
        self.changed.emit()

    def targets(self,audio=None):
        p=self.window.project; ids=self.window.timeline.selected_ids or {self.item_id}; items=[i for i in p.timeline if i.id in ids]
        primary=p.item_by_id(self.item_id)
        def kind(item):return 'title' if item.role=='title' else 'audio' if item.track in p.audio_tracks else 'video'
        return [i for i in items if not p.track_states.get(i.track,{}).get('locked') and (audio is None or (i.track in p.audio_tracks)==audio) and (not primary or kind(i)==kind(primary))]

    def property_value(self,item,attr):
        p=self.window.project; media=p.media_by_id(item.media_id); w=media.width if media else 1920; h=media.height if media else 1080
        special={"position_x":(item.transform.x-.5)*p.settings.width,"position_y":(.5-item.transform.y)*p.settings.height,
            "crop_left":item.crop.x*w,"crop_right":(1-item.crop.x-item.crop.width)*w,"crop_top":item.crop.y*h,"crop_bottom":(1-item.crop.y-item.crop.height)*h}
        if attr in special:return special[attr]
        if attr=="transform.scale_y":return item.transform.effective_scale_y
        if attr.startswith("transform."):return getattr(item.transform,attr.split(".")[1])
        return getattr(item,attr)

    def set_property(self,item,attr,value):
        p=self.window.project; m=p.media_by_id(item.media_id); w=max(1,m.width if m else 1920); h=max(1,m.height if m else 1080)
        bounds={"gain_db":(-60,18),"pan":(-1,1),"pitch_semitones":(-24,24),"pitch_cents":(-100,100)}
        if attr in bounds:value=max(bounds[attr][0],min(bounds[attr][1],value))
        if attr=="position_x":item.transform.x=.5+value/p.settings.width
        elif attr=="position_y":item.transform.y=.5-value/p.settings.height
        elif attr.startswith("crop_") and attr!="crop_softness":
            c=item.crop
            if attr=="crop_left":right=c.x+c.width; c.x=min(right-.02,value/w); c.width=right-c.x
            elif attr=="crop_right":c.width=max(.02,1-c.x-value/w)
            elif attr=="crop_top":bottom=c.y+c.height; c.y=min(bottom-.02,value/h); c.height=bottom-c.y
            else:c.height=max(.02,1-c.y-value/h)
            item.crop=c.clamped()
        elif attr.startswith("transform."):setattr(item.transform,attr.split(".")[1],value)
        else:setattr(item,attr,value)

    def edit_property(self,attr,value,delta,mixed=False):
        if self.updating:return
        audio=attr in {"gain_db","pan","pitch_semitones","pitch_cents"}
        self.window.flush_text_edit()
        for item in self.targets(audio):self.set_property(item,attr,value)
        self.changed.emit()

    def edit_bool(self,attr,value):
        if self.updating:return
        for item in self.targets(False):setattr(item,attr,value)
        self.changed.emit()
    def toggle_transform(self,attr,value):
        if self.updating:return
        for item in self.targets(False):setattr(item.transform,attr,value)
        self.changed.emit()
    def set_link(self,value):self.toggle_transform("scale_linked",value)
    def reset_zoom(self):
        if self.updating:return
        for item in self.targets(False):item.transform.scale=1.; item.transform.scale_y=1.
        self.zoom_x.set_values([1.]); self.zoom_y.set_values([1.]); self.changed.emit()
    def edit_zoom(self,attr,value):
        if self.updating:return
        for item in self.targets(False):
            transform=item.transform; x=transform.scale; y=transform.effective_scale_y
            if transform.scale_linked:
                factor=value/(x if attr=='scale' else y)
                factor=max(.01/min(x,y),min(10/max(x,y),factor))
                transform.scale=x*factor; transform.scale_y=y*factor
            else:
                # Materialize the implicit Y before changing X independently.
                transform.scale_y=y
                setattr(transform,attr,value)
        targets=self.targets(False)
        self.zoom_x.set_values([i.transform.scale for i in targets])
        self.zoom_y.set_values([i.transform.effective_scale_y for i in targets])
        self.changed.emit()

    def select(self,item_id):
        if not item_id and getattr(self, "transition_id", "") and getattr(self.window, "timeline", None) and getattr(self.window.timeline, "selected_transition_id", "") == self.transition_id:
            trans = self.window.project.transition_by_id(self.transition_id) if getattr(self.window, "project", None) else None
            if trans:
                self.refresh_transition(trans)
                return
        if not item_id and getattr(self.window, "timeline", None) and getattr(self.window.timeline, "selected_transition_id", ""):
            trans = self.window.project.transition_by_id(self.window.timeline.selected_transition_id) if getattr(self.window, "project", None) else None
            if trans:
                self.select_transition(trans.id)
                return
        self.transition_id=""
        if item_id!=self.item_id:self.window.flush_text_edit()
        previous_item=self.item_id; self.item_id=item_id; p=self.window.project; item=p.item_by_id(item_id)
        if item and item.role=="title":
            self.caption_id=""; self.updating=True; self.video_stack.setCurrentIndex(2); self.filename.setText("Title — "+(item.title_text or "Basic Title").replace("\n"," ")[:45])
            if self.title_text.toPlainText()!=item.title_text:self.title_text.blockSignals(True); self.title_text.setPlainText(item.title_text); self.title_text.moveCursor(QTextCursor.End); self.title_text.blockSignals(False)
            for index in range(4):self.tabs.setTabEnabled(index,index==0)
            self.tabs.setCurrentIndex(0); self.updating=False; self.relocate_style(); self.refresh_title(); return
        if item and item.role=="graphic":
            self.caption_id=""; self.updating=True; self.video_stack.setCurrentIndex(3); self.filename.setText(f"Graphic — {item.graphic_type or 'Graphic'}")
            for index in range(4):self.tabs.setTabEnabled(index,index==0)
            self.tabs.setCurrentIndex(0); self.updating=False; self.refresh_graphic(); return
        if self.caption_id and not item and self.current_caption() and self.window.timeline.selected_caption==self.caption_id:self.refresh_caption(); return
        self.caption_id=""; self.video_stack.setCurrentIndex(0); self.updating=True
        audio=bool(item and item.track in p.audio_tracks); video=bool(item and not audio)
        has_effects=bool(item and item.effects)
        self.video.setVisible(video); self.audio.setVisible(audio); self.effects.setVisible(has_effects); self.colors.setVisible(video)
        self.video.setEnabled(video); self.audio.setEnabled(audio); self.effects.setEnabled(has_effects); self.colors.setEnabled(video)
        self.tabs.setTabEnabled(0,video); self.tabs.setTabEnabled(1,audio); self.tabs.setTabEnabled(2,has_effects); self.tabs.setTabEnabled(3,video)
        if item and item_id!=previous_item:self.tabs.setCurrentIndex(1 if audio else 0)
        self.filename.setText(p.media_by_id(item.media_id).name if item and p.media_by_id(item.media_id) else "No clip selected")
        if item:
            bg=next((e for e in item.effects if e.get("inspector_background_blur")),{})
            self.background_blur_enabled.setChecked(bg.get("enabled",False)); self.background_blur_strength.setEnabled(bg.get("enabled",False))
            self.background_blur_strength.set_values([bg.get("horizontal",12.)])
            for attr,row in self.bindings+self.audio_bindings:row.set_values([self.property_value(i,attr) for i in self.targets(attr in {"gain_db","pan","pitch_semitones","pitch_cents"})])
            for attr,row in self.color_bindings:row.set_values([getattr(i,attr) for i in self.targets(False)])
            self.grayscale.setChecked(item.grayscale)
            self.link.setChecked(item.transform.scale_linked); self.flip_h.setChecked(item.transform.flip_horizontal); self.flip_v.setChecked(item.transform.flip_vertical); self.retain.setChecked(item.retain_image_position); self.mode.setCurrentText(item.composite_mode)
            if not self.tabs.isTabEnabled(self.tabs.currentIndex()):self.tabs.setCurrentIndex(1 if audio else 0)
            effect_index=self.effect_picker.currentIndex(); self.effect_picker.clear()
            for effect in item.effects:self.effect_picker.addItem(effect.get("name","Gaussian Blur"))
            self.effect_picker.setCurrentIndex(max(0,min(effect_index,len(item.effects)-1)))
        self.updating=False; self.video_presets.refresh(); self.refresh_effect()

    def effect(self):
        item=self.window.project.item_by_id(self.item_id); index=self.effect_picker.currentIndex()
        return item.effects[index] if item and 0<=index<len(item.effects) else None
    def refresh_effect(self,*_):
        from .effects import ADJUSTABLE, DESCRIPTIONS
        from .visual_fx import VISUAL_FX_SET, SUBSECTION_BY_EFFECT
        effect=self.effect()
        tracking=bool(effect and effect.get('name')=='Object Tracking')
        self.tracking_panel.setVisible(tracking)
        self.vision_reanalyse.hide()
        self.vision_customize.hide()
        if not effect:
            self.vfx_panel.hide(); return
        if tracking:
            self.vfx_panel.hide(); self.effect_detail.hide(); self.key_panel.hide(); self.effect_amount_panel.hide(); self.effect_note.hide()
            self.updating=True
            self.effect_enabled.setText('Object Tracking'); self.effect_enabled.setChecked(effect.get('enabled',True))
            self.updating=False; self.tracking_panel.refresh(effect); return
        is_vfx=effect.get("category")=="Visual FX" or effect.get("name") in VISUAL_FX_SET
        self.vfx_panel.setVisible(is_vfx)
        if is_vfx:
            self.effect_detail.hide(); self.key_panel.hide(); self.effect_amount_panel.hide(); self.effect_note.hide()
            self.updating=True
            self.effect_enabled.setText(effect.get("name","Visual FX")); self.effect_enabled.setChecked(effect.get("enabled",True))
            self.vfx_panel.setEnabled(effect.get("enabled",True))
            sub=effect.get("subsection",SUBSECTION_BY_EFFECT.get(effect.get("name"),"Zooms"))
            self.vfx_zoom_panel.setVisible(sub=="Zooms")
            self.vfx_cam_panel.setVisible(sub=="Camera Movement")
            self.vfx_shake_panel.setVisible(sub=="Shake / Impact Effects" or "Shake" in effect.get("name",""))
            item = self.window.project.item_by_id(self.item_id) if hasattr(self.window, "project") else None
            clip_dur = max(0.05, float(item.duration)) if item else 3600.0

            # Clamp sliders/spinboxes to max length of media item
            self.vfx_duration.set_maximum(clip_dur)
            self.vfx_start_time.set_maximum(clip_dur)

            # Clamp existing values if they exceed media length
            cur_dur = min(clip_dur, max(0.05, float(effect.get("duration", 1.0))))
            cur_start = min(clip_dur, max(0.0, float(effect.get("start_time", 0.0))))
            if effect.get("duration") != cur_dur:
                effect["duration"] = cur_dur
            if effect.get("start_time") != cur_start:
                effect["start_time"] = cur_start

            mode_map={"clip_start":"At Clip Start","clip_end":"At Clip End","playhead":"Custom / Playhead","entire_clip":"Entire Clip"}
            self.vfx_timing_mode.setCurrentText(mode_map.get(effect.get("timing_mode","clip_start"),"At Clip Start"))
            self.vfx_start_time.set_values([cur_start])
            self.vfx_duration.set_values([cur_dur])
            self.vfx_easing.setCurrentText(effect.get("easing","Smooth"))

            from .visual_fx import ZOOM_IN_EFFECTS
            name = effect.get("name", "")
            is_zoom_in = name in ZOOM_IN_EFFECTS
            has_return = is_zoom_in and bool(effect.get("zoom_return", False))
            self.vfx_zoom_return.setVisible(is_zoom_in)
            self.vfx_zoom_hold.setVisible(has_return)
            self.vfx_zoom_attack.setVisible(has_return)
            self.vfx_show_overlay.setVisible(True)
            self.vfx_show_overlay.setChecked(bool(effect.get("show_timeline_overlay", True)))
            self.vfx_zoom_hold.set_maximum(cur_dur)
            self.vfx_zoom_attack.set_maximum(cur_dur)
            if is_zoom_in:
                self.vfx_zoom_return.setChecked(bool(effect.get("zoom_return", False)))
                hold_v = float(effect.get("zoom_hold_duration", 0.15))
                self.vfx_zoom_hold.set_values([hold_v])
                def_att = round(max(0.01, (cur_dur - hold_v) / 2.0), 3)
                self.vfx_zoom_attack.set_values([float(effect.get("zoom_attack_duration", def_att))])
            self.vfx_zoom_start.set_values([effect.get("zoom_start",1.0)])
            self.vfx_zoom_target.set_values([effect.get("zoom_target",1.35)])
            self.vfx_center_x.set_values([effect.get("center_x",0.5)])
            self.vfx_center_y.set_values([effect.get("center_y",0.5)])
            self.vfx_bounce_amp.set_values([effect.get("bounce_amplitude",0.25)])
            self.vfx_shake_int.set_values([effect.get("shake_intensity",15.0)])
            self.vfx_pan_x_start.set_values([effect.get("pan_x_start",0.0)])
            self.vfx_pan_x_end.set_values([effect.get("pan_x_end",0.15)])
            self.vfx_pan_y_start.set_values([effect.get("pan_y_start",0.0)])
            self.vfx_pan_y_end.set_values([effect.get("pan_y_end",0.0)])
            self.vfx_tilt_angle.set_values([effect.get("tilt_angle",0.0)])
            self.vfx_rot_angle.set_values([effect.get("rotation_angle",0.0)])
            self.vfx_handheld_speed.set_values([effect.get("handheld_speed",1.2)])
            self.vfx_handheld_amount.set_values([effect.get("handheld_amount",14.0)])
            self.vfx_whip_dir.setCurrentText(effect.get("whip_direction","Right"))
            self.vfx_amp_x.set_values([effect.get("shake_amplitude_x",20.0)])
            self.vfx_amp_y.set_values([effect.get("shake_amplitude_y",15.0)])
            self.vfx_amp_rot.set_values([effect.get("shake_rotation",2.0)])
            self.vfx_freq.set_values([effect.get("shake_frequency",15.0)])
            self.vfx_decay.setCurrentText(effect.get("shake_decay","Exponential"))
            self.updating=False
            return
        blur=effect.get("name")=="Gaussian Blur"; self.effect_detail.setVisible(blur); self.effect_note.setVisible(not blur)
        self.effect_amount_panel.setVisible(effect.get("name") in ADJUSTABLE)
        from .chroma import NAMES
        self.key_panel.setVisible(effect.get("name") in NAMES); self.key_panel.setEnabled(effect.get("enabled",True))
        color=effect.get("color","#00ff00"); self.key_color.setText(color)
        self.key_color.setStyleSheet(f"background:{color};color:{'#111' if QColor(color).lightnessF()>.5 else '#fff'}")
        self.key_similarity.set_values([effect.get("similarity",15)]); self.key_softness.set_values([effect.get("softness",8)])
        self.effect_note.setText(DESCRIPTIONS.get(effect.get("name"),"Adjust this preset using the clip's Video, Audio or Colours controls."))
        from .vision_effects import NAMES as VISION_NAMES,status
        vision=effect.get('name') in VISION_NAMES; self.vision_reanalyse.setVisible(vision)
        self.vision_customize.setVisible(effect.get('name')=='Custom Face')
        if vision:
            item=self.window.project.item_by_id(self.item_id); media=self.window.project.media_by_id(item.media_id)
            note=status(item,media,item.source_time(self.window.project.playhead))
            self.effect_note.setText(self.effect_note.text()+'\n\n'+(note or 'Analysis ready. You can stack these effects, bypass them, or remove them.'))
        self.updating=True; self.effect_enabled.setText(effect.get("name","Effect")); self.effect_enabled.setChecked(effect.get("enabled",True))
        self.effect_amount.set_values([effect.get("amount",100)])
        self.effect_detail.setEnabled(effect.get("enabled",True)); self.effect_amount_panel.setEnabled(effect.get("enabled",True))
        if blur:self.blur_h.set_values([effect.get("horizontal",12)]); self.blur_v.set_values([effect.get("vertical",12)]); self.blur_link.setChecked(effect.get("linked",True)); self.border.setCurrentText(effect.get("border","Reflect")); self.blend.set_values([effect.get("blend",100)])
        self.updating=False

    def on_vfx_timing_mode_changed(self,text):
        if self.updating:return
        mapping={"At Clip Start":"clip_start","At Clip End":"clip_end","Custom / Playhead":"playhead","Entire Clip":"entire_clip"}
        mode=mapping.get(text,"clip_start"); self.edit_effect("timing_mode",mode)
        self.vfx_start_time.setEnabled(mode=="playhead")
        self.vfx_duration.setEnabled(mode!="entire_clip")

    def reset_vfx_timing(self):
        self.edit_effect("timing_mode","clip_start"); self.edit_effect("start_time",0.0); self.edit_effect("duration",1.0); self.edit_effect("easing","Smooth"); self.edit_effect("zoom_return",False); self.edit_effect("zoom_hold_duration",0.15); self.edit_effect("zoom_attack_duration",0.25); self.edit_effect("show_timeline_overlay",True); self.refresh_effect()

    def reset_vfx_zoom(self):
        effect=self.effect()
        if not effect:return
        from .visual_fx import default_visual_fx
        d=default_visual_fx(effect.get("name","Punch Zoom"))
        for k in ("zoom_start","zoom_target","center_x","center_y","bounce_amplitude","shake_intensity"):
            if k in d:self.edit_effect(k,d[k])
        self.refresh_effect()

    def reset_vfx_cam(self):
        effect=self.effect()
        if not effect:return
        from .visual_fx import default_visual_fx
        d=default_visual_fx(effect.get("name","Pan Left/Right"))
        for k in ("pan_x_start","pan_x_end","pan_y_start","pan_y_end","tilt_angle","rotation_angle","handheld_speed","handheld_amount","whip_direction","whip_blur"):
            if k in d:self.edit_effect(k,d[k])
        self.refresh_effect()

    def reset_vfx_shake(self):
        effect=self.effect()
        if not effect:return
        from .visual_fx import default_visual_fx
        d=default_visual_fx(effect.get("name","Camera Shake"))
        for k in ("shake_amplitude_x","shake_amplitude_y","shake_rotation","shake_frequency","shake_decay","shake_decay_rate"):
            if k in d:self.edit_effect(k,d[k])
        self.refresh_effect()

    def reset_vfx_defaults(self):
        effect=self.effect()
        if not effect:return
        from .visual_fx import default_visual_fx
        d=default_visual_fx(effect.get("name",""))
        for k,v in d.items():
            if k not in ("name","category","subsection"):self.edit_effect(k,v)
        self.refresh_effect()

    def swap_ken_burns(self):
        effect=self.effect()
        if not effect:return
        s1,s2=effect.get("ken_burns_start_scale",1.0),effect.get("ken_burns_end_scale",1.3)
        x1,x2=effect.get("ken_burns_start_x",0.5),effect.get("ken_burns_end_x",0.55)
        y1,y2=effect.get("ken_burns_start_y",0.5),effect.get("ken_burns_end_y",0.45)
        self.edit_effect("ken_burns_start_scale",s2); self.edit_effect("ken_burns_end_scale",s1)
        self.edit_effect("ken_burns_start_x",x2); self.edit_effect("ken_burns_end_x",x1)
        self.edit_effect("ken_burns_start_y",y2); self.edit_effect("ken_burns_end_y",y1)
        self.refresh_effect()

    def bake_vfx_effect(self):
        item=self.window.project.item_by_id(self.item_id); effect=self.effect()
        if not item or not effect:return
        from .visual_fx import bake_visual_fx_to_keyframes
        if bake_visual_fx_to_keyframes(item,effect):
            self.window.model_changed()
            self.window.statusBar().showMessage("Converted Visual FX to clip keyframes",3000)
            self.select(self.item_id)
    def pick_key_color(self):
        effect=self.effect()
        if not effect:return
        color=QColorDialog.getColor(QColor(effect.get("color","#00ff00")),self,"Chroma key colour")
        if color.isValid() and self.effect() is effect:self.edit_effect("color",color.name()); self.refresh_effect()

    def sample_key_color(self):
        from .chroma_dialog import ChromaSampleDialog
        item=self.window.project.item_by_id(self.item_id); effect=self.effect(); project=self.window.project
        if not item or not effect:return
        dialog=ChromaSampleDialog(self.window,item)
        if dialog.exec() and dialog.colour and self.window.project is project and self.effect() is effect and not project.track_states.get(item.track,{}).get("locked"):
            self.edit_effect("color",dialog.colour); self.refresh_effect()

    def open_vfx_timing_dialog(self):
        item = self.window.project.item_by_id(self.item_id) if hasattr(self.window, "project") else None
        effect = self.effect()
        if not item or not effect:
            return
        if getattr(self.window, "transport", None) and getattr(self.window.transport, "playing", False):
            self.window.transport.pause()
        from .vfx_timing_dialog import VFXTimingDialog
        dialog = VFXTimingDialog(self.window, item, effect, self)
        dialog.exec()
        self.refresh_effect()

    def edit_effect(self,key,value):
        if self.updating:return
        self.window.flush_text_edit(); primary=self.effect()
        if not primary:return
        for item,effect in self.effect_targets():
            if key=='enabled' and effect.get('before'):
                from .effects import toggle_preset
                toggle_preset(item,effect,value)
            else:effect[key]=value
            if key in {'horizontal','vertical'} and effect.get('linked',True):effect['horizontal']=effect['vertical']=value
        if primary.get('name')=='Gaussian Blur' and key in {'horizontal','vertical','linked'}:
            effects=[effect for _,effect in self.effect_targets()]
            self.blur_h.set_values([effect.get('horizontal',12) for effect in effects])
            self.blur_v.set_values([effect.get('vertical',12) for effect in effects])
        if key=="enabled" and primary.get("name")=="Auto Duck":
            self.window.duck.setChecked(any(e.get("name")=="Auto Duck" and e.get("enabled",True) for item in self.window.project.timeline for e in item.effects))
        if key in ("start_time", "duration", "zoom_return", "zoom_hold_duration", "zoom_attack_duration", "show_timeline_overlay"):
            if hasattr(self.window, "timeline") and hasattr(self.window.timeline, "flash_vfx_overlay"):
                self.window.timeline.flash_vfx_overlay(self.item_id)
        self.changed.emit()
    def effect_targets(self):
        primary=self.effect(); item=self.window.project.item_by_id(self.item_id)
        if not primary or not item:return []
        name=primary.get('name'); occurrence=sum(e.get('name')==name for e in item.effects[:self.effect_picker.currentIndex()])
        result=[]
        for target in self.targets():
            matches=[e for e in target.effects if e.get('name')==name]
            if occurrence<len(matches):result.append((target,matches[occurrence]))
        return result
    def reset_effect_section(self):
        for _,effect in self.effect_targets():
            if effect.get("name")=="Gaussian Blur":effect.update(enabled=True,horizontal=12.,vertical=12.,linked=True,border="Reflect",blend=100.)
        self.changed.emit()
    def remove_effect(self):
        targets=self.effect_targets()
        for item,effect in targets:
            if effect.get("before"):
                from .effects import toggle_preset, preset_owner
                toggle_preset(item,effect,False)
                # Rebase later presets when an earlier preset leaves the stack.
                for later in item.effects[item.effects.index(effect)+1:]:
                    if preset_owner(item,later.get("name")) is preset_owner(item,effect.get("name")):
                        for key,value in effect["before"].items():
                            if key in later.get("before",{}):later["before"][key]=value
            item.effects.remove(effect)
            if effect.get("name")=="Auto Duck":self.window.duck.setChecked(any(e.get("name")=="Auto Duck" and e.get("enabled",True) for other in self.window.project.timeline for e in other.effects))
        if targets:self.changed.emit(); self.select(self.item_id)

    def build_subtitle(self):
        tabs=QTabWidget(); caption=QWidget(); root=QVBoxLayout(caption)
        self.caption_header=QWidget(); header=QVBoxLayout(self.caption_header); header.setContentsMargins(0,0,0,0); root.addWidget(self.caption_header)
        times=QFormLayout(); self.caption_in=ValueRow(0,36000,0,.01,False); self.caption_out=ValueRow(0,36000,1,.01,False); times.addRow("In",self.caption_in); times.addRow("Out",self.caption_out); header.addLayout(times)
        self.caption_text=EmojiTextEdit(); self.caption_text.setFixedHeight(110); header.addWidget(self.caption_text)
        self.customize=QCheckBox("Customize Caption"); header.addWidget(self.customize)
        self.caption_header.setFixedHeight(header.sizeHint().height())
        self.caption_text.textChanged.connect(self.edit_caption); self.caption_in.edited.connect(lambda v,d:self.edit_caption_time('start',v)); self.caption_out.edited.connect(lambda v,d:self.edit_caption_time('end',v)); self.customize.toggled.connect(self.customize_caption)
        timing=QWidget(); timing_root=QVBoxLayout(timing)
        actions=QHBoxLayout()
        for label,callback in [("Add New",self.add_caption),("Prev",lambda:self.adjacent_caption(-1)),("Next",lambda:self.adjacent_caption(1))]:
            b=QPushButton(label); b.clicked.connect(callback); actions.addWidget(b)
        timing_root.addLayout(actions); self.caption_table=QTableWidget(0,3); self.caption_table.setHorizontalHeaderLabels(["In","Out","Caption"]); self.caption_table.horizontalHeader().setStretchLastSection(True); self.caption_table.cellClicked.connect(self.table_caption); timing_root.addWidget(self.caption_table)
        self.caption_table.setEditTriggers(QTableWidget.DoubleClicked|QTableWidget.EditKeyPressed)
        self.caption_table.setSelectionBehavior(QTableWidget.SelectRows); self.caption_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.caption_table.itemChanged.connect(self.edit_timing_cell); self.caption_table.itemSelectionChanged.connect(self.select_timing_rows)
        from .caption_highlights import HighlightDelegate
        self.caption_table.setItemDelegateForColumn(2,HighlightDelegate(self.caption_table))
        self.caption_table.setContextMenuPolicy(Qt.CustomContextMenu); self.caption_table.customContextMenuRequested.connect(self.caption_highlight_menu)
        self.caption_table.setToolTip('Double-click In, Out or Caption to edit. Ctrl/Shift selects multiple subtitles.')
        self.custom_style_host=QWidget(); self.custom_style_layout=QVBoxLayout(self.custom_style_host); self.custom_style_layout.setContentsMargins(0,0,0,0); root.addWidget(self.custom_style_host,1)
        self.caption_bottom_space=QWidget(); root.addWidget(self.caption_bottom_space,1)
        tabs.addTab(scroll(caption),"Caption")
        style=QWidget(); sr=QVBoxLayout(style); sr.setContentsMargins(0,0,0,0)
        char=self.section(sr,"Character",lambda:self.reset_style_section("font","font_face","color","size","line_spacing","kerning","alignment"))
        self.style_combo(char,"Font","font",[]); self.style_combo(char,"Font Face","font_face",["Regular","Bold","Italic","Bold Italic"]); self.style_color(char,"Color","color")
        for label,attr,lo,hi,default,step in [("Size","size",8,200,72,1),("Line Spacing","line_spacing",-50,100,0,1),("Kerning","kerning",-50,100,0,1)]:self.style_number(char,label,attr,lo,hi,default,step)
        self.style_combo(char,"Alignment","alignment",["Left","Center","Right","Justify"])
        stroke=self.section(sr,"Stroke",lambda:self.reset_style_section("outline","outline_width")); self.style_color(stroke,"Color","outline"); self.style_number(stroke,"Size","outline_width",0,30,7,1)
        transform=self.section(sr,"Transform",lambda:self.reset_style_section("position_x","position_y","zoom_x","zoom_y","zoom_linked","opacity","anchor"))
        self.style_number(transform,"Position X","position_x",-4,5,.5,.001); self.style_number(transform,"Position Y","position_y",-4,5,.78,.001)
        self.style_number(transform,"Zoom X","zoom_x",.1,5,1,.01); self.style_number(transform,"Zoom Y","zoom_y",.1,5,1,.01)
        self.style_check(transform,"Link Zoom X / Y","zoom_linked")
        self.style_number(transform,"Opacity","opacity",0,100,100,.1); self.style_combo(transform,"Anchor","anchor",["Top","Center","Bottom"])
        shadow=self.section(sr,"Drop Shadow",lambda:self.reset_style_section("shadow_enabled","shadow_color","shadow_x","shadow_y","shadow_blur","shadow_opacity"),"shadow_enabled"); self.style_color(shadow,"Color","shadow_color")
        offsets=QWidget(); offset_layout=QHBoxLayout(offsets); offset_layout.setContentsMargins(0,0,0,0); offset_layout.setSpacing(4)
        for axis,attr in (("X","shadow_x"),("Y","shadow_y")):
            if axis=="Y":offset_layout.addStretch()
            offset_layout.addWidget(QLabel(axis)); row=ValueRow(-100,100,3,.001,False); row.spin.setFixedWidth(66); row.spin.drag_sensitivity=.5; row.reset.hide(); row.setFixedWidth(66); row.display_scale=1
            offset_layout.addWidget(row); self.style_bindings.append((attr,row)); row.edited.connect(lambda v,d,a=attr:self.edit_style(a,v))
        reset=QToolButton(); reset.setIcon(lucide_icon("rotate-ccw","#96989f",13)); reset.setToolTip("Reset Offset"); reset.clicked.connect(lambda:self.reset_style_section("shadow_x","shadow_y")); offset_layout.addWidget(reset); shadow.addRow("Offset",offsets)
        for label,attr,default in [("Blur","shadow_blur",3),("Opacity","shadow_opacity",70)]:self.style_number(shadow,label,attr,0,100,default,1)
        bg=self.section(sr,"Background",lambda:self.reset_style_section("background_enabled","background_color","background_outline","background_outline_width","background_radius","background_opacity","background_override","background_width","background_height")); self.style_check(bg,"Enabled","background_enabled"); self.style_color(bg,"Color","background_color"); self.style_color(bg,"Outline Color","background_outline")
        self.style_number(bg,"Outline Width","background_outline_width",0,30,0,.1); self.style_number(bg,"Corner Radius","background_radius",0,.5,.01,.001); self.style_number(bg,"Opacity","background_opacity",0,100,50,.1)
        self.style_check(bg,"Override Sizing","background_override"); self.style_number(bg,"Width","background_width",.01,1,.9,.01); self.style_number(bg,"Height","background_height",.01,1,.15,.01)
        glow=self.section(sr,"Glow",lambda:self.reset_style_section("glow_enabled","glow_follow_color","glow_color","glow_radius","glow_opacity"),"glow_enabled")
        self.style_check(glow,"Use Text Color","glow_follow_color"); self.style_color(glow,"Color","glow_color")
        self.style_number(glow,"Radius","glow_radius",1,40,12,1); self.style_number(glow,"Opacity","glow_opacity",0,100,55,1)
        from .caption_words import ANIMATIONS
        animation_form=self.section(sr,"Animation",lambda:self.reset_style_section("animation","highlight")); self.style_combo(animation_form,"Reveal","animation",ANIMATIONS); self.style_color(animation_form,"Word Highlight Color","highlight")
        self.title_tts_section=self.build_title_tts()
        sr.addWidget(self.title_tts_section)
        sr.addStretch(); self.style_content=style; self.style_scroll=scroll(style); self.track_style_host=QWidget(); self.track_style_layout=QVBoxLayout(self.track_style_host); self.track_style_layout.setContentsMargins(0,0,0,0); self.track_style_layout.addWidget(self.style_scroll)
        tabs.addTab(self.track_style_host,"Track"); tabs.addTab(timing,'Timings'); tabs.addTab(self.build_subtitle_templates(),"Templates"); tabs.currentChanged.connect(lambda _:self.relocate_style()); return tabs

    def build_subtitle_templates(self):
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(8)
        self.inspector_template_cards = []
        cols = 2
        for idx, t in enumerate(CAPTION_TEMPLATES):
            card = TemplateCardWidget(t)
            card.clicked.connect(self.apply_inspector_template)
            self.inspector_template_cards.append(card)
            grid.addWidget(card, idx // cols, idx % cols)
        return scroll(content)

    @edit_only
    def apply_inspector_template(self, template_data):
        if self.window.project.track_states.get('subtitle_1', {}).get('locked'):
            return
        self.window.commit_history()
        is_none = template_data.get("is_none", False) or template_data.get("id") == "none"
        if is_none:
            default_style = CaptionStyle()
            default_style.id = None
            default_style.name = "Default"
            self.window.project.subtitle_style = copy.deepcopy(default_style)
            for c in self.window.project.captions:
                if not c.customize and not c.is_hook:
                    c.style = copy.deepcopy(default_style)
        else:
            target_style = self.window.project.subtitle_style
            target_style.id = template_data.get("id")
            target_style.name = template_data.get("name", "")
            for k, v in template_data.items():
                if hasattr(target_style, k):
                    setattr(target_style, k, copy.deepcopy(v) if isinstance(v, (list, dict)) else v)
            for c in self.window.project.captions:
                if not c.customize and not c.is_hook:
                    c.style = copy.deepcopy(target_style)

        self.sync_inspector_template_cards()
        self.changed.emit()
        self.window.model_changed()
        self.refresh_caption()
        self.relocate_style()

    def sync_inspector_template_cards(self):
        curr_id = getattr(self.window.project.subtitle_style, "id", None)
        if not curr_id:
            curr_id = "none"
        for card in getattr(self, "inspector_template_cards", []):
            card_id = card.template.get("id")
            card.set_selected(card_id == curr_id or (card.template.get("is_none") and curr_id == "none"))

    def build_title(self):
        panel=QWidget(); root=QVBoxLayout(panel); root.setContentsMargins(8,8,8,0); root.addWidget(QLabel("Rich Text"))
        self.title_text=EmojiTextEdit(); self.title_text.setPlaceholderText("Title text"); self.title_text.setMaximumHeight(120); self.title_text.textChanged.connect(self.edit_title); root.addWidget(self.title_text)
        self.headline_controls=QWidget(); headline_layout=QFormLayout(self.headline_controls); headline_layout.setContentsMargins(0,4,0,0)
        self.headline_color=QPushButton(); self.headline_color.setFixedSize(40,22); self.headline_color.clicked.connect(lambda:self.pick_color("color")); headline_layout.addRow("Color",self.headline_color)
        self.headline_size=ValueRow(20,250,100,1); self.headline_size.spin.setSuffix(" %"); self.headline_size.edited.connect(lambda v,d:self.edit_headline_size(v)); headline_layout.addRow("Size",self.headline_size)
        self.headline_duration=ValueRow(.05,60,5,.01); self.headline_duration.spin.setMaximum(3600); self.headline_duration.spin.setSuffix(" s"); self.headline_duration.edited.connect(lambda v,d:self.edit_headline_duration(v)); headline_layout.addRow("Duration",self.headline_duration)
        transform_body=QWidget(); positions=QFormLayout(transform_body); positions.setContentsMargins(0,4,0,4)
        self.headline_positions={}
        for axis,dimension in (("X","width"),("Y","height")):
            row=ValueRow(-20000,20000,getattr(self.window.project.settings,dimension)/2,.001,False); row.spin.setDecimals(3); row.edited.connect(lambda v,d,a=axis:self.edit_style("position_"+a.lower(),v/getattr(self.window.project.settings,"width" if a=="X" else "height"))); positions.addRow("Position "+axis,row); self.headline_positions[axis]=row
        headline_layout.addRow(InspectorSection("Transform",transform_body,reset_callback=lambda:self.center_headline()))
        hint=QLabel("Text wraps automatically. Press Enter for a new line.\nDrag the headline in the viewer to position it."); hint.setWordWrap(True); headline_layout.addRow(hint); root.addWidget(self.headline_controls); self.headline_controls.hide()
        self.title_style_host=QWidget(); self.title_style_layout=QVBoxLayout(self.title_style_host); self.title_style_layout.setContentsMargins(0,0,0,0); root.addWidget(self.title_style_host,1)
        self.title_bottom_space=QWidget(); root.addWidget(self.title_bottom_space,1); self.title_bottom_space.hide(); return panel

    def relocate_style(self):
        # Custom caption controls belong to the Caption tab's ONE outer scroll
        # area. Restore the reusable inner scroller only for Track/Title pages.
        if self.style_scroll.widget() is None:
            self.style_scroll.setWidget(self.style_content)
        self.style_scroll.show()
        title=self.window.project.item_by_id(self.item_id)
        if title and title.role=="title":
            self.style_scroll.setEnabled(not self.window.project.track_states.get(title.track,{}).get('locked'))
            headline=title.title_style.box_style=="headline"
            self.headline_controls.setVisible(headline); self.title_style_host.setVisible(not headline)
            self.title_bottom_space.setVisible(headline)
            if hasattr(self,"title_tts_section"):
                self.title_tts_section.setVisible(not headline)
            self.title_style_layout.addWidget(self.style_scroll); return
        c=self.current_caption(); custom=bool(c and c.customize and self.subtitle.currentIndex()==0)
        self.style_scroll.setEnabled(not self.window.project.track_states.get('subtitle_1',{}).get('locked'))
        if hasattr(self,"title_tts_section"):
            self.title_tts_section.setVisible(False)
        if custom:
            self.style_scroll.takeWidget(); self.style_scroll.hide()
            self.custom_style_layout.addWidget(self.style_content); self.style_content.show()
        else:self.track_style_layout.addWidget(self.style_scroll)
        self.custom_style_host.setVisible(custom)
        self.caption_bottom_space.setVisible(not custom)
        if c:self.refresh_caption()

    def style_number(self,form,label,attr,low,high,default,step):
        scale=self.window.project.settings.width if attr=="position_x" else self.window.project.settings.height if attr=="position_y" else 1
        row=ValueRow(low*scale,high*scale,default*scale,step*scale); row.display_scale=scale
        if attr in {'position_x','position_y'}:row.spin.drag_sensitivity=.5; row.spin.setDecimals(3); row.spin.setSingleStep(1)
        form.addRow(label,row); self.style_bindings.append((attr,row)); row.edited.connect(lambda v,d,a=attr,r=row:self.edit_style(a,v/r.display_scale))
    def style_combo(self,form,label,attr,values):
        from .caption_fonts import CaptionFontCombo
        combo=CaptionFontCombo() if attr=='font' else SafeComboBox(); combo.addItems(values); form.addRow(label,combo); self.style_combos.append((attr,combo)); combo.currentTextChanged.connect(lambda v,a=attr:self.edit_style(a,v))
    def style_check(self,form,label,attr):
        check=QCheckBox(label); form.addRow("",check); self.style_combos.append((attr,check)); check.toggled.connect(lambda v,a=attr:self.edit_style(a,v))
    def style_color(self,form,label,attr):
        host=QWidget(); layout=QHBoxLayout(host); layout.setContentsMargins(0,0,0,0)
        button=QPushButton(); button.setFixedSize(40,20); layout.addWidget(button); layout.addStretch(); reset=QToolButton(); reset.setIcon(lucide_icon("rotate-ccw","#96989f",13)); reset.setToolTip("Reset colour"); layout.addWidget(reset)
        reset.clicked.connect(lambda:self.edit_style(attr,getattr(CaptionStyle(),attr)))
        button.setAccessibleName(label+" colour"); button.setCursor(Qt.PointingHandCursor)
        form.addRow(label,host); self.style_colors.append((attr,button)); button.clicked.connect(lambda _checked=False,a=attr:self.pick_color(a))
    def current_caption(self):return next((c for c in self.window.project.captions if c.id==self.caption_id),None)
    def caption_targets(self,include_locked=False):
        if not include_locked and self.window.project.track_states.get('subtitle_1',{}).get('locked'):return []
        ids=self.window.timeline.selected_caption_ids or {self.caption_id}
        return [c for c in self.window.project.captions if c.id in ids]
    def style_targets(self,prepare=False):
        item=self.window.project.item_by_id(self.item_id)
        if item and item.role=='title':return [i.title_style for i in self.targets(False)]
        if prepare and self.window.project.track_states.get('subtitle_1',{}).get('locked'):return []
        if self.current_caption() and self.subtitle.currentIndex()==0:
            captions=self.caption_targets(include_locked=not prepare)
            if prepare:
                for c in captions:
                    if not c.customize and not c.is_hook:c.style=copy.deepcopy(self.window.project.subtitle_style); c.customize=True
            return [self.window.project.caption_style(c) for c in captions]
        return [self.window.project.subtitle_style]
    def style_target(self):
        item=self.window.project.item_by_id(self.item_id)
        if item and item.role=="title":return item.title_style
        caption=self.current_caption(); return caption.style if caption and self.subtitle.currentIndex()==0 and (caption.customize or caption.is_hook) else self.window.project.subtitle_style
    @edit_only
    def edit_style(self,attr,value):
        if self.updating:return
        self.window.flush_text_edit()
        for style in self.style_targets(True):
            if attr in {"zoom_x","zoom_y"} and style.zoom_linked:
                factor=value/getattr(style,attr); style.zoom_x*=factor; style.zoom_y*=factor
            else:setattr(style,attr,value)
        self.changed.emit()
    def reset_style_section(self,*attrs):
        self.window.flush_text_edit(); defaults=CaptionStyle()
        for style in self.style_targets(True):
            for attr in attrs:setattr(style,attr,copy.deepcopy(getattr(defaults,attr)))
        self.changed.emit()
    @edit_only
    def pick_color(self,attr):
        # Opacity is a separate Inspector property; do not offer an alpha value
        # here that would be silently discarded when storing the RGB colour.
        color=QColorDialog.getColor(QColor(getattr(self.style_target(),attr)),self,"Select "+attr.replace("_"," ").title(),QColorDialog.DontUseNativeDialog)
        if color.isValid():self.edit_style(attr,color.name())

    def refresh_style_controls(self,style):
        for attr,button in self.style_colors:
            value=getattr(style,attr)
            button.setStyleSheet(f"QPushButton {{background:{value};border:1px solid #7d8590;border-radius:2px;}} QPushButton:hover {{border:2px solid #d8e4f2;}} QPushButton:pressed {{border:2px solid #ed806f;}} QPushButton:disabled {{border-color:#474a51;}}")
            button.setToolTip(f"{attr.replace('_',' ').title()} · {value.upper()} · Click to choose")
        for attr,widget in self.style_bindings+self.style_colors+self.style_combos:
            enabled=True
            if attr.startswith("background_") and attr!="background_enabled":enabled=style.background_enabled and (attr not in {"background_width","background_height"} or style.background_override)
            if attr.startswith("shadow_") and attr!="shadow_enabled":enabled=style.shadow_enabled
            if attr.startswith("glow_") and attr!="glow_enabled":enabled=style.glow_enabled and (attr!='glow_color' or not style.glow_follow_color)
            widget.setEnabled(enabled)
    def select_caption(self,id):
        self.transition_id=""
        if id!=self.caption_id:self.window.flush_text_edit()
        self.caption_id=id; self.item_id=""; self.tabs.setTabEnabled(3,False); self.refresh_caption(); self.tabs.setCurrentIndex(0); self.video_stack.setCurrentIndex(1); self.relocate_style(); self.sync_inspector_template_cards()

    def refresh_title(self):
        item=self.window.project.item_by_id(self.item_id)
        if not item or item.role!="title":return
        self.updating=True; style=item.title_style; self.filename.setText("Title — "+(item.title_text or "Basic Title").replace("\n"," ")[:45])
        self.headline_size.set_values([style.zoom_x*100])
        self.headline_duration.set_values([item.duration]); self.headline_color.setStyleSheet(f"QPushButton {{background:{style.color};border:1px solid #7d8590;border-radius:2px;}} QPushButton:hover {{border:2px solid #d8e4f2;}}")
        for axis,row in self.headline_positions.items():row.set_values([getattr(style,"position_"+axis.lower())*getattr(self.window.project.settings,"width" if axis=="X" else "height")])
        for attr,row in self.style_bindings:
            if attr in {"position_x","position_y"}:
                scale=self.window.project.settings.width if attr=="position_x" else self.window.project.settings.height; row.display_scale=scale; row.low=-4*scale; row.high=5*scale; row.spin.setRange(row.low,row.high)
            row.set_values([getattr(style,attr)*row.display_scale])
        for attr,widget in self.style_combos:
            if isinstance(widget,(QCheckBox,QToolButton)):widget.setChecked(getattr(style,attr))
            else:widget.setCurrentText(getattr(style,attr))
        self.refresh_style_controls(style)
        is_tts=getattr(item,"tts_enabled",False)
        self.title_tts_enabled.blockSignals(True)
        self.title_tts_voice.blockSignals(True)
        self.title_tts_speed.spin.blockSignals(True)
        self.title_tts_pitch.spin.blockSignals(True)
        self.title_tts_enabled.setChecked(is_tts)
        v=getattr(item,"tts_voice","") or DEFAULT_VOICE
        idx=self.title_tts_voice.findData(v)
        if idx>=0:self.title_tts_voice.setCurrentIndex(idx)
        self.title_tts_speed.set_values([getattr(item,"tts_speed",0)])
        self.title_tts_pitch.set_values([getattr(item,"tts_pitch",0)])
        self.title_tts_enabled.blockSignals(False)
        self.title_tts_voice.blockSignals(False)
        self.title_tts_speed.spin.blockSignals(False)
        self.title_tts_pitch.spin.blockSignals(False)
        for w in (self.title_tts_voice,self.title_tts_speed,self.title_tts_pitch,self.title_tts_preview_btn,self.title_tts_generate_btn,self.title_tts_match_duration):
            w.setEnabled(is_tts)
        self.updating=False

    @edit_only
    def edit_headline_size(self,value):
        if self.updating:return
        self.window.flush_text_edit()
        for style in self.style_targets(True):style.zoom_x=style.zoom_y=value/100
        self.changed.emit()

    @edit_only
    def center_headline(self):
        self.window.flush_text_edit()
        for style in self.style_targets(True):style.position_x=style.position_y=.5
        self.changed.emit()

    @edit_only
    def edit_headline_duration(self,value):
        if self.updating:return
        self.window.flush_text_edit()
        for item in self.targets(False):
            if item.role=='title':item.duration=max(1/self.window.project.settings.fps,round(value*self.window.project.settings.fps)/self.window.project.settings.fps)
        self.window.project.overwrite({i.id for i in self.targets(False)}); self.changed.emit()

    @edit_only
    def edit_title(self):
        if self.updating:return
        for item in self.targets(False):
            if item.role=='title':item.title_text=self.title_text.toPlainText()
        self.window.text_edited()

    def build_title_tts(self):
        tts_body=QWidget(); form=QFormLayout(tts_body); form.setContentsMargins(12,8,8,12); form.setHorizontalSpacing(8); form.setVerticalSpacing(7)
        form.setLabelAlignment(Qt.AlignRight|Qt.AlignVCenter)
        self.title_tts_enabled=QCheckBox("Enable AI voiceover for this text box")
        self.title_tts_enabled.toggled.connect(self.toggle_title_tts)
        form.addRow("",self.title_tts_enabled)

        self.title_tts_voice=SafeComboBox()
        for display,vid in VOICES:
            self.title_tts_voice.addItem(display,vid)
        self.title_tts_voice.currentIndexChanged.connect(self.edit_title_tts_voice)
        form.addRow("Voice",self.title_tts_voice)

        self.title_tts_speed=ValueRow(-50,50,0,5,False)
        self.title_tts_speed.spin.setSuffix(" %")
        self.title_tts_speed.edited.connect(lambda v,d:self.edit_title_tts_speed(int(v)))
        form.addRow("Speed",self.title_tts_speed)

        self.title_tts_pitch=ValueRow(-40,40,0,2,False)
        self.title_tts_pitch.spin.setSuffix(" Hz")
        self.title_tts_pitch.edited.connect(lambda v,d:self.edit_title_tts_pitch(int(v)))
        form.addRow("Pitch",self.title_tts_pitch)

        self.title_tts_match_duration=QCheckBox("Sync text box duration to audio speech")
        self.title_tts_match_duration.setChecked(True)
        form.addRow("",self.title_tts_match_duration)

        btn_row=QHBoxLayout()
        self.title_tts_preview_btn=QPushButton(" Preview")
        self.title_tts_preview_btn.setIcon(lucide_icon("play","#ffffff",12))
        self.title_tts_preview_btn.clicked.connect(self.preview_title_tts)
        btn_row.addWidget(self.title_tts_preview_btn)

        self.title_tts_generate_btn=QPushButton(" Generate / Link Audio")
        self.title_tts_generate_btn.setIcon(lucide_icon("sparkles","#11130d",12))
        set_ui_style(self.title_tts_generate_btn, 'QPushButton {background:@accent;color:@accent_text;font-weight:700;border-radius:4px;padding:4px 8px;} QPushButton:hover {background:@accent;}')
        self.title_tts_generate_btn.clicked.connect(self.generate_title_tts)
        btn_row.addWidget(self.title_tts_generate_btn)
        form.addRow("",btn_row)

        self.title_tts_status=QLabel("")
        set_ui_style(self.title_tts_status, 'color:@info;font-size:11px;')
        self.title_tts_status.setWordWrap(True)
        self.title_tts_status.hide()
        form.addRow("",self.title_tts_status)

        return InspectorSection("Text to Speech (AI Voice)",tts_body,reset_callback=self.reset_title_tts)

    def reset_title_tts(self):
        if self.updating:return
        for item in self.targets(False):
            if item.role=='title':
                item.tts_enabled=False
                item.tts_voice=DEFAULT_VOICE
                item.tts_speed=0
                item.tts_pitch=0
        self.refresh_title()
        self.changed.emit()

    def toggle_title_tts(self,enabled):
        if self.updating:return
        for item in self.targets(False):
            if item.role=='title':item.tts_enabled=enabled
        for w in (self.title_tts_voice,self.title_tts_speed,self.title_tts_pitch,self.title_tts_preview_btn,self.title_tts_generate_btn,self.title_tts_match_duration):
            w.setEnabled(enabled)
        self.changed.emit()

    def edit_title_tts_voice(self):
        if self.updating:return
        voice=self.title_tts_voice.currentData()
        for item in self.targets(False):
            if item.role=='title':item.tts_voice=voice
        self.changed.emit()

    def edit_title_tts_speed(self,val):
        if self.updating:return
        for item in self.targets(False):
            if item.role=='title':item.tts_speed=val
        self.changed.emit()

    def edit_title_tts_pitch(self,val):
        if self.updating:return
        for item in self.targets(False):
            if item.role=='title':item.tts_pitch=val
        self.changed.emit()

    def preview_title_tts(self):
        text=self.title_text.toPlainText().strip()
        if not text:
            self.title_tts_status.setText("Enter text in the Title text box first.")
            self.title_tts_status.show(); return
        voice=self.title_tts_voice.currentData() or DEFAULT_VOICE
        speed=int(self.title_tts_speed.spin.value())
        pitch=int(self.title_tts_pitch.spin.value())
        if not hasattr(self,"_tts_preview_player"):
            self._tts_preview_player=QMediaPlayer(self)
            self._tts_preview_output=QAudioOutput(self)
            self._tts_preview_player.setAudioOutput(self._tts_preview_output)
            self._tts_preview_player.playbackStateChanged.connect(self._on_title_preview_state)
        if self._tts_preview_player.playbackState()==QMediaPlayer.PlayingState:
            self._tts_preview_player.stop()
            self.title_tts_preview_btn.setText(" Preview")
            self.title_tts_preview_btn.setIcon(lucide_icon("play","#ffffff",12))
            return
        try:
            path=synthesize_speech(text[:200],voice,speed,pitch)
            set_media_source(self._tts_preview_player,QUrl.fromLocalFile(path))
            self._tts_preview_player.play()
            self.title_tts_preview_btn.setText(" Stop")
            self.title_tts_preview_btn.setIcon(lucide_icon("square","#ff6b6b",12))
        except Exception as err:
            self.title_tts_status.setText(f"Preview error: {err}")
            self.title_tts_status.show()

    def _on_title_preview_state(self,state):
        if state!=QMediaPlayer.PlayingState:
            self.title_tts_preview_btn.setText(" Preview")
            self.title_tts_preview_btn.setIcon(lucide_icon("play","#ffffff",12))

    @edit_only
    def generate_title_tts(self):
        item=self.window.project.item_by_id(self.item_id)
        if not item or item.role!='title':return
        text=item.title_text.strip() or self.title_text.toPlainText().strip()
        if not text:
            self.title_tts_status.setText("Enter text in the Title text box first.")
            self.title_tts_status.show(); return
        voice=item.tts_voice or self.title_tts_voice.currentData() or DEFAULT_VOICE
        speed=item.tts_speed or int(self.title_tts_speed.spin.value())
        pitch=item.tts_pitch or int(self.title_tts_pitch.spin.value())
        try:
            path=synthesize_speech(text,voice,speed,pitch)
            probed=probe(path,self.window.settings.get("ffprobe","ffprobe"),self.window.settings.get("ffmpeg","ffmpeg"))
            self.window.project.add_media(probed)
            self.window.refresh_media()
            self.window.request_waveform(probed)

            p=self.window.project
            link=item.link_id or uid(); item.link_id=link
            linked_audio=next((i for i in p.timeline if i.track in p.audio_tracks and i.link_id and i.link_id==link),None)
            if linked_audio:
                linked_audio.media_id=probed.id; linked_audio.in_point=0.0; linked_audio.duration=probed.duration
                p.overwrite({linked_audio.id})
            else:
                track=p.audio_tracks[0] if p.audio_tracks else p.add_track("audio")
                audio_clip=TimelineItem(uid(),probed.id,track,item.start,probed.duration,0.0,group_id=item.group_id or uid(),link_id=link,role="sfx")
                p.timeline.append(audio_clip)
                p.overwrite({audio_clip.id})

            if self.title_tts_match_duration.isChecked():
                item.duration=probed.duration
                p.overwrite({item.id})

            item.tts_enabled=True
            self.title_tts_enabled.setChecked(True)
            self.window.commit_history()
            self.window.model_changed()
            self.title_tts_status.setText(f"✓ Linked voiceover ({probed.duration:.1f}s)")
            self.title_tts_status.show()
        except Exception as err:
            self.title_tts_status.setText(f"TTS error: {err}")
            self.title_tts_status.show()
    def refresh_caption(self):
        c=self.current_caption()
        if not c:return
        self.updating=True; count=len(self.caption_targets()); self.filename.setText(f'{count} subtitles selected' if count>1 else "Subtitle — "+c.text[:45]); self.tabs.setTabEnabled(0,True); self.tabs.setTabEnabled(1,False); self.tabs.setTabEnabled(2,False); self.tabs.setTabEnabled(3,False)
        if self.caption_text.toPlainText()!=c.text:self.caption_text.setPlainText(c.text); self.caption_text.moveCursor(QTextCursor.End)
        locked=self.window.project.track_states.get('subtitle_1',{}).get('locked',False)
        self.caption_text.setReadOnly(locked); self.caption_in.setEnabled(not locked); self.caption_out.setEnabled(not locked); self.customize.setEnabled(not locked)
        self.caption_in.set_values([c.start]); self.caption_out.set_values([c.end]); self.customize.setChecked(c.customize)
        style=self.style_target()
        for attr,row in self.style_bindings:
            if attr in {"position_x","position_y"}:
                scale=self.window.project.settings.width if attr=="position_x" else self.window.project.settings.height
                row.display_scale=scale; row.low=-4*scale; row.high=5*scale; row.default=(.5 if attr=="position_x" else .78)*scale; row.spin.setRange(row.low,row.high)
            row.set_values([getattr(value,attr)*row.display_scale for value in self.style_targets()])
        for attr,widget in self.style_combos:
            if isinstance(widget,(QCheckBox,QToolButton)):widget.setChecked(getattr(style,attr))
            else:widget.setCurrentText(getattr(style,attr))
        self.refresh_style_controls(style)
        self.sync_inspector_template_cards()
        if self.subtitle.currentIndex()==2:self.refresh_timings()
        self.updating=False
    def refresh_timings(self):
        table=self.caption_table; table.blockSignals(True); table.setUpdatesEnabled(False)
        vertical=table.verticalScrollBar().value(); horizontal=table.horizontalScrollBar().value()
        caps=sorted(self.window.project.captions,key=lambda c:c.start)
        signature=tuple((c.id,c.start,c.end,c.text,tuple(c.highlighted_words),self.window.project.caption_style(c).highlight,self.window.project.caption_style(c).animation) for c in caps)
        if signature!=getattr(self,'_timing_signature',None):
            table.setRowCount(len(caps))
            for row,cap in enumerate(caps):
                for col,value in enumerate([f'{cap.start:.3f}',f'{cap.end:.3f}',cap.text]):
                    item=QTableWidgetItem(value); item.setData(Qt.UserRole,cap.id); table.setItem(row,col,item)
                    if col==2 and cap.highlighted_words and self.window.project.caption_style(cap).animation=='word highlight 2':
                        item.setData(Qt.UserRole+1,(cap.highlighted_words,self.window.project.caption_style(cap).highlight))
                        item.setToolTip('Highlighted: '+', '.join(word for n,word in enumerate(cap.text.split()) if n in cap.highlighted_words)+' · Right-click to change')
            self._timing_signature=signature
        table.clearSelection()
        for row,cap in enumerate(caps):
            if cap.id in self.window.timeline.selected_caption_ids:table.setRangeSelected(QTableWidgetSelectionRange(row,0,row,2),True)
        table.verticalScrollBar().setValue(vertical); table.horizontalScrollBar().setValue(horizontal)
        table.setUpdatesEnabled(True); table.blockSignals(False)
    def caption_highlight_menu(self,pos):
        item=self.caption_table.itemAt(pos)
        if not item or item.column()!=2:return
        caption=next((c for c in self.window.project.captions if c.id==item.data(Qt.UserRole)),None)
        if not caption:return
        menu=QMenu(self); words=caption.text.split(); locked=self.window.project.track_states.get('subtitle_1',{}).get('locked',False)
        for index,word in enumerate(words):
            label='Unhighlight word' if index in caption.highlighted_words else 'Highlight word'
            action=menu.addAction(label+(' — '+word if len(words)>1 else '')); action.setEnabled(not locked)
            action.triggered.connect(lambda checked=False,c=caption.id,n=index:self.toggle_word_highlight(c,n))
        menu.exec(self.caption_table.viewport().mapToGlobal(pos))
    @edit_only
    def toggle_word_highlight(self,caption_id,index):
        if self.window.project.track_states.get('subtitle_1',{}).get('locked'):return
        caption=next((c for c in self.window.project.captions if c.id==caption_id),None)
        if not caption or not 0<=index<len(caption.text.split()):return
        self.window.flush_text_edit()
        if index in caption.highlighted_words:caption.highlighted_words.remove(index)
        else:caption.highlighted_words.append(index)
        if self.window.project.caption_style(caption).animation!='word highlight 2':
            caption.style=copy.deepcopy(self.window.project.caption_style(caption)); caption.customize=True; caption.style.animation='word highlight 2'
        self.changed.emit(); self.refresh_timings()
    def select_timing_rows(self):
        if self.updating:return
        ids={item.data(Qt.UserRole) for item in self.caption_table.selectedItems()}
        if ids:self.window.timeline.select_captions(ids,self.caption_id if self.caption_id in ids else next(iter(ids)))
    @edit_only
    def edit_timing_cell(self,item):
        if self.updating:return
        id=item.data(Qt.UserRole); column=item.column(); text=item.text()
        if column<2:
            try:
                value=float(text)
                if not math.isfinite(value) or not 0<=value<=36000:raise ValueError()
            except ValueError:
                self._timing_signature=None; self.refresh_timings(); self.window.statusBar().showMessage('Enter a time in seconds between 0 and 36000.',5000); return
        self.window.timeline.select_captions(self.window.timeline.selected_caption_ids if id in self.window.timeline.selected_caption_ids else {id},id)
        if column<2:self.edit_caption_time('start' if column==0 else 'end',value)
        else:
            from .caption_words import set_text
            for caption in self.caption_targets():set_text(caption,text)
            self.window.text_edited(); self.window.flush_text_edit(); self.refresh_caption()
        self._timing_signature=None; self.refresh_timings()
    @edit_only
    def edit_caption(self):
        if self.updating:return
        from .caption_words import set_text
        for c in self.caption_targets():set_text(c,self.caption_text.toPlainText())
        self.window.text_edited()
    @edit_only
    def edit_caption_time(self,attr,value):
        if self.updating:return
        self.window.flush_text_edit(); primary=self.current_caption(); captions=self.caption_targets()
        if not primary or not captions:return
        delta=value-getattr(primary,attr)
        if attr=='start':delta=max(-min(c.start for c in captions),min(delta,min(c.end-c.start-.05 for c in captions)))
        else:delta=max(delta,max(.05-c.end+c.start for c in captions))
        from .caption_words import shift_origin
        for c in captions:
            if attr=='start':shift_origin(c,delta)
            setattr(c,attr,getattr(c,attr)+delta)
        self.window.project.overwrite_captions({c.id for c in captions}); self.changed.emit()
    def customize_caption(self,value):
        if self.updating:return
        self.window.flush_text_edit()
        for c in self.caption_targets():
            if value and not c.customize and not c.is_hook:c.style=copy.deepcopy(self.window.project.subtitle_style)
            c.customize=value
        self.changed.emit(); self.relocate_style()
    def table_caption(self,row,col):
        id=self.caption_table.item(row,0).data(Qt.UserRole); ids=self.window.timeline.selected_caption_ids
        self.window.timeline.select_captions(ids if id in ids else {id},id)
        c=self.current_caption()
        if c:self.window.seek(c.start)
    def adjacent_caption(self,direction):
        caps=sorted(self.window.project.captions,key=lambda c:c.start); c=self.current_caption()
        if c:
            index=max(0,min(len(caps)-1,caps.index(c)+direction)); self.window.timeline.select_captions({caps[index].id},caps[index].id); self.window.seek(caps[index].start)
    @edit_only
    def add_caption(self):
        self.window.flush_text_edit(); p=self.window.project; c=Caption(uid(),p.playhead,p.playhead+1.5,"New caption"); p.captions.append(c); p.overwrite_captions({c.id}); self.window.inspector_toggle.setChecked(True); self.window.timeline.select_captions({c.id},c.id); self.changed.emit()
    def sync_scene(self):pass

    def update_btn_color(self, btn, color_hex):
        btn.setStyleSheet(f"QPushButton {{background:{color_hex}; border:1px solid #7d8590; border-radius:2px;}} QPushButton:hover {{border:2px solid #d8e4f2;}} QPushButton:pressed {{border:2px solid #ed806f;}}")
        btn.setToolTip(f"{str(color_hex).upper()} · Click to choose")

    @edit_only
    def pick_graphic_color(self, key, default="#ffffff"):
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        current = item.graphic_data.get(key, default)
        color = QColorDialog.getColor(QColor(current), self.window, f"Select {key.replace('_',' ').title()} Color", QColorDialog.DontUseNativeDialog)
        if color.isValid():
            item.graphic_data[key] = color.name()
            self.changed.emit()
            self.refresh_graphic()

    @edit_only
    def edit_graphic_prop(self, key, value):
        if self.updating: return
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        if key == "opacity":
            item.opacity = float(value)
        elif key == "fade_in":
            item.fade_in = float(value)
        elif key == "fade_out":
            item.fade_out = float(value)
        else:
            item.graphic_data[key] = value
        self.changed.emit()

    @edit_only
    def edit_graphic_duration(self, val):
        if self.updating: return
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        new_dur = max(0.05, float(val))
        item.duration = new_dur
        kind = getattr(item, "graphic_type", "").lower()
        if "timer" in kind:
            data = getattr(item, "graphic_data", {})
            if data.get("mode", "Countdown") == "Countdown":
                data["duration"] = new_dur
                self.gt_dur.set_values([new_dur])
        self.changed.emit()

    @edit_only
    def _timer_mode_changed(self, mode):
        if self.updating: return
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        data = getattr(item, "graphic_data", {})
        data["mode"] = mode
        is_countdown = (mode == "Countdown")
        if is_countdown:
            data["duration"] = item.duration
            self.gt_dur.set_values([item.duration])
        self.gt_dur.setEnabled(is_countdown)
        if hasattr(self, "tf_timer"):
            self.tf_timer.setRowVisible(self.gt_dur, is_countdown)
        self.changed.emit()

    @edit_only
    def _timer_glow_toggled(self, checked):
        if self.updating: return
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        data = getattr(item, "graphic_data", {})
        data["glow_enabled"] = checked
        if "glow_radius" not in data:
            data["glow_radius"] = 12.0
        if "glow_opacity" not in data:
            data["glow_opacity"] = 55.0
        if "glow_color" not in data:
            data["glow_color"] = "#55ffff"
        self.gt_glow_color.setEnabled(checked)
        if hasattr(self, "tf_timer"):
            self.tf_timer.setRowVisible(self.gt_glow_color, checked)
        self.changed.emit()

    @edit_only
    def edit_graphic_transform(self, attr, value):
        if self.updating: return
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        if attr=='scale' and item.transform.scale_y is None:
            item.transform.scale_y=item.transform.effective_scale_y
        setattr(item.transform, attr, float(value))
        self.changed.emit()

    @edit_only
    def edit_graphic_transform_pos(self, axis, pixel_val):
        if self.updating: return
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        dim = self.window.project.settings.width if axis == "x" else self.window.project.settings.height
        setattr(item.transform, axis, 0.5 + float(pixel_val) / max(1.0, float(dim)))
        self.changed.emit()

    @edit_only
    def reset_graphic_transform(self):
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        item.transform.x = 0.5
        item.transform.y = 0.5
        item.transform.scale = 1.0
        item.transform.scale_y = None
        item.transform.rotation = 0.0
        item.opacity = 100.0
        item.fade_in = 0.0
        item.fade_out = 0.0
        self.changed.emit()
        self.refresh_graphic()

    def build_graphic(self):
        panel = QWidget()
        root = QVBoxLayout(panel)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top_box = QWidget()
        top_layout = QFormLayout(top_box)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self.graphic_type_badge = QLabel("Circle")
        set_ui_style(self.graphic_type_badge, 'font-weight:bold; font-size:13px; color:@info;')
        top_layout.addRow("Graphic", self.graphic_type_badge)

        self.graphic_duration = ValueRow(0.1, 300, 2.0, 0.1, True)
        self.graphic_duration.spin.setSuffix(" s")
        self.graphic_duration.spin.setMaximum(3600)
        self.graphic_duration.edited.connect(lambda v, d: self.edit_graphic_duration(v))
        top_layout.addRow("Duration", self.graphic_duration)
        self.motion_edit=QPushButton('Edit Motion Composition…',top_box)
        self.motion_edit.clicked.connect(lambda:self.window.open_motion_composition(self.item_id))
        top_layout.addRow(self.motion_edit)
        root.addWidget(top_box)

        def color_btn(key, default="#00e5ff"):
            btn = QPushButton()
            btn.setFixedSize(40, 22)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key, df=default: self.pick_graphic_color(k, df))
            return btn

        # Circle
        circle_body = QWidget()
        cf = QFormLayout(circle_body); cf.setContentsMargins(0, 4, 0, 4)
        self.gc_color = color_btn("color", "#00e5ff"); cf.addRow("Line Color", self.gc_color)
        self.gc_thick = ValueRow(1, 60, 8, 1, True); self.gc_thick.spin.setSuffix(" px")
        self.gc_thick.edited.connect(lambda v, d: self.edit_graphic_prop("thickness", v)); cf.addRow("Thickness", self.gc_thick)
        self.gc_dash = SafeComboBox(); self.gc_dash.addItems(["Solid", "Dashed", "Dotted"])
        self.gc_dash.currentTextChanged.connect(lambda v: self.edit_graphic_prop("dash_style", v)); cf.addRow("Line Style", self.gc_dash)
        self.gc_radius = ValueRow(10, 800, 160, 2, True); self.gc_radius.spin.setSuffix(" px")
        self.gc_radius.edited.connect(lambda v, d: self.edit_graphic_prop("radius", v)); cf.addRow("Radius", self.gc_radius)
        self.gc_fill_enable = QCheckBox("Fill Interior")
        self.gc_fill_enable.toggled.connect(lambda v: self.edit_graphic_prop("fill_enabled", v)); cf.addRow("", self.gc_fill_enable)
        self.gc_fill_color = color_btn("fill_color", "#00e5ff"); cf.addRow("Fill Color", self.gc_fill_color)
        self.gc_fill_op = ValueRow(0, 100, 25, 1, True); self.gc_fill_op.spin.setSuffix(" %")
        self.gc_fill_op.edited.connect(lambda v, d: self.edit_graphic_prop("fill_opacity", v)); cf.addRow("Fill Opacity", self.gc_fill_op)
        self.sec_circle = InspectorSection("Circle Properties", circle_body); root.addWidget(self.sec_circle)

        # Arrow
        arrow_body = QWidget()
        af = QFormLayout(arrow_body); af.setContentsMargins(0, 4, 0, 4)
        self.ga_color = color_btn("color", "#ff3b30"); af.addRow("Arrow Color", self.ga_color)
        self.ga_style = SafeComboBox(); self.ga_style.addItems(["Standard Arrow", "Double-Headed", "Stealth / Dart", "Curved Arc"])
        self.ga_style.currentTextChanged.connect(lambda v: self.edit_graphic_prop("style", v)); af.addRow("Style", self.ga_style)
        self.ga_thick = ValueRow(2, 60, 12, 1, True); self.ga_thick.spin.setSuffix(" px")
        self.ga_thick.edited.connect(lambda v, d: self.edit_graphic_prop("thickness", v)); af.addRow("Stem Thickness", self.ga_thick)
        self.ga_head = ValueRow(10, 150, 48, 1, True); self.ga_head.spin.setSuffix(" px")
        self.ga_head.edited.connect(lambda v, d: self.edit_graphic_prop("head_size", v)); af.addRow("Head Size", self.ga_head)
        self.ga_len = ValueRow(40, 1200, 240, 5, True); self.ga_len.spin.setSuffix(" px")
        self.ga_len.edited.connect(lambda v, d: self.edit_graphic_prop("length", v)); af.addRow("Length", self.ga_len)
        self.ga_angle = ValueRow(-180, 180, 0, 1, True); self.ga_angle.spin.setSuffix(" °")
        self.ga_angle.edited.connect(lambda v, d: self.edit_graphic_prop("angle", v)); af.addRow("Direction Angle", self.ga_angle)
        self.sec_arrow = InspectorSection("Arrow Properties", arrow_body); root.addWidget(self.sec_arrow)

        # Square
        sq_body = QWidget()
        sqf = QFormLayout(sq_body); sqf.setContentsMargins(0, 4, 0, 4)
        self.gsq_color = color_btn("color", "#00e5ff"); sqf.addRow("Border Color", self.gsq_color)
        self.gsq_size = ValueRow(20, 1200, 260, 5, True); self.gsq_size.spin.setSuffix(" px")
        self.gsq_size.edited.connect(lambda v, d: self.edit_graphic_prop("size", v)); sqf.addRow("Size", self.gsq_size)
        self.gsq_thick = ValueRow(0, 60, 8, 1, True); self.gsq_thick.spin.setSuffix(" px")
        self.gsq_thick.edited.connect(lambda v, d: self.edit_graphic_prop("thickness", v)); sqf.addRow("Border Width", self.gsq_thick)
        self.gsq_cr = ValueRow(0, 200, 16, 1, True); self.gsq_cr.spin.setSuffix(" px")
        self.gsq_cr.edited.connect(lambda v, d: self.edit_graphic_prop("corner_radius", v)); sqf.addRow("Corner Radius", self.gsq_cr)
        self.gsq_fill_enable = QCheckBox("Fill Interior")
        self.gsq_fill_enable.toggled.connect(lambda v: self.edit_graphic_prop("fill_enabled", v)); sqf.addRow("", self.gsq_fill_enable)
        self.gsq_fill_color = color_btn("fill_color", "#00e5ff"); sqf.addRow("Fill Color", self.gsq_fill_color)
        self.gsq_fill_op = ValueRow(0, 100, 25, 1, True); self.gsq_fill_op.spin.setSuffix(" %")
        self.gsq_fill_op.edited.connect(lambda v, d: self.edit_graphic_prop("fill_opacity", v)); sqf.addRow("Fill Opacity", self.gsq_fill_op)
        self.sec_square = InspectorSection("Square Properties", sq_body); root.addWidget(self.sec_square)

        # Rectangle
        rec_body = QWidget()
        rf = QFormLayout(rec_body); rf.setContentsMargins(0, 4, 0, 4)
        self.grec_color = color_btn("color", "#00e5ff"); rf.addRow("Border Color", self.grec_color)
        self.grec_w = ValueRow(20, 1920, 420, 5, True); self.grec_w.spin.setSuffix(" px")
        self.grec_w.edited.connect(lambda v, d: self.edit_graphic_prop("width", v)); rf.addRow("Width", self.grec_w)
        self.grec_h = ValueRow(20, 1920, 240, 5, True); self.grec_h.spin.setSuffix(" px")
        self.grec_h.edited.connect(lambda v, d: self.edit_graphic_prop("height", v)); rf.addRow("Height", self.grec_h)
        self.grec_thick = ValueRow(0, 60, 8, 1, True); self.grec_thick.spin.setSuffix(" px")
        self.grec_thick.edited.connect(lambda v, d: self.edit_graphic_prop("thickness", v)); rf.addRow("Border Width", self.grec_thick)
        self.grec_cr = ValueRow(0, 200, 16, 1, True); self.grec_cr.spin.setSuffix(" px")
        self.grec_cr.edited.connect(lambda v, d: self.edit_graphic_prop("corner_radius", v)); rf.addRow("Corner Radius", self.grec_cr)
        self.grec_fill_enable = QCheckBox("Fill Interior")
        self.grec_fill_enable.toggled.connect(lambda v: self.edit_graphic_prop("fill_enabled", v)); rf.addRow("", self.grec_fill_enable)
        self.grec_fill_color = color_btn("fill_color", "#00e5ff"); rf.addRow("Fill Color", self.grec_fill_color)
        self.grec_fill_op = ValueRow(0, 100, 25, 1, True); self.grec_fill_op.spin.setSuffix(" %")
        self.grec_fill_op.edited.connect(lambda v, d: self.edit_graphic_prop("fill_opacity", v)); rf.addRow("Fill Opacity", self.grec_fill_op)
        self.sec_rectangle = InspectorSection("Rectangle Properties", rec_body); root.addWidget(self.sec_rectangle)

        # Timer
        timer_body = QWidget()
        self.tf_timer = QFormLayout(timer_body); self.tf_timer.setContentsMargins(0, 4, 0, 4)
        self.gt_mode = SafeComboBox(); self.gt_mode.addItems(["Countdown", "Stopwatch"])
        self.gt_mode.currentTextChanged.connect(self._timer_mode_changed); self.tf_timer.addRow("Type", self.gt_mode)
        self.gt_dur = ValueRow(0.1, 3600, 10, 0.1, True); self.gt_dur.spin.setSuffix(" s"); self.gt_dur.spin.setMaximum(86400)
        self.gt_dur.edited.connect(lambda v, d: self.edit_graphic_prop("duration", v)); self.tf_timer.addRow("Target Duration", self.gt_dur)
        self.gt_fmt = SafeComboBox(); self.gt_fmt.addItems(["MM:SS", "SS", "MM:SS.ms", "SS.ms"])
        self.gt_fmt.currentTextChanged.connect(lambda v: self.edit_graphic_prop("format", v)); self.tf_timer.addRow("Format", self.gt_fmt)
        from .caption_fonts import CaptionFontCombo
        self.gt_font = CaptionFontCombo(); self.gt_font.currentTextChanged.connect(lambda v: self.edit_graphic_prop("font", v)); self.tf_timer.addRow("Font", self.gt_font)
        self.gt_size = ValueRow(16, 240, 72, 2, True); self.gt_size.spin.setSuffix(" px")
        self.gt_size.edited.connect(lambda v, d: self.edit_graphic_prop("font_size", v)); self.tf_timer.addRow("Font Size", self.gt_size)
        self.gt_color = color_btn("color", "#ffffff"); self.tf_timer.addRow("Digit Color", self.gt_color)
        self.gt_glow_enable = QCheckBox("Font Glow")
        self.gt_glow_enable.toggled.connect(self._timer_glow_toggled); self.tf_timer.addRow("", self.gt_glow_enable)
        self.gt_glow_color = color_btn("glow_color", "#55ffff"); self.tf_timer.addRow("Glow Color", self.gt_glow_color)
        self.gt_bg_enable = QCheckBox("Card Background")
        self.gt_bg_enable.toggled.connect(lambda v: self.edit_graphic_prop("bg_enabled", v)); self.tf_timer.addRow("", self.gt_bg_enable)
        self.gt_bg_color = color_btn("bg_color", "#15181f"); self.tf_timer.addRow("Card Color", self.gt_bg_color)
        self.gt_bg_op = ValueRow(0, 100, 88, 1, True); self.gt_bg_op.spin.setSuffix(" %")
        self.gt_bg_op.edited.connect(lambda v, d: self.edit_graphic_prop("bg_opacity", v)); self.tf_timer.addRow("Card Opacity", self.gt_bg_op)
        self.gt_border_col = color_btn("border_color", "#3d8cff"); self.tf_timer.addRow("Border Color", self.gt_border_col)
        self.gt_border_w = ValueRow(0, 20, 2.5, 0.5, True); self.gt_border_w.spin.setSuffix(" px")
        self.gt_border_w.edited.connect(lambda v, d: self.edit_graphic_prop("border_width", v)); self.tf_timer.addRow("Border Width", self.gt_border_w)
        self.gt_cr = ValueRow(0, 60, 20, 1, True); self.gt_cr.spin.setSuffix(" px")
        self.gt_cr.edited.connect(lambda v, d: self.edit_graphic_prop("corner_radius", v)); self.tf_timer.addRow("Card Radius", self.gt_cr)
        self.sec_timer = InspectorSection("Timer & Stopwatch", timer_body); root.addWidget(self.sec_timer)

        # Speech Bubble / Quote Card
        sp_body = QWidget()
        spf = QFormLayout(sp_body); spf.setContentsMargins(0, 4, 0, 4)
        self.gsp_text = EmojiTextEdit(); self.gsp_text.setMaximumHeight(85); self.gsp_text.setPlaceholderText("Enter quote or speech...")
        self.gsp_text.textChanged.connect(lambda: self.edit_graphic_prop("text", self.gsp_text.toPlainText())); spf.addRow("Message", self.gsp_text)
        self.gsp_tail = SafeComboBox(); self.gsp_tail.addItems(["Bottom-Left", "Bottom-Right", "Top-Left", "Top-Right", "None"])
        self.gsp_tail.currentTextChanged.connect(lambda v: self.edit_graphic_prop("tail_position", v)); spf.addRow("Tail Pointer", self.gsp_tail)
        self.gsp_font = CaptionFontCombo(); self.gsp_font.currentTextChanged.connect(lambda v: self.edit_graphic_prop("font", v)); spf.addRow("Font", self.gsp_font)
        self.gsp_fsize = ValueRow(12, 140, 44, 1, True); self.gsp_fsize.spin.setSuffix(" px")
        self.gsp_fsize.edited.connect(lambda v, d: self.edit_graphic_prop("font_size", v)); spf.addRow("Font Size", self.gsp_fsize)
        self.gsp_tcolor = color_btn("color", "#ffffff"); spf.addRow("Text Color", self.gsp_tcolor)
        self.gsp_bgcolor = color_btn("bg_color", "#1f242d"); spf.addRow("Bubble Color", self.gsp_bgcolor)
        self.gsp_bgop = ValueRow(0, 100, 94, 1, True); self.gsp_bgop.spin.setSuffix(" %")
        self.gsp_bgop.edited.connect(lambda v, d: self.edit_graphic_prop("bg_opacity", v)); spf.addRow("Bubble Opacity", self.gsp_bgop)
        self.gsp_bordercol = color_btn("border_color", "#62d0ff"); spf.addRow("Border Color", self.gsp_bordercol)
        self.gsp_borderw = ValueRow(0, 20, 2.5, 0.5, True); self.gsp_borderw.spin.setSuffix(" px")
        self.gsp_borderw.edited.connect(lambda v, d: self.edit_graphic_prop("border_width", v)); spf.addRow("Border Width", self.gsp_borderw)
        self.gsp_cr = ValueRow(0, 60, 22, 1, True); self.gsp_cr.spin.setSuffix(" px")
        self.gsp_cr.edited.connect(lambda v, d: self.edit_graphic_prop("corner_radius", v)); spf.addRow("Corner Radius", self.gsp_cr)
        self.sec_speech = InspectorSection("Speech Bubble / Quote", sp_body); root.addWidget(self.sec_speech)

        # Progress Bar
        pb_body = QWidget()
        pbf = QFormLayout(pb_body); pbf.setContentsMargins(0, 4, 0, 4)
        self.gpb_barcol = color_btn("color", "#00e5ff"); pbf.addRow("Bar Color", self.gpb_barcol)
        self.gpb_trackcol = color_btn("track_color", "#252b36"); pbf.addRow("Track Color", self.gpb_trackcol)
        self.gpb_height = ValueRow(4, 60, 14, 1, True); self.gpb_height.spin.setSuffix(" px")
        self.gpb_height.edited.connect(lambda v, d: self.edit_graphic_prop("height", v)); pbf.addRow("Height", self.gpb_height)
        self.gpb_cr = ValueRow(0, 30, 7, 1, True); self.gpb_cr.spin.setSuffix(" px")
        self.gpb_cr.edited.connect(lambda v, d: self.edit_graphic_prop("corner_radius", v)); pbf.addRow("Corner Radius", self.gpb_cr)
        self.gpb_dir = SafeComboBox(); self.gpb_dir.addItems(["Left to Right", "Right to Left"])
        self.gpb_dir.currentTextChanged.connect(lambda v: self.edit_graphic_prop("direction", v)); pbf.addRow("Direction", self.gpb_dir)
        self.sec_progress = InspectorSection("Progress Bar Properties", pb_body); root.addWidget(self.sec_progress)

        # Callout Badge
        bd_body = QWidget()
        bdf = QFormLayout(bd_body); bdf.setContentsMargins(0, 4, 0, 4)
        self.gbd_text = QLineEdit(); self.gbd_text.textChanged.connect(lambda v: self.edit_graphic_prop("text", v)); bdf.addRow("Badge Text", self.gbd_text)
        self.gbd_bgcolor = color_btn("bg_color", "#d9ff43"); bdf.addRow("Badge Color", self.gbd_bgcolor)
        self.gbd_tcolor = color_btn("color", "#11130d"); bdf.addRow("Text Color", self.gbd_tcolor)
        self.gbd_fsize = ValueRow(14, 100, 48, 1, True); self.gbd_fsize.spin.setSuffix(" px")
        self.gbd_fsize.edited.connect(lambda v, d: self.edit_graphic_prop("font_size", v)); bdf.addRow("Font Size", self.gbd_fsize)
        self.gbd_cr = ValueRow(0, 50, 24, 1, True); self.gbd_cr.spin.setSuffix(" px")
        self.gbd_cr.edited.connect(lambda v, d: self.edit_graphic_prop("corner_radius", v)); bdf.addRow("Corner Radius", self.gbd_cr)
        self.gbd_pulse = QCheckBox("Pulse Animation"); self.gbd_pulse.toggled.connect(lambda v: self.edit_graphic_prop("pulse", v)); bdf.addRow("", self.gbd_pulse)
        self.sec_badge = InspectorSection("Callout Badge Properties", bd_body); root.addWidget(self.sec_badge)

        # Transform & Animation
        tr_body = QWidget()
        trf = QFormLayout(tr_body); trf.setContentsMargins(0, 4, 0, 4)
        self.gtr_x = ValueRow(-1920, 1920, 0, 1, True); self.gtr_x.spin.setSuffix(" px")
        self.gtr_x.edited.connect(lambda v, d: self.edit_graphic_transform_pos("x", v)); trf.addRow("Position X", self.gtr_x)
        self.gtr_y = ValueRow(-1920, 1920, 0, 1, True); self.gtr_y.spin.setSuffix(" px")
        self.gtr_y.edited.connect(lambda v, d: self.edit_graphic_transform_pos("y", v)); trf.addRow("Position Y", self.gtr_y)
        self.gtr_scale = ValueRow(0.1, 5.0, 1.0, 0.05, True)
        self.gtr_scale.edited.connect(lambda v, d: self.edit_graphic_transform("scale", v)); trf.addRow("Scale X", self.gtr_scale)
        self.gtr_scale_y = ValueRow(0.1, 5.0, 1.0, 0.05, True)
        self.gtr_scale_y.edited.connect(lambda v, d: self.edit_graphic_transform("scale_y", v)); trf.addRow("Scale Y", self.gtr_scale_y)
        self.gtr_rot = ValueRow(-180, 180, 0, 1, True); self.gtr_rot.spin.setSuffix(" °")
        self.gtr_rot.edited.connect(lambda v, d: self.edit_graphic_transform("rotation", v)); trf.addRow("Rotation", self.gtr_rot)
        self.gtr_opacity = ValueRow(0, 100, 100, 1, True); self.gtr_opacity.spin.setSuffix(" %")
        self.gtr_opacity.edited.connect(lambda v, d: self.edit_graphic_prop("opacity", v)); trf.addRow("Opacity", self.gtr_opacity)
        self.gtr_fadein = ValueRow(0, 10, 0, 0.05, True); self.gtr_fadein.spin.setSuffix(" s")
        self.gtr_fadein.edited.connect(lambda v, d: self.edit_graphic_prop("fade_in", v)); trf.addRow("Fade In", self.gtr_fadein)
        self.gtr_fadeout = ValueRow(0, 10, 0, 0.05, True); self.gtr_fadeout.spin.setSuffix(" s")
        self.gtr_fadeout.edited.connect(lambda v, d: self.edit_graphic_prop("fade_out", v)); trf.addRow("Fade Out", self.gtr_fadeout)
        self.sec_transform = InspectorSection("Transform & Animation", tr_body, reset_callback=self.reset_graphic_transform)
        root.addWidget(self.sec_transform)

        root.addStretch()
        return panel

    def refresh_graphic(self):
        item = self.window.project.item_by_id(self.item_id)
        if not item or item.role != "graphic": return
        self.updating = True
        kind = getattr(item, "graphic_type", "circle").lower()
        data = getattr(item, "graphic_data", {}) or {}
        p_settings = self.window.project.settings

        self.graphic_type_badge.setText(item.graphic_type or "Graphic")
        self.graphic_duration.set_values([item.duration])
        self.motion_edit.setVisible(kind in ('motion','motion composition'))

        self.sec_circle.setVisible("circle" in kind)
        self.sec_arrow.setVisible("arrow" in kind)
        self.sec_square.setVisible("square" in kind)
        self.sec_rectangle.setVisible("rectangle" in kind)
        self.sec_timer.setVisible("timer" in kind)
        self.sec_speech.setVisible("speech" in kind or "quote" in kind)
        self.sec_progress.setVisible("progress" in kind)
        self.sec_badge.setVisible("badge" in kind or "callout" in kind)

        if "circle" in kind:
            self.update_btn_color(self.gc_color, data.get("color", "#00e5ff"))
            self.gc_thick.set_values([float(data.get("thickness", 8.0))])
            self.gc_dash.setCurrentText(data.get("dash_style", "Solid"))
            self.gc_radius.set_values([float(data.get("radius", 160.0))])
            self.gc_fill_enable.setChecked(bool(data.get("fill_enabled", False)))
            self.update_btn_color(self.gc_fill_color, data.get("fill_color", "#00e5ff"))
            self.gc_fill_op.set_values([float(data.get("fill_opacity", 25.0))])
        elif "arrow" in kind:
            self.update_btn_color(self.ga_color, data.get("color", "#ff3b30"))
            self.ga_style.setCurrentText(data.get("style", "Standard Arrow"))
            self.ga_thick.set_values([float(data.get("thickness", 12.0))])
            self.ga_head.set_values([float(data.get("head_size", 48.0))])
            self.ga_len.set_values([float(data.get("length", 240.0))])
            self.ga_angle.set_values([float(data.get("angle", 0.0))])
        elif "square" in kind:
            self.update_btn_color(self.gsq_color, data.get("color", "#00e5ff"))
            self.gsq_size.set_values([float(data.get("size", 260.0))])
            self.gsq_thick.set_values([float(data.get("thickness", 8.0))])
            self.gsq_cr.set_values([float(data.get("corner_radius", 16.0))])
            self.gsq_fill_enable.setChecked(bool(data.get("fill_enabled", False)))
            self.update_btn_color(self.gsq_fill_color, data.get("fill_color", "#00e5ff"))
            self.gsq_fill_op.set_values([float(data.get("fill_opacity", 25.0))])
        elif "rectangle" in kind:
            self.update_btn_color(self.grec_color, data.get("color", "#00e5ff"))
            self.grec_w.set_values([float(data.get("width", 420.0))])
            self.grec_h.set_values([float(data.get("height", 240.0))])
            self.grec_thick.set_values([float(data.get("thickness", 8.0))])
            self.grec_cr.set_values([float(data.get("corner_radius", 16.0))])
            self.grec_fill_enable.setChecked(bool(data.get("fill_enabled", False)))
            self.update_btn_color(self.grec_fill_color, data.get("fill_color", "#00e5ff"))
            self.grec_fill_op.set_values([float(data.get("fill_opacity", 25.0))])
        elif "timer" in kind:
            mode = data.get("mode", "Countdown")
            is_countdown = (mode == "Countdown")
            if is_countdown:
                if "duration" not in data or data.get("duration") != item.duration:
                    data["duration"] = item.duration
                self.gt_dur.set_values([float(data["duration"])])
            else:
                self.gt_dur.set_values([float(data.get("duration", 10.0))])

            self.gt_mode.setCurrentText(mode)
            self.gt_dur.setEnabled(is_countdown)
            if hasattr(self, "tf_timer"):
                self.tf_timer.setRowVisible(self.gt_dur, is_countdown)

            self.gt_fmt.setCurrentText(data.get("format", "MM:SS"))
            self.gt_font.setCurrentText(data.get("font", "Arial"))
            self.gt_size.set_values([float(data.get("font_size", 72.0))])
            self.update_btn_color(self.gt_color, data.get("color", "#ffffff"))

            # Glow
            glow_en = bool(data.get("glow_enabled", False))
            self.gt_glow_enable.setChecked(glow_en)
            self.update_btn_color(self.gt_glow_color, data.get("glow_color", "#55ffff"))
            self.gt_glow_color.setEnabled(glow_en)
            if hasattr(self, "tf_timer"):
                self.tf_timer.setRowVisible(self.gt_glow_color, glow_en)

            self.gt_bg_enable.setChecked(bool(data.get("bg_enabled", True)))
            self.update_btn_color(self.gt_bg_color, data.get("bg_color", "#15181f"))
            self.gt_bg_op.set_values([float(data.get("bg_opacity", 88.0))])
            self.update_btn_color(self.gt_border_col, data.get("border_color", "#3d8cff"))
            self.gt_border_w.set_values([float(data.get("border_width", 2.5))])
            self.gt_cr.set_values([float(data.get("corner_radius", 20.0))])
        elif "speech" in kind or "quote" in kind:
            if self.gsp_text.toPlainText() != data.get("text", ""):
                self.gsp_text.blockSignals(True)
                self.gsp_text.setPlainText(str(data.get("text", "")))
                self.gsp_text.blockSignals(False)
            self.gsp_tail.setCurrentText(data.get("tail_position", "Bottom-Left"))
            self.gsp_font.setCurrentText(data.get("font", "Segoe UI"))
            self.gsp_fsize.set_values([float(data.get("font_size", 44.0))])
            self.update_btn_color(self.gsp_tcolor, data.get("color", "#ffffff"))
            self.update_btn_color(self.gsp_bgcolor, data.get("bg_color", "#1f242d"))
            self.gsp_bgop.set_values([float(data.get("bg_opacity", 94.0))])
            self.update_btn_color(self.gsp_bordercol, data.get("border_color", "#62d0ff"))
            self.gsp_borderw.set_values([float(data.get("border_width", 2.5))])
            self.gsp_cr.set_values([float(data.get("corner_radius", 22.0))])
        elif "progress" in kind:
            self.update_btn_color(self.gpb_barcol, data.get("color", "#00e5ff"))
            self.update_btn_color(self.gpb_trackcol, data.get("track_color", "#252b36"))
            self.gpb_height.set_values([float(data.get("height", 14.0))])
            self.gpb_cr.set_values([float(data.get("corner_radius", 7.0))])
            self.gpb_dir.setCurrentText(data.get("direction", "Left to Right"))
        elif "badge" in kind or "callout" in kind:
            if self.gbd_text.text() != data.get("text", ""):
                self.gbd_text.blockSignals(True)
                self.gbd_text.setText(str(data.get("text", "")))
                self.gbd_text.blockSignals(False)
            self.update_btn_color(self.gbd_bgcolor, data.get("bg_color", "#d9ff43"))
            self.update_btn_color(self.gbd_tcolor, data.get("color", "#11130d"))
            self.gbd_fsize.set_values([float(data.get("font_size", 48.0))])
            self.gbd_cr.set_values([float(data.get("corner_radius", 24.0))])
            self.gbd_pulse.setChecked(bool(data.get("pulse", True)))

        px = (item.transform.x - 0.5) * p_settings.width
        py = (item.transform.y - 0.5) * p_settings.height
        self.gtr_x.set_values([px])
        self.gtr_y.set_values([py])
        self.gtr_scale.set_values([item.transform.scale])
        self.gtr_scale_y.set_values([item.transform.effective_scale_y])
        self.gtr_rot.set_values([item.transform.rotation])
        self.gtr_opacity.set_values([item.opacity])
        self.gtr_fadein.set_values([item.fade_in])
        self.gtr_fadeout.set_values([item.fade_out])

        self.updating = False

    def select_transition(self, transition_id: str):
        if hasattr(self.window, "flush_text_edit"):
            self.window.flush_text_edit()
        self.transition_id = transition_id
        if not transition_id:
            self.filename.setText("No clip selected")
            return
        self.item_id = ""
        self.caption_id = ""
        trans = self.window.project.transition_by_id(transition_id) if getattr(self.window, "project", None) else None
        if not trans:
            self.filename.setText("No clip selected")
            return
        self.updating = True
        self.filename.setText(f"Transition — {trans.name}")
        self.video_stack.setCurrentIndex(4)
        for index in range(4):
            self.tabs.setTabEnabled(index, index == 0)
        self.tabs.setCurrentIndex(0)
        self.updating = False
        self.refresh_transition(trans)

    def build_transition(self):
        panel = QWidget()
        root = QVBoxLayout(panel)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Header card
        header_card = QWidget()
        hc_layout = QHBoxLayout(header_card)
        hc_layout.setContentsMargins(4, 4, 4, 4)
        hc_layout.setSpacing(8)
        self.trans_icon_lbl = QLabel()
        self.trans_icon_lbl.setFixedSize(28, 28)
        hc_layout.addWidget(self.trans_icon_lbl)

        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(2)
        self.trans_name_lbl = QLabel("Cross Dissolve")
        set_ui_style(self.trans_name_lbl, 'font-weight:bold; font-size:13px; color:@info;')
        self.trans_category_badge = QLabel("Dissolve")
        set_ui_style(self.trans_category_badge, 'color:@text_sub; font-size:11px;')
        info_col.addWidget(self.trans_name_lbl)
        info_col.addWidget(self.trans_category_badge)
        hc_layout.addLayout(info_col, 1)
        root.addWidget(header_card)

        # Section: Timing
        timing_body = QWidget()
        tf = QFormLayout(timing_body)
        tf.setContentsMargins(4, 4, 4, 8)
        tf.setHorizontalSpacing(8)
        tf.setVerticalSpacing(7)

        self.trans_duration = ValueRow(0.05, 10.0, 0.80, 0.05, True)
        self.trans_duration.spin.setSuffix(" s")
        self.trans_duration.edited.connect(self._on_trans_duration_edited)
        tf.addRow("Duration", self.trans_duration)

        self.trans_alignment = SafeComboBox()
        self.trans_alignment.addItems(["Center on Cut", "Start on Cut", "End on Cut"])
        self.trans_alignment.currentTextChanged.connect(self._on_trans_alignment_changed)
        tf.addRow("Alignment", self.trans_alignment)

        self.trans_easing = SafeComboBox()
        self.trans_easing.addItems(["Ease In-Out", "Linear", "Ease In", "Ease Out", "Smooth S-Curve"])
        self.trans_easing.currentTextChanged.connect(self._on_trans_easing_changed)
        tf.addRow("Easing", self.trans_easing)

        self.sec_trans_timing = InspectorSection("Timing", timing_body, reset_callback=self.reset_trans_timing)
        root.addWidget(self.sec_trans_timing)

        # Section: Transition Parameters
        param_body = QWidget()
        pf = QFormLayout(param_body)
        pf.setContentsMargins(4, 4, 4, 8)
        pf.setHorizontalSpacing(8)
        pf.setVerticalSpacing(7)
        self.tf_trans_param = pf

        self.trans_color_btn = QPushButton()
        self.trans_color_btn.setFixedSize(50, 24)
        self.trans_color_btn.setCursor(Qt.PointingHandCursor)
        self.trans_color_btn.clicked.connect(self.pick_trans_color)
        pf.addRow("Flash Color", self.trans_color_btn)

        self.trans_intensity = ValueRow(0.1, 3.0, 1.0, 0.05, True)
        self.trans_intensity.edited.connect(lambda v, d: self.edit_trans_prop("intensity", v))
        pf.addRow("Intensity", self.trans_intensity)

        self.trans_blur = ValueRow(1, 100, 24, 1, True)
        self.trans_blur.spin.setSuffix(" px")
        self.trans_blur.edited.connect(lambda v, d: self.edit_trans_prop("blur_radius", v))
        pf.addRow("Blur Radius", self.trans_blur)

        self.trans_feather = ValueRow(0, 50, 10, 1, True)
        self.trans_feather.spin.setSuffix(" px")
        self.trans_feather.edited.connect(lambda v, d: self.edit_trans_prop("feather", v))
        pf.addRow("Feather", self.trans_feather)

        self.trans_direction = SafeComboBox()
        self.trans_direction.addItems(["Left", "Right", "Up", "Down", "Horizontal", "Vertical", "Both"])
        self.trans_direction.currentTextChanged.connect(lambda v: self.edit_trans_prop("direction", v))
        pf.addRow("Direction", self.trans_direction)

        self.trans_motion_blur = QCheckBox("Enable Motion Blur")
        self.trans_motion_blur.toggled.connect(lambda v: self.edit_trans_prop("motion_blur", v))
        pf.addRow("", self.trans_motion_blur)

        self.trans_zoom_scale = ValueRow(1.1, 5.0, 2.5, 0.1, True)
        self.trans_zoom_scale.edited.connect(lambda v, d: self.edit_trans_prop("zoom_scale", v))
        pf.addRow("Zoom Scale", self.trans_zoom_scale)

        self.trans_glitch_strength = ValueRow(0.1, 2.0, 0.8, 0.05, True)
        self.trans_glitch_strength.edited.connect(lambda v, d: self.edit_trans_prop("glitch_strength", v))
        pf.addRow("Glitch Strength", self.trans_glitch_strength)

        self.trans_rgb_offset = ValueRow(1, 60, 16, 1, True)
        self.trans_rgb_offset.spin.setSuffix(" px")
        self.trans_rgb_offset.edited.connect(lambda v, d: self.edit_trans_prop("offset_px", v))
        pf.addRow("RGB Offset", self.trans_rgb_offset)

        self.sec_trans_param = InspectorSection("Parameters", param_body, reset_callback=self.reset_trans_properties)
        root.addWidget(self.sec_trans_param)

        # Actions
        actions_box = QWidget()
        act_layout = QHBoxLayout(actions_box)
        act_layout.setContentsMargins(4, 12, 4, 4)
        act_layout.setSpacing(10)

        reset_btn = QPushButton("Reset Defaults")
        reset_btn.setIcon(lucide_icon("rotate-ccw", "#96989f", 14))
        reset_btn.clicked.connect(self.reset_trans_properties)
        act_layout.addWidget(reset_btn)

        del_btn = QPushButton("Delete Transition")
        del_btn.setIcon(lucide_icon("trash-2", "#ff6b6b", 14))
        set_ui_style(del_btn, 'QPushButton:hover {color:@danger; border-color:@accent;}')
        del_btn.clicked.connect(self.delete_current_transition)
        act_layout.addWidget(del_btn)

        root.addWidget(actions_box)
        root.addStretch()
        return panel

    def refresh_transition(self, trans: Transition):
        if not trans: return
        self.updating = True
        self.trans_name_lbl.setText(trans.name)
        self.trans_category_badge.setText(trans.category or "Transition")
        icon_name = TRANSITION_ICONS.get(trans.name, "droplet")
        set_ui_icon(self.trans_icon_lbl, icon_name, "#5ec2f8", 24)

        self.trans_duration.set_values([trans.duration])
        align_map = {"center": "Center on Cut", "start": "Start on Cut", "end": "End on Cut"}
        self.trans_alignment.setCurrentText(align_map.get(trans.alignment, "Center on Cut"))

        props = trans.properties or {}
        self.trans_easing.setCurrentText(props.get("easing", "Ease In-Out"))

        name = trans.name
        has_color = "Color" in name or "Flash" in name or "Black" in name
        has_blur = "Blur" in name
        has_feather = "Wipe" in name
        has_dir = "Wipe" in name or "Push" in name or "Slide" in name or "Whip" in name
        has_motion = "Push" in name or "Whoosh" in name or "Slide" in name
        has_zoom = "Zoom" in name or "Whoosh" in name
        has_glitch = "Glitch" in name
        has_rgb = "RGB" in name
        has_intensity = "Flash" in name or "Color" in name or "Black" in name or "Flare" in name

        self.tf_trans_param.setRowVisible(self.trans_color_btn, has_color)
        if has_color:
            col = props.get("color", "#000000" if "Black" in name else "#ffffff")
            self.update_btn_color(self.trans_color_btn, col)

        self.tf_trans_param.setRowVisible(self.trans_intensity, has_intensity)
        if has_intensity:
            self.trans_intensity.set_values([float(props.get("intensity", 1.0))])

        self.tf_trans_param.setRowVisible(self.trans_blur, has_blur)
        if has_blur:
            self.trans_blur.set_values([float(props.get("blur_radius", 24))])

        self.tf_trans_param.setRowVisible(self.trans_feather, has_feather)
        if has_feather:
            self.trans_feather.set_values([float(props.get("feather", 10))])

        self.tf_trans_param.setRowVisible(self.trans_direction, has_dir)
        if has_dir:
            self.trans_direction.setCurrentText(props.get("direction", "Left"))

        self.tf_trans_param.setRowVisible(self.trans_motion_blur, has_motion)
        if has_motion:
            self.trans_motion_blur.setChecked(bool(props.get("motion_blur", True)))

        self.tf_trans_param.setRowVisible(self.trans_zoom_scale, has_zoom)
        if has_zoom:
            self.trans_zoom_scale.set_values([float(props.get("zoom_scale", 2.5))])

        self.tf_trans_param.setRowVisible(self.trans_glitch_strength, has_glitch)
        if has_glitch:
            self.trans_glitch_strength.set_values([float(props.get("glitch_strength", 0.8))])

        self.tf_trans_param.setRowVisible(self.trans_rgb_offset, has_rgb)
        if has_rgb:
            self.trans_rgb_offset.set_values([float(props.get("offset_px", 16))])

        any_params = any([has_color, has_intensity, has_blur, has_feather, has_dir, has_motion, has_zoom, has_glitch, has_rgb])
        self.sec_trans_param.setVisible(any_params)

        self.updating = False

    @edit_only
    def _on_trans_duration_edited(self, value, delta):
        if self.updating or not self.transition_id: return
        trans = self.window.project.transition_by_id(self.transition_id) if getattr(self.window, "project", None) else None
        if not trans: return
        new_dur = max(0.05, min(10.0, float(value)))
        if trans.alignment == "center":
            cut = trans.start + trans.duration / 2.0
            trans.start = max(0.0, cut - new_dur / 2.0)
        elif trans.alignment == "end":
            cut = trans.start + trans.duration
            trans.start = max(0.0, cut - new_dur)
        trans.duration = new_dur
        self.changed.emit()
        if getattr(self.window, "timeline", None):
            self.window.timeline.viewport().update()
        if getattr(self.window, "preview", None):
            self.window.preview.update()

    @edit_only
    def _on_trans_alignment_changed(self, text):
        if self.updating or not self.transition_id: return
        trans = self.window.project.transition_by_id(self.transition_id) if getattr(self.window, "project", None) else None
        if not trans: return
        mapping = {"Center on Cut": "center", "Start on Cut": "start", "End on Cut": "end"}
        new_align = mapping.get(text, "center")
        if trans.alignment == new_align: return
        if trans.alignment == "center":
            cut = trans.start + trans.duration / 2.0
        elif trans.alignment == "start":
            cut = trans.start
        else:
            cut = trans.start + trans.duration
        trans.alignment = new_align
        if new_align == "center":
            trans.start = max(0.0, cut - trans.duration / 2.0)
        elif new_align == "start":
            trans.start = cut
        else:
            trans.start = max(0.0, cut - trans.duration)
        self.changed.emit()
        if getattr(self.window, "timeline", None):
            self.window.timeline.viewport().update()
        if getattr(self.window, "preview", None):
            self.window.preview.update()

    @edit_only
    def _on_trans_easing_changed(self, text):
        if self.updating or not self.transition_id: return
        trans = self.window.project.transition_by_id(self.transition_id) if getattr(self.window, "project", None) else None
        if not trans: return
        if trans.properties is None: trans.properties = {}
        trans.properties["easing"] = text
        self.changed.emit()
        if getattr(self.window, "preview", None):
            self.window.preview.update()

    @edit_only
    def edit_trans_prop(self, key, value):
        if self.updating or not self.transition_id: return
        trans = self.window.project.transition_by_id(self.transition_id) if getattr(self.window, "project", None) else None
        if not trans: return
        if trans.properties is None: trans.properties = {}
        trans.properties[key] = value
        self.changed.emit()
        if getattr(self.window, "preview", None):
            self.window.preview.update()

    @edit_only
    def pick_trans_color(self):
        if not self.transition_id: return
        trans = self.window.project.transition_by_id(self.transition_id) if getattr(self.window, "project", None) else None
        if not trans: return
        current = (trans.properties or {}).get("color", "#ffffff")
        color = QColorDialog.getColor(QColor(current), self.window, "Select Transition Color", QColorDialog.DontUseNativeDialog)
        if color.isValid():
            if trans.properties is None: trans.properties = {}
            trans.properties["color"] = color.name()
            self.update_btn_color(self.trans_color_btn, color.name())
            self.changed.emit()
            if getattr(self.window, "preview", None):
                self.window.preview.update()

    @edit_only
    def reset_trans_timing(self):
        if not self.transition_id: return
        trans = self.window.project.transition_by_id(self.transition_id) if getattr(self.window, "project", None) else None
        if not trans: return
        new_dur = 0.80
        if trans.alignment == "center":
            cut = trans.start + trans.duration / 2.0
            trans.start = max(0.0, cut - new_dur / 2.0)
        elif trans.alignment == "end":
            cut = trans.start + trans.duration
            trans.start = max(0.0, cut - new_dur)
        trans.duration = new_dur
        if trans.properties:
            trans.properties["easing"] = "Ease In-Out"
        self.changed.emit()
        self.refresh_transition(trans)
        if getattr(self.window, "timeline", None):
            self.window.timeline.viewport().update()
        if getattr(self.window, "preview", None):
            self.window.preview.update()

    @edit_only
    def reset_trans_properties(self):
        if not self.transition_id: return
        trans = self.window.project.transition_by_id(self.transition_id) if getattr(self.window, "project", None) else None
        if not trans: return
        from .transitions import default_transition_properties
        trans.properties = default_transition_properties(trans.name)
        self.changed.emit()
        self.refresh_transition(trans)
        if getattr(self.window, "preview", None):
            self.window.preview.update()

    @edit_only
    def delete_current_transition(self):
        if not self.transition_id: return
        tid = self.transition_id
        self.transition_id = ""
        self.window.project.remove_transition(tid)
        self.select_transition("")
        if getattr(self.window, "timeline", None):
            self.window.timeline.selected_transition_id = ""
            self.window.timeline.viewport().update()
        if getattr(self.window, "preview", None):
            self.window.preview.update()
        self.changed.emit()
