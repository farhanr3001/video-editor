"""View-dependent 3D-model face props for preview and lossless export.

The transparent views are rendered from actual GLB meshes at build time. A
MediaPipe face-pose matrix selects their yaw/pitch, while live landmarks place
and roll the prop. This avoids a GPU readback or a second 3D scene on each
timeline frame. It is not a deforming face mesh or live depth-buffer renderer.
"""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter

from .icons import resource_path


AR_FILTERS = {
    'AR Plague Mask': ('ar-plague', 2.78, .50, .545),
    'AR Pixel Glasses': ('ar-pixel-glasses', 1.34, .50, .50),
}
YAW_MIN, YAW_MAX, YAW_STEP = -60, 60, 6
PITCH_MIN, PITCH_MAX, PITCH_STEP = -20, 20, 10


def head_angles(matrix):
    """Extract bounded face yaw/pitch/roll from MediaPipe's rigid 4x4 pose."""
    yaw = math.degrees(math.atan2(float(matrix[0][2]), float(matrix[2][2])))
    pitch = math.degrees(math.atan2(-float(matrix[1][2]),
                                    math.hypot(float(matrix[1][0]), float(matrix[1][1]))))
    roll = math.degrees(math.atan2(float(matrix[1][0]), float(matrix[1][1])))
    return yaw, pitch, roll


def view_angles(matrix):
    yaw, pitch, _ = head_angles(matrix)
    yaw = min(YAW_MAX, max(YAW_MIN, round(yaw / YAW_STEP) * YAW_STEP))
    pitch = min(PITCH_MAX, max(PITCH_MIN, round(pitch / PITCH_STEP) * PITCH_STEP))
    return yaw, pitch


@lru_cache(maxsize=16)
def _view(folder, yaw, pitch):
    return QImage(str(resource_path('assets', 'face_filters', folder,
                                    f'y{yaw:+03d}_p{pitch:+03d}.png')))


def paint_ar_filters(image: QImage, pose: dict | None, names: set[str]):
    if not pose or not names:
        return
    points = pose['points']
    width, height = image.width(), image.height()
    eye_left, eye_right = points[:2]
    eye_x = (eye_left[0] + eye_right[0]) * width / 2
    eye_y = (eye_left[1] + eye_right[1]) * height / 2
    face_width = math.hypot((points[5][0] - points[4][0]) * width,
                            (points[5][1] - points[4][1]) * height)
    if face_width < 12:
        return
    matrix = pose['matrix']
    yaw, pitch = view_angles(matrix)
    # The measured temple-to-temple distance contracts with yaw. Restore the
    # unrotated face scale; the view already contains the model's 3D foreshortening.
    face_width /= max(.48, abs(float(matrix[0][0])))
    roll = math.degrees(math.atan2((eye_right[1] - eye_left[1]) * height,
                                   (eye_right[0] - eye_left[0]) * width))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(eye_x, eye_y)
    painter.rotate(roll)
    for name in sorted(names):
        folder, size, anchor_x, anchor_y = AR_FILTERS[name]
        view = _view(folder, yaw, pitch)
        if view.isNull():
            continue
        extent = max(1.0, face_width * size)
        painter.drawImage(QRectF(-extent * anchor_x, -extent * anchor_y,
                                 extent, extent), view)
    painter.end()
