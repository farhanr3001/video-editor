import os
import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from kinetic_cut.cache_manager import CLEAR_PLAYBACK_ON_EXIT, clear_on_exit, prune_idle_playback


def touch(path, age=0., size=4):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'x' * size)
    stamp = time.time() - age; os.utime(path, (stamp, stamp)); return path


class PlaybackCacheTests(unittest.TestCase):
    def test_startup_prunes_only_playback_copies_idle_for_a_day(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = touch(root / 'proxies' / 'full-seek-0123456789abcdef.mp4', age=25 * 3600)
            fresh = touch(root / 'proxies' / 'full-seek-fedcba9876543210.mp4', age=3600)
            thumb = touch(root / 'thumbs' / 'a.jpg', age=30 * 86400)
            other = touch(root / 'proxies' / 'notes.txt', age=30 * 86400)
            self.assertEqual(prune_idle_playback(root), (1, 4))
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists() and thumb.exists() and other.exists())

    def test_reused_copy_is_marked_as_used(self):
        from unittest.mock import patch
        from kinetic_cut import media as media_module
        from kinetic_cut.model import MediaItem
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'clip.mp4'; source.write_bytes(b'video')
            item = MediaItem('m', str(source), 'video', 'clip.mp4', 1., 1920, 1080, 30., False)
            with patch.object(media_module, 'CACHE_DIR', Path(directory)):
                target = media_module.proxy_path(item, seek_cache=True)
                touch(target, age=3 * 86400)
                self.assertEqual(media_module.generate_proxy(item, seek_cache=True), str(target))
                self.assertLess(time.time() - target.stat().st_mtime, 60)

    def test_exit_clears_playback_copies_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proxy = touch(root / 'proxies' / 'full-seek-0123456789abcdef.mp4')
            wave = touch(root / 'waveforms' / 'a.npz')
            preview = touch(root / 'audio-preview-0123456789abcdef.wav')
            other = touch(root / 'keep-me.wav')
            clear_on_exit({CLEAR_PLAYBACK_ON_EXIT: False}, root)
            self.assertTrue(proxy.exists()); self.assertFalse(wave.exists()); self.assertTrue(preview.exists())
            clear_on_exit({CLEAR_PLAYBACK_ON_EXIT: True}, root)
            self.assertFalse(proxy.exists()); self.assertFalse(preview.exists())
            self.assertTrue(other.exists())     # only audio-preview-*.wav files are ever removed

    def test_startup_prunes_idle_audio_previews_even_without_proxies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = touch(root / 'audio-preview-aaaa.flac', age=3 * 86400)
            legacy = touch(root / 'audio-preview-bbbb.wav', age=3 * 86400)
            fresh = touch(root / 'audio-preview-cccc.flac')
            other = touch(root / 'notes.flac', age=3 * 86400)
            count, _ = prune_idle_playback(root)
            self.assertEqual(count, 2)
            self.assertFalse(old.exists()); self.assertFalse(legacy.exists())
            self.assertTrue(fresh.exists()); self.assertTrue(other.exists())

    def test_clearing_is_on_by_default_for_a_first_run(self):
        from unittest.mock import patch
        from kinetic_cut import config
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proxy = touch(root / 'proxies' / 'full-seek-0123456789abcdef.mp4')
            preview = touch(root / 'audio-preview-0123456789abcdef.wav')
            with patch.object(config, 'SETTINGS_PATH', root / 'missing-settings.json'):
                fresh = config.load_settings()
            self.assertIs(fresh[CLEAR_PLAYBACK_ON_EXIT], True)
            clear_on_exit(fresh, root)
            self.assertFalse(proxy.exists()); self.assertFalse(preview.exists())

    def test_cache_manager_toggle_saves_the_setting(self):
        from unittest.mock import patch
        app = QApplication.instance() or QApplication([])
        app.setProperty('kineticTestDiscardUnsaved', True)
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.cache_manager import CacheManagerDialog
        window = MainWindow(); window.autosave_timer.stop()
        try:
            dialog = CacheManagerDialog(window)
            self.assertTrue(dialog.clear_on_exit.isChecked())
            with patch('kinetic_cut.config.save_settings') as save:
                dialog.clear_on_exit.setChecked(False)
            self.assertFalse(window.settings[CLEAR_PLAYBACK_ON_EXIT]); save.assert_called_once()
            dialog.close()
        finally:
            window.close()


if __name__ == '__main__':
    unittest.main()
