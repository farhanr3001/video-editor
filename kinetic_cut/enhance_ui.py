"""Existing effect-stack controls and cancellable background preparation."""
import copy,threading,time,math
from PySide6.QtCore import QObject,Qt,Slot,QTimer,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QFormLayout,QCheckBox,QPushButton,QLabel,QMessageBox,QDialog,QProgressBar,QHBoxLayout
from .controls import SafeComboBox
from . import enhance


class EnhanceProgress(QDialog):
    canceled=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('AI Enhance');self.setWindowModality(Qt.NonModal)
        self.resize(510,160);self.setMinimumWidth(360);self.percent=0.;self.started=time.monotonic()
        layout=QVBoxLayout(self);self.status=QLabel('Preparing AI Enhance…');self.status.setWordWrap(True);layout.addWidget(self.status)
        note=QLabel('Processes the current trim only. Extended frames stay original until prepared.');note.setWordWrap(True);layout.addWidget(note)
        self.timing=QLabel();layout.addWidget(self.timing);self.bar=QProgressBar();self.bar.setRange(0,100);layout.addWidget(self.bar)
        actions=QHBoxLayout();actions.addStretch();button=QPushButton('Cancel');button.clicked.connect(self.reject);actions.addWidget(button);layout.addLayout(actions)
        self.timer=QTimer(self);self.timer.timeout.connect(self.update_time);self.timer.start(1000);self.update_time()
    def setValue(self,value):self.percent=max(0.,min(100.,float(value)));self.bar.setValue(round(self.percent));self.update_time()
    def setLabelText(self,text):self.status.setText(text)
    def update_time(self):
        elapsed=max(0.,time.monotonic()-self.started)
        remaining=(elapsed*(100-self.percent)/self.percent) if self.percent>0 else None
        estimate='Calculating…' if remaining is None else f'{math.ceil(remaining)}s'
        self.timing.setText(f'Elapsed: {int(elapsed)}s  ·  Estimated remaining: {estimate}')
    def reject(self):self.canceled.emit();super().reject()
    def closeEvent(self,event):self.canceled.emit();self.timer.stop();super().closeEvent(event)


def targets(window):
    from .effects import compatible
    ids=window.timeline.selected_ids or {window.timeline.selected_id}
    return [item for item in window.project.timeline if item.id in ids and compatible(enhance.NAME,item,window.project)]


def confirm_space(window,selected,applying=False):
    import shutil
    from .config import CACHE_DIR
    try:plan=enhance.estimate_space(window.project,selected,applying)
    except (OSError,ValueError,TypeError,AttributeError):
        QMessageBox.warning(window,'AI Enhance','The source media is unavailable or its enhancement settings are invalid. Relink the media or correct the settings before preparing.');return False
    CACHE_DIR.mkdir(parents=True,exist_ok=True);free=shutil.disk_usage(CACHE_DIR).free
    def amount(value):return f'{value/1024**3:.2f} GiB' if value>=1024**3 else f'{value/1024**2:.0f} MiB'
    box=QMessageBox(window);box.setWindowTitle('AI Enhance · Storage');box.setTextFormat(Qt.PlainText)
    enough=plan['peak_bytes']<=free
    box.setIcon(QMessageBox.Question if enough else QMessageBox.Warning)
    box.setText(f'Prepare AI Enhance for {len(selected)} clip'+('?' if len(selected)==1 else 's?') if enough else 'Not enough space for AI Enhance.')
    box.setInformativeText(f"Additional frame cache: up to {amount(plan['cache_bytes'])}\nPeak working space: up to {amount(plan['peak_bytes'])}\nFree on cache drive: {amount(free)}\n\nConservative uncompressed estimates; actual compressed storage varies.\n\nAfter your final render, clear AI Enhance frames in Cache Manager to recover space. Removed effects/clips release unshared frames when Undo history is released or the app closes; other projects' frames are kept.")
    box.setDetailedText('\n'.join(f"{row['name']}: up to {amount(row['cache_bytes'])} cached" for row in plan['details']) or 'Matching enhanced frames are already prepared; no new neural frame cache is needed.')
    box.setStandardButtons(QMessageBox.Ok|QMessageBox.Cancel if enough else QMessageBox.Cancel)
    if enough:box.button(QMessageBox.Ok).setText('Add AI Enhance' if applying else 'Prepare')
    box.setDefaultButton(QMessageBox.Cancel)
    answer=box.exec()
    return enough and answer==QMessageBox.Ok


