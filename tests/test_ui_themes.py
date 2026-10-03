import unittest
from types import SimpleNamespace
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton, QButtonGroup, QWidget

from kinetic_cut.theme import PALETTES, THEME_DEFINITIONS, get_theme_stylesheet, get_active_theme_palette
from kinetic_cut.workspace import refresh_workspace_theme, update_nav_icons
from kinetic_cut.widgets import PreviewCanvas
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.theme_dialog import UIThemesDialog

_app = QApplication.instance() or QApplication([])


class DummyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = {}
        self.applied = []

    def apply_theme(self, tid, save=True):
        self.applied.append(tid)


class UIThemesTests(unittest.TestCase):
    def test_palettes_structure(self):
        self.assertEqual([p['id'] for p in THEME_DEFINITIONS], ['default', 'final_cut_obsidian', 'ableton_gray'])
        required_keys = {
            "bg_main", "bg_topbar", "bg_panel", "border",
            "accent", "accent_hover", "text_main", "text_sub",
            "timeline_bg", "timeline_track_bg", "timeline_ruler_bg", "viewer_bg", "icon_color",
            "nav_edit_color", "nav_deliver_color", "nav_phone_color", "nav_inactive_color"
        }
        for theme_id, info in PALETTES.items():
            self.assertTrue(required_keys.issubset(info.keys()), f"Missing keys in theme {theme_id}")

    def test_ableton_gray_palette(self):
        p = PALETTES["ableton_gray"]
        self.assertEqual(p["accent"], "#ff764d")
        self.assertEqual(p["nav_edit_color"], "#ff764d")
        self.assertEqual(p["nav_deliver_color"], "#ff764d")
        self.assertEqual(p["nav_phone_color"], "#ff764d")
        self.assertEqual(p["nav_inactive_color"], "#1c1c1c")

    def test_stylesheet_generation(self):
        for theme in THEME_DEFINITIONS:
            css = get_theme_stylesheet(theme["id"])
            palette = PALETTES[theme["id"]]
            self.assertIn(palette["accent"], css)
            self.assertIn("QMainWindow", css)
            self.assertIn("QScrollBar", css)

    def test_preview_canvas_theme(self):
        canvas = PreviewCanvas()
        palette = get_active_theme_palette("ableton_gray")
        canvas.set_theme(palette)
        self.assertEqual(canvas._viewer_bg, palette["viewer_bg"])
        self.assertEqual(canvas._border_col, palette["border"])

    def test_timeline_theme(self):
        timeline = TimelineWidget()
        palette = get_active_theme_palette("ableton_gray")
        timeline.set_theme(palette)
        self.assertEqual(timeline._palette(), palette)

    def test_nav_icons_update(self):
        b0 = QToolButton(); b0.setProperty("navIcon", "sliders-horizontal")
        b1 = QToolButton(); b1.setProperty("navIcon", "download")
        b2 = QToolButton(); b2.setProperty("navIcon", "smartphone")
        group = QButtonGroup()
        group.addButton(b0, 0)
        group.addButton(b1, 1)
        group.addButton(b2, 2)
        w = SimpleNamespace(page_group=group, settings={}, findChildren=lambda types: [b0, b1, b2])

        palette = get_active_theme_palette("ableton_gray")
        refresh_workspace_theme(w, palette)
        self.assertFalse(b0.icon().isNull())
        self.assertFalse(b1.icon().isNull())
        self.assertFalse(b2.icon().isNull())

    def test_theme_dialog_apply(self):
        win = DummyWindow()
        dialog = UIThemesDialog(win)
        dialog.apply_theme("ableton_gray")
        self.assertIn("ableton_gray", win.applied)
        self.assertEqual(dialog.current_theme, "ableton_gray")


if __name__ == "__main__":
    unittest.main()
