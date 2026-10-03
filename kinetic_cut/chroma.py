"""RGB-distance key with identical alpha math in Qt and FFmpeg."""
from PySide6.QtGui import QColor,QImage

NAMES={"Chroma Key","Green Screen"}


def values(effect):
    color=QColor(effect.get("color","#00ff00"))
    if not color.isValid():color=QColor("#00ff00")
    return color,max(.001,min(1,float(effect.get("similarity",15))/100)),max(0,min(1,float(effect.get("softness",8))/100))


def apply(image,effect):
    import numpy as np
    color,similarity,softness=values(effect)
    rgba=image.convertToFormat(QImage.Format_RGBA8888)
    pixels=np.frombuffer(rgba.constBits(),dtype=np.uint8).reshape(rgba.height(),rgba.width(),4).copy()
    delta=pixels[:,:,:3].astype(np.float32)-np.array([color.red(),color.green(),color.blue()],dtype=np.float32)
    distance=np.sqrt((delta*delta).sum(axis=2)/(3*255**2))
    alpha=((distance-similarity)/softness).clip(0,1) if softness>0 else (distance>similarity)
    pixels[:,:,3]=(pixels[:,:,3]*alpha).clip(0,255).astype(np.uint8)
    return QImage(pixels.data,rgba.width(),rgba.height(),QImage.Format_RGBA8888).copy()


def filter_string(effect):
    color,similarity,softness=values(effect)
    distance=f"sqrt((pow(r(X,Y)-{color.red()},2)+pow(g(X,Y)-{color.green()},2)+pow(b(X,Y)-{color.blue()},2))/{3*255**2})"
    mask=f"clip(({distance}-{similarity:.8f})/{softness:.8f},0,1)" if softness else f"gt({distance},{similarity:.8f})"
    return f"format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*{mask}'"


def apply_stack(image,item):
    for effect in item.effects:
        if effect.get("enabled",True) and effect.get("name") in NAMES:image=apply(image,effect)
    return image
