"""Section-owned panning, drag edge scrolling and linked rolling edits."""
import copy
from PySide6.QtCore import QObject,QTimer,QPointF,QEvent,Qt
from PySide6.QtGui import QMouseEvent
from .selection_scroll import edge_step


class ClipScroll(QObject):
    # Only placement gestures scroll. Resizing/fading/rolling never changes the
    # viewport underneath the edge the user is holding.
    MODES={'move','caption_move','mixed_move'}
    def __init__(self,view):
        super().__init__(view); self.view=view; self.section=''; self.pos=QPointF(); self.modifiers=Qt.NoModifier; self.origin=0
        self.timer=QTimer(self); self.timer.setInterval(40); self.timer.timeout.connect(self.tick)
    def begin(self,pos,section,modifiers):
        self.section=section; self.pos=QPointF(pos); self.press=QPointF(pos); self.modifiers=modifiers; self.origin=self.view.horizontalScrollBar().value(); self.timer.start()
    def stop(self):self.timer.stop(); self.section=''
    def remember(self,event):self.pos=QPointF(event.position()); self.modifiers=event.modifiers()
    def refresh_drag(self):
        t=self.view
        event=QMouseEvent(QEvent.MouseMove,self.pos,QPointF(t.viewport().mapToGlobal(self.pos.toPoint())),Qt.NoButton,Qt.LeftButton,self.modifiers)
        t.mouseMoveEvent(event)
    def tick(self):
        t=self.view
        if t.drag_mode not in self.MODES or t.read_only or not self.section:self.stop(); return
        if (self.pos-self.press).manhattanLength()<5:return
        rect=t._sections()[self.section]; bar=getattr(t,self.section+'_scroll'); before=(bar.value(),t.horizontalScrollBar().value())
        step=edge_step(self.pos.y(),rect.top(),rect.bottom())
        bar.setValue(bar.value()+(-step if self.section=='video' else step))
        horizontal=t.horizontalScrollBar(); step=edge_step(self.pos.x(),t.LABEL_WIDTH,t.viewport().width()-12)
        if step>0 and horizontal.value()+step>=horizontal.maximum():
            t._navigation_end=max(getattr(t,'_navigation_end',20),t.time_for_x(t.viewport().width())+5); t._range()
        horizontal.setValue(horizontal.value()+step)
        if before!=(bar.value(),horizontal.value()):self.refresh_drag()


def roll_pair(view,pos):
    if pos.x()<view.LABEL_WIDTH or view.tool=='blade':return None
    track=view.track_at(pos)
    if not track or view._state(track).get('locked'):return None
    row=view.track_rect(track)
    if pos.y()<row.top()+15 or pos.y()>row.bottom()-12:return None  # Keep corners independent.
    items=sorted((i for i in view.project.timeline if i.track==track),key=lambda i:i.start)
    for left,right in zip(items,items[1:]):
        if abs(left.start+left.duration-right.start)<1e-5 and abs(pos.x()-view.x_for_time(right.start))<=2.5:
            return left,right
    return None


def roll_snapshots(project,left,right,linked):
    boundary=right.start
    members={left.id,right.id}
    if linked:members.update(i.id for i in project.linked_items(left)+project.linked_items(right))
    ends={i.id:copy.deepcopy(i) for i in project.timeline if i.id in members and abs(i.start+i.duration-boundary)<1e-5}
    starts={i.id:copy.deepcopy(i) for i in project.timeline if i.id in members and abs(i.start-boundary)<1e-5}
    if any(project.track_states.get(i.track,{}).get('locked') for i in list(ends.values())+list(starts.values())):return None
    return ends,starts


def roll(project,ends,starts,delta):
    low=-float('inf'); high=float('inf')
    for old in ends.values():
        low=max(low,.05-old.duration); media=project.media_by_id(old.media_id)
        if old.role!='title' and media and media.kind!='image':high=min(high,(media.duration-old.in_point)/old.speed-old.duration)
    for old in starts.values():
        low=max(low,-old.start); high=min(high,old.duration-.05); media=project.media_by_id(old.media_id)
        if old.role!='title' and media and media.kind!='image':low=max(low,-old.in_point/old.speed)
    delta=max(low,min(high,delta))
    for originals,is_left in ((ends,True),(starts,False)):
        for key,old in originals.items():
            item=project.item_by_id(key)
            if item is None:continue
            item.__dict__.update(copy.deepcopy(old.__dict__))
            if is_left:item.duration=old.duration+delta
            else:
                item.start=old.start+delta; item.duration=old.duration-delta; media=project.media_by_id(old.media_id)
                from .keyframes import shift
                shift(item,delta)
                if old.role!='title' and media and media.kind!='image':item.in_point=old.in_point+delta*old.speed
    return delta
