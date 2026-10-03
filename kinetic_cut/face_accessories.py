"""Pose-aware textured accessories shared by editor preview and export.

Artwork is split into independent transparent sprites at draw time. Ear size,
roll and foreshortening follow the tracked face; the detected face silhouette
occludes the ear roots so they do not look pasted over the forehead.
"""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QPainterPath

from .icons import resource_path


@lru_cache(maxsize=2)
def _kit(animal):
    return QImage(str(resource_path('assets', 'face_filters', animal + '-kit.png')))


def paint_accessories(image: QImage, pose: dict | None, names: set[str]):
    if not pose or not names:
        return
    points = pose['points']
    width, height = image.width(), image.height()
    eye_l, eye_r = points[0], points[1]
    cx = (points[4][0] + points[5][0]) * width / 2
    cy = (eye_l[1] + eye_r[1]) * height / 2
    fw = math.hypot((points[5][0] - points[4][0]) * width,
                    (points[5][1] - points[4][1]) * height)
    fh = math.hypot((points[3][0] - points[2][0]) * width,
                    (points[3][1] - points[2][1]) * height)
    if fw < 12 or fh < 12:
        return
    matrix = pose['matrix']
    fw /= max(.52, abs(float(matrix[0][0])))
    roll = math.degrees(math.atan2((eye_r[1]-eye_l[1])*height,
                                   (eye_r[0]-eye_l[0])*width))
    radians = math.radians(roll)
    co, si = math.cos(radians), math.sin(radians)
    def local(point):
        dx, dy = point[0]*width-cx, point[1]*height-cy
        return co*dx+si*dy, -si*dx+co*dy
    forehead_y = local(points[2])[1]
    nose_x, nose_y = local(points[6])
    # MediaPipe's canonical-face transform supplies head yaw. Shrink and fade
    # the far ear rather than letting it slide across the face on head turns.
    yaw = max(-.8, min(.8, float(matrix[0][2])))
    original = image.copy()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(cx, cy)
    painter.rotate(roll)
    for name in sorted(names):
        animal = 'puppy' if name.startswith('Puppy') else 'cat'
        sheet = _kit(animal)
        if sheet.isNull():
            continue
        for side in (-1, 1):
            far = max(0., side*yaw)
            scale = 1. - .48*far
            painter.setOpacity(1. - .30*far)
            ear_w = fw * (.65 if animal == 'puppy' else .53) * scale
            ear_h = fh * (.73 if animal == 'puppy' else .68)
            x = side*fw*.64 - ear_w/2
            base_y = forehead_y - fh*.36
            top = base_y - (ear_h*.20 if animal == 'puppy' else ear_h)
            source = QRectF(0 if side < 0 else 626, 0, 626, 760 if animal == 'puppy' else 700)
            painter.drawImage(QRectF(x,top,ear_w,ear_h),sheet,source)
        painter.setOpacity(1.)
    # Restore the actual forehead/face over ear roots. This gives convincing
    # depth without a brittle hair-segmentation or 3-D mesh rasterizer.
    painter.save()
    forehead = local(points[2])
    chin = local(points[3])
    face = QPainterPath()
    face.addEllipse(QRectF(-fw*.47,forehead[1]-fh*.45,fw*.94,
                           max(1.,chin[1]-forehead[1]+fh*.52)))
    painter.setClipPath(face)
    painter.rotate(-roll)
    painter.translate(-cx,-cy)
    painter.drawImage(0,0,original)
    painter.restore()
    for name in sorted(names):
        animal = 'puppy' if name.startswith('Puppy') else 'cat'
        sheet = _kit(animal)
        if sheet.isNull():
            continue
        muzzle_w = fw * (.55 if animal == 'puppy' else .90)
        muzzle_h = fh * (.33 if animal == 'puppy' else .37)
        source = QRectF(260,805,730,370) if animal == 'puppy' else QRectF(0,765,1254,485)
        painter.drawImage(QRectF(nose_x-muzzle_w/2,nose_y-fh*.07,muzzle_w,muzzle_h),sheet,source)
    painter.end()
