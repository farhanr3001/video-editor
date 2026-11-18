import json,tempfile,threading,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from kinetic_cut import offline_speech,tts
from kinetic_cut.help_ui import AboutDialog,RepairDialog,support_report

def settle(predicate):
    end=time.monotonic()+5;loop=QEventLoop();timer=QTimer();timer.setInterval(5)
    timer.timeout.connect(lambda:loop.quit() if predicate() or time.monotonic()>end else None);timer.start();loop.exec();timer.stop()
    if not predicate():raise AssertionError('Job did not settle')

class Help(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_about_and_repair_are_nonblocking_and_keep_project(self):
        from kinetic_cut.ui import MainWindow
        window=MainWindow();window.autosave_timer.stop();before=window.project
        try:
            with patch('kinetic_cut.updates.check',return_value=None):
                dialog=AboutDialog(window);dialog.show();settle(lambda:not window._workers)
                self.assertIn('up to date',dialog.status.text());self.assertEqual(dialog.channel.currentData(),'stable');dialog.close()
            repair=RepairDialog(window);repair.start();self.assertIn('installed app',repair.status.text());repair.close()
            self.assertIs(window.project,before)
        finally:window.close();settle(lambda:not window._workers)
    def test_support_report_excludes_projects_settings_credentials_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'application.log').write_text('ERROR file C:\\Users\\Person\\SecretProject.kcut\napi_key=abcdef\nhttps://host.test/?token=secret\nAuthorization: Bearer hidden-bearer\n{"api_key":"quoted-secret"}\nwss://host.test/?token=socket-secret\n')
            (root/'private.kcut').write_text('private');(root/'settings.json').write_text('key')
            output=root/'support.zip';support_report(output,{'version':'fixture'},root)
            with zipfile.ZipFile(output) as z:
                self.assertEqual(set(z.namelist()),{'system.json','application.log'});text=z.read('application.log').decode()
                for secret in ('Person','SecretProject','abcdef','host.test','token=secret','hidden-bearer','quoted-secret','socket-secret'):self.assertNotIn(secret,text)

class Offline(unittest.TestCase):
    def test_optional_voice_does_not_invoke_online_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'voice.mp3'
            def local(text,path,rate,pitch,ffmpeg,cancel):
                self.assertEqual((text,rate,pitch),('Hello',25,-4));Path(path).write_bytes(b'local audio')
            with patch.object(offline_speech,'synthesize',side_effect=local),patch.object(tts,'_synthesize_async',side_effect=AssertionError('Network forbidden')):
                tts.synthesize_speech('Hello',offline_speech.VOICE,25,-4,output_path=target)
            self.assertEqual(target.read_bytes(),b'local audio')
    def test_offline_selection_remains_usable_during_service_outage(self):
        from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog
        from kinetic_cut.tts_availability import Availability
        app=QApplication.instance() or QApplication([]);dialog=TTSDialogueDialog(initial_text='Hello')
        try:
            health=dialog.voice_availability;health.started=True;health.result=Availability(False,'Service unavailable')
            with patch.object(offline_speech,'ready',return_value=True):
                dialog.voice_combo.setCurrentIndex(dialog.voice_combo.findData(offline_speech.VOICE));health.refresh()
                self.assertTrue(health.allowed());self.assertTrue(dialog.generate_btn.isEnabled());self.assertIn('Offline voice ready',health.label.text())
            with patch.object(offline_speech,'ready',return_value=False):
                health.refresh();self.assertFalse(health.allowed());self.assertFalse(dialog.generate_btn.isEnabled());self.assertFalse(health.offline.isHidden())
        finally:dialog.close()
    def test_cancelling_offline_install_does_not_publish_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'runtime';cancel=threading.Event();cancel.set()
            with patch('kinetic_cut.verified_download.fetch',side_effect=InterruptedError('paused')):
                with self.assertRaises(InterruptedError):offline_speech.install(lambda *_:None,cancel,root)
            self.assertFalse((root/'ready.json').exists())
