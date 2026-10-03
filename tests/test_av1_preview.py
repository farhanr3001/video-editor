import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QMainWindow

from kinetic_cut.model import MediaItem, Project, TimelineItem
from kinetic_cut.preview_quality import PreviewQuality
from kinetic_cut.media import generate_proxy


class AV1PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.source = Path(self.folder.name) / 'source.mp4'
        self.source.write_bytes(b'test fixture')
        self.window = QMainWindow()
        self.media = MediaItem('av1', str(self.source), 'video', 'source.mp4', 5, 1920, 1080,
                               60, True, video_codec='av1')
        self.window.project = Project(media=[self.media],
                                      timeline=[TimelineItem('clip', 'av1', 'video_1', 0, 5)])
        self.window.settings = {}
        self.window.proxies = {}
        self.window.preview = SimpleNamespace(caption_focus=False, frames={})
        calls = []
        self.window.transport = SimpleNamespace(closed=False, playing=False, decoders={},
                                                retire_decoder=lambda key: calls.append(key),
                                                sync=lambda force: calls.append(('sync', force)))
        self.calls = calls
        self.quality = PreviewQuality(self.window)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def test_full_mode_automatically_requests_compatible_preview(self):
        with patch.object(self.quality, '_start') as start:
            self.quality.request()
        self.assertEqual(start.call_args.args[:2], ('compat', self.media))
        self.assertTrue(self.quality.needs_compatible(self.media))

    def test_imported_av1_can_prepare_before_timeline_placement(self):
        self.window.project.timeline.clear()
        self.quality.extra_ids.add(self.media.id)
        with patch.object(self.quality, '_start') as start:
            self.quality.request()
        self.assertEqual(start.call_args.args[:2], ('compat', self.media))

    def test_compatibility_proxy_uses_available_decode_threads(self):
        cache = Path(self.folder.name) / 'cache'
        (cache / 'proxies').mkdir(parents=True)
        captured = {}
        progress = lambda fraction, message: None

        def render(args, duration, callback, cancel):
            captured.update(args=args, duration=duration, callback=callback)
            Path(args[-1]).write_bytes(b'encoded fixture')
            return 0, []

        with patch('kinetic_cut.media.CACHE_DIR', cache), \
             patch('kinetic_cut.exporter.automatic_encoder', return_value='CPU'), \
             patch('kinetic_cut.export_process.render', side_effect=render):
            result = generate_proxy(self.media, compatibility=True, progress=progress)
        self.assertTrue(Path(result).exists())
        self.assertEqual(captured['args'][captured['args'].index('-threads') + 1], '0')
        self.assertIs(captured['callback'], progress)

    def test_ready_preview_replaces_only_decoder_input_not_source(self):
        compatible = Path(self.folder.name) / 'compatible.mp4'
        compatible.write_bytes(b'compatible fixture')
        signature = self.quality._signature(self.media)
        self.quality.compat_ready[self.media.id] = str(compatible)
        self.quality.compat_signatures[self.media.id] = signature
        self.quality.apply(force=True)
        self.assertEqual(self.window.proxies[self.media.id], str(compatible))
        self.assertEqual(self.media.path, str(self.source))
        self.assertFalse(self.quality.needs_compatible(self.media))
        self.assertIn(('sync', True), self.calls)

    def test_cached_compatibility_preview_is_reapplied_after_project_switch(self):
        compatible = Path(self.folder.name) / 'compatible.mp4'
        compatible.write_bytes(b'compatible fixture')
        signature = self.quality._signature(self.media)
        self.quality.compat_ready[self.media.id] = str(compatible)
        self.quality.compat_signatures[self.media.id] = signature
        with patch.object(self.quality, '_start') as start:
            self.quality.request()
        self.assertEqual(self.window.proxies.get(self.media.id), str(compatible))
        start.assert_not_called()

    def test_unknown_legacy_codec_is_not_inspected_forever(self):
        self.media.video_codec = ''
        signature = self.quality._signature(self.media)
        with patch.object(self.quality, '_start') as start:
            self.quality.request()
            self.assertEqual(start.call_args.args[0], 'inspect')
            start.reset_mock()
            self.quality.inspected_codecs[self.media.id] = (signature, '')
            self.quality.request()
            start.assert_not_called()

    def test_codec_field_survives_project_roundtrip(self):
        restored = Project.from_dict(self.window.project.to_dict())
        self.assertEqual(restored.media[0].video_codec, 'av1')


if __name__ == '__main__':
    unittest.main()
