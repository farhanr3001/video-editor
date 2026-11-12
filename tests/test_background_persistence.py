"""Slow storage cannot block editing; latest preferences/recovery still publish."""
import copy,json,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QObject,QThreadPool,QEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut import config
from kinetic_cut.background_persistence import register,recovery
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem

class Owner(QObject):
    start_worker=MainWindow.start_worker
    worker_finished=MainWindow.worker_finished
    def __init__(self):
        super().__init__();self.settings=copy.deepcopy(config.DEFAULT_SETTINGS);self._workers=set();self.thread_pool=QThreadPool(self)
        self.project=Project(timeline=[TimelineItem('title','','video_1',0,3,role='title',title_text='First')])
        self.compounds=SimpleNamespace(root=lambda:self.project);self._closing=False;register(self)
    def update_job_status(self):pass

class BackgroundPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'settings.json'
        self.patch=patch.object(config,'SETTINGS_PATH',self.path);self.patch.start();self.owners=[Owner()]
    def drain(self):
        deadline=time.monotonic()+5
        while any(o._workers for o in self.owners) and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.002)
        self.app.processEvents();self.assertFalse(any(o._workers for o in self.owners))
    def tearDown(self):
        self.drain()
        for owner in self.owners:owner.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.patch.stop();self.temp.cleanup()
    def test_blocked_settings_write_returns_immediately_and_load_reads_latest(self):
        owner=self.owners[0];started=threading.Event();release=threading.Event();write=config._write_settings;threads=[]
        def slow(snapshot,path):
            threads.append(threading.get_ident());started.set();release.wait(2);write(snapshot,path)
        with patch.object(config,'_write_settings',slow):
            try:
                owner.settings['media_pool_list_view']=True;at=time.monotonic();config.save_settings(owner.settings)
                self.assertLess(time.monotonic()-at,.15);self.assertTrue(started.wait(2))
                self.assertTrue(config.load_settings()['media_pool_list_view'])
                self.assertNotIn(threading.get_ident(),threads)
            finally:release.set()
            self.drain()
        self.assertTrue(json.loads(self.path.read_text())['media_pool_list_view'])
    def test_rapid_preferences_coalesce_and_snapshot_is_detached(self):
        owner=self.owners[0];started=threading.Event();release=threading.Event();write=config._write_settings;calls=[]
        def slow(snapshot,path):
            calls.append(copy.deepcopy(snapshot));started.set();release.wait(2);write(snapshot,path)
        with patch.object(config,'_write_settings',slow):
            try:
                owner.settings['test']='first';config.save_settings(owner.settings);self.assertTrue(started.wait(2))
                for n in range(8):owner.settings['test']='last'+str(n);config.save_settings(owner.settings)
                self.assertEqual(len(owner._workers),1);self.assertEqual(config.load_settings()['test'],'last7')
                owner.settings['test']='not submitted'
            finally:release.set()
            self.drain()
        self.assertEqual(len(calls),2);self.assertEqual(json.loads(self.path.read_text())['test'],'last7')
    def test_two_windows_cannot_publish_an_older_queued_settings_snapshot_last(self):
        first=self.owners[0];second=Owner();self.owners.append(second);release=threading.Event();started=threading.Event();write=config._write_settings
        def slow(snapshot,path):started.set();release.wait(2);write(snapshot,path)
        with patch.object(config,'_write_settings',slow):
            try:
                first.settings['test']='one';config.save_settings(first.settings);self.assertTrue(started.wait(2))
                first.settings['test']='two';config.save_settings(first.settings)
                second.settings['test']='three';config.save_settings(second.settings)
            finally:release.set()
            self.drain()
        self.assertEqual(json.loads(self.path.read_text())['test'],'three')
    def test_recovery_preserves_live_path_and_keeps_latest_project(self):
        owner=self.owners[0];owner.project.path='original.kcut';live=owner.project;before=copy.deepcopy(live);path=Path(self.temp.name)/'recovery.kcut'
        release=threading.Event();started=threading.Event();save=Project.save
        def slow(project,*args):started.set();release.wait(2);return save(project,*args)
        with patch.object(Project,'save',slow):
            try:
                at=time.monotonic();recovery(owner,path);self.assertLess(time.monotonic()-at,.15);self.assertTrue(started.wait(2))
                owner.project=Project(name='Second',timeline=[TimelineItem('other','','video_1',0,2,role='title',title_text='Latest')]);recovery(owner,path)
                owner.project.timeline[0].title_text='not submitted'
            finally:release.set()
            self.drain()
        self.assertEqual(live,before);self.assertEqual(live.path,'original.kcut');self.assertEqual(Project.load(path).timeline[0].title_text,'Latest')
    def test_shutdown_owned_writes_finish_pending_latest_snapshot(self):
        owner=self.owners[0];release=threading.Event();started=threading.Event();write=config._write_settings
        def slow(snapshot,path):started.set();release.wait(2);write(snapshot,path)
        with patch.object(config,'_write_settings',slow):
            try:
                config.save_settings(owner.settings);self.assertTrue(started.wait(2));owner._closing=True
                owner.settings['last']='on close';config.save_settings(owner.settings)
                self.assertTrue(owner._workers)
            finally:release.set()
            self.drain()
        self.assertEqual(json.loads(self.path.read_text())['last'],'on close')
    def test_failed_atomic_publication_preserves_previous_valid_settings(self):
        config.save_settings({'test':'before'})
        with patch.object(Path,'replace',side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):config.save_settings({'test':'after'})
        self.assertEqual(json.loads(self.path.read_text()),{'test':'before'})
        self.assertFalse(list(self.path.parent.glob('*.pending')))
    def test_deferred_startup_callback_is_retired_with_its_window(self):
        from PySide6.QtTest import QTest
        import sys
        window=MainWindow();window.show();window.autosave_timer.stop();called=[];errors=[]
        window.when_app_loaded(lambda:called.append(True),settle=350);QTest.qWait(280)
        window.close()
        deadline=time.monotonic()+3
        while window._workers and time.monotonic()<deadline:self.app.processEvents();time.sleep(.002)
        window.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
        with patch.object(sys,'excepthook',lambda *args:errors.append(args)):QTest.qWait(450)
        self.assertEqual(called,[]);self.assertEqual(errors,[])
    def test_late_waveform_and_audio_errors_do_not_touch_destroyed_window(self):
        import sys
        from kinetic_cut.model import MediaItem
        window=MainWindow();window.autosave_timer.stop();jobs=[];source=Path(self.temp.name)/'sound.wav';source.write_bytes(b'fixture')
        media=MediaItem('s',str(source),'audio','Fixture',1,has_audio=True);window.project.media=[media]
        with patch.object(window,'start_worker',side_effect=jobs.append):
            window.request_waveform(media)
            audio=TimelineItem('a','s','audio_1',0,1,pan=.5);window.transport.processed_audio(audio,media)
        self.assertEqual(len(jobs),2)
        window.close();deadline=time.monotonic()+3
        while window._workers and time.monotonic()<deadline:self.app.processEvents();time.sleep(.002)
        window.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete);errors=[]
        with patch.object(sys,'excepthook',lambda *args:errors.append(args)):
            jobs[0].signals.finished.emit();jobs[1].signals.error.emit('Late decoder failure');self.app.processEvents()
        for job in jobs:job.signals.deleteLater()
        self.assertEqual(errors,[])

    def test_non_editor_save_stays_synchronous(self):
        config.save_settings({'test':'direct'});self.assertEqual(json.loads(self.path.read_text()),{'test':'direct'})
