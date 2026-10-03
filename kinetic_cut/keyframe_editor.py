"""Transactional, single-clip keyframe editor. Nothing reaches the edit until Save."""
import copy
from .theme_widgets import ui_color
from PySide6.QtCore import Qt,QPointF,QTimer,Signal,QSignalBlocker
from PySide6.QtGui import QPainter,QColor,QPen,QPolygonF,QKeySequence,QShortcut
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QSplitter,
    QLabel,QPushButton,QComboBox,QCheckBox,QScrollArea,QDialogButtonBox,QMessageBox)
from .controls import SafeDoubleSpinBox
from .widgets import PreviewCanvas
from .model import TimelineItem
from .keyframes import PROPERTIES,MODES,base,value,put,clean


class KeyframeTimeline(QWidget):
    seekRequested=Signal(float)
    propertySelected=Signal(str)
    changed=Signal()
    def __init__(self,dialog):
        super().__init__(dialog); self.dialog=dialog; self.setMinimumHeight(245); self.drag_key=None
        self.setFocusPolicy(Qt.StrongFocus)
    def x(self,time):return 140+max(0,time)/max(.01,self.dialog.item.duration)*max(1,self.width()-153)
    def time(self,x):
        d=self.dialog; return min(d.item.duration,max(0,round((x-140)/max(1,self.width()-153)*d.item.duration*d.project.settings.fps)/d.project.settings.fps))
    def paintEvent(self,event):
        p=QPainter(self); p.fillRect(self.rect(),ui_color('bg_main')); p.setRenderHint(QPainter.Antialiasing)
        d=self.dialog; p.setPen(ui_color('text_sub'))
        for n in range(6):
            t=d.item.duration*n/5; x=self.x(t); p.drawText(QPointF(x-8,17),f'{t:.2f}'); p.drawLine(QPointF(x,22),QPointF(x,self.height()))
        p.fillRect(140,27,max(1,self.width()-153),22,QColor('#41677f')); p.setPen(QColor('white')); p.drawText(146,43,d.media.name)
        for row,(name,(label,*_)) in enumerate(PROPERTIES.items()):
            y=66+row*28
            if name==d.property:p.fillRect(0,y-12,self.width(),26,ui_color('bg_hover'))
            p.setPen(ui_color('text_main')); p.drawText(8,y+4,label)
            p.setPen(ui_color('border_subtle')); p.drawLine(140,y,self.width()-13,y)
            for key in d.item.keyframes.get(name,[]):
                if not -.00001<=key['time']<=d.item.duration+.00001:continue
                x=self.x(key['time']); selected=name==d.property and abs(key['time']-d.position)<.5/d.project.settings.fps
                p.setPen(QPen(QColor('#fff2bc' if selected else '#17191b'),1)); p.setBrush(QColor('#f3c762' if selected else '#86b9d1'))
                p.drawPolygon(QPolygonF([QPointF(x,y-6),QPointF(x+6,y),QPointF(x,y+6),QPointF(x-6,y)]))
        x=self.x(d.position); p.setPen(QPen(QColor('#ed3545'),1)); p.drawLine(QPointF(x,22),QPointF(x,self.height()))
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return
        self.dialog.transport.pause()
        d=self.dialog; row=round((event.position().y()-66)/28); names=list(PROPERTIES)
        if 0<=row<len(names) and event.position().y()>50:
            name=names[row]; self.propertySelected.emit(name)
            if event.position().x()<140:return
            key=next((k for k in d.item.keyframes.get(name,[]) if abs(self.x(k['time'])-event.position().x())<=8),None)
            if key:self.drag_key=(name,key); self.seekRequested.emit(key['time']); return
        self.seekRequested.emit(self.time(event.position().x()))
    def mouseMoveEvent(self,event):
        if not event.buttons()&Qt.LeftButton:return
        t=self.time(event.position().x())
        if self.drag_key:
            name,key=self.drag_key; previous=key['time']; names=['scale','scale_y'] if name in {'scale','scale_y'} and self.dialog.link.isChecked() else [name]
            for n in names:
                keys=self.dialog.item.keyframes.get(n,[]); moving=key if n==name else next((k for k in keys if abs(k['time']-previous)<1e-7),None)
                if moving:
                    keys[:]=[k for k in keys if k is moving or abs(k['time']-t)>1e-7]; moving['time']=t; keys.sort(key=lambda k:k['time'])
            self.changed.emit()
        self.seekRequested.emit(t)
    def mouseReleaseEvent(self,event):self.drag_key=None


