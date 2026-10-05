"""Interactive normalized Bézier graph, with theme-role drawing."""
from PySide6.QtCore import Qt,QPointF,Signal
from PySide6.QtGui import QPainter,QPen,QPainterPath
from PySide6.QtWidgets import QWidget
from .theme_widgets import ui_color
from .easing import ease,controls

class EasingGraph(QWidget):
    changed=Signal()
    def __init__(self,key,parent=None):
        super().__init__(parent); self.key=key; self.drag=None; self.setMinimumSize(240,160)
        self.setToolTip('Drag Bézier control handles. Horizontal axis: time; vertical axis: value.')
    def point(self,x,y):return QPointF(25+x*(self.width()-50),self.height()-25-(y+.5)/2*(self.height()-45))
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.fillRect(self.rect(),ui_color('bg_main'))
        p.setPen(QPen(ui_color('border_subtle'),1))
        for x in (0,.25,.5,.75,1):p.drawLine(self.point(x,-.5),self.point(x,1.5))
        for y in (0,.5,1):p.drawLine(self.point(0,y),self.point(1,y))
        key=self.key() or {}; mode=key.get('interpolation','Linear'); handles=controls(key.get('bezier'))
        path=QPainterPath(self.point(0,0))
        for n in range(1,121):path.lineTo(self.point(n/120,ease(n/120,mode,handles)))
        p.setPen(QPen(ui_color('accent'),2)); p.drawPath(path)
        if mode=='Bezier':
            p.setPen(QPen(ui_color('text_sub'),1)); p.drawLine(self.point(0,0),self.point(*handles[:2])); p.drawLine(self.point(1,1),self.point(*handles[2:]))
            p.setBrush(ui_color('accent'))
            for x,y in (handles[:2],handles[2:]):p.drawEllipse(self.point(x,y),5,5)
        p.setPen(ui_color('text_sub')); p.drawText(25,self.height()-5,'Time →'); p.drawText(4,15,'Value')
    def mousePressEvent(self,event):
        key=self.key()
        if event.button()!=Qt.LeftButton or not key or key.get('interpolation')!='Bezier':return
        handles=controls(key.get('bezier'))
        for n in (0,2):
            if (event.position()-self.point(*handles[n:n+2])).manhattanLength()<18:self.drag=n; break
    def mouseMoveEvent(self,event):
        if self.drag is None:return
        key=self.key(); handles=controls(key.get('bezier')); n=self.drag
        x=max(0,min(1,(event.position().x()-25)/max(1,self.width()-50)))
        handles[n]=min(handles[2],x) if n==0 else max(handles[0],x)
        handles[n+1]=max(-4,min(4,(self.height()-25-event.position().y())*2/max(1,self.height()-45)-.5))
        key['bezier']=handles; self.changed.emit(); self.update()
    def mouseReleaseEvent(self,event):self.drag=None
