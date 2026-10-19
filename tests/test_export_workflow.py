import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QEvent,QThreadPool
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,TimelineItem
from kinetic_cut.exporter import ExportPreset
from kinetic_cut.ui import MainWindow


class ExportWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'edit.kcut'
        self.p=Project(timeline=[TimelineItem('t','','video_1',0,2,role='title',title_text='Original')]);self.p.save(self.path)
        self.w=MainWindow();self.w.autosave_timer.stop();self.w.set_project(self.p)
    def tearDown(self):
        self.w.close();QThreadPool.globalInstance().waitForDone(10000);self.w.deleteLater()
        QApplication.sendPostedEvents(None,QEvent.DeferredDelete);QApplication.processEvents();self.temp.cleanup()
    def job(self):
        return self.w.delivery.bind_job(dict(project=copy.deepcopy(self.w.project),output=str(self.path.with_suffix('.mp4')),
            preset=ExportPreset('Custom','h264',15,192,'Custom','auto'),hardware='Auto',burn=False,audio=True,state='Queued',elapsed=0.))
    def settle(self):
        self.assertTrue(QThreadPool.globalInstance().waitForDone(10000));QApplication.processEvents()
    def test_auto_quality_default_and_manual_control(self):
        d=self.w.delivery;self.assertEqual(d.preset().quality,'auto');self.assertTrue(d.bitrate.isHidden());self.assertFalse(d.bitrate.isEnabled())
        d.quality.setCurrentIndex(1);d.bitrate.setValue(22);self.assertEqual(d.preset().quality,'bitrate');self.assertEqual(d.preset().bitrate_mbps,22)
        self.assertFalse(d.bitrate.isHidden());self.assertTrue(d.bitrate.isEnabled());self.assertIn('MB',d.estimate.text())
        d.quality.setCurrentIndex(0);self.assertIn('Variable file size',d.estimate.text())
    def test_complete_reopens_in_queue_and_remove_updates_saved_metadata(self):
        d=self.w.delivery;job=self.job();d.jobs=[job]
        with patch('kinetic_cut.config.save_settings'):d.complete(job,'Complete')
        self.settle()
        self.assertEqual(len(Project.load(self.path).render_history),1)
        self.w.set_project(Project.load(self.path));d=self.w.delivery;self.assertEqual(len(d.jobs),1);self.assertEqual(d.jobs[0]['state'],'Complete')
        d.list.setCurrentRow(0);d.remove_job();self.settle();self.assertEqual(d.jobs,[]);self.assertEqual(Project.load(self.path).render_history,[])
    def test_completed_history_survives_edit_undo_redo_without_extra_history_entry(self):
        d=self.w.delivery;job=self.job();d.jobs=[job];index=self.w._history_index
        with patch('kinetic_cut.config.save_settings'):d.complete(job,'Complete')
        self.w.commit_history();self.assertEqual(self.w._history_index,index)
        self.w.project.timeline[0].title_text='Edited';self.w.commit_history();self.w.undo()
        self.assertEqual(self.w.project.timeline[0].title_text,'Original');self.assertEqual(len(self.w.project.render_history),1)
        self.w.redo();self.assertEqual(self.w.project.timeline[0].title_text,'Edited');self.assertEqual(len(self.w.project.render_history),1)
    def test_late_completion_updates_original_project_only(self):
        d=self.w.delivery;job=self.job();job['state']='Rendering';d.jobs=[job];d.running=True
        other=Project(name='Other');self.w.set_project(other)
        with patch('kinetic_cut.config.save_settings'):d.complete(job,'Complete')
        self.settle()
        self.assertEqual(other.render_history,[]);self.assertEqual(d.jobs,[]);self.assertEqual(len(Project.load(self.path).render_history),1)
    def test_unrendered_jobs_do_not_survive_reload(self):
        d=self.w.delivery;d.jobs=[self.job()];self.w.project.save(self.path);self.w.set_project(Project.load(self.path));self.assertEqual(d.jobs,[])
