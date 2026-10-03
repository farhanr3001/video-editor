"""Nested-timeline navigation and asynchronous, revision-safe compound caches."""
import copy,threading
from pathlib import Path
from PySide6.QtWidgets import QWidget,QHBoxLayout,QPushButton,QLabel,QInputDialog,QMessageBox
from .model import Project
from .compounds import create,content,update_asset,cache_path,render_asset,validate

class CompoundController:
    def __init__(self,w):
        self.w=w; self.stack=[]; self.navigating=False; self.pending=set(); self.failed=set(); self.cancellations={}
        w.preview.compound_failures=self.failed
        self.bar=QWidget(); self.layout=QHBoxLayout(self.bar); self.layout.setContentsMargins(4,0,4,0)
        w.timeline.parentWidget().layout().addWidget(self.bar); self.bar.hide()
    def switched(self):
        if not self.navigating:self.stack=[]
        self.refresh_bar(); self.request_caches()
    def synchronize(self):
        child=self.w.project
        for parent,media_id,_,_ in reversed(self.stack):
            media=parent.media_by_id(media_id)
            if media and media.compound!=content(child):update_asset(media,child); parent.touch()
            child=parent
        return child
    def root(self):return self.synchronize()
    def refresh_bar(self):
        while self.layout.count():
            item=self.layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.bar.setVisible(bool(self.stack))
        for index,(parent,_,_,_) in enumerate(self.stack):
            button=QPushButton(parent.name if index else 'Main Timeline'); button.clicked.connect(lambda _,n=index:self.back(n)); self.layout.addWidget(button); self.layout.addWidget(QLabel('›'))
        self.layout.addWidget(QLabel(self.w.project.name)); self.layout.addStretch()
    def new(self,name=None):
        w=self.w
        if w.current_page!=0:return
        w.flush_text_edit(); w.transport.pause()
        if name is None:
            name,ok=QInputDialog.getText(w,'New Compound Clip','Name',text='Compound Clip')
            if not ok:return
        try:asset,clips=create(w.project,w.timeline.selected_ids,w.timeline.selected_caption_ids,name)
        except ValueError as error:QMessageBox.warning(w,'Compound clip',str(error)); return
        w.model_changed(); w.refresh_media(); w.timeline.select_ids({i.id for i in clips},clips[0].id); self.request_caches()
    def open(self,item_id):
        w=self.w; item=w.project.item_by_id(item_id); media=w.project.media_by_id(item.media_id) if item else None
        if w.current_page!=0 or not media or not media.compound:return
        if w.project.track_states.get(item.track,{}).get('locked'):
            QMessageBox.information(w,'Compound clip','Unlock this track before editing its compound.'); return
        try:validate(media.compound,(media.id,))
        except ValueError as error:QMessageBox.warning(w,'Compound clip',str(error)); return
        w.flush_text_edit(); w.transport.pause(); self.stack.append((w.project,media.id,w._history,w._history_index))
        child=Project.from_dict(media.compound); child.playhead=max(0,min(child.duration,item.source_time(w.project.playhead)))
        self.navigating=True
        try:w.set_project(child)
        finally:self.navigating=False
        self.refresh_bar()
    def back(self,index):
        w=self.w
        if w.current_page!=0 or index>=len(self.stack):return
        w.flush_text_edit(); w.transport.pause(); self.synchronize()
        parent,media_id,history,history_index=self.stack[index]; self.stack=self.stack[:index]
        self.navigating=True
        try:w.set_project(parent)
        finally:self.navigating=False
        w._history=history; w._history_index=history_index; w.commit_history()
        self.refresh_bar(); self.request_caches()
    def request_caches(self):
        from .ui import Worker
        w=self.w; project=w.project
        used={i.media_id for i in project.timeline}
        wanted={str(cache_path(m.compound)) for m in project.media if m.compound and m.id in used}
        for target,token in self.cancellations.items():
            if target not in wanted:token.set()
        if self.pending or getattr(w.transport,'closed',False) or getattr(w.preview,'caption_focus',False):return
        for media in project.media:
            if not media.compound or media.id not in used:continue
            from .missing_media import is_missing
            if is_missing(media):continue
            try:target=str(cache_path(media.compound))
            except ValueError:continue
            media.path=target
            w.request_waveform(media)
            if Path(target).is_file():
                if not media.thumbnail or not Path(media.thumbnail).exists():
                    from .media import make_thumbnail
                    thumb=make_thumbnail(target,'video',w.settings.get('ffmpeg','ffmpeg'))
                    if thumb:media.thumbnail=thumb; w.refresh_media()
                continue
            if target in self.pending or target in self.failed:continue
            self.pending.add(target); snapshot=copy.deepcopy(media)
            token=threading.Event(); self.cancellations[target]=token
            worker=Worker(render_asset,snapshot,w.settings.get('ffmpeg','ffmpeg'),cancel=token)
            def ready(path,m=snapshot,p=project):
                current=p.media_by_id(m.id)
                if current and current.compound==m.compound and w.project is p:
                    from .media import make_thumbnail
                    thumb=make_thumbnail(current.path,'video',w.settings.get('ffmpeg','ffmpeg'))
                    if thumb:
                        current.thumbnail=thumb
                        w.timeline.thumbnails.pop(thumb,None)
                        w.timeline._scaled_thumbnails.clear()
                    w.timeline.waveforms.pop(m.id,None); w.request_waveform(current); w.refresh_media(); w.transport.sync(True)
                    w.timeline.viewport().update()
                    w.statusBar().showMessage('Compound preview ready · '+current.name,4000)
            def failed(error,t=target,cancel=token):
                if cancel.is_set():return
                for current in w.project.media:
                    if current.path==t:
                        w.timeline.waveform_pending.discard(current.id); w.timeline.waveform_failures.add(current.id)
                w.timeline.viewport().update()
                self.failed.add(t); w.statusBar().showMessage('Compound preparation failed: '+str(error)[-350:],15000)
            def finished(t=target):
                self.pending.discard(t); self.cancellations.pop(t,None); self.request_caches()
            worker.signals.result.connect(ready); worker.signals.error.connect(failed)
            worker.signals.finished.connect(finished); w.start_worker(worker)
            w.statusBar().showMessage('Preparing lossless compound preview · '+media.name)
            break
    def retry(self):self.failed.clear(); self.request_caches()
    def cancel(self):
        for token in self.cancellations.values():token.set()
