"""Tracking-local zoomable sample timeline. Values stay in clip-frame units."""
import math
from PySide6.QtCore import Qt,Signal,QPointF,QRectF
from PySide6.QtGui import QPainter,QPolygonF,QPen,QColor
from PySide6.QtWidgets import QSlider


class TrackingScrubber(QSlider):
    keyframeClicked=Signal(int)
    framesSelected=Signal(object)
    scrubStarted=Signal()

    def __init__(self,parent=None):
        super().__init__(Qt.Horizontal,parent)
        self.keyframes=[];self.selected_rows=set();self.zoom=1.;self.view_start=0.;self.fps=30.
        self._drag=False;self._anchor=None;self._wheel_remainder=0
        self.setFixedHeight(54);self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip('Diamonds: select frames. Ctrl/Shift: multiple. Wheel: previous/next selected frame. Ctrl+wheel: zoom. Shift+wheel: pan.')
        self.valueChanged.connect(self.ensure_visible)

    def span(self):return max(1.,(self.maximum()-self.minimum())/self.zoom)

    def bounds(self):return 9.,max(10.,self.width()-9.)

    def set_keyframes(self,frames):
        self.keyframes=list(frames);self.selected_rows={r for r in self.selected_rows if r<len(frames)};self.update()

    def set_selected(self,rows):
        self.selected_rows=set(rows);self.update()

    def keyframe_position(self,value):
        left,right=self.bounds()
        return QPointF(left+(value-self.view_start)/self.span()*(right-left),23)

    def at(self,x):
        left,right=self.bounds()
        return max(self.minimum(),min(self.maximum(),round(self.view_start+(x-left)/max(1,right-left)*self.span())))

    def ensure_visible(self,*_):
        if self._drag:return
        value=self.value();span=self.span()
        if value<self.view_start:self.view_start=value
        elif value>self.view_start+span:self.view_start=value-span
        self.clamp_view();self.update()

    def clamp_view(self):self.view_start=max(self.minimum(),min(self.maximum()-self.span(),self.view_start))

    def zoom_by(self,factor):
        anchor=self.value();fraction=(anchor-self.view_start)/self.span()
        self.zoom=max(1.,min(max(1.,(self.maximum()-self.minimum())/5),self.zoom*factor))
        self.view_start=anchor-fraction*self.span();self.clamp_view();self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        from .theme_widgets import palette
        left,right=self.bounds();base=self.palette().mid().color();text=self.palette().text().color();active=QColor(palette()['accent'])
        p.setPen(QPen(base,3,Qt.SolidLine,Qt.RoundCap));p.drawLine(QPointF(left,41),QPointF(right,41))
        seconds=self.span()/max(1,self.fps);raw=seconds/max(2,self.width()/70)
        unit=10**math.floor(math.log10(max(.001,raw)));step=next(v*unit for v in (1,2,5,10) if v*unit>=raw)
        first=math.ceil(self.view_start/self.fps/step)*step
        font=p.font();font.setPixelSize(10);p.setFont(font);p.setPen(text)
        for n in range(100):
            stamp=first+n*step
            if stamp*self.fps>self.view_start+self.span()+1e-7:break
            x=self.keyframe_position(stamp*self.fps).x()
            p.drawText(QRectF(x-24,0,48,13),Qt.AlignCenter,f'{stamp:g}s')
        for row,value in enumerate(self.keyframes):
            point=self.keyframe_position(value)
            if not left-1<=point.x()<=right+1:continue
            colour=active if row in self.selected_rows else text
            colour=QColor(colour);colour.setAlpha(255 if row in self.selected_rows else 145)
            p.setPen(Qt.NoPen);p.setBrush(colour);r=5 if row in self.selected_rows else 3
            p.drawPolygon(QPolygonF([point+QPointF(0,-r),point+QPointF(r,0),point+QPointF(0,r),point+QPointF(-r,0)]))
        x=self.keyframe_position(self.value()).x()
        if left<=x<=right:
            p.setPen(QPen(active,1));p.drawLine(QPointF(x,29),QPointF(x,47))
            p.setBrush(text);p.setPen(Qt.NoPen);p.drawEllipse(QPointF(x,41),5,5)
        p.end()

    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return
        self.setFocus(Qt.MouseFocusReason)
        if event.position().y()<31 and self.keyframes:
            row=min(range(len(self.keyframes)),key=lambda n:abs(self.keyframe_position(self.keyframes[n]).x()-event.position().x()))
            if abs(self.keyframe_position(self.keyframes[row]).x()-event.position().x())<=7:
                mods=event.modifiers()
                if mods&Qt.ShiftModifier and self._anchor is not None:
                    rows=set(range(min(row,self._anchor),max(row,self._anchor)+1))
                    if mods&Qt.ControlModifier:rows|=self.selected_rows
                elif mods&Qt.ControlModifier:rows=self.selected_rows^{row}
                else:rows={row}
                self._anchor=row;self.selected_rows=rows;self.framesSelected.emit(sorted(rows))
                self.setValue(self.keyframes[row]);self.keyframeClicked.emit(row);self.update();event.accept();return
        self.selected_rows.clear();self.framesSelected.emit([]);self.scrubStarted.emit()
        self._drag=True;self.setSliderDown(True);self.setValue(self.at(event.position().x()));event.accept()

    def mouseMoveEvent(self,event):
        if self._drag:self.setValue(self.at(event.position().x()));event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self._drag:
            self.setValue(self.at(event.position().x()));self._drag=False;self.setSliderDown(False);event.accept()

    def wheelEvent(self,event):
        delta=event.angleDelta().y()
        if event.modifiers()&Qt.ControlModifier:
            self.zoom_by(1.35 if delta>0 else 1/1.35);event.accept();return
        if event.modifiers()&Qt.ShiftModifier and self.zoom>1:
            self.view_start-=delta/120*self.span()*.15;self.clamp_view();self.update();event.accept();return
        if self.hasFocus() and self.selected_rows and self.keyframes:
            self.navigate_frames(delta);event.accept();return
        event.ignore()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape:self.selected_rows.clear();self.framesSelected.emit([]);self.update();event.accept();return
        super().keyPressEvent(event)

    def navigate_frames(self,delta):
        if not self.selected_rows or not self.keyframes:return
        self._wheel_remainder+=delta
        steps=int(self._wheel_remainder/120);self._wheel_remainder-=steps*120
        if steps:
            row=max(0,min(len(self.keyframes)-1,(self._anchor if self._anchor in self.selected_rows else min(self.selected_rows))-steps))
            self._anchor=row;self.selected_rows={row};self.framesSelected.emit([row]);self.setValue(self.keyframes[row]);self.keyframeClicked.emit(row);self.update()
