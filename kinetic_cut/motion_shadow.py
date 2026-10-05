"""Byte-bounded Gaussian shape shadows, shared by viewer and native exports."""
import math
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QImage,QPainter,QPen,QColor
from .image_cache import ImageCache

_cache=ImageCache(32*1024**2,max_entries=24)

def validate_shadow(raw):
    from .motion import finite
    if not isinstance(raw,dict):raise ValueError('Shadow must be an object')
    result=dict(raw)
    if not isinstance(result.get('enabled',False),bool):raise ValueError('Shadow enabled must be boolean')
    color=result.get('color','#000000')
    if not isinstance(color,str) or not QColor(color).isValid():raise ValueError('Invalid shadow colour')
    result['color']=color
    for key,default,low,high in [('opacity',20,0,100),('blur',20,0,128),('x',0,-10000,10000),('y',8,-10000,10000)]:
        v=finite(result.get(key,default))
        if not low<=v<=high:raise ValueError('Shadow '+key+' is out of range')
        result[key]=v
    return result

def paint_shadow(painter,path,shadow,fill,stroke_width):
    if not shadow.get('opacity',20) or path.isEmpty() or not (fill or stroke_width):return
    blur=shadow.get('blur',20); pad=math.ceil(blur*3+stroke_width/2+2); bounds=path.boundingRect().adjusted(-pad,-pad,pad,pad)
    if bounds.isEmpty():return
    # Match output density, cap working surfaces even for very large coordinates.
    transform=painter.worldTransform(); density=max(.125,min(2,math.sqrt(abs(transform.determinant()))))
    density=min(density,1024/max(bounds.width(),bounds.height()))
    width=max(1,math.ceil(bounds.width()*density)); height=max(1,math.ceil(bounds.height()*density))
    elements=tuple((path.elementAt(n).type.value,path.elementAt(n).x,path.elementAt(n).y) for n in range(path.elementCount()))
    key=(elements,fill,stroke_width,blur,width,height,shadow.get('color','#000000'))
    image=_cache.get(key)
    if image is None:
        from PIL import Image,ImageFilter
        mask=QImage(width,height,QImage.Format_RGBA8888); mask.fill(Qt.transparent); p=QPainter(mask)
        p.setRenderHint(QPainter.Antialiasing); p.scale(density,density); p.translate(-bounds.left(),-bounds.top())
        p.setBrush(Qt.white if fill else Qt.NoBrush); p.setPen(QPen(Qt.white,stroke_width,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin) if stroke_width else Qt.NoPen)
        try:p.drawPath(path)
        finally:p.end()
        alpha=Image.frombytes('RGBA',(width,height),bytes(mask.constBits())).getchannel('A').filter(ImageFilter.GaussianBlur(blur*density))
        color=QColor(shadow.get('color','#000000')); alpha=alpha.point(lambda v:round(v*color.alphaF()))
        rgba=Image.new('RGBA',(width,height),(color.red(),color.green(),color.blue(),255)); rgba.putalpha(alpha)
        image=QImage(rgba.tobytes(),width,height,width*4,QImage.Format_RGBA8888).copy(); _cache.put(key,image)
    painter.save()
    try:
        painter.setOpacity(painter.opacity()*shadow.get('opacity',20)/100)
        painter.drawImage(bounds.translated(shadow.get('x',0),shadow.get('y',8)),image)
    finally:painter.restore()
