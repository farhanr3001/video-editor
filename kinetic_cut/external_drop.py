"""Non-blocking Explorer drag probing, provisional ghosts, atomic import/insert."""
from pathlib import Path
from PySide6.QtCore import QObject,QMimeData,QUrl
from PySide6.QtWidgets import QMessageBox
from .media import media_kind,probe
from .media_insert import source_key
from .model import MediaItem,uid


def paths_from_mime(mime):
    return list(dict.fromkeys(url.toLocalFile() for url in mime.urls() if url.isLocalFile() and media_kind(url.toLocalFile())!="unknown" and Path(url.toLocalFile()).is_file()))[:1000]


class FileDropController(QObject):
    def __init__(self,window):
        super().__init__(window); self.window=window; self.cache={}; self.pending=set(); self.errors={}; self.waiting=[]
        self.placeholders={}

    def resolved(self,path):
        key=source_key(path)
        return next((m for m in self.window.project.media if not m.timeline_preset and source_key(m.path)==key),None) or self.cache.get(key)

    def assets(self,paths):
        from .ui import Worker
        result=[]
        for path in paths:
            key=source_key(path); asset=self.resolved(path)
            if asset:result.append(asset); continue
            if key not in self.pending and key not in self.errors:
                self.pending.add(key)
                worker=Worker(probe,path,self.window.settings.get("ffprobe","ffprobe"),self.window.settings.get("ffmpeg","ffmpeg"))
                worker.signals.result.connect(lambda media,k=key:self.ready(k,media))
                worker.signals.error.connect(lambda error,k=key:self.failed(k,error)); self.window.start_worker(worker)
            if key not in self.placeholders:
                kind=media_kind(path)
                self.placeholders[key]=MediaItem(uid(),path,kind,Path(path).name+" · reading duration…",5.,1920,1080,60.,kind!="image")
            result.append(self.placeholders[key])
        return result

    def ready(self,key,media):
        self.pending.discard(key); self.cache[key]=media; self.refresh_drag(); self.flush()

    def failed(self,key,error):
        self.pending.discard(key); self.errors[key]=error; self.flush()

    def refresh_drag(self):
        timeline=self.window.timeline
        if not getattr(timeline,"external_drag_paths",None):return
        paths=list(timeline.external_drag_paths); point=timeline.external_drag_point
        mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(path) for path in paths])
        class Event:
            def mimeData(self):return mime
            def position(self):return point
            def acceptProposedAction(self):pass
            def ignore(self):pass
        timeline.preview_incoming(Event())

    def drop(self,paths,track,start):
        self.assets(paths)
        self.waiting.append((self.window.project,list(paths),track,start))
        self.window.statusBar().showMessage("Reading dropped files; placement will complete when durations are ready…")
        self.flush()

    def flush(self):
        waiting=self.waiting; self.waiting=[]
        for project,paths,track,start in waiting:
            if project is not self.window.project:continue
            error=next((self.errors[source_key(path)] for path in paths if source_key(path) in self.errors),None)
            if error:QMessageBox.warning(self.window,"Timeline import","No clips were placed. "+error[-1200:]); continue
            assets=[self.resolved(path) for path in paths]
            if not all(assets):self.waiting.append((project,paths,track,start)); continue
            self.window.insert_media_assets(assets,track,start)
