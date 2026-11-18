import copy,tempfile,threading,time,unittest,wave
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QTimer,QEventLoop,QEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from kinetic_cut.model import Project,TimelineItem,MediaItem,Caption
from kinetic_cut.ui import MainWindow
from kinetic_cut.workspace import set_page


class TimelineSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.app.setQuitOnLastWindowClosed(False);cls.app.setProperty('kineticTestDiscardUnsaved',True)
    def wait(self,ms=30):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def setUp(self):
        self.w=MainWindow();self.w.autosave_timer.stop();self.w.request_waveform=lambda _:None;self.w.queue_proxy=lambda _:None;self.w.preview_quality.request=lambda:None
        self.w.set_project(Project(media=[MediaItem('shared','still.png','image','Shared',0,320,180)],timeline=[TimelineItem('one','shared','video_1',0,5)]));self.nav=self.w.timeline_sessions;self.first=self.w.project.active_timeline_id
    def tearDown(self):
        self.app.clipboard().clear()
        self.w.close();end=time.monotonic()+10
        while self.w._workers and time.monotonic()<end:self.wait()
        self.assertFalse(self.w._workers);self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
    def edit(self,value):
        self.w.project.timeline[0].duration=value;self.w.model_changed()
    def test_selectors_initial_create_cancel_and_disabled_single_deliver(self):
        self.assertEqual(self.w.timeline_selector.itemText(0),'Create new timeline…');self.assertEqual(self.w.timeline_selector.currentText(),'Timeline 1');self.assertFalse(self.w.delivery.timeline_selector.isEnabled())
        with patch('kinetic_cut.timeline_sessions.QInputDialog.getText',return_value=('Ignored',False)):self.w.timeline_selector.setCurrentIndex(0)
        self.assertEqual(len(self.w.project.timeline_choices()),1);self.assertEqual(self.w.timeline_selector.currentText(),'Timeline 1')
        with patch('kinetic_cut.timeline_sessions.QInputDialog.getText',return_value=('',True)):self.w.timeline_selector.setCurrentIndex(0)
        self.assertEqual(self.w.timeline_selector.currentText(),'Timeline 2');self.assertTrue(self.w.delivery.timeline_selector.isEnabled());self.assertFalse(self.w.project.timeline)
    def test_each_timeline_keeps_undo_redo_and_does_not_restore_other_timeline_content(self):
        self.edit(4);second=self.nav.create();self.w.project.timeline.append(TimelineItem('two','shared','video_1',0,3));self.w.model_changed();self.edit(2)
        self.nav.switch(self.first);self.w.undo();self.assertEqual(self.w.project.timeline[0].duration,5);self.w.redo();self.assertEqual(self.w.project.timeline[0].duration,4)
        self.nav.switch(second);self.assertEqual(self.w.project.timeline[0].duration,2);self.w.undo();self.assertEqual(self.w.project.timeline[0].duration,3)
        self.nav.switch(self.first);self.assertEqual(self.w.project.timeline[0].duration,4)
    def test_shared_pool_survives_other_timeline_undo_and_preserves_inactive_dependencies(self):
        self.w.project.add_media(MediaItem('added','added.png','image','Added'));self.w.project.timeline.append(TimelineItem('uses-added','added','video_1',5,1));self.w.model_changed()
        second=self.nav.create();self.w.project.timeline.append(TimelineItem('dependency','added','video_1',0,1));self.w.model_changed()
        self.w.project.add_media(MediaItem('other','other.png','image','Other'));self.w.model_changed();self.nav.switch(self.first);self.w.undo()
        self.assertIsNotNone(self.w.project.media_by_id('other'));self.assertIsNotNone(self.w.project.media_by_id('added'));self.assertIsNone(self.w.project.item_by_id('uses-added'))
        self.nav.switch(second);self.assertEqual(self.w.project.timeline[0].media_id,'added')
    def test_external_media_is_rebased_into_every_inactive_history_state(self):
        self.edit(4);self.edit(3);second=self.nav.create()
        self.w.project.add_media(MediaItem('external','external.png','image','External'));self.w.model_changed();self.nav.switch(self.first)
        self.w.undo();self.w.undo();self.assertIsNotNone(self.w.project.media_by_id('external'))
        self.w.redo();self.nav.switch(second);self.assertIsNotNone(self.w.project.media_by_id('external'))
    def test_new_project_resets_timeline_banks_and_unsaved_empty_active_still_protects_other_work(self):
        self.edit(3);self.nav.create();from kinetic_cut.close_guard import has_unsaved
        self.assertTrue(has_unsaved(self.w));self.w.set_project(Project())
        self.assertFalse(self.nav.banks);self.assertEqual(self.w.timeline_selector.currentText(),'Timeline 1');self.w.undo();self.assertFalse(self.w.project.timeline)
    def test_pool_removal_cannot_break_an_inactive_timeline(self):
        self.nav.create();from kinetic_cut.pool_removal import remove
        with patch('kinetic_cut.pool_removal.QMessageBox.information') as notice:
            self.assertFalse(remove(self.w.media_panel,{'shared'},'project'))
        notice.assert_called_once();self.assertIsNotNone(self.w.project.media_by_id('shared'))
    def test_deliver_switch_stays_deliver_updates_preview_and_keeps_frozen_jobs(self):
        self.w.delivery.location.setText(tempfile.gettempdir());second=self.nav.create('Chase');self.w.project.timeline.append(TimelineItem('two','shared','video_1',0,2));self.w.model_changed()
        set_page(self.w,1);self.assertEqual(self.w.delivery.name.text(),'Chase');self.w.delivery.add_job();job=self.w.delivery.jobs[-1];self.assertEqual(job['project'].timeline[0].id,'two');self.assertFalse(job['project'].other_timelines)
        combo=self.w.delivery.timeline_selector;combo.setCurrentIndex(combo.findData(self.first))
        self.assertEqual(self.w.current_page,1);self.assertIs(self.w.preview.project,self.w.project);self.assertEqual(self.w.project.timeline[0].id,'one');self.assertEqual(self.w.delivery.name.text(),'Timeline 1');self.assertIn(job,self.w.delivery.jobs)
        self.assertEqual(job['project'].timeline[0].id,'two');set_page(self.w,0);self.assertEqual(self.w.timeline_selector.currentText(),'Timeline 1')
    def test_view_and_custom_filename_are_independent(self):
        self.w.timeline.set_zoom(80);self.w.delivery.name.setText('Custom first');self.w.delivery.name.setModified(True)
        self.w.link_toggle.click();second=self.nav.create();self.w.timeline.set_zoom(120)
        self.assertEqual(self.w.delivery.name.text(),'Timeline 2');self.nav.switch(self.first)
        self.assertEqual(self.w.timeline.pixels_per_second,80);self.assertFalse(self.w.timeline.linked_selection);self.assertEqual(self.w.delivery.name.text(),'Custom first')
        self.nav.switch(second);self.assertEqual(self.w.timeline.pixels_per_second,120)
    def test_rename_undo_and_save_keep_both_timeline_contents(self):
        second=self.nav.create();self.w.project.timeline.append(TimelineItem('two','shared','video_1',0,2));self.w.model_changed()
        with patch('kinetic_cut.timeline_sessions.QInputDialog.getText',return_value=('The chase',True)):self.nav.prompt_rename()
        self.assertEqual(self.w.delivery.name.text(),'The chase');self.w.undo();self.assertEqual(self.w.timeline_selector.currentText(),'Timeline 2');self.assertEqual(self.w.delivery.name.text(),'Timeline 2')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'both.kcut';self.w.project.save(path);loaded=Project.load(path)
        self.assertEqual(loaded.timeline[0].id,'two');loaded.switch_timeline(self.first);self.assertEqual(loaded.timeline[0].id,'one')
    def test_caption_generation_only_uses_current_timeline_and_switch_cancels(self):
        speech=MediaItem('speech','speech.mp4','video','Speech',20,640,360,has_audio=True);self.w.project.add_media(speech)
        self.w.project.timeline=[TimelineItem('v1','speech','video_1',0,4),TimelineItem('a1','speech','audio_1',0,4,in_point=0,role='source_audio')];self.w.model_changed()
        second=self.nav.create();self.w.project.timeline=[TimelineItem('v2','speech','video_1',0,3,in_point=10),TimelineItem('a2','speech','audio_1',0,3,in_point=10,role='source_audio')];self.w.model_changed()
        with patch('kinetic_cut.process.run_cancellable') as mix,patch('kinetic_cut.ui.transcribe',return_value=([Caption('caption',0,1,'Second')],'fixture')):
            self.w.generate_captions(headless=True);end=time.monotonic()+3
            while self.w._caption_cancel is not None and time.monotonic()<end:self.wait()
        self.assertEqual([r['item_id'] for r in self.w._caption_report['sources']],['a2']);self.assertIn('10',mix.call_args.args[0]);self.assertEqual(self.w.project.captions[0].text,'Second')
        self.nav.switch(self.first);self.assertFalse(self.w.project.captions)
        entered=threading.Event();release=threading.Event()
        def delayed(*a,**kw):entered.set();release.wait(2);return [Caption('late',0,1,'Late')],'fixture'
        with patch('kinetic_cut.process.run_cancellable'),patch('kinetic_cut.ui.transcribe',side_effect=delayed):
            self.w.generate_captions(headless=True);self.assertTrue(entered.wait(2));cancel=self.w._caption_cancel;self.nav.switch(second);release.set()
            end=time.monotonic()+3
            while self.w._caption_cancel is not None and time.monotonic()<end:self.wait()
        self.assertTrue(cancel.is_set());self.assertFalse(any(c.id=='late' for c in self.w.project.captions))
    def test_tts_lands_on_current_timeline_and_late_results_do_not_cross_switch(self):
        second=self.nav.create()
        with patch('kinetic_cut.tts.synthesize_speech',return_value='tts.wav'),patch('kinetic_cut.ui.probe',return_value=MediaItem('tts','tts.wav','audio','Voice',1,has_audio=True)):
            result=self.w.generate_tts_dialogue(initial_text='Speech',headless=True)
        self.assertIsNotNone(result);self.assertTrue(any(i.media_id=='tts' for i in self.w.project.timeline));self.nav.switch(self.first);self.assertFalse(any(i.media_id=='tts' for i in self.w.project.timeline))
        def delayed(*a,**kw):time.sleep(.15);return 'late.wav'
        with patch('kinetic_cut.tts.synthesize_speech',side_effect=delayed),patch.object(self.w,'_apply_generated_dialogue') as apply:
            QTimer.singleShot(35,lambda:self.nav.switch(second));self.w.generate_tts_dialogue(initial_text='Late speech',headless=True)
        apply.assert_not_called()
    def test_copy_paste_crosses_timelines_with_independent_destination_undo(self):
        self.w.timeline.select_ids({'one'},'one');self.w.timeline_clipboard('copy',True)
        second=self.nav.create();self.w.seek(2);self.w.timeline_clipboard('paste',True)
        self.assertEqual(len(self.w.project.timeline),1);pasted=self.w.project.timeline[0]
        self.assertEqual(pasted.media_id,'shared');self.assertEqual(pasted.start,2);self.assertNotEqual(pasted.id,'one')
        self.w.undo();self.assertFalse(self.w.project.timeline);self.nav.switch(self.first)
        self.assertEqual(self.w.project.timeline[0].id,'one');self.nav.switch(second);self.w.redo()
        self.assertEqual(self.w.project.timeline[0].id,pasted.id)
    def test_cut_paste_crosses_timelines_and_each_side_undoes_its_own_action(self):
        self.w.timeline.select_ids({'one'},'one');self.w.timeline_clipboard('cut',True)
        self.assertFalse(self.w.project.timeline);second=self.nav.create();self.w.timeline_clipboard('paste',True)
        self.assertEqual(len(self.w.project.timeline),1);pasted=self.w.project.timeline[0].id
        self.nav.switch(self.first);self.w.undo();self.assertEqual(self.w.project.timeline[0].id,'one')
        self.nav.switch(second);self.assertEqual(self.w.project.timeline[0].id,pasted);self.w.undo();self.assertFalse(self.w.project.timeline)
        self.nav.switch(self.first);self.w.redo();self.assertFalse(self.w.project.timeline)

if __name__=='__main__':unittest.main()
