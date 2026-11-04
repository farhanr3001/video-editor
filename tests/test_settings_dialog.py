import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('KINETIC_CUT_HOME', tempfile.mkdtemp(prefix='kc-settings-'))

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from kinetic_cut.config import DEFAULT_SHORTCUTS


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setProperty('kineticTestDiscardUnsaved', True)

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.w = MainWindow(); self.w.autosave_timer.stop(); self.w.settings['shortcuts'] = dict(DEFAULT_SHORTCUTS)

    def tearDown(self):
        self.w.close(); self.w.deleteLater(); self.app.processEvents()

    def dialog(self):
        from kinetic_cut.settings_dialog import SettingsDialog
        d = SettingsDialog(self.w); d.show(); self.app.processEvents(); return d

    def test_shortcuts_tab_is_first_and_advanced_options_have_their_own_tab(self):
        d = self.dialog()
        self.assertEqual([d.tabs.tabText(i) for i in range(d.tabs.count())], ['Keyboard shortcuts', 'Advanced'])
        self.assertEqual(d.tabs.currentIndex(), 0)
        advanced = d.tabs.widget(1)
        for widget in (d.ffmpeg, d.ffprobe, d.whisper_size, d.whisper, d.model, d.sfx, d.decoder):
            self.assertIs(widget.window(), d); self.assertTrue(advanced.isAncestorOf(widget))
        self.assertFalse(d.tabs.widget(0).isAncestorOf(d.ffmpeg))
        d.close()

    def test_every_default_shortcut_is_listed(self):
        d = self.dialog()
        self.assertEqual(set(d.keys), set(DEFAULT_SHORTCUTS))
        d.close()

    def test_click_then_press_keys_records_the_shortcut(self):
        d = self.dialog(); button = d.keys['mark_in']
        QTest.mouseClick(button, Qt.LeftButton); self.assertTrue(button.recording); self.assertEqual(button.text(), 'Press keys…')
        QTest.keyClick(button, Qt.Key_K, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertEqual(button.value, 'Ctrl+Shift+K'); self.assertFalse(button.recording)
        d.close()

    def test_escape_cancels_and_backspace_clears(self):
        d = self.dialog(); button = d.keys['mark_in']; before = button.value
        button.begin(); QTest.keyClick(button, Qt.Key_Escape)
        self.assertEqual(button.value, before); self.assertFalse(button.recording)
        button.begin(); QTest.keyClick(button, Qt.Key_Backspace)
        self.assertEqual(button.value, ''); self.assertEqual(button.text(), 'Not set')
        d.close()

    def test_modifier_alone_keeps_waiting(self):
        d = self.dialog(); button = d.keys['mark_in']; button.begin()
        QTest.keyClick(button, Qt.Key_Control)
        self.assertTrue(button.recording)
        d.close()

    def test_duplicate_shortcut_is_flagged_and_reset_restores_default(self):
        d = self.dialog()
        d.keys['mark_out'].set_value('I')
        self.assertTrue(d.keys['mark_in'].conflict and d.keys['mark_out'].conflict)
        self.assertIn('Mark in', d.status.text()); self.assertIn('Mark out', d.status.text())
        self.assertTrue(d.rows['mark_out'][2].isEnabled()); self.assertFalse(d.rows['mark_in'][2].isEnabled())
        d.rows['mark_out'][2].click()
        self.assertEqual(d.keys['mark_out'].value, 'O'); self.assertEqual(d.status.text(), '')
        d.close()

    def test_search_filters_rows_and_reset_all(self):
        d = self.dialog()
        d.search.setText('ripple'); self.assertTrue(d.rows['ripple_delete'][0].isVisibleTo(d)); self.assertFalse(d.rows['undo'][0].isVisibleTo(d))
        d.search.setText(''); self.assertTrue(d.rows['undo'][0].isVisibleTo(d))
        d.keys['undo'].set_value('Ctrl+Y'); d.reset_all(); self.assertEqual(d.keys['undo'].value, 'Ctrl+Z')
        d.close()

    def test_saving_applies_values_and_conflicting_save_asks_first(self):
        from kinetic_cut.ui import MainWindow
        d = self.dialog(); d.keys['mark_in'].set_value('Ctrl+Shift+K'); d.ffmpeg.setText('custom-ffmpeg'); d.decoder.setCurrentIndex(0)
        d.apply()
        self.assertEqual(self.w.settings['shortcuts']['mark_in'], 'Ctrl+Shift+K'); self.assertEqual(self.w.settings['ffmpeg'], 'custom-ffmpeg')
        d.keys['mark_out'].set_value('Ctrl+Shift+K')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No) as ask:
            d.accept(); ask.assert_called_once(); self.assertNotEqual(d.result(), QDialog.Accepted)
        d.close()

    def test_open_settings_saves_and_rebinds_live(self):
        from kinetic_cut.settings_dialog import SettingsDialog
        def run(self_dialog):
            self_dialog.keys['mark_in'].set_value('Ctrl+Shift+K'); return SettingsDialog.Accepted
        with patch.object(SettingsDialog, 'exec', run), patch('kinetic_cut.ui.save_settings') as save:
            self.w.open_settings()
        save.assert_called_once()
        self.assertEqual(self.w.shortcut_actions['mark_in'].shortcut().toString(), 'Ctrl+Shift+K')


if __name__ == '__main__':
    unittest.main()
