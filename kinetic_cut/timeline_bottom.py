"""Fullscreen-only placement of the existing timeline ruler and toolbar."""
from PySide6.QtCore import Qt,QPoint,QRectF
from PySide6.QtGui import QPainter,QMouseEvent,QWheelEvent,QContextMenuEvent,QColor
from PySide6.QtWidgets import QWidget


class TimelineBody(QWidget):
    def __init__(self,timeline,parent):
        super().__init__(parent);self.timeline=timeline
        # Native children must be clipped by this host too, not merely by
        # QWidget painting; the original ruler sits just outside its top edge.
        self.setAttribute(Qt.WA_NativeWindow)
        self.setMinimumHeight(max(0,timeline.minimumHeight()-timeline.RULER_HEIGHT))
    def resizeEvent(self,event):
        super().resizeEvent(event);self.arrange()
    def arrange(self):
        offset=self.timeline.RULER_HEIGHT+self.timeline.viewport().y()
        self.timeline.setGeometry(0,-offset,self.width(),self.height()+offset)


class BottomRuler(QWidget):
    def __init__(self,w):
        super().__init__(w.timeline_panel);self.timeline=w.timeline
        self.setFixedHeight(self.timeline.RULER_HEIGHT);self.setMouseTracking(True)
        self.setAccessibleName('Timeline ruler');self.setToolTip('Drag to scrub the timeline')
        for signal in (w.transport.changed,self.timeline.playheadChanged,self.timeline.zoomChanged,self.timeline.horizontalScrollBar().valueChanged):signal.connect(self.refresh)
    def refresh(self,*_):
        if self.isVisible():self.update()
    def offset(self):return self.timeline.viewport().pos().x()
    def paintEvent(self,event):
        t=self.timeline;p=QPainter(self);palette=t._palette()
        p.fillRect(self.rect(),QColor(palette['timeline_ruler_bg']))
        p.translate(self.offset(),0)
        t._paint_ruler(p,palette,t.viewport().width(),event.region().translated(-self.offset(),0))
        t._paint_clock(p,palette);p.end()
    def mouse(self,event,handler):
        point=event.position();point.setX(point.x()-self.offset())
        forwarded=QMouseEvent(event.type(),point,event.globalPosition(),event.button(),event.buttons(),event.modifiers(),event.pointingDevice())
        getattr(self.timeline,handler)(forwarded);event.setAccepted(forwarded.isAccepted());self.update()
    def mousePressEvent(self,event):self.mouse(event,'mousePressEvent')
    def mouseMoveEvent(self,event):self.mouse(event,'mouseMoveEvent')
    def mouseReleaseEvent(self,event):self.mouse(event,'mouseReleaseEvent')
    def mouseDoubleClickEvent(self,event):self.mouse(event,'mouseDoubleClickEvent')
    def wheelEvent(self,event):
        point=event.position();point.setX(point.x()-self.offset())
        forwarded=QWheelEvent(point,event.globalPosition(),event.pixelDelta(),event.angleDelta(),event.buttons(),event.modifiers(),event.phase(),event.inverted(),event.source(),event.pointingDevice())
        self.timeline.wheelEvent(forwarded);event.setAccepted(forwarded.isAccepted());self.update()
    def contextMenuEvent(self,event):
        forwarded=QContextMenuEvent(event.reason(),event.pos()-QPoint(self.offset(),0),event.globalPos(),event.modifiers())
        self.timeline.contextMenuEvent(forwarded);event.setAccepted(forwarded.isAccepted())


class BottomTimeline:
    def __init__(self,w):
        self.w=w;self.body=TimelineBody(w.timeline,w.timeline_panel);self.ruler=BottomRuler(w)
        self.body.hide();self.ruler.hide()
    def set_active(self,active):
        w=self.w;layout=w.timeline_panel.layout();layout.removeItem(w.timeline_bar);w.timeline_bar.setParent(None)
        if active:
            layout.removeWidget(w.timeline);w.timeline.setParent(self.body)
            layout.addWidget(self.body,1);layout.addWidget(self.ruler);layout.addLayout(w.timeline_bar)
            self.body.show();w.timeline.show();self.body.arrange();self.ruler.show()
        else:
            layout.removeWidget(self.body);layout.removeWidget(self.ruler);self.body.hide();self.ruler.hide()
            w.timeline.setParent(w.timeline_panel);layout.insertLayout(0,w.timeline_bar);layout.addWidget(w.timeline,1);w.timeline.show()
        layout.activate();self.body.arrange() if active else None
