"""Native Qt/D3D scene-graph preview with bounded asynchronous effect islands.

Ordinary video never becomes QImage: QMediaPlayer -> VideoOutput -> RHI texture
-> crop/grade/blur shaders -> Qt's render thread. Unsupported pixel algorithms
remain exact, isolated in a single background renderer, then uploaded as layers.
The GUI only publishes geometry and immutable handles. No synchronous fallback.
"""
import copy
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QTimer, QRectF, QPointF, QSizeF, Qt
from PySide6.QtGui import QImage, QPainter, QTransform, QMatrix4x4, QVector4D, QVector2D
from PySide6.QtQuick import QQuickItem
from .quick_surface import Surface, enabled
from .native_engine import LatestRequest
from .creative_effects import NAMES as CREATIVE_NAMES, descriptor, clock as creative_clock


def sampling_size(source_width,source_height,viewport_width,viewport_height,dpr=1.,view_zoom=1.):
    """Stable source-space effect grid, independent of the animated media rect.

    Two physical viewport pixels per intermediate axis retain minification
    detail without growing beyond native source resolution or the existing
    2048-pixel render-target limit. Resize/DPI/manual view changes may reallocate;
    per-frame clip transforms do not. Geometry is never snapped to this grid.
    """
    width=max(1.,float(source_width));height=max(1.,float(source_height))
    budget=min(2048.,2*max(1.,viewport_width,viewport_height)*max(.25,dpr)*max(1.,view_zoom))
    scale=min(1.,budget/max(width,height))
    return QSizeF(min(2048,max(2,math.ceil(width*scale))),min(2048,max(2,math.ceil(height*scale))))


def shader_supported(item):
    if item.role in ('title','graphic') or item.crop_softness or abs(item.contrast-1)>.001:return False
    if item.composite_mode!='Normal':return False
    effects=[e for e in item.effects if e.get('enabled',True)]
    return all(e.get('name')=='Gaussian Blur' or e.get('category')=='Visual FX' or e.get('name') in CREATIVE_NAMES for e in effects) and sum(e.get('name')=='Gaussian Blur' for e in effects)<=1

def transition_supported(project,transition):
    from .animated_transitions import NAMES
    if transition.name not in NAMES:return False
    items=[project.item_by_id(v) for v in (transition.left_item_id,transition.right_item_id) if v]
    return all(i and not i.muted and shader_supported(i) for i in items)


def attach(canvas):
    if not enabled():return None
    try:
        import os
        if os.environ.get('KINETIC_GPU_PREVIEW_PROCESS','1')=='1' and not os.environ.get('KINETIC_GPU_RENDERER_CHILD'):
            from .remote_preview import RemotePreview
            renderer=RemotePreview(canvas)
        else:renderer=GpuPreview(canvas)
        canvas.gpu=renderer;return renderer
    except Exception:
        import logging
        logging.exception('D3D preview initialization failed; compatibility renderer remains available')
        return None


