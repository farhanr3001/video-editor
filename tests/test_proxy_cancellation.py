"""Whole-source preparation survives edits; deleting its final use cancels it."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication,QMainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem
from kinetic_cut.preview_quality import PreviewQuality


class ProxyCancellationTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([])
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        source=self.base/'original.mp4';source.write_bytes(b'original')
        self.media=MediaItem('m',str(source),'video','long',3261.15,1920,1080,60,True,video_codec='h264')
        self.w=QMainWindow();self.w.project=Project(media=[self.media],timeline=[TimelineItem('v','m','video_1',0,3261.15)])
        self.w.settings={};self.w.proxies={};self.w.preview=SimpleNamespace(frames={})
        self.w.transport=SimpleNamespace(closed=False,playing=False,decoders={},sync=lambda force:None)
        self.workers=[];self.w.start_worker=self.workers.append;self.q=PreviewQuality(self.w)
        self.path_patch=patch('kinetic_cut.media.proxy_path',return_value=self.base/'absent.mp4');self.path_patch.start();self.addCleanup(self.path_patch.stop)
    def tearDown(self):
        self.q.cancel();self.w.close();self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
    def test_repeated_cuts_and_trims_never_cancel_or_spawn_another_job(self):
        self.q.request();token=self.q.token
        self.w.project.split_selection(['v'],1,linked=False)
        for n in range(80):
            item=self.w.project.timeline[0];item.in_point=n*.1;item.duration=.4+n*.01;self.q.request()
        self.assertFalse(token.is_set());self.assertEqual(len(self.workers),1)
        self.assertEqual(self.workers[0].function.__name__,'generate_proxy');self.assertEqual(self.workers[0].args[0].duration,3261.15)
    def test_last_video_deletion_cancels_without_import_prewarm_restart(self):
        self.q.extra_ids.add('m');self.q.request();token=self.q.token
        self.w.project.timeline=[TimelineItem('audio','m','audio_1',0,10)]
        self.q.request();self.assertTrue(token.is_set());self.workers[0].signals.finished.emit()
        for _ in range(10):self.q.request()
        self.assertEqual(len(self.workers),1);self.assertFalse(self.q.busy);self.assertEqual(len(self.w.project.media),1)
    def test_deleting_one_of_multiple_source_uses_keeps_preparation_running(self):
        self.w.project.timeline.append(TimelineItem('second','m','video_1',10,2,in_point=50))
        self.q.request();token=self.q.token;self.w.project.timeline.pop(0);self.q.request()
        self.assertFalse(token.is_set());self.assertEqual(len(self.workers),1)
    def test_completed_full_copy_remains_reusable_after_edits_and_deletion(self):
        self.q.request();completed=self.base/'completed.mp4';completed.write_bytes(b'complete cached copy')
        self.workers[0].signals.result.emit(str(completed));self.workers[0].signals.finished.emit()
        for _ in range(25):
            self.w.project.timeline[0].in_point+=1;self.q.request()
        self.w.project.timeline.clear();self.q.request()
        self.w.project.timeline.append(TimelineItem('restored','m','video_1',0,2,in_point=100));self.q.request()
        self.assertEqual(len(self.workers),1);self.assertEqual(completed.read_bytes(),b'complete cached copy')
        self.assertEqual(self.w.proxies['m'],str(completed));self.assertEqual(self.media.duration,3261.15)
    def test_inactive_timeline_does_not_restart_removed_import_work(self):
        self.q.extra_ids.add('m');self.q.request();token=self.q.token
        self.w.project.other_timelines=[dict(id='old',name='Old',number=1,data=dict(timeline=[dict(media_id='m')]))]
        self.w.project.timeline.clear();self.q.request();self.assertTrue(token.is_set())
        self.workers[0].signals.finished.emit();self.assertEqual(len(self.workers),1)


if __name__=='__main__':unittest.main()
