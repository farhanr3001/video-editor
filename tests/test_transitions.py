"""Comprehensive tests for the Video Transitions system."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication

from kinetic_cut.transitions import (
    Transition,
    TRANSITION_NAMES,
    TRANSITION_SUBSECTIONS,
    TRANSITION_SET,
    TRANSITION_ICONS,
    TRANSITION_DESCRIPTIONS,
    XFADE_MAP,
    xfade_name,
    apply_easing,
    default_transition_properties,
    composite_transition,
)
from kinetic_cut.model import Project, TimelineItem, MediaItem, Crop, Transform
from kinetic_cut.effects import CATALOG, CATEGORY_STYLE
from kinetic_cut.exporter import ExportPreset
from kinetic_cut.rendergraph import command

_APP = None

def get_app():
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


class TestTransitionsCatalog(unittest.TestCase):
    def test_catalog_subsections_and_names(self):
        self.assertIn("Dissolve", TRANSITION_SUBSECTIONS)
        self.assertIn("Wipe & Split", TRANSITION_SUBSECTIONS)
        self.assertIn("Motion & Push", TRANSITION_SUBSECTIONS)
        self.assertIn("Glitch & Stylized", TRANSITION_SUBSECTIONS)

        # 25 popular transitions defined
        self.assertEqual(len(TRANSITION_NAMES), 25)
        for name in TRANSITION_NAMES:
            self.assertIn(name, TRANSITION_SET)
            self.assertIn(name, TRANSITION_ICONS)
            self.assertIn(name, TRANSITION_DESCRIPTIONS)
            self.assertIn(name, XFADE_MAP)
            self.assertTrue(bool(xfade_name(name)))

    def test_effects_catalog_registration(self):
        self.assertIn("Video Transitions", CATALOG)
        self.assertEqual(CATALOG["Video Transitions"], TRANSITION_NAMES)
        icon, color = CATEGORY_STYLE["Video Transitions"]
        self.assertEqual(color, "#5ec2f8")


class TestTransitionDataModel(unittest.TestCase):
    def test_transition_initialization_and_clamping(self):
        t = Transition(id="t1", name="Cross Dissolve", duration=0.8)
        self.assertEqual(t.id, "t1")
        self.assertEqual(t.name, "Cross Dissolve")
        self.assertEqual(t.category, "Dissolve")
        self.assertAlmostEqual(t.duration, 0.8)

        # Clamping min (0.05s) and max (10.0s)
        t_short = Transition(id="t2", name="Wipe Left", duration=0.01)
        self.assertAlmostEqual(t_short.duration, 0.05)

        t_long = Transition(id="t3", name="Wipe Left", duration=15.0)
        self.assertAlmostEqual(t_long.duration, 10.0)

    def test_timing_and_progress(self):
        t = Transition(id="t1", name="Cross Dissolve", start=2.0, duration=1.0)
        self.assertFalse(t.contains_time(1.99))
        self.assertTrue(t.contains_time(2.0))
        self.assertTrue(t.contains_time(2.5))
        self.assertFalse(t.contains_time(3.0))

        self.assertAlmostEqual(t.progress(2.0), 0.0)
        self.assertAlmostEqual(t.progress(2.5), 0.5)
        self.assertAlmostEqual(t.progress(3.0), 1.0)
        self.assertAlmostEqual(t.progress(4.0), 1.0)
        self.assertAlmostEqual(t.progress(1.0), 0.0)

    def test_easing_curves(self):
        for curve in ("Linear", "Ease In", "Ease Out", "Ease In-Out", "Smooth S-Curve"):
            self.assertAlmostEqual(apply_easing(0.0, curve), 0.0)
            self.assertAlmostEqual(apply_easing(1.0, curve), 1.0)
            mid = apply_easing(0.5, curve)
            self.assertTrue(0.0 <= mid <= 1.0)

    def test_project_serialization(self):
        p = Project()
        m1 = MediaItem(id="m1", path="test1.mp4", kind="video", name="Test 1", duration=5.0)
        p.add_media(m1)
        i1 = TimelineItem(id="clip1", media_id="m1", track="video_1", start=0.0, duration=3.0)
        i2 = TimelineItem(id="clip2", media_id="m1", track="video_1", start=3.0, duration=3.0)
        p.timeline.extend([i1, i2])

        t = Transition(
            id="trans1",
            name="Dip to Color / White Flash",
            track="video_1",
            start=2.6,
            duration=0.8,
            left_item_id="clip1",
            right_item_id="clip2",
            alignment="center",
            properties={"color": "#ffffff", "intensity": 1.2},
        )
        p.add_transition(t)

        self.assertEqual(len(p.transitions), 1)
        self.assertEqual(p.transition_by_id("trans1"), t)
        self.assertEqual(p.transitions_for_track("video_1"), [t])
        self.assertEqual(p.transitions_for_item("clip1"), [t])
        self.assertEqual(p.transitions_for_item("clip2"), [t])
        self.assertEqual(p.transition_at_time("video_1", 2.8), t)
        self.assertIsNone(p.transition_at_time("video_1", 3.5))

        # Serialization round-trip
        data = p.to_dict()
        p_loaded = Project.from_dict(data)
        self.assertEqual(len(p_loaded.transitions), 1)
        t_loaded = p_loaded.transitions[0]
        self.assertEqual(t_loaded.id, "trans1")
        self.assertEqual(t_loaded.name, "Dip to Color / White Flash")
        self.assertAlmostEqual(t_loaded.start, 2.6)
        self.assertAlmostEqual(t_loaded.duration, 0.8)
        self.assertEqual(t_loaded.properties.get("color"), "#ffffff")

        # Deletion
        self.assertTrue(p.remove_transition("trans1"))
        self.assertEqual(len(p.transitions), 0)
        self.assertFalse(p.remove_transition("trans1"))


class TestTimelineInteraction(unittest.TestCase):
    def setUp(self):
        get_app()

    def test_timeline_clamper_and_hit_testing(self):
        from kinetic_cut.timeline import TimelineWidget
        tl = TimelineWidget()
        p = Project()
        m = MediaItem(id="m1", path="test.mp4", kind="video", name="Test", duration=10.0)
        p.add_media(m)
        c1 = TimelineItem(id="c1", media_id="m1", track="video_1", start=0.0, duration=4.0)
        c2 = TimelineItem(id="c2", media_id="m1", track="video_1", start=4.0, duration=4.0)
        p.timeline.extend([c1, c2])

        t = Transition(id="t1", name="Blur Dissolve", track="video_1", start=3.5, duration=1.0, left_item_id="c1", right_item_id="c2")
        p.add_transition(t)
        tl.set_project(p)

        # Clamper rect calculation
        r = tl.transition_rect(t)
        self.assertTrue(r.width() > 0)
        self.assertTrue(r.height() > 0)

        # Hit testing body and handles
        hit_body, part_body = tl.transition_at(r.center())
        self.assertIsNotNone(hit_body)
        self.assertEqual(hit_body.id, "t1")
        self.assertEqual(part_body, "body")

        left_handle_pt = QPointF(r.left() + 3, r.center().y())
        hit_left, part_left = tl.transition_at(left_handle_pt)
        self.assertEqual(part_left, "left_handle")

        right_handle_pt = QPointF(r.right() - 3, r.center().y())
        hit_right, part_right = tl.transition_at(right_handle_pt)
        self.assertEqual(part_right, "right_handle")

    def test_drag_drop_cut_target_snapping(self):
        from kinetic_cut.timeline import TimelineWidget
        tl = TimelineWidget()
        p = Project()
        m = MediaItem(id="m1", path="test.mp4", kind="video", name="Test", duration=10.0)
        p.add_media(m)
        c1 = TimelineItem(id="c1", media_id="m1", track="video_1", start=0.0, duration=4.0)
        c2 = TimelineItem(id="c2", media_id="m1", track="video_1", start=4.0, duration=4.0)
        p.timeline.extend([c1, c2])
        tl.set_project(p)

        # Proximity to cut at 4.0s
        x_cut = tl.x_for_time(4.0)
        y_track = tl.track_rect("video_1").center().y()
        target = tl.transition_target("Cross Dissolve", QPointF(x_cut, y_track))
        self.assertIsNotNone(target)
        kind, name, track, cut_t, left, right = target
        self.assertEqual(kind, "transition_cut")
        self.assertEqual(name, "Cross Dissolve")
        self.assertEqual(track, "video_1")
        self.assertAlmostEqual(cut_t, 4.0)
        self.assertEqual(left.id, "c1")
        self.assertEqual(right.id, "c2")

        # Proximity to start boundary at 0.0s (single clip start)
        x_start = tl.x_for_time(0.0)
        target_start = tl.transition_target("Cross Dissolve", QPointF(x_start, y_track))
        self.assertIsNotNone(target_start)
        self.assertEqual(target_start[0], "transition_start")


class TestCompositingEngine(unittest.TestCase):
    def setUp(self):
        get_app()

    def test_all_24_transitions_composite_without_error(self):
        dest_rect = QRectF(0, 0, 1080, 1920)
        img_a = QImage(1080, 1920, QImage.Format_ARGB32_Premultiplied)
        img_a.fill(QColor(255, 0, 0))

        img_b = QImage(1080, 1920, QImage.Format_ARGB32_Premultiplied)
        img_b.fill(QColor(0, 0, 255))

        out = QImage(1080, 1920, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(out)

        for name in TRANSITION_NAMES:
            trans = Transition(id="test", name=name, duration=1.0)
            for progress in (0.0, 0.25, 0.5, 0.75, 1.0):
                composite_transition(painter, dest_rect, img_a, img_b, trans, progress)

        painter.end()


class TestExportFiltergraphSynthesis(unittest.TestCase):
    def test_export_command_synthesizes_transitions(self):
        p = Project()
        p.settings.width = 1080
        p.settings.height = 1920
        p.settings.fps = 60
        m1 = MediaItem(id="m1", path="clip1.mp4", kind="video", name="Clip 1", duration=5.0)
        m2 = MediaItem(id="m2", path="clip2.mp4", kind="video", name="Clip 2", duration=5.0)
        p.add_media(m1)
        p.add_media(m2)
        c1 = TimelineItem(id="c1", media_id="m1", track="video_1", start=0.0, duration=3.0)
        c2 = TimelineItem(id="c2", media_id="m2", track="video_1", start=3.0, duration=3.0)
        p.timeline.extend([c1, c2])

        trans = Transition(
            id="t1",
            name="Dip to Color / White Flash",
            track="video_1",
            start=2.5,
            duration=1.0,
            left_item_id="c1",
            right_item_id="c2",
        )
        p.add_transition(trans)

        preset = ExportPreset("Custom Export", "h264", 10.0, 192, "Custom")
        args = command(p, "output.mp4", preset, burn_captions=False, export_audio=False)

        # Confirm filter complex has been synthesized with fade transitions
        fc_idx = args.index("-filter_complex")
        filter_complex = args[fc_idx + 1]
        self.assertIn("fade=", filter_complex)


class MockWindow:
    def __init__(self, project):
        self.project = project
        self.settings = {}
        self.timeline = SimpleNamespace(selected_ids=set(), selected_caption_ids=set(),
                                        selected_transition_id='',
                                        viewport=lambda: SimpleNamespace(update=lambda: None))
        self._property_scrubbing = False

    def flush_text_edit(self):
        pass

    def commit_history(self):
        pass

    def text_edited(self):
        pass


class TestInspectorProperties(unittest.TestCase):
    def setUp(self):
        get_app()

    def test_inspector_transition_selection_and_editing(self):
        from kinetic_cut.properties import PropertiesPanel
        p = Project()
        m1 = MediaItem(id="m1", path="clip1.mp4", kind="video", name="Clip 1", duration=10.0)
        p.add_media(m1)
        c1 = TimelineItem(id="c1", media_id="m1", track="video_1", start=0.0, duration=4.0)
        c2 = TimelineItem(id="c2", media_id="m1", track="video_1", start=4.0, duration=4.0)
        p.timeline.extend([c1, c2])

        t = Transition(id="t_insp", name="Blur Dissolve", track="video_1", start=3.6, duration=0.8, left_item_id="c1", right_item_id="c2")
        p.add_transition(t)

        win = MockWindow(p)
        insp = PropertiesPanel(win)

        # Select transition
        insp.select_transition("t_insp")
        self.assertEqual(insp.transition_id, "t_insp")
        self.assertEqual(insp.video_stack.currentIndex(), 4)
        self.assertIn("Blur Dissolve", insp.filename.text())
        self.assertAlmostEqual(insp.trans_duration.spin.value(), 0.8)

        # Edit duration
        insp._on_trans_duration_edited(1.2, 0.4)
        self.assertAlmostEqual(t.duration, 1.2)

        # Edit alignment
        insp._on_trans_alignment_changed("Start on Cut")
        self.assertEqual(t.alignment, "start")

        # Edit custom property
        insp.edit_trans_prop("blur_radius", 45)
        self.assertEqual(t.properties.get("blur_radius"), 45)

        # Reset properties
        insp.reset_trans_properties()
        self.assertEqual(t.properties.get("blur_radius"), 24)

        # Delete transition
        insp.delete_current_transition()
        self.assertEqual(insp.transition_id, "")
        self.assertIsNone(p.transition_by_id("t_insp"))


class TestLayerBasedTransitionCompositing(unittest.TestCase):
    def setUp(self):
        get_app()

    def test_layer_transition_preserves_underlying_layers_and_properties(self):
        from kinetic_cut.widgets import PreviewCanvas
        p = Project()
        p.settings.width = 1080
        p.settings.height = 1920
        p.video_tracks = ["video_1", "video_2", "video_3"]
        m1 = MediaItem(id="m1", path="bg.mp4", kind="video", name="BG", duration=10.0)
        m2 = MediaItem(id="m2", path="cam.mp4", kind="video", name="Cam", duration=10.0)
        p.add_media(m1)
        p.add_media(m2)

        # Track 1: full-screen background
        bg = TimelineItem(id="bg", media_id="m1", track="video_1", start=0.0, duration=10.0)

        # Track 3: cropped webcam overlay in top area (pos y=0.2, crop width=0.25, height=0.25)
        cam1 = TimelineItem(
            id="cam1", media_id="m2", track="video_3", start=0.0, duration=3.0,
            crop=Crop(x=0.0, y=0.2, width=0.25, height=0.25),
            transform=Transform(x=0.5, y=0.2, scale=1.5),
            is_webcam=True,
        )
        cam2 = TimelineItem(
            id="cam2", media_id="m2", track="video_3", start=3.0, duration=3.0,
            crop=Crop(x=0.0, y=0.2, width=0.25, height=0.25),
            transform=Transform(x=0.5, y=0.2, scale=1.5),
            is_webcam=True,
        )
        p.timeline.extend([bg, cam1, cam2])

        canvas = PreviewCanvas()
        canvas.resize(540, 960)
        canvas.set_project(p)
        p.playhead = 3.0

        bg_img = QImage(1920, 1080, QImage.Format_ARGB32_Premultiplied); bg_img.fill(QColor(20, 40, 90))
        cam1_img = QImage(1920, 1080, QImage.Format_ARGB32_Premultiplied); cam1_img.fill(QColor(0, 200, 255))
        cam2_img = QImage(1920, 1080, QImage.Format_ARGB32_Premultiplied); cam2_img.fill(QColor(255, 150, 0))

        canvas.fallback_frames = {"bg": bg_img, "cam1": cam1_img, "cam2": cam2_img}

        # Render base (at 3.0s without transition, cam2 is active)
        img_base = QImage(540, 960, QImage.Format_ARGB32_Premultiplied)
        img_base.fill(Qt.black)
        canvas.render(img_base)

        # Add transition to track 3 (Push Left)
        t = Transition(id="t_cam", name="Push Left (Swipe)", track="video_3", start=2.5, duration=1.0, left_item_id="cam1", right_item_id="cam2")
        p.add_transition(t)

        img_trans = QImage(540, 960, QImage.Format_ARGB32_Premultiplied)
        img_trans.fill(Qt.black)
        canvas.render(img_trans)

        # Pixel check: Bottom half (y > 480) MUST be 100% identical between base and transition
        bottom_rect = QRectF(0, 480, 540, 480).toRect()
        base_bottom = img_base.copy(bottom_rect)
        trans_bottom = img_trans.copy(bottom_rect)
        self.assertEqual(base_bottom, trans_bottom, "Underlying layer video_1 was modified by transition on video_3!")

        # Top area (where webcam lives) MUST be transitioned
        top_rect = QRectF(0, 50, 540, 300).toRect()
        base_top = img_base.copy(top_rect)
        trans_top = img_trans.copy(top_rect)
        self.assertNotEqual(base_top, trans_top, "Webcam transition did not take effect!")

    def test_transition_clamper_click_and_release_preserves_inspector(self):
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF
        from kinetic_cut.ui import MainWindow

        win = MainWindow()
        p = Project()
        p.video_tracks = ["video_1"]
        m = MediaItem(id="m1", name="test.mp4", path="test.mp4", duration=10.0, kind="video", width=1920, height=1080)
        p.add_media(m)
        i1 = TimelineItem(id="i1", media_id="m1", track="video_1", start=0.0, duration=5.0)
        i2 = TimelineItem(id="i2", media_id="m1", track="video_1", start=5.0, duration=5.0)
        p.timeline = [i1, i2]
        t = Transition(id="t1", name="Cross Dissolve", track="video_1", start=4.5, duration=1.0, left_item_id="i1", right_item_id="i2")
        p.transitions = [t]
        win.set_project(p)

        tl = win.timeline
        rx = tl.x_for_time(5.0)
        ry = tl.track_rect("video_1").center().y()
        click_pos = QPointF(rx, ry)

        # 1. Mouse press on transition clamper
        press_ev = QMouseEvent(QMouseEvent.MouseButtonPress, click_pos, click_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        tl.mousePressEvent(press_ev)
        self.assertEqual(tl.selected_transition_id, "t1")
        self.assertEqual(win.inspector.transition_id, "t1")
        self.assertIn("Cross Dissolve", win.inspector.filename.text())

        # 2. Mouse release on transition clamper (must NOT clear inspector)
        rel_ev = QMouseEvent(QMouseEvent.MouseButtonRelease, click_pos, click_pos, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        tl.mouseReleaseEvent(rel_ev)
        self.assertEqual(tl.selected_transition_id, "t1")
        self.assertEqual(win.inspector.transition_id, "t1")
        self.assertIn("Cross Dissolve", win.inspector.filename.text())

        # 3. Trigger model_changed (e.g. from properties or timeline edit) - must preserve inspector
        win.model_changed()
        self.assertEqual(tl.selected_transition_id, "t1")
        self.assertEqual(win.inspector.transition_id, "t1")
        self.assertIn("Cross Dissolve", win.inspector.filename.text())

    def test_transition_handle_symmetrical_resize(self):
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF
        from kinetic_cut.ui import MainWindow

        win = MainWindow()
        p = Project()
        p.video_tracks = ["video_1"]
        m = MediaItem(id="m1", name="test.mp4", path="test.mp4", duration=20.0, kind="video", width=1920, height=1080)
        p.add_media(m)
        i1 = TimelineItem(id="i1", media_id="m1", track="video_1", start=0.0, duration=5.0)
        i2 = TimelineItem(id="i2", media_id="m1", track="video_1", start=5.0, duration=5.0)
        p.timeline = [i1, i2]
        t = Transition(id="t1", name="Cross Dissolve", track="video_1", start=4.5, duration=1.0, left_item_id="i1", right_item_id="i2", alignment="center")
        p.transitions = [t]
        win.set_project(p)

        tl = win.timeline
        ry = tl.track_rect("video_1").center().y()
        cut_point = 5.0
        pps = tl.pixels_per_second

        # 1. Drag right handle outward -> both sides lengthen together around cut
        orig_right_x = tl.x_for_time(5.5)
        tl.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(orig_right_x, ry), QPointF(orig_right_x, ry), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        self.assertEqual(tl.drag_mode, "trans_resize_right")
        drag_right_pos = QPointF(orig_right_x + 20, ry)
        tl.mouseMoveEvent(QMouseEvent(QMouseEvent.MouseMove, drag_right_pos, drag_right_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))

        delta = (drag_right_pos.x() - tl.drag_start.x()) / pps
        expected_half = 0.5 + delta
        self.assertAlmostEqual(t.duration, 2.0 * expected_half, places=3)
        self.assertAlmostEqual(t.start, cut_point - expected_half, places=3)
        self.assertAlmostEqual(t.start + t.duration / 2.0, cut_point, places=3)
        tl.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease, drag_right_pos, drag_right_pos, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

        # 2. Drag left handle inward -> both sides smallen together around cut
        orig_left_x = tl.x_for_time(t.start)
        tl.mousePressEvent(QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(orig_left_x, ry), QPointF(orig_left_x, ry), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        self.assertEqual(tl.drag_mode, "trans_resize_left")
        drag_left_pos = QPointF(orig_left_x + 15, ry)
        prev_dur = t.duration
        tl.mouseMoveEvent(QMouseEvent(QMouseEvent.MouseMove, drag_left_pos, drag_left_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))

        delta_left = -(drag_left_pos.x() - tl.drag_start.x()) / pps
        expected_half_left = (prev_dur / 2.0) + delta_left
        self.assertAlmostEqual(t.duration, 2.0 * expected_half_left, places=3)
        self.assertAlmostEqual(t.start, cut_point - expected_half_left, places=3)
        self.assertAlmostEqual(t.start + t.duration / 2.0, cut_point, places=3)
        tl.mouseReleaseEvent(QMouseEvent(QMouseEvent.MouseButtonRelease, drag_left_pos, drag_left_pos, Qt.LeftButton, Qt.NoButton, Qt.NoModifier))


if __name__ == "__main__":
    unittest.main()
