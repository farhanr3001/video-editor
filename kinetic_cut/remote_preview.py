"""Input-owning frontend for an isolated native GPU preview.

The embedded render HWND is disabled, so native hit testing belongs to the
editor's host window. No cross-process input forwarding or frame readback runs
in ordinary playback.
"""
import copy
import time
from types import SimpleNamespace
from PySide6.QtCore import QObject,QTimer,QPointF,QPoint,QRect,Qt,Signal,QEventLoop
from PySide6.QtGui import QWindow,QImage,QColor,QBackingStore,QPainter,QRegion
from PySide6.QtWidgets import QWidget,QApplication
from .quick_surface import Surface
from .native_engine import LatestRequest
from .gpu_preview_process import Peer,desktop_name


class InputHost(QWindow):
    frameSwapped=Signal()
    def __init__(self,surface):
        super().__init__();self.surface=surface;self.store=QBackingStore(self)
    def exposeEvent(self,event):
        if not self.isExposed():return
        rect=QRect(QPoint(),self.size());self.store.resize(self.size());region=QRegion(rect)
        self.store.beginPaint(region);painter=QPainter(self.store.paintDevice())
        painter.fillRect(rect,QColor(getattr(self.surface.canvas,'_viewer_bg','#191a1d')))
        painter.end();self.store.endPaint();self.store.flush(region)
    def grabWindow(self):return self.surface.capture()
    def update(self):self.requestUpdate()
    def releaseResources(self):pass
    def rendererInterface(self):
        return SimpleNamespace(graphicsApi=lambda:SimpleNamespace(name=self.surface.diagnostics().get('graphics_backend','initializing')))


