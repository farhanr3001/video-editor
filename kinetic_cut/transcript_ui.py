"""Shared retained transcript jobs and a small inspector search browser."""
import copy
import threading
import time
from PySide6.QtCore import QObject, Signal, Qt, QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,QLabel,QListWidget,QListWidgetItem,QComboBox
from . import transcripts
from .model import uid


class TranscriptService(QObject):
    changed = Signal()
    def __init__(self, window):
        super().__init__(window if isinstance(window,QObject) else None); self.window=window; self.jobs={}; self.cancels={}

    def start(self, media_ids, force=False):
        w=self.window
        if getattr(w,'_closing',False): raise ValueError('The editor is closing.')
        if any(j['state'] in ('Running','Cancelling') for j in self.jobs.values()):
            raise ValueError('A transcript is already being generated. Cancel it or wait.')
        if not isinstance(media_ids,list) or not 1<=len(media_ids)<=100: raise ValueError('Select 1–100 sources.')
        sources=[copy.deepcopy(w.project.media_by_id(i)) for i in dict.fromkeys(media_ids)]
        if any(not m or not m.has_audio for m in sources): raise ValueError('Choose sources containing audio.')
        from .ui import Worker
        settings=copy.deepcopy(w.settings); cancel=threading.Event()
        job=dict(id=uid(),label='Source transcripts',state='Running',progress=0,media_ids=media_ids,started=time.time(),cancellable=True)
        self.jobs[job['id']]=job; self.cancels[job['id']]=cancel
        def work():
            result=[]
            for n,media in enumerate(sources):
                def progress(value):
                    percent,message=value if isinstance(value,tuple) else (0,str(value))
                    worker.signals.progress.emit(((n+percent/100)/len(sources)*100,media.name+' · '+message))
                data=transcripts.generate(media,settings,cancel,progress,force)
                result.append(dict(media_id=media.id,segments=len(data['segments']),timing=data['timing'],backend=data['backend']))
            return result
        worker=Worker(work); worker.cancel_callback=cancel.set
        def progress(value):
            if job['state']=='Running': job.update(progress=value[0],message=value[1]); self.changed.emit()
        def ready(result):
            job.update(state='Cancelled' if cancel.is_set() else 'Complete',progress=100,result=result)
            self.changed.emit()
        def failed(error):
            job.update(state='Cancelled' if cancel.is_set() else 'Failed',error='' if cancel.is_set() else str(error)[-1500:]); self.changed.emit()
        def finished():
            if job['state'] in ('Running','Cancelling'): failed('Transcript generation did not complete.')
            job.update(cancellable=False,finished=time.time()); self.cancels.pop(job['id'],None); self.changed.emit()
        worker.signals.progress.connect(progress); worker.signals.result.connect(ready)
        worker.signals.error.connect(failed); worker.signals.finished.connect(finished)
        try:w.start_worker(worker)
        except Exception: cancel.set(); failed('Could not start transcription.'); finished(); raise
        if len(self.jobs)>50:
            for key in list(self.jobs):
                if len(self.jobs)<=50:break
                if not self.jobs[key]['cancellable']:self.jobs.pop(key)
        self.changed.emit(); return dict(job)

    def cancel(self, job_id):
        if job_id not in self.cancels or self.jobs[job_id]['state'] not in ('Running','Cancelling'):raise ValueError('This transcript job is not running.')
        self.cancels[job_id].set(); self.jobs[job_id]['state']='Cancelling'; self.changed.emit()
        return dict(self.jobs[job_id])


def service(window):
    if not hasattr(window,'transcript_service'):window.transcript_service=TranscriptService(window)
    return window.transcript_service


