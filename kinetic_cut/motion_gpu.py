"""GPU motion graphics layers for the live preview.

A motion composition is never rasterised on the CPU: Python evaluates the keyframes into a small frame description
(`motion_frame.frame`) and `assets/qml/GpuMotion.qml` draws it on the GPU in the preview's own Qt Quick scene.
"""
import json
from PySide6.QtCore import QRectF
from PySide6.QtGui import QTransform, QMatrix4x4
from . import motion as M
from . import motion_frame as F


def is_motion(item):
    from .motion_presets import PRESETS
    kind = getattr(item, 'graphic_type', '').lower()
    if item.role != 'graphic' or not isinstance(getattr(item, 'graphic_data', None), dict): return False
    return (kind in ('motion', 'motion composition') or getattr(item, 'graphic_type', '') in PRESETS) and isinstance(item.graphic_data.get('scene'), dict)


def scene_of(project, item, cache):
    raw = item.graphic_data.get('scene', {}); key = id(raw)
    hit = cache.get(key)
    if hit is None or hit[0] is not raw:
        scene = {**raw, 'canvas': raw.get('canvas', [project.settings.width, project.settings.height])}
        try: scene = M.validate(scene)
        except Exception: pass
        cache[key] = hit = (raw, scene)
        if len(cache) > 64: cache.pop(next(iter(cache)))
    return hit[1]


def placement(item, project, frame_rect):
    sf = frame_rect.width() / max(1., float(project.settings.width)); w, h = project.settings.width, project.settings.height
    t = item.transform; m = QTransform()
    m.translate(frame_rect.left() + t.x * frame_rect.width(), frame_rect.top() + t.y * frame_rect.height())
    m.translate(t.anchor_x * sf, t.anchor_y * sf); m.rotate(t.rotation); m.scale(t.scale * sf, t.effective_scale_y * sf); m.translate(-t.anchor_x, -t.anchor_y)
    m.translate(-w / 2, -h / 2); m.scale(1 / sf, 1 / sf)
    return m


def opacity_of(item, elapsed):
    fade = min(1., max(0., elapsed / item.fade_in)) if getattr(item, 'fade_in', 0) > 0 else 1.
    if getattr(item, 'fade_out', 0) > 0: fade *= min(1., max(0., (item.duration - elapsed) / item.fade_out))
    return (getattr(item, 'opacity', 100.) / 100.) * fade


class MotionLayers:
    """Owns one GpuMotion.qml item per visible motion graphic."""
    def __init__(self, surface):
        self.surface = surface; self.layers = {}; self.scenes = {}; self.frame_ms = 0.; self.count = 0

    def update(self, items, project, at, frame_rect, z):
        import time
        started = time.perf_counter(); shown = set()
        for item in items:
            elapsed = at - item.start; alpha = opacity_of(item, elapsed)
            if alpha <= .001: continue
            key = 'motion:' + item.id; layer = self.layers.get(key)
            if layer is None:
                try:
                    from .motion_video import install
                    install(self.surface.view.engine())
                except Exception: pass
                layer = self.surface.create('GpuMotion.qml', self.surface.item('canvas')); self.layers[key] = layer
            size = (max(2, round(frame_rect.width())), max(2, round(frame_rect.height())))
            scene = scene_of(project, item, self.scenes)
            description = F.frame(scene, item.in_point + elapsed * item.speed, size, project.settings.fps)
            layer.setVisible(True); layer.setZ(z); layer.setWidth(size[0]); layer.setHeight(size[1])
            layer.setProperty('k', size[0] / max(1, scene.get('canvas', [project.settings.width])[0]))
            layer.setProperty('placement', QMatrix4x4(placement(item, project, frame_rect)))
            layer.setProperty('alpha', alpha); layer.setProperty('frame', description); shown.add(key)
        for key, layer in self.layers.items():
            if key not in shown: layer.setVisible(False)
        self.count = len(shown); self.frame_ms = (time.perf_counter() - started) * 1000
        return shown

    def close(self):
        for layer in self.layers.values(): layer.deleteLater()
        self.layers.clear()
