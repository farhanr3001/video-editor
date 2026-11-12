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
        self.window.preview = SimpleNamespace( frames={})
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

    def test_simultaneous_proxy_writers_own_separate_temporary_files(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        cache=Path(self.folder.name)/'cache'
        (cache/'proxies').mkdir(parents=True)
        barrier=threading.Barrier(2)
        pending=[]
        def render(args,*unused):
            path=Path(args[-1]);pending.append(path)
            path.write_bytes(b'complete proxy')
            barrier.wait(timeout=5)
            return 0,[]
        with patch('kinetic_cut.media.CACHE_DIR',cache), \
             patch('kinetic_cut.exporter.automatic_encoder',return_value='CPU'), \
             patch('kinetic_cut.export_process.render',side_effect=render), \
             ThreadPoolExecutor(2) as pool:
            paths=list(pool.map(lambda _:generate_proxy(self.media),range(2)))
        self.assertEqual(paths[0],paths[1])
        self.assertNotEqual(pending[0],pending[1])
        self.assertEqual(Path(paths[0]).read_bytes(),b'complete proxy')
        self.assertFalse(any(p.exists() for p in pending))

    def test_failed_proxy_removes_its_temporary_file(self):
        cache=Path(self.folder.name)/'cache'
        (cache/'proxies').mkdir(parents=True)
        with patch('kinetic_cut.media.CACHE_DIR',cache), \
             patch('kinetic_cut.exporter.automatic_encoder',return_value='CPU'), \
             patch('kinetic_cut.export_process.render',side_effect=RuntimeError('stopped')):
            with self.assertRaisesRegex(RuntimeError,'stopped'):generate_proxy(self.media)
        self.assertEqual(list((cache/'proxies').iterdir()),[])

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
        self.assertIn(('sync', False), self.calls)  # Only reopened video needs positioning; audio continues.

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

    def test_optional_seek_proxy_restored_during_play_waits_for_pause(self):
        self.media.video_codec='h264'
        self.window.start_worker=lambda worker:None
        cached=Path(self.folder.name)/'full-seek.mp4';cached.write_bytes(b'complete')
        key=(self.media.id,0.,1.,'video')
        self.window.transport.decoders[key]=object()
        self.window.transport.playing=True
        with patch('kinetic_cut.media.proxy_path',return_value=cached),patch.object(self.quality,'_start'):
            self.quality.request()
        self.assertEqual(self.window.proxies,{})
        self.assertEqual(self.calls,[])
        self.assertEqual(self.quality.seek_ready[self.media.id],str(cached))
        self.window.transport.playing=False;self.quality.apply()
        self.assertEqual(self.window.proxies[self.media.id],str(cached))
        self.assertIn(key,self.calls)

    def test_completed_seek_copy_does_not_interrupt_playing_original(self):
        self.media.video_codec='h264'
        cached=Path(self.folder.name)/'completed.mp4';cached.write_bytes(b'complete')
        self.window.transport.playing=True
        workers=[];self.window.start_worker=workers.append
        self.quality._start('seek',self.media,self.quality._signature(self.media))
        workers[0].signals.result.emit(str(cached))
        self.assertEqual(self.window.proxies,{})
        self.assertEqual(self.calls,[])
        self.window.transport.playing=False;self.quality.apply()
        self.assertEqual(self.window.proxies[self.media.id],str(cached))

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
