"""On-open speech checks, recovery, cancellation and sanitized provider errors."""
import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import aiohttp
from PySide6.QtCore import QEventLoop, QTimer, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from kinetic_cut import tts, tts_availability as health
from kinetic_cut.dialog_jobs import active_dialog_threads, cancel_dialog_threads, wait_dialog_threads
from kinetic_cut.tts_dialog import TTSDialog
from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog


def settle(condition, timeout=3):
    deadline=time.monotonic()+timeout
    loop=QEventLoop();timer=QTimer();timer.setInterval(5)
    timer.timeout.connect(lambda:loop.quit() if condition() or time.monotonic()>deadline else None)
    timer.start();loop.exec();timer.stop()
    if not condition():raise AssertionError('Speech job did not settle')


class AvailabilityUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def tearDown(self):
        for widget in self.app.topLevelWidgets():
            if isinstance(widget,(TTSDialog,TTSDialogueDialog)):widget.close();widget.deleteLater()
        cancel_dialog_threads();self.assertTrue(wait_dialog_threads())
        settle(lambda:not active_dialog_threads())
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def test_check_only_on_open_once_and_does_not_block_editing(self):
        for kind in (TTSDialog,TTSDialogueDialog):
            entered=threading.Event();release=threading.Event()
            def pending(cancel):
                entered.set()
                while not release.wait(.01):
                    if cancel():raise InterruptedError()
                return health.Availability(True)
            with patch.object(health,'probe_service',pending) as probe:
                dialog=kind(initial_text='Owner script')
                self.assertFalse(entered.is_set())
                dialog.show();settle(entered.is_set)
                self.assertIn('Checking',dialog.voice_availability.label.text())
                self.assertFalse(dialog.generate_btn.isEnabled())
                self.assertFalse(dialog.preview_btn.isEnabled())
                edit=getattr(dialog,'script_edit',None) or dialog.text_edit
                self.assertFalse(edit.isReadOnly());edit.setPlainText('Still editable')
                release.set();settle(lambda:not dialog.voice_availability.checking)
                self.assertTrue(dialog.generate_btn.isEnabled())
                dialog.hide();dialog.show();self.app.processEvents()
                self.assertTrue(dialog.voice_availability.allowed())
                dialog.close()

    def test_unavailable_and_retry_preserve_every_input(self):
        for kind in (TTSDialog,TTSDialogueDialog):
            with patch.object(health,'probe_service',return_value=health.Availability(False,'The online voice service could not be reached.')) as probe:
                dialog=kind(initial_text='Keep my script');dialog.speed_slider.setValue(15);dialog.pitch_slider.setValue(-4)
                voice=dialog.voice_combo.currentData();dialog.show()
                settle(lambda:not dialog.voice_availability.checking)
                self.assertFalse(dialog.generate_btn.isEnabled());self.assertFalse(dialog.preview_btn.isEnabled())
                for i in range(dialog.voice_combo.count()):
                    self.assertIn('unavailable',dialog.voice_combo.itemText(i))
                    self.assertFalse(dialog.voice_combo.model().item(i).isEnabled())
                self.assertTrue(dialog.voice_availability.retry.isVisible())
                probe.return_value=health.Availability(True)
                dialog.voice_availability.retry.click();settle(lambda:not dialog.voice_availability.checking)
                self.assertEqual(probe.call_count,2)
                self.assertTrue(dialog.generate_btn.isEnabled());self.assertTrue(dialog.preview_btn.isEnabled())
                self.assertEqual(dialog.voice_combo.currentData(),voice)
                self.assertEqual(dialog.speed_slider.value(),15);self.assertEqual(dialog.pitch_slider.value(),-4)
                edit=getattr(dialog,'script_edit',None) or dialog.text_edit
                self.assertEqual(edit.toPlainText(),'Keep my script');dialog.close()

    def test_missing_backend_marks_alias_and_preserves_other_voices(self):
        ids=frozenset(v for _,v in tts.VOICES if not v.startswith('adam') and v!='en-US-AndrewNeural')
        with patch.object(health,'probe_service',return_value=health.Availability(True,voices=ids)):
            dialog=TTSDialogueDialog();dialog.show();settle(lambda:not dialog.voice_availability.checking)
            self.assertFalse(dialog.generate_btn.isEnabled())
            self.assertIn('unavailable',dialog.voice_combo.itemText(0))
            dialog.voice_combo.setCurrentIndex(2)
            self.assertTrue(dialog.generate_btn.isEnabled());self.assertTrue(dialog.voice_availability.retry.isVisible())

    def test_close_pending_check_cancels_and_no_late_delivery(self):
        entered=threading.Event();cancelled=threading.Event()
        def pending(cancel):
            entered.set()
            while not cancel():time.sleep(.01)
            cancelled.set();return health.Availability(True)
        with patch.object(health,'probe_service',pending):
            dialog=TTSDialogueDialog();dialog.show();settle(entered.is_set)
            controller=dialog.voice_availability;dialog.close()
            self.assertTrue(controller.closed);self.assertIsNone(controller.token)
            settle(cancelled.is_set);settle(lambda:not active_dialog_threads())
            self.assertIsNone(controller.result)

    def test_delete_pending_check_cancels_without_destroying_running_thread(self):
        entered=threading.Event();cancelled=threading.Event()
        def pending(cancel):
            entered.set()
            while not cancel():time.sleep(.01)
            cancelled.set();raise InterruptedError()
        with patch.object(health,'probe_service',pending):
            dialog=TTSDialogueDialog();dialog.show();settle(entered.is_set)
            dialog.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            settle(cancelled.is_set);settle(lambda:not active_dialog_threads())

    def test_real_generation_failure_marks_unavailable_until_retry(self):
        with patch.object(health,'probe_service',return_value=health.Availability(True)),patch.object(QMessageBox,'critical'):
            dialog=TTSDialogueDialog(initial_text='Test');dialog.show();settle(lambda:not dialog.voice_availability.checking)
            error=tts.SpeechServiceUnavailable('The online voice service rejected the connection (HTTP 403).')
            with patch('kinetic_cut.tts_dialogue_dialog.synthesize_dialogue_batches',side_effect=error):
                dialog._on_generate_clicked();settle(lambda:not dialog._is_generating)
            self.assertFalse(dialog.generate_btn.isEnabled());self.assertTrue(dialog.voice_availability.retry.isVisible())
            dialog.voice_availability.retry.click();settle(lambda:not dialog.voice_availability.checking)
            self.assertTrue(dialog.generate_btn.isEnabled())

    def test_unexpected_probe_failure_becomes_retryable(self):
        with patch.object(health,'probe_service',side_effect=RuntimeError('private URL')):
            dialog=TTSDialogueDialog();dialog.show();settle(lambda:not dialog.voice_availability.checking)
            self.assertFalse(dialog.generate_btn.isEnabled());self.assertNotIn('private',dialog.voice_availability.label.text())