def apply(window):
    selected=targets(window)
    if not selected:
        window.statusBar().showMessage('Select unlocked video clips to enhance.',5000);return
    if not confirm_space(window,selected,applying=True):return
    from .enhance_component import ready
    if not ready():
        from .component_ui import offer
        if not offer(window,'enhance'):return
        selected=targets(window)
        if not selected:return
    window.flush_text_edit()
    for item in selected:item.effects.append(enhance.default_effect())
    window.model_changed();primary=window.project.item_by_id(window.timeline.selected_id)
    current=primary if primary in selected else selected[0]
    window.inspector.select(current.id);window.inspector.effect_picker.setCurrentIndex(len(current.effects)-1);window.inspector.tabs.setCurrentIndex(2)
    begin(window,selected,storage_confirmed=True)


class Preparation(QObject):
    def __init__(self,window,selected):
        super().__init__(window);self.window=window;self.project=window.project;self.cancel=threading.Event();self.worker=None
        self.snapshot=copy.deepcopy(window.project);self.ids=[i.id for i in selected]
        self.dialog=EnhanceProgress(window)
        self.dialog.canceled.connect(self.cancel.set);self.dialog.destroyed.connect(self.cancel.set)
        self.guard=QTimer(self);self.guard.setInterval(150);self.guard.timeout.connect(self.check_plan)

    def check_plan(self):
        if self.window.transport.closed or self.window.project is not self.project:
            self.cancel.set();return
        for identity in self.ids:
            old=self.snapshot.item_by_id(identity);current=self.project.item_by_id(identity)
            if current is None or [n for n,_ in enhance.active(current)]!=[n for n,_ in enhance.active(old)]:self.cancel.set();return
            media=self.project.media_by_id(current.media_id);before=self.snapshot.media_by_id(old.media_id)
            if media is None or before is None:self.cancel.set();return
            for index,_ in enhance.active(old):
                try:changed=enhance.signature(media,current,index,enhance.sample_fps(self.project,media,current))!=enhance.signature(before,old,index,enhance.sample_fps(self.snapshot,before,old))
                except (OSError,ValueError,TypeError,AttributeError):changed=True
                if changed:self.cancel.set();return

    def start(self):
        from .ui import Worker
        ffmpeg=self.window.settings.get('ffmpeg','ffmpeg')
        def work():
            for n,item_id in enumerate(self.ids):
                if self.cancel.is_set():raise InterruptedError('AI Enhance cancelled')
                item=self.snapshot.item_by_id(item_id)
                enhance.prepare_item(self.snapshot,item,ffmpeg,lambda value:self.worker.signals.progress.emit(((n+value[0]/100)*100/len(self.ids),f'Clip {n+1}/{len(self.ids)} · '+value[1])),self.cancel)
            return len(self.ids)
        self.worker=Worker(work);self.worker.signals.progress.connect(self.progress,Qt.QueuedConnection);self.worker.signals.result.connect(self.done,Qt.QueuedConnection);self.worker.signals.error.connect(self.failed,Qt.QueuedConnection);self.worker.signals.finished.connect(self.retire,Qt.QueuedConnection)
        self.worker.cancel_callback=self.cancel.set;self.guard.start()
        self.dialog.show();self.window.start_worker(self.worker)

    @Slot(object)
    def progress(self,value):
        if not self.cancel.is_set() and not self.window.transport.closed:
            self.dialog.setValue(value[0]);self.dialog.setLabelText(value[1])

    @Slot(object)
    def done(self,result):
        if self.cancel.is_set() or self.window.transport.closed or self.window.project is not self.project:return
        # Cache publication changes no edit values/history. Edits made during the
        # job have a different signature and cannot display this stale result.
        from .enhance_storage import observe
        observe(self.window)
        self.window.preview.composition_cache.clear();self.window.preview.effect_cache.clear();self.window.preview.crop_cache.clear();self.window.preview.update()
        self.window.inspector.enhance_panel.refresh(self.window.inspector.effect())
        remaining=sum(bool(enhance.status(self.project,item)) for item in self.project.timeline if item.id in self.ids)
        self.window.statusBar().showMessage(f'AI Enhance ready for {result-remaining}/{result} clips.'+(' Changed clips need Prepare again.' if remaining else ''),8000)

    @Slot(str)
    def failed(self,error):
        if not self.cancel.is_set() and not self.window.transport.closed:QMessageBox.warning(self.window,'AI Enhance could not finish',error[-1800:]+'\n\nOriginal media and timeline properties are unchanged. The effect remains available to retry or remove.')

    @Slot()
    def retire(self):
        self.guard.stop()
        if self.window._enhance_job is self:self.window._enhance_job=None;self.window._enhance_cancel=None
        if not self.window.transport.closed:self.dialog.close();self.dialog.deleteLater()
        self.worker=None;self.deleteLater()


