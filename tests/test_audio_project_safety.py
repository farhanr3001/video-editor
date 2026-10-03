import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PySide6.QtCore import QByteArray
from PySide6.QtMultimedia import QAudioBuffer, QAudioFormat

from kinetic_cut.audio_levels import channel_peaks, peak_db
from kinetic_cut.model import MediaItem, Project
from kinetic_cut.project_safety import collect_project, preserve_version, versions


class AudioProjectSafetyTests(unittest.TestCase):
    def test_live_buffer_peak_stereo_and_mono(self):
        fmt = QAudioFormat(); fmt.setSampleRate(48000); fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.Float)
        data = np.array([.2, -.3, .4, -.5], dtype=np.float32)
        buffer = QAudioBuffer(QByteArray(data.tobytes()), fmt)
        left, right = channel_peaks(buffer)
        self.assertAlmostEqual(left, .4, places=5)
        self.assertAlmostEqual(right, .5, places=5)
        self.assertAlmostEqual(peak_db(1), 0)
        fmt.setChannelCount(1); fmt.setSampleFormat(QAudioFormat.Int16)
        mono = QAudioBuffer(QByteArray(np.array([-16384, 8192], dtype=np.int16).tobytes()), fmt)
        self.assertEqual(channel_peaks(mono), (.5, .5))

    def test_versions_keep_previous_saved_document(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'edit.kcut'
            project = Project(name='One'); project.save(path)
            original = path.read_bytes()
            saved = preserve_version(path)
            self.assertEqual(saved.read_bytes(), original)
            project.name = 'Two'; project.save(path)
            self.assertEqual(Project.load(versions(path)[0]).name, 'One')
            self.assertEqual(Project.load(path).name, 'Two')

    def test_collect_nested_sources_and_move_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / 'one' / 'clip.mp4'; first.parent.mkdir(); first.write_bytes(b'first')
            second = root / 'two' / 'clip.mp4'; second.parent.mkdir(); second.write_bytes(b'second')
            thumb = root / 'preview.jpg'; thumb.write_bytes(b'preview')
            child = Project(name='Child', media=[MediaItem('child', str(second), 'video', second.name)])
            parent = Project(name='Portable', media=[MediaItem('first', str(first), 'video', first.name, thumbnail=str(thumb)),
                                                     MediaItem('compound', 'old-cache.mkv', 'video', 'Nested', compound=child.to_dict())])
            original = copy.deepcopy(parent.to_dict())
            output = collect_project(parent, root / 'Collected')
            self.assertEqual(parent.to_dict(), original)
            self.assertEqual(len(list((root / 'Collected' / 'Media').iterdir())), 2)
            moved = root / 'Relocated'
            (root / 'Collected').rename(moved)
            loaded = Project.load(moved / output.name)
            self.assertTrue(loaded.portable_media)
            self.assertEqual(Path(loaded.media[0].path).read_bytes(), b'first')
            self.assertEqual(Path(loaded.media[0].thumbnail).read_bytes(), b'preview')
            self.assertEqual(Path(loaded.media[1].compound['media'][0]['path']).read_bytes(), b'second')
            self.assertEqual(loaded.media[1].path, '')
            loaded.save(moved / output.name)
            reloaded = Project.load(moved / output.name)
            self.assertEqual(Path(reloaded.media[0].path).read_bytes(), b'first')

    def test_missing_source_does_not_publish_project(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'Collected'
            project = Project(media=[MediaItem('missing', str(Path(temp) / 'gone.mp4'), 'video', 'gone.mp4')])
            with self.assertRaises(FileNotFoundError):collect_project(project, destination)
            self.assertFalse(destination.exists())

    def test_inspector_levels_and_track_meter_receive_preview_peaks(self):
        from PySide6.QtWidgets import QApplication
        from kinetic_cut.model import TimelineItem
        from kinetic_cut.ui import MainWindow
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        try:
            window.request_waveform = lambda media: None
            project = Project(media=[MediaItem('sound', 'unavailable.wav', 'audio', 'Sound')],
                              timeline=[TimelineItem('clip', 'sound', 'audio_1', 0, 2)])
            window.set_project(project)
            window.inspector.select('clip')
            self.assertEqual(window.inspector.audio_subtabs.count(), 2)
            window.transport.levelsChanged.emit({'audio_1': (.5, .25, True)})
            app.processEvents()
            self.assertGreater(window.inspector.level_bars[0].value(), 0)
            self.assertIn('CLIP', window.inspector.level_clip.text())
            self.assertTrue(window.timeline._audio_levels['audio_1'][2])
            window.transport.levelsChanged.emit({})
            app.processEvents()
            self.assertEqual(window.inspector.level_bars[0].value(), 0)
        finally:
            window.close()


if __name__ == '__main__':
    unittest.main()