class RemotePreview(Surface):
    remote=True
    def __init__(self,canvas):
        QObject.__init__(self,canvas)
        self.owner=self.viewport=self.canvas=canvas;self.closed=False;self.suspended=False
        self.offset=QPointF();self._viewport_update=None;self._expose_pending=False
        self.view=InputHost(self);self.container=QWidget.createWindowContainer(self.view,canvas)
        self.container.setFocusPolicy(Qt.NoFocus);self.container.setAcceptDrops(True)
        self.container.hide();self.container.setGeometry(canvas.rect());self.container.setAttribute(Qt.WA_NativeWindow);self.container.winId()
        for obj in (self.view,self.container,canvas):obj.installEventFilter(self)
        self.root=QObject(self);self.root.setProperty('color',QColor('#191a1d'))
        self.epoch=0;self.signature=None;self.mailbox=LatestRequest();self.sources={};self.worker=None
        self.frames=self.completed=self.gpu_frames=self.cpu_frames=0;self.bounds={};self._diagnostics={};self.cpu_ready={}
        self._sequence=0;self._force=True;self._signature=None;self._document=None;self._cpu_revision=None
        self._cache_epoch=0
        self._last_frame=0;self._capture_serial=0;self._capturing=False
        self.identity_image=QImage(1,1,QImage.Format_ARGB32_Premultiplied);self.identity_image.fill(Qt.white)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        self.status_timer=QTimer(self);self.status_timer.setInterval(16);self.status_timer.timeout.connect(self.collect)
        self.peer=Peer(desktop_name(),int(self.view.winId()));self.status_timer.start()
        self._restarts=0
        self.geometry(canvas.rect());self.schedule()

    def _expose(self):
        self._expose_pending=False
        if not self.closed and self.viewport.isVisible() and not getattr(self.canvas,'caption_focus',False):
            self.container.show();self.view.update()

    def schedule(self):
        if not self.closed and not self.suspended and not self.timer.isActive():self.timer.start(0)

    def sync_transport(self,force=False):
        self._force|=force;self.schedule()

    def invalidate_caches(self):
        self._cache_epoch+=1;self.schedule()

    def cpu_media(self,media_id):
        # Same full-document compatibility decision as the in-process engine,
        # recomputed only after a document edit, never per playback frame.
        from .gpu_preview import GpuPreview
        return GpuPreview.cpu_media(self,media_id)

    @property
    def targets(self):
        c=self.canvas;p=c.project
        if p is None:return []
        from .keyframes import evaluated
        from .visual_fx import evaluate_visual_fx,apply_visual_fx_to_transform
        at=p.playhead;nearby,transitions,_=p.runtime_index.playback(at)
        active={i.track:i for i in nearby if i.start<=at<i.start+i.duration and not i.muted
                and i.track in p.video_tracks and p.track_states.get(i.track,{}).get('visible',True)}
        for trans in transitions:
            if trans.track not in p.video_tracks or not p.track_states.get(trans.track,{}).get('visible',True):continue
            identifier=trans.right_item_id if trans.progress(at)>=.5 and trans.right_item_id else trans.left_item_id or trans.right_item_id
            if identifier:active[trans.track]=p.item_by_id(identifier)
        targets=[];frame=c.composition_rect()
        for item in active.values():
            if not item or item.role in ('title','graphic'):continue
            shown=evaluated(item,at-item.start)
            fx=evaluate_visual_fx(shown,at-item.start,p.settings.width,p.settings.height)
            if fx.is_active:
                shown=copy.copy(shown);shown.transform=copy.copy(shown.transform);apply_visual_fx_to_transform(shown.transform,fx)
            rect=frame if shown.role=='background' else c._layer_rect(shown,self.identity_image,frame,shown.role=='facecam')
            targets.append((shown,self.identity_image,rect))
        return targets

    def refresh(self):
        if self.closed or self.suspended:return
        c=self.canvas;p=c.project;window=c.window();transport=getattr(window,'transport',None)
        self.geometry(c.rect())
        if p is None or transport is None:return
        at=transport.position;nearby,transitions,captions=p.runtime_index.playback(at)
        items=list(nearby);ids={i.id for i in items}
        for transition in transitions:
            for identifier in (transition.left_item_id,transition.right_item_id):
                item=p.item_by_id(identifier)
                if item and identifier not in ids:items.append(item);ids.add(identifier)
        signature=(id(p),p.__dict__.get('_edit_revision',0),tuple(i.id for i in items),tuple(t.id for t in transitions),tuple(cap.id for cap in captions))
        if signature!=self._signature:
            template=copy.copy(p);template.timeline=items;template.transitions=list(transitions);template.captions=list(captions)
            template.media=[p.media_by_id(identifier) for identifier in {i.media_id for i in items} if p.media_by_id(identifier)]
            self._document=template.to_dict();self._document['path']='';self._signature=signature
            self.bounds={};c.text_rects={};self.cpu_ready={};self.sources={}
        # Ensure a CPU eligibility map exists even on an empty timeline.
        self.cpu_media('');tabs=getattr(getattr(window,'inspector',None),'tabs',None)
        selected=getattr(window,'timeline',None);toggle=getattr(window,'inspector_toggle',None)
        self._sequence+=1
        payload=dict(signature=signature,document=self._document,duration=p.duration,sequence=self._sequence,at=at,cache_epoch=self._cache_epoch,
            proxies=dict(getattr(window,'proxies',{})),cpu_media=tuple(getattr(self,'_cpu_media',())),
            size=(max(1,c.width()),max(1,c.height())),zoom=c.view_zoom,pan=(c.view_pan.x(),c.view_pan.y()),
            canvas={name:getattr(c,name,None) for name in ('selected_item_id','selected_caption_id','transform_controls_visible',
                'caption_focus','drag_mode','drag_handle','drag_text','drag_origin','center_guide_active','read_only')},
            drag_item=getattr(getattr(c,'drag_item',None),'id',''),selected=tuple(getattr(selected,'selected_ids',())),
            captions=tuple(getattr(selected,'selected_caption_ids',())),inspector=(tabs.currentIndex(),tabs.tabText(tabs.currentIndex())) if tabs else (0,'Video'),
            inspector_open=toggle.isChecked() if toggle else True,background=getattr(c,'_viewer_bg','#191a1d'),
            clock=(transport.origin,transport.started,transport.rate,transport.playing,transport.scrubbing),force=self._force)
        self._force=False;self.peer.submit(payload)

    def collect(self):
        status=self.peer.take_status()
        if status:
            self._diagnostics=status['diagnostics'];self.native_status={key:status[key] for key in ('hwnd','parent','pid','exposed','visible','disabled')}
            self.completed=status['completed'];self.frames=self._diagnostics.get('scene_graph_frames',0)
            self.gpu_frames=self._diagnostics.get('gpu_source_frames',0);self.cpu_frames=self._diagnostics.get('cpu_source_frames',0)
            if status.get('signature')==self._signature:
                self.bounds=status['bounds'];self.sources=status['sources'];self.cpu_ready=status['cpu_frames']
                if not getattr(self.canvas,'caption_focus',False):
                    self.canvas.text_rects={key:rect.translated(self.canvas.composition_rect().topLeft()) for key,rect in self.bounds.items()}
            if self.frames!=self._last_frame:self._last_frame=self.frames;self.view.frameSwapped.emit()
        if self.peer.error:self._diagnostics['renderer_error']=self.peer.error
        if self.peer.error and not self.peer.active and not self.closed and not self.suspended and self._restarts<2:
            self._restarts+=1;self.peer=Peer(desktop_name(),int(self.view.winId()))
            self._force=True;self.schedule()
            status_bar=getattr(self.canvas.window(),'statusBar',None)
            if status_bar:status_bar().showMessage('Preview renderer restarted after a device or decoding failure.',6000)
        if self.suspended and not self.peer.active:self.status_timer.stop()

    def diagnostics(self):
        return dict(self._diagnostics,composition_owner='isolated GPU preview process',renderer_pid=self.peer.pid,
            scene_requests_replaced=self.peer.replaced,renderer_process_alive=self.peer.active,renderer_restarts=self._restarts)

    def capture(self):
        if self.closed or self._capturing or not self.peer.active:return QImage()
        from .preview_process import unpack
        self._capture_serial+=1;serial=self._capture_serial
        if not self.peer.command(('capture',serial)):return QImage()
        self._capturing=True;loop=QEventLoop();timer=QTimer();timer.setInterval(5);answer=[]
        def poll():
            result=self.peer.take_response(serial)
            if result is not None:answer.append(result);loop.quit()
            elif not self.peer.active:loop.quit()
        timer.timeout.connect(poll);timer.start();QTimer.singleShot(3000,loop.quit)
        try:loop.exec()
        finally:timer.stop();self._capturing=False
        return unpack(answer[0]) if answer else QImage()

    def suspend(self):
        self.suspended=True;self.timer.stop();self.container.hide();self.peer.close()

    def close(self):
        if self.closed:return
        self.suspend();self.closed=True;self.status_timer.stop()
        for obj in (self.view,self.container,self.viewport):obj.removeEventFilter(self)
        self.container.deleteLater()
