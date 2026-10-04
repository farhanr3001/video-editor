import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QDialog
from kinetic_cut.controls import InspectorSection
from kinetic_cut.properties import ValueRow
from kinetic_cut.render_queue import RenderJobCard
from kinetic_cut.model import Project
from kinetic_cut.window_audit import WindowShowAudit


class StartupWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.audit = WindowShowAudit(self.app)
        self.widgets = []

    def tearDown(self):
        self.app.removeEventFilter(self.audit)
        for widget in reversed(self.widgets):
            widget.close()
            widget.deleteLater()
        self.app.processEvents()

    def test_numeric_rows_never_show_detached_sliders(self):
        host = QWidget(); self.widgets.append(host); layout = QVBoxLayout(host)
        rows = [ValueRow(0, 2, 1, slider=visible) for visible in (True, False)]
        for row in rows:layout.addWidget(row)
        self.assertEqual(self.audit.unexpected, [])
        self.audit.allow(host); host.show(); self.app.processEvents()
        self.assertTrue(rows[0].slider.isVisible())
        self.assertFalse(rows[1].slider.isVisible())
        rows[0].slider.setValue(750)
        self.assertAlmostEqual(rows[0].spin.value(), 1.5)
        self.assertEqual(self.audit.unexpected, [])

    def test_section_construction_and_expansion_keep_content_embedded(self):
        host = QWidget(); self.widgets.append(host); layout = QVBoxLayout(host)
        for expanded in (True, False):
            content = QWidget(); QVBoxLayout(content).addWidget(ValueRow(0, 2, 1))
            section = InspectorSection('Transform', content, expanded)
            layout.addWidget(section)
            self.assertEqual(self.audit.unexpected, [])
            self.audit.allow(host); host.show(); self.app.processEvents()
            self.assertEqual(content.isVisible(), expanded)
            for state in (not expanded, expanded):
                section.toggle.setChecked(state); self.app.processEvents()
                self.assertEqual(content.isVisible(), state)
                self.assertIs(content.window(), host)
            host.hide()
        self.assertEqual(self.audit.unexpected, [])

    def test_queue_refresh_never_flashes_remove_buttons(self):
        host = QWidget(); self.widgets.append(host); layout = QVBoxLayout(host)
        self.audit.allow(host); host.show()
        for state in ('Queued', 'Cancelled', 'Failed', 'Rendering', 'Completed'):
            job = dict(state=state, project=Project(), output='fixture.mp4')
            row = RenderJobCard(job, 1, lambda _:None); layout.addWidget(row)
            self.app.processEvents()
            self.assertEqual(row.remove_button.isVisible(), state in {'Queued', 'Cancelled', 'Failed'})
        self.assertEqual(self.audit.unexpected, [])

    def test_workspace_construction_all_themes_has_no_intermediate_windows(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.theme import get_theme_stylesheet
        from kinetic_cut.config import load_settings
        for theme in ('default', 'final_cut_obsidian', 'ableton_gray'):
            with self.subTest(theme=theme):
                self.app.setStyleSheet(get_theme_stylesheet(theme))
                settings = dict(load_settings(), ui_theme=theme)
                with patch('kinetic_cut.ui.load_settings', return_value=settings):
                    window = MainWindow(startup_progress=lambda *_:self.app.processEvents())
                self.widgets.append(window)
                self.assertEqual(self.audit.unexpected, [])
                self.audit.allow(window); window.show(); self.app.processEvents()
                window.resize(1100, 700); self.app.processEvents()
                self.assertEqual(self.audit.unexpected, [])
                window.close()

    def test_observer_catches_short_lived_windows_and_allows_intentional_dialogs(self):
        accidental = QWidget(); self.widgets.append(accidental)
        accidental.show(); accidental.hide()
        self.assertEqual(len(self.audit.unexpected), 1)
        dialog = QDialog(); self.widgets.append(dialog); self.audit.allow(dialog)
        dialog.show(); self.app.processEvents()
        self.assertTrue(dialog.isVisible())
        self.assertEqual(len(self.audit.unexpected), 1)

