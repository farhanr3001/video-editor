"""Content-anchored box selection with bounded, stationary-pointer edge scrolling."""
from PySide6.QtCore import QObject,QTimer,QPointF,QRectF,Qt,QItemSelection,QItemSelectionModel
from PySide6.QtWidgets import QRubberBand,QApplication


def edge_step(position,low,high,margin=24):
    margin=min(margin,max(1,(high-low)/3))
    distance=position-(low+margin) if position<low+margin else position-(high-margin) if position>high-margin else 0
    return round((3+min(1,abs(distance)/margin)*17)*(1 if distance>0 else -1)) if distance else 0


class TimelineMarquee(QObject):
    def __init__(self,view):
        super().__init__(view); self.view=view; self.anchor=None; self.pos=QPointF(); self.logical=QRectF(); self.moved=False
        self.active_section=''; self.anchor_section=''; self.endpoint=QPointF(); self.endpoint_screen_y=0.; self.anchor_padding=0.
        self.timer=QTimer(self); self.timer.setInterval(40); self.timer.timeout.connect(self.scroll)
        for bar in (view.subtitle_scroll,view.video_scroll,view.audio_scroll,view.horizontalScrollBar()):bar.valueChanged.connect(self.update)
    def metrics(self):
        t=self.view; base=0.; result=[]
        for name,rect in t._sections().items():
            count=int(t.has_subtitles()) if name=='subtitle' else len(t.display_tracks(name)); content=count*t.track_height
            if not count or rect.height()<=0:continue
            bar=getattr(t,name+'_scroll'); origin=rect.bottom()-content+bar.value() if name in {'video','subtitle'} else rect.top()-bar.value()
            result.append((name,rect,base,content,origin)); base+=content
        return result
    def point(self,pos,metric=None):
        metrics=self.metrics()
        if not metrics:return QPointF()
        name,rect,base,content,origin=metric or min(metrics,key=lambda m:max(m[1].top()-pos.y(),0,pos.y()-m[1].bottom()))
        return QPointF(max(0,self.view.time_for_x(pos.x())),base+max(0,min(content,pos.y()-origin)))
    def begin(self,pos):
        metrics=self.metrics()
        if not metrics:return
        metric=min(metrics,key=lambda m:max(m[1].top()-pos.y(),0,pos.y()-m[1].bottom()))
        self.active_section=self.anchor_section=metric[0]
        self.pos=QPointF(pos); self.press=QPointF(pos); self.anchor=self.point(pos,metric); self.moved=False
        self.anchor_padding=pos.y()-(metric[4]+self.anchor.y()-metric[2])
        self.endpoint=QPointF(self.anchor); self.endpoint_screen_y=pos.y(); self.timer.start()
    def move(self,pos):
        self.pos=QPointF(pos); self.moved|=(self.pos-self.press).manhattanLength()>=QApplication.startDragDistance(); self.update()
    def stop(self):self.timer.stop(); self.anchor=None; self.active_section=''
    def can_scroll(self,name,direction):
        bar=getattr(self.view,name+'_scroll')
        delta=-direction if name in {'video','subtitle'} else direction
        return bar.value()<bar.maximum() if delta>0 else bar.value()>bar.minimum()
    def resolve_endpoint(self):
        """Do not jump over hidden lanes when the pointer crosses a divider.

        The active section owns the endpoint until its scroll limit is reached.
        Only then may a stationary pointer continue into the adjacent section.
        This applies symmetrically when extending or reversing the selection.
        """
        metrics=self.metrics()
        if not metrics:return None
        index=next((n for n,m in enumerate(metrics) if m[0]==self.active_section),0)
        while True:
            metric=metrics[index]; name,rect,*_=metric
            direction=-1 if self.pos.y()<rect.top() else 1 if self.pos.y()>rect.bottom() else 0
            if not direction or self.can_scroll(name,direction):break
            neighbour=index+direction
            if not 0<=neighbour<len(metrics):break
            # Gaps belong to the outgoing section until the pointer actually
            # reaches the next section; otherwise repeated updates oscillate.
            adjacent=metrics[neighbour][1]
            if direction>0 and self.pos.y()<adjacent.top() or direction<0 and self.pos.y()>adjacent.bottom():break
            index=neighbour
        self.active_section=name
        self.endpoint_screen_y=max(rect.top(),min(rect.bottom(),self.pos.y()))
        self.endpoint=self.point(QPointF(self.pos.x(),self.endpoint_screen_y),metric)
        return metric
    def update(self,*_):
        t=self.view
        if self.anchor is None or t.drag_mode!='marquee' or not t.project:return
        self.resolve_endpoint()
        self.logical=QRectF(self.anchor,self.endpoint).normalized(); r=self.logical
        t.marquee=QRectF(0,0,r.width()*t.pixels_per_second,r.height())
        metrics={name:(base,origin) for name,_,base,_,origin in self.metrics()}
        def intersects(rect,track):
            base,origin=metrics[t._section_name(track)]
            logical=QRectF(t.time_for_x(rect.left()),base+rect.top()-origin,rect.width()/t.pixels_per_second,rect.height())
            return logical.intersects(r)
        ids={i.id for i in t.project.timeline if t._section_name(i.track) in metrics and intersects(t.item_rect(i),i.track)}
        captions={c.id for c in t.project.captions if 'subtitle' in metrics and intersects(t.caption_rect(c),'subtitle_1')}
        ids=t.marquee_initial|t.expanded(ids); captions=t.marquee_caption_initial|captions
        changed=ids!=t.selected_ids or captions!=t.selected_caption_ids
        t.selected_ids=ids; t.selected_id=t.selected_id if t.selected_id in ids else next(iter(ids),''); t.selected_caption_ids=captions; t.selected_caption=next(iter(captions),'')
        if changed:
            if t.selected_id:t.itemSelected.emit(t.selected_id)
            else:t.captionSelected.emit(t.selected_caption)
            t.selected_caption_ids=captions; t.selected_caption=next(iter(captions),'')
        if changed:t.viewport().update()
        else:t.update_selection_overlay()
    def rects(self):
        if self.anchor is None:return []
        t=self.view; metric=next((m for m in self.metrics() if m[0]==self.anchor_section),None)
        if metric is None:return []
        _,section,base,content,origin=metric
        # Keep one outline/fill over the whole timeline, including dividers.
        # An offscreen origin is capped at its own section's visible boundary,
        # so scrolling video cannot make an audio section look selected.
        anchor_y=max(section.top(),min(section.bottom(),origin+self.anchor.y()-base+self.anchor_padding))
        rect=QRectF(QPointF(t.x_for_time(self.anchor.x()),anchor_y),QPointF(t.x_for_time(self.endpoint.x()),self.endpoint_screen_y)).normalized()
        canvas=QRectF(t.LABEL_WIDTH,t.RULER_HEIGHT,t.viewport().width()-t.LABEL_WIDTH,t.viewport().height()-t.RULER_HEIGHT)
        return [rect.intersected(canvas)]
    def wheel(self,event):
        self.move(event.position()); metric=self.resolve_endpoint()
        if metric:
            name=metric[0]; bar=getattr(self.view,name+'_scroll'); delta=event.angleDelta().y() or event.pixelDelta().y()
            bar.setValue(bar.value()+(delta if name in {'video','subtitle'} else -delta))
        bar=self.view.horizontalScrollBar(); bar.setValue(bar.value()-(event.angleDelta().x() or event.pixelDelta().x()))
        self.update(); event.accept()
    def scroll(self):
        t=self.view
        if self.anchor is None or t.drag_mode!='marquee' or t.read_only:self.stop(); return
        if not self.moved:return
        metric=self.resolve_endpoint()
        if metric is None:return
        name,rect,*_=metric
        step=edge_step(self.pos.y(),rect.top(),rect.bottom()); bar=getattr(t,name+'_scroll')
        bar.setValue(bar.value()+(-step if name in {'video','subtitle'} else step))
        bar=t.horizontalScrollBar(); bar.setValue(bar.value()+edge_step(self.pos.x(),t.LABEL_WIDTH,t.viewport().width()))
        self.update()


