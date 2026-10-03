"""Bounded, landmark-driven facial morph and optional skin tint.

All image operations are deterministic and shared by preview and export. The
effect changes pixels in the selected clip only; original media is untouched.
"""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen


CONTROLS = (
    ('face_width', 'Face width', 'Face'),
    ('jaw_width', 'Jaw width', 'Face'),
    ('eye_spacing', 'Eye spacing', 'Eyes'),
    ('left_eye', 'Left eye size', 'Eyes'),
    ('right_eye', 'Right eye size', 'Eyes'),
    ('nose_size', 'Nose size', 'Nose'),
    ('mouth_width', 'Mouth width', 'Mouth'),
    ('mouth_height', 'Mouth height', 'Mouth'),
)
DEFAULTS = {key: 0 for key, _, _ in CONTROLS}
LIMITS = {key: (-100, 140) if key == 'nose_size' else (-100, 100)
          for key in DEFAULTS}

# Ordered MediaPipe face-landmark rings. This uses actual detected geometry,
# rather than a guessed screen-space ellipse that would drift on head turns.
REGIONS = {
    'Face': (10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,
             378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,
             162,21,54,103,67,109),
    'Left eye': (33,160,158,133,153,144),
    'Right eye': (362,385,387,263,373,380),
    'Nose': (168,6,197,195,5,4,1,2,98,327),
    'Mouth': (61,40,37,0,267,270,291,321,314,17,84,91),
}
GUIDE_COLORS = {'Face':'#57d5d2','Left eye':'#edbd70','Right eye':'#edbd70',
                'Nose':'#a7d86c','Mouth':'#ec79ac'}


def values(effect):
    """Normalize saved or edited values without trusting project-file input."""
    incoming = effect.get('morph', {})
    if not isinstance(incoming, dict):
        incoming = {}
    result = {}
    for key in DEFAULTS:
        try:
            value = float(incoming.get(key, 0))
            low, high = LIMITS[key]
            result[key] = max(low, min(high, value)) if math.isfinite(value) else 0.
        except (TypeError, ValueError):
            result[key] = 0.
    return result


def _points(mesh, width, height):
    if mesh is None or getattr(mesh, 'shape', None) != (478, 3):
        return None
    if not np.isfinite(mesh[[1, 4, 10, 33, 133, 152, 234, 263, 291, 362, 454], :2]).all():
        return None
    return np.asarray(mesh[:, :2], dtype=np.float32) * (width, height)


def _path(points, indices):
    path = QPainterPath(QPointF(float(points[indices[0], 0]),
                                float(points[indices[0], 1])))
    for index in indices[1:]:
        path.lineTo(QPointF(float(points[index, 0]), float(points[index, 1])))
    path.closeSubpath()
    return path


