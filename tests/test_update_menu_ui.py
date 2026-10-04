import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from kinetic_cut.update_ui import UpdateDialog
from kinetic_cut.updates import Release
from kinetic_cut.theme_widgets import apply_application_theme
from kinetic_cut.version import VERSION


class UpdateMenuUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_current_and_available_layouts_fit_both_sizes_in_all_themes(self):
        release = Release('9.9.9', '', 'a'*64, 21_113_218, 'Release notes\n'*40, incremental=True)
        for theme in ('default', 'final_cut_obsidian', 'ableton_gray'):
            apply_application_theme(theme)
            for width in (400, 510):
                for options in (dict(state='current', message=f'Installed version: {VERSION}'), dict(release=release, startup=True)):
                    dialog = UpdateDialog(None, **options)
                    try:
                        dialog.resize(width, dialog.height()); dialog.show(); self.app.processEvents()
                        self.assertEqual(dialog.width(), width)
                        for button in dialog.findChildren(QPushButton):
                            self.assertTrue(button.isVisible()); self.assertTrue(dialog.rect().contains(button.geometry()))
                        if 'release' in options:
                            self.assertLessEqual(dialog.notes.height(), 140)
                            self.assertLess(dialog.detail.geometry().bottom(), dialog.notes.geometry().top())
                        else:
                            self.assertLessEqual(dialog.height(), 150)
                            self.assertLessEqual(dialog.detail.y()-dialog.heading.geometry().bottom(), 14)
                    finally:dialog.close(); dialog.deleteLater(); self.app.processEvents()

    def test_download_cancel_and_version_dismissal_keep_their_choices(self):
        release = Release('9.9.9', '', 'a'*64, 100)
        for label, expected in (('OK', 'download'), ("Don't show again", 'ignore'), ('Cancel', 'cancel')):
            dialog = UpdateDialog(None, release, startup=True)
            button = next(b for b in dialog.findChildren(QPushButton) if b.text() == label)
            button.click(); self.assertEqual(dialog.choice, expected)
            dialog.close(); dialog.deleteLater(); self.app.processEvents()
        dialog = UpdateDialog(None, release)
        self.assertNotIn("Don't show again", [b.text() for b in dialog.findChildren(QPushButton)])
        dialog.close(); dialog.deleteLater(); self.app.processEvents()

    def test_workflow_only_settings_and_removed_duplicates_preserve_shortcuts(self):
        from kinetic_cut.ui import MainWindow
        with patch.object(MainWindow, 'generate_captions') as captions:
            window = MainWindow(); window.show(); self.app.processEvents()
            try:
                menus = {a.text():a.menu() for a in window.menuBar().actions()}
                self.assertEqual(set(menus), {'File', 'Edit', 'Workflow'})
                self.assertEqual([a.text() for a in menus['Workflow'].actions()], ['Settings…'])
                names = [a.text() for a in menus['File'].actions()]
                self.assertNotIn('Collect project and media…', names)
                self.assertEqual(names.count('UI Themes…'), 1)
                self.assertEqual(window.shortcut_actions['captions'].shortcut().toString(), 'G')
                QTest.keyClick(window, Qt.Key_G); self.app.processEvents()
                captions.assert_called_once()
            finally:window.close(); window.deleteLater(); self.app.processEvents()
