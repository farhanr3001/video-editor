"""Viewport-indexed retained timeline nodes and GPU multiresolution waveforms.

Zoom/pan changes scene-graph coordinates, never thumbnail URLs or clip rasters.
The existing QWidget owns editing gestures, locks, snapping, history and drops.
"""
import copy
import math
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import QRect, QRectF, QTimer, QUrl
from PySide6.QtGui import QImage,QPainter,QColor
from .quick_surface import Surface, enabled


def attach(timeline):
    if not enabled():return None
    try:
        renderer=GpuTimeline(timeline);timeline.gpu=renderer;return renderer
    except Exception:
        import logging
        logging.exception('Native timeline initialization failed; retained QWidget compatibility surface remains available')
        return None


def peak_images(samples):
    """Prepare immutable peak textures outside the GUI; bounded row width."""
    import numpy as np
    from .waveforms import Waveform
    if not isinstance(samples,Waveform):
        values=np.clip(np.abs(np.asarray(samples,dtype=float)),0,1)*32767
        samples=Waveform(np.column_stack((-values,values)).astype(np.int16))
    result=[]
    for level,data in enumerate(samples.levels):
        width=min(4096,max(1,len(data)));height=max(1,math.ceil(len(data)/width))
        pixels=np.zeros((width*height,4),dtype=np.uint8);pixels[:,3]=255
        pixels[:len(data),0]=np.ceil(np.clip(-data[:,0].astype(float)/32768,0,1)*255).astype(np.uint8)
        pixels[:len(data),1]=np.ceil(np.clip(data[:,1].astype(float)/32768,0,1)*255).astype(np.uint8)
        image=QImage(pixels.data,width,height,width*4,QImage.Format_RGBA8888).copy()
        result.append((image,len(data),.001*4**level))
    return result