def draw_guides(image: QImage, mesh, regions=None):
    points = _points(mesh, image.width(), image.height())
    if points is None:
        return
    enabled = set(regions or REGIONS)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scale = max(1., min(image.width(), image.height()) / 400)
    for name, indices in REGIONS.items():
        if name not in enabled:
            continue
        color = QColor(GUIDE_COLORS[name])
        painter.setPen(QPen(color, max(1.5, 2 * scale)))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(_path(points, indices))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        for index in indices[::max(1, len(indices)//9)]:
            painter.drawEllipse(QPointF(float(points[index,0]),
                                        float(points[index,1])), 2.2*scale, 2.2*scale)
    painter.end()


def _skin_tint(image, points, effect):
    try:
        strength = max(0., min(1., float(effect.get('skin_strength', 0)) / 100))
    except (TypeError, ValueError):
        return
    color = QColor(effect.get('skin_color', ''))
    if strength <= 0 or not color.isValid():
        return
    width, height = image.width(), image.height()
    mask_image = QImage(width, height, QImage.Format_Grayscale8)
    mask_image.fill(0)
    painter = QPainter(mask_image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawPath(_path(points, REGIONS['Face']))
    painter.setBrush(QColor(0, 0, 0))
    for ring in ('Left eye', 'Right eye', 'Mouth'):
        painter.drawPath(_path(points, REGIONS[ring]))
    painter.end()
    face = points[list(REGIONS['Face'])]
    x0 = max(0, int(np.min(face[:,0]))-3)
    x1 = min(width, int(np.max(face[:,0]))+4)
    y0 = max(0, int(np.min(face[:,1]))-3)
    y1 = min(height, int(np.max(face[:,1]))+4)
    if x1 <= x0 or y1 <= y0:
        return
    pixels = np.frombuffer(image.bits(), dtype=np.uint8).reshape(height, image.bytesPerLine())[:, :width*4].reshape(height,width,4)
    mask = np.frombuffer(mask_image.constBits(),dtype=np.uint8).reshape(height,mask_image.bytesPerLine())[:, :width]
    area = pixels[y0:y1,x0:x1,:3]
    alpha = mask[y0:y1,x0:x1].astype(np.float32) / 255
    # The polygon follows landmarks exactly, but a soft transition is needed
    # where skin meets hair/background. Blur only the small face rectangle.
    radius = max(2, min(10, round((x1-x0)*.035)))
    for axis in (1,0):
        padding = [(0,0),(0,0)]
        padding[axis] = (radius,radius)
        padded = np.pad(alpha,padding,mode='edge')
        sums = np.cumsum(padded,axis=axis,dtype=np.float32)
        sums = np.pad(sums,[(1,0) if n==axis else (0,0) for n in range(2)])
        if axis==1:
            alpha = (sums[:,2*radius+1:] - sums[:,:-2*radius-1])/(2*radius+1)
        else:
            alpha = (sums[2*radius+1:,:] - sums[:-2*radius-1,:])/(2*radius+1)
    if not np.any(alpha):
        return
    # Apply across the tracked face polygon, including differently lit skin.
    # Earlier cheek-colour gates left large untouched patches on turned faces.
    # Eye and mouth cut-outs protect the most conspicuous non-skin features;
    # per-pixel luminance retains the original shading and texture.
    original = area.astype(np.float32)
    intensity = original @ np.array([.2126,.7152,.0722],dtype=np.float32)
    target = np.array([color.red(),color.green(),color.blue()],dtype=np.float32)
    target_luma = max(8.,float(target @ np.array([.2126,.7152,.0722])))
    recolored = target[None,None,:] * (intensity/target_luma)[...,None]
    recolored = original*.12 + recolored*.88
    opacity = (alpha * strength)[...,None]
    area[:] = np.clip(original*(1-opacity)+recolored*opacity,0,255).astype(np.uint8)


def _feature(points, indices, width_factor=1., height_factor=1.):
    xy = points[list(indices)]
    centre = np.mean(xy,axis=0)
    span = np.max(xy,axis=0)-np.min(xy,axis=0)
    return float(centre[0]),float(centre[1]),max(3.,float(span[0])*width_factor),max(3.,float(span[1])*height_factor)


def _warp(image, points, controls):
    width, height = image.width(), image.height()
    face = points[list(REGIONS['Face'])]
    x0 = max(0,int(np.min(face[:,0]))-12)
    x1 = min(width,int(np.max(face[:,0]))+13)
    y0 = max(0,int(np.min(face[:,1]))-12)
    y1 = min(height,int(np.max(face[:,1]))+13)
    if x1 <= x0 or y1 <= y0:
        return
    yy,xx = np.mgrid[y0:y1,x0:x1].astype(np.float32)
    sx,sy = xx.copy(),yy.copy()

    def shift(key,cx,cy,rx,ry,axis='both',power=.42,use_source=False):
        amount=controls[key]/100 * power
        if abs(amount)<.001:
            return
        reference_x,reference_y=(sx,sy) if use_source else (xx,yy)
        radius=((reference_x-cx)/max(3.,rx))**2+((reference_y-cy)/max(3.,ry))**2
        weight=np.maximum(0.,1-radius)**2
        if axis in ('both','x'):
            sx[:] -= amount*(reference_x-cx)*weight
        if axis in ('both','y'):
            sy[:] -= amount*(reference_y-cy)*weight

    cx,cy,fw,fh=_feature(points,REGIONS['Face'],.80,.65)
    shift('face_width',cx,cy,fw,fh,'x',.32)
    jaw=points[152]
    shift('jaw_width',cx,float((cy+jaw[1])/2),fw*.9,fh*.75,'x',.45)
    left_eye=_feature(points,REGIONS['Left eye'],.9,2.0)
    right_eye=_feature(points,REGIONS['Right eye'],.9,2.0)
    eye_x0,eye_x1=sorted((left_eye[0],right_eye[0]))
    eye_distance=eye_x1-eye_x0
    if abs(controls['eye_spacing'])>.01 and eye_distance>=8:
        # A continuous, bounded displacement field moves both eyes around the
        # face centre without copying an eye patch or creating a second iris.
        # Its horizontal derivative stays positive at the centre even at 100%.
        eye_mid=(eye_x0+eye_x1)/2
        eye_y=(left_eye[1]+right_eye[1])/2
        band=max(8.,float(np.ptp(face[:,1]))*.21)
        vertical=np.maximum(0.,1-((yy-eye_y)/band)**2)**2
        horizontal=np.clip((xx-eye_mid)/max(4.,eye_distance/2),-1,1)
        face_left,face_right=float(np.min(face[:,0])),float(np.max(face[:,0]))
        left_fade=np.clip((xx-face_left)/max(4.,eye_x0-face_left),0,1)
        right_fade=np.clip((face_right-xx)/max(4.,face_right-eye_x1),0,1)
        delta=controls['eye_spacing']/100*eye_distance*.20
        sx[:] -= delta*horizontal*vertical*np.minimum(left_fade,right_fade)
    for key,ring in (('left_eye','Left eye'),('right_eye','Right eye')):
        cx,cy,rw,rh=_feature(points,REGIONS[ring],.9,2.0)
        shift(key,cx,cy,rw,rh,'both',.70,use_source=True)
    cx,cy,rw,rh=_feature(points,(168,6,197,195,5,4,1,2,98,327),.95,1.0)
    shift('nose_size',cx,cy,rw,rh,'both',.57)
    cx,cy,rw,rh=_feature(points,REGIONS['Mouth'],.7,1.7)
    shift('mouth_width',cx,cy,rw,rh,'x',.48)
    shift('mouth_height',cx,cy,rw,rh,'y',.52)
    if np.array_equal(sx,xx) and np.array_equal(sy,yy):
        return
    sx=np.clip(sx,0,width-1)
    sy=np.clip(sy,0,height-1)
    ix=sx.astype(np.int32)
    iy=sy.astype(np.int32)
    fx=(sx-ix)[...,None]
    fy=(sy-iy)[...,None]
    pixels=np.frombuffer(image.bits(),dtype=np.uint8).reshape(height,image.bytesPerLine())[:,:width*4].reshape(height,width,4)
    source=pixels.copy()
    right=np.minimum(ix+1,width-1)
    down=np.minimum(iy+1,height-1)
    sampled=(source[iy,ix]*(1-fx)*(1-fy)+source[iy,right]*fx*(1-fy)
             +source[down,ix]*(1-fx)*fy+source[down,right]*fx*fy)
    pixels[y0:y1,x0:x1]=np.rint(sampled).astype(np.uint8)


def apply_custom_face(image: QImage, mesh, effect):
    points=_points(mesh,image.width(),image.height())
    if points is None:
        return
    controls=values(effect)
    _skin_tint(image,points,effect)
    if any(abs(value)>.01 for value in controls.values()):
        _warp(image,points,controls)