class GpuPreview(Surface):
    def __init__(self,canvas):
        super().__init__(canvas,'GpuPreview.qml')
        self.canvas=canvas;self.sources={};self.layers={};self.transition_pairs={};self.serial=0
        self.sampling_diagnostic=os.environ.get('KINETIC_SAMPLING_DIAGNOSTIC')=='1'
        self.layer_images={};self._used_textures=set();self.bounds={};self.last_tracks={};self.retired_sources=[];self.notice=''
        self.targets=[]
        self.suspended=False;self.whole_scene_cpu=False
        self.worker=None;self.future=None;self.executor=None;self.pending=None;self.snapshot_cache={}
        self.mailbox=LatestRequest();self.epoch=0;self.signature=None;self.last_time=None
        self.completed=0;self.dropped=0;self.cpu_frames=0;self.gpu_frames=0
        self.decoded_handles={};self.decode_wait={};self.preparation_ms=0.;self.publish_ms=0.
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        self.result_timer=QTimer(self);self.result_timer.setInterval(8);self.result_timer.timeout.connect(self.publish)
        self.geometry(canvas.rect());self.identity_image=QImage(1,1,QImage.Format_ARGB32_Premultiplied)
        self.identity_image.fill(Qt.white)
        self.overlay=self.create('GpuImage.qml');self.overlay.setProperty('visible',True);self.overlay.setZ(100000)
        self.schedule()
    def schedule(self):
        if not self.closed and not self.suspended and not self.timer.isActive():self.timer.start(0)
    def invalidate_caches(self):
        self.epoch+=1;self.signature=None;self.snapshot_cache.clear()
        self.canvas.still_cache.clear();self.canvas.effect_cache.clear();self.canvas.crop_cache.clear()
        # Retire the pixel helper too: its retained AI/vision images must not
        # survive an explicit Cache Manager clear in another process.
        if self.worker:self.worker.close()
        self.schedule()
    def cpu_media(self,media_id):
        if hasattr(self,'_forced_cpu_media'):return media_id in self._forced_cpu_media
        p=self.canvas.project
        if p is None:return False
        revision=(id(p),p.__dict__.get('_edit_revision',0))
        if getattr(self,'_cpu_revision',None)!=revision:
            # Document changes rebuild this map once. It is not a playback query.
            ids={i.media_id for i in p.timeline if i.role not in ('title','graphic') and not shader_supported(i)}
            if any(i.composite_mode!='Normal' for i in p.timeline):
                ids.update(i.media_id for i in p.timeline if i.role not in ('title','graphic'))
            transition_ids={v for t in p.transitions if not transition_supported(p,t) for v in (t.left_item_id,t.right_item_id)}
            ids.update(i.media_id for i in p.timeline if i.id in transition_ids)
            self._cpu_revision=revision;self._cpu_media=ids
        return media_id in self._cpu_media
    def create_source(self,key,media):
        old=self.sources.get(key)
        if old:self.retired_sources.append(old)
        source=self.create('GpuSource.qml',self.item('sources'))
        source.setProperty('pixelWidth',max(1,media.width));source.setProperty('pixelHeight',max(1,media.height))
        self.sources[key]=dict(item=source,texture=source.findChild(QQuickItem,'texture'),ready=False,stamp=None)
        sink=source.property('sink');sink._frame_stamp=None;sink._kinetic_gpu_texture=True
        self.sources[key]['probe']=self.timing.watch(sink) if self.timing else None
        return sink
    def freeze(self,key):
        record=self.sources.get(key)
        if record:
            record['item'].setProperty('admitted',False);record['ready']=False
            if record.get('probe'):record['probe'].active(False)
    def admit(self,key,frame,seek_started=None):
        record=self.sources.get(key)
        if record:
            record['item'].setProperty('admitted',True);record['ready']=True;record['stamp']=frame.startTime()
            self.gpu_frames+=1;record['handle']=frame.handleType().name;self.decoded_handles[key[0]]=record['handle']
            if seek_started is not None:self.decode_wait[key[0]]=(time.monotonic()-seek_started)*1000
            self.schedule()
    def cpu_frame(self,key,image):
        self.cpu_frames+=1
        self.schedule()
    def retire(self,key,engine=None):
        record=self.sources.get(key)
        if record:
            record['item'].setProperty('admitted',False);record['retired']=True;record['ready']=False;record['engine']=engine
            if record.get('probe'):record['probe'].active(False)
    def _texture(self,identifier,image):
        self._used_textures.add(identifier)
        obj=self.layer_images.get(identifier)
        if obj is None:
            obj=self.create('GpuImage.qml');obj.setProperty('minification',True);self.layer_images[identifier]=obj
        identity=image.cacheKey()
        if obj.property('_imageIdentity')==identity:return obj
        obj.setProperty('_imageIdentity',identity)
        self.serial+=1;self.images.put(identifier,image)
        obj.setProperty('source',f'image://prepared/{identifier}?v={self.serial}')
        return obj
    def _file_texture(self,path):
        from PySide6.QtCore import QUrl
        import os
        identifier='file:'+path;self._used_textures.add(identifier);obj=self.layer_images.get(identifier)
        if obj is None:
            obj=self.create('GpuImage.qml');obj.setProperty('asynchronous',True);obj.setProperty('minification',True)
            self.layer_images[identifier]=obj
        try:
            info=os.stat(path);stamp=f'{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}'
        except OSError:stamp='missing'
        if obj.property('_fileStamp')!=stamp:
            obj.setProperty('_fileStamp',stamp)
            url=QUrl.fromLocalFile(path);url.setQuery('_asset='+stamp)
            obj.setProperty('source',url.toString())
        return obj
    def _layer(self,key,creative=False):
        existing=self.layers.get(key)
        if existing and bool(existing.property('_creativeLayer'))!=creative:
            existing.setVisible(False);existing.setParentItem(None);existing.deleteLater();self.layers.pop(key)
        if key not in self.layers:
            self.layers[key]=self.create('GpuCreativeLayer.qml' if creative else 'GpuLayer.qml',self.item('canvas'))
            self.layers[key].setProperty('_creativeLayer',creative)
        return self.layers[key]
    def _place(self,key,texture,target,matrix=None,crop=None,item=None,alpha=1.,blur=(0.,0.,1.,1.),z=0):
        creative=bool(item and any(e.get('name') in CREATIVE_NAMES for e in item.effects))
        layer=self._layer(key,creative);layer.setVisible(True);layer.setZ(z)
        if creative:
            before=[];after=[];passed=False
            for effect in item.effects:
                if not effect.get('enabled',True):continue
                if effect.get('name')=='Gaussian Blur':passed=True
                if effect.get('name') in CREATIVE_NAMES:
                    data=descriptor(effect,item);data['time']=creative_clock(effect,item,self.canvas.project.playhead)
                    (after if passed else before).append(data)
            layer.setProperty('beforeEffects',before);layer.setProperty('afterEffects',after)
        layer.setWidth(max(.01,target.width()));layer.setHeight(max(.01,target.height()))
        layer.setProperty('placement',QMatrix4x4(matrix or QTransform().translate(target.x(),target.y())))
        layer.setProperty('texture',texture);layer.setProperty('cropRect',crop or QVector4D(0,0,1,1))
        layer.setProperty('grade',QVector4D(item.brightness,item.contrast,0 if item.grayscale else item.saturation,
            self.canvas.project.settings.background_brightness if item.role=='background' else 1.) if item else QVector4D(0,1,1,1))
        layer.setProperty('alpha',alpha);layer.setProperty('ellipse',bool(item and item.transform.shape=='circle'))
        # Sharpen is a per-layer shader uniform, including at zero. It must not
        # retire every decoder/crop using this source just to reset one control.
        media=self.canvas.project.media_by_id(item.media_id) if item else None
        # Full source dimensions remain constant through procedural zoom and
        # nonuniform transforms; shader UVs still apply the exact fractional crop.
        source_size=texture.property('sourceSize')
        source_width=media.width if media and media.width>0 else source_size.width() if source_size and source_size.width()>0 else self.canvas.width()*self.view.devicePixelRatio()
        source_height=media.height if media and media.height>0 else source_size.height() if source_size and source_size.height()>0 else self.canvas.height()*self.view.devicePixelRatio()
        if creative:
            # Procedural patterns generate detail beyond source pixels. Anchor
            # their raster to the document transform, never the animated clone.
            original=self.canvas.project.item_by_id(item.id) or item
            base=self.canvas._layer_rect(original,self.identity_image,self.canvas.composition_rect())
            source_width=base.width()*self.view.devicePixelRatio()
            source_height=base.height()*self.view.devicePixelRatio()
        layer.setProperty('processingSize',sampling_size(source_width,source_height,
            self.canvas.width(),self.canvas.height(),self.view.devicePixelRatio(),getattr(self.canvas,'view_zoom',1.)))
        sw=media.width*crop.z() if media and crop else target.width()
        sh=media.height*crop.w() if media and crop else target.height()
        layer.setProperty('sharpen',max(0.,item.sharpen*2) if item else 0.)
        layer.setProperty('pixelStep',QVector2D(1/max(1,min(sw,target.width())),1/max(1,min(sh,target.height()))))
        transport=getattr(self.canvas.window(),'transport',None)
        layer.setProperty('rasterScale',.5 if transport and transport.scrubbing else 1.)
        for prop,value in zip(('blurX','blurY','blurMix','borderMode'),blur):layer.setProperty(prop,float(value))
        return layer
    def refresh(self):
        if self.closed:return
        started=time.perf_counter();c=self.canvas;p=c.project
        self._used_textures=set()
        if getattr(c,'caption_focus',False):
            self.container.hide();return
        self.geometry(c.rect())
        frame=c.composition_rect()
        for prop,value in (('canvasX',frame.x()),('canvasY',frame.y()),('canvasWidth',frame.width()),('canvasHeight',frame.height())):self.root.setProperty(prop,value)
        self.root.setProperty('background',getattr(c,'_viewer_bg','#191a1d'))
        if p is None:return
        at=p.playhead;nearby,transitions,captions=p.runtime_index.playback(at)
        items=[i for i in nearby if i.start<=at<i.start+i.duration]
        active={i.track:i for i in items if not i.muted and i.track in p.video_tracks and p.track_states.get(i.track,{}).get('visible',True)}
        transition_tracks={t.track:t for t in transitions if t.track in p.video_tracks and p.track_states.get(t.track,{}).get('visible',True)}
        shown=set();jobs=[];self.targets=[];used_sources=set();native_tracks=set()
        local=QRectF(0,0,frame.width(),frame.height())
        # CPU compatibility for non-source-over blend stacks is explicit. The
        # bounded worker preserves exact ordering, without blocking input.
        whole=any(i.composite_mode!='Normal' for i in active.values())
        self.whole_scene_cpu=whole
        tracks=['__whole__'] if whole else p.video_tracks
        from .keyframes import evaluated
        from .visual_fx import evaluate_visual_fx,apply_visual_fx_to_transform
        from .missing_media import unavailable
        from .native_animation import required as native_required
        legacy=[i for i in items if i.role in ('title','graphic') and not native_required(i) and not i.muted
                and i.track in p.video_tracks and p.track_states.get(i.track,{}).get('visible',True)]
        legacy_ids={i.id for i in legacy}
        whole_ids={i.id for i in active.values()}|legacy_ids
        whole_items=[i for i in items if i.id in whole_ids]
        for transition in transitions:
            for identifier in (transition.left_item_id,transition.right_item_id):
                partner=p.item_by_id(identifier)
                if partner and partner.id not in whole_ids:whole_items.append(partner);whole_ids.add(partner.id)
        geometry_active=dict(active)
        for track,transition in transition_tracks.items():
            chosen=transition.right_item_id if transition.progress(at)>=.5 and transition.right_item_id else transition.left_item_id or transition.right_item_id
            if chosen:geometry_active[track]=p.item_by_id(chosen)
        evaluated_items={}
        render_originals=dict((i.id,i) for i in geometry_active.values() if i)
        for t in transitions:
            if transition_supported(p,t):
                for identifier in (t.left_item_id,t.right_item_id):
                    item=p.item_by_id(identifier)
                    if item:render_originals[item.id]=item
        for original in render_originals.values():
            if original is None or original.role in ('title','graphic'):continue
            elapsed=min(max(0,at-original.start),max(0,original.duration-1/p.settings.fps)) if original.id not in {i.id for i in active.values()} else at-original.start
            shown_item=evaluated(original,elapsed)
            fx=evaluate_visual_fx(shown_item,elapsed,p.settings.width,p.settings.height)
            if fx.is_active:
                shown_item=copy.copy(shown_item);shown_item.transform=copy.copy(shown_item.transform);apply_visual_fx_to_transform(shown_item.transform,fx)
            evaluated_items[original.id]=shown_item
            target=frame if shown_item.role=='background' else c._layer_rect(shown_item,self.identity_image,frame,shown_item.role=='facecam')
            self.targets.append((shown_item,self.identity_image,target))
        valid_bounds={i.id for i in active.values()}|legacy_ids|{cap.id for cap in captions}
        self.bounds={key:value for key,value in self.bounds.items() if key[1] in valid_bounds}
        entries=[];visible_pairs=set()
        for z,track in enumerate(tracks):
            trans=transition_tracks.get(track)
            if not whole and trans and transition_supported(p,trans):
                from .animated_transitions import descriptor
                from .transitions import apply_easing
                pair=self.transition_pairs.get(track)
                if pair is None:pair=self.create('GpuTransition.qml',self.item('canvas'));self.transition_pairs[track]=pair
                pair.setVisible(True);pair.setZ(z);pair.setWidth(frame.width());pair.setHeight(frame.height());visible_pairs.add(track)
                data=descriptor(trans);v=data['params']
                pair.setProperty('shader',f'../shaders/transition_{data["mode"]}.frag.qsb')
                pair.setProperty('progress',apply_easing(trans.progress(at),data['easing']))
                pair.setProperty('p1',QVector4D(*v[:3],0));pair.setProperty('p2',QVector4D(*v[3:],frame.width()/max(1,frame.height())))
                for side,identifier in zip(('outgoing','incoming'),(trans.left_item_id,trans.right_item_id)):
                    item=p.item_by_id(identifier)
                    if item:entries.append((z,track+'::'+side,item,None,pair.findChild(QQuickItem,side)))
            else:entries.append((z,track,active.get(track),trans,None))
        for track,pair in self.transition_pairs.items():
            if track not in visible_pairs:pair.setVisible(False)
        for z,track,item,transition,pair_parent in entries:
            key='track:'+track
            if whole:
                jobs.append((key,whole_items,list(transitions),list(captions),z,False));shown.add(key);continue
            if transition:
                pair=[p.item_by_id(v) for v in (transition.left_item_id,transition.right_item_id) if v]
                jobs.append((key,[i for i in pair if i],[transition],[],z,True));shown.add(key);continue
            if item is None:continue
            if item.id in legacy_ids:continue
            if not shader_supported(item):
                jobs.append((key,[item],[],[],z,True));shown.add(key);continue
            original=item;item=evaluated_items[item.id]
            if pair_parent:
                item=copy.copy(item);item.start=at-min(max(0,at-original.start),max(0,original.duration-1/p.settings.fps))
            media=p.media_by_id(item.media_id)
            if unavailable(media,item):continue
            texture=None;held_native=False;source_key=c.active_frames.get(item.id)
            record=self.sources.get(source_key)
            if record and record.get('retired'):record=None
            if record and record['ready']:texture=record['texture']
            elif record:
                previous=self.last_tracks.get(track)
                # A pending seek holds the preceding texture. Gaps retire it
                # below; normal navigation never reuses an earlier frame.
                if previous:texture=previous['texture']
            if texture is None:
                if media and media.kind=='image':texture=self._file_texture(media.path)
                else:
                    image=c.frames.get(source_key,getattr(c,'fallback_frames',{}).get(item.id,QImage()))
                    if not image.isNull():texture=self._texture('raw:'+str(source_key or media.id),image)
                    elif self.cpu_media(media.id):
                        # A backend switch may retain its last native texture
                        # only until the first replacement CPU frame arrives.
                        # Never let a retired source override arriving frames.
                        previous=self.last_tracks.get(track)
                        if previous:texture=previous['texture'];held_native=True
            if texture is None:continue
            if record or held_native:native_tracks.add(track)
            if record and record['ready']:
                self.last_tracks[track]=record;used_sources.add(id(record))
            target=local if item.role=='background' else c._layer_rect(item,self.identity_image,local,item.role=='facecam')
            crop=item.crop.clamped();uv=QVector4D(crop.x,crop.y,crop.width,crop.height)
            factor=frame.width()/p.settings.width
            blur=[0.,0.,1.,1.]
            for effect in item.effects:
                if effect.get('enabled',True) and effect.get('name')=='Gaussian Blur':
                    blur=[effect.get('horizontal',12)*factor,effect.get('vertical',12)*factor,effect.get('blend',100)/100,{'Reflect':1.,'Replicate':0.,'Transparent':2.}.get(effect.get('border','Reflect'),1.)]
            if item.role=='background':
                # Background source is fitted with KeepAspectRatioByExpanding.
                sw=max(1,media.width);sh=max(1,media.height);ratio=frame.width()/max(1,frame.height());sr=sw/sh
                uv=QVector4D((1-ratio/sr)/2,0,ratio/sr,1) if sr>ratio else QVector4D(0,(1-sr/ratio)/2,1,sr/ratio)
                small_scale=max(270/sw,480/sh)
                display_scale=max(frame.width()/sw,frame.height()/sh)
                sigma=p.settings.blur*.25*display_scale/small_scale
                blur[0]*=display_scale/small_scale/max(.0001,factor)
                blur[1]*=display_scale/small_scale/max(.0001,factor)
                blur[0]=math.hypot(blur[0],sigma);blur[1]=math.hypot(blur[1],sigma)
                alpha=1.
                matrix=QTransform()
                if original.keyframes:
                    center=QPointF(item.transform.x*frame.width(),item.transform.y*frame.height())
                    center-=QPointF(item.transform.anchor_x*(item.transform.scale-1)*factor,item.transform.anchor_y*(item.transform.effective_scale_y-1)*factor)
                    anchor=QPointF(item.transform.anchor_x*factor,item.transform.anchor_y*factor)
                    matrix.translate(center.x()+anchor.x(),center.y()+anchor.y());matrix.rotate(item.transform.rotation);matrix.translate(-anchor.x(),-anchor.y());matrix.scale(item.transform.scale,item.transform.effective_scale_y);matrix.translate(-local.center().x(),-local.center().y())
            else:
                alpha=1.;pivot=target.center()+QPointF(item.transform.anchor_x*factor,item.transform.anchor_y*factor)
                matrix=QTransform().translate(pivot.x(),pivot.y());matrix.rotate(item.transform.rotation);delta=target.center()-pivot;matrix.translate(delta.x(),delta.y())
                perspective=QTransform().rotate(item.transform.pitch,Qt.XAxis).rotate(item.transform.yaw,Qt.YAxis)
                matrix=perspective*matrix
                matrix.scale(-1 if item.transform.flip_horizontal else 1,-1 if item.transform.flip_vertical else 1)
                matrix.translate(-target.width()/2,-target.height()/2)
            elapsed=at-item.start;alpha*=item.opacity/100
            if item.fade_in:alpha*=min(1.,max(0.,elapsed/item.fade_in))
            if item.fade_out:alpha*=min(1.,max(0.,(item.duration-elapsed)/item.fade_out))
            layer=self._place(key,texture,target,matrix,uv,item,alpha,blur,z)
            layer.setParentItem(pair_parent or self.item('canvas'));shown.add(key)
        if not whole and legacy:
            jobs.append(('legacy-overlays',legacy,[],[],len(tracks)+1,True));shown.add('legacy-overlays')
        if not whole and captions and p.track_states.get('subtitle_1',{}).get('visible',True):
            jobs.append(('captions',[],[],list(captions),len(tracks)+2,True));shown.add('captions')
        for key,layer in self.layers.items():
            if key not in shown:layer.setVisible(False)
        self.last_tracks={t:v for t,v in self.last_tracks.items() if t in native_tracks}
        retained={id(v) for v in self.last_tracks.values()}
        for source_key,record in list(self.sources.items()):
            if record.get('probe'):record['probe'].active(id(record) in used_sources and not record.get('retired'))
            if record.get('retired') and id(record) not in retained and (not record.get('engine') or record['engine'].finished):
                if record.get('probe'):record['probe'].close()
                record['item'].deleteLater();self.sources.pop(source_key,None)
        for record in list(self.retired_sources):
            if id(record) not in retained and (not record.get('engine') or record['engine'].finished):
                if record.get('probe'):record['probe'].close()
                record['item'].deleteLater();self.retired_sources.remove(record)
        signature=(id(p),p.__dict__.get('_edit_revision',0),tuple((key,tuple(i.id for i in its),tuple(t.id for t in ts),tuple(cap.id for cap in caps)) for key,its,ts,caps,_,_ in jobs),round(frame.width()),round(frame.height()))
        transport=getattr(c.window(),'transport',None);direction=-1 if transport and transport.playing and transport.rate<0 else 1
        if signature!=self.signature or self.last_time is not None and direction*(at-self.last_time)<-1/max(1,p.settings.fps):
            self.epoch+=1;self.signature=signature;self.snapshot_cache.clear()
        self.last_time=at
        self.requested=(jobs,p,local,direction,at,self.epoch)
        if jobs:
            self.mailbox.submit(self.epoch,at)
            if self.future is None:self._start()
        else:self.notice=''
        self._used_textures.update(key for key in shown if key in self.layer_images)
        for identifier in tuple(self.layer_images):
            if len(self.layer_images)<=32:break
            if identifier not in self._used_textures:
                self.layer_images.pop(identifier).deleteLater();self.images.remove(identifier)
        self._fit_prepared_geometry(jobs,local)
        self._controls(frame)
        self.publish_ms=(time.perf_counter()-started)*1000
    def _fit_prepared_geometry(self,jobs,rect):
        # Prepared pixels use canvas-local coordinates. Keep the last useful
        # texture attached to the current canvas while a new raster is pending.
        # Otherwise the canvas origin moves immediately but text retains its
        # previous size, visibly jumping on every worker completion during zoom.
        for key,*_ in jobs:
            layer=self.layers.get(key)
            if layer is not None:
                layer.setWidth(max(.01,rect.width()));layer.setHeight(max(.01,rect.height()))
                layer.setProperty('placement',QMatrix4x4(QTransform()))
        previous=getattr(self,'_bounds_size',None)
        if previous and previous.width()>0 and previous.height()>0:
            sx=rect.width()/previous.width();sy=rect.height()/previous.height()
            if sx!=1 or sy!=1:
                self.bounds={key:QRectF(value.x()*sx,value.y()*sy,value.width()*sx,value.height()*sy) for key,value in self.bounds.items()}
        self._bounds_size=rect.size()
    def _controls(self,frame):
        c=self.canvas
        c.text_rects={k:r.translated(frame.topLeft()) for k,r in self.bounds.items()}
        transport=getattr(c.window(),'transport',None)
        if transport and transport.playing and not c.transform_controls_visible and not self.notice:
            # Animated layer geometry must not repaint/upload an invisible
            # full-viewer controls image on every video frame.
            self.overlay.setVisible(False)
            return
        self.overlay.setVisible(True)
        # Only controls are painted here. Video, blur and composition are all
        # native GPU nodes. Hit geometry reuses the editor's existing routines.
        ids=getattr(getattr(c.window(),'timeline',None),'selected_ids',set())|{c.selected_item_id}
        caption_ids=getattr(getattr(c.window(),'timeline',None),'selected_caption_ids',set())|{c.selected_caption_id}
        inspector=getattr(c.window(),'inspector',None);tabs=getattr(inspector,'tabs',None)
        selected=c.project.item_by_id(c.selected_item_id)
        key=(self.canvas.size(),frozenset(ids),frozenset(caption_ids),c.selected_item_id,tuple((i.id,repr(i.transform),r) for i,_,r in self.targets if i.id in ids),repr(self.bounds),c.transform_controls_visible,c.drag_mode,getattr(c,'center_guide_active',False),frame,self.notice,
             tabs.currentIndex() if tabs else None,repr(selected.effects) if selected else None)
        if key==getattr(self,'_control_key',None):return
        self._control_key=key
        image=QImage(max(1,c.width()),max(1,c.height()),QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
        painter=QPainter(image);painter.setRenderHint(QPainter.Antialiasing)
        try:
            if c.transform_controls_visible:
                for item,_,target in self.targets:
                    if item.id in ids:c._draw_transform_box(painter,item,target)
                for (kind,identifier),bounds in c.text_rects.items():
                    if identifier not in ids|caption_ids:continue
                    item=c.project.item_by_id(identifier)
                    if kind=='graphic' and item:c._draw_transform_box(painter,item,c._graphic_rect(item,frame))
                    elif c._is_headline(item):c._draw_transform_box(painter,item,c._headline_rect(item,frame))
                    else:c._draw_text_box(painter,bounds)
            c._draw_effect_center(painter,frame)
            if self.notice:
                from PySide6.QtGui import QColor,QFont
                painter.setPen(QColor('#ffdd88'));painter.setFont(QFont('Segoe UI',9));painter.drawText(c.rect().adjusted(12,8,-12,-8),Qt.AlignBottom|Qt.AlignHCenter,self.notice)
        finally:painter.end()
        self.images.put('controls',image);self.serial+=1
        self.overlay.setWidth(c.width());self.overlay.setHeight(c.height());self.overlay.setProperty('source',f'image://prepared/controls?v={self.serial}')
    def _start(self):
        if self.closed or self.future is not None:return
        request=self.mailbox.take()
        if request is None:return
        jobs,p,rect,direction,at,epoch=self.requested
        if not jobs:return
        c=self.canvas;batch=[]
        for key,items,transitions,captions,z,transparent in jobs:
            template=self.snapshot_cache.get(key)
            if template is None:
                template=copy.copy(p);template.settings=copy.deepcopy(p.settings);template.subtitle_style=copy.deepcopy(p.subtitle_style)
                template.timeline=copy.deepcopy(items);template.transitions=copy.deepcopy(transitions);template.captions=copy.deepcopy(captions)
                template.media=copy.deepcopy([p.media_by_id(identifier) for identifier in {i.media_id for i in items} if p.media_by_id(identifier)])
                template.track_states=copy.deepcopy(p.track_states);self.snapshot_cache[key]=template
            snapshot=copy.copy(template);snapshot.playhead=at
            active={i.id:c.active_frames[i.id] for i in items if i.id in c.active_frames}
            frames={v:QImage(c.frames[v]) for v in set(active.values()) if v in c.frames}
            fallback={i.id:QImage(c.fallback_frames[i.id]) for i in items if i.id in getattr(c,'fallback_frames',{})}
            # Never publish an incomplete worker composition as a valid frame.
            # Native sources do not have CPU images, and newly-seeked software
            # sources can arrive after the scene command.
            if any((media:=p.media_by_id(i.media_id)) and media.kind=='video' and i.track in p.video_tracks and i.role not in ('title','graphic')
                   and active.get(i.id) not in frames and i.id not in fallback for i in items):return
            batch.append((key,snapshot,active,frames,fallback,z,transparent))
        if self.executor is None:
            self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='gpu-effect-bridge')
        if self.worker is None or self.worker.closed:
            from .preview_process import RendererProcess
            self.worker=RendererProcess()
        worker=self.worker
        def render_batch():
            from .preview_compositor import SceneContext
            started=time.perf_counter();results=[]
            for key,snapshot,active,frames,fallback,z,transparent in batch:
                context=SceneContext(snapshot,frames,active,fallback,True,1.,True);context.transparent=transparent
                image,bounds,notice=worker.render(context,rect,(max(1,math.ceil(rect.width())),max(1,math.ceil(rect.height()))),1.)
                results.append((key,image,bounds,z,notice))
            return results,(time.perf_counter()-started)*1000
        self.pending=(epoch,at,direction,rect);self.future=self.executor.submit(render_batch)
        self.result_timer.start()
    def publish(self):
        if self.closed or self.future is None or not self.future.done():return
        future=self.future;epoch,at,direction,rect=self.pending;self.future=None
        try:
            results,elapsed=future.result()
            if epoch!=self.epoch:self.dropped+=1
            else:
                self.preparation_ms=elapsed;self.completed+=1;bounds={};notices=[]
                current=self.canvas.composition_rect()
                target=QRectF(0,0,current.width(),current.height())
                for key,image,item_bounds,z,notice in results:
                    texture=self._texture(key,image);self._place(key,texture,target,z=z);bounds.update(item_bounds)
                    if notice:notices.append(notice)
                self.bounds=bounds;self._bounds_size=rect.size();self._fit_prepared_geometry([],target)
                self.notice='\n'.join(dict.fromkeys(notices));self._control_key=None;self._controls(current)
        except Exception:
            if epoch==self.epoch:
                import logging
                logging.exception('Asynchronous GPU effect preparation failed')
            else:self.dropped+=1
        self.result_timer.stop();self._start()
    def diagnostics(self):
        project=self.canvas.project
        active_ids={item.media_id for item in project.runtime_index.playback(project.playhead)[0]
                    if item.start<=project.playhead<item.start+item.duration and item.track in project.video_tracks} if project else set()
        active_keys=set(self.canvas.active_frames.values());decoders=[];handles={}
        from .video_worker import WorkerVideoPlayer
        from .qt_native import NativeVideoPlayer
        transport=getattr(self.canvas.window(),'transport',None)
        for key,(player,_,sink) in getattr(transport,'decoders',{}).items():
            if key not in active_keys or sink is None:continue
            record=self.sources.get(key,{})
            handle=record.get('handle') if record.get('ready') and not record.get('retired') else None
            if handle:handles[key[0]]=handle
            software=isinstance(player,WorkerVideoPlayer)
            decoders.append(dict(media_id=key[0],engine='PyAV/libav worker' if software else 'Qt FFmpeg / native VideoOutput' if isinstance(player,NativeVideoPlayer) else 'Qt FFmpeg compatibility',
                hardware_decode=player.engine.hardware_active if software else True if handle=='RhiTextureHandle' else None,handle_type=handle))
        hardware=[entry['hardware_decode'] for entry in decoders]
        result=dict(super().diagnostics(),composition='CPU whole-scene fallback / GPU presentation' if self.whole_scene_cpu else 'GPU scene graph',decoder=', '.join(dict.fromkeys(entry['engine'] for entry in decoders)) or 'prepared image texture',active_decoders=decoders,
                    hardware_decode=True if True in hardware else False if hardware and all(value is False for value in hardware) else None,decoded_frame_handles=handles,
                    source_codecs={key:media.video_codec for key in active_ids if (media:=project.media_by_id(key))},
                    hardware_decode_note='RhiTextureHandle confirms a Qt FFmpeg hardware-backed frame; missing texture handles alone do not identify decoder hardware status. Software-worker status is reported per decoder.',
                    gpu_source_frames=self.gpu_frames,cpu_source_frames=self.cpu_frames,
                    effect_helper_pid=self.worker.process.pid if self.worker and self.worker.process else None,
                    pending_effect_batches=int(self.future is not None),dropped_effect_batches=self.dropped+self.mailbox.dropped,
                    asynchronous_effect_ms=self.preparation_ms,gui_scene_publish_ms=self.publish_ms,
                    seek_to_decoded_frame_ms=dict(self.decode_wait),decode_execution_ms=None,
                    adaptive_scrub_resolution=True,dropped_preview_frames=None,
                    presentation_counter_note='Qt VideoOutput does not expose per-video presentation drops; discarded queued effect requests are counted separately',
                    decode_timing_note='Qt public video sink exposes delivery timestamps, not decoder execution duration')
        if self.sampling_diagnostic:
            from .preview_sampling_diagnostics import sampling_state
            result.update(sampling_state(self))
        return result
    def close(self):
        if self.closed:return
        self.suspend()
        for record in [*self.sources.values(),*self.retired_sources]:
            if record.get('probe'):record['probe'].close()
        self.sources.clear();super().close()
    def suspend(self):
        self.suspended=True;self.container.hide()
        self.timer.stop();self.result_timer.stop()
        if self.future:self.future.cancel()
        if self.worker:self.worker.close()
        if self.executor:self.executor.shutdown(wait=False,cancel_futures=True)
