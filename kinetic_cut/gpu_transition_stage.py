"""GPU compositing of paired transitions for the compatibility export path.

The compatibility exporter used to blend every transition frame with a numpy CPU compositor. This module renders the very same
Qt Quick transition shaders the live preview uses (assets/shaders/transition_N.frag.qsb) in a producer process: the parent streams
the two source frames in, the GPU blends them, and the finished frame comes back. The Qt Quick window lives in its own process,
so this works from export worker threads.
"""
import os, struct, sys
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QCoreApplication, QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlComponent
from PySide6.QtQuick import QQuickView, QQuickItem, QQuickImageProvider


class _Frames(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image); self.images = {}
    def requestImage(self, identifier, size, requested):
        image = self.images.get(identifier.split('?')[0], QImage())
        return image


class TransitionStage:
    def __init__(self, width, height):
        from .icons import resource_path
        self.width, self.height = int(width), int(height); self.count = 0
        self.view = QQuickView(); self.view.setColor(QColor(0, 0, 0, 0)); self.view.setResizeMode(QQuickView.SizeRootObjectToView)
        self.view.setFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.provider = _Frames(); self.view.engine().addImageProvider('tframes', self.provider)
        self.view.setSource(QUrl.fromLocalFile(str(resource_path('assets', 'qml', 'GpuMotionStage.qml'))))
        if self.view.status() != QQuickView.Ready: raise RuntimeError('\n'.join(e.toString() for e in self.view.errors()))
        self.view.resize(self.width, self.height); self.view.setPosition(-self.width - 200, -self.height - 200)
        self.root = self.view.rootObject(); self.root.setWidth(self.width); self.root.setHeight(self.height)
        component = QQmlComponent(self.view.engine(), QUrl.fromLocalFile(str(resource_path('assets', 'qml', 'GpuTransition.qml'))))
        self.pair = component.create()
        if self.pair is None: raise RuntimeError('\n'.join(e.toString() for e in component.errors()))
        self.pair.setParent(self.root); self.pair.setParentItem(self.root); self.pair.setWidth(self.width); self.pair.setHeight(self.height)
        image = QQmlComponent(self.view.engine()); image.setData(b'import QtQuick\nImage { anchors.fill: parent; cache: false; asynchronous: false; smooth: true; fillMode: Image.Stretch }', QUrl())
        self.sides = []
        for name in ('outgoing', 'incoming'):
            item = image.create(); parent = self.pair.findChild(QQuickItem, name)
            item.setParent(parent); item.setParentItem(parent); self.sides.append(item)
        self.view.show()

    def render(self, left, right, phase, mode, params, aspect):
        """left/right: RGBA8888 QImage; phase already eased. Returns an RGBA8888 QImage."""
        from PySide6.QtGui import QVector4D
        self.count += 1
        for key, image, item in (('L', left, self.sides[0]), ('R', right, self.sides[1])):
            name = f'{key}{self.count}'; self.provider.images[name] = image; item.setProperty('source', f'image://tframes/{name}')
        self.pair.setProperty('shader', f'../shaders/transition_{mode}.frag.qsb')
        self.pair.setProperty('progress', float(phase))
        self.pair.setProperty('p1', QVector4D(*params[:3], 0)); self.pair.setProperty('p2', QVector4D(*params[3:], aspect))
        QCoreApplication.processEvents()
        result = self.view.grabWindow().convertToFormat(QImage.Format_RGBA8888)
        self.provider.images.clear()
        return result

    def close(self):
        self.view.close(); self.view.deleteLater()


def _read(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk: return None
        data += chunk
    return bytes(data)


def serve(spec):
    """Producer loop: [phase f32][left RGBA][right RGBA] in, [result RGBA] out, until stdin closes."""
    from .export_preview_source import write_pixels
    width, height, mode, params = spec['width'], spec['height'], spec['mode'], spec['params']
    stage = TransitionStage(width, height); size = width * height * 4; source = sys.stdin.buffer
    try:
        while True:
            head = _read(source, 4)
            if head is None: return 0
            left = _read(source, size); right = _read(source, size)
            if left is None or right is None: return 1
            a = QImage(left, width, height, width * 4, QImage.Format_RGBA8888).copy(); b = QImage(right, width, height, width * 4, QImage.Format_RGBA8888).copy()
            image = stage.render(a, b, struct.unpack('<f', head)[0], mode, params, width / max(1, height))
            write_pixels(bytes(image.constBits())[:size])
    finally:
        stage.close()


class Client:
    """Parent-side handle: composite(a, b, phase) -> RGBA8888 QImage, drawn by the GPU in a producer process."""
    def __init__(self, project, transition, directory, check=None):
        import json, subprocess
        from .animated_transitions import descriptor
        data = descriptor(transition); self.width, self.height = project.settings.width, project.settings.height
        spec = Path(directory) / ('gpu-transition-%s.json' % transition.id)
        spec.write_text(json.dumps(dict(gpu_transition=True, width=self.width, height=self.height, mode=data['mode'], params=list(data['params']))), encoding='utf-8')
        command = [sys.executable] + ([] if getattr(sys, 'frozen', False) else [str(Path(__file__).resolve().parent.parent / 'main.py')]) + ['--preview-effect-source', str(spec)]
        self.log = spec.with_suffix('.log').open('wb')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.size = self.width * self.height * 4

    def _bytes(self, image):
        if image is None or image.isNull(): return bytes(self.size)
        if image.width() != self.width or image.height() != self.height: image = image.scaled(self.width, self.height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        image = image.convertToFormat(QImage.Format_RGBA8888)
        return bytes(image.constBits())[:self.size]

    def composite(self, a, b, phase):
        self.process.stdin.write(struct.pack('<f', phase) + self._bytes(a) + self._bytes(b)); self.process.stdin.flush()
        data = _read(self.process.stdout, self.size)
        if data is None: raise RuntimeError('GPU transition renderer stopped (exit %s)' % self.process.poll())
        return QImage(data, self.width, self.height, self.width * 4, QImage.Format_RGBA8888).copy()

    def close(self):
        try: self.process.stdin.close()
        except OSError: pass
        try: self.process.wait(timeout=10)
        except Exception: self.process.kill()
        try: self.process.stdout.close()
        except OSError: pass
        self.log.close()
