"""Transactional source-region tracking and correction authoring."""
import copy, math, threading
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QWidget,QPushButton,QCheckBox,QProgressBar,QTableWidget,QTableWidgetItem,
    QHeaderView,QMessageBox,QFileDialog)
from .controls import SafeDoubleSpinBox,SafeComboBox,SafeSlider
from .model import Crop
from .theme_widgets import set_ui_style


class RegionView(QWidget):
    regionChanged=Signal(object)
    def __init__(self,parent=None):
        super().__init__(parent); self.image=QImage(); self.region=None; self.crop=Crop()
        self.drag_start=None; self.setMinimumSize(320,220); self.setMouseTracking(True)
    def image_rect(self):
        if self.image.isNull():return QRectF()
        size=self.image.size().scaled(self.size(),Qt.KeepAspectRatio)
        return QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
    def position(self,point):
        r=self.image_rect()
        return QPointF(max(0,min(1,(point.x()-r.x())/max(1,r.width()))),max(0,min(1,(point.y()-r.y())/max(1,r.height()))))
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton and self.image_rect().contains(event.position()):
            self.drag_start=self.position(event.position()); event.accept()
    def mouseMoveEvent(self,event):
        if self.drag_start is None:return
        p=self.position(event.position()); a=self.drag_start
        self.region=[min(p.x(),a.x()),min(p.y(),a.y()),abs(p.x()-a.x()),abs(p.y()-a.y())]; self.update()
    def mouseReleaseEvent(self,event):
        if self.drag_start is None:return
        self.mouseMoveEvent(event); self.drag_start=None
        if self.region and min(self.region[2:])>=.01:self.regionChanged.emit(list(self.region))
        else:self.region=None
        self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.fillRect(self.rect(),QColor('#14171a')); r=self.image_rect()
        if not self.image.isNull():
            p.setRenderHint(QPainter.SmoothPixmapTransform); p.drawImage(r,self.image)
            if self.crop!=Crop():
                c=self.crop.clamped(); p.setPen(QPen(QColor('#8bc9ff'),1,Qt.DashLine))
                p.drawRect(QRectF(r.x()+c.x*r.width(),r.y()+c.y*r.height(),c.width*r.width(),c.height*r.height()))
            if self.region:
                x,y,w,h=self.region; p.setPen(QPen(QColor('#46e0ad'),2))
                p.drawRect(QRectF(r.x()+x*r.width(),r.y()+y*r.height(),w*r.width(),h*r.height()))
        p.end()


