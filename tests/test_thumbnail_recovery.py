"""A failed thumbnail must not strand healthy media or block the GUI."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QEventLoop, QTimer, QThreadPool
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from kinetic_cut.model import MediaItem, Project
from kinetic_cut.ui import MainWindow


class ThumbnailRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.window=MainWindow();self.window.autosave_timer.stop()
        self.panel=self.window.media_panel
        self.thumb=self.root/'good.png'
        image=QImage(32,18,QImage.Format_RGB32);image.fill(QColor('blue'));image.save(str(self.thumb))
        self.panel.folder='project'

    def wait_until(self,condition,seconds=3):
        deadline=time.monotonic()+seconds
        while not condition() and time.monotonic()<deadline:
            loop=QEventLoop();QTimer.singleShot(10,loop.quit);loop.exec()
        self.assertTrue(condition())

    def tearDown(self):
        self.window.close();QThreadPool.globalInstance().waitForDone(5000)
        QApplication.processEvents();self.window.deleteLater()
        QApplication.sendPostedEvents(None,QEvent.DeferredDelete);QApplication.processEvents();self.temp.cleanup()

    def media(self,count=2,kind='video'):
        rows=[]
        for index in range(count):
            path=self.root/f'input-{index}.mp4';path.write_bytes(b'disposable')
            rows.append(MediaItem(str(index),str(path),kind,str(index),1,32,18))
        self.window.project=Project(media=rows)
        return rows

    def test_one_deleted_source_cannot_abort_healthy_thumbnail_batch(self):
        rows=self.media()
        def make(path,*args,**kwargs):
            if path==rows[0].path:raise FileNotFoundError('Removed after it was queued')
            return str(self.thumb)
        with patch('kinetic_cut.media.make_thumbnail',side_effect=make):
            self.panel._thumbnail_rebuild_paths={row.path:row.kind for row in rows}
            self.panel._start_thumbnail_rebuild()
            self.wait_until(lambda:not self.panel._thumbnail_rebuild_busy)
            self.assertEqual(rows[1].thumbnail,str(self.thumb))
            self.assertNotIn(rows[1].path,self.panel._thumbnail_rebuild_failed)
            self.assertIn(rows[0].path,self.panel._thumbnail_rebuild_failed)

    def test_failed_batch_does_not_strand_later_queued_sources(self):
        rows=self.media(23);seen=[]
        def make(path,*args,**kwargs):
            seen.append(path)
            if path==rows[0].path:raise OSError('Damaged input')
            return str(self.thumb)
        with patch('kinetic_cut.media.make_thumbnail',side_effect=make):
            self.panel._thumbnail_rebuild_paths={row.path:row.kind for row in rows}
            self.panel._start_thumbnail_rebuild()
            self.wait_until(lambda:not self.panel._thumbnail_rebuild_busy)
            self.assertEqual({row.path for row in rows},set(seen))
            self.assertTrue(all(row.thumbnail==str(self.thumb) for row in rows[1:]))
            self.assertFalse(self.panel._thumbnail_rebuild_paths)

    def test_missing_image_thumbnail_is_rebuilt_off_gui_thread(self):
        row=self.media(1,kind='image')[0];threads=[]
        def make(*args,**kwargs):
            threads.append(threading.get_ident());return str(self.thumb)
        with patch('kinetic_cut.media.make_thumbnail',side_effect=make):
            self.panel.media_icon(row)
            self.assertEqual(threads,[],'Reading a full image must not run in the immediate UI call')
            self.wait_until(lambda:bool(threads) and not self.panel._thumbnail_rebuild_busy)
            self.assertNotEqual(threads[0],threading.get_ident())
            self.assertEqual(row.thumbnail,str(self.thumb))

    def test_rebuild_invalidates_timeline_artwork_without_dirtying_history(self):
        row=self.media(1)[0];generation=self.window.timeline._paint_generation
        history=list(self.window._history)
        with patch('kinetic_cut.media.make_thumbnail',return_value=str(self.thumb)):
            self.panel._thumbnail_rebuild_paths={row.path:row.kind}
            self.panel._start_thumbnail_rebuild()
            self.wait_until(lambda:not self.panel._thumbnail_rebuild_busy)
            self.assertGreater(self.window.timeline._paint_generation,generation)
            self.assertEqual(self.window._history,history)

    def test_switching_projects_during_failure_still_generates_new_project(self):
        rows=self.media(2);entered=threading.Event();release=threading.Event()
        first=Project(media=[rows[0]]);second=Project(media=[rows[1]])
        self.window.project=first
        def make(path,*args,**kwargs):
            if path==rows[0].path:
                entered.set();release.wait(3);raise OSError('First project source failed')
            return str(self.thumb)
        try:
            with patch('kinetic_cut.media.make_thumbnail',side_effect=make):
                self.panel.refresh();self.wait_until(entered.is_set)
                original_thumbnail=rows[0].thumbnail
                self.window.project=second;self.panel.refresh()
                release.set()
                self.wait_until(lambda:not self.panel._thumbnail_rebuild_busy and not self.panel._thumbnail_rebuild_paths)
                self.assertEqual(rows[1].thumbnail,str(self.thumb))
                self.assertEqual(rows[0].thumbnail,original_thumbnail)
        finally:release.set()

    def test_returning_to_project_retries_previous_thumbnail_failure(self):
        rows=self.media(1);project=self.window.project
        self.panel.refresh();self.panel._thumbnail_rebuild_paths.clear()
        self.panel._thumbnail_rebuild_failed.add(rows[0].path)
        self.window.project=Project();self.panel.refresh()
        with patch('kinetic_cut.media.make_thumbnail',return_value=str(self.thumb)):
            self.window.project=project;self.panel.refresh()
            self.wait_until(lambda:rows[0].thumbnail==str(self.thumb))

    def test_close_cancels_running_thumbnail_and_does_not_start_next_batch(self):
        rows=self.media(23);entered=threading.Event();observed=threading.Event();calls=[]
        def make(path,*args,cancel_check=None,**kwargs):
            calls.append(path);entered.set()
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if cancel_check and cancel_check():observed.set();raise InterruptedError('Cancelled')
                time.sleep(.005)
            return str(self.thumb)
        with patch('kinetic_cut.media.make_thumbnail',side_effect=make):
            self.panel._thumbnail_rebuild_paths={row.path:row.kind for row in rows}
            self.panel._start_thumbnail_rebuild();self.wait_until(entered.is_set)
            self.window.close();self.wait_until(lambda:not self.window._workers)
            self.assertTrue(observed.is_set());self.assertEqual(calls,[rows[0].path])

    def test_project_thumbnails_generate_even_when_pool_shows_a_power_bin(self):
        row=self.media(1)[0];self.panel.folder='Master'
        with patch('kinetic_cut.media.make_thumbnail',return_value=str(self.thumb)):
            self.panel.refresh()
            self.wait_until(lambda:row.thumbnail==str(self.thumb))

