"""Small, byte-bounded caches for decoded CPU images, never native video frames."""
from collections import OrderedDict
import os
from threading import RLock

from PySide6.QtGui import QImage


class ImageCache:
    """Retain full-quality images within both an entry and a pixel-byte budget.

    Copies here are implicitly shared QImage handles, not extra pixel buffers.
    Each caller gets its own handle so painting/mutation detaches safely. The
    byte count deliberately overestimates if two entries share a pixel buffer.
    """
    def __init__(self, max_bytes, max_entries=64):
        self.max_bytes = max(0, int(max_bytes))
        self.max_entries = max(0, int(max_entries))
        self._images = OrderedDict()
        self._bytes = 0
        self._lock = RLock()

    @property
    def byte_count(self):
        with self._lock:
            return self._bytes

    def __len__(self):
        with self._lock:
            return len(self._images)

    def get(self, key):
        with self._lock:
            image = self._images.get(key)
            if image is None:
                return None
            self._images.move_to_end(key)
            return QImage(image)

    def put(self, key, image):
        with self._lock:
            old = self._images.pop(key, None)
            if old is not None:
                self._bytes -= old.sizeInBytes()
            size = image.sizeInBytes()
            # Oversize/null images still render normally; just don't retain them.
            if image.isNull() or size > self.max_bytes or not self.max_entries:
                return
            while self._images and (self._bytes + size > self.max_bytes
                                    or len(self._images) >= self.max_entries):
                _, evicted = self._images.popitem(last=False)
                self._bytes -= evicted.sizeInBytes()
            self._images[key] = QImage(image)
            self._bytes += size

    def clear(self):
        with self._lock:
            self._images.clear()
            self._bytes = 0


class FileImageCache(ImageCache):
    def load(self, path):
        path = os.path.normcase(os.path.abspath(os.fspath(path)))
        try:
            stat = os.stat(path)
        except OSError:
            return QImage()
        key = (path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        image = self.get(key)
        if image is None:
            image = QImage(path)
            self.put(key, image)
        return image