class TrackingDialog(QDialog):
    def __init__(self,window,media,item,existing=None):
        super().__init__(window)
        from .tracking_effect import default_effect,MODES,valid
        self.window_=window; self.media=copy.deepcopy(media); self.item=copy.deepcopy(item)
        self.effect=copy.deepcopy(existing) if existing else default_effect()
        self.anchors=copy.deepcopy(self.effect.get('anchors',self.effect.get('analysis',{}).get('anchors',[]))); self.cancel=threading.Event()
        self._closed=False; self._busy=False; self._decoding=False; self.raw=QImage(); self._shown_time=None
        self.dirty_track=not valid(self.effect,self.media,self.item); self.fps=max(1,window.project.settings.fps)
        self.setWindowTitle('Object Tracking · '+media.name); self.resize(980,750)
        self.setWindowModality(Qt.WindowModal); root=QVBoxLayout(self)
        hint=QLabel('Draw a tight box around the object in the full source. Track the clip, scrub to review it, and add correction points where needed. The blue guide shows the clip crop.')
        hint.setWordWrap(True); root.addWidget(hint)
        self.view=RegionView(self); self.view.crop=copy.deepcopy(item.crop); root.addWidget(self.view,1)
        self.view.regionChanged.connect(self.region_changed)
        transport=QHBoxLayout(); self.timeline=SafeSlider(Qt.Horizontal,self)
        self.timeline.setRange(0,max(1,math.ceil(item.duration*self.fps)-1)); transport.addWidget(self.timeline,1)
        self.time_label=QLabel(); transport.addWidget(self.time_label); root.addLayout(transport)
        self.before=QCheckBox('Show original'); self.before.setChecked(True)
        self.before.toggled.connect(self.refresh_preview); transport.addWidget(self.before)
        self._decode_timer=QTimer(self); self._decode_timer.setSingleShot(True); self._decode_timer.timeout.connect(self.request_frame)
        self.timeline.valueChanged.connect(self.seek)
        forms=QHBoxLayout(); a=QFormLayout(); b=QFormLayout(); forms.addLayout(a,1); forms.addLayout(b,1); root.addLayout(forms)
        self.mode=SafeComboBox(self); self.mode.addItems(MODES); self.mode.setCurrentText(self.effect.get('mode','Censor Bar')); self.mode.currentTextChanged.connect(self.mode_changed); a.addRow('Tracking mode',self.mode)
        self.image_form=a
        self.image_button=QPushButton('Choose image…',self); self.image_button.clicked.connect(self.choose_image); a.addRow('Image marker',self.image_button); a.setRowVisible(self.image_button,self.mode.currentText()=='Image')
        self.sample_fps=SafeDoubleSpinBox(self); self.sample_fps.setRange(1,60); self.sample_fps.setDecimals(0); self.sample_fps.setValue(self.effect.get('sample_fps',15)); a.addRow('Analysis frames / second',self.sample_fps)
        self.search_radius=SafeDoubleSpinBox(self); self.search_radius.setRange(.03,.5); self.search_radius.setDecimals(2); self.search_radius.setValue(self.effect.get('search_radius',.22)); b.addRow('Movement search range',self.search_radius)
        self.confidence_threshold=SafeDoubleSpinBox(self); self.confidence_threshold.setRange(.2,.95); self.confidence_threshold.setDecimals(2); self.confidence_threshold.setValue(self.effect.get('confidence_threshold',.58)); b.addRow('Minimum confidence',self.confidence_threshold)
        for spin in (self.sample_fps,self.search_radius,self.confidence_threshold):spin.valueChanged.connect(self.analysis_setting_changed)
        actions=QHBoxLayout(); self.track_button=QPushButton('Track clip',self); self.track_button.clicked.connect(self.track); actions.addWidget(self.track_button)
        self.anchor_button=QPushButton('Add correction here',self); self.anchor_button.clicked.connect(self.add_anchor); actions.addWidget(self.anchor_button)
        self.clear_button=QPushButton('Clear corrections',self); self.clear_button.clicked.connect(self.clear_anchors); actions.addWidget(self.clear_button)
        self.cancel_tracking=QPushButton('Cancel tracking',self); self.cancel_tracking.clicked.connect(self.cancel.set); actions.addWidget(self.cancel_tracking); root.addLayout(actions)
        self.anchor_list=QTableWidget(0,2,self); self.anchor_list.setHorizontalHeaderLabels(['Source time','Region']); self.anchor_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch); self.anchor_list.setMaximumHeight(90); self.anchor_list.cellClicked.connect(self.seek_anchor); root.addWidget(self.anchor_list)
        self.progress_bar=QProgressBar(self); self.progress_bar.setRange(0,100); root.addWidget(self.progress_bar)
        self.info=QLabel('Choose a reference frame and draw a box to start.'); self.info.setWordWrap(True); root.addWidget(self.info)
        self.loss_review=QCheckBox('I reviewed the frames where tracking was lost',self); self.loss_review.setChecked(self.effect.get('loss_reviewed',False)); self.loss_review.toggled.connect(self.review_changed); root.addWidget(self.loss_review)
        footer=QHBoxLayout(); footer.addStretch(); self.cancel_button=QPushButton('Cancel',self); self.cancel_button.clicked.connect(self.reject); footer.addWidget(self.cancel_button)
        self.apply_button=QPushButton('Apply',self); self.apply_button.clicked.connect(self.accept); footer.addWidget(self.apply_button); root.addLayout(footer)
        self.refresh_anchors(); self.set_busy(False)
        if not self.dirty_track:self.show_ready()
        start=max(0,min(item.duration,(window.project.playhead-item.start)))
        self.timeline.setValue(round(start*self.fps)); self.seek(self.timeline.value())
    def source_time(self):return self.item.in_point+self.timeline.value()/self.fps*self.item.speed
    def settled_frame(self):return not self._decoding and self._shown_time is not None and abs(self._shown_time-self.source_time())<1e-6
    def seek(self,index):
        self.time_label.setText(f'Clip {index/self.fps:.3f}s · Source {self.source_time():.3f}s')
        self.track_button.setEnabled(False); self.anchor_button.setEnabled(False)
        self.view.setEnabled(False)
        self._decode_timer.start(80)
    def request_frame(self):
        if self._closed or self._decoding:return
        from .ui import Worker
        from .custom_face_dialog import _decode_frame
        requested=self.source_time(); self._decoding=True
        worker=Worker(lambda:_decode_frame(self.media.path,self.media.kind,requested,self.window_.settings.get('ffmpeg','ffmpeg')))
        def done(image):
            self._decoding=False
            if self._closed:return
            if abs(requested-self.source_time())>1e-6:self.request_frame(); return
            self.raw=image; self._shown_time=requested
            if not self.dirty_track:
                from .object_tracking import sample
                point=sample(self.effect.get('analysis',{}),requested)
                if point and point.get('box'):self.view.region=list(point['box'])
            self.refresh_preview(); self.set_busy(self._busy)
        def failed(detail):
            self._decoding=False
            if not self._closed:self.info.setText('Could not read this frame. '+detail[-250:])
        worker.signals.result.connect(done); worker.signals.error.connect(failed); self.window_.start_worker(worker)
    def refresh_preview(self,*_):
        if self.raw.isNull():return
        image=self.raw
        self.view.crop=copy.deepcopy(self.item.crop)
        if not self.before.isChecked() and not self.dirty_track:
            from .tracking_effect import apply,effective_crop
            if self.effect.get('mode')=='Follow Crop':
                tracked=copy.deepcopy(self.item); tracked.effects=[self.effect]
                self.view.crop=effective_crop(tracked,self.media,self._shown_time)
            item=copy.deepcopy(self.item); item.crop=Crop(); item.effects=[self.effect]
            image=apply(image,item,self.media,self._shown_time)
        self.view.image=image; self.view.update()
    def region_changed(self,region):
        self.dirty_track=True; self.effect['loss_reviewed']=False; self.loss_review.setChecked(False)
        self.info.setText('Region selected. Track clip, or add this as a correction and track again.'); self.set_busy(self._busy)
    def mode_changed(self,mode):
        from .tracking_effect import default_effect
        self.effect['mode']=mode; self.effect['loss_policy']=default_effect(mode)['loss_policy']
        self.image_form.setRowVisible(self.image_button,mode=='Image')
        self.effect['loss_reviewed']=False; self.loss_review.setChecked(False); self.refresh_preview()
        if not self.dirty_track:self.show_ready()
    def choose_image(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose tracked image','','Images (*.png *.webp *.jpg *.jpeg *.bmp)')
        if path:self.effect['image']=path; self.image_button.setText(path.split('/')[-1].split('\\')[-1]); self.refresh_preview()
    def review_changed(self,value):self.effect['loss_reviewed']=value
    def show_ready(self):
        from .tracking_effect import CENSOR_MODES
        frames=self.effect.get('analysis',{}).get('frames',[])
        lost=sum(isinstance(f,dict) and f.get('status')=='lost' for f in frames)
        self.progress_bar.setValue(100)
        mode=self.effect.get('mode')
        fallback='Censor fallback protects the frame.' if mode in CENSOR_MODES else 'The crop follows the selected loss policy.' if mode=='Follow Crop' else 'The marker follows the selected loss policy.'
        self.info.setText(f'Tracking ready · {len(frames)-lost}/{len(frames)} samples followed the object. '+('Review lost sections or add correction points. '+fallback if lost else 'Scrub to review, then Apply.'))
    def analysis_setting_changed(self,*_):self.dirty_track=True; self.set_busy(self._busy)
    def add_anchor(self):
        if not self.view.region or self.raw.isNull() or not self.settled_frame():return
        t=self.source_time(); self.anchors=[a for a in self.anchors if abs(a['time']-t)>.5/self.fps*self.item.speed]
        self.anchors.append({'time':t,'box':list(self.view.region)}); self.anchors.sort(key=lambda a:a['time'])
        self.dirty_track=True; self.refresh_anchors(); self.set_busy(self._busy)
    def clear_anchors(self):self.anchors=[]; self.dirty_track=True; self.refresh_anchors(); self.set_busy(self._busy)
    def refresh_anchors(self):
        self.anchor_list.setRowCount(len(self.anchors))
        for row,a in enumerate(self.anchors):
            self.anchor_list.setItem(row,0,QTableWidgetItem(f"{a['time']:.3f}s")); self.anchor_list.setItem(row,1,QTableWidgetItem(', '.join(f'{v:.3f}' for v in a['box'])))
    def seek_anchor(self,row,column):
        self.timeline.setValue(round((self.anchors[row]['time']-self.item.in_point)/self.item.speed*self.fps))
    def set_busy(self,busy):
        self._busy=busy
        self.track_button.setEnabled(not busy and self.view.region is not None and not self.raw.isNull() and self.settled_frame())
        for control in (self.anchor_button,self.clear_button,self.mode,self.sample_fps,self.search_radius,self.confidence_threshold,self.timeline,self.view):control.setEnabled(not busy)
        self.cancel_tracking.setVisible(busy); self.apply_button.setEnabled(not busy and not self.dirty_track)
        self.anchor_button.setEnabled(not busy and self.settled_frame() and self.view.region is not None)
        self.view.setEnabled(not busy and self.settled_frame())
    def track(self):
        if self._busy or not self.view.region or not self.settled_frame():return
        from .object_tracking import analyze
        from .ui import Worker
        reference=self.source_time(); region=list(self.view.region); anchors=copy.deepcopy(self.anchors)
        options=dict(sample_fps=self.sample_fps.value(),search_radius=self.search_radius.value(),confidence_threshold=self.confidence_threshold.value())
        self.cancel=threading.Event(); self.window_._tracking_cancel=self.cancel; self.set_busy(True); self.progress_bar.setValue(0)
        worker=Worker(lambda:analyze(self.media,self.item,reference,region,anchors,lambda percent,message:worker.signals.progress.emit((percent,message)),self.cancel,**options))
        worker.signals.progress.connect(self.analysis_progress)
        def finish():
            if self.window_._tracking_cancel is self.cancel:self.window_._tracking_cancel=None
            if not self._closed:self.set_busy(False)
        def done(analysis):
            finish()
            if self._closed or self.cancel.is_set():return
            self.effect.update(analysis=analysis,anchors=anchors,**options); self.dirty_track=False; self.progress_bar.setValue(100)
            self.effect['loss_reviewed']=False; self.loss_review.setChecked(False); self.show_ready()
            self.before.setChecked(False); self.refresh_preview(); self.set_busy(False)
        def failed(detail):
            finish()
            if not self._closed:self.info.setText('Tracking cancelled · clip unchanged.' if self.cancel.is_set() else detail[-600:])
        worker.signals.result.connect(done); worker.signals.error.connect(failed); self.window_.start_worker(worker)
    def analysis_progress(self,value):
        if self._closed:return
        if isinstance(value,(tuple,list)):self.progress_bar.setValue(round(value[0])); self.info.setText(str(value[1]))
        else:self.progress_bar.setValue(round(value))
    def result_effect(self):return copy.deepcopy(self.effect)
    def accept(self):
        from .tracking_effect import validate,valid,export_error
        try:
            if self._busy or self.dirty_track or not valid(self.effect,self.media,self.item):raise ValueError('Track this clip before applying the effect.')
            validate(self.effect)
            error=export_error(self.effect,self.media,self.item)
            if error:raise ValueError(error)
        except (ValueError,TypeError) as error:QMessageBox.information(self,'Tracking needs review',str(error)); return
        self._closed=True; self._decode_timer.stop(); super().accept()
    def reject(self):
        self.cancel.set(); self._closed=True; self._decode_timer.stop(); super().reject()
