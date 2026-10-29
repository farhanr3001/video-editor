"""Project changes during audio peak generation must not mix source results."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QEvent,QEventLoop,QTimer,QThreadPool
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem
from kinetic_cut.waveforms import Waveform


class ProjectWaveformJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.w=MainWindow();self.w.autosave_timer.stop()
        self.icons=patch.object(self.w.media_panel.audio_thumbnails,'icon',return_value=QIcon());self.icons.start()
        self.release=threading.Event()

    def wait_until(self,condition):
        deadline=time.monotonic()+3
        while not condition() and time.monotonic()<deadline:
            loop=QEventLoop();QTimer.singleShot(10,loop.quit);loop.exec()
        self.assertTrue(condition())

    def tearDown(self):
        self.release.set();self.w.close();QThreadPool.globalInstance().waitForDone(5000)
        QApplication.processEvents();self.w.deleteLater();QApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.icons.stop();self.temp.cleanup()

    def project(self,name):
        p=self.root/(name+'.wav');p.write_bytes(b'disposable')
        return Project(name=name,media=[MediaItem('shared-id',str(p),'audio',name,1,has_audio=True)])

    def test_old_project_waveform_cannot_replace_same_id_in_new_project(self):
        a=self.project('a');b=self.project('b');entered=threading.Event()
        old=Waveform(np.array([[-100,100]],dtype=np.int16));new=Waveform(np.array([[-200,200]],dtype=np.int16))
        def generate(path,*args):
            if path==a.media[0].path:entered.set();self.release.wait(3);return old
            return new
        with patch('kinetic_cut.ui.waveform',side_effect=generate):
            self.w.set_project(a);self.wait_until(entered.is_set)
            self.w.set_project(b);self.wait_until(lambda:self.w.timeline.waveforms.get('shared-id') is new)
            self.release.set();self.wait_until(lambda:not self.w._workers)
            self.assertIs(self.w.timeline.waveforms['shared-id'],new)
            self.assertFalse(self.w.timeline.waveform_pending);self.assertFalse(self.w.timeline.waveform_failures)

    def test_return_to_same_source_receives_inflight_result_without_duplicate_job(self):
        a=self.project('a');entered=threading.Event();values=Waveform(np.array([[-500,500]],dtype=np.int16))
        def generate(*args):entered.set();self.release.wait(3);return values
        with patch('kinetic_cut.ui.waveform',side_effect=generate) as generate_mock:
            self.w.set_project(a);self.wait_until(entered.is_set)
            self.w.set_project(Project());self.w.set_project(a)
            self.release.set();self.wait_until(lambda:not self.w._workers)
            self.assertIs(self.w.timeline.waveforms['shared-id'],values)
            self.assertFalse(self.w.timeline.waveform_pending);self.assertEqual(generate_mock.call_count,1)

    def test_old_failure_cannot_mark_new_project_waveform_failed(self):
        a=self.project('a');b=self.project('b');entered=threading.Event()
        new=Waveform(np.array([[-200,200]],dtype=np.int16))
        def generate(path,*args):
            if path==a.media[0].path:
                entered.set();self.release.wait(3);raise OSError('Old source became unreadable')
            return new
        with patch('kinetic_cut.ui.waveform',side_effect=generate):
            self.w.set_project(a);self.wait_until(entered.is_set)
            self.w.set_project(b);self.release.set();self.wait_until(lambda:not self.w._workers)
            self.assertIs(self.w.timeline.waveforms['shared-id'],new)
            self.assertFalse(self.w.timeline.waveform_pending);self.assertFalse(self.w.timeline.waveform_failures)
