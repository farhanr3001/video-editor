"""Inspector controls and guarded Object Tracking commit."""
import copy
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QFormLayout,QLabel,QPushButton,
    QCheckBox,QLineEdit,QColorDialog,QFileDialog)
from PySide6.QtGui import QColor,QFontDatabase
from .controls import SafeComboBox


def begin(window,item_id=None,existing_index=None):
    from .tracking_dialog import TrackingDialog
    from .tracking_effect import valid
    if getattr(window,'_tracking_cancel',None) is not None:
        window.statusBar().showMessage('Object tracking is already running. Finish or cancel it before starting another analysis.',6000); return
    item=window.project.item_by_id(item_id or window.timeline.selected_id)
    if not item or item.track not in window.project.video_tracks or window.project.track_states.get(item.track,{}).get('locked'):return
    media=window.project.media_by_id(item.media_id)
    if not media or media.kind not in ('video','image'):return
    if window.transport.playing:window.transport.pause()
    window.flush_text_edit(); project=window.project; snapshot=copy.deepcopy(item)
    existing=item.effects[existing_index] if existing_index is not None and 0<=existing_index<len(item.effects) else None
    dialog=TrackingDialog(window,media,item,existing)
    if dialog.exec()!=QDialog.Accepted:return
    current=project.item_by_id(item.id)
    if window.transport.closed or window.project is not project or current is not item or current!=snapshot or window.current_page!=0 or project.track_states.get(item.track,{}).get('locked'):
        window.statusBar().showMessage('The clip changed while tracking was open. No changes were applied.',7000); return
    effect=dialog.result_effect()
    if not valid(effect,project.media_by_id(item.media_id),item):
        window.statusBar().showMessage('The source changed. Track the current source before applying.',7000); return
    if existing_index is None:current.effects.append(effect); index=len(current.effects)-1
    else:current.effects[existing_index]=effect; index=existing_index
    window.model_changed(); window.select_item(item.id); window.inspector.tabs.setCurrentIndex(2); window.inspector.effect_picker.setCurrentIndex(index)
    window.statusBar().showMessage('Object Tracking applied · Undo available',5000)


