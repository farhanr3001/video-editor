"""Caption input coverage survives saved-project selections and project switches."""
import copy
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QEvent,QEventLoop,QTimer
from PySide6.QtWidgets import QApplication,QDialog
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,CaptionStyle
from kinetic_cut.caption_style_dialog import CaptionStyleDialog
from kinetic_cut.captions import _check_cancel


class CaptionProjectScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False);cls.app.setProperty('kineticTestDiscardUnsaved',True)

    def setUp(self):
        self.w=MainWindow();self.w.autosave_timer.stop()
        self.w.request_waveform=lambda _:None;self.w.queue_proxy=lambda _:None
        self.w.preview_quality.request=lambda:None
        self.w.show();self.project=self.speech_project();self.w.set_project(self.project)

    def wait(self,ms=20):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()

    def drained(self):
        end=time.monotonic()+3
        while self.w._workers and time.monotonic()<end:self.wait()
        self.assertFalse(self.w._workers)

    def tearDown(self):
        self.w.close();self.drained();self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)

    def speech_project(self):
        p=Project(media=[MediaItem('m','missing-speech.mp4','video','Speech',12,640,360,has_audio=True)])
        for n in range(4):
            p.timeline.extend([TimelineItem('v'+str(n),'m','video_1',n*3,3,in_point=n*3,link_id='pair'+str(n)),TimelineItem('a'+str(n),'m','audio_1',n*3,3,in_point=n*3,role='source_audio',link_id='pair'+str(n))])
        return p

    def generate(self,selection=False,headless=False,**kw):
        def accept(dialog):
            dialog.scope.button(1 if selection else 0).setChecked(True)
            return QDialog.Accepted
        def transcribe(wav,settings,offset,*args,**kwargs):
            return [Caption('generated',offset,offset+1,'Recognized speech')],'fixture'
        with patch.object(CaptionStyleDialog,'exec',accept),patch('kinetic_cut.process.run_cancellable') as mix,patch('kinetic_cut.ui.transcribe',side_effect=transcribe):
            worker=self.w.generate_captions(headless=headless,**kw)
            self.drained()
        return worker,mix

    def test_saved_project_with_retained_selection_defaults_to_all_speech(self):
        self.w.timeline.select_ids({'v2'},'v2')
        self.w.set_project(Project.from_dict(self.project.to_dict()))
        self.assertIn('v2',self.w.timeline.selected_ids)
        worker,mix=self.generate()
        self.assertIsNotNone(worker);report=self.w._caption_report
        self.assertEqual(report['audio_range'],[0,12]);self.assertEqual(report['scope'],'timeline')
        self.assertEqual([s['item_id'] for s in report['sources']],['a0','a1','a2','a3'])
        self.assertEqual(mix.call_args.args[0].count('-i'),4)

    def test_explicit_selected_speech_keeps_its_range_and_honest_skip_reason(self):
        self.w.timeline.select_ids({'v2'},'v2');self.generate(selection=True)
        report=self.w._caption_report
        self.assertEqual(report['audio_range'],[6,9]);self.assertEqual(report['scope'],'selection')
        self.assertEqual([s['item_id'] for s in report['sources']],['a2'])
        self.assertEqual({s['reason'] for s in report['skipped']},{'outside selected clips'})

    def test_explicit_selection_without_speech_refuses_instead_of_captioning_everything(self):
        self.w.timeline.select_ids(set(),'');worker,mix=self.generate(headless=True,selection_only=True)
        self.assertIsNone(worker);mix.assert_not_called();self.assertEqual(self.w._caption_report['state'],'refused')

    def test_headless_default_ignores_selection_and_explicit_scope_still_works(self):
        self.w.timeline.select_ids({'v1'},'v1');self.generate(headless=True)
        self.assertEqual(self.w._caption_report['audio_range'],[0,12])
        self.w.timeline.select_ids({'v1'},'v1')
        self.generate(headless=True,selection_only=True);self.assertEqual(self.w._caption_report.get('audio_range'),[3,6],self.w._caption_report)

    def test_video_only_saved_project_captions_all_cuts_and_deduplicates_layout_layers(self):
        p=self.project;p.timeline=[i for i in p.timeline if i.track=='video_1'];p.add_track('video')
        for item in list(p.timeline):
            duplicate=copy.deepcopy(item);duplicate.id+='-layout';duplicate.track='video_2';p.timeline.append(duplicate)
        self.w.set_project(p);_,mix=self.generate(headless=True)
        self.assertEqual(self.w._caption_report['audio_range'],[0,12]);self.assertEqual(mix.call_args.args[0].count('-i'),4)
        self.w.timeline.select_ids({'v2-layout'},'v2-layout');self.generate(headless=True,selection_only=True)
        self.assertEqual(self.w._caption_report.get('audio_range'),[6,9],self.w._caption_report)

    def test_muted_source_speech_never_falls_back_to_embedded_video(self):
        for item in self.project.timeline:
            if item.track=='audio_1':item.muted=True
        worker,mix=self.generate(headless=True);self.assertIsNone(worker);mix.assert_not_called()
        self.assertIn('muted',self.w._caption_report['reason'].lower())

    def test_project_switch_cancels_old_inference_and_allows_new_job_without_restart(self):
        entered=threading.Event();calls=[]
        def delayed(wav,settings,offset,*args,**kw):
            calls.append(offset)
            if len(calls)==1:
                entered.set();deadline=time.monotonic()+2
                while time.monotonic()<deadline:
                    _check_cancel(kw['cancel_check']);time.sleep(.01)
                self.fail('Previous project inference was not cancelled')
            return [Caption('new',0,1,'New project speech')],'fixture'
        with patch('kinetic_cut.process.run_cancellable'),patch('kinetic_cut.ui.transcribe',side_effect=delayed):
            self.w.generate_captions(headless=True);self.assertTrue(entered.wait(2))
            cancel=self.w._caption_cancel;other=self.speech_project();other.name='Other project';self.w.set_project(other)
            self.assertTrue(cancel.is_set());self.drained();self.assertIsNone(self.w._caption_cancel)
            self.assertFalse(other.captions);self.w.generate_captions(headless=True);self.drained()
        self.assertEqual(len(calls),2);self.assertEqual(self.w._caption_report['state'],'complete');self.assertEqual(other.captions[0].text,'New project speech')

    def test_dialog_scope_resets_per_open_and_disables_selection_when_empty(self):
        d=CaptionStyleDialog(CaptionStyle(),{'caption_scope':'selection'},selection_available=False)
        self.assertEqual(d.scope.checkedId(),0);self.assertFalse(d.scope.button(1).isEnabled());d.close()
        d=CaptionStyleDialog(CaptionStyle(),{},selection_available=True)
        self.assertTrue(d.scope.button(1).isEnabled());self.assertEqual(d.scope.checkedId(),0);d.close()

    def test_default_subtitle_state_added_during_paint_does_not_discard_result(self):
        for locked in (False,True):
            self.w.set_project(self.speech_project());entered=threading.Event();release=threading.Event()
            def delayed(*a,**kw):
                entered.set();release.wait(2);return [Caption('result',0,1,'Speech')],'fixture'
            with patch('kinetic_cut.process.run_cancellable'),patch('kinetic_cut.ui.transcribe',side_effect=delayed):
                self.w.generate_captions(headless=True);self.assertTrue(entered.wait(2))
                self.w.project.track_states['subtitle_1']=dict(visible=True,locked=locked,muted=False)
                release.set();self.drained()
            self.assertEqual(bool(self.w.project.captions),not locked)
            self.assertEqual(self.w._caption_report['state'],'discarded' if locked else 'complete')

    def test_generation_setup_dialogs_are_released_after_accept_and_cancel(self):
        for _ in range(2):self.generate()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete)
        self.assertFalse(self.w.findChildren(CaptionStyleDialog))
        with patch.object(CaptionStyleDialog,'exec',return_value=QDialog.Rejected):
            self.assertIsNone(self.w.generate_captions())
        self.app.sendPostedEvents(None,QEvent.DeferredDelete)
        self.assertFalse(self.w.findChildren(CaptionStyleDialog))

if __name__=='__main__':unittest.main()
