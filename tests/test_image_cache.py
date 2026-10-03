import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from kinetic_cut.image_cache import ImageCache, FileImageCache
from kinetic_cut.model import Project, MediaItem, TimelineItem
from kinetic_cut.widgets import PreviewCanvas


def solid(color='red', width=16, height=16):
    image = QImage(width, height, QImage.Format_RGBA8888)
    image.fill(QColor(color))
    return image


class ImageCacheTests(unittest.TestCase):
    def test_byte_entry_limits_lru_replacement_and_clear(self):
        image = solid()
        size = image.sizeInBytes()
        cache = ImageCache(size*2, 3)
        cache.put('a', image); cache.put('b', image)
        self.assertEqual(cache.byte_count, size*2)
        cache.get('a')
        cache.put('c', image)
        self.assertIsNone(cache.get('b'))
        self.assertIsNotNone(cache.get('a'))
        cache.put('a', solid(width=8, height=8))
        self.assertEqual(cache.byte_count, size+256)
        for n in range(1000):
            cache.put(n, image)
            self.assertLessEqual(cache.byte_count, cache.max_bytes)
        cache.clear()
        self.assertEqual(len(cache), 0); self.assertEqual(cache.byte_count, 0)
        cache = ImageCache(size*10, 1)
        cache.put('a', image); cache.put('b', image)
        self.assertIsNone(cache.get('a')); self.assertEqual(len(cache), 1)

    def test_handles_detach_without_changing_cached_pixels(self):
        image = solid(); cache = ImageCache(4096)
        cache.put('a', image)
        result = cache.get('a')
        self.assertEqual(result.cacheKey(), image.cacheKey())
        result.fill(QColor('blue')); image.fill(QColor('green'))
        self.assertEqual(cache.get('a').pixelColor(0, 0), QColor('red'))

    def test_oversize_and_null_do_not_evict_useful_entries(self):
        cache = ImageCache(1024); cache.put('a', solid())
        cache.put('large', solid(width=64, height=64)); cache.put('null', QImage())
        self.assertEqual(len(cache), 1); self.assertIsNotNone(cache.get('a'))

    def test_file_reuse_change_missing_and_reappearance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'image.png'; solid().save(str(path))
            cache = FileImageCache(4096)
            with patch('kinetic_cut.image_cache.QImage', wraps=QImage) as constructor:
                first = cache.load(path); second = cache.load(path)
                decodes = [c for c in constructor.call_args_list if c.args and isinstance(c.args[0], str)]
                self.assertEqual(len(decodes), 1)
                self.assertEqual(first.cacheKey(), second.cacheKey())
            before = path.stat()
            solid('blue').save(str(path))
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns+1_000_000))
            self.assertEqual(cache.load(path).pixelColor(0, 0), QColor('blue'))
            path.unlink(); self.assertTrue(cache.load(path).isNull())
            solid('green').save(str(path))
            self.assertEqual(cache.load(path).pixelColor(0, 0), QColor('green'))

    def test_missing_mask_is_not_sticky_and_deleted_cached_mask_is_not_returned(self):
        from kinetic_cut.vision_effects import mask_image
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'masks'/'00000000.png'; path.parent.mkdir()
            self.assertTrue(mask_image(directory, 0).isNull())
            solid().save(str(path)); self.assertFalse(mask_image(directory, 0).isNull())
            path.unlink(); self.assertTrue(mask_image(directory, 0).isNull())
        mask_image.cache_clear()

    def test_canvas_still_reuses_source_and_effect_pixels_without_quality_loss(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'still.png'; original = solid(width=64, height=64); original.save(str(path))
            canvas = PreviewCanvas()
            p = Project(media=[MediaItem('m',str(path),'image','Still',3,64,64)])
            item = TimelineItem('v','m',p.video_tracks[0],0,3)
            item.effects=[dict(name='Gaussian Blur',horizontal=12,vertical=12)]
            p.timeline=[item]; canvas.set_project(p)
            a = canvas._visible_items()[0][1]; b = canvas._visible_items()[0][1]
            self.assertEqual(a.convertToFormat(original.format()), original)
            self.assertEqual(a.cacheKey(), b.cacheKey())
            rect = QRectF(0,0,64,64)
            first = canvas._prepare_layer_image(item,a,rect,rect)
            with patch('kinetic_cut.visuals.blur_image', side_effect=AssertionError('unchanged still re-filtered')):
                second = canvas._prepare_layer_image(item,b,rect,rect)
            self.assertEqual(first.cacheKey(), second.cacheKey())
            canvas.set_project(Project()); self.assertEqual(canvas.still_cache.byte_count, 0)
            canvas.close(); canvas.deleteLater(); app.processEvents()
