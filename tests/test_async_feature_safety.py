"""Real Qt job lifetimes and deterministic late-result/cancellation failures."""
import gc
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PySide6.QtCore import QEvent, QThreadPool, Qt, Signal, QBuffer, QIODevice, QTimer
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QWidget, QMessageBox
from kinetic_cut import captions
from kinetic_cut.downloader_dialog import (MediaDownloaderDialog, _FetchMetadataWorker,
    _DownloadWorker, _DownloaderCallbacks)
from kinetic_cut.dialog_jobs import active_dialog_threads, cancel_dialog_threads

app=QApplication.instance() or QApplication([])


def drain(predicate,timeout=5):
    deadline=time.monotonic()+timeout
    while not predicate() and time.monotonic()<deadline:
        app.processEvents(); app.sendPostedEvents(None,QEvent.DeferredDelete); time.sleep(.005)
    app.processEvents(); app.sendPostedEvents(None,QEvent.DeferredDelete)
    return predicate()


class DownloaderFailureTests(unittest.TestCase):
    def tearDown(self):
        cancel_dialog_threads()
        self.assertTrue(drain(lambda:not active_dialog_threads()))

    def test_close_delete_and_collect_repeated_active_metadata_dialogs(self):
        # The original QThread ownership aborts this process (0xC0000409).
        entered=[]
        def metadata(command,cancel,*args,**kwargs):
            entered.append(cancel)
            cancel.wait(.08)
            return subprocess.CompletedProcess(command,0,json.dumps({'title':'Late result'}),'')
        with patch('kinetic_cut.downloader_dialog._capture_process',side_effect=metadata),patch('kinetic_cut.downloader_dialog.get_ytdlp_runtime_args',return_value=[]):
            for index in range(30):
                dialog=MediaDownloaderDialog(); dialog._headless=True
                dialog.url_input.setText('https://example.invalid/video'); dialog._on_fetch_clicked()
                self.assertTrue(drain(lambda:len(entered)==index+1))
                dialog.close(); dialog.deleteLater(); del dialog
                app.sendPostedEvents(None,QEvent.DeferredDelete); gc.collect()
            self.assertTrue(drain(lambda:not active_dialog_threads()))
        self.assertEqual(len(entered),30)
        self.assertTrue(all(cancel.is_set() for cancel in entered))

    def test_stale_metadata_and_cancelled_download_results_are_ignored(self):
        dialog=MediaDownloaderDialog(); dialog._headless=True
        try:
            dialog.url_input.setText('https://example.invalid/old')
            old=_FetchMetadataWorker(dialog.url_input.text())
            stale=_DownloaderCallbacks(dialog,'fetch',old)
            dialog.url_input.setText('https://example.invalid/new')
            current=_DownloaderCallbacks(dialog,'fetch',_FetchMetadataWorker(dialog.url_input.text()))
            stale.metadata({'title':'OLD'})
            self.assertIsNone(dialog.metadata)
            current.metadata({'title':'NEW','thumbnail':''})
            self.assertEqual(dialog.title_lbl.text(),'NEW')
            worker=_DownloadWorker('url','video',Path('.'))
            callbacks=_DownloaderCallbacks(dialog,'download',worker)
            received=[]; dialog.mediaDownloaded.connect(received.append)
            worker.cancel(); callbacks.result('cancelled.mp4')
            self.assertEqual(received,[])
        finally:dialog.close(); dialog.deleteLater()

    def test_repeated_native_metadata_and_thumbnail_results_retire_callbacks(self):
        # Fast completion can delete the native sender before the GUI dispatch.
        image=QImage(20,20,QImage.Format_RGBA8888); image.fill(QColor('orange'))
        buffer=QBuffer(); buffer.open(QIODevice.WriteOnly); image.save(buffer,'PNG'); payload=bytes(buffer.data())
        def metadata(command,cancel,*args,**kwargs):
            return subprocess.CompletedProcess(command,0,json.dumps({'title':command[-1],'thumbnail':'https://example.invalid/thumb.png'}),'')
        dialog=MediaDownloaderDialog(); dialog._headless=True
        try:
            with patch('kinetic_cut.downloader_dialog._capture_process',side_effect=metadata),patch('kinetic_cut.downloader_dialog.get_ytdlp_runtime_args',return_value=[]),patch('urllib.request.urlopen',side_effect=lambda *a,**k:io.BytesIO(payload)):
                for index in range(50):
                    url='https://example.invalid/'+str(index); dialog.url_input.setText(url); dialog._on_fetch_clicked()
                    self.assertTrue(drain(lambda:dialog.title_lbl.text()==url and dialog._fetch_thread is None and dialog._thumb_thread is None))
                    self.assertFalse(dialog.thumb_label.pixmap().isNull())
                    self.assertEqual(dialog.findChildren(_DownloaderCallbacks),[])
                    self.assertFalse(active_dialog_threads())
        finally:dialog.close(); dialog.deleteLater()

    def test_duplicate_clicks_and_url_changes_never_start_parallel_downloads(self):
        workers=[]
        def download(worker):
            workers.append(worker); worker._cancel.wait(1); worker.settled.emit()
        dialog=MediaDownloaderDialog(); dialog._headless=True
        try:
            with patch.object(_DownloadWorker,'run',download):
                dialog.url_input.setText('https://example.invalid/one'); dialog._start_download('video')
                self.assertTrue(drain(lambda:len(workers)==1))
                for _ in range(30):
                    dialog.url_input.setText('https://example.invalid/two'); dialog._start_download('audio')
                self.assertFalse(dialog.btn_download_video.isEnabled())
                self.assertFalse(dialog.btn_download_audio.isEnabled())
                self.assertEqual(len(workers),1)
                dialog.cancel_download_btn.click()
                self.assertTrue(drain(lambda:dialog._download_thread is None))
                self.assertTrue(dialog.btn_download_video.isEnabled())
                self.assertIn('cancelled',dialog.status_lbl.text().lower())
        finally:dialog.close(); dialog.deleteLater()

    def test_cancel_silent_download_reaps_child_and_cleans_job_log(self):
        from kinetic_cut.process import popen
        children=[]
        def silent(command,**kwargs):
            child=popen([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
            children.append(child); return child
        with tempfile.TemporaryDirectory() as temp:
            worker=_DownloadWorker('https://example.invalid/video','video',Path(temp))
            errors=[]; results=[]; worker.error.connect(errors.append); worker.finished.connect(results.append)
            timer=threading.Timer(.2,worker.cancel); timer.start(); started=time.monotonic()
            try:
                with patch('kinetic_cut.downloader_dialog.popen',side_effect=silent),patch('kinetic_cut.downloader_dialog.get_ytdlp_runtime_args',return_value=[]):worker.run()
            finally:timer.cancel()
            self.assertLess(time.monotonic()-started,5)
            self.assertIsNotNone(children[0].poll()); self.assertEqual(errors,[]); self.assertEqual(results,[])
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_download_uses_reported_output_not_newest_unrelated_file(self):
        from kinetic_cut.process import popen
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); actual=root/'actual.mp4'; actual.write_bytes(b'clip')
            unrelated=root/'unrelated.mp4'; unrelated.write_bytes(b'other')
            def complete(command,**kwargs):
                self.assertIn('--progress',command)
                return popen([sys.executable,'-u','-c','import sys,json; print("KC_PATH:"+json.dumps(sys.argv[1]),flush=True)',str(actual)],**kwargs)
            worker=_DownloadWorker('https://example.invalid/video','video',root)
            found=[]; errors=[]; worker.finished.connect(found.append); worker.error.connect(errors.append)
            with patch('kinetic_cut.downloader_dialog.popen',side_effect=complete),patch('kinetic_cut.downloader_dialog.get_ytdlp_runtime_args',return_value=[]):worker.run()
            self.assertEqual(errors,[]); self.assertEqual(found,[str(actual.resolve())])
            self.assertFalse(list(root.glob('.kinetic-download-*')))

    def test_direct_sound_cancel_or_incomplete_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); original=root/'Sound.mp3'; original.write_bytes(b'previous')
            for cancel in (True,False):
                worker=_DownloadWorker('url','audio',root,direct_audio_url='https://example.invalid/a.mp3',sound_title='Sound')
                class Response(io.BytesIO):
                    headers={'Content-Length':'100'}
                    def read(self,*args):
                        data=super().read(*args)
                        if cancel:worker.cancel()
                        return data
                errors=[]; worker.error.connect(errors.append)
                with patch('urllib.request.urlopen',return_value=Response(b'partial')):worker.run()
                self.assertEqual(original.read_bytes(),b'previous')
                self.assertFalse(list(root.glob('*.partial')))
                if not cancel:self.assertIn('incomplete',errors[0].lower())

    def test_automation_downloader_cancel_reaps_silent_child(self):
        from kinetic_cut.downloader_dialog import download_media_synchronous
        from kinetic_cut.process import popen
        event=threading.Event(); children=[]
        def silent(command,**kwargs):
            child=popen([sys.executable,'-c','import time;time.sleep(30)'],**kwargs); children.append(child); return child
        with tempfile.TemporaryDirectory() as temp:
            timer=threading.Timer(.2,event.set); timer.start()
            try:
                with patch('kinetic_cut.downloader_dialog.popen',side_effect=silent),patch('kinetic_cut.downloader_dialog.get_ytdlp_runtime_args',return_value=[]):
                    with self.assertRaises(InterruptedError):download_media_synchronous('https://example.invalid/video',output_dir=Path(temp),cancel_check=event.is_set)
                self.assertIsNotNone(children[0].poll()); self.assertEqual(list(Path(temp).iterdir()),[])
            finally:timer.cancel()


