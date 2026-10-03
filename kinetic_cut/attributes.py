"""Selective attribute transfer; timing, content, source media and links stay put."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QGridLayout,QLabel,QCheckBox,QGroupBox,QDialogButtonBox,QScrollArea,QWidget

VIDEO=[("Composition Mode","composite_mode"),("Opacity","opacity"),("Position","position"),("Rotation Angle","rotation"),("Anchor Point","anchor"),("Pitch","pitch"),("Yaw","yaw"),
       ("Scale X","scale_x"),("Scale Y","scale_y"),("Crop Left","crop_left"),("Crop Right","crop_right"),("Crop Top","crop_top"),("Crop Bottom","crop_bottom"),("Crop Softness","crop_softness"),("Retain Image Position","retain_image_position"),("Horizontal Flip","flip_h"),("Vertical Flip","flip_v"),("Plugins / Effects","effects"),("Color Correction","grade")]
AUDIO=[("Volume","gain_db"),("Pan","pan"),("Pitch","audio_pitch"),("Fades","fades"),("Plugins / Effects","effects"),("Mute","muted")]
VIDEO.append(('Keyframe Animation','keyframes'))
TEXT=[("Font","font"),("Font Face","font_face"),("Color","color"),("Size","size"),("Line Spacing","line_spacing"),("Kerning","kerning"),("Alignment","alignment"),("Position","text_position"),("Zoom","text_zoom"),("Opacity","opacity"),("Anchor","text_anchor"),("Stroke","stroke"),("Drop Shadow","shadow"),("Background","background"),("Animation","animation")]


def kind(project,item):
    if hasattr(item,"text") or getattr(item,"role","")=="title":return "text"
    return "audio" if item.track in project.audio_tracks else "video"


def source_for(payload,category):
    if not payload:return None
    candidates=[]
    for item in payload.get("items",[]):
        current="text" if item.get("role")=="title" else payload.get("tracks",{}).get(item.get("track"),{}).get("kind")
        if current==category:candidates.append(item)
    if category=="text":candidates+=payload.get("captions",[])
    source=next((item for item in candidates if item.get("id")==payload.get("primary_id")),next(iter(candidates),None))
    if source:
        source=copy.deepcopy(source); media=next((m for m in payload.get("media",[]) if m.get("id")==source.get("media_id")),{})
        source["_media_size"]=(media.get("width",0),media.get("height",0))
    return source


def apply(project,source,targets,category,selected):
    allowed={key for _,key in {"video":VIDEO,"audio":AUDIO,"text":TEXT}[category]}; selected=set(selected)&allowed
    if not selected:return 0
    targets=[item for item in targets if kind(project,item)==category]
    if any(project.track_states.get(getattr(item,"track","subtitle_1"),{}).get("locked") for item in targets):raise ValueError("Unlock the selected tracks before pasting attributes.")
    for item in targets:
        if category=="text":
            src=source.get("title_style") or source.get("style") or {}
            if hasattr(item,"text"):
                if not item.customize:item.style=copy.deepcopy(project.caption_style(item)); item.customize=True
                dst=item.style
            else:dst=item.title_style
            groups={"text_position":("position_x","position_y"),"text_zoom":("zoom_x","zoom_y","zoom_linked"),"text_anchor":("anchor",),"stroke":("outline","outline_width"),
                    "shadow":("shadow_enabled","shadow_color","shadow_x","shadow_y","shadow_blur","shadow_opacity"),
                    "background":("box_style","background_enabled","background_color","background_outline","background_outline_width","background_radius","background_opacity","background_override","background_width","background_height"),"animation":("animation","highlight")}
            for key in selected:
                for attr in groups.get(key,(key,)):
                    if attr in src:setattr(dst,attr,copy.deepcopy(src[attr]))
        elif category=="audio":
            for key in selected:
                for attr in {"audio_pitch":("pitch_semitones","pitch_cents"),"fades":("fade_in","fade_out")}.get(key,(key,)):
                    if attr in source:setattr(item,attr,copy.deepcopy(source[attr]))
            item.fade_in=min(item.duration,item.fade_in); item.fade_out=min(item.duration,item.fade_out)
        else:
            transform=source.get("transform",{}); crop=source.get("crop",{})
            groups={"position":("x","y"),"rotation":("rotation",),"anchor":("anchor_x","anchor_y"),"pitch":("pitch",),"yaw":("yaw",),"flip_h":("flip_horizontal",),"flip_v":("flip_vertical",)}
            for key in selected:
                if key in groups:
                    for attr in groups[key]:
                        if attr in transform:setattr(item.transform,attr,copy.deepcopy(transform[attr]))
                elif key=="scale_x":
                    if "scale_y" not in selected:item.transform.scale_y=item.transform.effective_scale_y
                    item.transform.scale=transform.get("scale",1)
                elif key=="scale_y":item.transform.scale_y=transform.get("scale_y") if transform.get("scale_y") is not None else transform.get("scale",1)
                elif key=="grade":
                    for attr in ("grayscale","brightness","contrast","saturation","sharpen"):
                        if attr in source:setattr(item,attr,copy.deepcopy(source[attr]))
                elif not key.startswith("crop_") and key in source:setattr(item,key,copy.deepcopy(source[key]))
                elif key=="crop_softness":item.crop_softness=source.get("crop_softness",0)
            if {"scale_x","scale_y"}&selected:item.transform.scale_linked=transform.get("scale_linked",True) if {"scale_x","scale_y"}<=selected else False
            media=project.media_by_id(item.media_id); sw,sh=source.get("_media_size",(0,0)); fx=sw/media.width if sw and media and media.width else 1; fy=sh/media.height if sh and media and media.height else 1
            left=crop.get("x",0)*fx if "crop_left" in selected else item.crop.x
            right=(1-crop.get("x",0)-crop.get("width",1))*fx if "crop_right" in selected else 1-item.crop.x-item.crop.width
            top=crop.get("y",0)*fy if "crop_top" in selected else item.crop.y
            bottom=(1-crop.get("y",0)-crop.get("height",1))*fy if "crop_bottom" in selected else 1-item.crop.y-item.crop.height
            from .model import Crop
            item.crop=Crop(left,top,max(.02,1-left-right),max(.02,1-top-bottom)).clamped()
    project.touch(); return len(targets)


class PasteAttributesDialog(QDialog):
    def __init__(self,source_name,target_name,category,parent=None,selected=()):
        super().__init__(parent); self.setWindowTitle("Paste Attributes"); self.resize(560,520)
        root=QVBoxLayout(self); root.addWidget(QLabel("From   "+source_name)); root.addWidget(QLabel("To       "+target_name))
        self.master=QCheckBox(category.title()+" Attributes"); root.addWidget(self.master)
        area=QScrollArea(); area.setWidgetResizable(True); area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body=QWidget(); sections=QVBoxLayout(body); sections.setContentsMargins(0,0,6,0); sections.setSpacing(4)
        area.setWidget(body); root.addWidget(area,1); self.checks={}; self.section_boxes={}; self.groups=[]
        definitions={
            'video': [('Transform',('position','rotation','anchor','pitch','yaw','scale_x','scale_y','flip_h','flip_v')),
                      ('Crop',('crop_left','crop_right','crop_top','crop_bottom','crop_softness','retain_image_position')),
                      ('Composite',('composite_mode','opacity')),('Colour',('grade',)),
                      ('Effects',('effects',)),('Animation',('keyframes',))],
            'audio': [('Levels',('gain_db','pan','muted')),('Pitch',('audio_pitch',)),('Fades',('fades',)),('Effects',('effects',))],
            'text': [('Typography',('font','font_face','color','size','line_spacing','kerning','alignment')),
                     ('Transform',('text_position','text_zoom','text_anchor','opacity')),
                     ('Appearance',('stroke','shadow','background')),('Animation',('animation',))]}
        labels={key:label for label,key in {'video':VIDEO,'audio':AUDIO,'text':TEXT}[category]}
        for title,keys in definitions[category]:
            box=QGroupBox(title); grid=QGridLayout(box); grid.setContentsMargins(8,8,8,6)
            grid.setHorizontalSpacing(10); grid.setVerticalSpacing(3)
            sections.addWidget(box); self.section_boxes[title]=box
            for n,key in enumerate(keys):
                check=QCheckBox(labels[key]); grid.addWidget(check,n//3,n%3); self.checks[key]=check; check.toggled.connect(self.changed)
        sections.addStretch(); self.master.clicked.connect(self.toggle_all)
        if category=="video":
            shortcut_row={}
            for label,keys,section in (("Zoom",["scale_x","scale_y"],'Transform'),("Crop",["crop_left","crop_right","crop_top","crop_bottom","crop_softness"],'Crop'),("Flip",["flip_h","flip_v"],'Transform')):
                grid=self.section_boxes[section].layout(); check=QCheckBox("All "+label)
                row,column=shortcut_row.setdefault(section,(grid.rowCount(),0))
                check.clicked.connect(lambda checked,k=keys:self.toggle_keys(k,checked)); grid.addWidget(check,row,column)
                shortcut_row[section]=(row,column+1); self.groups.append((check,keys))
        note=QLabel("Only checked properties are copied. Clip timing, text and source media are unchanged."); note.setWordWrap(True); root.addWidget(note)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Apply); self.buttons.rejected.connect(self.reject); self.buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept); root.addWidget(self.buttons)
        self.toggle_keys(set(selected)&self.checks.keys(),True); self.changed()
    def toggle_keys(self,keys,checked):
        for key in keys:self.checks[key].setChecked(checked)
    def toggle_all(self,checked):self.toggle_keys(self.checks,checked)
    def selected(self):return {key for key,check in self.checks.items() if check.isChecked()}
    def changed(self,*_):
        count=len(self.selected()); self.master.blockSignals(True); self.master.setCheckState(Qt.Checked if count==len(self.checks) else Qt.PartiallyChecked if count else Qt.Unchecked); self.master.blockSignals(False)
        for check,keys in getattr(self,"groups",[]):
            active=sum(self.checks[key].isChecked() for key in keys); check.blockSignals(True); check.setCheckState(Qt.Checked if active==len(keys) else Qt.PartiallyChecked if active else Qt.Unchecked); check.blockSignals(False)
        self.buttons.button(QDialogButtonBox.Apply).setEnabled(bool(count)) if hasattr(self,"buttons") else None
