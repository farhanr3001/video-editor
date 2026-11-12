"""Tracking-only marker geometry and direct manipulation, in source coordinates."""
import math
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QTransform,QFont,QFontMetricsF,QPainter,QPen,QColor
from .tracking_dialog import RegionView


def marker_geometry(marker,props,rect,index):
    """Match the actual overlay's local bounds, including text and arrows."""
    w,h=marker['w']*rect.width(),marker['h']*rect.height()
    local=QRectF(-w/2,-h/2,w,h)
    if marker['mode']=='Arrow':
        length,head=marker['arrow_length'],max(marker['arrow_head']*1.1,marker['stroke'])
        local=QRectF(-length,-head/2,length,head)
    elif marker['mode']=='Label':
        font=QFont(marker['font']);font.setPixelSize(max(1,round(marker['font_size'])));font.setBold(True)
        metrics=QFontMetricsF(font);width=metrics.horizontalAdvance(marker['label'])+2*marker['label_padding']
        height=metrics.height()+2*marker['label_padding'];local=QRectF(-width/2,-height/2,width,height)
    return dict(index=index,cx=marker['x']+marker['w']/2,cy=marker['y']+marker['h']/2,
        left=local.x()/max(1,rect.width()),top=local.y()/max(1,rect.height()),
        w=local.width()/max(1,rect.width()),h=local.height()/max(1,rect.height()),
        rotation=marker['rotation'],props=props,mode=marker['mode'])