class KeyframeEditor(QDialog):
    def __init__(self,owner,item):
        super().__init__(owner); self.owner=owner; self.original=copy.deepcopy(item); self.project=copy.copy(owner.project)
        self.project.settings=copy.deepcopy(owner.project.settings)
        self.item=copy.deepcopy(item); self.item.start=0; self.item.muted=False; self.media=copy.deepcopy(owner.project.media_by_id(item.media_id))
        self.project.timeline=[self.item]; self.project.captions=[]; self.project.media=[self.media]; self.project.playhead=0
        self.project.video_tracks=[item.track]; self.project.audio_tracks=['__source_audio']
        self.project.track_states={item.track:{'visible':True},'__source_audio':{'visible':True}}
        if self.media.has_audio:self.project.timeline.append(TimelineItem('__source_audio',item.media_id,'__source_audio',0,item.duration,item.in_point,speed=item.speed,gain_db=item.gain_db))
        self.settings=owner.settings; self.proxies=owner.proxies; self.position=0.; self.property='scale'; self.updating=False
        self.setWindowTitle('Manage Keyframes · '+self.media.name); self.resize(1100,740); self.setWindowModality(Qt.WindowModal)
        root=QVBoxLayout(self); split=QSplitter(Qt.Horizontal); root.addWidget(split,1)
        left=QWidget(); content=QVBoxLayout(left); self.preview=PreviewCanvas(); self.preview.set_project(self.project); self.preview.set_read_only(True); self.preview.set_transform_controls_visible(False); content.addWidget(self.preview,1)
        controls=QHBoxLayout(); self.play=QPushButton('Play'); self.play.clicked.connect(self.toggle_play); controls.addWidget(self.play)
        self.time=SafeDoubleSpinBox(); self.time.setDecimals(3); self.time.setRange(0,item.duration); self.time.setSingleStep(1/self.project.settings.fps); self.time.setSuffix(' s'); self.time.valueChanged.connect(self.seek); controls.addWidget(self.time)
        for label,direction in [('Previous key',-1),('Next key',1)]:
            b=QPushButton(label); b.clicked.connect(lambda _,n=direction:self.next_key(n)); controls.addWidget(b)
        content.addLayout(controls); self.lanes=KeyframeTimeline(self); content.addWidget(self.lanes); split.addWidget(left)
        right=QWidget(); form=QFormLayout(right); form.addRow(QLabel('Clip transform / keyframe values'))
        hint=QLabel('Choose a property and add a key at this time. Edit its value, move the playhead, then add the next key. Diamonds connect automatically.'); hint.setWordWrap(True); form.addRow(hint)
        self.rows={}
        for name,(label,low,high,step) in PROPERTIES.items():
            row=QWidget(); layout=QHBoxLayout(row); layout.setContentsMargins(0,0,0,0)
            spin=SafeDoubleSpinBox(); spin.setDecimals(3); spin.setRange(low,high); spin.setSingleStep(step); spin.valueChanged.connect(lambda v,n=name:self.edit_value(n,v)); layout.addWidget(spin)
            add=QPushButton('◇'); add.setFixedWidth(28); add.setProperty('compact',True); add.setToolTip('Add/update '+label+' keyframe here'); add.clicked.connect(lambda _,n=name:self.add_key(n)); layout.addWidget(add)
            spin.setObjectName('keyframe_value_'+name); add.setObjectName('keyframe_add_'+name)
            form.addRow(label,row); self.rows[name]=(spin,add)
        self.link=QCheckBox('Link Zoom X / Y'); self.link.setChecked(item.transform.scale_linked); form.addRow(self.link)
        self.time.setObjectName('keyframe_time'); self.link.setObjectName('keyframe_link_zoom')
        self.interpolation=QComboBox(); self.interpolation.addItems(MODES); self.interpolation.currentTextChanged.connect(self.change_mode); form.addRow('To next key',self.interpolation)
        self.interpolation.setObjectName('keyframe_interpolation')
        self.property_label=QLabel(); form.addRow('Selected lane',self.property_label)
        for label,callback in [('Add / Update Keyframe',lambda:self.add_key(self.property)),('Remove Keyframe',self.remove_key),('Remove All Keyframes',self.remove_all)]:
            b=QPushButton(label); b.clicked.connect(callback); form.addRow(b)
        note=QLabel('Values without a key at this time are read-only until you add one. Times are relative to this clip. Cancel discards all changes.'); note.setWordWrap(True); form.addRow(note)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(right); scroll.setMinimumWidth(285); split.addWidget(scroll); split.setSizes([760,300])
        footer=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel); footer.accepted.connect(self.accept); footer.rejected.connect(self.reject); root.addWidget(footer)
        from .transport import TimelineTransport
        self.transport=TimelineTransport(self); self.transport.changed.connect(self.position_changed); self.transport.stateChanged.connect(lambda playing:self.play.setText('Pause' if playing else 'Play'))
        self.lanes.seekRequested.connect(self.seek); self.lanes.propertySelected.connect(self.select_property); self.lanes.changed.connect(self.refresh)
        self.space=QShortcut(QKeySequence(Qt.Key_Space),self); self.space.setContext(Qt.WindowShortcut); self.space.activated.connect(self.toggle_play)
        self.refresh(); QTimer.singleShot(0,lambda:self.seek(0))
    def start_worker(self,worker):self.owner.start_worker(worker)
    def statusBar(self):return self.owner.statusBar()
    def toggle_play(self):self.transport.pause() if self.transport.playing else self.transport.play()
    def seek(self,t):self.transport.seek(t)
    def position_changed(self,t):
        self.position=t; self.project.playhead=t
        with QSignalBlocker(self.time):self.time.setValue(t)
        self.refresh()
    def select_property(self,name):self.property=name; self.refresh()
    def at_key(self,name):return next((k for k in self.item.keyframes.get(name,[]) if abs(k['time']-self.position)<.5/self.project.settings.fps),None)
    def refresh(self):
        self.updating=True
        for name,(spin,add) in self.rows.items():
            spin.setValue(value(self.item.keyframes.get(name,[]),self.position,base(self.item,name))); spin.setReadOnly(self.at_key(name) is None)
            add.setText('◆' if self.at_key(name) else '◇')
        self.property_label.setText(PROPERTIES[self.property][0]); key=self.at_key(self.property); self.interpolation.setEnabled(key is not None)
        self.interpolation.setCurrentText(key.get('interpolation','Linear') if key else 'Linear'); self.updating=False; self.lanes.update(); self.preview.update()
    def add_key(self,name):
        self.transport.pause(); self.property=name
        names=['scale','scale_y'] if name in {'scale','scale_y'} and self.link.isChecked() else [name]
        for n in names:put(self.item,n,self.position,value(self.item.keyframes.get(n,[]),self.position,base(self.item,n)))
        self.refresh()
    def edit_value(self,name,number):
        if self.updating:return
        key=self.at_key(name)
        if not key:return
        key['value']=number; self.property=name
        if name in {'scale','scale_y'} and self.link.isChecked():
            other='scale_y' if name=='scale' else 'scale'; put(self.item,other,self.position,number,key.get('interpolation','Linear'))
        self.refresh()
    def change_mode(self,mode):
        if self.updating:return
        key=self.at_key(self.property)
        if key:key['interpolation']=mode
        if self.property in {'scale','scale_y'} and self.link.isChecked():
            for n in ('scale','scale_y'):
                key=self.at_key(n)
                if key:key['interpolation']=mode
    def next_key(self,direction):
        keys=self.item.keyframes.get(self.property,[]); candidates=[k['time'] for k in keys if (k['time']-self.position)*direction>1e-6 and 0<=k['time']<=self.item.duration]
        if candidates:self.seek(min(candidates) if direction>0 else max(candidates))
    def remove_key(self):
        names=['scale','scale_y'] if self.property in {'scale','scale_y'} and self.link.isChecked() else [self.property]
        for name in names:
            keys=[k for k in self.item.keyframes.get(name,[]) if abs(k['time']-self.position)>=.5/self.project.settings.fps]
            if keys:self.item.keyframes[name]=keys
            else:self.item.keyframes.pop(name,None)
        self.refresh()
    def remove_all(self):self.item.keyframes={}; self.refresh()
    def accept(self):
        current=self.owner.project.item_by_id(self.original.id)
        if current!=self.original or self.owner.current_page!=0 or self.owner.project.track_states.get(self.original.track,{}).get('locked'):
            QMessageBox.warning(self,'Clip changed','The clip changed or its track is locked. Cancel and reopen this editor to avoid overwriting newer edits.'); return
        current.keyframes=clean(self.item.keyframes); current.transform.scale_linked=self.link.isChecked(); self.owner.model_changed(); super().accept()
    def done(self,result):
        self.transport.shutdown(); super().done(result); self.owner.activateWindow(); self.owner.timeline.viewport().setFocus()
