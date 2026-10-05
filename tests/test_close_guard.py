import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtCore import QEvent, QThreadPool, QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project, MediaItem, TimelineItem, Caption
from kinetic_cut.close_guard import confirm_close, document_key, mark_saved


class CloseGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.app.setProperty('kineticTestDiscardUnsaved', False)
        self.w = MainWindow(); self.w.autosave_timer.stop()
        from kinetic_cut.config import DATA_DIR
        self.w.settings['last_open_project_dir']=str(DATA_DIR)
        self.w.set_project(Project(media=[MediaItem('m','missing.png','image','fixture',10,1920,1080)],
                                   timeline=[TimelineItem('v','m','video_1',0,2)]))

    def tearDown(self):
        self.app.setProperty('kineticTestDiscardUnsaved', True)
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000)
        self.w.deleteLater(); QApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.app.processEvents()

    def choose(self, answer):
        def click():
            box=self.app.activeModalWidget(); self.assertIsInstance(box,QMessageBox)
            QTest.mouseClick(box.button(answer),Qt.LeftButton)
        QTimer.singleShot(0,click)

    def test_empty_unsaved_and_bin_only_skip(self):
        self.w.project.timeline=[]
        with patch.object(QMessageBox,'exec',side_effect=AssertionError('Unexpected prompt')):
            self.assertTrue(confirm_close(self.w))

    def test_unchanged_saved_playhead_thumbnail_touch_skip(self):
        self.w.project.path='fixture.kcut'; mark_saved(self.w)
        self.w.project.playhead=1; self.w.project.touch(); self.w.project.media[0].thumbnail='new-cache.png'
        with patch.object(QMessageBox,'exec',side_effect=AssertionError('Unexpected prompt')):
            self.assertTrue(confirm_close(self.w))

    def test_unsaved_timeline_cancel_preserves_services(self):
        self.choose(QMessageBox.Cancel)
        with patch.object(self.w.compounds,'cancel') as cancel, patch.object(self.w.transport,'shutdown') as shutdown:
            event=QCloseEvent(); self.w.closeEvent(event)
            self.assertFalse(event.isAccepted()); cancel.assert_not_called(); shutdown.assert_not_called()

    def test_saved_edit_and_undo(self):
        self.w.project.path='fixture.kcut'; mark_saved(self.w)
        old=copy.deepcopy(self.w.project)
        self.w.project.timeline[0].transform.scale=2
        self.choose(QMessageBox.Cancel); self.assertFalse(confirm_close(self.w))
        self.w.project=old
        with patch.object(QMessageBox,'exec',side_effect=AssertionError('Unexpected prompt')):
            self.assertTrue(confirm_close(self.w))

    def test_saved_empty_after_delete_prompts(self):
        self.w.project.path='fixture.kcut'; mark_saved(self.w); self.w.project.timeline=[]
        self.choose(QMessageBox.Discard); self.assertTrue(confirm_close(self.w))

    def test_caption_only_unsaved_prompts(self):
        self.w.project.timeline=[]; self.w.project.captions=[Caption('c',0,1,'Hello')]
        self.choose(QMessageBox.Cancel); self.assertFalse(confirm_close(self.w))

    def test_save_success_and_save_cancel_or_failure(self):
        for result in (False,True):
            self.choose(QMessageBox.Save)
            with patch.object(self.w,'save_project',return_value=result) as save:
                self.assertEqual(confirm_close(self.w),result); save.assert_called_once_with()

    def test_actual_save_as_cancel_keeps_open(self):
        self.choose(QMessageBox.Save)
        with patch('kinetic_cut.ui.QFileDialog.getSaveFileName',return_value=('','')):
            self.assertFalse(confirm_close(self.w)); self.assertEqual(self.w.project.path,'')

    def test_actual_save_and_load_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            path=str(Path(temp)/'fixture.kcut')
            self.choose(QMessageBox.Save)
            with patch('kinetic_cut.ui.QFileDialog.getSaveFileName',return_value=(path,'')):
                self.assertTrue(confirm_close(self.w))
            self.assertTrue(Path(path).is_file()); self.assertEqual(self.w._saved_close_key,document_key(self.w.project))
            self.w.project.timeline[0].gain_db=3
            with patch.object(self.w,'confirm_project_switch',return_value=True): self.assertTrue(self.w.load_project_path(path))
            with patch.object(QMessageBox,'exec',side_effect=AssertionError('Unexpected prompt')): self.assertTrue(confirm_close(self.w))

    def test_save_error_prevents_shutdown(self):
        self.w.project.path='fixture.kcut'
        self.choose(QMessageBox.Save)
        with patch.object(Project,'save',side_effect=OSError('disk full')),patch('kinetic_cut.ui.QMessageBox.warning') as warning:
            self.assertFalse(confirm_close(self.w)); warning.assert_called_once()

    def test_compound_key_ignores_cache_but_not_nested_edits(self):
        p=copy.deepcopy(self.w.project); child=p.to_dict()
        p.media[0].compound=child; baseline=document_key(p)
        p.media[0].path='new-cache.mkv'; p.media[0].compound['playhead']=1
        self.assertEqual(document_key(p),baseline)
        p.media[0].compound['timeline'][0]['transform']['scale']=2
        self.assertNotEqual(document_key(p),baseline)

    def test_unsaved_clone_of_saved_document_still_prompts(self):
        self.w.project.path='fixture.kcut'; mark_saved(self.w); self.w.project.path=''
        self.choose(QMessageBox.Cancel); self.assertFalse(confirm_close(self.w))

    def test_escape_cancels_prompt(self):
        QTimer.singleShot(0,lambda:QTest.keyClick(self.app.activeModalWidget(),Qt.Key_Escape))
        self.assertFalse(confirm_close(self.w))


if __name__=='__main__': unittest.main()