class CaptionCancellationTests(unittest.TestCase):
    def test_precancel_does_not_load_or_start_any_backend(self):
        with patch('kinetic_cut.captions._windows_speech') as fallback:
            with self.assertRaises(captions.CaptionCancelled):captions.transcribe('source.wav',{},cancel_check=lambda:True)
            fallback.assert_not_called()

    def test_cancel_during_native_segment_iteration_never_falls_back(self):
        event=threading.Event(); parent=types.ModuleType('faster_whisper')
        audio=types.ModuleType('faster_whisper.audio'); vad=types.ModuleType('faster_whisper.vad')
        class Model:
            def __init__(self,*args,**kwargs):pass
            def transcribe(self,*args,**kwargs):
                def segments():
                    yield types.SimpleNamespace(start=0.,end=1.,text='hello',words=[types.SimpleNamespace(word='hello',start=0.,end=1.)])
                    event.set()
                    yield types.SimpleNamespace(start=1.,end=2.,text='world',words=[])
                return segments(),None
        parent.WhisperModel=Model; audio.decode_audio=lambda *a,**k:[0]*32000
        vad.VadOptions=lambda **k:None; vad.get_speech_timestamps=lambda *a:[{'start':0,'end':32000}]
        with patch.dict(sys.modules,{'faster_whisper':parent,'faster_whisper.audio':audio,'faster_whisper.vad':vad}),patch('kinetic_cut.caption_runtime.model_arguments',return_value=('fixture',{})),patch('kinetic_cut.captions._windows_speech') as fallback:
            with self.assertRaises(captions.CaptionCancelled):captions.transcribe('source.wav',{},cancel_check=event.is_set)
            fallback.assert_not_called()

    def test_cancel_silent_caption_process_reaps_child(self):
        from kinetic_cut.process import popen
        event=threading.Event(); children=[]
        def start(*args,**kwargs):child=popen(*args,**kwargs); children.append(child); return child
        timer=threading.Timer(.2,event.set); timer.start(); started=time.monotonic()
        try:
            with patch('kinetic_cut.process.popen',side_effect=start):
                with self.assertRaises(captions.CaptionCancelled):captions.run_caption_process([sys.executable,'-c','import time;time.sleep(30)'],event.is_set,capture_output=True,text=True)
            self.assertLess(time.monotonic()-started,5); self.assertIsNotNone(children[0].poll())
        finally:timer.cancel()


