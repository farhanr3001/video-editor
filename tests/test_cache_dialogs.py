import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('KINETIC_CUT_HOME', tempfile.mkdtemp(prefix='kc-cache-dialogs-'))

from PySide6.QtWidgets import QApplication, QGroupBox, QMessageBox


class CacheDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setProperty('kineticTestDiscardUnsaved', True)

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.w = MainWindow(); self.w.autosave_timer.stop()

    def tearDown(self):
        self.w.close(); self.w.deleteLater(); self.app.processEvents()

    def test_sizes_are_measured_in_the_background_with_progress(self):
        from kinetic_cut import cache_manager
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'thumbs').mkdir(); (root / 'thumbs' / 'a.jpg').write_bytes(b'x' * 2048)
            with patch.object(cache_manager, 'CACHE_DIR', root):
                dialog = cache_manager.CacheManagerDialog(self.w)
                # Opening must not block on measuring: the dialog is up with placeholders first.
                self.assertTrue(dialog._scanning)
                self.assertEqual(dialog.total.text(), 'Calculating sizes…')
                self.assertEqual(dialog.rows['thumbs'][1].text(), 'Calculating…')
                self.assertFalse(dialog.rows['thumbs'][0].isEnabled())
                self.assertFalse(dialog.clear_button.isEnabled())
                self.assertTrue(dialog.wait_for_scan())
                self.assertTrue(dialog.rows['thumbs'][1].text().startswith('2.0 KB'))
                self.assertTrue(dialog.rows['thumbs'][0].isEnabled())
                self.assertTrue(dialog.scan_progress.isHidden())
                self.assertEqual(dialog.total.text(), 'Regenerable cache: 2.0 KB')
                self.assertTrue(dialog.clear_button.isEnabled())
                dialog.close()

    def test_closing_during_a_scan_is_safe(self):
        from kinetic_cut.cache_manager import CacheManagerDialog
        dialog = CacheManagerDialog(self.w); dialog.close(); dialog.deleteLater()
        for _ in range(20): self.app.processEvents()

    def test_settings_and_cache_options_are_in_titled_groups(self):
        from kinetic_cut.cache_manager import CacheManagerDialog
        dialog = CacheManagerDialog(self.w)
        titles = [g.title() for g in dialog.findChildren(QGroupBox)]
        self.assertIn('Cache Manager settings', titles); self.assertIn('Clear regenerable cache', titles)
        self.assertIs(dialog.clear_on_exit.parentWidget(), dialog.settings_group)
        self.assertIs(dialog.rows['proxies'][0].parentWidget(), dialog.clear_group)
        layout = dialog.settings_group.layout()
        self.assertIsNone(layout.itemAt(0).widget()); self.assertIsNone(layout.itemAt(2).widget())  # stretches on both sides
        self.assertIs(layout.itemAt(1).widget(), dialog.clear_on_exit)
        dialog.close()


class ComponentsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setProperty('kineticTestDiscardUnsaved', True)

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.w = MainWindow(); self.w.autosave_timer.stop()

    def tearDown(self):
        self.w.close(); self.w.deleteLater(); self.app.processEvents()

    def test_uninstall_buttons_follow_install_state(self):
        from kinetic_cut.component_ui import ComponentsDialog
        with patch('kinetic_cut.feature_packs.installed', side_effect=lambda key: key == 'vocals'):
            dialog = ComponentsDialog(self.w)
            self.assertEqual(set(dialog.rows), {'vision', 'vocals', 'enhance', 'speech'})
            for key, (download, uninstall) in dialog.rows.items():
                self.assertEqual(uninstall.isEnabled(), key == 'vocals')
                self.assertEqual(download.isEnabled(), key != 'vocals')
                self.assertEqual(download.text(), 'Installed' if key == 'vocals' else 'Download')
            dialog.close()

    def test_uninstall_asks_first_and_removes_only_that_tool(self):
        from kinetic_cut.component_ui import ComponentsDialog
        state = {'vocals': True, 'vision': True}
        with patch('kinetic_cut.feature_packs.installed', side_effect=lambda key: state.get(key, False)), \
             patch('kinetic_cut.feature_packs.remove', side_effect=lambda key: state.__setitem__(key, False)) as remove:
            dialog = ComponentsDialog(self.w)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
                dialog.rows['vocals'][1].click()
            remove.assert_not_called()
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                dialog.rows['vocals'][1].click()
            remove.assert_called_once_with('vocals')
            self.assertFalse(dialog.rows['vocals'][1].isEnabled()); self.assertEqual(dialog.rows['vocals'][0].text(), 'Download')
            self.assertTrue(dialog.rows['vision'][1].isEnabled())
            dialog.close()

    def test_removal_failure_is_reported(self):
        from kinetic_cut.component_ui import ComponentsDialog
        with patch('kinetic_cut.feature_packs.installed', return_value=True), \
             patch('kinetic_cut.feature_packs.remove', side_effect=RuntimeError('Power Bin source inside')), \
             patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), \
             patch.object(QMessageBox, 'warning') as warning:
            dialog = ComponentsDialog(self.w); dialog.rows['vision'][1].click()
            self.assertIn('Power Bin', warning.call_args.args[2]); dialog.close()

    def test_dialog_has_no_forced_oversized_height(self):
        from kinetic_cut.component_ui import ComponentsDialog
        dialog = ComponentsDialog(self.w); dialog.show(); self.app.processEvents()
        self.assertLessEqual(dialog.height(), dialog.sizeHint().height() + 40)
        dialog.close()

    def test_speech_model_row_has_info_and_uses_own_copy_state(self):
        from kinetic_cut.component_ui import ComponentsDialog, SPEECH_INFO
        with patch('kinetic_cut.feature_packs.installed', side_effect=lambda key: key == 'speech'):
            dialog = ComponentsDialog(self.w)
            download, uninstall = dialog.rows['speech']
            self.assertEqual(download.text(), 'Installed'); self.assertTrue(uninstall.isEnabled())
            info = dialog.info_buttons['speech']
            self.assertIn('Speech model', info.toolTip()); self.assertIn('large-v3-turbo', info.toolTip())
            with patch.object(QMessageBox, 'information') as shown:
                info.click()
            self.assertEqual(shown.call_args.args[2], SPEECH_INFO)
            self.assertEqual(set(dialog.info_buttons), {'speech'})
            dialog.close()

    def test_speech_uninstall_warns_when_it_is_the_selected_model(self):
        from kinetic_cut.component_ui import ComponentsDialog
        self.w.settings['whisper_model'] = 'large-v3-turbo'
        with patch('kinetic_cut.feature_packs.installed', side_effect=lambda key: key == 'speech'), \
             patch('kinetic_cut.feature_packs.remove') as remove:
            dialog = ComponentsDialog(self.w)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as ask:
                dialog.rows['speech'][1].click()
            self.assertIn('base.en', ask.call_args.args[2]); remove.assert_called_once_with('speech')
            dialog.close()

    def test_sizes_use_gb_and_installed_rows_show_measured_size(self):
        from kinetic_cut.component_ui import ComponentsDialog
        from kinetic_cut.feature_packs import size_label
        self.assertEqual([size_label(v) for v in (354_000_000, 1_167_000_000, 1_621_670_079)], ['338 MB', '1.1 GB', '1.5 GB'])
        with patch('kinetic_cut.feature_packs.installed', side_effect=lambda key: key == 'vocals'), \
             patch('kinetic_cut.cache_manager.tree_size', return_value=1_167_000_000):
            dialog = ComponentsDialog(self.w)
            for _ in range(100):
                self.app.processEvents()
                if 'on disk' in dialog.states['vocals'].text():break
                __import__('time').sleep(.02)
            self.assertIn('1.1 GB on disk', dialog.states['vocals'].text())
            self.assertEqual(dialog.states['speech'].text(), 'About 1.5 GB')
            self.assertIn('1 of 4 installed', dialog.total.text())
            dialog.close()


if __name__ == '__main__':
    unittest.main()
