"""Offscreen GPU rendering of motion graphics for export.

The same GpuMotion.qml that draws the live preview renders each export frame in a hidden Qt Quick window (Direct3D 11 on
Windows), so export matches the preview and nothing is rasterised by the CPU. Only the finished frame is read back for the
native compositor.
"""
import os
from PySide6.QtCore import Qt, QUrl, QRectF, QCoreApplication
from PySide6.QtGui import QColor, QImage, QMatrix4x4
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickView, QQuickItem
from . import motion_frame as F
from .motion_gpu import placement, opacity_of, scene_of


class MotionStage:
    def __init__(self, width, height):
        from .icons import resource_path
        self.width, self.height = int(width), int(height); self.scenes = {}; self.layers = {}; self.side_layers = {}; self.pair = None
        self.view = QQuickView(); self.view.setColor(QColor(0, 0, 0, 0)); self.view.setResizeMode(QQuickView.SizeRootObjectToView)
        self.view.setFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.view.setSource(QUrl.fromLocalFile(str(resource_path('assets', 'qml', 'GpuMotionStage.qml'))))
        if self.view.status() != QQuickView.Ready: raise RuntimeError('\n'.join(e.toString() for e in self.view.errors()))
        self.view.resize(self.width, self.height); self.view.setPosition(-self.width - 200, -self.height - 200)
        self.root = self.view.rootObject(); self.root.setWidth(self.width); self.root.setHeight(self.height)
        from .motion_video import install
        install(self.view.engine())
        self.component = QQmlComponent(self.view.engine(), QUrl.fromLocalFile(str(resource_path('assets', 'qml', 'GpuMotion.qml'))))
        self.view.show()

    def layer(self, key):
        item = self.layers.get(key)
        if item is None:
            item = self.component.create()
            if item is None: raise RuntimeError('\n'.join(e.toString() for e in self.component.errors()))
            item.setParent(self.root); item.setParentItem(self.root); self.layers[key] = item
        return item

    def _place(self, layer, item, elapsed, project, z, size):
        frame_rect = QRectF(0, 0, self.width, self.height); scene = scene_of(project, item, self.scenes)
        layer.setVisible(True); layer.setZ(z); layer.setWidth(self.width); layer.setHeight(self.height)
        layer.setProperty('k', self.width / max(1, scene.get('canvas', [project.settings.width])[0]))
        layer.setProperty('placement', QMatrix4x4(placement(item, project, frame_rect))); layer.setProperty('alpha', opacity_of(item, elapsed))
        layer.setProperty('frame', F.frame(scene, item.in_point + elapsed * item.speed, size, project.settings.fps))

    def render(self, entries, project, at_for):
        """entries: motion graphic items. at_for(item) -> seconds of the item's own clock. Returns an RGBA8888 QImage."""
        shown = set(); size = (self.width, self.height)
        if self.pair is not None: self.pair.setVisible(False)
        for z, item in enumerate(entries):
            elapsed = at_for(item)
            if opacity_of(item, elapsed) <= .001 or elapsed < 0: continue
            self._place(self.layer(item.id), item, elapsed, project, z, size); shown.add(item.id)
        for key, layer in self.layers.items():
            if key not in shown: layer.setVisible(False)
        QCoreApplication.processEvents()
        return self.view.grabWindow().convertToFormat(QImage.Format_RGBA8888)

    def render_transition(self, left, right, left_elapsed, right_elapsed, phase, mode, params, project):
        """Both graphics are drawn by the GPU and blended by the preview's transition shader. Returns RGBA8888."""
        from PySide6.QtGui import QVector4D
        size = (self.width, self.height)
        if self.pair is None:
            from .icons import resource_path
            component = QQmlComponent(self.view.engine(), QUrl.fromLocalFile(str(resource_path('assets', 'qml', 'GpuTransition.qml'))))
            self.pair = component.create()
            if self.pair is None: raise RuntimeError('\n'.join(e.toString() for e in component.errors()))
            self.pair.setParent(self.root); self.pair.setParentItem(self.root); self.pair.setWidth(self.width); self.pair.setHeight(self.height); self.pair.setZ(1000)
        for layer in self.layers.values(): layer.setVisible(False)
        self.pair.setVisible(True)
        for side, (item, elapsed, name) in enumerate(((left, left_elapsed, 'outgoing'), (right, right_elapsed, 'incoming'))):
            key = 'T%d:%s' % (side, item.id); layer = self.side_layers.get(key)
            if layer is None:
                layer = self.component.create()
                if layer is None: raise RuntimeError('\n'.join(e.toString() for e in self.component.errors()))
                parent = self.pair.findChild(QQuickItem, name); layer.setParent(parent); layer.setParentItem(parent); self.side_layers[key] = layer
            self._place(layer, item, max(0., elapsed), project, 0, size)
        self.pair.setProperty('shader', f'../shaders/transition_{mode}.frag.qsb'); self.pair.setProperty('progress', float(phase))
        self.pair.setProperty('p1', QVector4D(*params[:3], 0)); self.pair.setProperty('p2', QVector4D(*params[3:], self.width / max(1, self.height)))
        QCoreApplication.processEvents()
        return self.view.grabWindow().convertToFormat(QImage.Format_RGBA8888)

    def close(self):
        self.view.close(); self.view.deleteLater()


_STAGES = {}


def scene_image(scene, seconds, size, fps=60):
    """Render one composition frame (transparent background unless the scene has one) on the GPU. Used by MCP previews,
    contact sheets and the asset picker thumbnails, so what the assistant sees is what playback and export draw."""
    from types import SimpleNamespace
    width, height = max(2, int(size[0])), max(2, int(size[1]))
    stage = _STAGES.get((width, height))
    if stage is None:
        while len(_STAGES) >= 3: _STAGES.pop(next(iter(_STAGES))).close()
        stage = _STAGES[(width, height)] = MotionStage(width, height)
    canvas = scene.get('canvas', [width, height])
    transform = SimpleNamespace(x=.5, y=.5, anchor_x=0, anchor_y=0, rotation=0, scale=1, effective_scale_y=1)
    item = SimpleNamespace(id='__scene_image__', role='graphic', graphic_type='Motion Composition', graphic_data={'scene': scene}, start=0.,
                           duration=1e9, in_point=float(seconds), speed=1., fade_in=0, fade_out=0, opacity=100., transform=transform)
    project = SimpleNamespace(settings=SimpleNamespace(width=int(canvas[0]), height=int(canvas[1]), fps=fps))
    stage.scenes.clear()
    return stage.render([item], project, lambda _: 0.)
