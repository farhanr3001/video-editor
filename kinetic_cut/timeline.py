"""Interactive NLE timeline: selection and links are independent of layout roles."""
import copy
import math
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetrics, QKeySequence, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QRegion
from PySide6.QtWidgets import QApplication, QMenu, QScrollBar, QToolTip
from .widgets import TimelineWidget as BaseTimeline
from .model import uid
from .icons import lucide_icon
from .editing import edit_only
from .transitions import Transition, TRANSITION_SET, TRANSITION_ICONS, SUBSECTION_BY_TRANSITION, default_transition_properties


class TimelineWidget(BaseTimeline):
    selectionChanged=Signal(object)
    captionSelected=Signal(str)
    captionBladeRequested=Signal(str,float)
    effectDropped=Signal(str,str)
    titleDropped=Signal(str,str,float)
    mediaBatchDropped=Signal(object,str,float)
    filesDropped=Signal(object,str,float)
    scrubFinished=Signal()
    transitionSelected=Signal(str)

    def __init__(self):
        self.move_preview=[]; self.provisional_track=""; self.provisional_scroll=None
        self.incoming_preview=[]; self.incoming_plan=None; self.incoming_drop=None
        self.selected_transition_id=""; self.transition_hover=None; self.trans_drag_orig=None
        self.read_only=False; self.effect_hover=None
        self.selected_ids=set(); self.selected_caption=""; self.selected_caption_ids=set(); self.linked_selection=True
        self.track_height=62; self.video_track_height=62.; self.audio_track_height=62.; self.subtitle_height=62.; self.subtitle_extent=68.; self.audio_extent=92.; self.marquee=None; self.snapshots={}; self.duplicate=False
        self.section_track_heights={}
        self.waveform_pending=set(); self.waveform_failures=set()
        self.drag_destination=""; self.thumbnails={}; self.caption_original=None
        self.caption_snapshots={}; self.caption_copy_ids={}; self.caption_preview=[]; self.caption_painted=None
        self.retime_ids=set(); self.hover_id=""; self.snap_guide=None; self.blade_hover_id=""; self.blade_hover_caption=""; self.blade_hover_time=None; self.divider_original=None
        self._waveform_pixmaps={}; self._scaled_thumbnails={}; self._frame_track_rects=None; self._frame_sec_rects=None; self.alt_drag=False
        self._vfx_flash_item_id = None
        self._timeline_backing=None; self._playhead_damage=QRegion(); self._painted_marquee=QRegion()
        self._audio_levels={}; self._meter_damage=QRegion()
        super().__init__()
        self._vfx_flash_timer = QTimer(self)
        self._vfx_flash_timer.setSingleShot(True)
        self._vfx_flash_timer.timeout.connect(self._clear_vfx_flash)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.subtitle_scroll=QScrollBar(Qt.Vertical,self.viewport()); self.video_scroll=QScrollBar(Qt.Vertical,self.viewport()); self.audio_scroll=QScrollBar(Qt.Vertical,self.viewport())
        for bar in (self.subtitle_scroll,self.video_scroll,self.audio_scroll):
            bar.setFixedWidth(10); bar.valueChanged.connect(self.viewport().update); bar.hide()
        self.viewport().setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_OpaquePaintEvent)
        self.scrub_timer=QTimer(self); self.scrub_timer.setInterval(16); self.scrub_timer.timeout.connect(self.scroll_scrub); self.scrub_x=0.
        from .selection_scroll import TimelineMarquee
        self.marquee_controller=TimelineMarquee(self)
        from .timeline_gestures import ClipScroll
        self.clip_scroll=ClipScroll(self); self.pan_section=''; self.roll_hover=None; self.roll_members=None

    def flash_vfx_overlay(self, item_id: str):
        """Temporarily illuminate the effect duration clamper overlay on the clip."""
        self._vfx_flash_item_id = item_id
        if hasattr(self, "_vfx_flash_timer"):
            self._vfx_flash_timer.stop()
            self._vfx_flash_timer.start(1500)
        self.viewport().update()

    def _clear_vfx_flash(self):
        self._vfx_flash_item_id = None
        self.viewport().update()

    def set_read_only(self,value):
        if value:self.cancel_drag()
        self.scrub_timer.stop()
        self.marquee_controller.stop()
        self.read_only=bool(value); self.drag_mode=""; self.alt_drag=False; self.marquee=None; self.snapshots={}; self.effect_hover=None
        self.hover_id=""; self.blade_hover_id=""; self.blade_hover_caption=""; self.blade_hover_time=None; self.snap_guide=None
        self.viewport().setCursor(Qt.ArrowCursor)
        if getattr(self,"_menu",None):self._menu.close()
        self.viewport().update()

    def ensure_playhead_visible(self,value):
        """Follow seeks/playback, without undoing deliberate manual scrolling."""
        left=self.LABEL_WIDTH+18; right=self.viewport().width()-24
        if right<=left:return
        navigation_end=max(20,getattr(self,"_navigation_end",20),self.project.duration+5)
        if value+5>navigation_end:
            self._navigation_end=value+10; self._range()
        x=self.x_for_time(value); bar=self.horizontalScrollBar()
        if x<left:bar.setValue(bar.value()+round(x-left))
        elif x>right:bar.setValue(bar.value()+round(x-right))

    def update_playhead(self):
        """Invalidate only the old/new cursor strips and the timecode, not clips."""
        x=round(self.x_for_time(self.project.playhead)); old=getattr(self,'_painted_playhead_x',x)
        region=QRegion(QRect(0,0,self.LABEL_WIDTH,self.RULER_HEIGHT))
        for at in (old,x):region|=QRegion(QRect(at-10,0,21,self.viewport().height()))
        self._playhead_damage |= region
        self.viewport().update(region)

    def set_audio_levels(self,levels):
        if levels==self._audio_levels:return
        changed=set(levels)|set(self._audio_levels)
        self._audio_levels=levels
        damage=QRegion()
        for track in changed:
            if not self.project or track not in self.project.audio_tracks:continue
            rect=self.track_rect(track).intersected(self.section_rect(track))
            if not rect.isEmpty():damage |= QRegion(QRect(109,round(rect.top()+26),67,max(1,round(rect.height()-26))))
        self._meter_damage |= damage
        self.viewport().update(damage)

    def _paint_audio_levels(self,p):
        for track in (self.project.audio_tracks if self.project else []):
            rect=self.track_rect(track).intersected(self.section_rect(track))
            if rect.isEmpty() or rect.height()<36:continue
            _,button=self.header_controls(track); top=button.top()+2
            left,right,clipped=self._audio_levels.get(track,(0.,0.,False))
            for n,level in enumerate((left,right)):
                bar=QRectF(112,top+n*7,53,5)
                p.fillRect(bar,QColor('#171b1c'))
                fraction=max(0.,min(1.,(20*math.log10(max(level,1e-7))+60)/60))
                filled=bar.width()*fraction
                if filled:
                    p.fillRect(QRectF(bar.x(),bar.y(),min(filled,bar.width()*.78),bar.height()),QColor('#4cbd72'))
                    if filled>bar.width()*.78:p.fillRect(QRectF(bar.x()+bar.width()*.78,bar.y(),min(filled-bar.width()*.78,bar.width()*.17),bar.height()),QColor('#e1c052'))
                    if filled>bar.width()*.95:p.fillRect(QRectF(bar.x()+bar.width()*.95,bar.y(),filled-bar.width()*.95,bar.height()),QColor('#e45a51'))
            p.fillRect(QRectF(168,top,5,12),QColor('#e45a51' if clipped else '#35383d'))

    def update_selection_overlay(self):
        """Move the box without rerasterizing unchanged clips, text and thumbnails.

        Selection membership/scroll changes still request an ordinary full paint.
        The previous and next box fills both need damage, not just their borders.
        """
        region=QRegion(self._painted_marquee)
        if self.marquee:
            for rect in self.marquee_controller.rects():region |= QRegion(rect.toAlignedRect().adjusted(-2,-2,2,2))
        self._playhead_damage |= region
        self.viewport().update(region)

    def start_scrub(self,x):
        self.drag_mode="playhead"; self.scrub_x=x
        self._scrub_snap_points=[0.]+[edge for item in self.project.timeline for edge in (item.start,item.start+item.duration)]+[edge for caption in self.project.captions for edge in (caption.start,caption.end)] if (self.project and self.property("snapping")) else []
        self.scrub_at(x); self.scrub_timer.start()

    def scrub_at(self,x):
        self.scrub_x=x
        x=max(self.LABEL_WIDTH,min(self.viewport().width()-1,x))
        moment=max(0,self.time_for_x(x))
        self.snap_guide=None
        if self.property("snapping"):
            points=getattr(self,"_scrub_snap_points",None)
            if points is None:
                points=[0.]+[edge for item in self.project.timeline for edge in (item.start,item.start+item.duration)]+[edge for caption in self.project.captions for edge in (caption.start,caption.end)] if self.project else []
            if points:
                nearest=min(points,key=lambda value:abs(value-moment))
                if abs(nearest-moment)<=8/self.pixels_per_second:moment=nearest; self.snap_guide=nearest
        self.project.playhead=moment; self.playheadChanged.emit(moment); self.update_playhead()

    def scroll_scrub(self):
        if self.drag_mode!="playhead" or not self.project:self.scrub_timer.stop(); return
        left=self.LABEL_WIDTH+32; right=self.viewport().width()-32
        distance=self.scrub_x-left if self.scrub_x<left else self.scrub_x-right if self.scrub_x>right else 0
        if not distance:return
        if distance<0 and self.project.playhead<=0:return
        delta=round((4+min(1,abs(distance)/32)*14)*(1 if distance>0 else -1))
        bar=self.horizontalScrollBar(); before=bar.value()
        if distance>0 and before+delta>=bar.maximum():
            self._navigation_end=max(getattr(self,"_navigation_end",20),self.time_for_x(self.viewport().width())+10); self._range()
        bar.setValue(before+delta)
        if bar.value()!=before:self.scrub_at(self.scrub_x)

    def _track_height(self,track):
        return self.section_track_heights.get(self._section_name(track),self.track_height)

    def tracks(self):
        if not self.project:return []
        return (["subtitle_1"] if self.has_subtitles() else [])+list(reversed(self.display_tracks("video")))+self.display_tracks("audio")

    def has_subtitles(self):return bool(self.project and self.project.captions) or any(i.track=="subtitle_1" for i in self.incoming_preview)

    def display_tracks(self,kind):
        result=list(getattr(self.incoming_plan or self.project,kind+"_tracks")) if self.project else []
        if self.provisional_track=="__new_"+kind:result.append(self.provisional_track)
        elif kind=="audio" and self.provisional_track=="__new_audio_top":result.insert(0,self.provisional_track)
        return result

    def _state(self,track):
        if self.incoming_plan and track not in self.project.video_tracks+self.project.audio_tracks and track!="subtitle_1":return self.incoming_plan.track_states.get(track,{"locked":False,"visible":True})
        if track.startswith("__new_"):return {"locked":False,"visible":True}
        return super()._state(track)

    def set_provisional(self,track):
        if track==self.provisional_track:return
        if not self.provisional_track and track:self.provisional_scroll=(self.video_scroll.value(),self.audio_scroll.value())
        self.provisional_track=track; self._range()
        if track=="__new_video":self.video_scroll.setValue(self.video_scroll.maximum())
        elif track=="__new_audio":self.audio_scroll.setValue(self.audio_scroll.maximum())
        elif track=="__new_audio_top":self.audio_scroll.setValue(0)
        elif self.provisional_scroll:
            self.video_scroll.setValue(self.provisional_scroll[0]); self.audio_scroll.setValue(self.provisional_scroll[1]); self.provisional_scroll=None

    def cancel_drag(self):
        if hasattr(self,'clip_scroll'):self.clip_scroll.stop()
        self.pan_section=''; self.roll_hover=None; self.roll_members=None; self.viewport().unsetCursor()
        self.marquee_controller.stop()
        self.clear_incoming()
        if self.drag_mode.startswith('caption_'):
            for caption in self.project.captions:
                original=self.caption_snapshots.get(caption.id)
                if original:caption.start=original.start; caption.end=original.end
        if self.drag_mode.startswith("caption_") and self.caption_original:
            caption=next((c for c in self.project.captions if c.id==self.selected_caption),None)
            if caption:caption.start,caption.end=self.caption_original
        if self.drag_mode=="playhead":
            self._scrub_snap_points=None
            self.scrubFinished.emit()
        if self.drag_mode not in {"","move","playhead","marquee"}:
            for id,original in self.snapshots.items():
                item=self.project.item_by_id(id)
                if item:item.__dict__.update(copy.deepcopy(original.__dict__))
        self.move_preview=[]; self.set_provisional(""); self.drag_mode=""; self.alt_drag=False; self.marquee=None; self.snap_guide=None; self.scrub_timer.stop(); self.viewport().update()
        from .caption_gestures import clear
        clear(self)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape and self.drag_mode:self.cancel_drag(); event.accept(); return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected_transition_id:
            tid = self.selected_transition_id
            self.selected_transition_id = ""
            self.project.remove_transition(tid)
            self.transitionSelected.emit("")
            self.itemChanged.emit("")
            self.viewport().update()
            event.accept()
            return
        if (event.key()==Qt.Key_A and event.modifiers()==Qt.ControlModifier) or event.matches(QKeySequence.SelectAll):
            if self.project:
                all_ids={i.id for i in self.project.timeline}
                self.select_ids(all_ids,primary=self.selected_id or (next(iter(all_ids)) if all_ids else ""))
                event.accept(); return
        if event.key() in (Qt.Key_Left,Qt.Key_Right) and event.modifiers()==Qt.NoModifier and self.project:
            frame=round(self.project.playhead*self.project.settings.fps)+(1 if event.key()==Qt.Key_Right else -1)
            self.project.playhead=max(0,frame)/self.project.settings.fps; self.ensure_playhead_visible(self.project.playhead); self.playheadChanged.emit(self.project.playhead); self.viewport().update(); event.accept(); return
        super().keyPressEvent(event)

    def set_project(self,project):
        self._waveform_pixmaps.clear(); self._scaled_thumbnails.clear()
        if hasattr(self,'marquee_controller') and project is not self.project:self.marquee_controller.stop(); self.marquee=None; self.drag_mode=''
        self.selected_ids.intersection_update(i.id for i in project.timeline)
        if self.selected_id not in self.selected_ids:self.selected_id=next(iter(self.selected_ids),"")
        caption_ids={c.id for c in project.captions}; self.selected_caption_ids.intersection_update(caption_ids)
        if self.selected_caption not in self.selected_caption_ids:self.selected_caption=next(iter(self.selected_caption_ids),"")
        self.retime_ids.intersection_update(i.id for i in project.timeline)
        if self.selected_transition_id and not project.transition_by_id(self.selected_transition_id):
            self.selected_transition_id=""
        super().set_project(project)

    def set_zoom(self,value:float,anchor_x:float|None=None):
        self._waveform_pixmaps.clear()
        super().set_zoom(value,anchor_x)

    def set_waveform(self,media_id:str,values:list[float]):
        self._waveform_pixmaps.clear()
        super().set_waveform(media_id,values)

    def _range(self):
        if not hasattr(self,"track_height"):return
        duration=max(20,getattr(self,"_navigation_end",20),(self.project.duration if self.project else 0)+5)
        self.horizontalScrollBar().setRange(0,max(0,round(duration*self.pixels_per_second-self.viewport().width()+self.LABEL_WIDTH)))
        self.horizontalScrollBar().setPageStep(max(1,self.viewport().width()-self.LABEL_WIDTH))
        self.verticalScrollBar().setRange(0,0)
        sections=self._sections(); width=10; right=max(0,self.viewport().width()-width)
        counts={"subtitle":int(self.has_subtitles()),"video":len(self.display_tracks("video")),"audio":len(self.display_tracks("audio"))}
        for name,bar in (("subtitle",self.subtitle_scroll),("video",self.video_scroll),("audio",self.audio_scroll)):
            rect=sections[name]; content=counts[name]*self._track_height("subtitle_1" if name=="subtitle" else (self.project.video_tracks[0] if name=="video" and self.project and self.project.video_tracks else self.project.audio_tracks[0] if self.project and self.project.audio_tracks else ""))
            maximum=max(0,round(content-rect.height())); bar.setRange(0,maximum); bar.setPageStep(max(1,round(rect.height()))); bar.setSingleStep(max(12,round(self.section_track_heights.get(name,self.track_height)/2)))
            bar.setInvertedAppearance(name in {"video","subtitle"}); bar.setInvertedControls(name in {"video","subtitle"}); bar.setGeometry(right,round(rect.top()),width,max(0,round(rect.height()))); bar.setVisible(maximum>0 and rect.height()>14)

    def _sections(self):
        if self._frame_sec_rects is not None:
            return self._frame_sec_rects
        w=self.viewport().width(); top=float(self.RULER_HEIGHT); available=max(1.,self.viewport().height()-top)
        has_sub=self.has_subtitles(); div=float(self.AV_SEPARATOR)
        minimum=30.; sub=0.
        if has_sub:
            max_sub=max(minimum,available-div*2-minimum*2); sub=min(max_sub,max(minimum,self.subtitle_extent))
        remaining=available-sub-(div if has_sub else 0)
        audio=max(minimum,min(max(minimum,remaining-minimum-div),self.audio_extent)) if self.project and self.project.audio_tracks else 0.
        video=max(0.,remaining-audio-(div if audio else 0))
        sub_rect=QRectF(0,top,w,sub) if has_sub else QRectF()
        video_top=top+sub+(div if has_sub else 0); video_rect=QRectF(0,video_top,w,video)
        audio_top=video_rect.bottom()+div if audio else self.viewport().height(); audio_rect=QRectF(0,audio_top,w,max(0,self.viewport().height()-audio_top)) if audio else QRectF()
        res={"subtitle":sub_rect,"video":video_rect,"audio":audio_rect}
        return res

    def _section_name(self,track):
        if track=="subtitle_1":return "subtitle"
        return "audio" if track.startswith("__new_audio") or self.project and track in self.display_tracks("audio") else "video"

    def section_rect(self,track):return self._sections()[self._section_name(track)]

    def track_rect(self,track):
        if self._frame_track_rects is not None and track in self._frame_track_rects:
            return self._frame_track_rects[track]
        if not self.project or track not in self.tracks():return QRectF()
        section=self.section_rect(track); name=self._section_name(track)
        height=self._track_height(track)
        if name=="subtitle":index=0; y=section.bottom()-height+self.subtitle_scroll.value()
        elif name=="video":
            visual=list(reversed(self.display_tracks("video"))); index=visual.index(track); content=len(visual)*height
            # Video lanes grow upward from the A/V divider, matching NLE lane
            # ordering: V1 stays on the bottom and spare space remains above.
            y=section.bottom()-content+index*height+self.video_scroll.value()
        else:index=self.display_tracks("audio").index(track); y=section.top()+index*height-self.audio_scroll.value()
        rect=QRectF(0,y,self.viewport().width(),height)
        if self._frame_track_rects is not None:
            self._frame_track_rects[track]=rect
        return rect

    def track_at(self,pos):
        if not self.project or pos.y()<self.RULER_HEIGHT:return ""
        secs=self._sections()
        for name,sec in secs.items():
            if not sec.contains(pos):continue
            if name=="subtitle":return "subtitle_1" if self.has_subtitles() else ""
            tracks=self.display_tracks(name)
            if not tracks:return ""
            h=self._track_height(tracks[0])
            if h<=0:continue
            if name=="audio":
                idx=int((pos.y()-sec.top()+self.audio_scroll.value())//h)
                if 0<=idx<len(tracks):return tracks[idx]
            else:
                visual=list(reversed(tracks)); content=len(visual)*h
                idx=int((pos.y()-(sec.bottom()-content+self.video_scroll.value()))//h)
                if 0<=idx<len(visual):return visual[idx]
        return next((track for track in self.tracks() if self.track_rect(track).intersected(self.section_rect(track)).contains(pos)),"")

    def transition_rect(self, transition: Transition) -> QRectF:
        if not self.project or transition.track not in self.project.video_tracks:
            return QRectF()
        track_r = self.track_rect(transition.track)
        if track_r.isEmpty():
            return QRectF()
        x1 = self.x_for_time(transition.start)
        x2 = self.x_for_time(transition.start + transition.duration)
        return QRectF(x1, track_r.top() + 2, max(8.0, x2 - x1), track_r.height() - 4)

    def transition_at(self, pos: QPointF) -> tuple[Transition | None, str]:
        """Return (transition, hit_part) where hit_part is 'left_handle', 'right_handle', 'body', or ''."""
        if not self.project:
            return None, ""
        track = self.track_at(pos)
        if not track or track not in self.project.video_tracks:
            return None, ""
        for trans in reversed(self.project.transitions_for_track(track)):
            r = self.transition_rect(trans)
            if r.contains(pos):
                if abs(pos.x() - r.left()) <= 7:
                    return trans, "left_handle"
                elif abs(pos.x() - r.right()) <= 7:
                    return trans, "right_handle"
                return trans, "body"
        return None, ""

    def transition_target(self, name: str, pos: QPointF):
        if not self.project or self.read_only or pos.x() < self.LABEL_WIDTH:
            return None
        track = self.track_at(pos)
        if not track or track not in self.project.video_tracks:
            return None
        if self.project.track_states.get(track, {}).get("locked", False):
            return None

        track_items = sorted(
            [i for i in self.project.timeline if i.track == track and not getattr(i, "_drag_ghost", False)],
            key=lambda i: i.start
        )
        if not track_items:
            return None

        cursor_t = self.time_for_x(pos.x())
        snap_thresh_sec = 28.0 / max(1.0, self.pixels_per_second)

        # 1. Edit cut between two touching/adjacent clips
        for idx in range(len(track_items) - 1):
            left = track_items[idx]
            right = track_items[idx + 1]
            cut_t = left.start + left.duration
            if abs(cut_t - right.start) <= 0.12 and abs(cursor_t - cut_t) <= snap_thresh_sec:
                return ("transition_cut", name, track, cut_t, left, right)

        # 2. Single clip start or end boundary
        for item in track_items:
            if abs(cursor_t - item.start) <= snap_thresh_sec:
                return ("transition_start", name, track, item.start, None, item)
            if abs(cursor_t - (item.start + item.duration)) <= snap_thresh_sec:
                return ("transition_end", name, track, item.start + item.duration, item, None)

        # 3. If hovering inside clip, snap to nearest boundary
        hit = next((i for i in track_items if i.start <= cursor_t <= i.start + i.duration), None)
        if hit:
            d_start = abs(cursor_t - hit.start)
            d_end = abs(cursor_t - (hit.start + hit.duration))
            if d_start < d_end:
                return ("transition_start", name, track, hit.start, None, hit)
            else:
                return ("transition_end", name, track, hit.start + hit.duration, hit, None)

        return None

    def _fast_hit_at(self,pos):
        if not self.project or pos.y()<self.RULER_HEIGHT:return None,None
        secs=self._sections()
        sub_sec=secs.get("subtitle")
        if sub_sec and sub_sec.contains(pos) and self.has_subtitles():
            t=self.time_for_x(pos.x())
            margin=15.0/max(1.0,self.pixels_per_second)
            cap=next((c for c in reversed(self.project.captions) if (c.start-margin<=t<=c.end+margin) and self.visible_caption_rect(c).contains(pos)),None)
            return None,cap
        track=self.track_at(pos)
        if not track:return None,None
        t=self.time_for_x(pos.x())
        margin=15.0/max(1.0,self.pixels_per_second)
        hit=next((i for i in reversed(self.project.timeline) if i.track==track and (i.start-margin<=t<=i.start+i.duration+margin) and self.visible_item_rect(i).contains(pos)),None)
        return hit,None

    def _audio_top(self):return self.track_rect(self.project.audio_tracks[0]).top() if self.project.audio_tracks else 0

    def _subtitle_divider_rect(self):
        if not self.project.captions:return QRectF()
        bottom=self._sections()["subtitle"].bottom(); return QRectF(0,bottom,self.viewport().width(),self.AV_SEPARATOR)

    def _av_divider_rect(self):
        if not self.project.video_tracks or not self.project.audio_tracks:return QRectF()
        top=self._sections()["audio"].top()-self.AV_SEPARATOR; return QRectF(0,top,self.viewport().width(),self.AV_SEPARATOR)

    def _divider_at(self,pos):
        if self._subtitle_divider_rect().contains(pos):return "subtitle"
        if self._av_divider_rect().contains(pos):return "av"
        return ""

    @staticmethod
    def _razor_cursor():
        pix=QPixmap(28,28); pix.fill(Qt.transparent); painter=QPainter(pix)
        painter.drawPixmap(1,1,lucide_icon("razor","#111318",26).pixmap(26,26)); painter.drawPixmap(0,0,lucide_icon("razor","#ffffff",26).pixmap(26,26)); painter.end()
        return QCursor(pix,13,13)

    @staticmethod
    def _trim_cursor(direction="right"):
        cache_key = f"_cur_trim_{direction}"
        cur = getattr(TimelineWidget, cache_key, None)
        if cur is not None:return cur
        size = 32; pix = QPixmap(size, size); pix.fill(Qt.transparent)
        p = QPainter(pix); p.setRenderHint(QPainter.Antialiasing, True)
        bracket = QPainterPath(); arrow = QPainterPath(); mid_y = 16.0
        if direction == "right":
            bracket.moveTo(8.0, 6.5)
            bracket.lineTo(13.5, 6.5)
            bracket.lineTo(13.5, 25.5)
            bracket.lineTo(8.0, 25.5)
            ax, aw, ah = 17.5, 5.0, 3.5
            arrow.moveTo(ax, mid_y - ah); arrow.lineTo(ax + aw, mid_y); arrow.lineTo(ax, mid_y + ah); arrow.closeSubpath()
            hotspot = (14, 16)
        else:
            bracket.moveTo(24.0, 6.5)
            bracket.lineTo(18.5, 6.5)
            bracket.lineTo(18.5, 25.5)
            bracket.lineTo(24.0, 25.5)
            ax, aw, ah = 14.5, 5.0, 3.5
            arrow.moveTo(ax, mid_y - ah); arrow.lineTo(ax - aw, mid_y); arrow.lineTo(ax, mid_y + ah); arrow.closeSubpath()
            hotspot = (18, 16)
        black_pen = QPen(QColor(0, 0, 0, 255), 2.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(black_pen); p.setBrush(Qt.NoBrush)
        p.drawPath(bracket); p.strokePath(arrow, black_pen); p.fillPath(arrow, QBrush(QColor(0, 0, 0, 255)))
        white_pen = QPen(QColor(255, 255, 255, 255), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(white_pen)
        p.drawPath(bracket); p.strokePath(arrow, white_pen); p.fillPath(arrow, QBrush(QColor(255, 255, 255, 255)))
        p.end()
        cur = QCursor(pix, hotspot[0], hotspot[1])
        setattr(TimelineWidget, cache_key, cur)
        return cur

    @staticmethod
    def _roll_cursor():
        cur = getattr(TimelineWidget, "_cur_roll", None)
        if cur is not None:return cur
        size = 32; pix = QPixmap(size, size); pix.fill(Qt.transparent)
        p = QPainter(pix); p.setRenderHint(QPainter.Antialiasing, True)
        b_left = QPainterPath(); b_right = QPainterPath()
        b_left.moveTo(9.5, 7.5); b_left.lineTo(13.5, 7.5); b_left.lineTo(13.5, 24.5); b_left.lineTo(9.5, 24.5)
        b_right.moveTo(22.5, 7.5); b_right.lineTo(18.5, 7.5); b_right.lineTo(18.5, 24.5); b_right.lineTo(22.5, 24.5)
        arr_l = QPainterPath(); arr_r = QPainterPath()
        mid_y = 16.0
        arr_l.moveTo(6.0, mid_y - 3.5); arr_l.lineTo(1.5, mid_y); arr_l.lineTo(6.0, mid_y + 3.5); arr_l.closeSubpath()
        arr_r.moveTo(26.0, mid_y - 3.5); arr_r.lineTo(30.5, mid_y); arr_r.lineTo(26.0, mid_y + 3.5); arr_r.closeSubpath()
        black_pen = QPen(QColor(0, 0, 0, 255), 2.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(black_pen); p.setBrush(Qt.NoBrush)
        p.drawPath(b_left); p.drawPath(b_right)
        p.strokePath(arr_l, black_pen); p.fillPath(arr_l, QBrush(QColor(0, 0, 0, 255)))
        p.strokePath(arr_r, black_pen); p.fillPath(arr_r, QBrush(QColor(0, 0, 0, 255)))
        white_pen = QPen(QColor(255, 255, 255, 255), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(white_pen)
        p.drawPath(b_left); p.drawPath(b_right)
        p.strokePath(arr_l, white_pen); p.fillPath(arr_l, QBrush(QColor(255, 255, 255, 255)))
        p.strokePath(arr_r, white_pen); p.fillPath(arr_r, QBrush(QColor(255, 255, 255, 255)))
        p.end()
        cur = QCursor(pix, 16, 16)
        setattr(TimelineWidget, "_cur_roll", cur)
        return cur

    def snap_edge(self,moment,exclude_items=(),exclude_captions=()):
        self.snap_guide=None
        if not self.property("snapping"):return moment
        points=[0.,self.project.playhead]+[edge for i in self.project.timeline if i.id not in exclude_items for edge in (i.start,i.start+i.duration)]+[edge for c in self.project.captions if c.id not in exclude_captions for edge in (c.start,c.end)]
        nearest=min(points,key=lambda point:abs(point-moment))
        if abs(nearest-moment)<=10/self.pixels_per_second:self.snap_guide=nearest; return nearest
        return moment

    def _blade_time(self,hit,x):
        end=hit.end if hasattr(hit,'end') else hit.start+hit.duration
        value=max(hit.start,min(end,self.time_for_x(x))); fps=max(1,self.project.settings.fps)
        self.snap_guide=None
        if self.property("snapping"):
            playhead=self.project.playhead
            # Wider acquisition at the playhead; hold until the pointer moves
            # deliberately away. Media and subtitle blades share this path.
            distance=18 if getattr(self,'_blade_snap',None)==playhead else 12
            if hit.start<playhead<end and abs(value-playhead)*self.pixels_per_second<=distance:
                self._blade_snap=playhead; self.snap_guide=playhead; return playhead
            points=[edge for item in self.project.timeline for edge in (item.start,item.start+item.duration)]+[edge for cap in self.project.captions for edge in (cap.start,cap.end)]
            if points:
                nearest=min(points,key=lambda edge:abs(edge-value))
                if hit.start<nearest<end and abs(nearest-value)<=8/self.pixels_per_second:value=nearest; self.snap_guide=nearest
        self._blade_snap=None
        return max(hit.start,min(end,round(value*fps)/fps))

    def item_rect(self,item,track_rect=None):
        tr=self.track_rect(item.track) if track_rect is None else track_rect
        return QRectF(self.x_for_time(item.start),tr.y()+3,max(5,item.duration*self.pixels_per_second),tr.height()-6)

    def caption_rect(self,caption,track_rect=None):
        tr=self.track_rect("subtitle_1") if track_rect is None else track_rect
        return QRectF(self.x_for_time(caption.start),tr.y()+7,max(5,(caption.end-caption.start)*self.pixels_per_second),tr.height()-14)

    def header_controls(self,track):
        r=self.track_rect(track); y=r.top()+26+(r.height()-26-18)/2
        return QRectF(52,y,22,18),QRectF(82,y,22,18)

    def set_theme(self, palette: dict):
        self._theme_palette = palette
        self.viewport().update()

    def _palette(self):
        if not getattr(self, "_theme_palette", None):
            from .theme import get_active_theme_palette
            self._theme_palette = get_active_theme_palette()
        return self._theme_palette

    def paint_track_header(self,p,track):
        pal = self._palette()
        r=self.track_rect(track); audio=self._section_name(track)=="audio"; state=self._state(track)
        p.save(); p.setClipRect(self.section_rect(track),Qt.IntersectClip)
        p.fillRect(QRectF(0,r.y(),self.LABEL_WIDTH,r.height()),QColor(pal.get("timeline_header_bg", "#2b2c31")))
        p.fillRect(QRectF(0,r.y(),3,r.height()),QColor("#4d9b72" if audio else "#5f9cc9"))
        p.setPen(QPen(QColor(pal.get("border", "#111215")),1))
        p.drawRect(QRectF(4,r.y(),self.LABEL_WIDTH-5,r.height()))
        p.drawLine(QPointF(47,r.top()),QPointF(47,r.bottom()))
        if r.height()>=38:p.drawLine(QPointF(4,r.top()+26),QPointF(self.LABEL_WIDTH-1,r.top()+26))
        code="ST1" if track=="subtitle_1" else ("A" if audio else "V")+str(self.display_tracks("audio" if audio else "video").index(track)+1)
        p.setFont(QFont("Segoe UI",9)); p.setPen(QColor(pal.get("timeline_text", "#eff0f2")))
        p.drawText(QRectF(6,r.top()+2,39,22),Qt.AlignCenter,code)
        p.drawText(QRectF(54,r.top()+2,self.LABEL_WIDTH-57,22),Qt.AlignVCenter,"Subtitle" if track=="subtitle_1" else (self.incoming_plan or self.project).track_names.get(track,track))
        if r.height()>=38:
            lock,toggle=self.header_controls(track)
            p.drawPixmap(round(lock.x()+4),round(lock.y()+2),lucide_icon("lock" if state.get("locked") else "lock-open","#f08075" if state.get("locked") else pal.get("icon_sub_color","#9a9ca6"),14).pixmap(14,14))
            if audio:
                p.setBrush(QColor("#a94d46" if state.get("muted") else pal.get("bg_input", "#41434a"))); p.setPen(Qt.NoPen); p.drawRoundedRect(toggle,3,3)
                p.setPen(QColor("#ffffff" if state.get("muted") else pal.get("timeline_text", "#bfc1c8"))); p.drawText(toggle,Qt.AlignCenter,"M")
            else:p.drawPixmap(round(toggle.x()+4),round(toggle.y()+2),lucide_icon("eye" if state.get("visible",True) else "eye-off",pal.get("icon_sub_color","#9a9ca6"),14).pixmap(14,14))
        p.restore()

    def visible_item_rect(self,item):return self.item_rect(item).intersected(self.section_rect(item.track))
    def visible_caption_rect(self,caption):return self.caption_rect(caption).intersected(self._sections()["subtitle"])

    def selected_items(self):
        return [i for i in self.project.timeline if i.id in self.selected_ids]

    def expanded(self,ids):
        result=set(ids)
        if self.linked_selection:
            # Expand whole link groups in two linear passes, not a full timeline
            # scan for every selected clip during marquee/copy/delete.
            keys={item.group_id if item.link_id is None else item.link_id for item in self.project.timeline if item.id in result}
            keys.discard(""); keys.discard(None)
            for item in self.project.timeline:
                if (item.group_id if item.link_id is None else item.link_id) in keys:result.add(item.id)
        return result

    def select_ids(self,ids,primary="",preserve_other=False):
        self.selected_ids=set(ids)
        if not preserve_other:self.selected_caption=""; self.selected_caption_ids=set()
        self.selected_id=primary if primary in self.selected_ids else next(iter(self.selected_ids),"")
        item=self.project.item_by_id(self.selected_id)
        if item:self.selected_track=item.track
        self.selectionChanged.emit(list(self.selected_ids)); self.itemSelected.emit(self.selected_id); self.viewport().update()

    def select_captions(self,ids,primary="",preserve_other=False):
        self.selected_caption_ids=set(ids); self.selected_caption=primary if primary in self.selected_caption_ids else next(iter(self.selected_caption_ids),"")
        if not preserve_other:self.selected_ids=set(); self.selected_id=""
        if self.selected_caption:self.captionSelected.emit(self.selected_caption)
        elif not self.selected_ids:self.captionSelected.emit("")
        self.viewport().update()

    def _timecode(self,value):
        fps=max(1,round(self.project.settings.fps)); frames=max(0,round(value*fps)); seconds,frame=divmod(frames,fps); minutes,second=divmod(seconds,60); hour,minute=divmod(minutes,60)
        return f"{hour:02d}:{minute:02d}:{second:02d}:{frame:02d}"

    def paintEvent(self,event):
        pal = self._palette()
        viewport=self.viewport(); scale=viewport.devicePixelRatioF()
        size=viewport.size()*scale
        cursor_only=(self._timeline_backing is not None and self._timeline_backing.size()==size
                     and self._timeline_backing.devicePixelRatioF()==scale
                     and not (self._playhead_damage|self._meter_damage).isEmpty()
                     and event.region().subtracted(self._playhead_damage|self._meter_damage).isEmpty()
                     and self.drag_mode in {'','marquee','playhead'} and self.snap_guide is None)
        self._playhead_damage=self._playhead_damage.subtracted(event.region())
        self._meter_damage=self._meter_damage.subtracted(event.region())
        if cursor_only:
            p=QPainter(viewport); p.drawPixmap(0,0,self._timeline_backing)
            self._paint_clock(p,pal); self._paint_selection_overlay(p); self._paint_audio_levels(p); return
        # Keep the static content separate from the clock/cursor. Any ordinary
        # update (edits, hover, selection, scroll, waveforms, theme, resize) rebuilds
        # it. Only explicit, narrow update_playhead damage may reuse this raster.
        backing=QPixmap(size); backing.setDevicePixelRatio(scale)
        p=QPainter(backing); p.setRenderHint(QPainter.Antialiasing); p.fillRect(viewport.rect(),QColor(pal.get("timeline_bg", "#191a1e"))); p.setFont(QFont("Segoe UI",9))
        if not self.project:
            p.end(); screen=QPainter(viewport); screen.drawPixmap(0,0,backing); return
        self._frame_sec_rects=self._sections()
        self._frame_track_rects={t:self.track_rect(t) for t in self.tracks()}
        link_counts={}
        for candidate in self.project.timeline:
            k=candidate.group_id if candidate.link_id is None else candidate.link_id
            if k:link_counts[k]=link_counts.get(k,0)+1
        try:
            w=self.viewport().width(); h=self.viewport().height()
            dirty=QRegion(viewport.rect())
            p.save(); p.setClipRect(QRectF(0,self.RULER_HEIGHT,w,h-self.RULER_HEIGHT))
            for track in self.tracks():
                r=self.track_rect(track); audio=self._section_name(track)=="audio"; subtitle=track=="subtitle_1"
                p.save(); p.setClipRect(self.section_rect(track),Qt.IntersectClip)
                track_col = pal.get("timeline_track_bg", "#202126")
                p.fillRect(r,QColor(track_col)); p.fillRect(QRectF(0,r.y(),self.LABEL_WIDTH,r.height()),QColor(pal.get("timeline_header_bg", "#2b2c31")))
                p.setPen(QColor(pal.get("border", "#111215"))); p.drawLine(0,round(r.bottom()),w,round(r.bottom()))
                p.restore()
            for divider in (self._subtitle_divider_rect(),self._av_divider_rect()):
                if divider.isEmpty():continue
                p.fillRect(divider,QColor(pal.get("timeline_divider", "#0b0c0f"))); p.setPen(QPen(QColor(pal.get("border_subtle", "#464950")),1)); p.drawLine(0,round(divider.center().y()),w,round(divider.center().y()))
            # Replace the broad track-header clip with a hard media-area boundary.
            # Clip names, thumbnails, fades and captions alike so horizontal zoom or
            # scrolling can never paint over the fixed track controls.
            p.setClipRect(QRectF(self.LABEL_WIDTH+1,self.RULER_HEIGHT,max(0,w-self.LABEL_WIDTH-1),h-self.RULER_HEIGHT),Qt.ReplaceClip)
            painted=self.project.timeline
            damage=dirty.intersected(QRegion(QRect(self.LABEL_WIDTH,self.RULER_HEIGHT,w-self.LABEL_WIDTH,h-self.RULER_HEIGHT))).boundingRect()
            visible_start=self.time_for_x(max(self.LABEL_WIDTH-6,damage.left()-6)); visible_end=self.time_for_x(min(w+6,damage.right()+6))
            if self.drag_mode in {'trim_left','trim_right','retime_left','retime_right'}:
                # Preview the same overwrite that release commits, without changing
                # neighbours until the gesture is accepted (Escape still restores).
                # overwrite creates new neighbour fragments; untouched/placed clips
                # can be shared. Avoid deep-copying the entire project every paint.
                staged=copy.copy(self.project); staged.timeline=list(self.project.timeline); staged.overwrite(self.snapshots)
                painted=sorted(staged.timeline,key=lambda i:i.id in self.snapshots)
            for item in painted+self.move_preview+self.incoming_preview:
                if item.start+item.duration<visible_start or item.start>visible_end:continue
                ghost=getattr(item,"_drag_ghost",False)
                if self.move_preview and item.id in self.snapshots and not ghost and not self.alt_drag:continue
                r=self.item_rect(item)
                if not dirty.intersects(r.toAlignedRect()):continue
                item_clip=self.section_rect(item.track).intersected(QRectF(self.LABEL_WIDTH+1,self.RULER_HEIGHT,max(0,w-self.LABEL_WIDTH-1),h-self.RULER_HEIGHT))
                if not r.intersects(item_clip):continue
                p.save(); p.setClipRect(item_clip,Qt.IntersectClip)
                shape=QPainterPath(); shape.addRoundedRect(r,3,3); p.setClipPath(shape,Qt.IntersectClip)
                audio=self._section_name(item.track)=="audio"; media=(self.incoming_plan if getattr(item,"_incoming",False) else self.project).media_by_id(item.media_id)
                from .missing_media import unavailable,label,offline_icon
                offline=unavailable(media,item)
                base=QColor("#326951" if audio else "#6d4a8e" if item.role=="graphic" else "#b8aa7c" if item.role=="title" else "#3c6c90"); selected=item.id in self.selected_ids and not self.read_only and not ghost
                if offline:base=QColor('#510b0e')
                p.fillRect(r,base.lighter(112) if selected else base)
                p.setPen(QPen(QColor("#08090b"),1)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(r.adjusted(.5,.5,-.5,-.5),3,3)
                p.save(); p.setClipRect(r.adjusted(2,2,-2,-2),Qt.IntersectClip)
                text_r=r.adjusted(6,0,-5,0)
                if offline:
                    if audio:
                        p.setPen(QPen(QColor('#dc6057'),1)); p.drawLine(QPointF(r.left()+4,r.center().y()),QPointF(r.right()-4,r.center().y()))
                    elif r.height()>36:
                        if not hasattr(self,'_offline_icon'):self._offline_icon=offline_icon().pixmap(44,26)
                        left=max(r.left()+4,self.LABEL_WIDTH+4)
                        for x in range(round(left),round(min(r.right(),w)),62):p.drawPixmap(x,round(r.top()+3),self._offline_icon)
                    text_r=QRectF(r.x()+6,r.bottom()-21,r.width()-12,20)
                elif not audio and r.width()>=28 and r.height()>=52 and media and (media.thumbnail or media.kind=="image"):
                    key=("rgba:"+media.path) if media.kind=="image" else media.thumbnail
                    if key not in self.thumbnails:
                        if media.kind=="image":
                            # Old projects may still point at an alpha-flattened JPEG.
                            from PySide6.QtGui import QImageReader
                            from PySide6.QtCore import QSize
                            reader=QImageReader(media.path); reader.setAutoTransform(True)
                            if reader.size().isValid():reader.setScaledSize(reader.size().scaled(QSize(320,180),Qt.KeepAspectRatio))
                            self.thumbnails[key]=QPixmap.fromImage(reader.read())
                        else:self.thumbnails[key]=QPixmap(media.thumbnail)
                    pix=self.thumbnails[key]; strip=QRectF(r.x()+2,r.y()+2,r.width()-4,r.height()-23)
                    p.save(); thumb_shape=QPainterPath(); thumb_shape.addRoundedRect(strip,2.5,2.5); p.setClipPath(thumb_shape,Qt.IntersectClip)
                    p.fillRect(strip,QColor("#08090b"))
                    if not pix.isNull():
                        th_h=round(strip.height()); scaled_key=(key,th_h)
                        scaled=self._scaled_thumbnails.get(scaled_key)
                        if scaled is None:
                            tw=max(1,round(strip.height()*pix.width()/pix.height()))
                            scaled=pix.scaled(tw,th_h,Qt.KeepAspectRatio,Qt.SmoothTransformation)
                            self._scaled_thumbnails[scaled_key]=scaled
                        tw=scaled.width(); begin=max(0,int((self.LABEL_WIDTH-strip.left())//tw))
                        for n in range(begin,begin+math.ceil(min(r.width(),w)/tw)+2):p.drawPixmap(round(strip.left()+n*tw),round(strip.top()),scaled)
                    p.restore(); p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#050506'),1)); p.drawRoundedRect(strip.adjusted(.5,.5,-.5,-.5),2.5,2.5)
                    text_r=QRectF(r.x()+6,r.bottom()-21,r.width()-12,20)
                elif audio:
                    samples=self.waveforms.get(item.media_id,[])
                    if samples and media:
                        from .waveforms import paint_waveform
                        damage=dirty.intersected(QRegion(r.toAlignedRect())).boundingRect()
                        wf_key=(item.id,int(r.width()),int(r.height()),round(item.in_point,3),round(item.speed,3),round(item.gain_db,2),round(item.fade_in,3),round(item.fade_out,3))
                        cached_wf=self._waveform_pixmaps.get(wf_key)
                        if cached_wf is None and 2<=r.width()<=4000 and r.height()>=2:
                            pix=QPixmap(max(1,int(r.width())),max(1,int(r.height())))
                            pix.fill(Qt.transparent)
                            wf_p=QPainter(pix)
                            wf_p.setRenderHint(QPainter.Antialiasing)
                            local_r=QRectF(0,0,r.width(),r.height())
                            paint_waveform(wf_p,local_r,samples,media,item,self.pixels_per_second,0,r.width())
                            wf_p.end()
                            if len(self._waveform_pixmaps)>120:self._waveform_pixmaps.clear()
                            self._waveform_pixmaps[wf_key]=pix
                            cached_wf=pix
                        if cached_wf is not None:
                            p.drawPixmap(round(r.left()),round(r.top()),cached_wf)
                        else:
                            paint_waveform(p,r,samples,media,item,self.pixels_per_second,max(self.LABEL_WIDTH,damage.left()),min(w,damage.right()+1))
                    elif media and r.width()>140 and (media.id in self.waveform_pending or media.id in self.waveform_failures):
                        p.setPen(QColor('#bdcfc4')); p.drawText(r.adjusted(6,2,-6,-20),Qt.AlignVCenter,'Loading waveform…' if media.id in self.waveform_pending else 'Waveform unavailable')
                    text_r=QRectF(r.x()+6,r.bottom()-20,r.width()-12,19)
                if r.width()>=26 and (audio or item.id==self.hover_id or item.id in self.selected_ids or item.fade_in or item.fade_out):
                    p.setPen(QPen(QColor("#faf0c2"),1))
                    fi=min(r.width(),item.fade_in*self.pixels_per_second); fo=min(r.width(),item.fade_out*self.pixels_per_second)
                    p.save(); p.setPen(Qt.NoPen); p.setBrush(QColor(0,0,0,125))
                    if fi>0:
                        shade=QPainterPath(); shade.moveTo(r.topLeft()); shade.lineTo(r.bottomLeft()); shade.lineTo(QPointF(r.left()+fi,r.top()+3)); shade.closeSubpath(); p.drawPath(shade)
                    if fo>0:
                        shade=QPainterPath(); shade.moveTo(QPointF(r.right()-fo,r.top()+3)); shade.lineTo(r.topRight()); shade.lineTo(r.bottomRight()); shade.closeSubpath(); p.drawPath(shade)
                    p.restore()
                    p.drawLine(r.bottomLeft(),QPointF(r.left()+fi,r.top()+3)); p.drawLine(QPointF(r.right()-fo,r.top()+3),r.bottomRight())
                    for mode,x in (("fade_in",r.left()+max(5,fi)),("fade_out",r.right()-max(5,fo))):
                        if r.width()<34:continue
                        active=self.drag_mode==mode and item.id==self.selected_id
                        p.fillRect(QRectF(x-4,r.top()+1,8,8),QColor("#ef6657" if active else "#f3ead1"))
                k=item.group_id if item.link_id is None else item.link_id
                is_linked=bool(k and link_counts.get(k,0)>1)
                if text_r.width()>=44:
                    name=(f"Graphic · {item.graphic_type or 'Shape'}" if item.role=="graphic" else getattr(item,"title_text","") if item.role=="title" else (media.name if media else "Offline"))
                    if offline:name=label(media,item)
                    reserve=22 if is_linked and r.width()>=110 else 0
                    shown=QFontMetrics(p.font()).elidedText(name,Qt.ElideRight,max(0,round(text_r.width()-reserve)))
                    p.setPen(QColor("#ffffff")); p.drawText(text_r.adjusted(0,0,-reserve,0),Qt.AlignVCenter|Qt.TextSingleLine,shown)
                if is_linked and r.width()>=110:p.drawPixmap(round(r.right()-20),round(r.bottom()-19),lucide_icon("link","@on_dark",13).pixmap(13,13))
                if item.id in self.retime_ids and not self.read_only:
                    p.fillRect(QRectF(r.x(),r.top(),r.width(),17),QColor("#244157")); p.setPen(QColor("#f4f4f4")); p.drawText(QRectF(r.x()+5,r.top(),r.width()-10,17),Qt.AlignVCenter,"×  Speed Change  "+(media.name if media else "Offline"))
                    p.fillRect(QRectF(r.x(),r.bottom()-21,r.width(),21),QColor("#244157")); p.drawText(QRectF(r.x()+5,r.bottom()-21,r.width()-10,21),Qt.AlignCenter,f"{item.speed*100:g}%  ▾")
                if item.id==self.selected_id and self.drag_mode in {"fade_in","fade_out"}:
                    tag=QRectF(max(r.left(),min(r.right()-85,w-90)),r.bottom()-23,85,21); p.fillRect(tag,QColor("#111318")); p.setPen(QColor("white")); p.drawText(tag,Qt.AlignCenter,f"{getattr(item,self.drag_mode):.2f} s")
                p.restore()
                p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#050506'),1)); p.drawRoundedRect(r.adjusted(.5,.5,-.5,-.5),3,3)
                if offline:p.setPen(QPen(QColor('#d9473d'),1)); p.drawRoundedRect(r.adjusted(.5,.5,-.5,-.5),3,3)
                if selected:
                    # Paint selection last and outside the clip-content mask so the
                    # full Resolve-style red perimeter remains visible over thumbs,
                    # waveforms, titles, fades and linked-selection decoration.
                    p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor("#f05a50"),2)); p.drawRoundedRect(r.adjusted(1,1,-1,-1),3,3)
                # Visual FX Duration Clamper Overlay along the top edge of the media clip (Image 3 mockup)
                vfx_effects = [e for e in getattr(item, "effects", []) if e.get("category") == "Visual FX" and e.get("enabled", True)]
                is_flashing = (self._vfx_flash_item_id == item.id)
                for eff in vfx_effects:
                    show_overlay = bool(eff.get("show_timeline_overlay", True))
                    if not (is_flashing or (selected and show_overlay)):
                        continue
                    timing_mode = eff.get("timing_mode", "clip_start")
                    eff_dur = float(eff.get("duration", 1.0))
                    clip_dur = max(0.01, getattr(item, "duration", 1.0))
                    dur = clip_dur if timing_mode == "entire_clip" else min(clip_dur, max(0.05, eff_dur))
                    if timing_mode == "clip_end":
                        start_off = max(0.0, clip_dur - dur)
                    elif timing_mode == "entire_clip":
                        start_off = 0.0
                    else:
                        start_off = max(0.0, min(clip_dur - 0.05, float(eff.get("start_time", 0.0))))

                    t_start = item.start + start_off
                    t_end = min(item.start + clip_dur, t_start + dur)
                    x1 = max(r.left(), min(r.right(), self.x_for_time(t_start)))
                    x2 = max(r.left(), min(r.right(), self.x_for_time(t_end)))
                    w_bar = max(0.0, x2 - x1)
                    if w_bar < 2.0:
                        continue

                    bar_y = r.top() + 1.0
                    bar_h = 4.0

                    from .visual_fx import ZOOM_IN_EFFECTS, SUBSECTION_BY_EFFECT
                    name = eff.get("name", "")
                    sub = eff.get("subsection", SUBSECTION_BY_EFFECT.get(name, "Zooms"))
                    has_return = bool(eff.get("zoom_return", False)) and sub == "Zooms" and name in ZOOM_IN_EFFECTS

                    # Luminous flash glow if recently adjusted in inspector
                    if is_flashing:
                        p.setPen(QPen(QColor(80, 223, 116, 180), 2.5))
                        p.setBrush(Qt.NoBrush)
                        p.drawRoundedRect(QRectF(x1 - 1, bar_y - 1, w_bar + 2, bar_h + 2), 2, 2)

                    if has_return and w_bar > 12:
                        hold_s = max(0.0, float(eff.get("zoom_hold_duration", 0.15)))
                        hold_s = min(hold_s, max(0.0, dur - 0.02))
                        r_avail = max(0.02, dur - hold_s)
                        att_req = eff.get("zoom_attack_duration")
                        att_s = max(0.01, min(r_avail - 0.01, float(att_req))) if att_req is not None else r_avail / 2.0

                        xp1 = max(r.left(), min(r.right(), self.x_for_time(t_start + att_s)))
                        xp2 = max(r.left(), min(r.right(), self.x_for_time(t_start + att_s + hold_s)))

                        # Phase 1: Attack (Blue)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor("#3d8cff"))
                        p.drawRoundedRect(QRectF(x1, bar_y, max(1.0, xp1 - x1), bar_h), 1.5, 1.5)

                        # Phase 2: Peak Hold (Vibrant Green)
                        p.setBrush(QColor("#50df74"))
                        p.drawRoundedRect(QRectF(xp1, bar_y - 0.5, max(2.0, xp2 - xp1), bar_h + 1.0), 2, 2)

                        # Phase 3: Ease Out (Blue)
                        p.setBrush(QColor("#3d8cff"))
                        p.drawRoundedRect(QRectF(xp2, bar_y, max(1.0, x2 - xp2), bar_h), 1.5, 1.5)

                        # Circular pips at ends
                        p.setPen(QPen(QColor("#ffffff"), 1.0))
                        p.setBrush(QColor("#3d8cff"))
                        p.drawEllipse(QPointF(x1, bar_y + bar_h / 2.0), 2.5, 2.5)
                        p.drawEllipse(QPointF(x2, bar_y + bar_h / 2.0), 2.5, 2.5)
                    else:
                        # Standard vibrant green clamper bar (Image 3 mockup)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor("#50df74"))
                        p.drawRoundedRect(QRectF(x1, bar_y, w_bar, bar_h), 1.5, 1.5)

                        # Circular pips at ends (matching user's green circles in image 3)
                        p.setPen(QPen(QColor("#ffffff"), 1.0))
                        p.setBrush(QColor("#50df74"))
                        p.drawEllipse(QPointF(x1, bar_y + bar_h / 2.0), 2.8, 2.8)
                        p.drawEllipse(QPointF(x2, bar_y + bar_h / 2.0), 2.8, 2.8)
                if item.effects and r.width()>70:
                    badge=QRectF(max(r.left()+5,self.LABEL_WIDTH+5),r.top()+12,22,15)
                    p.fillRect(badge,QColor("#202833")); p.setPen(QColor("#afc6e1")); p.setFont(QFont("Segoe UI",8,QFont.DemiBold)); p.drawText(badge,Qt.AlignCenter,"fx"); p.setFont(QFont("Segoe UI",9))
                if self.effect_hover and self.effect_hover[1]==item.id:
                    p.fillRect(r,QColor(172,181,194,115)); p.setPen(QPen(QColor("#dfe8f5"),2)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(r.adjusted(1,1,-1,-1),3,3)
                    label=r.intersected(item_clip).adjusted(5,3,-5,-3)
                    if label.width()>60:
                        p.fillRect(QRectF(label.left(),label.center().y()-10,label.width(),20),QColor(28,33,40,225)); p.setPen(QColor("white"))
                        p.drawText(label,Qt.AlignCenter,QFontMetrics(p.font()).elidedText("+ "+self.effect_hover[0],Qt.ElideRight,int(label.width())))
                if ghost:
                    p.fillRect(r,QColor(173,180,192,130)); p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor("#e0e5ed"),1,Qt.DashLine)); p.drawRoundedRect(r.adjusted(1,1,-1,-1),3,3)
                p.restore()
            for caption in self.caption_painted if self.caption_painted is not None else self.project.captions:
                if caption.end<visible_start or caption.start>visible_end:continue
                r=self.caption_rect(caption)
                if not dirty.intersects(r.toAlignedRect()):continue
                p.save(); p.setClipRect(self._sections()["subtitle"],Qt.IntersectClip)
                shape=QPainterPath(); shape.addRoundedRect(r,3,3); p.setClipPath(shape,Qt.IntersectClip)
                base=QColor("#b8aa7c"); p.fillRect(r,base.lighter(112) if caption.id in self.selected_caption_ids else base); p.setPen(QPen(QColor("#08090b"),1)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(r.adjusted(.5,.5,-.5,-.5),3,3)
                if r.width()>=26:p.setPen(QColor("#151617")); p.drawText(r.adjusted(5,0,-5,0),Qt.AlignVCenter|Qt.TextSingleLine,QFontMetrics(p.font()).elidedText(caption.text,Qt.ElideRight,max(0,round(r.width()-10))))
                if (caption.id in self.selected_caption_ids or any(c.id==caption.id for c in self.caption_preview)) and not self.read_only:p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor("#ef5b50"),2)); p.drawRoundedRect(r.adjusted(1,1,-1,-1),3,3)
                p.restore()
            if self.tool=="blade" and self.blade_hover_id and self.blade_hover_time is not None:
                ids=self.expanded({self.blade_hover_id}) if self.linked_selection else {self.blade_hover_id}
                x=self.x_for_time(self.blade_hover_time); p.setPen(QPen(QColor("#ff4f55"),2))
                for item in self.project.timeline:
                    if item.id in ids and item.start<self.blade_hover_time<item.start+item.duration:
                        rect=self.item_rect(item).intersected(self.section_rect(item.track))
                        if not rect.isEmpty():p.drawLine(round(x),round(rect.top()),round(x),round(rect.bottom()))
            if self.tool=="blade" and self.blade_hover_caption and self.blade_hover_time is not None:
                caption=next((candidate for candidate in self.project.captions if candidate.id==self.blade_hover_caption),None)
                if caption:
                    rect=self.caption_rect(caption).intersected(self.section_rect("subtitle_1")); x=self.x_for_time(self.blade_hover_time); p.setPen(QPen(QColor("#ff4f55"),2))
                    if not rect.isEmpty():p.drawLine(round(x),round(rect.top()),round(x),round(rect.bottom()))
            if self.effect_hover and self.effect_hover[2]:
                name,_,track,start=self.effect_hover; rect=self.track_rect(track); rect.setLeft(self.x_for_time(start)); rect.setWidth(5*self.pixels_per_second)
                p.save(); p.setClipRect(self.section_rect(track),Qt.IntersectClip); p.fillRect(rect,QColor(196,181,136,90)); p.setPen(QPen(QColor("#dfd4b2"),2,Qt.DashLine)); p.setBrush(Qt.NoBrush); p.drawRect(rect.adjusted(2,2,-2,-2)); p.drawText(rect.adjusted(8,0,-4,0),Qt.AlignVCenter,"+ "+name); p.restore()
            # Paint DaVinci Resolve-style video transition clampers
            for trans in self.project.transitions:
                if trans.track not in self.project.video_tracks:continue
                if not self.project.track_states.get(trans.track,{}).get("visible",True):continue
                if trans.start+trans.duration<visible_start or trans.start>visible_end:continue
                r_trans=self.transition_rect(trans)
                if r_trans.isEmpty() or not dirty.intersects(r_trans.toAlignedRect()):continue
                item_clip=self.section_rect(trans.track).intersected(QRectF(self.LABEL_WIDTH+1,self.RULER_HEIGHT,max(0,w-self.LABEL_WIDTH-1),h-self.RULER_HEIGHT))
                if not r_trans.intersects(item_clip):continue
                p.save(); p.setClipRect(item_clip,Qt.IntersectClip)
                is_selected=(trans.id==self.selected_transition_id)
                # Frosted glass translucent white clamper box
                clamper_bg=QColor(255,255,255,68 if is_selected else 44)
                p.fillRect(r_trans,clamper_bg)
                # Clamper border
                p.setBrush(Qt.NoBrush)
                if is_selected:
                    p.setPen(QPen(QColor("#f05a50"),2.0))
                    p.drawRect(r_trans.adjusted(.5,.5,-.5,-.5))
                else:
                    p.setPen(QPen(QColor(255,255,255,140),1.0))
                    p.drawRect(r_trans.adjusted(.5,.5,-.5,-.5))
                # Left and right vertical grip handles
                handle_w=min(5.0,max(2.0,r_trans.width()/4.0))
                p.fillRect(QRectF(r_trans.left(),r_trans.top()+1,handle_w,r_trans.height()-2),QColor(255,255,255,190 if is_selected else 140))
                p.fillRect(QRectF(r_trans.right()-handle_w,r_trans.top()+1,handle_w,r_trans.height()-2),QColor(255,255,255,190 if is_selected else 140))
                # Center cut indicator line
                if trans.alignment=="center":
                    cut_x=self.x_for_time(trans.start+trans.duration/2.0)
                    p.setPen(QPen(QColor(255,255,255,160),1.0,Qt.DashLine))
                    p.drawLine(round(cut_x),round(r_trans.top()),round(cut_x),round(r_trans.bottom()))
                # Centered icon and transition name
                if r_trans.width()>=24:
                    icon_name=TRANSITION_ICONS.get(trans.name,"droplet")
                    icon_pix=lucide_icon(icon_name,"@on_dark",13).pixmap(13,13)
                    if r_trans.width()>=82:
                        badge_w=min(r_trans.width()-14,136.0)
                        badge_rect=QRectF(r_trans.center().x()-badge_w/2.0,r_trans.center().y()-10,badge_w,20)
                        p.fillRect(badge_rect,QColor(15,17,23,205))
                        p.setPen(QPen(QColor(255,255,255,70),1))
                        p.setBrush(Qt.NoBrush)
                        p.drawRoundedRect(badge_rect,2,2)
                        p.drawPixmap(round(badge_rect.left()+4),round(badge_rect.center().y()-6),icon_pix)
                        p.setPen(QColor("#ffffff"))
                        font=p.font(); font.setPointSize(8); font.setBold(True); p.setFont(font)
                        p.drawText(badge_rect.adjusted(22,0,-4,0),Qt.AlignVCenter|Qt.AlignLeft,QFontMetrics(font).elidedText(trans.name,Qt.ElideRight,int(badge_w-26)))
                    else:
                        p.drawPixmap(round(r_trans.center().x()-6),round(r_trans.center().y()-6),icon_pix)
                p.restore()
            # Snapping ghost clamper during transition drag
            if self.transition_hover:
                t_kind,t_name,t_track,t_cut,t_left,t_right=self.transition_hover
                tr_rect=self.track_rect(t_track)
                ghost_dur=0.80
                if t_kind=="transition_cut":ghost_start=t_cut-ghost_dur/2.0
                elif t_kind=="transition_start":ghost_start=t_cut
                else:ghost_start=t_cut-ghost_dur
                gx1=self.x_for_time(ghost_start); gx2=self.x_for_time(ghost_start+ghost_dur)
                ghost_clamper=QRectF(gx1,tr_rect.top()+2,max(12.0,gx2-gx1),tr_rect.height()-4)
                p.save(); p.setClipRect(self.section_rect(t_track),Qt.IntersectClip)
                p.fillRect(ghost_clamper,QColor(94,194,248,70))
                p.setPen(QPen(QColor("#5ec2f8"),2,Qt.DashLine)); p.setBrush(Qt.NoBrush)
                p.drawRect(ghost_clamper.adjusted(1,1,-1,-1))
                p.fillRect(QRectF(ghost_clamper.left(),ghost_clamper.center().y()-10,ghost_clamper.width(),20),QColor(20,24,34,215))
                p.setPen(QColor("#ffffff"))
                font=p.font(); font.setBold(True); p.setFont(font)
                p.drawText(ghost_clamper,Qt.AlignCenter,f"+ {t_name}")
                p.restore()
            if self.snap_guide is not None and self.tool!="blade":
                sx=self.x_for_time(self.snap_guide); p.setPen(QPen(QColor("#f3d45f"),1,Qt.DashLine)); p.drawLine(round(sx),self.RULER_HEIGHT,round(sx),h)
            p.restore()
            # Track controls are an opaque, final overlay.  Timeline content can be
            # horizontally scrolled underneath it but can never paint into it.
            for track in self.tracks():
                r=self.track_rect(track)
                if not r.intersects(self.section_rect(track)):continue
                if not dirty.intersects(QRect(0,round(r.top()),self.LABEL_WIDTH,round(r.height()))):continue
                self.paint_track_header(p,track)
                p.save(); p.setClipRect(self.section_rect(track),Qt.IntersectClip)
                audio=self._section_name(track)=="audio"
                if track.startswith("__new_"):
                    p.fillRect(QRectF(4,r.y(),self.LABEL_WIDTH-5,r.height()),QColor("#343c48")); p.setPen(QColor("#e3e8f0")); p.drawText(QRectF(10,r.y(),self.LABEL_WIDTH-18,r.height()),Qt.AlignVCenter,"+ New "+("Audio" if audio else "Video")+" Track")
                p.restore()
            p.fillRect(QRectF(self.LABEL_WIDTH-2,self.RULER_HEIGHT,3,h-self.RULER_HEIGHT),QColor(pal.get("timeline_divider", "#0b0c0e")))
            for divider in (self._subtitle_divider_rect(),self._av_divider_rect()):
                if not divider.isEmpty():p.fillRect(divider,QColor(pal.get("timeline_divider", "#0b0c0f"))); p.setPen(QColor(pal.get("border_subtle", "#555860"))); p.drawLine(0,round(divider.center().y()),w,round(divider.center().y()))
            p.fillRect(QRectF(0,0,w,self.RULER_HEIGHT),QColor(pal.get("timeline_ruler_bg", "#26272c")))
            p.fillRect(QRectF(0,0,self.LABEL_WIDTH-2,self.RULER_HEIGHT),QColor(pal.get("timeline_header_bg", "#202126")))
            p.setFont(QFont("Segoe UI",8)); major=next((step for step in (1,5,10,15,30,60,120,300,600) if step*self.pixels_per_second>=75),600); divisions=max(2,min(20,round(major*self.pixels_per_second/8))); minor=major/divisions
            first=max(0,math.floor(self.time_for_x(self.LABEL_WIDTH)/minor)*minor); last=self.time_for_x(w)+minor; count=math.ceil((last-first)/minor)
            for index in range(count+1):
                moment=first+index*minor; x=self.x_for_time(moment)
                if x<self.LABEL_WIDTH:continue
                unit=round(moment/minor); major_tick=unit%divisions==0; middle_tick=unit%(divisions//2)==0
                # Qt clips raster writes, not Python draw/layout calls. Most
                # playback damage is only two cursor strips plus the timecode.
                if not dirty.intersects(QRect(round(x)-1,0,65 if major_tick else 3,self.RULER_HEIGHT)):continue
                tick_height=12 if major_tick else 8 if middle_tick else 4
                p.setPen(QColor(pal.get("timeline_text", "#858990") if major_tick else pal.get("icon_sub_color", "#4e5158"))); p.drawLine(round(x),self.RULER_HEIGHT-tick_height,round(x),self.RULER_HEIGHT)
                if major_tick:
                    second=max(0,round(moment)); p.setPen(QColor(pal.get("timeline_text", "#b7bac1"))); p.drawText(round(x)+4,13,f"{second//60:02d}:{second%60:02d}")
            p.fillRect(QRectF(self.LABEL_WIDTH-2,0,3,self.RULER_HEIGHT),QColor(pal.get("timeline_divider", "#0b0c0e")))
            if self.roll_hover:
                left,right=self.roll_hover; boundary=self.x_for_time(right.start)
                rect=self.track_rect(left.track).intersected(self.section_rect(left.track))
                p.save(); p.setClipRect(rect.intersected(QRectF(self.LABEL_WIDTH+1,self.RULER_HEIGHT,w-self.LABEL_WIDTH-1,h-self.RULER_HEIGHT)))
                p.fillRect(QRectF(boundary-4,rect.top()+3,8,max(0,rect.height()-6)),QColor(85,235,132,90))
                p.setPen(QPen(QColor('#55eb84'),2)); p.drawLine(QPointF(boundary-2,rect.top()+3),QPointF(boundary-2,rect.bottom()-3)); p.drawLine(QPointF(boundary+2,rect.top()+3),QPointF(boundary+2,rect.bottom()-3)); p.restore()
        finally:
            self._frame_sec_rects=None
            self._frame_track_rects=None
            p.end()
        self._timeline_backing=backing
        screen=QPainter(viewport); screen.drawPixmap(0,0,backing); self._paint_clock(screen,pal); self._paint_selection_overlay(screen); self._paint_audio_levels(screen)

    def _paint_selection_overlay(self,p):
        # Keep one continuous box above all sections, but OUT of the static cache.
        self._painted_marquee=QRegion()
        if not self.marquee:return
        p.save(); p.setClipRect(QRectF(self.LABEL_WIDTH+1,self.RULER_HEIGHT,max(0,self.viewport().width()-self.LABEL_WIDTH-1),self.viewport().height()-self.RULER_HEIGHT))
        p.setBrush(QColor(136,173,216,35)); p.setPen(QPen(QColor('#acbfd6'),1,Qt.DashLine))
        for rect in self.marquee_controller.rects():
            p.drawRect(rect); self._painted_marquee |= QRegion(rect.toAlignedRect().adjusted(-2,-2,2,2))
        p.restore()

    def _paint_clock(self,p,pal):
        if not self.project:return
        p.setPen(QColor(pal.get('timeline_text','#eef0f3')))
        p.setFont(QFont('Segoe UI',13,QFont.DemiBold))
        p.drawText(QRectF(8,0,self.LABEL_WIDTH-16,self.RULER_HEIGHT),Qt.AlignCenter,self._timecode(self.project.playhead))
        x=self.x_for_time(self.project.playhead); self._painted_playhead_x=round(x)
        if x>=self.LABEL_WIDTH:
            p.setPen(QPen(QColor('#ed3545'),2)); p.drawLine(round(x),0,round(x),self.viewport().height())
            p.setRenderHint(QPainter.Antialiasing,True); p.setPen(Qt.NoPen); p.setBrush(QColor('#ed3545'))
            p.drawPolygon(QPolygonF([QPointF(x-7,0),QPointF(x+7,0),QPointF(x+7,6),QPointF(x,13),QPointF(x-7,6)]))

    def mousePressEvent(self,event):
        if not self.project:return
        if event.button()==Qt.MiddleButton:
            if self.drag_mode:self.cancel_drag()
            self.pan_section=next((n for n,r in self._sections().items() if r.contains(event.position())), '')
            if self.pan_section:
                self.drag_mode='pan'; self.pan_origin=event.position(); self.pan_offsets=(self.horizontalScrollBar().value(),getattr(self,self.pan_section+'_scroll').value()); self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept(); return
        if event.button()!=Qt.LeftButton:return
        if self.read_only:
            if event.position().x()>=self.LABEL_WIDTH:
                self.start_scrub(event.position().x())
            return
        pos=event.position(); self.drag_start=pos.toPoint(); self.drag_destination=""; self.duplicate=False; self.move_preview=[]; self.set_provisional(""); self.viewport().setFocus()
        trans_hit, trans_part = self.transition_at(pos)
        if trans_hit:
            self.selected_transition_id = trans_hit.id
            self.selected_ids = set()
            self.selected_id = ""
            self.selected_caption = ""
            self.selected_caption_ids = set()
            self.selectionChanged.emit([])
            self.trans_drag_orig = (trans_hit.start, trans_hit.duration)
            if trans_part == "left_handle":
                self.drag_mode = "trans_resize_left"
                self.viewport().setCursor(Qt.SizeHorCursor)
            elif trans_part == "right_handle":
                self.drag_mode = "trans_resize_right"
                self.viewport().setCursor(Qt.SizeHorCursor)
            else:
                self.drag_mode = "trans_select"
            self.transitionSelected.emit(trans_hit.id)
            self.viewport().update()
            return
        elif self.selected_transition_id:
            self.selected_transition_id = ""
            self.transitionSelected.emit("")
        divider=self._divider_at(pos)
        if divider:
            self.drag_mode="divider_"+divider; self.divider_original=(self.subtitle_extent,self.audio_extent,self.video_track_height,self.audio_track_height); self.viewport().setCursor(Qt.SplitVCursor); return
        hit, cap = self._fast_hit_at(pos)
        if (pos.y()<self.RULER_HEIGHT or (abs(pos.x()-self.x_for_time(self.project.playhead))<4 and not (hit or cap))) and pos.x()>=self.LABEL_WIDTH:
            self.start_scrub(pos.x()); return
        if pos.x()<self.LABEL_WIDTH:
            track=self.track_at(pos)
            if track:
                self.selected_track=track
                lock,toggle=self.header_controls(track)
                if self.track_rect(track).height()>=38 and lock.contains(pos):self._state(track)["locked"]=not self._state(track).get("locked",False); self.itemChanged.emit("")
                elif self.track_rect(track).height()>=38 and toggle.contains(pos):
                    key="muted" if track in self.project.audio_tracks else "visible"
                    self._state(track)[key]=not self._state(track).get(key,key=="visible"); self.itemChanged.emit("")
            return
        from .timeline_gestures import roll_pair,roll_snapshots
        pair=roll_pair(self,pos)
        if pair:
            members=roll_snapshots(self.project,*pair,self.linked_selection)
            if members:
                self.roll_members=members; self.snapshots={**members[0],**members[1]}; self.select_ids(set(self.snapshots),pair[0].id)
                self.drag_mode='roll'; self.roll_boundary=pair[1].start; self.roll_hover=pair
                self.viewport().setCursor(self._roll_cursor())
                self.viewport().update(); return
        if cap:
            if self._state("subtitle_1").get("locked"):self.select_captions({cap.id},cap.id); return
            if self.tool=="blade":
                at=self._blade_time(cap,pos.x()); self.select_captions({cap.id},cap.id)
                if cap.start<at<cap.end:self.captionBladeRequested.emit(cap.id,at)
                return
            modifiers=event.modifiers()
            if modifiers&Qt.ShiftModifier and self.selected_caption:
                ordered=sorted(self.project.captions,key=lambda candidate:(candidate.start,candidate.end)); anchor=next((n for n,candidate in enumerate(ordered) if candidate.id==self.selected_caption),None); current=ordered.index(cap)
                ids={candidate.id for candidate in ordered[min(anchor,current):max(anchor,current)+1]} if anchor is not None else {cap.id}
                if modifiers&Qt.ControlModifier:ids|=self.selected_caption_ids
                self.select_captions(ids,cap.id,True)
            elif modifiers&Qt.ControlModifier:
                ids=set(self.selected_caption_ids)
                if cap.id in ids:ids.remove(cap.id)
                else:ids.add(cap.id)
                self.select_captions(ids,cap.id,True)
            elif modifiers&Qt.ShiftModifier:self.select_captions(self.selected_caption_ids|{cap.id},cap.id,True)
            else:self.select_captions(self.selected_caption_ids if cap.id in self.selected_caption_ids else {cap.id},cap.id,cap.id in self.selected_caption_ids)
            if modifiers&(Qt.ControlModifier|Qt.ShiftModifier):self.drag_mode=""; return
            r=self.caption_rect(cap)
            if pos.x()-r.left()<8:self.drag_mode="caption_left"; self.viewport().setCursor(self._trim_cursor("left"))
            elif r.right()-pos.x()<8:self.drag_mode="caption_right"; self.viewport().setCursor(self._trim_cursor("right"))
            else:self.drag_mode="caption_move"
            if self.drag_mode=='caption_move' and self.selected_ids:
                from .mixed_move import begin
                begin(self,pos,'subtitle',modifiers); return
            self.caption_original=(cap.start,cap.end)
            from .caption_gestures import begin
            begin(self,cap,bool(modifiers&Qt.AltModifier))
            if self.drag_mode=='caption_move':self.clip_scroll.begin(pos,'subtitle',event.modifiers())
            self.viewport().update(); return
        if not hit:
            self.drag_mode="marquee"; self.marquee=QRectF(pos,pos); self.marquee_initial=set(self.selected_ids) if event.modifiers()&Qt.ControlModifier else set(); self.marquee_caption_initial=set(self.selected_caption_ids) if event.modifiers()&Qt.ControlModifier else set(); self.marquee_controller.begin(pos); return
        if self.tool=="blade":
            at=self._blade_time(hit,pos.x()); self.select_ids({hit.id},hit.id); self.bladeRequested.emit(hit.id,at); return
        if event.modifiers()&Qt.ShiftModifier and self.selected_id:
            anchor=self.project.item_by_id(self.selected_id)
            if anchor and anchor.track==hit.track:
                ordered=sorted((item for item in self.project.timeline if item.track==hit.track),key=lambda item:(item.start,item.id)); a=ordered.index(anchor); b=ordered.index(hit)
                ids={item.id for item in ordered[min(a,b):max(a,b)+1]}
            else:
                left=min(anchor.start if anchor else hit.start,hit.start); right=max((anchor.start+anchor.duration) if anchor else hit.start+hit.duration,hit.start+hit.duration)
                ids={item.id for item in self.project.timeline if item.start<right and item.start+item.duration>left}
            if event.modifiers()&Qt.ControlModifier:ids|=self.selected_ids
            self.select_ids(self.expanded(ids),hit.id,True)
        elif event.modifiers()&Qt.ControlModifier:
            ids=set(self.selected_ids); ids.symmetric_difference_update(self.expanded({hit.id})); self.select_ids(ids,hit.id,True)
        elif event.modifiers()&Qt.ShiftModifier:self.select_ids(self.selected_ids|self.expanded({hit.id}),hit.id,True)
        elif hit.id not in self.selected_ids:self.select_ids(self.expanded({hit.id}),hit.id)
        else:self.selected_id=hit.id; self.itemSelected.emit(hit.id)
        if event.modifiers()&(Qt.ControlModifier|Qt.ShiftModifier):self.drag_mode=""; return
        if self._state(hit.track).get("locked",False):return
        r=self.item_rect(hit)
        if hit.id in self.retime_ids and r.bottom()-pos.y()<21 and pos.x()-r.left()>8 and r.right()-pos.x()>8:
            self.speed_menu(hit,event.globalPosition().toPoint()); self.drag_mode=""; return
        if hit.id in self.retime_ids and pos.y()-r.top()<17 and 8<pos.x()-r.left()<18:
            self.retime_ids.difference_update(self.expanded({hit.id})); self.viewport().update(); return
        self.snapshots={i.id:copy.deepcopy(i) for i in self.selected_items() if not self._state(i.track).get("locked",False)}
        if len(self.snapshots)!=len(self.selected_items()):
            self.drag_mode=""; return  # Never tear a mixed locked/unlocked selection apart.
        r=self.item_rect(hit); self.original=(hit.start,hit.duration,hit.in_point); self.drag_original_track=hit.track
        self.alt_drag=bool(event.modifiers()&Qt.AltModifier)
        self._move_snap=None
        fi=r.left()+max(5,hit.fade_in*self.pixels_per_second); fo=r.right()-max(5,hit.fade_out*self.pixels_per_second)
        if hit.id in self.retime_ids and min(pos.x()-r.left(),r.right()-pos.x())<8:
            self.drag_mode="retime_left" if pos.x()-r.left()<8 else "retime_right"
            self.viewport().setCursor(self._trim_cursor("left" if self.drag_mode=="retime_left" else "right"))
        elif hit.id not in self.retime_ids and pos.y()-r.top()<12 and min(abs(pos.x()-fi),abs(pos.x()-fo))<7:
            self.drag_mode="fade_in" if abs(pos.x()-fi)<abs(pos.x()-fo) else "fade_out"
        elif pos.x()-r.left()<8 and 12<=pos.y()-r.top()<=r.height()-12:
            self.drag_mode="trim_left"; self.viewport().setCursor(self._trim_cursor("left"))
        elif r.right()-pos.x()<8 and 12<=pos.y()-r.top()<=r.height()-12:
            self.drag_mode="trim_right"; self.viewport().setCursor(self._trim_cursor("right"))
        else:self.drag_mode="move"
        if self.drag_mode=='move' and self.selected_caption_ids:
            from .mixed_move import begin
            begin(self,pos,self._section_name(hit.track),event.modifiers()); return
        if self.drag_mode in self.clip_scroll.MODES:self.clip_scroll.begin(pos,self._section_name(hit.track),event.modifiers())

    def mouseMoveEvent(self,event):
        if not self.project:return
        if self.drag_mode=='pan':
            delta=event.position()-self.pan_origin; horizontal,vertical=self.pan_offsets
            self.horizontalScrollBar().setValue(horizontal-round(delta.x()))
            bar=getattr(self,self.pan_section+'_scroll'); bar.setValue(vertical+round(delta.y())*(1 if self.pan_section in {'video','subtitle'} else -1))
            event.accept(); return
        if self.read_only:
            if self.drag_mode=="playhead" and event.buttons()&Qt.LeftButton:self.scrub_at(event.position().x())
            self.viewport().setCursor(Qt.ArrowCursor); return
        if not self.drag_mode:
            from .timeline_gestures import roll_pair
            new_roll=roll_pair(self,event.position())
            if new_roll!=self.roll_hover:
                self.roll_hover=new_roll; self.viewport().update()
            if self.roll_hover:
                self.viewport().setCursor(self._roll_cursor()); return
            divider=self._divider_at(event.position())
            if divider:
                needs_update=bool(self.hover_id or self.blade_hover_id)
                self.hover_id=""; self.blade_hover_id=""; self.blade_hover_time=None; self.viewport().setCursor(Qt.SplitVCursor)
                if needs_update:self.viewport().update()
                return
            trans_hit, trans_part = self.transition_at(event.position())
            if trans_hit:
                if trans_part in ("left_handle", "right_handle"):
                    self.viewport().setCursor(Qt.SizeHorCursor); return
                else:
                    self.viewport().setCursor(Qt.ArrowCursor); return
            hit,cap=self._fast_hit_at(event.position())
            new_hover_id=hit.id if hit else ""
            if self.tool=="blade":
                new_blade_id=hit.id if hit else ""
                new_blade_cap=cap.id if cap else ""
                new_blade_time=self._blade_time(cap or hit,event.position().x()) if (cap or hit) else None
                changed=(self.hover_id!=new_hover_id or self.blade_hover_id!=new_blade_id or self.blade_hover_caption!=new_blade_cap or self.blade_hover_time!=new_blade_time)
                self.hover_id=new_hover_id; self.blade_hover_id=new_blade_id; self.blade_hover_caption=new_blade_cap; self.blade_hover_time=new_blade_time
                self.viewport().setCursor(self._razor_cursor() if (hit or cap) else Qt.ArrowCursor)
                if changed:self.viewport().update()
                return
            if self.blade_hover_id or self.blade_hover_time is not None:
                self.blade_hover_id=""; self.blade_hover_time=None
            if new_hover_id!=self.hover_id:
                self.hover_id=new_hover_id; self.viewport().update()
            target=cap or hit
            if target:
                r=self.caption_rect(cap) if cap else self.item_rect(hit)
                x=event.position().x()
                if hit and not 12<=event.position().y()-r.top()<=r.height()-12:
                    self.viewport().setCursor(Qt.ArrowCursor); return
                if x-r.left()<8:self.viewport().setCursor(self._trim_cursor("left")); return
                elif r.right()-x<8:self.viewport().setCursor(self._trim_cursor("right")); return
            self.viewport().setCursor(Qt.ArrowCursor)
            return
        if self.drag_mode in {"trans_resize_left", "trans_resize_right"}:
            self.viewport().setCursor(Qt.SizeHorCursor)
            trans = self.project.transition_by_id(self.selected_transition_id)
            if trans and self.trans_drag_orig:
                orig_start, orig_dur = self.trans_drag_orig
                raw_delta = (event.position().x() - self.drag_start.x()) / self.pixels_per_second
                delta = -raw_delta if self.drag_mode == "trans_resize_left" else raw_delta
                fps = max(1, round(self.project.settings.fps))

                left_item = self.project.item_by_id(trans.left_item_id) if getattr(trans, "left_item_id", "") else None
                right_item = self.project.item_by_id(trans.right_item_id) if getattr(trans, "right_item_id", "") else None

                if trans.alignment == "center":
                    cut = orig_start + orig_dur / 2.0
                    left_bound = left_item.start if left_item else 0.0
                    right_bound = (right_item.start + right_item.duration) if right_item else (cut + 10.0)
                    max_half = min(cut - left_bound, right_bound - cut, 5.0)
                    min_half = 0.025
                    max_half = max(min_half, max_half)
                    new_half = max(min_half, min(max_half, (orig_dur / 2.0) + delta))
                    trans.start = cut - new_half
                    trans.duration = 2.0 * new_half
                elif trans.alignment == "start":
                    cut = orig_start
                    right_bound = (right_item.start + right_item.duration) if right_item else (cut + 10.0)
                    max_dur = min(10.0, max(0.05, right_bound - cut))
                    trans.start = cut
                    trans.duration = max(0.05, min(max_dur, orig_dur + delta))
                elif trans.alignment == "end":
                    cut = orig_start + orig_dur
                    left_bound = left_item.start if left_item else 0.0
                    max_dur = min(10.0, max(0.05, cut - left_bound))
                    new_dur = max(0.05, min(max_dur, orig_dur + delta))
                    trans.start = max(0.0, cut - new_dur)
                    trans.duration = new_dur

                frames = round(trans.duration * fps)
                QToolTip.showText(event.globalPosition().toPoint(), f"Transition: {trans.duration:.2f} s ({frames} frames)", self)
                win = self.window()
                if hasattr(win, "inspector") and getattr(win.inspector, "transition_id", "") == trans.id:
                    win.inspector.trans_duration.set_values([trans.duration])
                if hasattr(win, "preview"):
                    win.preview.update()
                self.viewport().update()
            return
        if self.drag_mode in {"trim_left","retime_left","caption_left"}:
            self.viewport().setCursor(self._trim_cursor("left"))
        elif self.drag_mode in {"trim_right","retime_right","caption_right"}:
            self.viewport().setCursor(self._trim_cursor("right"))
        elif self.drag_mode=='roll':
            self.viewport().setCursor(self._roll_cursor())
        if self.drag_mode in {"move","caption_move"} and getattr(self,"power_bin_target",lambda _:None)(event.globalPosition().toPoint()) is not None:
            self.power_bin_drag_handler(self); return
        pos=event.position()
        if self.drag_mode in self.clip_scroll.MODES:self.clip_scroll.remember(event)
        scroll_delta=self.horizontalScrollBar().value()-self.clip_scroll.origin if self.clip_scroll.section else 0
        delta=(pos.x()-self.drag_start.x()+scroll_delta)/self.pixels_per_second
        if self.drag_mode=='mixed_move':
            from .mixed_move import move
            move(self,delta); self._range(); self.viewport().update(); return
        if self.drag_mode=='roll':
            from .timeline_gestures import roll
            delta=self.snap_edge(self.roll_boundary+delta,self.snapshots)-self.roll_boundary
            roll(self.project,*self.roll_members,delta); self.viewport().update(); return
        if self.drag_mode.startswith("divider_"):
            dy=pos.y()-self.drag_start.y(); subtitle,audio,legacy_video,legacy_audio=self.divider_original
            if self.drag_mode=="divider_av":
                self.audio_extent=max(30.,audio-dy); self.video_track_height=legacy_video+dy/max(1,len(self.project.video_tracks)); self.audio_track_height=legacy_audio-dy/max(1,len(self.project.audio_tracks))
            else:self.subtitle_extent=max(30.,subtitle+dy)
            self._range(); self.viewport().update(); return
        if self.drag_mode=="playhead":self.scrub_at(pos.x()); return
        if self.drag_mode=="marquee":
            self.marquee_controller.move(pos); return
        if self.drag_mode.startswith("caption_"):
            from .caption_gestures import move
            move(self,delta)
            self.viewport().update(); return
        hit=self.project.item_by_id(self.selected_id)
        if not hit:return
        if self.drag_mode=="move":
            if not self.move_preview and (pos-QPointF(self.drag_start)).manhattanLength()<=5:return
            delta=max(-min(i.start for i in self.snapshots.values()),delta)
            original=self.snapshots.get(hit.id)
            if not original:return
            from .mixed_move import snap_move
            edges=[edge for i in self.snapshots.values() for edge in (i.start,i.start+i.duration)]
            audio=original.track in self.project.audio_tracks; tracks=self.project.audio_tracks if audio else self.project.video_tracks
            section=self._sections()['audio' if audio else 'video']; target_pos=QPointF(pos.x(),max(section.top()+1,min(section.bottom()-1,pos.y())))
            target=self.track_at(target_pos)
            if not audio and self.video_scroll.value()==self.video_scroll.maximum():
                highest=self.track_rect(self.project.video_tracks[-1])
                above=(section.contains(pos) and pos.y()<highest.top()+10) or (not self.has_subtitles() and pos.y()<section.top())
                if above:target='__new_video'
            if target.startswith("__new_"):target=target[2:]
            if target not in tracks:
                if target in {"new_video","new_audio","new_audio_top"}:pass
                elif not audio and section.contains(pos) and pos.y()<self.track_rect(self.project.video_tracks[-1]).top():target="new_video"
                elif audio and section.contains(pos) and pos.y()>self.track_rect(self.project.audio_tracks[-1]).bottom():target="new_audio"
                elif audio and self._sections()["audio"].top()-self.AV_SEPARATOR<=pos.y()<self._sections()["audio"].top():target="new_audio_top"
                else:target=original.track
            self.drag_destination=target
            if target.startswith("new_") and ((audio and target=="new_video") or (not audio and target!="new_video")):
                target=original.track; self.drag_destination=target
            if target in tracks and self._state(target).get("locked"):target=original.track; self.drag_destination=target
            provisional="__"+target if target.startswith("new_") else ""
            destinations=([provisional]+list(tracks)) if target=="new_audio_top" else list(tracks)+([provisional] if provisional else [])
            destination=provisional or target
            indices=[destinations.index(i.track) for i in self.snapshots.values() if i.track in tracks]
            shift=destinations.index(destination)-destinations.index(original.track)
            # Clamp one shared offset, not each clip independently: lane spacing
            # must survive dragging the top member below the bottom lane.
            shift=max(-min(indices),min(len(destinations)-1-max(indices),shift))
            if any(self._state(destinations[index+shift]).get("locked") for index in indices):shift=0
            used_provisional=provisional and any(destinations[index+shift]==provisional for index in indices)
            destination_tracks={destinations[destinations.index(i.track)+shift] if i.track in tracks else i.track for i in self.snapshots.values()}
            delta=snap_move(self,delta,edges,self.snapshots,destination_tracks=destination_tracks)
            delta=max(-min(i.start for i in self.snapshots.values()),delta)
            self.move_preview=[]; self.set_provisional(provisional if used_provisional else "")
            for old in self.snapshots.values():
                item=copy.deepcopy(old); item._drag_ghost=True
                item.start=old.start+delta
                if old.track in tracks:item.track=destinations[destinations.index(old.track)+shift]
                self.move_preview.append(item)
        elif self.drag_mode in {"fade_in","fade_out"}:
            value=self.time_for_x(pos.x())-hit.start if self.drag_mode=="fade_in" else hit.start+hit.duration-self.time_for_x(pos.x())
            for item in self.selected_items():
                if item.id in self.snapshots:setattr(item,self.drag_mode,max(0,min(item.duration,value)))
            QToolTip.showText(event.globalPosition().toPoint(),f"{self.drag_mode.replace('_',' ').title()}: {max(0,value):.2f} s",self.viewport())
        else:
            old=self.snapshots[hit.id]; edge=old.start if self.drag_mode.endswith("left") else old.start+old.duration
            delta=self.snap_edge(edge+delta,self.snapshots)-edge
            for item in self.selected_items():
                if item.id in self.snapshots:item.__dict__.update(copy.deepcopy(self.snapshots[item.id].__dict__))
            if self.drag_mode.startswith("retime_"):
                old=self.snapshots[hit.id]; length=max(.05,old.duration+(-delta if self.drag_mode=="retime_left" else delta))
                self.project.retime_items(self.snapshots,old.source_duration/length,"right" if self.drag_mode=="retime_left" else "left")
            else:self.project.trim_items(self.snapshots,delta,"left" if self.drag_mode=="trim_left" else "right")
        self._range(); self.viewport().update()

    def mouseReleaseEvent(self,event):
        if self.drag_mode=='pan':
            if event.button()==Qt.MiddleButton:self.drag_mode=''; self.pan_section=''; self.viewport().unsetCursor()
            event.accept(); return
        if self.drag_mode in {'move','mixed_move','caption_move'} and isinstance(event,QMouseEvent) and event.button()==Qt.LeftButton:
            # Qt may coalesce moves: commit the release location, not the last
            # delivered move a few pixels short of the neighbor.
            self.mouseMoveEvent(event)
        self.clip_scroll.stop(); self.roll_hover=None; self.roll_members=None
        self.scrub_timer.stop()
        self.marquee_controller.stop()
        if self.drag_mode=="playhead":
            self._scrub_snap_points=None
            self.scrubFinished.emit()
        if self.read_only:self.drag_mode=""; self.snap_guide=None; self.viewport().update(); return
        if self.drag_mode=='mixed_move':
            from .mixed_move import finish
            finish(self); self.drag_mode=''; self.snap_guide=None; self._range(); self.viewport().update(); return
        changed=self.drag_mode not in {"","marquee","playhead","divider_av","divider_subtitle"}
        if self.drag_mode=="marquee" and self.marquee is not None and self.marquee.width()<3 and self.marquee.height()<3:
            if self.marquee_initial:self.select_ids(self.marquee_initial)
            elif self.marquee_caption_initial:self.select_captions(self.marquee_caption_initial)
            else:self.select_ids(set())
        if self.drag_mode=="move" and self.move_preview:
            if any(not self.project.item_by_id(id) or self.project.track_states.get(old.track,{}).get("locked") for id,old in self.snapshots.items()):self.cancel_drag(); return
            if any(self.project.track_states.get(i.track,{}).get("locked") for i in self.move_preview):self.cancel_drag(); return
            try:
                destination=""
                if self.provisional_track:
                    destination=self.project.add_track("audio" if self.drag_destination.startswith("new_audio") else "video")
                    if self.drag_destination=="new_audio_top":self.project.audio_tracks.remove(destination); self.project.audio_tracks.insert(0,destination)
                placed=set(); links={}; groups={}; primary=""
                for ghost in self.move_preview:
                    track=destination if ghost.track.startswith("__new_") else ghost.track
                    if self.alt_drag:
                        item=copy.deepcopy(ghost); del item._drag_ghost; item.id=uid(); key=item.group_id if item.link_id is None else item.link_id
                        item.link_id=links.setdefault(key,uid()) if key else ""; item.group_id=groups.setdefault(item.group_id,uid()); self.project.timeline.append(item)
                    else:item=self.project.item_by_id(ghost.id)
                    if not item:continue
                    item.start=ghost.start; item.track=track; placed.add(item.id)
                    if ghost.id==self.selected_id:primary=item.id
                self.project.overwrite(placed); self.move_preview=[]; self.set_provisional(""); self.select_ids(placed,primary)
            except Exception as error:
                import logging
                logging.exception("Failed to commit timeline move: %s", error)
                self.cancel_drag(); return
        elif self.drag_mode in {"trim_left","trim_right","retime_left","retime_right"}:self.project.overwrite(self.snapshots)
        elif self.drag_mode.startswith('caption_'):
            from .caption_gestures import finish
            finish(self)
        if self.drag_mode in {"trans_resize_left", "trans_resize_right", "trans_select"}:
            QToolTip.hideText()
            mode = self.drag_mode
            self.drag_mode = ""
            self.trans_drag_orig = None
            self.viewport().unsetCursor()
            if mode in {"trans_resize_left", "trans_resize_right"}:
                self.itemChanged.emit("")
            self.viewport().update()
            return
        QToolTip.hideText()
        self.marquee=None; self.snap_guide=None; self.drag_mode=""; self.divider_original=None; self.viewport().unsetCursor(); self._range(); self.viewport().update()
        if changed:self.itemChanged.emit(self.selected_id)

    @edit_only
    def toggle_retime(self):
        ids=self.expanded(self.selected_ids)
        if not ids:return
        self.select_ids(ids,self.selected_id)
        if ids.issubset(self.retime_ids):self.retime_ids.difference_update(ids)
        else:self.retime_ids.update(ids)
        self.viewport().update()

    @edit_only
    def set_speed(self,speed):
        ids=self.expanded(self.selected_ids); self.project.retime_items(ids,speed); self.project.overwrite(ids); self.retime_ids.update(ids); self._range(); self.itemChanged.emit(self.selected_id)

    @edit_only
    def speed_menu(self,item,position):
        menu=QMenu(self); speeds=menu.addMenu("Change Speed")
        for percent in [10,25,50,75,100,110,150,200,400,800]:
            action=speeds.addAction(f"{percent}%",lambda p=percent:self.set_speed(p/100)); action.setCheckable(True); action.setChecked(abs(item.speed-percent/100)<.00001)
        menu.addAction("Reset to 100%",lambda:self.set_speed(1.)); menu.popup(position); self._menu=menu

    def layer_wheel_delta(self,event,section):
        if event.pixelDelta().y():return event.pixelDelta().y()
        step=max(8,min(28,self.section_track_heights.get(section,self.track_height)/2))
        remainders=getattr(self,'_layer_wheel_remainders',{})
        value=event.angleDelta().y()/120*step+remainders.get(section,0)
        delta=round(value);remainders[section]=value-delta
        self._layer_wheel_remainders=remainders
        return delta

    def wheelEvent(self,event):
        if self.drag_mode=='pan' or event.buttons()&Qt.MiddleButton:event.accept(); return
        if self.drag_mode in {'trim_left','trim_right','roll','fade_in','fade_out','caption_left','caption_right','retime_left','retime_right'}:event.accept(); return
        if self.drag_mode in self.clip_scroll.MODES and self.clip_scroll.section:
            name=self.clip_scroll.section; bar=getattr(self,name+'_scroll'); delta=self.layer_wheel_delta(event,name)
            bar.setValue(bar.value()+(delta if name=='video' else -delta)); self.clip_scroll.remember(event); self.clip_scroll.refresh_drag(); event.accept(); return
        if self.drag_mode=='marquee':self.marquee_controller.wheel(event); return
        delta=event.angleDelta().y() or event.pixelDelta().y() or event.angleDelta().x()
        if event.modifiers()&Qt.AltModifier:
            if delta:
                self.set_zoom(self.pixels_per_second*(1.15 if delta>0 else 1/1.15))
                center=(self.LABEL_WIDTH+self.viewport().width())/2
                self._navigation_end=max(getattr(self,'_navigation_end',20),self.project.playhead+(self.viewport().width()-center)/self.pixels_per_second+2); self._range()
                self.horizontalScrollBar().setValue(round(self.project.playhead*self.pixels_per_second+self.LABEL_WIDTH-center))
            event.accept(); return
        if event.modifiers()&Qt.ControlModifier:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta); event.accept(); return
        if event.modifiers()&Qt.ShiftModifier and not self.read_only:
            section=next((name for name,rect in self._sections().items() if rect.contains(event.position())),None)
            if section:
                rect=self._sections()[section]; old=self.section_track_heights.get(section,self.track_height)
                delta=event.angleDelta().y() or event.pixelDelta().y()
                if delta:
                    new=max(28,min(140,old+(8 if delta>0 else -8))); bar=getattr(self,section+'_scroll')
                    distance=rect.bottom()-event.position().y() if section in {'video','subtitle'} else event.position().y()-rect.top()
                    offset=(bar.value()+distance)*new/old-distance
                    self.section_track_heights[section]=new; self._range(); bar.setValue(round(offset)); self.viewport().update()
            event.accept(); return
        section=next((name for name,rect in self._sections().items() if rect.contains(event.position())),"")
        bar={"subtitle":self.subtitle_scroll,"video":self.video_scroll,"audio":self.audio_scroll}.get(section)
        if bar and bar.maximum()>0:
            # Video has a bottom-origin offset: up reveals higher video lanes;
            # down returns towards V1. Subtitles also use a bottom origin.
            delta=self.layer_wheel_delta(event,section)
            bar.setValue(bar.value()+(delta if section in {"video","subtitle"} else -delta)); event.accept()
        else:self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-event.angleDelta().x()); event.accept()

    def leaveEvent(self,event):
        if not self.drag_mode:self.hover_id=""; self.blade_hover_id=""; self.blade_hover_caption=""; self.blade_hover_time=None; self.snap_guide=None; self.viewport().update()
        super().leaveEvent(event)

    def hideEvent(self,event):
        if self.drag_mode:self.cancel_drag()
        super().hideEvent(event)

    def dragEnterEvent(self,event):
        if self.read_only:event.ignore(); return
        if event.mimeData().hasFormat("application/x-kinetic-effect"):
            from .effects import DESCRIPTIONS
            if bytes(event.mimeData().data("application/x-kinetic-effect")).decode(errors="replace") in DESCRIPTIONS:event.acceptProposedAction()
            else:event.ignore()
        elif event.mimeData().hasFormat("application/x-kinetic-media-id") or event.mimeData().hasFormat("application/x-kinetic-media-ids") or event.mimeData().hasUrls():
            self.preview_incoming(event)
            # Accept entry even over the fixed header. Rejecting DragEnter there
            # prevents Qt from delivering later moves into valid clip space.
            event.acceptProposedAction()
        else:super().dragEnterEvent(event)

    def clear_incoming(self):
        self.external_drag_paths=[]
        self.incoming_preview=[]; self.incoming_plan=None; self.incoming_drop=None
        if hasattr(self,"subtitle_scroll"):self._range(); self.viewport().update()

    def preview_incoming(self,event):
        from .media_insert import plan
        from .model import TimelineItem
        import json
        if self.read_only or not self.project or event.position().x()<self.LABEL_WIDTH:self.clear_incoming(); event.ignore(); return
        try:
            mime=event.mimeData()
            external=mime.hasUrls()
            if external:
                from .external_drop import paths_from_mime
                ids=paths_from_mime(mime); self.external_drag_paths=ids; self.external_drag_point=event.position()
            else:ids=json.loads(bytes(mime.data("application/x-kinetic-media-ids"))) if mime.hasFormat("application/x-kinetic-media-ids") else [bytes(mime.data("application/x-kinetic-media-id")).decode()]
            if not isinstance(ids,list) or not ids or len(ids)>1000 or not all(isinstance(id,str) for id in ids):raise ValueError()
            resolver=getattr(self,"media_resolver",self.project.media_by_id)
            assets=self.file_drop_controller.assets(ids) if external and hasattr(self,"file_drop_controller") else [resolver(id) for id in ids]
            if not all(assets):raise ValueError()
            target=self.track_at(event.position()); asset=assets[0]
            audio=asset.kind=="audio" or (asset.kind=="video" and asset.has_audio and (target in self.display_tracks("audio")))
            kind="audio" if audio else "video"; lanes=getattr(self.project,kind+"_tracks")
            if target in self.display_tracks(kind) and target not in lanes:target="__new_"+kind
            elif target not in lanes:
                outside=(event.position().y()>self.track_rect(lanes[-1]).bottom()) if audio else (event.position().y()<self.track_rect(lanes[-1]).top())
                target="__new_"+kind if outside else lanes[0] if audio else lanes[-1]
            self.snap_guide=None; moment=self.snap_edge(self.time_for_x(event.position().x()))
            stage,added,captions=plan(self.project,assets,target,moment)
        except (ValueError,KeyError,TypeError,UnicodeError):self.clear_incoming(); self.snap_guide=None; event.ignore(); return
        ghosts=[copy.copy(i) for i in stage.timeline if i.id in added]
        ghosts.extend(TimelineItem(c.id,"","subtitle_1",c.start,c.end-c.start,role="title",title_text=c.text) for c in stage.captions if c.id in captions)
        for ghost in ghosts:ghost._drag_ghost=True; ghost._incoming=True
        self.incoming_plan=stage; self.incoming_preview=ghosts; self.incoming_drop=(ids,target,moment)
        self._range(); self.viewport().update(); event.acceptProposedAction()

    def effect_target(self,name,pos):
        from .effects import TITLES, GRAPHICS, compatible
        if not self.project or self.read_only or pos.x()<self.LABEL_WIDTH:return None
        track=self.track_at(pos)
        if name in TITLES or name in GRAPHICS:
            top=self.project.video_tracks[-1]
            if track=='__new_video' or (self.section_rect(top).contains(pos) and pos.y()<self.track_rect(top).top()):
                return (name,'','__new_video',self.time_for_x(pos.x()))
        if self.project.track_states.get(track,{}).get("locked",False):return None
        if (name in TITLES or name in GRAPHICS) and track in self.project.video_tracks:return (name,"",track,self.time_for_x(pos.x()))
        hit=next((i for i in reversed(self.project.timeline) if self.visible_item_rect(i).contains(pos)),None)
        return (name,hit.id,"",0) if compatible(name,hit,self.project) else None

    def dragMoveEvent(self,event):
        mime=event.mimeData()
        name=""
        if mime.hasFormat("application/x-kinetic-transition"):
            name=bytes(mime.data("application/x-kinetic-transition")).decode(errors="replace")
        elif mime.hasFormat("application/x-kinetic-effect"):
            raw_name=bytes(mime.data("application/x-kinetic-effect")).decode(errors="replace")
            if raw_name in TRANSITION_SET:
                name=raw_name

        if name:
            self.transition_hover=self.transition_target(name,event.position())
            self.effect_hover=None
            self.viewport().update()
            if self.transition_hover:event.acceptProposedAction()
            else:event.ignore()
            return

        self.transition_hover=None
        if mime.hasFormat("application/x-kinetic-effect"):
            name=bytes(mime.data("application/x-kinetic-effect")).decode(errors="replace")
            self.effect_hover=self.effect_target(name,event.position())
            self.set_provisional('__new_video' if self.effect_hover and self.effect_hover[2]=='__new_video' else '')
            self.viewport().update()
            if self.effect_hover:event.acceptProposedAction()
            else:event.ignore()
        else:self.preview_incoming(event)

    def dragLeaveEvent(self,event):
        self.set_provisional('')
        self.transition_hover=None; self.effect_hover=None; self.snap_guide=None; self.clear_incoming(); self.viewport().update(); event.accept()

    def dropEvent(self,event):
        if self.read_only:event.ignore(); return
        mime=event.mimeData()
        name=""
        if mime.hasFormat("application/x-kinetic-transition"):
            name=bytes(mime.data("application/x-kinetic-transition")).decode(errors="replace")
        elif mime.hasFormat("application/x-kinetic-effect"):
            raw_name=bytes(mime.data("application/x-kinetic-effect")).decode(errors="replace")
            if raw_name in TRANSITION_SET:
                name=raw_name

        if name:
            target=self.transition_target(name,event.position())
            self.transition_hover=None; self.effect_hover=None; self.viewport().update()
            if target:
                kind,trans_name,track,cut_time,left_item,right_item=target
                default_dur=0.80
                if kind=="transition_cut":
                    max_dur=min(left_item.duration,right_item.duration)*2.0
                    dur=min(default_dur,max(0.05,max_dur))
                    start=cut_time-dur/2.0
                    alignment="center"
                elif kind=="transition_start":
                    dur=min(default_dur,max(0.05,right_item.duration))
                    start=cut_time
                    alignment="start"
                else:  # transition_end
                    dur=min(default_dur,max(0.05,left_item.duration))
                    start=cut_time-dur
                    alignment="end"

                trans=Transition(
                    id=uid(),
                    name=trans_name,
                    category=SUBSECTION_BY_TRANSITION.get(trans_name,"Dissolve"),
                    track=track,
                    start=start,
                    duration=dur,
                    left_item_id=left_item.id if left_item else "",
                    right_item_id=right_item.id if right_item else "",
                    alignment=alignment,
                    properties=default_transition_properties(trans_name),
                )
                self.project.add_transition(trans)
                self.selected_transition_id=trans.id
                self.select_ids(set(),"")
                self.select_captions(set(),"")
                self.transitionSelected.emit(trans.id)
                self.itemChanged.emit("")
                self.viewport().update()
                event.acceptProposedAction()
                return
            else:
                event.ignore(); return

        if event.mimeData().hasFormat("application/x-kinetic-effect"):
            name=bytes(event.mimeData().data("application/x-kinetic-effect")).decode(errors="replace")
            target=self.effect_target(name,event.position()); self.effect_hover=None; self.set_provisional(''); self.viewport().update()
            if target:
                if target[2]:self.titleDropped.emit(name,target[2],target[3])
                else:self.effectDropped.emit(name,target[1])
                event.acceptProposedAction()
            else:event.ignore()
            return
        self.preview_incoming(event)
        if not self.incoming_drop:return
        ids,target,moment=self.incoming_drop; self.clear_incoming(); self.snap_guide=None
        if event.mimeData().hasUrls():self.filesDropped.emit(ids,target,moment)
        elif len(ids)==1:self.mediaDropped.emit(ids[0],target,moment)
        else:self.mediaBatchDropped.emit(ids,target,moment)
        event.acceptProposedAction()

    def _reset_transition_defaults(self, trans: Transition):
        trans.properties = default_transition_properties(trans.name)
        self.transitionSelected.emit(trans.id)
        self.itemChanged.emit("")
        self.viewport().update()

    def _delete_transition_by_id(self, trans_id: str):
        self.selected_transition_id = ""
        self.project.remove_transition(trans_id)
        self.transitionSelected.emit("")
        self.itemChanged.emit("")
        self.viewport().update()

    def contextMenuEvent(self,event):
        if self.read_only:return
        if event.pos().x()<self.LABEL_WIDTH:return super().contextMenuEvent(event)
        trans_hit, _ = self.transition_at(event.pos())
        if trans_hit:
            self.selected_transition_id = trans_hit.id
            self.selected_ids = set()
            self.selected_id = ""
            self.selected_caption = ""
            self.selected_caption_ids = set()
            self.selectionChanged.emit([])
            self.transitionSelected.emit(trans_hit.id)
            self.viewport().update()
            menu = QMenu(self)
            hdr = menu.addAction(f"Transition: {trans_hit.name}")
            hdr.setEnabled(False)
            menu.addSeparator()
            menu.addAction("Reset Defaults", lambda t=trans_hit: self._reset_transition_defaults(t))
            menu.addAction("Delete Transition\tDelete", lambda tid=trans_hit.id: self._delete_transition_by_id(tid))
            menu.popup(event.globalPos())
            self._menu = menu
            return
        hit=next((i for i in reversed(self.project.timeline) if self.visible_item_rect(i).contains(event.pos())),None)
        if hit:
            if hit.id not in self.selected_ids:self.select_ids(self.expanded({hit.id}),hit.id)
            menu=QMenu(self); items=self.selected_items()
            self.add_clipboard_actions(menu)
            menu.addAction('New Compound Clip…',lambda:self.commandRequested.emit('compound_create',''))
            menu.addAction("Retime Controls · Ctrl+R",self.toggle_retime)
            media=self.project.media_by_id(hit.media_id)
            from .missing_media import unavailable
            if media and unavailable(media,hit) and not media.compound:
                menu.addAction('Change replacement file…',lambda:self.commandRequested.emit('relink_media',hit.id))
            if media and media.compound:
                menu.addAction('Open in Timeline',lambda:self.commandRequested.emit('compound_open',hit.id))
                menu.addAction('Retry Compound Preview',lambda:self.commandRequested.emit('compound_retry',hit.id))
            if media and media.kind in {'video','image'} and hit.track in self.project.video_tracks and hit.role!='title':
                action=menu.addAction('Manage Keyframes…',lambda:self.commandRequested.emit('keyframes',hit.id)); action.setEnabled(not self._state(hit.track).get('locked'))
            for label,cmd in [("Split Clips","split"),("Lift","lift"),("Ripple Delete","ripple")]:
                menu.addAction(label,lambda c=cmd:self.commandRequested.emit(c,self.selected_id))
            menu.addSeparator(); linked=len(items)>1 and self.selected_ids.issubset({i.id for i in self.project.linked_items(items[0])})
            action=menu.addAction("Link Clips"); action.setCheckable(True); action.setChecked(linked)
            action.triggered.connect(lambda:self.link_clips(linked))
            menu.popup(event.globalPos()); self._menu=menu
        elif any(self.visible_caption_rect(c).contains(event.pos()) for c in self.project.captions):
            caption=next(c for c in self.project.captions if self.visible_caption_rect(c).contains(event.pos()))
            if caption.id not in self.selected_caption_ids:self.select_captions({caption.id},caption.id)
            menu=QMenu(self); self.add_clipboard_actions(menu); menu.addAction('New Compound Clip…',lambda:self.commandRequested.emit('compound_create','')); menu.addAction("Split Subtitle",self.split_caption); menu.addAction("Merge With Next",self.merge_caption); menu.addAction("Delete Subtitle",self.delete_caption); menu.popup(event.globalPos()); self._menu=menu
        else:super().contextMenuEvent(event)

    def add_clipboard_actions(self,menu,selected=True):
        from .clipboard import get
        for command,key in (("cut","Ctrl+X"),("copy","Ctrl+C"),("paste","Ctrl+V")):
            action=menu.addAction(command.title()+"\t"+key,lambda c=command:self.commandRequested.emit(c,None))
            action.setEnabled(bool(get()) if command=="paste" else selected)
        action=menu.addAction("Paste Attributes…\tAlt+V",lambda:self.commandRequested.emit("paste_attributes",None)); action.setEnabled(selected and bool(get()))
        menu.addSeparator()

    @edit_only
    def link_clips(self,unlink=False):
        self.project.link_selection(self.selected_ids,unlink); self.itemChanged.emit(self.selected_id)

    @edit_only
    def delete_caption(self):
        if self._state("subtitle_1").get("locked"):return
        ids=self.selected_caption_ids or ({self.selected_caption} if self.selected_caption else set()); self.project.captions=[c for c in self.project.captions if c.id not in ids]; self.selected_caption=""; self.selected_caption_ids=set(); self.itemChanged.emit("")

    @edit_only
    def split_caption(self,at=None):
        if self._state("subtitle_1").get("locked"):return
        from .captions import split_caption
        caption=next((c for c in self.project.captions if c.id==self.selected_caption),None)
        result=split_caption(caption,self.project.playhead if at is None or isinstance(at,bool) else at) if caption else None
        if result:
            self.project.captions.remove(caption); self.project.captions.extend(result); self.selected_caption=result[0].id; self.selected_caption_ids={result[0].id}; self.captionSelected.emit(result[0].id); self.itemChanged.emit("")

    @edit_only
    def merge_caption(self):
        if self._state("subtitle_1").get("locked"):return
        from .captions import merge_captions
        captions=sorted(self.project.captions,key=lambda c:c.start); index=next((n for n,c in enumerate(captions) if c.id==self.selected_caption),-1)
        if 0<=index<len(captions)-1:
            pair=captions[index:index+2]; result=merge_captions(pair)
            self.project.captions=[c for c in self.project.captions if c not in pair]+[result]; self.selected_caption=result.id; self.selected_caption_ids={result.id}; self.captionSelected.emit(result.id); self.itemChanged.emit("")