class TrackingRegionView(RegionView):
    markerEdited=Signal(object)
    markerSelected=Signal(int)
    cursorChanged=Signal()

    def __init__(self,media,parent=None):
        super().__init__(parent)
        self.media=media;self.tool='draw';self.gizmos=[];self.selected_index=0
        self._gesture=None;self.setMinimumSize(240,180)

    def image_rect(self):
        aspect=max(1,self.media.width)/max(1,self.media.height)
        width=min(self.width(),self.height()*aspect);height=width/aspect
        return QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)

    def setCursor(self,cursor):
        super().setCursor(cursor)
        self.cursorChanged.emit()

    def set_tool(self,tool):
        self.tool=tool
        self.setCursor(Qt.CrossCursor if tool=='draw' else Qt.ArrowCursor)
        self.update()

    def selected(self):
        return next((g for g in self.gizmos if g['index']==self.selected_index),None)

    def shape(self,g):
        r=self.image_rect()
        transform=QTransform();transform.translate(r.x()+g['cx']*r.width(),r.y()+g['cy']*r.height())
        transform.rotate(g['rotation'])
        local=QRectF(g['left']*r.width(),g['top']*r.height(),g['w']*r.width(),g['h']*r.height())
        return transform,local

    def handles(self,g):
        transform,rect=self.shape(g)
        points={name:transform.map(QPointF(rect.left()+fx*rect.width(),rect.top()+fy*rect.height()))
            for name,fx,fy in [('nw',0,0),('n',.5,0),('ne',1,0),('e',1,.5),('se',1,1),('s',.5,1),('sw',0,1),('w',0,.5)]}
        points['rotate']=transform.map(QPointF(rect.center().x(),rect.top()-24))
        return points

    def hit(self,point,g):
        for name,handle in self.handles(g).items():
            if math.hypot(point.x()-handle.x(),point.y()-handle.y())<=8:return name
        transform,rect=self.shape(g)
        return 'move' if rect.contains(transform.inverted()[0].map(point)) else None

    def mousePressEvent(self,event):
        # Qt Quick forwards directly to these handlers, bypassing QWidget's
        # usual disabled-input filter. Never draw on an unsettled source frame.
        if not self.isEnabled():event.ignore();return
        if self.tool=='draw':return super().mousePressEvent(event)
        if event.button()!=Qt.LeftButton:return super().mousePressEvent(event)
        g=self.selected();kind=self.hit(event.position(),g) if g else None
        if not kind:
            for candidate in reversed(self.gizmos):
                if self.hit(event.position(),candidate):
                    g=candidate;kind='move';self.markerSelected.emit(g['index']);break
        if not kind:return
        self.regionStarted.emit()
        transform,rect=self.shape(g)
        self._gesture=dict(g=g.copy(),kind=kind,start=QPointF(event.position()),transform=transform,rect=rect)
        self.setCursor(Qt.ClosedHandCursor if kind=='move' else Qt.SizeAllCursor)
        event.accept()

    def mouseMoveEvent(self,event):
        if not self.isEnabled():
            self._gesture=None;self.drag_start=None;event.ignore();return
        if self.tool=='draw':return super().mouseMoveEvent(event)
        if self._gesture:
            self._edit(event.position());event.accept();return
        g=self.selected();kind=self.hit(event.position(),g) if g else None
        cursor={'move':Qt.OpenHandCursor,'rotate':Qt.SizeAllCursor,'n':Qt.SizeVerCursor,'s':Qt.SizeVerCursor,
                'w':Qt.SizeHorCursor,'e':Qt.SizeHorCursor,'nw':Qt.SizeFDiagCursor,'se':Qt.SizeFDiagCursor,
                'ne':Qt.SizeBDiagCursor,'sw':Qt.SizeBDiagCursor}.get(kind,Qt.ArrowCursor)
        self.setCursor(cursor)

    def _edit(self,point):
        gesture=self._gesture;g=gesture['g'];props=g['props'];r=self.image_rect()
        scale=max(.00001,r.width()/max(1,self.media.width))
        kind=gesture['kind'];delta=point-gesture['start']
        if kind=='move':
            update=dict(offset_x=props['offset_x']+delta.x()/scale,offset_y=props['offset_y']+delta.y()/scale)
        elif kind=='rotate':
            origin=gesture['transform'].map(QPointF(0,0))
            start=gesture['start']-origin;now=point-origin
            angle=math.degrees(math.atan2(now.y(),now.x())-math.atan2(start.y(),start.x()))
            angle=(angle+180)%360-180
            update=dict(rotation=props['rotation']+angle)
        else:
            rect=gesture['rect'];local=gesture['transform'].inverted()[0].map(point)
            x,y=rect.center().x(),rect.center().y()
            rx=ry=1.
            if 'e' in kind:
                x=rect.left();rx=max(5,local.x()-x)/max(1,rect.width())
            if 'w' in kind:
                x=rect.right();rx=max(5,x-local.x())/max(1,rect.width())
            if 's' in kind:
                y=rect.top();ry=max(5,local.y()-y)/max(1,rect.height())
            if 'n' in kind:
                y=rect.bottom();ry=max(5,y-local.y())/max(1,rect.height())
            update={}
            if g['mode']=='Label':
                factor=(rx+ry)/2 if len(kind)==2 else rx if kind in ('e','w') else ry
                rx=ry=factor
                update.update(font_size=props['font_size']*factor,label_padding=props['label_padding']*factor)
            elif g['mode']=='Arrow':
                update.update(arrow_length=props['arrow_length']*rx,arrow_head=props['arrow_head']*ry)
            else:
                padding=props['padding']*scale*2
                update.update(width=props['width']*max(1,rect.width()*rx-padding)/max(1,rect.width()-padding),
                              height=props['height']*max(1,rect.height()*ry-padding)/max(1,rect.height()-padding))
            shift=QTransform().rotate(props['rotation']).map(QPointF(x*(1-rx),y*(1-ry)))
            update.update(offset_x=props['offset_x']+shift.x()/scale,offset_y=props['offset_y']+shift.y()/scale)
        self.markerEdited.emit(update)

    def mouseReleaseEvent(self,event):
        if not self.isEnabled():
            self._gesture=None;self.drag_start=None;event.ignore();return
        if self._gesture and event.button()==Qt.LeftButton:
            self._edit(event.position());self._gesture=None;self.mouseMoveEvent(event);event.accept();return
        super().mouseReleaseEvent(event)

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.tool!='transform' or not self.selected():return
        # Only used by the CPU fallback; native preview draws the same box in QML.
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#7dbbff'),1));painter.setBrush(Qt.NoBrush)
        transform,rect=self.shape(self.selected());painter.setTransform(transform);painter.drawRect(rect)
        painter.resetTransform();painter.setBrush(QColor('#ffffff'))
        for name,point in self.handles(self.selected()).items():
            if name=='rotate':painter.drawEllipse(point,4,4)
            else:painter.drawRect(QRectF(point.x()-4,point.y()-4,8,8))
        painter.end()
