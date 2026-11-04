"""Video layers inside motion compositions.

Frames are decoded frame-accurately with FFmpeg (PyAV, the export decoder) and handed to Qt Quick through an image
provider, so the GPU draws them as textures in the editor canvas, the live preview and the export stage alike. The same
code path everywhere keeps preview and export identical. Video layers are silent; add sound with timeline audio or cues.
"""
import threading
import time
import urllib.parse
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

PROVIDER = 'motionvideo'


class Frames:
    """Keeps a forward-decoding reader per file; backwards or far jumps reopen at the target (exact seek)."""
    def __init__(self, limit=8):
        self.lock = threading.Lock(); self.readers = {}; self.durations = {}; self.limit = limit

    def duration(self, path):
        if path not in self.durations:
            try:
                import av
                with av.open(path) as movie:
                    stream = movie.streams.video[0]
                    seconds = float(stream.duration * stream.time_base) if stream.duration else float(movie.duration or 0) / 1e6
            except Exception: seconds = 0.
            self.durations[path] = seconds
        return self.durations[path]

    def image(self, path, seconds):
        seconds = max(0., float(seconds))
        with self.lock:
            entry = self.readers.get(path)
            if entry is None or seconds < entry['t'] - 1e-6 or seconds > entry['t'] + 2.:
                if entry: entry['reader'].close()
                from .gpu_export_decode import Source
                entry = self.readers[path] = {'reader': Source(path, seconds), 't': seconds, 'used': 0.}
                while len(self.readers) > self.limit:
                    oldest = min(self.readers, key=lambda key: self.readers[key]['used'])
                    self.readers.pop(oldest)['reader'].close()
            pixels = entry['reader'].frame(seconds); entry['t'] = seconds; entry['used'] = time.monotonic()
            height, width = pixels.shape[:2]
            return QImage(pixels.data, width, height, width * 4, QImage.Format_RGBA8888).copy()

    def close(self):
        with self.lock:
            for entry in self.readers.values(): entry['reader'].close()
            self.readers.clear()


FRAMES = Frames()


def url(path, seconds):
    return 'image://%s/%s?t=%.4f' % (PROVIDER, urllib.parse.quote(path, safe=''), seconds)


def parse(identifier):
    path, _, query = identifier.partition('?')
    seconds = float(urllib.parse.parse_qs(query).get('t', ['0'])[0])
    return urllib.parse.unquote(path), seconds


class Provider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)

    def requestImage(self, identifier, size, requested):
        try:
            path, seconds = parse(identifier); image = FRAMES.image(path, seconds)
        except Exception:
            image = QImage(2, 2, QImage.Format_RGBA8888); image.fill(Qt.transparent)
        if requested is not None and requested.width() > 0 and requested.height() > 0 and image.width() > requested.width() * 1.5:
            image = image.scaled(requested, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if size is not None: size.setWidth(image.width()); size.setHeight(image.height())
        return image


def install(engine):
    """Register the video frame provider on a QML engine once (editor canvas, live preview, export stage)."""
    if engine is not None and engine.imageProvider(PROVIDER) is None:
        engine.addImageProvider(PROVIDER, Provider())


def source_time(node, t):
    """Composition time -> seconds inside the video file (in_point, speed, optional loop)."""
    local = max(0., t - node.get('start', 0.)); seconds = node.get('in_point', 0.) + local * node.get('speed', 1.)
    if node.get('loop'):
        length = FRAMES.duration(node.get('source', ''))
        if length > 0: seconds = node.get('in_point', 0.) + (seconds - node.get('in_point', 0.)) % max(.04, length - node.get('in_point', 0.))
    return seconds