class GpuTimeline(Surface):
    def __init__(self,timeline):
        super().__init__(timeline,'GpuTimeline.qml',timeline.viewport())
        self.timeline=timeline;self.nodes=OrderedDict();self.lanes={};self.waveforms={};self.wave_pending={}
        self.wave_executor=None;self.refresh_ms=0.;self.visible_count=0;self.updates=0;self.project_id=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.refresh)
        from .qt_native import LIB
        from .qt_native import NativeClips
        self.native_clips=NativeClips(self.item('body')) if LIB else None
        if self.native_clips:self.native_clips.link_icon()
        self.root.setProperty('nativeRuler',True)
        self.root.setProperty('originalChrome',True)
        self.wave_timer=QTimer(self);self.wave_timer.setInterval(16);self.wave_timer.timeout.connect(self.publish_waves)
        self.schedule()
    def schedule(self):
        if not self.closed and not self.timer.isActive():self.timer.start(0)
    def _node(self,key):
        node=self.nodes.get(key)
        if node is None:
            if self.native_clips:
                from .qt_native import ClipProxy
                node=ClipProxy()
            else:node=self.create('GpuClip.qml',self.item('body'));node.setProperty('timeline',self.root)
            self.nodes[key]=node
        self.nodes.move_to_end(key);return node
    def _wave(self,media,samples,seconds_per_pixel):
        if samples is None or not len(samples):return '',0,0
        cached=self.waveforms.get(media.id)
        if not cached or cached[0]!=id(samples):
            if media.id not in self.wave_pending:
                if self.wave_executor is None:self.wave_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='timeline-peaks')
                self.wave_pending[media.id]=(id(samples),self.wave_executor.submit(peak_images,samples))
                if not self.wave_timer.isActive():self.wave_timer.start()
            if not cached:return '',0,0
        levels=cached[1];level=0
        while level+1<len(levels) and levels[level][2]<seconds_per_pixel/16:level+=1
        image,count,resolution=levels[level]
        return f'image://prepared/wave:{media.id}:{cached[0]}:{level}',count,resolution
    def publish_waves(self):
        if self.closed:return
        changed=False
        for media_id,(identity,future) in list(self.wave_pending.items()):
            if not future.done():continue
            self.wave_pending.pop(media_id)
            try:levels=future.result()
            except Exception:
                import logging
                logging.exception('Timeline peak texture preparation failed');continue
            samples=self.timeline.waveforms.get(media_id)
            if identity!=id(samples):
                # _wave could not enqueue the replacement while this job was
                # pending. Wake refresh even on a paused, otherwise idle view.
                self.signature=None
                changed=True
                continue
            previous=self.waveforms.get(media_id)
            if previous:
                for level in range(len(previous[1])):self.images.remove(f'wave:{media_id}:{previous[0]}:{level}')
            self.waveforms[media_id]=(identity,levels)
            for level,(image,count,resolution) in enumerate(levels):
                identifier=f'wave:{media_id}:{identity}:{level}';self.images.put(identifier,image)
                if self.native_clips:self.native_clips.image('image://prepared/'+identifier,image)
            changed=True
        if not self.wave_pending:self.wave_timer.stop()
        if changed:self.schedule()
    def refresh(self):
        if self.closed:return
        started=time.perf_counter();t=self.timeline;p=t.project;viewport=t.viewport()
        area=QRect(t.LABEL_WIDTH+1,t.RULER_HEIGHT+1,max(1,viewport.width()-t.LABEL_WIDTH-12),max(1,viewport.height()-t.RULER_HEIGHT-1))
        self.geometry(QRect(0,0,max(1,viewport.width()-12),max(1,viewport.height())))
        if p is None:return
        if self.project_id!=id(p):
            self.project_id=id(p);self.signature=None;self.coverage=None
            for node in self.nodes.values():node.deleteLater()
            self.nodes.clear();self.waveforms.clear()
            for _,future in self.wave_pending.values():future.cancel()
            self.wave_pending.clear()
            with self.images.lock:self.images.images.clear()
            self._header_signature=None;self._affordance_signature=None
            if self.native_clips:self.native_clips.reset()
        pal=t._palette();self.root.setProperty('color',pal.get('timeline_bg','#191a1e'))
        self.root.setProperty('pixelsPerSecond',t.pixels_per_second)
        self.root.setProperty('scrollOffset',t.horizontalScrollBar().value()+1.)
        self.root.setProperty('playhead',p.playhead)
        if self.native_clips:self.native_clips.view(area.width(),area.height(),t.pixels_per_second,t.horizontalScrollBar().value()+1.)
        from .ui import timecode
        self.properties(self.root,dict(bodyX=area.left(),bodyY=area.top(),fps=float(p.settings.fps),clockText=timecode(p.playhead,p.settings.fps),rulerColor=pal.get('timeline_ruler_bg','#26272c'),textColor=pal.get('timeline_text','#b7bac1')))
        self._headers(pal,area)
        self._meters(area)
        from .gpu_timeline_chrome import refresh as refresh_chrome
        refresh_chrome(self,pal)
        self.root.setProperty('guide',t.snap_guide if t.snap_guide is not None and t.tool!='blade' else -1.)
        rects=t.marquee_controller.rects() if t.marquee else []
        self.root.setProperty('marquee',rects[0] if rects else QRectF())
        from .gpu_timeline_controls import refresh as refresh_controls
        refresh_controls(self,area)
        # Navigation changes only uniforms for nodes already in the overscan.
        # Active playback updates the cursor without rebuilding any delegates.
        zoom_band=math.floor(math.log(max(.001,t.pixels_per_second),4))
        signature=(id(p),p.__dict__.get('_edit_revision',0),t._paint_generation,zoom_band,viewport.size(),
                   t.video_scroll.value(),t.audio_scroll.value(),t.subtitle_scroll.value(),
                   frozenset(t.selected_ids),t.selected_id,frozenset(t.selected_caption_ids),
                   t.hover_id,t.drag_mode,tuple((i.id,i.start,i.duration,i.track) for i in t.move_preview+t.incoming_preview),
                   tuple((c.id,c.start,c.end) for c in t.caption_preview),repr(t.effect_hover),repr(t.transition_hover),
                   frozenset(t.retime_ids),repr(t.section_track_heights),t.provisional_track,repr(p.track_states),repr(pal),
                   tuple((m,record[0]) for m,record in self.waveforms.items()))
        visible_left=t.time_for_x(t.LABEL_WIDTH);visible_right=t.time_for_x(viewport.width())
        coverage=getattr(self,'coverage',None)
        if (signature==getattr(self,'signature',None) and coverage
                and coverage[0]<=visible_left and visible_right<=coverage[1]):
            self.refresh_ms=(time.perf_counter()-started)*1000;return
        self.signature=signature;self.updates+=1
        shown_lanes=set()
        for track in t.tracks():
            lane=t.track_rect(track);section=t.section_rect(track)
            if not lane.intersects(section):continue
            obj=self.lanes.get(track)
            if obj is None:obj=self.create('GpuLane.qml',self.item('body'));self.lanes[track]=obj
            obj.setVisible(True);obj.setProperty('color',pal.get('timeline_track_bg','#202126'))
            self.properties(obj,dict(laneY=lane.y()-area.top(),laneHeight=lane.height(),sectionTop=section.top()-area.top(),sectionBottom=section.bottom()-area.top()))
            shown_lanes.add(track)
        for track,obj in self.lanes.items():
            if track not in shown_lanes:obj.setVisible(False)
        left=t.time_for_x(t.LABEL_WIDTH-256);right=t.time_for_x(viewport.width()+256)
        self.coverage=(left,right)
        items=p.runtime_index.query('timeline',left,right)
        if t.drag_mode in ('trim_left','trim_right','retime_left','retime_right'):
            staged=copy.copy(p);staged.timeline=copy.deepcopy(items);staged.overwrite(t.snapshots);items=staged.timeline
        shown=set();link_counts=p.runtime_index.link_counts
        for ordinal,item in enumerate(list(items)+t.move_preview+t.incoming_preview):
            if item.track not in shown_lanes:continue
            ghost=getattr(item,'_drag_ghost',False)
            if t.move_preview and item.id in t.snapshots and not ghost and not t.alt_drag:continue
            media=(t.incoming_plan if getattr(item,'_incoming',False) else p).media_by_id(item.media_id)
            track_rect=t.track_rect(item.track);lane=t.item_rect(item,track_rect);section=t.section_rect(item.track)
            if not lane.intersects(section):continue
            key=('ghost:' if ghost else 'incoming:' if getattr(item,'_incoming',False) else '')+item.id
            obj=self._node(key);obj.setVisible(True);obj.setZ(ordinal)
            audio=item.track in p.audio_tracks
            from .missing_media import unavailable,label
            offline=unavailable(media,item)
            name=(label(media,item) if offline else 'Graphic · '+(item.graphic_type or 'Shape') if item.role=='graphic' else item.title_text if item.role=='title' else media.name if media else 'Offline')
            thumbnail=''
            if media and not audio and not offline:
                path=media.path if media.kind=='image' else media.thumbnail
                if path:thumbnail=QUrl.fromLocalFile(path).toString()
            wave,count,resolution=self._wave(media,t.waveforms.get(item.media_id),item.speed/max(.001,4**zoom_band)) if audio and media and not offline else ('',0,.001)
            group=item.group_id if item.link_id is None else item.link_id
            properties=dict(startTime=item.start,duration=item.duration,selected=item.id in t.selected_ids and not t.read_only,
                audio=audio,hovered=item.id==t.hover_id,ghost=ghost,label=name,thumbnail=thumbnail,textItem=item.role=='title',
                thumbnailAspect=(media.width/media.height if media and media.height else 16/9),waveform=wave,waveCount=float(count),waveResolution=resolution,
                sourceIn=item.in_point,sourceSpeed=item.speed,gain=10**(item.gain_db/20),fadeIn=item.fade_in,fadeOut=item.fade_out,
                retime=item.id in t.retime_ids,linked=bool(group and link_counts.get(group,0)>1),hasEffects=bool(item.effects),
                effectLabel='+ '+t.effect_hover[0] if t.effect_hover and t.effect_hover[1]==item.id else '',
                laneY=lane.y()-area.top(),laneHeight=lane.height(),sectionTop=section.top()-area.top(),sectionBottom=section.bottom()-area.top())
            color='#510b0e' if offline else '#326951' if audio else '#6d4a8e' if item.role=='graphic' else '#b9b097' if item.role=='title' else '#3c6c90'
            properties['color']=color
            self.properties(obj,properties)
            shown.add(key)
        captions=t.caption_painted if t.caption_painted is not None else p.runtime_index.query('captions',left,right)
        for caption in captions:
            lane=t.caption_rect(caption);section=t.section_rect('subtitle_1')
            if not lane.intersects(section):continue
            key='caption:'+caption.id;obj=self._node(key);obj.setVisible(True);obj.setZ(10000)
            for name,value in dict(startTime=caption.start,duration=caption.end-caption.start,selected=caption.id in t.selected_caption_ids,
                label=caption.text,caption=True,color='#b9b097',laneY=lane.y()-area.top(),laneHeight=lane.height(),sectionTop=section.top()-area.top(),sectionBottom=section.bottom()-area.top()).items():self.properties(obj,{name:value})
            shown.add(key)
        for transition in (() if self.native_clips else p.runtime_index.query('transitions',left,right)):
            lane=t.transition_rect(transition);section=t.section_rect(transition.track)
            if lane.isEmpty() or not lane.intersects(section):continue
            key='transition:'+transition.id;obj=self._node(key);obj.setVisible(True);obj.setZ(20000)
            for name,value in dict(startTime=transition.start,duration=transition.duration,selected=transition.id==t.selected_transition_id,
                label=transition.name,color='#44ffffff',laneY=lane.y()-area.top(),laneHeight=lane.height(),sectionTop=section.top()-area.top(),sectionBottom=section.bottom()-area.top()).items():self.properties(obj,{name:value})
            shown.add(key)
        for key,obj in self.nodes.items():
            if key not in shown:obj.setVisible(False)
        # Retain nearby delegates/texture URLs through reversals, with a hard cap.
        for key in list(self.nodes):
            if len(self.nodes)<=max(2048,len(shown)):break
            if key not in shown:self.nodes.pop(key).deleteLater()
        if self.native_clips:self.native_clips.publish(self.nodes.values())
        self.visible_count=len(shown);self.refresh_ms=(time.perf_counter()-started)*1000
    def _headers(self,pal,area):
        t=self.timeline;p=t.project
        signature=(t.viewport().size(),t.video_scroll.value(),t.audio_scroll.value(),t.subtitle_scroll.value(),
                   repr(t.section_track_heights),t.video_extent if hasattr(t,'video_extent') else 0,t.audio_extent,t.subtitle_extent,
                   repr(p.track_states),repr(p.track_names),tuple(p.video_tracks),tuple(p.audio_tracks),repr(pal),t.selected_track)
        if signature==getattr(self,'_header_signature',None):return
        self._header_signature=signature
        image=QImage(area.left(),max(1,t.viewport().height()),QImage.Format_ARGB32_Premultiplied)
        image.fill(QColor(pal.get('timeline_header_bg','#202126')));painter=QPainter(image)
        try:
            for track in t.tracks():
                if t.track_rect(track).intersects(t.section_rect(track)):t.paint_track_header(painter,track)
        finally:painter.end()
        self.images.put('headers',image);self.root.setProperty('headerSource',f'image://prepared/headers?v={self.updates}:{time.monotonic_ns()}')
    def _meters(self,area):
        t=self.timeline;signature=(self._header_signature,repr(t._audio_levels))
        if signature==getattr(self,'_meter_signature',None):return
        self._meter_signature=signature
        image=QImage(area.left(),max(1,t.viewport().height()),QImage.Format_ARGB32_Premultiplied);image.fill(0)
        painter=QPainter(image)
        try:t._paint_audio_levels(painter)
        finally:painter.end()
        node=getattr(self,'meter_texture',None)
        if node is None:
            node=self.create('GpuImage.qml');node.setVisible(True);node.setZ(1.5);self.meter_texture=node
        node.setWidth(image.width());node.setHeight(image.height());self.images.put('meters',image)
        node.setProperty('source',f'image://prepared/meters?v={time.monotonic_ns()}')
    def diagnostics(self):
        return dict(super().diagnostics(),surface='retained GPU timeline',visible_nodes=self.visible_count,
                    retained_nodes=len(self.nodes),gui_publish_ms=self.refresh_ms,delegate_updates=self.updates,
                    pending_peak_jobs=len(self.wave_pending),thumbnail_placeholders=False)
    def close(self):
        if self.closed:return
        self.timer.stop();self.wave_timer.stop()
        for _,future in self.wave_pending.values():future.cancel()
        if self.wave_executor:self.wave_executor.shutdown(wait=False,cancel_futures=True)
        self.wave_pending.clear();super().close()
