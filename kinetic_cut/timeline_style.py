"""Timeline-only text and handle appearance; never changes rendered captions."""
from PySide6.QtCore import Qt,QPointF
from PySide6.QtGui import QFont,QFontMetricsF,QTextLayout,QTextOption,QPainterPath,QColor,QPen,QPainter

CAPTION_COLOR='#b9b097'

def caption_font():
    font=QFont('Segoe UI');font.setPixelSize(11);font.setWeight(QFont.DemiBold)
    return font

def caption_layout(text,width,height):
    font=caption_font();layout=QTextLayout('\u2028'.join(str(text).splitlines()),font)
    option=QTextOption();option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere);layout.setTextOption(option)
    line_height=QFontMetricsF(font).height();y=0.
    layout.beginLayout()
    if width>=6:
        while y+line_height<=height:
            line=layout.createLine()
            if not line.isValid():break
            line.setLineWidth(width);line.setPosition(QPointF(0,y));y+=line.height()
    layout.endLayout();return layout

def paint_caption(painter,rect,text):
    area=rect.adjusted(4,4,-4,-3)
    if area.width()<6:return
    painter.save();painter.setClipRect(area,Qt.IntersectClip);painter.setPen(QColor('#151515'))
    caption_layout(text,area.width(),area.height()).draw(painter,area.topLeft());painter.restore()

def fade_tab(painter,x,top,active=False):
    path=QPainterPath(QPointF(x-4,top+2));path.lineTo(x+4,top+2);path.lineTo(x+4,top+8)
    path.cubicTo(x+4,top+13,x-4,top+13,x-4,top+8);path.closeSubpath()
    painter.save();painter.setRenderHint(QPainter.Antialiasing);painter.setPen(QPen(QColor('#151515'),1))
    painter.setBrush(QColor('#ef6657' if active else '#ffffff'));painter.drawPath(path);painter.restore()