def begin(window,selected=None,*,storage_confirmed=False):
    if getattr(window,'_enhance_job',None):
        window.statusBar().showMessage('AI Enhance is already preparing clips. Cancel or wait before preparing more.',6000);return
    selected=[i for i in (selected or targets(window)) if enhance.active(i)]
    if not selected:return
    if not storage_confirmed and not confirm_space(window,selected):return
    from .enhance_component import ready
    if not ready():
        from .component_ui import offer
        if not offer(window,'enhance'):return
    job=Preparation(window,selected);window._enhance_job=job;window._enhance_cancel=job.cancel;job.start()


class EnhancePanel(QWidget):
    def __init__(self,inspector):
        super().__init__();self.inspector=inspector;self.rows={};self.updating=False
        from .properties import ValueRow
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);form=QFormLayout();form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow);layout.addLayout(form)
        for key,label in enhance.LABELS.items():
            row=ValueRow(0,100,enhance.DEFAULTS[key],1);form.addRow(label,row);self.rows[key]=row
            row.edited.connect(lambda value,delta,k=key:self.edit(k,value))
        self.face=QCheckBox('Conservative Face Restore');self.face.toggled.connect(lambda value:self.edit('face_restore',value));form.insertRow(6,self.face)
        self.upscale=SafeComboBox();self.upscale.addItems(['Off / 1x','1.5x','2x','4x']);form.addRow('Upscale',self.upscale);self.upscale.currentIndexChanged.connect(lambda index:self.edit('upscale',(1.,1.5,2.,4.)[max(0,index)]))
        for field in (self.face,self.rows['face_restore_strength'],self.rows['temporal_stability'],self.rows['mix'],self.upscale):
            field.hide()
            label=form.labelForField(field)
            if label:label.hide()
        self.quality=SafeComboBox();self.quality.addItems(['Preview','Balanced','High','Maximum']);form.addRow('Quality Mode',self.quality);self.quality.currentTextChanged.connect(lambda value:self.edit('quality_mode',value))
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        hint=QLabel('Temporal restoration runs locally in the background. Only the current source range is processed. Extended portions stay at original quality until prepared. Prepare again after settings, crop or source changes. Transform scaling and placement remain independent. Higher modes may take significantly longer.');hint.setWordWrap(True);layout.addWidget(hint)
        button=QPushButton('Prepare selected clips');button.clicked.connect(lambda:begin(inspector.window));layout.addWidget(button)
        self.difference=QPushButton('View difference…');self.difference.clicked.connect(self.compare);layout.addWidget(self.difference)
        from PySide6.QtWidgets import QHBoxLayout
        actions=QHBoxLayout();layout.addLayout(actions)
        for label,delta in (('Move earlier',-1),('Move later',1),('Duplicate effect',0)):
            action=QPushButton(label);action.clicked.connect(lambda checked=False,d=delta:self.reorder(d));actions.addWidget(action)

    def reorder(self,delta):
        selected=self.inspector.effect_targets()
        if not selected:return
        for item,effect in selected:
            index=next(n for n,value in enumerate(item.effects) if value is effect)
            if delta:
                new=max(0,min(len(item.effects)-1,index+delta));item.effects.insert(new,item.effects.pop(index))
            else:item.effects.insert(index+1,copy.deepcopy(effect))
        self.inspector.changed.emit();self.inspector.select(self.inspector.item_id)

    def edit(self,key,value):
        if self.updating:return
        self.inspector.edit_effect(key,value);self.refresh(self.inspector.effect())

    def compare(self):
        from .enhance_compare import show
        show(self.inspector)

    def refresh(self,effect):
        self.updating=True
        try:
            show=bool(effect and effect.get('name')==enhance.NAME);self.setVisible(show)
            if not show:return
            p=enhance.parameters(effect)
            for key,row in self.rows.items():row.set_values([p[key]])
            self.face.setChecked(p['face_restore']);self.rows['face_restore_strength'].setEnabled(p['face_restore'])
            self.upscale.setCurrentIndex((1.,1.5,2.,4.).index(p['upscale']));self.quality.setCurrentText(p['quality_mode'])
            item=self.inspector.window.project.item_by_id(self.inspector.item_id)
            media=self.inspector.window.project.media_by_id(item.media_id)
            prepared=enhance.range_at(self.inspector.window.project,media,item,self.inspector.effect_picker.currentIndex(),item.source_time(self.inspector.window.project.playhead))
            has_range=bool(enhance.ranges(self.inspector.window.project,media,item,self.inspector.effect_picker.currentIndex()))
            self.difference.setEnabled(has_range);self.difference.setToolTip('Compare the current prepared frame; Space plays the prepared range.' if prepared else 'Prepare the current source range first.')
            self.note.setText(enhance.status(self.inspector.window.project,item) or ('Original footage (zero strength or mix).' if not enhance.active(item) else 'Enhanced frames ready.'))
            self.setEnabled(effect.get('enabled',True))
        finally:self.updating=False
