import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,MediaItem
from kinetic_cut.ui import MainWindow

class CompoundWaveformTests(unittest.TestCase):
    def test_obsolete_result_and_error_cannot_replace_new_source(self):
        with tempfile.TemporaryDirectory() as folder:
            first=Path(folder)/'first.wav'; first.touch()
            second=Path(folder)/'second.wav'; second.touch()
            w=MainWindow(); w.autosave_timer.stop(); jobs=[]
            try:
                media=MediaItem('audio',str(first),'audio','Audio',1,has_audio=True)
                with patch.object(w,'start_worker',side_effect=jobs.append):
                    w.set_project(Project(media=[media]))
                    old=jobs[-1]; media.path=str(second); w.request_waveform(media); new=jobs[-1]
                    old.signals.result.emit([.1]); old.signals.error.emit('old error'); old.signals.finished.emit()
                    self.assertNotIn(media.id,w.timeline.waveforms)
                    self.assertNotIn(media.id,w.timeline.waveform_failures)
                    self.assertIn(media.id,w.timeline.waveform_pending)
                    new.signals.result.emit([.5]); new.signals.finished.emit()
                    self.assertEqual(w.timeline.waveforms[media.id],[.5])
                    self.assertNotIn(media.id,w.timeline.waveform_pending)
            finally:w.close(); w.deleteLater(); QApplication.processEvents()

    def test_parent_child_switch_reuses_inflight_source_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'audio.wav'; path.touch()
            w=MainWindow(); w.autosave_timer.stop(); jobs=[]
            try:
                media=MediaItem('audio',str(path),'audio','Audio',1,has_audio=True)
                with patch.object(w,'start_worker',side_effect=jobs.append):
                    w.set_project(Project(media=[media])); job=jobs[-1]
                    w.set_project(Project()); w.set_project(Project(media=[media]))
                    self.assertEqual(len(jobs),1)
                    self.assertIn(media.id,w.timeline.waveform_pending)
                    job.signals.result.emit([.4]); job.signals.finished.emit()
                    self.assertEqual(w.timeline.waveforms[media.id],[.4])
            finally:w.close(); w.deleteLater(); QApplication.processEvents()
