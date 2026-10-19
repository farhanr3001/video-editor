"""Bounded worker composition and exact-content raster reuse at viewer resolution.

No widget, mutable project, decoder buffer or native video frame enters a worker.
The renderer is shared with the synchronous viewer; edit controls stay on the GUI.
"""
import copy
import hashlib
import time
import math
from concurrent.futures import ThreadPoolExecutor, Future
from types import MethodType
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from .image_cache import ImageCache, FileImageCache


class SceneContext:
    def __init__(self, project, frames, active, fallback, interactive, raster_scale, draw_captions=True):
        from .widgets import PreviewCanvas
        self.project=project; self.frames=frames; self.active_frames=active; self.fallback_frames=fallback
        self.frame=QImage(); self.text_rects={}; self.effect_cache={}; self.crop_cache={}
        self.still_cache=FileImageCache(64*1024**2,16)
        self.selected_item_id=''; self.transform_controls_visible=False
        self.interactive=interactive; self.raster_scale=raster_scale
        self.draw_captions=draw_captions
        for name in ('_active','_layer_rect','_graphic_rect','_draw_layer_item','_draw_layer_transition','_paint_scene'):
            setattr(self,name,MethodType(getattr(PreviewCanvas,name),self))
        self._source_rect=PreviewCanvas._source_rect
        self._has_pixel_effects=PreviewCanvas._has_pixel_effects
    def _prepare_layer_image(self,item,image,target,rect):
        from .preview_raster import RasterContext, prepare_layer_image
        context=RasterContext(self.project,self.interactive,self.raster_scale,self.effect_cache,self.crop_cache)
        return prepare_layer_image(context,item,image,target,rect)


