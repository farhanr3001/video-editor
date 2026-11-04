import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('KINETIC_CUT_HOME', tempfile.mkdtemp(prefix='kc-speech-'))

from PySide6.QtWidgets import QApplication, QMessageBox

from kinetic_cut import caption_runtime


def model_folder(root):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    (root / 'model.bin').write_bytes(b'x'); (root / 'config.json').write_text('{}'); return root


class SpeechModelRuntimeTests(unittest.TestCase):
    def test_turbo_uses_the_repository_faster_whisper_downloads(self):
        self.assertEqual(caption_runtime.repository('large-v3-turbo'), 'mobiuslabsgmbh/faster-whisper-large-v3-turbo')
        self.assertEqual(caption_runtime.repository('base.en'), 'Systran/faster-whisper-base.en')
        self.assertIn('large-v3-turbo', caption_runtime.CHOICES)

    def test_a_model_folder_is_used_directly(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = model_folder(Path(directory) / 'turbo')
            self.assertEqual(caption_runtime.model_arguments(str(folder)), (str(folder), {}))
            self.assertEqual(caption_runtime.model_status(str(folder))[0], 'ready')

    def test_missing_folder_fails_clearly_instead_of_downloading(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / 'nope')
            with self.assertRaises(FileNotFoundError):
                caption_runtime.model_arguments(missing)
            self.assertEqual(caption_runtime.model_status(missing), ('missing', ''))

    def test_named_model_not_downloaded_reports_its_size_and_downloads_into_the_app(self):
        with patch.object(caption_runtime, 'local_model', return_value=''):
            self.assertEqual(caption_runtime.model_status('large-v3-turbo'), ('download', 1620))
            name, options = caption_runtime.model_arguments('large-v3-turbo')
        self.assertEqual(name, 'large-v3-turbo'); self.assertIn('download_root', options)

    def test_cached_copy_is_found_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = model_folder(Path(directory) / 'snap')
            with patch('huggingface_hub.snapshot_download', return_value=str(folder)) as download:
                self.assertEqual(caption_runtime.local_model('large-v3-turbo'), str(folder))
            self.assertEqual(download.call_args.args[0], 'mobiuslabsgmbh/faster-whisper-large-v3-turbo')
            self.assertTrue(download.call_args.kwargs['local_files_only'])


class SpeechModelSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setProperty('kineticTestDiscardUnsaved', True)

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.w = MainWindow(); self.w.autosave_timer.stop()

    def tearDown(self):
        self.w.close(); self.w.deleteLater(); self.app.processEvents()

    def dialog(self):
        from kinetic_cut.settings_dialog import SettingsDialog
        d = SettingsDialog(self.w); d.show(); d.tabs.setCurrentIndex(1); self.app.processEvents(); return d

    def test_listed_models_and_custom_folder_are_offered(self):
        self.w.settings['whisper_model'] = 'base.en'
        d = self.dialog()
        data = [d.whisper_size.itemData(i) for i in range(d.whisper_size.count())]
        self.assertEqual(data[:4], ['tiny.en', 'base.en', 'small.en', 'large-v3-turbo'])
        self.assertEqual(d.whisper_size.currentData(), 'base.en')
        self.assertFalse(d.model_folder_row.isVisibleTo(d))
        d.whisper_size.setCurrentIndex(3); d.apply()
        self.assertEqual(self.w.settings['whisper_model'], 'large-v3-turbo')
        d.close()

    def test_custom_folder_round_trips_and_is_not_reset_on_save(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = str(model_folder(Path(directory) / 'faster-whisper-large-v3-turbo'))
            self.w.settings['whisper_model'] = folder
            d = self.dialog()
            from kinetic_cut.settings_dialog import CUSTOM_MODEL
            self.assertEqual(d.whisper_size.currentData(), CUSTOM_MODEL)
            self.assertEqual(d.model_folder.text(), folder); self.assertTrue(d.model_folder_row.isVisibleTo(d))
            self.assertIn('Model found', d.model_status.text())
            d.apply(); self.assertEqual(self.w.settings['whisper_model'], folder)
            d.close()

    def test_bad_custom_folder_blocks_save(self):
        d = self.dialog()
        from kinetic_cut.settings_dialog import CUSTOM_MODEL
        d.whisper_size.setCurrentIndex(d.whisper_size.findData(CUSTOM_MODEL)); d.model_folder.setText('/definitely/not/here')
        with patch.object(QMessageBox, 'warning') as warning:
            d.accept()
        warning.assert_called_once(); self.assertTrue(d.isVisible())
        d.close()


if __name__ == '__main__':
    unittest.main()