class ProbeContract(unittest.TestCase):
    def test_transient_empty_audio_retries_exact_voice_and_replaces_partial_bytes(self):
        attempts=[]
        async def save(path):
            attempts.append(Path(path))
            self.assertFalse(Path(path).exists())
            Path(path).write_bytes(b'partial' if len(attempts)<3 else b'complete')
            if len(attempts)<3:raise tts.edge_tts.exceptions.NoAudioReceived('temporary')
        with tempfile.TemporaryDirectory() as tmp,patch.object(tts.edge_tts,'Communicate') as communicate:
            communicate.return_value.save=save;target=Path(tmp)/'audio.mp3'
            tts.synthesize_speech('hello guys',voice='en-US-ChristopherNeural',rate_percent=15,pitch_hz=-3,output_path=target)
            self.assertEqual(target.read_bytes(),b'complete');self.assertEqual(communicate.call_count,3)
            self.assertTrue(all(call.args==('hello guys','en-US-ChristopherNeural') and call.kwargs==dict(rate='+15%',pitch='-3Hz') for call in communicate.call_args_list))

    def test_persistent_no_audio_is_bounded_and_does_not_publish(self):
        async def save(path):raise tts.edge_tts.exceptions.NoAudioReceived('temporary')
        with tempfile.TemporaryDirectory() as tmp,patch.object(tts.edge_tts,'Communicate') as communicate:
            communicate.return_value.save=save;target=Path(tmp)/'audio.mp3'
            with self.assertRaisesRegex(tts.SpeechServiceUnavailable,'returned no audio'):
                tts.synthesize_speech('hello guys',voice='en-US-ChristopherNeural',output_path=target)
            self.assertEqual(communicate.call_count,3);self.assertFalse(target.exists())

    def test_cancellation_interrupts_retry_delay_without_another_request(self):
        stopped=threading.Event();calls=[]
        async def request():
            calls.append(True);stopped.set();raise tts.edge_tts.exceptions.NoAudioReceived('temporary')
        started=time.monotonic()
        with self.assertRaises(InterruptedError):asyncio.run(tts._retry_speech_request(request,stopped.is_set))
        self.assertEqual(calls,[True]);self.assertLess(time.monotonic()-started,.2)

    def test_catalog_alone_is_insufficient_for_ready(self):
        async def catalog():return [{'ShortName':'en-US-AndrewNeural'}]
        async def stream():
            raise aiohttp.WSServerHandshakeError(Mock(),(),status=403,message='secret URL')
            yield
        with patch('edge_tts.list_voices',catalog),patch('edge_tts.Communicate') as communicate:
            communicate.return_value.stream=stream
            result=health.probe_service()
        self.assertFalse(result.available);self.assertIn('403',result.message);self.assertNotIn('secret',result.message)

    def test_probe_is_fixed_phrase_and_closes_stream_after_first_audio(self):
        closed=[]
        async def catalog():return [{'ShortName':'en-US-AndrewNeural'}]
        async def stream():
            try:
                yield {'type':'audio','data':b'audio'}
                raise AssertionError('Should stop after first audio')
            finally:closed.append(True)
        with patch('edge_tts.list_voices',catalog),patch('edge_tts.Communicate') as communicate:
            communicate.return_value.stream=stream
            result=health.probe_service()
            self.assertEqual(communicate.call_args.args,('Hello.','en-US-AndrewNeural'))
        self.assertTrue(result.available);self.assertEqual(closed,[True])

    def test_probe_cancellation_closes_pending_network_coroutine(self):
        cancelled=[]
        async def catalog():
            try:await asyncio.sleep(10)
            finally:cancelled.append(True)
        count=[0]
        def cancel():count[0]+=1;return count[0]>2
        with patch('edge_tts.list_voices',catalog):
            started=time.monotonic()
            with self.assertRaises(InterruptedError):health.probe_service(cancel)
        self.assertLess(time.monotonic()-started,1);self.assertEqual(cancelled,[True])

    def test_timeout_is_bounded_and_user_safe(self):
        async def catalog():await asyncio.sleep(10)
        wait_for=asyncio.wait_for
        with patch('edge_tts.list_voices',catalog),patch.object(health.asyncio,'wait_for',lambda operation,timeout:wait_for(operation,.02)):
            started=time.monotonic();result=health.probe_service()
        self.assertFalse(result.available);self.assertLess(time.monotonic()-started,1)

    def test_client_version_guard(self):
        with patch.object(tts.edge_tts,'__version_info__',(7,2,8)):
            with self.assertRaisesRegex(tts.SpeechServiceUnavailable,'out of date'):tts.check_speech_client()

    def test_failed_provider_does_not_publish_partial_audio_and_hides_urls(self):
        async def save(path):
            Path(path).write_bytes(b'partial')
            raise aiohttp.WSServerHandshakeError(Mock(),(),status=403,message='wss://secret?TrustedClientToken=private')
        with tempfile.TemporaryDirectory() as tmp,patch.object(tts.edge_tts,'Communicate') as communicate:
            communicate.return_value.save=save;target=Path(tmp)/'result.mp3'
            with self.assertRaises(tts.SpeechServiceUnavailable) as caught:
                tts.synthesize_speech('Hello',voice='en-US-ChristopherNeural',output_path=target)
            self.assertIn('403',str(caught.exception));self.assertNotIn('secret',str(caught.exception))
            self.assertFalse(target.exists());self.assertEqual(list(Path(tmp).iterdir()),[])


if __name__=='__main__':unittest.main()