def render(context, rect, size, scale):
    image=QImage(size[0],size[1],QImage.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(scale); image.fill(Qt.transparent)
    painter=QPainter(image)
    painter.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
    try:
        if not getattr(context,'transparent',False):painter.fillRect(rect,Qt.black)
        _,notice=context._paint_scene(painter,rect)
    finally: painter.end()
    return image,context.text_rects,notice


class CompositionCache:
    def __init__(self, canvas):
        self.canvas=canvas; self.images=ImageCache(128*1024**2,96)
        self.bounds={}; self.executor=None; self.future=None; self.pending=None
        self.last=None; self.closed=False; self.hits=0; self.misses=0; self.discarded=0
        self.template=None; self.template_signature=None
        self.renderer=None
        self.last_completed=0.
        self.completed=0;self.last_frame=None;self.requested_frame=None;self.serial=0;self.presented_serial=0;self.direction=1;self.presented_key=None
    def clear(self):
        self.images.clear(); self.bounds.clear(); self.last=None; self.pending=None;self.last_frame=None;self.requested_frame=None;self.presented_serial=0;self.presented_key=None
        self.template=None; self.template_signature=None
        self.last_completed=0.
        if self.future:self.future.cancel()
        self.future=None
    def close(self):
        self.closed=True; self.clear()
        if self.renderer:self.renderer.close()
        if self.executor:self.executor.shutdown(wait=False,cancel_futures=True)
        self.executor=None
    def synchronous(self,key=None):
        # Record exact GUI fallback too, including missing input/extreme zoom.
        # Later work may match this scene, but must never replace it with an
        # earlier request or an older source at the same timeline timestamp.
        p=self.canvas.project;transport=getattr(self.canvas.window(),'transport',None)
        self.direction=-1 if transport and getattr(transport,'playing',False) and getattr(transport,'rate',1)<0 else 1
        self.serial+=1;self.last=None;self.last_frame=round(p.playhead*max(1,p.settings.fps));self.requested_frame=self.last_frame
        self.presented_serial=self.serial;self.presented_key=key
    def request(self, frame_rect):
        c=self.canvas; p=c.project
        at=p.playhead
        # Preserve ordering and all transition endpoints, including those outside
        # ordinary clip containment. Local signatures invalidate only changed scenes.
        transitions=[t for t in p.transitions if t.contains_time(at)]
        transition_ids={i for t in transitions for i in (t.left_item_id,t.right_item_id) if i}
        items=[i for i in p.timeline if i.track in p.video_tracks and
               (i.start<=at<i.start+i.duration or i.id in transition_ids)]
        # The raster belongs to the composition, not the widget's pan offset.
        # View translation must never invalidate expensive pixel preparation.
        # Render the complete canvas locally, then place it in the GUI painter.
        origin=frame_rect.topLeft()
        rect=QRectF(0,0,frame_rect.width(),frame_rect.height())
        size=(max(1,math.ceil(rect.width()*c.devicePixelRatioF())),max(1,math.ceil(rect.height()*c.devicePixelRatioF())))
        if size[0]*size[1]*4>64*1024**2:self.synchronous();return None
        def publish_bounds(bounds):c.text_rects={k:r.translated(origin) for k,r in bounds.items()}
        active={i.id:c.active_frames[i.id] for i in items if i.id in c.active_frames}
        frames={k:QImage(c.frames[k]) for k in set(active.values()) if k in c.frames}
        fallback={i.id:QImage(c.fallback_frames[i.id]) for i in items if i.id in getattr(c,'fallback_frames',{})}
        used={i.media_id for i in items}
        media=[m for m in p.media if m.id in used]
        kinds={m.id:m.kind for m in media}
        required=[i for i in items if not i.muted and kinds.get(i.media_id)=='video'
                  and p.track_states.get(i.track,{}).get('visible',True)]
        if any((i.id not in active or active[i.id] not in frames or frames[active[i.id]].isNull())
               and (i.id not in fallback or fallback[i.id].isNull()) for i in required):
            # Never cache a black/incomplete composition while source decoders
            # are loading. The ordinary source hold remains authoritative.
            self.synchronous();return None
        assets=[m.path for m in media if m.kind=='image']
        assets += [n.get('source','') for i in items for n in i.graphic_data.get('scene',{}).get('nodes',[]) if n.get('kind')=='image']
        from pathlib import Path
        signatures=[]
        for path in assets:
            try:
                info=Path(path).stat(); signatures.append((path,info.st_size,info.st_mtime_ns,info.st_ctime_ns))
            except OSError:signatures.append((path,None))
        content=repr((p.settings,p.subtitle_style,p.track_states,items,transitions,
                      tuple(p.video_tracks),[(m.id,m.path,m.width,m.height) for m in media],signatures,
                      rect.x(),rect.y(),rect.width(),rect.height(),size,c.devicePixelRatioF()))
        signature=hashlib.sha256(content.encode()).digest()
        def frame_identity(image):return image.text('_kinetic_source_frame') or image.cacheKey()
        key=(signature,round(at*max(1,p.settings.fps)),tuple((repr(k),frame_identity(v)) for k,v in frames.items()),
             tuple((k,frame_identity(v)) for k,v in fallback.items()))
        self.serial+=1
        compatible=(signature,tuple((i.id,i.role) for i in items))
        transport=getattr(c.window(),'transport',None)
        direction=-1 if transport and getattr(transport,'playing',False) and getattr(transport,'rate',1)<0 else 1
        if self.requested_frame is not None and (direction!=self.direction or direction*(key[1]-self.requested_frame)<0):
            # Explicit seeks/direction changes start a new presentation order.
            self.last=None;self.last_frame=None;self.presented_serial=0;self.presented_key=None
        self.requested_frame=key[1];self.direction=direction
        # Full time-dependent scenes cannot share old frames after an edit or cut.
        # For continuous playback, only identical content signatures may hold while
        # the latest image is being completed; gaps/caption boundaries are exact.
        cached=self.images.get(key)
        if cached is not None:
            self.hits+=1;bounds,notice=self.bounds.get(key,({},''));publish_bounds(bounds)
            # Exact-cache hits are presentations too. A subsequent cache miss
            # must never fall back behind the frame we just displayed.
            self.last=(compatible,cached,bounds,notice);self.last_frame=key[1];self.last_completed=time.monotonic();self.presented_serial=self.serial;self.presented_key=key
            return cached,notice
        self.misses+=1
        if self.future and self.future.done():
            old_key,old_compatible,future=self.pending
            try:
                image,bounds,notice=future.result()
                self.completed+=1
                self.images.put(old_key,image); self.bounds[old_key]=(bounds,notice)
                while len(self.bounds)>96:self.bounds.pop(next(iter(self.bounds)))
                if (old_compatible==compatible and direction*(key[1]-old_key[1])>=0 and (self.last_frame is None or direction*(old_key[1]-self.last_frame)>=0)
                        and (getattr(future,"_kinetic_request_serial",0)>=self.presented_serial or old_key==self.presented_key)):
                    self.last=(compatible,image,bounds,notice); self.last_completed=time.monotonic();self.last_frame=old_key[1];self.presented_serial=self.serial;self.presented_key=old_key
                else:self.discarded+=1
            except Exception:
                import logging
                logging.exception('Preview composition failed; using synchronous renderer')
                self.close(); return None
            self.future=None; self.pending=None
            if old_key==key:
                self.last=(compatible,image,bounds,notice);self.last_frame=key[1];self.last_completed=time.monotonic();self.presented_serial=self.serial;self.presented_key=key
                publish_bounds(bounds)
                return image,notice
        if not self.closed and self.future is None:
            from .caption_fonts import load_fonts
            load_fonts()
            # Detach scene data once per content change, not once per frame.
            # Only one composition runs at a time; renderer inputs are read-only.
            if self.template_signature!=signature:
                snapshot=copy.copy(p)
                snapshot.settings=copy.deepcopy(p.settings); snapshot.subtitle_style=copy.deepcopy(p.subtitle_style)
                snapshot.timeline=copy.deepcopy(items); snapshot.transitions=copy.deepcopy(transitions)
                snapshot.captions=[]
                snapshot.track_states=copy.deepcopy(p.track_states); snapshot.media=copy.deepcopy(media)
                snapshot.video_tracks=list(p.video_tracks); snapshot.audio_tracks=list(p.audio_tracks)
                self.template=snapshot; self.template_signature=signature
            snapshot=copy.copy(self.template); snapshot.playhead=at
            context=SceneContext(snapshot,frames,active,fallback,True,c.devicePixelRatioF(),False)
            owner=c.window()
            if hasattr(owner,'start_worker'):
                from .ui import Worker
                from .preview_process import RendererProcess
                import os
                separate=os.environ.get('KINETIC_COMPOSITION_PROCESS','1')=='1'
                if separate and self.renderer is None:self.renderer=RendererProcess()
                future=Future()
                scale=c.devicePixelRatioF()
                def prepare():
                    if not future.set_running_or_notify_cancel():return
                    try:future.set_result(self.renderer.render(context,rect,size,scale) if separate else render(context,rect,size,scale))
                    except BaseException as error:future.set_exception(error)
                worker=Worker(prepare); worker.maintenance=True
                def cancel():
                    future.cancel()
                    if self.renderer:self.renderer.close()
                worker.cancel_callback=cancel
                self.future=future; owner.start_worker(worker)
            else:
                if self.executor is None:self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='preview-composition')
                self.future=self.executor.submit(render,context,rect,size,c.devicePixelRatioF())
            self.future._kinetic_request_serial=self.serial
            self.pending=(key,compatible,self.future)
        # A stalled helper must not turn into indefinitely frozen footage.
        # Preserve the recent complete composition briefly; after that use the
        # existing synchronous renderer while the bounded helper recovers/fails.
        if (self.last and self.last[0]==compatible and self.last_frame is not None
                and 0<=direction*(key[1]-self.last_frame)<=max(1,p.settings.fps*.2)
                and time.monotonic()-self.last_completed<.2):
            _,image,bounds,notice=self.last; publish_bounds(bounds); return image,notice
        # The caller will paint this exact scene synchronously. Fence it too:
        # late background output must not rewind behind that GUI presentation.
        self.synchronous(key)
        return None