class TrackingPanel(QWidget):
    def __init__(self,inspector):
        super().__init__(inspector); self.inspector=inspector; self.updating=False
        from .properties import ValueRow
        from .tracking_effect import MODES,LOSS_POLICIES
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); form=QFormLayout(); root.addLayout(form)
        self.form=form; self.controls={}
        self.mode=SafeComboBox(self); self.mode.addItems(MODES); self.mode.currentTextChanged.connect(self.change_mode); form.addRow('Tracking mode',self.mode)
        self.track_button=QPushButton('Track / Correct…',self); self.track_button.clicked.connect(self.open_tracker); form.addRow(self.track_button)
        self.notice=QLabel(self); self.notice.setWordWrap(True); form.addRow(self.notice)
        def number(key,label,low,high,default,step=1):
            row=ValueRow(low,high,default,step,True); row.edited.connect(lambda value,delta,k=key:self.change(k,value)); form.addRow(label,row); self.controls[key]=row
        self.follow_scale=QCheckBox('Follow object size',self); self.follow_scale.toggled.connect(lambda value:self.change('follow_scale',value)); form.addRow(self.follow_scale)
        for args in [('width','Width (%)',5,600,100),('height','Height (%)',5,600,100),('padding','Padding (source px)',0,500,12),('offset_x','Offset X (source px)',-2000,2000,0),('offset_y','Offset Y (source px)',-2000,2000,0),('rotation','Rotation (°)',-180,180,0),('opacity','Opacity (%)',0,100,100),('stroke_width','Line width (source px)',1,100,6),('blur','Blur strength',1,150,30),('pixel_size','Pixel size',2,200,18),('arrow_length','Arrow length (source px)',10,1000,120),('arrow_head','Arrow head (source px)',4,200,28),('font_size','Text size (source px)',8,300,48),('label_padding','Text padding (source px)',0,100,12),('radius','Corner radius (source px)',0,200,8)]:number(*args)
        self.colors={}
        for key,title in [('color','Marker colour'),('label_color','Text colour'),('label_background','Text background')]:
            button=QPushButton(self); button.clicked.connect(lambda _,k=key:self.choose_color(k)); form.addRow(title,button); self.colors[key]=button
        self.fill=QCheckBox('Filled shape',self); self.fill.toggled.connect(lambda value:self.change('fill',value)); form.addRow(self.fill)
        self.label=QLineEdit(self); self.label.setMaxLength(256); self.label.editingFinished.connect(lambda:self.change('label',self.label.text())); form.addRow('Label',self.label)
        self.font=SafeComboBox(self); self.font.addItems(QFontDatabase.families()); self.font.currentTextChanged.connect(lambda value:self.change('font',value)); form.addRow('Font',self.font)
        self.image=QPushButton('Choose image…',self); self.image.clicked.connect(self.choose_image); form.addRow('Image / sticker',self.image)
        self.loss_policy=SafeComboBox(self); self.loss_policy.addItems(LOSS_POLICIES); self.loss_policy.currentTextChanged.connect(lambda value:self.change('loss_policy',value)); form.addRow('When tracking is lost',self.loss_policy)
        self.loss_review=QCheckBox('Lost tracking frames reviewed',self); self.loss_review.toggled.connect(lambda value:self.change('loss_reviewed',value)); form.addRow(self.loss_review)
    def effect(self):return self.inspector.effect()
    def change(self,key,value):
        if self.updating or self.inspector.updating:return
        if key=='loss_policy':
            for _,effect in self.inspector.effect_targets():effect.update(loss_policy=value,loss_reviewed=False)
            self.inspector.changed.emit()
        else:self.inspector.edit_effect(key,value)
        if key in ('loss_policy','mode'):self.refresh(self.effect())
    def change_mode(self,mode):
        if self.updating or self.inspector.updating:return
        from .tracking_effect import default_effect
        for _,effect in self.inspector.effect_targets():
            effect.update(mode=mode,loss_policy=default_effect(mode)['loss_policy'],loss_reviewed=False)
        self.inspector.changed.emit(); self.refresh(self.effect())
    def choose_color(self,key):
        effect=self.effect()
        if not effect:return
        color=QColorDialog.getColor(QColor(effect.get(key,'#000000')),self,'Choose colour')
        if color.isValid():self.change(key,color.name()); self.refresh(self.effect())
    def choose_image(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose tracked image','','Images (*.png *.webp *.jpg *.jpeg *.bmp)')
        if path:self.change('image',path); self.refresh(self.effect())
    def open_tracker(self):begin(self.inspector.window,self.inspector.item_id,self.inspector.effect_picker.currentIndex())
    def refresh(self,effect):
        if not effect:return
        from .tracking_effect import status
        self.updating=True
        try:
            mode=effect.get('mode','Censor Bar'); self.mode.setCurrentText(mode); self.follow_scale.setChecked(effect.get('follow_scale',True))
            for key,row in self.controls.items():row.set_values([effect.get(key,row.default)])
            for key,button in self.colors.items():button.setText(effect.get(key,'#000000'))
            self.label.setText(effect.get('label','Tracked object')); self.font.setCurrentText(effect.get('font','Segoe UI')); self.fill.setChecked(effect.get('fill',False))
            self.image.setText(effect.get('image','Choose image…').split('/')[-1].split('\\')[-1]); self.loss_policy.setCurrentText(effect.get('loss_policy','Full frame')); self.loss_review.setChecked(effect.get('loss_reviewed',False))
            item=self.inspector.window.project.item_by_id(self.inspector.item_id); media=self.inspector.window.project.media_by_id(item.media_id)
            self.notice.setText(status(item,media,item.source_time(self.inspector.window.project.playhead)) or 'Tracking ready. Scrub to review; use Track / Correct to refine it.')
            visible={'Blur':{'blur'},'Pixelate':{'pixel_size'},'Arrow':{'arrow_length','arrow_head','stroke_width','color'},'Circle':{'stroke_width','color','fill'},'Rectangle':{'stroke_width','color','fill','radius'},'Label':{'label','font','font_size','label_color','label_background','label_padding','radius'},'Image':{'image'},'Censor Bar':{'color','radius'}}.get(mode,set())
            conditional={'blur','pixel_size','arrow_length','arrow_head','stroke_width','color','fill','radius','label','font','font_size','label_color','label_background','label_padding','image'}
            for key in conditional:
                control=self.controls.get(key) or self.colors.get(key) or getattr(self,key)
                self.form.setRowVisible(control,key in visible)
            follow=mode=='Follow Crop'
            for key in ('padding','rotation','opacity'):
                self.form.setRowVisible(self.controls[key],not follow)
            self.form.setRowVisible(self.follow_scale,not follow)
            for key in ('width','height'):
                label=self.form.labelForField(self.controls[key])
                if label:label.setText(key.title()+(' (% of clip crop)' if follow else ' (%)'))
                self.controls[key].setToolTip('Framing size relative to the clip crop. Smaller values zoom in; position follows the tracked target.' if follow else 'Marker size relative to the tracked region.')
            self.setEnabled(effect.get('enabled',True))
        finally:self.updating=False
