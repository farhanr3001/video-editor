"""Cancellation, close ownership and stale-result failure paths."""
import copy
import sys
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QEventLoop, QTimer, QEvent, QThreadPool
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QProgressDialog
from kinetic_cut.ui import MainWindow, Worker
from kinetic_cut.model import Project, MediaItem, TimelineItem, Caption
from kinetic_cut.process import run_cancellable


class StabilityJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)
        cls.app.setProperty('kineticTestDiscardUnsaved',True)

    def wait(self,ms=150):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()

    def setUp(self):
        self.w=MainWindow(); self.w.autosave_timer.stop()
        self.w.show()

    def tearDown(self):
        self.w.close()
        deadline=time.monotonic()+10
        while self.w._workers and time.monotonic()<deadline:self.wait(50)
        self.assertFalse(self.w._workers)
        self.w.close(); self.w.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.wait(30)

    def speech_project(self):
        p=Project(media=[MediaItem('m','missing.mp4','video','speech',3,640,360,has_audio=True)],
                  timeline=[TimelineItem('v','m','video_1',0,3),TimelineItem('a','m','audio_1',0,3,role='source_audio')])
        self.w.request_waveform=lambda _:None
        self.w.set_project(p)
        return p

    def test_process_cancel_reaps_running_child(self):
        cancel=threading.Event(); timer=threading.Timer(.2,cancel.set); timer.start()
        started=time.monotonic()
        try:
            with self.assertRaises(InterruptedError):
                run_cancellable([sys.executable,'-c','import time; time.sleep(30)'],cancel_check=cancel.is_set,capture_output=True)
        finally:timer.cancel()
        self.assertLess(time.monotonic()-started,5)

    def test_process_timeout_and_failure_are_distinct_from_cancel(self):
        import subprocess
        with self.assertRaises(subprocess.TimeoutExpired):
            run_cancellable([sys.executable,'-c','import time; time.sleep(30)'],timeout=.2)
        with self.assertRaises(subprocess.CalledProcessError):
            run_cancellable([sys.executable,'-c','raise SystemExit(7)'],check=True,capture_output=True)

    def test_cancelled_worker_keeps_terminal_contract_without_result(self):
        seen=[]
        def work():raise InterruptedError('Cancelled')
        worker=Worker(work)
        worker.signals.result.connect(lambda _:seen.append('result'))
        worker.signals.error.connect(lambda _:seen.append('error'))
        worker.signals.finished.connect(lambda:seen.append('finished'))
        self.w.start_worker(worker); self.wait()
        self.assertEqual(seen,['error','finished'])

    def test_close_keeps_window_alive_until_worker_reaped_and_rejects_late_commit(self):
        release=threading.Event(); entered=threading.Event(); committed=[]
        def work():entered.set(); release.wait(3); return 'late'
        worker=Worker(work); worker.cancel_callback=release.set
        worker.signals.result.connect(committed.append)
        self.w.start_worker(worker)
        self.assertTrue(entered.wait(2))
        event=QCloseEvent(); self.w.closeEvent(event)
        self.assertFalse(event.isAccepted()); self.assertTrue(self.w._closing)
        self.wait(250)
        self.assertFalse(self.w._workers); self.assertFalse(self.w.isVisible()); self.assertFalse(committed)

    def test_headless_tts_keeps_gui_responsive_and_rejects_project_switch(self):
        original=self.speech_project(); ticks=[]
        def delayed(*args,**kwargs):time.sleep(.3); return 'synth.wav'
        QTimer.singleShot(40,lambda:ticks.append('GUI'))
        QTimer.singleShot(90,lambda:self.w.set_project(Project()))
        with patch('kinetic_cut.tts.synthesize_speech',side_effect=delayed),patch.object(self.w,'_apply_generated_dialogue') as apply:
            self.assertIsNone(self.w.generate_tts_dialogue(initial_text='Speech',headless=True))
        self.assertTrue(ticks); apply.assert_not_called(); self.assertIsNot(self.w.project,original)

    def test_headless_tts_same_project_success_preserves_api_contract(self):
        self.speech_project()
        with patch('kinetic_cut.tts.synthesize_speech',return_value='synth.wav'),patch.object(self.w,'_apply_generated_dialogue',return_value={'clip_id':'c'}) as apply:
            self.assertEqual(self.w.generate_tts_dialogue(initial_text='Speech',headless=True),{'clip_id':'c'})
        self.assertEqual(apply.call_args.args[0]['audio_path'],'synth.wav')

    def test_caption_cancel_and_late_cancel_never_insert(self):
        for mode in ('cancel','switch','lock','mutate'):
            p=self.speech_project(); entered=threading.Event(); release=threading.Event()
            def delayed(*a,**kw):entered.set(); release.wait(2); return [Caption('c',0,1,'Speech')],'fixture'
            with patch('kinetic_cut.process.run_cancellable'),patch('kinetic_cut.ui.transcribe',side_effect=delayed):
                worker=self.w.generate_captions(headless=True)
                self.assertTrue(entered.wait(2))
                if mode=='cancel':worker.cancel()
                elif mode=='switch':self.w.set_project(Project())
                elif mode=='lock':p.track_states.setdefault('subtitle_1',{})['locked']=True
                else:p.timeline[0].in_point=.5
                release.set(); self.wait(200)
            self.assertFalse(self.w.project.captions,mode)

    def test_import_result_does_not_cross_project_switch(self):
        from kinetic_cut.config import DATA_DIR
        fixture=DATA_DIR/'import-fixture.png'; fixture.write_bytes(b'fixture')
        entered=threading.Event(); release=threading.Event()
        def delayed(*args,**kwargs):
            entered.set(); release.wait(2)
            return MediaItem('new',str(fixture),'image','fixture',3,640,360)
        with patch('kinetic_cut.ui.probe',side_effect=delayed):
            self.w.add_media_paths([str(fixture)]); self.assertTrue(entered.wait(2))
            self.w.set_project(Project()); release.set(); self.wait(200)
        self.assertFalse(self.w.project.media)

    def test_mcp_import_shutdown_settles_job_and_discards_pending_probe(self):
        from kinetic_cut.assistant_api import EditorAPI
        from kinetic_cut.config import DATA_DIR
        fixture=DATA_DIR/'mcp-import-fixture.png'; fixture.write_bytes(b'fixture')
        entered=threading.Event(); release=threading.Event()
        def delayed(*args,**kwargs):
            self.assertEqual(kwargs['timeout'],30)
            entered.set(); release.wait(2)
            return MediaItem('new',str(fixture),'image','fixture',3,640,360)
        api=EditorAPI(self.w)
        with patch('kinetic_cut.media.probe',side_effect=delayed):
            job=api.call_import_media([str(fixture)])
            self.assertTrue(entered.wait(2)); self.w.close()
            release.set(); self.wait(200)
        self.assertEqual(api.jobs[job['id']]['state'],'Cancelled')
        self.assertFalse(self.w.project.media)
        self.assertFalse(self.w._workers)


if __name__=='__main__':unittest.main()
