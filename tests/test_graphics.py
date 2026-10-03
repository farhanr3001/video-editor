import copy
import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QEvent, QThreadPool
from PySide6.QtGui import QPainter, QImage, QColor
from PySide6.QtWidgets import QApplication

from kinetic_cut.effects import CATALOG, GRAPHICS
from kinetic_cut.graphics import (
    GRAPHICS_CATALOG,
    default_graphic_data,
    draw_graphic,
    graphic_to_ass_events,
)
from kinetic_cut.model import Project, TimelineItem, uid
from kinetic_cut.exporter import write_ass


class GraphicsUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.app = QApplication.instance() or QApplication([])
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.w = MainWindow()
        self.w.show()
        self.w.autosave_timer.stop()
        self.app.processEvents()

    def tearDown(self):
        self.w.close()
        QThreadPool.globalInstance().waitForDone(10000)
        self.w.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def test_catalog_and_defaults(self):
        """Verify graphics catalog contains all requested items with correct default durations."""
        self.assertIn("Graphics", CATALOG)
        expected_items = [
            "Circle",
            "Pointing Arrow",
            "Square",
            "Rectangle",
            "Timer / Countdown",
            "Speech Bubble / Quote Card",
            "Progress Bar",
            "Callout Badge",
        ]
        for name in expected_items:
            self.assertIn(name, CATALOG["Graphics"])
            self.assertIn(name, GRAPHICS)
            self.assertIn(name, GRAPHICS_CATALOG)
            data = default_graphic_data(name)
            self.assertIsInstance(data, dict)

        # Check Circle defaulted to 2s and Timer defaulted to 10s as requested
        self.assertEqual(GRAPHICS_CATALOG["Circle"]["default_duration"], 2.0)
        self.assertEqual(GRAPHICS_CATALOG["Timer / Countdown"]["default_duration"], 10.0)

    def test_add_graphic_object(self):
        """Verify adding graphics to timeline produces correct TimelineItem."""
        self.w.add_graphic_object("Circle", "video_1", 0.0)
        circle_item = next((i for i in self.w.project.timeline if i.role == "graphic"), None)
        self.assertIsNotNone(circle_item)
        self.assertEqual(circle_item.graphic_type, "Circle")
        self.assertEqual(circle_item.duration, 2.0)
        self.assertEqual(circle_item.track, "video_1")

        # Add Timer
        self.w.add_graphic_object("Timer / Countdown", "video_1", 3.0)
        timer_item = next((i for i in self.w.project.timeline if i.graphic_type == "Timer / Countdown"), None)
        self.assertIsNotNone(timer_item)
        self.assertEqual(timer_item.duration, 10.0)
        self.assertEqual(timer_item.start, 3.0)

    def test_project_save_load_roundtrip(self):
        """Verify graphic item serialization and deserialization."""
        p = Project(name="GraphicsRoundtrip")
        circle_data = default_graphic_data("Circle")
        circle_data["color"] = "#123456"
        circle_data["thickness"] = 15.0
        item = TimelineItem(
            uid(), "", "video_1", 1.0, 2.5,
            role="graphic",
            graphic_type="Circle",
            graphic_data=circle_data,
        )
        p.timeline.append(item)

        save_path = self.root / "test_graphics.kcut"
        p.save(save_path)

        loaded = Project.load(save_path)
        self.assertEqual(len(loaded.timeline), 1)
        loaded_item = loaded.timeline[0]
        self.assertEqual(loaded_item.role, "graphic")
        self.assertEqual(loaded_item.graphic_type, "Circle")
        self.assertEqual(loaded_item.graphic_data.get("color"), "#123456")
        self.assertEqual(loaded_item.graphic_data.get("thickness"), 15.0)

    def test_draw_graphic_all_types(self):
        """Test that draw_graphic renders all 8 graphic types into a QImage without throwing exceptions."""
        img = QImage(1080, 1920, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing)
        frame_rect = QRectF(0, 0, 1080, 1920)

        p = Project()
        p.settings.width = 1080
        p.settings.height = 1920

        for name in GRAPHICS_CATALOG:
            item = TimelineItem(
                uid(), "", "video_1", 0.0, 5.0,
                role="graphic",
                graphic_type=name,
                graphic_data=default_graphic_data(name),
            )
            bounds = draw_graphic(painter, p, item, frame_rect, playhead=1.0)
            self.assertIsNotNone(bounds)
            self.assertGreater(bounds.width(), 0)
            self.assertGreater(bounds.height(), 0)

        painter.end()

    def test_ass_generation_for_export(self):
        """Test ASS subtitle dialogue generation for graphics."""
        p = Project()
        p.settings.width = 1080
        p.settings.height = 1920

        # Timer ASS events
        timer_item = TimelineItem(
            uid(), "", "video_1", 0.0, 5.0,
            role="graphic",
            graphic_type="Timer / Countdown",
            graphic_data=default_graphic_data("Timer / Countdown"),
        )
        p.timeline.append(timer_item)

        # Speech bubble
        speech_item = TimelineItem(
            uid(), "", "video_1", 0.0, 3.0,
            role="graphic",
            graphic_type="Speech Bubble / Quote Card",
            graphic_data=default_graphic_data("Speech Bubble / Quote Card"),
        )
        p.timeline.append(speech_item)

        ass_path = self.root / "test_graphics.ass"
        write_ass(p, ass_path, burn_captions=False)

        content = ass_path.read_text(encoding="utf-8-sig")
        dialogues = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        self.assertGreater(len(dialogues), 0)

    def test_inspector_selection_and_property_edits(self):
        """Verify inspector switches to graphic tab and edits update graphic_data."""
        self.w.add_graphic_object("Circle", "video_1", 0.0)
        item = self.w.project.timeline[-1]
        self.w.select_item(item.id)
        self.app.processEvents()

        # Stack index 3 is graphic inspector
        self.assertEqual(self.w.inspector.video_stack.currentIndex(), 3)
        self.assertTrue(self.w.inspector.sec_circle.isVisible())
        self.assertFalse(self.w.inspector.sec_timer.isVisible())

        # Edit circle thickness via inspector
        self.w.inspector.gc_thick.change(24.0)
        self.assertEqual(item.graphic_data.get("thickness"), 24.0)

        # Edit duration
        self.w.inspector.graphic_duration.change(4.5)
        self.assertEqual(item.duration, 4.5)

        # Now add Timer
        self.w.add_graphic_object("Timer / Countdown", "video_1", 5.0)
        timer_item = self.w.project.timeline[-1]
        self.w.select_item(timer_item.id)
        self.app.processEvents()

        self.assertTrue(self.w.inspector.sec_timer.isVisible())
        self.assertFalse(self.w.inspector.sec_circle.isVisible())

        # Change timer mode to Stopwatch
        self.w.inspector.gt_mode.setCurrentText("Stopwatch")
        self.assertEqual(timer_item.graphic_data.get("mode"), "Stopwatch")

    def test_effects_panel_ordering_and_icons(self):
        """Verify Graphics is at bottom of category list and bottom of All Effects, with distinct icons."""
        from kinetic_cut.effects import EFFECT_ICONS
        # 1. Check CATALOG ordering: Graphics is last key
        catalog_keys = list(CATALOG.keys())
        self.assertEqual(catalog_keys[-1], "Graphics")

        # 2. Check Categories list in EffectsPanel
        effects_panel = self.w.effects_panel
        cats = [effects_panel.categories.item(i).text() for i in range(effects_panel.categories.count())]
        self.assertEqual(cats[0], "All Effects")
        self.assertEqual(cats[-1], "Graphics")
        self.assertEqual(cats[-2], "Audio")

        # 3. Check All Effects list has Graphics items at the bottom
        effects_panel.categories.setCurrentRow(0)
        self.app.processEvents()
        all_items = [effects_panel.list.item(i).text() for i in range(effects_panel.list.count())]
        graphics_names = CATALOG["Graphics"]
        # The last len(graphics_names) items in All Effects must be the graphics items
        self.assertEqual(all_items[-len(graphics_names):], graphics_names)

        # 4. Check each graphic has a dedicated icon defined in EFFECT_ICONS and loaded
        for gname in graphics_names:
            self.assertIn(gname, EFFECT_ICONS)
            icon_name = EFFECT_ICONS[gname]
            from kinetic_cut.icons import lucide_icon
            icon = lucide_icon(icon_name)
            self.assertFalse(icon.isNull(), f"Icon {icon_name} for {gname} could not be loaded")

    def test_timer_countdown_sync_and_glow(self):
        """Verify Timer countdown syncs target duration and Stopwatch disables it, plus font glow."""
        self.w.add_graphic_object("Timer / Countdown", "video_1", 0.0)
        timer_item = self.w.project.timeline[-1]
        self.w.select_item(timer_item.id)
        self.app.processEvents()

        # Default mode is Countdown, duration 10.0s
        self.assertEqual(timer_item.graphic_data.get("mode"), "Countdown")
        self.assertEqual(timer_item.graphic_data.get("duration"), 10.0)
        self.assertTrue(self.w.inspector.gt_dur.isEnabled())

        # Edit duration via inspector
        self.w.inspector.graphic_duration.change(15.0)
        self.assertEqual(timer_item.duration, 15.0)
        self.assertEqual(timer_item.graphic_data.get("duration"), 15.0)
        self.assertEqual(self.w.inspector.gt_dur.spin.value(), 15.0)

        # Switch to Stopwatch
        self.w.inspector.gt_mode.setCurrentText("Stopwatch")
        self.assertEqual(timer_item.graphic_data.get("mode"), "Stopwatch")
        # Target duration should now be disabled (greyed out)
        self.assertFalse(self.w.inspector.gt_dur.isEnabled())

        # Switch back to Countdown
        self.w.inspector.gt_mode.setCurrentText("Countdown")
        self.assertEqual(timer_item.graphic_data.get("mode"), "Countdown")
        self.assertTrue(self.w.inspector.gt_dur.isEnabled())
        self.assertEqual(timer_item.graphic_data.get("duration"), 15.0)

        # Test Font Glow
        self.assertFalse(timer_item.graphic_data.get("glow_enabled", False))
        self.w.inspector.gt_glow_enable.setChecked(True)
        self.app.processEvents()
        self.assertTrue(timer_item.graphic_data.get("glow_enabled"))
        self.assertEqual(timer_item.graphic_data.get("glow_radius"), 12.0)
        self.assertEqual(timer_item.graphic_data.get("glow_opacity"), 55.0)
        self.assertTrue(self.w.inspector.gt_glow_color.isEnabled())

        # Change glow color
        self.w.inspector.edit_graphic_prop("glow_color", "#ff00ff")
        self.assertEqual(timer_item.graphic_data.get("glow_color"), "#ff00ff")

        # Test rendering with glow at playhead 2.0s
        self.w.seek(2.0)
        self.app.processEvents()
        self.assertIn(("graphic", timer_item.id), self.w.preview.text_rects)

        # Test ASS generation includes glow event
        from kinetic_cut.exporter import _ass_color
        ass_events = graphic_to_ass_events(self.w.project, timer_item)
        self.assertTrue(any(r"\blur12" in evt and _ass_color("#ff00ff").upper() in evt.upper() for evt in ass_events))


if __name__ == "__main__":
    unittest.main()

