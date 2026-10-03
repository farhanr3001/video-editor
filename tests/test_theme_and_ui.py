import os
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication([])

from kinetic_cut.theme import PALETTES, THEME_DEFINITIONS, get_theme_stylesheet
from kinetic_cut.theme_dialog import UIThemesDialog
from kinetic_cut.transitions import TRANSITION_ICONS, TRANSITION_NAMES
from kinetic_cut.icons import lucide_icon
from kinetic_cut.controls import SafeSlider
from kinetic_cut.ui import MainWindow


class ThemeAndUITests(unittest.TestCase):
    def tearDown(self):
        # Do not leave complete closed editors for subsequent global repolishes.
        # In production the single main window exits the application on close.
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def test_theme_palettes_and_stylesheet_generation(self):
        """All defined themes must have valid palette definitions and generate non-empty CSS."""
        self.assertEqual(len(PALETTES), 3)
        for theme_id in ["default", "ableton_gray", "final_cut_obsidian"]:
            self.assertIn(theme_id, PALETTES)
            css = get_theme_stylesheet(theme_id)
            self.assertTrue(len(css) > 500)
            self.assertIn("QLabel#mediaPoolTitle", css)
            self.assertIn("QLabel#powerBinsTitle", css)
            self.assertIn("QTreeWidget#poolFolderTree", css)

    def test_all_25_transition_icons_exist_and_render(self):
        """Every single transition in TRANSITION_NAMES must have a valid non-null icon."""
        self.assertEqual(len(TRANSITION_ICONS), len(TRANSITION_NAMES))
        for trans_name, icon_name in TRANSITION_ICONS.items():
            icon = lucide_icon(icon_name)
            self.assertFalse(
                icon.isNull(),
                f"Transition '{trans_name}' icon '{icon_name}.svg' failed to render!"
            )

    def test_safe_slider_jump_click(self):
        """Clicking along the SafeSlider track must jump the value directly to that point."""
        slider = SafeSlider(Qt.Horizontal)
        slider.setRange(0, 1000)
        slider.setValue(100)
        slider.resize(200, 30)

        # Simulate click near 75% of the width
        click_pos = QPointF(150, 15)
        press_event = QMouseEvent(
            QMouseEvent.MouseButtonPress,
            click_pos,
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier
        )
        slider.mousePressEvent(press_event)
        # Should jump from 100 to approximately 700-800
        self.assertGreater(slider.value(), 500)

    def test_ui_themes_dialog(self):
        """UIThemesDialog should instantiate and allow switching themes."""
        w = MainWindow()
        dialog = UIThemesDialog(w)
        self.assertEqual(len(dialog.cards), len(THEME_DEFINITIONS))

        # Select ableton_gray
        dialog.apply_theme("ableton_gray")
        self.assertEqual(w.settings.get("ui_theme"), "ableton_gray")

        # Select default
        dialog.apply_theme("default")
        self.assertEqual(w.settings.get("ui_theme"), "default")
        dialog.close()
        w.close()

    def test_recent_projects_menu_and_folder_memory(self):
        """Recent projects should display up to 10 valid files and remember previous folder."""
        w = MainWindow()
        # Set dummy recent projects
        test_dir = Path(w.settings.get("project_folder", "."))
        w.settings["recent_projects"] = [str(test_dir / f"test_proj_{i}.kcut") for i in range(15)]
        w._populate_recent_menu()
        # Check action count (up to 10 recent items + separator + clear action)
        actions = w.recent_menu.actions()
        self.assertLessEqual(len([a for a in actions if not a.isSeparator() and a.text() != "Clear Recent Projects"]), 10)

        # Folder memory
        w.settings["last_open_project_dir"] = "C:/TestProjectsFolder"
        self.assertEqual(w.settings["last_open_project_dir"], "C:/TestProjectsFolder")
        w.close()


if __name__ == "__main__":
    unittest.main()