class TranscriptPanel(QWidget):
    def __init__(self, inspector):
        super().__init__(inspector); self.inspector=inspector; self.w=inspector.window; self.media_id=''
        root=QVBoxLayout(self); root.setContentsMargins(8,8,8,8)
        self.query=QLineEdit(self); self.query.setPlaceholderText('Search spoken words…'); self.query.setClearButtonEnabled(True); root.addWidget(self.query)
        self.source=QComboBox(self); self.source.setToolTip('Choose any imported audio/video source, including footage not yet on the timeline.'); root.addWidget(self.source)
        self.scope=QComboBox(self); self.scope.addItems(('Selected source','All imported sources')); root.addWidget(self.scope)
        buttons=QHBoxLayout(); self.generate=QPushButton('Generate transcript',self); self.cancel_button=QPushButton('Cancel',self)
        buttons.addWidget(self.generate); buttons.addWidget(self.cancel_button); root.addLayout(buttons)
        self.status=QLabel(self); self.status.setWordWrap(True); root.addWidget(self.status)
        self.rows=QListWidget(self); self.rows.setWordWrap(True); root.addWidget(self.rows,1)
        paging=QHBoxLayout(); self.previous=QPushButton('Previous page',self); self.more=QPushButton('Next page',self); paging.addWidget(self.previous); paging.addWidget(self.more); root.addLayout(paging); self.offset=0
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(180); self.timer.timeout.connect(self.refresh)
        self.query.textChanged.connect(self.search_changed); self.scope.currentIndexChanged.connect(self.search_changed)
        self.source.currentIndexChanged.connect(self.source_changed)
        self.generate.clicked.connect(self.start); self.cancel_button.clicked.connect(self.cancel)
        self.rows.itemClicked.connect(self.activate); self.rows.itemActivated.connect(self.activate)
        self.more.clicked.connect(self.show_more); self.previous.clicked.connect(self.show_previous); service(self.w).changed.connect(self.jobs_changed)
        self._search_busy=False; self._search_serial=0; self._search_pending=False; self._job_states=None

    def jobs_changed(self):
        svc=service(self.w); running=next((j for j in svc.jobs.values() if j['cancellable']),None)
        if running:self.status.setText(f"{running.get('progress',0):.0f}% · {running.get('message','Generating transcript…')}")
        states=tuple((j['id'],j['state']) for j in svc.jobs.values())
        if states!=self._job_states:self._job_states=states; self.timer.start()

    def set_source(self, item):
        sources=[(m.id,m.name) for m in self.w.project.media if m.has_audio]
        changed=getattr(self,'_sources',None)!=(id(self.w.project),sources)
        identifier=item.media_id if item else self.media_id
        if changed:
            self._sources=(id(self.w.project),sources); self.source.blockSignals(True); self.source.clear()
            for mid,name in sources:self.source.addItem(name,mid)
            self.source.blockSignals(False)
        index=self.source.findData(identifier)
        self.source.blockSignals(True); self.source.setCurrentIndex(index if index>=0 else 0); self.source.blockSignals(False)
        identifier=self.source.currentData() or ''
        if changed or identifier!=self.media_id:self.media_id=identifier; self.offset=0; self.refresh()

    def source_changed(self,*_):self.media_id=self.source.currentData() or ''; self.offset=0; self.refresh()

    def search_changed(self,*_):self.offset=0; self.timer.start()
    def show_more(self):self.offset+=200; self.refresh()
    def show_previous(self):self.offset=max(0,self.offset-200); self.refresh()

    def showEvent(self,event):
        super().showEvent(event); self.rows.clear(); self.timer.start()

    def refresh(self):
        if getattr(self.w,'_closing',False):return
        # Merely importing media or changing projects must not schedule hidden
        # inspector searches (or interfere with waveform/background job reuse).
        if not self.isVisible():return
        svc=service(self.w); running=next((j for j in svc.jobs.values() if j['cancellable']),None)
        media=self.w.project.media_by_id(self.media_id)
        self.generate.setEnabled(bool((self.scope.currentIndex() and any(m.has_audio for m in self.w.project.media) or media and media.has_audio) and not running))
        self.cancel_button.setEnabled(bool(running))
        self._search_serial+=1
        if self._search_busy:self._search_pending=True; return
        if not self.w.project.media:self.display(dict(matches=[],total=0,indexed_media_ids=[])); return
        # Disk parsing and searching long source indexes stays off the GUI.
        from .ui import Worker
        snapshot=copy.copy(self.w.project); snapshot.media=copy.deepcopy(snapshot.media); snapshot.timeline=[copy.copy(i) for i in snapshot.timeline]
        settings=copy.deepcopy(self.w.settings); query=self.query.text(); ids=None if self.scope.currentIndex() else [self.media_id]
        serial=self._search_serial; project=self.w.project; self._search_busy=True; self._search_pending=False
        offset=self.offset
        worker=Worker(lambda:transcripts.search(snapshot,settings,query,ids,limit=200,offset=offset)); worker.maintenance=True
        def ready(result):
            if not getattr(self.w,'_closing',False) and serial==self._search_serial and self.w.project is project:self.display(result)
        def failed(error):
            if not getattr(self.w,'_closing',False) and serial==self._search_serial:self.status.setText(str(error)[-500:])
        def finished():
            self._search_busy=False
            if self._search_pending and not getattr(self.w,'_closing',False):self.timer.start()
        worker.signals.result.connect(ready); worker.signals.error.connect(failed); worker.signals.finished.connect(finished); self.w.start_worker(worker)

    def display(self,result):
        svc=service(self.w); running=next((j for j in svc.jobs.values() if j['cancellable']),None)
        # A fixed upper bound keeps long recordings from building thousands of Qt rows.
        self.rows.clear()
        for row in result['matches']:
            seconds=row['start']; label=f"{int(seconds)//60:02d}:{seconds%60:06.3f}  {row['text']}"
            if self.scope.currentIndex():label=row['name']+'\n'+label
            entry=QListWidgetItem(label,self.rows); entry.setData(Qt.UserRole,row)
            entry.setToolTip('Click to seek a matching timeline cut. Unplaced sources open in the source viewer.\nTiming: '+row['timing'])
        self.more.setVisible(self.offset+len(result['matches'])<result['total']); self.previous.setVisible(self.offset>0)
        if running:self.status.setText(f"{running.get('progress',0):.0f}% · {running.get('message','Generating transcript…')}")
        else:
            last=next(reversed(svc.jobs.values()),{}) if svc.jobs else {}
            self.status.setText(last.get('error') or (f"{result['total']} passages · page {self.offset//200+1} · source timestamps" if result['indexed_media_ids'] else 'Generate the selected source transcript first. This does not add captions or change your edit.'))

    def start(self):
        try:service(self.w).start([m.id for m in self.w.project.media if m.has_audio] if self.scope.currentIndex() else [self.media_id])
        except (ValueError,OSError) as error:self.status.setText(str(error))

    def cancel(self):
        svc=service(self.w)
        for key in list(svc.cancels):svc.cancel(key)

    def activate(self, entry):
        row=entry.data(Qt.UserRole); media=self.w.project.media_by_id(row['media_id'])
        if not media:return
        matches=transcripts.occurrences(self.w.project,media.id,row['start'],row['end'])
        if matches:
            primary=self.inspector.item_id
            match=min(matches,key=lambda r:(r['item_id']!=primary,abs(r['start']-self.w.project.playhead)))
            self.w.seek(match['start']); return
        from .pool_tools import SourcePreview
        from PySide6.QtMultimedia import QMediaPlayer
        self.w.transport.pause()
        dialog=SourcePreview(self.inspector,media)
        target=round(row['start']*1000)
        def loaded(state):
            if state==QMediaPlayer.LoadedMedia:dialog.player.setPosition(target)
        dialog.player.mediaStatusChanged.connect(loaded); dialog.show()
        # The source viewer owns loading/seek; keep it alive until closed.
        self._source_dialog=dialog
        dialog.player.setPosition(target)