class ComponentLifetimeTests(unittest.TestCase):
    def test_close_delete_still_cancels_and_retires_component_registry(self):
        from kinetic_cut.component_ui import InstallComponentDialog,active_downloads,_jobs
        entered=threading.Event(); tokens=[]
        def install(key,progress,cancel):
            tokens.append(cancel); entered.set(); cancel.wait(1)
            progress((50,'Late progress'))
            if cancel.is_set():raise InterruptedError('cancelled')
        with patch('kinetic_cut.feature_packs.manifest',return_value={}),patch('kinetic_cut.feature_packs.install',side_effect=install):
            dialog=InstallComponentDialog(None,'android'); dialog.begin()
            self.assertTrue(entered.wait(2)); self.assertIn('android',active_downloads)
            dialog.close(); dialog.deleteLater(); del dialog
            app.sendPostedEvents(None,QEvent.DeferredDelete); gc.collect()
            self.assertTrue(drain(lambda:'android' not in active_downloads))
            self.assertNotIn('android',_jobs); self.assertTrue(tokens[0].is_set())
        self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))

    def test_two_component_dialogs_cannot_install_same_root_concurrently(self):
        from kinetic_cut.component_ui import InstallComponentDialog,active_downloads
        entered=[]
        def install(key,progress,cancel):entered.append(key); cancel.wait(1); raise InterruptedError('cancelled')
        with patch('kinetic_cut.feature_packs.manifest',return_value={}),patch('kinetic_cut.feature_packs.install',side_effect=install):
            first=InstallComponentDialog(None,'android'); second=InstallComponentDialog(None,'android')
            try:
                first.begin(); self.assertTrue(drain(lambda:len(entered)==1)); second.begin()
                self.assertFalse(second.running); self.assertIn('already downloading',second.status.text())
                first.close(); self.assertTrue(drain(lambda:'android' not in active_downloads)); self.assertEqual(entered,['android'])
            finally:first.close(); second.close(); first.deleteLater(); second.deleteLater()

    def test_installer_close_keeps_gui_responsive_until_own_worker_settles(self):
        from kinetic_cut.component_ui import installer_downloads,_InstallerDownloadsDialog,_installer_jobs
        entered=threading.Event(); release=threading.Event(); cancellations=[]; snapshots=[]
        ticks=[]; closed_at=[]; cancelled_dialog=[]; retained_counts=[]
        def install(key,progress,cancel,local_source):
            cancellations.append(cancel); entered.set(); progress((10,'Working'))
            release.wait(2); progress((90,'Late progress after close'))
            if cancel.is_set():raise InterruptedError('cancelled')
        def heartbeat():
            ticks.append(time.monotonic())
            if entered.is_set() and not closed_at:
                dialog=next((w for w in app.topLevelWidgets() if isinstance(w,_InstallerDownloadsDialog)),None)
                if dialog and dialog.bar.value()==10:
                    snapshots.append((dialog.bar.value(),dialog.status.text()))
                    cancelled_dialog.append(dialog); dialog.close(); closed_at.append(len(ticks))
            elif closed_at and not release.is_set() and len(ticks)-closed_at[0]>=6:
                snapshots.append((cancelled_dialog[0].bar.value(),cancelled_dialog[0].status.text()))
                retained_counts.append(len(_installer_jobs)); release.set()
        timer=QTimer(); timer.setInterval(10); timer.timeout.connect(heartbeat); timer.start()
        previous=app.quitOnLastWindowClosed(); app.setQuitOnLastWindowClosed(True); started=time.monotonic()
        try:
            with patch('kinetic_cut.feature_packs.install',side_effect=install):code=installer_downloads(['android'])
            self.assertEqual(code,1); self.assertTrue(cancellations[0].is_set())
            self.assertLess(time.monotonic()-started,1)
            self.assertGreaterEqual(len(ticks)-closed_at[0],6); self.assertEqual(snapshots[0],snapshots[1])
            self.assertEqual(retained_counts,[1])
            self.assertFalse(_installer_jobs); self.assertTrue(app.quitOnLastWindowClosed())
        finally:
            release.set(); timer.stop(); timer.deleteLater(); app.setQuitOnLastWindowClosed(previous)

    def test_installer_waits_only_for_its_batch_not_unrelated_pool_work(self):
        from kinetic_cut.component_ui import installer_downloads,_installer_jobs
        from kinetic_cut.ui import Worker
        entered=threading.Event(); release=threading.Event()
        def unrelated():entered.set(); release.wait(2)
        worker=Worker(unrelated); QThreadPool.globalInstance().start(worker)
        self.assertTrue(entered.wait(2)); started=time.monotonic()
        try:
            with patch('kinetic_cut.feature_packs.install',side_effect=lambda key,progress,cancel,source:progress((100,'Done'))):code=installer_downloads(['android'])
            self.assertEqual(code,0); self.assertLess(time.monotonic()-started,1)
            self.assertFalse(release.is_set()); self.assertFalse(_installer_jobs)
        finally:
            release.set(); self.assertTrue(QThreadPool.globalInstance().waitForDone(3000)); worker.signals.deleteLater()

    def test_installer_failure_is_terminal_and_preserves_error_log(self):
        from kinetic_cut.component_ui import installer_downloads,_installer_jobs
        from kinetic_cut.config import DATA_DIR
        with self.assertLogs('root',level='ERROR'),patch('kinetic_cut.feature_packs.install',side_effect=ValueError('broken optional pack')):code=installer_downloads(['android'])
        self.assertEqual(code,1); self.assertFalse(_installer_jobs)
        self.assertIn('broken optional pack',(DATA_DIR/'component-install.log').read_text(encoding='utf-8'))

    def test_installer_close_and_delete_never_updates_destroyed_popup(self):
        from kinetic_cut.component_ui import installer_downloads,_InstallerDownloadsDialog,_installer_jobs
        entered=threading.Event(); release=threading.Event(); closed=[]
        def install(key,progress,cancel,source):
            entered.set(); release.wait(1); progress((90,'Late update'))
            if cancel.is_set():raise InterruptedError('cancelled')
        def destroy_popup():
            if not entered.is_set():return
            dialog=next((w for w in app.topLevelWidgets() if isinstance(w,_InstallerDownloadsDialog)),None)
            if dialog:
                dialog.close(); dialog.deleteLater(); closed.append(True)
                app.sendPostedEvents(None,QEvent.DeferredDelete); release.set()
        timer=QTimer(); timer.setInterval(10); timer.timeout.connect(destroy_popup); timer.start()
        try:
            with patch('kinetic_cut.feature_packs.install',side_effect=install):code=installer_downloads(['android'])
            self.assertEqual(code,1); self.assertEqual(closed,[True]); self.assertFalse(_installer_jobs)
        finally:release.set(); timer.stop(); timer.deleteLater()


class UpdateCancellationTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.update_ui import UpdateController
        class Window(QWidget):
            shutdownFinished=Signal()
            def __init__(self):super().__init__(); self.transport=types.SimpleNamespace(closed=False); self.settings={}; self.workers=[]
            def start_worker(self,worker):self.workers.append(worker)
        self.window=Window(); self.controller=UpdateController(self.window)
    def tearDown(self):self.window.close(); self.window.deleteLater(); app.processEvents()

    def test_closing_manual_check_prevents_late_result_dialog(self):
        from kinetic_cut.update_ui import UpdateDialog
        self.controller.check(); self.controller.dialog.reject()
        with patch.object(UpdateDialog,'exec') as execute:self.window.workers[-1].signals.result.emit(None)
        self.assertFalse(self.controller.busy); execute.assert_not_called()

    def test_successful_manual_check_still_opens_current_status(self):
        from kinetic_cut.update_ui import UpdateDialog
        self.controller.check()
        with patch.object(UpdateDialog,'exec',return_value=0) as execute:self.window.workers[-1].signals.result.emit(None)
        execute.assert_called_once(); self.assertFalse(self.controller.busy)

    def test_cancel_before_queued_download_success_never_prompts_install(self):
        from PySide6.QtWidgets import QProgressDialog
        event=threading.Event(); event.set(); progress=QProgressDialog(self.window)
        with patch.object(QMessageBox,'question') as prompt:self.controller.ready('update.exe',progress,cancelled=event)
        prompt.assert_not_called(); self.assertFalse(self.controller.busy)

    def test_actual_download_error_is_not_mistaken_for_cancel_on_close(self):
        from kinetic_cut.update_ui import UpdateDialog
        from PySide6.QtWidgets import QProgressDialog
        event=threading.Event(); progress=QProgressDialog(self.window); progress.canceled.connect(event.set)
        with patch.object(UpdateDialog,'exec',return_value=0) as execute:self.controller.download_failed('network failure',progress,event)
        execute.assert_called_once(); self.assertFalse(self.controller.busy)

    def test_update_launch_waits_for_deferred_shutdown_and_runs_once(self):
        from PySide6.QtWidgets import QProgressDialog
        for incremental in (False,True):
            with self.subTest(incremental=incremental):
                self.window._closing=True
                progress=QProgressDialog(self.window)
                with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(self.window,'close',return_value=False),patch('shutil.copy2'),patch('kinetic_cut.process.popen') as launch:
                    self.controller.ready('update.json' if incremental else 'update.exe',progress,incremental)
                    launch.assert_not_called()
                    self.window.shutdownFinished.emit(); launch.assert_called_once()
                    self.window.shutdownFinished.emit(); launch.assert_called_once()
                    if incremental:self.assertIn('apply',launch.call_args.args[0])

    def test_cancelled_save_prompt_never_leaves_updater_connected(self):
        from PySide6.QtWidgets import QProgressDialog
        self.window._closing=False; progress=QProgressDialog(self.window)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(self.window,'close',return_value=False),patch('kinetic_cut.process.popen') as launch:
            self.controller.ready('update.exe',progress)
            self.window.shutdownFinished.emit(); launch.assert_not_called()

    def test_immediate_shutdown_signal_and_true_return_launch_only_once(self):
        from PySide6.QtWidgets import QProgressDialog
        def close():self.window.shutdownFinished.emit(); return True
        progress=QProgressDialog(self.window)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(self.window,'close',side_effect=close),patch('kinetic_cut.process.popen') as launch:
            self.controller.ready('update.exe',progress); launch.assert_called_once()

    def test_actual_main_window_handoff_waits_for_native_worker_retirement(self):
        from kinetic_cut.ui import MainWindow, Worker
        from kinetic_cut.update_ui import UpdateController
        from PySide6.QtWidgets import QProgressDialog
        window=MainWindow(); controller=UpdateController(window); entered=threading.Event()
        def slow():entered.set(); time.sleep(.2)
        window.start_worker(Worker(slow)); self.assertTrue(entered.wait(2))
        observations=[]
        def launch(command):observations.append((len(window._workers),window.transport.closed,command))
        try:
            with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch('kinetic_cut.process.popen',side_effect=launch):
                controller.ready('update.exe',QProgressDialog(window))
                self.assertTrue(window._closing); self.assertEqual(observations,[])
                self.assertTrue(drain(lambda:len(observations)==1))
                self.assertEqual(observations,[(0,True,['update.exe'])])
        finally:window.close(); window.deleteLater(); app.processEvents()


