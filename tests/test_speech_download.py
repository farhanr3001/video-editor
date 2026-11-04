import tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch


class SpeechDownloadTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.root = Path(self.dir.name)
        self.patch = patch('kinetic_cut.config.DATA_DIR', self.root); self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.dir.cleanup()

    def make_copy(self, complete=True):
        from kinetic_cut import caption_runtime as cr
        folder = cr.app_model_root() / 'snapshots' / 'abc'; folder.mkdir(parents=True)
        (folder / 'config.json').write_text('{}')
        if complete: (folder / 'model.bin').write_bytes(b'x')
        return folder

    def test_only_a_complete_app_copy_counts_as_installed(self):
        from kinetic_cut import caption_runtime as cr, feature_packs
        self.assertFalse(feature_packs.installed('speech'))
        self.make_copy(complete=False); self.assertFalse(cr.app_copy_ready())
        (cr.app_model_root() / 'snapshots' / 'abc' / 'model.bin').write_bytes(b'x')
        self.assertTrue(feature_packs.installed('speech'))
        self.assertEqual(cr.model_status('large-v3-turbo')[0], 'ready')

    def test_install_reports_progress_and_validates(self):
        from kinetic_cut import caption_runtime as cr
        events = []
        def fake(repo, cache_dir, allow_patterns, tqdm_class):
            self.assertEqual(repo, 'mobiuslabsgmbh/faster-whisper-large-v3-turbo'); self.assertIn('model.bin', allow_patterns)
            bar = tqdm_class(total=100_000_000, unit='B'); bar.update(50_000_000)
            self.make_copy(); bar.update(50_000_000)
        with patch('huggingface_hub.snapshot_download', fake):
            cr.install_model(events.append, threading.Event())
        self.assertTrue(cr.app_copy_ready()); self.assertEqual(events[-1][0], 100)
        self.assertTrue(any(40 < e[0] < 60 for e in events))

    def test_cancel_and_failures_leave_no_false_install(self):
        from kinetic_cut import caption_runtime as cr
        cancel = threading.Event()
        def fake(repo, cache_dir, allow_patterns, tqdm_class):
            cancel.set(); tqdm_class(total=100_000_000, unit='B').update(1)
        with patch('huggingface_hub.snapshot_download', fake):
            with self.assertRaises(InterruptedError): cr.install_model(lambda e: None, cancel)
        def broken(*a, **k): raise OSError('offline')
        with patch('huggingface_hub.snapshot_download', broken):
            with self.assertRaisesRegex(RuntimeError, 'internet connection'): cr.install_model(lambda e: None, threading.Event())
        self.assertFalse(cr.app_copy_ready())

    def test_remove_deletes_only_the_app_copy(self):
        from kinetic_cut import caption_runtime as cr, feature_packs
        self.make_copy(); other = self.root / 'models' / 'huggingface' / 'models--other--thing'; other.mkdir(parents=True)
        custom = self.root / 'my-folder'; custom.mkdir()
        feature_packs.remove('speech')
        self.assertFalse(cr.app_model_root().exists()); self.assertTrue(other.exists()); self.assertTrue(custom.exists())
        feature_packs.remove('speech')  # already gone: no error

    def test_not_enough_disk_space_is_reported(self):
        from kinetic_cut import caption_runtime as cr
        with patch('shutil.disk_usage', return_value=__import__('types').SimpleNamespace(free=10)):
            with self.assertRaisesRegex(RuntimeError, 'disk space'): cr.install_model(lambda e: None, threading.Event())


if __name__ == '__main__':
    unittest.main()