class PoolMarquee(QObject):
    def __init__(self,view):
        super().__init__(view); self.view=view; self.anchor=None; self.moved=False; self.pos=QPointF()
        self.band=QRubberBand(QRubberBand.Rectangle,view.viewport())
        self.timer=QTimer(self); self.timer.setInterval(40); self.timer.timeout.connect(self.scroll)
        for bar in (view.horizontalScrollBar(),view.verticalScrollBar()):bar.valueChanged.connect(self.update)
    def offset(self):return QPointF(self.view.horizontalOffset(),self.view.verticalOffset())
    def begin(self,event):
        v=self.view
        if event.button()!=Qt.LeftButton or v.itemAt(event.position().toPoint()):return False
        v.setFocus(); self.pos=QPointF(event.position()); self.press=QPointF(self.pos); self.anchor=self.pos+self.offset(); self.moved=False
        self.initial={index.row() for index in v.selectedIndexes()} if event.modifiers()&(Qt.ControlModifier|Qt.ShiftModifier) else set()
        self.update(); self.band.show(); self.timer.start(); event.accept(); return True
    def move(self,pos):
        if self.anchor is None:return False
        self.pos=QPointF(pos); self.moved|=(self.pos-self.press).manhattanLength()>=QApplication.startDragDistance(); self.update(); return True
    def stop(self):self.timer.stop(); self.anchor=None; self.band.hide()
    def update(self,*_):
        if self.anchor is None:return
        v=self.view; offset=self.offset(); rect=QRectF(self.anchor,self.pos+offset).normalized(); selected=QItemSelection()
        for row in range(v.count()):
            if row in self.initial or QRectF(v.visualItemRect(v.item(row))).translated(offset).intersects(rect):
                index=v.model().index(row,0); selected.select(index,index)
        v.selectionModel().select(selected,QItemSelectionModel.ClearAndSelect)
        self.band.setGeometry(rect.translated(-offset).intersected(QRectF(v.viewport().rect())).toRect())
    def scroll(self):
        if self.anchor is None:self.timer.stop(); return
        if not self.moved:return
        v=self.view
        for bar,position,extent in ((v.verticalScrollBar(),self.pos.y(),v.viewport().height()),(v.horizontalScrollBar(),self.pos.x(),v.viewport().width())):
            bar.setValue(bar.value()+edge_step(position,0,extent))
        self.update()
