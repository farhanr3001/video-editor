"""Optional seek proxies and automatic, source-preserving codec compatibility."""
from pathlib import Path
import threading

from PySide6.QtWidgets import QComboBox

from .config import save_settings


class PreviewQuality(QComboBox):
    def __init__(self,w):
        super().__init__(w)
        self.w=w
        self.busy=False
        self.job_kind=''
        self.failed=set()
        self.ready={}              # Optional 960px optimized previews.
        self.compat_ready={}       # Full-size H.264 previews for AV1 sources.
        self.ready_signatures={}
        self.compat_signatures={}
        self.inspected_codecs={}
        self.token=None
        self.extra_ids=set()
        self.addItems(['Preview: Full','Preview: Optimized'])
        self.setCurrentIndex(int(w.settings.get('optimized_preview',False)))
        self.setToolTip('Full uses original frames when the decoder supports them; AV1 uses an automatically prepared full-size H.264 preview.\nOptimized uses 960px, short-GOP previews. Audio and exports always use originals.')
        self.currentIndexChanged.connect(self.changed)

    @staticmethod
    def _signature(media):
        try:
            stat=Path(media.path).stat()
            return media.path,stat.st_size,stat.st_mtime_ns
        except OSError:
            return None

    def _codec(self,media,signature):
        cached=self.inspected_codecs.get(media.id)
        if cached and cached[0]==signature:return cached[1]
        return str(getattr(media,'video_codec','') or '').lower()

    def _ready(self,media,signature,paths,signatures):
        path=paths.get(media.id)
        return path if path and signatures.get(media.id)==signature and Path(path).is_file() else ''

    def needs_compatible(self,media):
        # Called by the timeline's hot playback/scrub path: never stat a file
        # here. Source signatures are checked in request()/apply() instead.
        inspected=self.inspected_codecs.get(media.id)
        codec=inspected[1] if inspected else str(getattr(media,'video_codec','') or '').lower()
        return codec=='av1' and media.id not in self.w.proxies

    def changed(self):
        if not self.currentIndex():self.cancel(optimized_only=True)
        self.failed.clear()
        self.w.settings['optimized_preview']=bool(self.currentIndex())
        save_settings(self.w.settings)
        self.apply()
        self.request()

    def apply(self,force=False):
        w=self.w
        if not hasattr(w,'transport') or (w.transport.playing and not force):return
        wanted={}
        for media in w.project.media:
            if media.kind!='video':continue
            signature=self._signature(media)
            if not signature:continue
            codec=self._codec(media,signature)
            compatible=self._ready(media,signature,self.compat_ready,self.compat_signatures)
            optimized=self._ready(media,signature,self.ready,self.ready_signatures)
            # A prepared optimized H.264 copy remains a temporary AV1 fallback
            # while the full-resolution compatibility copy is being built.
            if self.currentIndex():path=optimized or compatible
            elif codec=='av1':path=compatible or optimized
            else:path=''
            if path:wanted[media.id]=path
        if wanted==w.proxies:return
        saved=dict(w.preview.frames)
        for key in list(w.transport.decoders):
            if key[3]=='video':w.transport.retire_decoder(key)
        w.preview.frames.update(saved)
        w.proxies=wanted
        w.transport.sync(True)

    def request(self):
        if getattr(self.w.preview,'caption_focus',False) or getattr(getattr(self.w,'transport',None),'closed',False):return
        w=self.w
        used={i.media_id for i in w.project.timeline if i.track in w.project.video_tracks}|self.extra_ids
        # A project switch can retire a decoder just as a cached compatibility
        # worker reports success. Reconcile the path on every request so a
        # ready preview cannot remain black until the user toggles quality.
        for media in w.project.media:
            if media.id not in used or media.kind!='video' or media.id in w.proxies:continue
            signature=self._signature(media)
            if signature and self._codec(media,signature)=='av1' and self._ready(media,signature,self.compat_ready,self.compat_signatures):
                self.apply(force=True)
                break
        if self.busy:return
        for media in w.project.media:
            if media.id not in used or media.kind!='video' or media.compound:continue
            signature=self._signature(media)
            if not signature:continue
            codec=self._codec(media,signature)
            inspected=self.inspected_codecs.get(media.id)
            if not codec and not (inspected and inspected[0]==signature) and ('inspect',signature) not in self.failed:
                self._start('inspect',media,signature)
                return
            if codec=='av1' and (not self.currentIndex() or media.width<=960) and not self._ready(media,signature,self.compat_ready,self.compat_signatures) and ('compat',signature) not in self.failed:
                self._start('compat',media,signature)
                return
            if self.currentIndex() and media.width>960 and not self._ready(media,signature,self.ready,self.ready_signatures) and ('optimized',signature) not in self.failed:
                self._start('optimized',media,signature)
                return

    def _start(self,kind,media,signature):
        from .ui import Worker
        from .media import generate_proxy,video_codec
        import copy

        snapshot=copy.deepcopy(media)
        self.busy=True
        self.job_kind=kind
        token=threading.Event()
        self.token=token
        if kind=='inspect':
            worker=Worker(video_codec,snapshot.path,self.w.settings.get('ffprobe','ffprobe'))
        else:
            def report_progress(fraction,message):
                worker.signals.progress.emit((fraction,message))
            worker=Worker(generate_proxy,snapshot,self.w.settings.get('ffmpeg','ffmpeg'),
                          cancel=token,compatibility=kind=='compat',progress=report_progress)

        def current():
            live=self.w.project.media_by_id(snapshot.id)
            return live if live and self._signature(live)==signature else None

        def ready(value):
            live=current()
            if token.is_set() or not live:return
            if kind=='inspect':
                self.inspected_codecs[snapshot.id]=(signature,value)
                live.video_codec=value
                if value=='av1':
                    for key in list(self.w.transport.decoders):
                        if key[0]==snapshot.id and key[3]=='video':self.w.transport.retire_decoder(key)
                    self.w.transport.sync(True)
            elif kind=='compat':
                self.compat_ready[snapshot.id]=value
                self.compat_signatures[snapshot.id]=signature
                # The existing AV1 decoder is black; switch as soon as the
                # compatible copy is ready, even while the timeline is playing.
                self.apply(force=True)
                self.w.statusBar().showMessage('AV1 preview ready · '+snapshot.name,5000)
            else:
                self.ready[snapshot.id]=value
                self.ready_signatures[snapshot.id]=signature
                self.apply(force=self._codec(live,signature)=='av1')

        def failed(error):
            if not token.is_set():
                self.failed.add((kind,signature))
                if kind=='compat':
                    self.w.statusBar().showMessage('AV1 preview preparation failed. Original media and export are unchanged; check FFmpeg settings.',10000)
                elif kind=='optimized':
                    self.w.statusBar().showMessage('Optimized preview failed; using the available original/compatible video.',10000)

        def finished():
            self.busy=False
            self.job_kind=''
            self.token=None
            self.request()

        worker.signals.result.connect(ready)
        worker.signals.error.connect(failed)
        worker.signals.finished.connect(finished)
        if kind=='compat':
            def show_progress(update):
                if not token.is_set() and current():
                    self.w.statusBar().showMessage(
                        f'Preparing AV1 preview: {round(update[0]*100)}% · {snapshot.name} · original retained for export')
            worker.signals.progress.connect(show_progress)
        self.w.start_worker(worker)
        if kind=='compat':
            self.w.statusBar().showMessage('Preparing H.264 preview for AV1 video · '+snapshot.name+' · original retained for export')
        elif kind=='optimized':
            self.w.statusBar().showMessage('Preparing optimized preview · '+snapshot.name+' · original retained for export')

    def cancel(self,optimized_only=False):
        if self.token and (not optimized_only or self.job_kind=='optimized'):
            self.token.set()