class CacheRemovalFailureTests(unittest.TestCase):
    def setUp(self):
        from PySide6.QtCore import QProcess
        self.window=QWidget()
        self.window._workers=set(); self.window.delivery=types.SimpleNamespace(running=False)
        self.window.transport=types.SimpleNamespace(playing=False)
        self.window.phone_connect=types.SimpleNamespace(active_job=None,mirror=types.SimpleNamespace(process=types.SimpleNamespace(state=lambda:QProcess.NotRunning)))
        self.window.timeline=types.SimpleNamespace(thumbnails={},_scaled_thumbnails={},_waveform_pixmaps={},viewport=lambda:types.SimpleNamespace(update=lambda:None))
        self.window.proxies={}; self.window.media_panel=types.SimpleNamespace(refresh=lambda:None)
    def tearDown(self):self.window.close(); self.window.deleteLater(); app.processEvents()

    def test_component_only_removal_does_not_validate_unselected_cache(self):
        from kinetic_cut.cache_manager import CacheManagerDialog
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'phone-android-v1'; root.mkdir(); (root/'tool.exe').write_bytes(b'tool')
            with patch('kinetic_cut.feature_packs.manifest',return_value={}),patch('kinetic_cut.feature_packs.installed',side_effect=lambda key:key=='android' and root.exists()),patch('kinetic_cut.feature_packs.component_root',return_value=root),patch('kinetic_cut.cache_manager.clear',side_effect=PermissionError('unselected cache inaccessible')) as clear,patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(QMessageBox,'information'),patch.object(QMessageBox,'warning') as warning:
                dialog=CacheManagerDialog(self.window); dialog.component_rows['android'][0].setChecked(True)
                dialog.clear_selected(); clear.assert_not_called(); warning.assert_not_called()
                self.assertFalse(root.exists()); dialog.close(); dialog.deleteLater()

    def test_selected_cache_failure_is_reported_and_clear_button_recovers(self):
        from kinetic_cut.cache_manager import CacheManagerDialog
        with patch('kinetic_cut.feature_packs.manifest',return_value={}),patch('kinetic_cut.feature_packs.installed',return_value=False),patch('kinetic_cut.cache_manager.clear',side_effect=PermissionError('selected cache inaccessible')) as clear,patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(QMessageBox,'warning') as warning:
            dialog=CacheManagerDialog(self.window); dialog.rows['thumbs'][0].setEnabled(True); dialog.rows['thumbs'][0].setChecked(True)
            dialog.clear_selected(); clear.assert_called_once_with(['thumbs'])
            self.assertIn('selected cache inaccessible',warning.call_args.args[2])
            self.assertTrue(dialog.clear_button.isEnabled()); dialog.close(); dialog.deleteLater()


class AssistantDownloadSafetyTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.assistant_api import EditorAPI
        self.window=MainWindow(); self.api=EditorAPI(self.window)
    def tearDown(self):
        self.window.close(); self.assertTrue(drain(lambda:not self.window._workers))
        self.window.deleteLater(); app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()

    def test_waiting_download_close_cancels_and_finished_releases_gui_loop(self):
        entered=threading.Event(); checks=[]
        def download(*args,cancel_check=None,**kwargs):
            checks.append(cancel_check); entered.set()
            while not cancel_check():time.sleep(.01)
            raise InterruptedError('cancelled')
        QTimer.singleShot(100,self.window.close); started=time.monotonic()
        with patch('kinetic_cut.downloader_dialog.download_media_synchronous',side_effect=download):
            with self.assertRaises(InterruptedError):self.api.call_download_media('https://example.invalid/video',auto_import=False,wait=True)
        self.assertTrue(entered.is_set()); self.assertTrue(checks[0]()); self.assertLess(time.monotonic()-started,3)
        self.assertEqual(list(self.api.jobs.values())[-1]['state'],'Cancelled')
        self.assertFalse(self.window.project.media)

    def test_finished_without_payload_is_terminal_instead_of_waiting_forever(self):
        def start(worker):QTimer.singleShot(0,worker.signals.finished.emit)
        with patch.object(self.window,'start_worker',side_effect=start):
            with self.assertRaisesRegex(RuntimeError,'did not complete'):self.api.call_download_media('https://example.invalid/video',auto_import=False,wait=True)
        self.assertEqual(list(self.api.jobs.values())[-1]['state'],'Failed')

    def test_error_is_terminal_and_returned_to_waiting_caller(self):
        def start(worker):
            def fail():worker.signals.error.emit('connection failed'); worker.signals.finished.emit()
            QTimer.singleShot(0,fail)
        with patch.object(self.window,'start_worker',side_effect=start):
            with self.assertRaisesRegex(RuntimeError,'connection failed'):self.api.call_download_media('https://example.invalid/video',auto_import=False,wait=True)
        self.assertEqual(list(self.api.jobs.values())[-1]['state'],'Failed')

    def test_async_cancelled_result_never_imports_and_project_switch_is_respected(self):
        from kinetic_cut.model import MediaItem, Project
        captured=[]; media=MediaItem('m','clip.mp4','video','Clip',1,64,64)
        payload=(dict(path='clip.mp4',name='clip.mp4',mode='video'),media)
        with patch.object(self.window,'start_worker',side_effect=captured.append):
            first=self.api.call_download_media('https://example.invalid/one',wait=False)
            captured[-1].cancel(); captured[-1].signals.result.emit(payload); captured[-1].signals.finished.emit()
            self.assertEqual(self.api.jobs[first['id']]['state'],'Cancelled'); self.assertFalse(self.window.project.media)
            second=self.api.call_download_media('https://example.invalid/two',wait=False)
            self.window.set_project(Project()); captured[-1].signals.result.emit(payload); captured[-1].signals.finished.emit()
            self.assertEqual(self.api.jobs[second['id']]['state'],'Complete'); self.assertFalse(self.api.jobs[second['id']]['imported'])
            self.assertFalse(self.window.project.media)

    def test_probe_runs_off_gui_with_bounded_timeout_and_snapshotted_settings(self):
        from kinetic_cut.model import MediaItem
        worker_ids=[]; main_id=threading.get_ident()
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'clip.mp4'; source.write_bytes(b'fixture')
            def download(*args,**kwargs):
                worker_ids.append(threading.get_ident()); return dict(path=str(source),name=source.name,mode='video')
            def probe(*args,**kwargs):
                worker_ids.append(threading.get_ident()); self.assertEqual(kwargs['timeout'],30)
                return MediaItem('m',str(source),'video','Clip',1,64,64)
            with patch('kinetic_cut.downloader_dialog.download_media_synchronous',side_effect=download),patch('kinetic_cut.media.probe',side_effect=probe),patch.object(self.window,'media_added') as added:
                result=self.api.call_download_media('https://example.invalid/video',wait=True)
                self.assertTrue(result['imported']); added.assert_called_once()
        self.assertEqual(len(worker_ids),2); self.assertTrue(all(identity!=main_id for identity in worker_ids))
