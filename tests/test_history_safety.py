import copy
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QThreadPool
from PySide6.QtWidgets import QApplication

from kinetic_cut.model import Caption, MediaItem, Project, TimelineItem
from kinetic_cut.ui import MainWindow


class HistorySafetyTests(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow()
        self.w.autosave_timer.stop()

    def tearDown(self):
        self.w.close()
        QThreadPool.globalInstance().waitForDone(10000)
        self.w.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QApplication.processEvents()

    def test_same_id_media_restore_updates_pool_but_clip_only_edit_does_not(self):
        media = MediaItem('m', 'original.mp4', 'video', 'Original', 5, 640, 360)
        self.w.set_project(Project(media=[media], captions=[Caption('c', 0, 2, 'One')]))
        self.w.media_panel.folder = 'project'
        media.name = 'Relinked'
        media.path = 'replacement.mp4'
        media.width = 1920
        self.w.commit_history()
        self.w.refresh_media()
        self.w.undo()
        row = self.w.media_panel.grid.item(0)
        self.assertEqual(row.text(), 'Original')
        self.assertEqual(row.toolTip(), 'original.mp4')
        self.w.redo()
        self.assertEqual(self.w.media_panel.grid.item(0).text(), 'Relinked')
        self.w.project.captions[0].start = .5
        self.w.commit_history()
        with patch.object(self.w, 'refresh_media', wraps=self.w.refresh_media) as refresh:
            self.w.undo()
            self.w.redo()
            refresh.assert_not_called()

    def test_restored_source_replaces_waveform_after_history_settles(self):
        media = MediaItem('m', 'original.mp4', 'video', 'Audio', 5, has_audio=True)
        jobs = []
        with patch.object(self.w, 'start_worker', side_effect=jobs.append):
            self.w.set_project(Project(media=[media]))
            jobs[-1].signals.result.emit([.1])
            jobs[-1].signals.finished.emit()
            media.path = 'replacement.mp4'
            self.w.request_waveform(media)
            replacement = jobs[-1]
            replacement.signals.result.emit([.9])
            replacement.signals.finished.emit()
            self.w.commit_history()
            self.w.undo()
            self.w._history_settle_timer.stop()
            self.w._on_history_settled()
            self.assertEqual(len(jobs), 3)
            self.assertNotIn('m', self.w.timeline.waveforms)
            replacement.signals.result.emit([.9])
            self.assertNotIn('m', self.w.timeline.waveforms)
            jobs[-1].signals.result.emit([.1])
            jobs[-1].signals.finished.emit()
            self.assertEqual(self.w.timeline.waveforms['m'], [.1])

    def test_new_caption_typing_after_undo_branches_without_losing_text(self):
        self.w.set_project(Project(captions=[Caption('c', 0, 2, 'One')]))
        self.w.timeline.select_captions({'c'}, 'c')
        self.w.inspector.caption_text.setPlainText('Two')
        self.w.flush_text_edit()
        self.w.undo()
        self.w.inspector.caption_text.setPlainText('New branch')
        self.w.redo()
        self.assertEqual(self.w.project.captions[0].text, 'New branch')
        self.w.undo()
        self.assertEqual(self.w.project.captions[0].text, 'One')
        self.w.redo()
        self.assertEqual(self.w.project.captions[0].text, 'New branch')

    def test_history_bound_nested_isolation_and_playhead_are_preserved(self):
        child = Project(captions=[Caption('nested', 0, 2, 'Inside')]).to_dict()
        media = MediaItem('compound', '', 'video', 'Nested', compound=child)
        clip = TimelineItem('title', '', 'video_1', 0, 2, role='title', title_text='Title')
        self.w.set_project(Project(media=[media], timeline=[clip], playhead=7))
        first = self.w._history[0]
        clip.start = 1
        self.w.commit_history()
        second = self.w._history[-1]
        self.assertIs(first.media[0], second.media[0])
        media.compound['captions'][0]['text'] = 'Live edit'
        self.assertEqual(first.media[0].compound['captions'][0]['text'], 'Inside')
        self.assertEqual(second.media[0].compound['captions'][0]['text'], 'Inside')
        self.w.undo()
        self.w.project.media[0].compound['captions'][0]['text'] = 'Uncommitted'
        self.assertEqual(first.media[0].compound['captions'][0]['text'], 'Inside')
        self.w.redo()
        self.assertEqual(self.w.project.media[0].compound['captions'][0]['text'], 'Inside')
        for start in range(2, 103):
            self.w.project.timeline[0].start = start
            self.w.commit_history()
        self.assertEqual(len(self.w._history), 100)
        self.assertEqual(self.w._history[0].timeline[0].start, 3)
        self.w.project.playhead = 55
        self.w.project.touch()
        self.w.commit_history()
        self.assertEqual(self.w._history_index, 99)
        oldest = copy.deepcopy(self.w._history[0])
        self.w._restore_history(0)
        self.assertEqual(self.w.project.playhead, 55)
        self.assertEqual(self.w._history[0], oldest)
        self.w.redo()
        self.assertEqual(self.w.project.timeline[0].start, 4)
        self.assertEqual(self.w.project.playhead, 55)
