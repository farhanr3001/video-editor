"""Unit tests for Visual FX section, subsections, inspector, keyframe synergy, and export."""
import copy
import math
import unittest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from kinetic_cut.effects import CATALOG, DESCRIPTIONS, EFFECT_ICONS, compatible
from kinetic_cut.visual_fx import (
    VISUAL_FX_SUBSECTIONS,
    VISUAL_FX_NAMES,
    VISUAL_FX_SET,
    SUBSECTION_BY_EFFECT,
    default_visual_fx,
    evaluate_visual_fx,
    evaluate_single_effect,
    apply_visual_fx_to_transform,
    bake_visual_fx_to_keyframes,
    visual_fx_synthetic_keyframes,
)
from kinetic_cut.model import Project, MediaItem, TimelineItem, Transform


class VisualFXCatalogTests(unittest.TestCase):
    def test_catalog_and_category_order(self):
        """Visual FX must be the 1st key in CATALOG, making it index 1 in category list (after All Effects)."""
        keys = list(CATALOG.keys())
        self.assertEqual(keys[0], "Visual FX", "Visual FX must be the first key in CATALOG")
        
        # Test simulated category list
        categories = ["All Effects", *CATALOG]
        self.assertEqual(categories[0], "All Effects")
        self.assertEqual(categories[1], "Visual FX", "Visual FX must be the 2nd category in the list")

    def test_subsections_count_and_composition(self):
        """Must have 3 subsections: Zooms (13), Camera Movement (14), Shake / Impact Effects (10) -> 37 total."""
        self.assertIn("Zooms", VISUAL_FX_SUBSECTIONS)
        self.assertIn("Camera Movement", VISUAL_FX_SUBSECTIONS)
        self.assertIn("Shake / Impact Effects", VISUAL_FX_SUBSECTIONS)

        zooms = VISUAL_FX_SUBSECTIONS["Zooms"]
        camera = VISUAL_FX_SUBSECTIONS["Camera Movement"]
        shake = VISUAL_FX_SUBSECTIONS["Shake / Impact Effects"]

        self.assertEqual(len(zooms), 13, f"Expected 13 Zooms, got {len(zooms)}: {zooms}")
        self.assertEqual(len(camera), 14, f"Expected 14 Camera Movement effects, got {len(camera)}: {camera}")
        self.assertEqual(len(shake), 10, f"Expected 10 Shake effects, got {len(shake)}: {shake}")
        self.assertEqual(len(VISUAL_FX_NAMES), 37, f"Expected 37 total effects, got {len(VISUAL_FX_NAMES)}")

        # Verify all 37 have descriptions and icons
        for name in VISUAL_FX_NAMES:
            self.assertIn(name, DESCRIPTIONS, f"Missing description for {name}")
            self.assertIn(name, EFFECT_ICONS, f"Missing icon mapping for {name}")
            self.assertTrue(len(DESCRIPTIONS[name]) > 10, f"Description too short for {name}")

    def test_drag_and_drop_compatibility(self):
        """Visual FX must be compatible with video/image clips on video tracks, not audio or titles."""
        p = Project(
            media=[
                MediaItem("v1", "v1.mp4", "video", "Vid", 10.0),
                MediaItem("a1", "a1.mp3", "audio", "Aud", 10.0),
            ],
            timeline=[
                TimelineItem("vid_clip", "v1", "video_1", 0.0, 5.0, role="video"),
                TimelineItem("img_clip", "v1", "video_1", 5.0, 5.0, role="image"),
                TimelineItem("aud_clip", "a1", "audio_1", 0.0, 5.0, role="audio"),
                TimelineItem("title_clip", "", "video_1", 0.0, 5.0, role="title"),
                TimelineItem("graphic_clip", "", "video_1", 0.0, 5.0, role="graphic"),
            ]
        )

        vid = p.item_by_id("vid_clip")
        img = p.item_by_id("img_clip")
        aud = p.item_by_id("aud_clip")
        tit = p.item_by_id("title_clip")
        grp = p.item_by_id("graphic_clip")

        for name in VISUAL_FX_NAMES:
            self.assertTrue(compatible(name, vid, p), f"{name} should be compatible with video clip")
            self.assertTrue(compatible(name, img, p), f"{name} should be compatible with image clip")
            self.assertFalse(compatible(name, aud, p), f"{name} should NOT be compatible with audio clip")
            self.assertFalse(compatible(name, tit, p), f"{name} should NOT be compatible with title clip")
            self.assertFalse(compatible(name, grp, p), f"{name} should NOT be compatible with graphic clip")


class VisualFXMathEvaluationTests(unittest.TestCase):
    def test_zoom_evaluation_and_focal_point(self):
        """Punch zoom should scale from 1.0 to 1.30 and shift focal point."""
        effect = default_visual_fx("Punch Zoom")
        effect["duration"] = 0.5
        effect["zoom_start"] = 1.0
        effect["zoom_target"] = 1.40
        effect["center_x"] = 0.25
        effect["center_y"] = 0.25

        # At t=0
        tf_start = evaluate_single_effect(effect, 0.0, 5.0)
        self.assertAlmostEqual(tf_start.delta_scale, 0.0, places=2)
        self.assertAlmostEqual(tf_start.delta_x, 0.0, places=2)

        # At t=0.5 (end of zoom)
        tf_end = evaluate_single_effect(effect, 0.5, 5.0)
        self.assertAlmostEqual(tf_end.delta_scale, 0.40, places=2)
        # Center shift: (0.5 - 0.25) * 0.40 = +0.10
        self.assertAlmostEqual(tf_end.delta_x, 0.10, places=2)
        self.assertAlmostEqual(tf_end.delta_y, 0.10, places=2)

    def test_zoom_bounce(self):
        """Zoom bounce should oscillate around target zoom."""
        effect = default_visual_fx("Zoom Bounce")
        effect["duration"] = 0.6
        effect["zoom_start"] = 1.0
        effect["zoom_target"] = 1.30
        
        samples = [evaluate_single_effect(effect, t, 5.0).delta_scale for t in [0.0, 0.15, 0.3, 0.45, 0.6]]
        # Should start at 0, rise, and end near 0.30
        self.assertAlmostEqual(samples[0], 0.0, places=2)
        self.assertGreater(max(samples), 0.25)

    def test_camera_movement_pan_and_tilt(self):
        """Pan left/right should smoothly interpolate pan X."""
        effect = default_visual_fx("Pan Left/Right")
        effect["duration"] = 2.0
        effect["pan_x_start"] = -0.10
        effect["pan_x_end"] = 0.10

        tf_start = evaluate_single_effect(effect, 0.0, 5.0)
        self.assertAlmostEqual(tf_start.delta_x, -0.10, places=2)

        tf_mid = evaluate_single_effect(effect, 1.0, 5.0)
        self.assertAlmostEqual(tf_mid.delta_x, 0.0, places=2)

        tf_end = evaluate_single_effect(effect, 2.0, 5.0)
        self.assertAlmostEqual(tf_end.delta_x, 0.10, places=2)

    def test_shake_impact_exponential_decay(self):
        """Heavy impact shake should have high initial vibration and decay to zero."""
        effect = default_visual_fx("Heavy Impact")
        effect["duration"] = 0.8
        effect["shake_decay"] = "Exponential"
        effect["shake_amplitude_x"] = 60.0

        tf_peak = evaluate_single_effect(effect, 0.02, 5.0, width=1000.0)
        tf_decayed = evaluate_single_effect(effect, 0.78, 5.0, width=1000.0)

        self.assertGreater(abs(tf_peak.delta_x), abs(tf_decayed.delta_x))

    def test_apply_visual_fx_to_transform(self):
        """Transform object should be properly updated by VisualFXTransform."""
        tf = Transform(x=0.5, y=0.5, scale=1.0, rotation=0.0)
        item = TimelineItem("test", "m1", "video_1", 0.0, 5.0, transform=tf)
        item.effects = [default_visual_fx("Punch Zoom")]
        item.effects[0]["zoom_start"] = 1.0
        item.effects[0]["zoom_target"] = 1.50
        item.effects[0]["duration"] = 0.5

        vfx = evaluate_visual_fx(item, 0.5)
        self.assertTrue(vfx.is_active)
        apply_visual_fx_to_transform(tf, vfx)

        self.assertAlmostEqual(tf.scale, 1.50, places=2)


class VisualFXKeyframeSynergyTests(unittest.TestCase):
    def test_bake_visual_fx_to_keyframes(self):
        """Baking Visual FX should write keyframe points and disable the procedural effect."""
        item = TimelineItem("clip", "m1", "video_1", 0.0, 4.0, transform=Transform(x=0.5, y=0.5, scale=1.0))
        effect = default_visual_fx("Punch Zoom")
        effect["duration"] = 0.5
        effect["zoom_target"] = 1.40
        item.effects = [effect]

        self.assertTrue(bake_visual_fx_to_keyframes(item, effect))
        
        # Effect should be deactivated
        self.assertFalse(effect["enabled"])
        self.assertTrue(effect.get("baked_to_keyframes"))

        # Clip keyframes should be populated
        self.assertIn("scale", item.keyframes)
        self.assertIn("x", item.keyframes)
        self.assertIn("y", item.keyframes)
        self.assertGreaterEqual(len(item.keyframes["scale"]), 3)

        # First and last values should match expected zoom progression
        first_scale = item.keyframes["scale"][0]["value"]
        last_scale = item.keyframes["scale"][-1]["value"]
        self.assertAlmostEqual(first_scale, 1.0, places=2)
        self.assertAlmostEqual(last_scale, 1.40, places=2)

    def test_synthetic_keyframes_for_export(self):
        """Export synthetic keyframes generator should create valid keyframe tracks."""
        item = TimelineItem("clip", "m1", "video_1", 0.0, 3.0, transform=Transform(x=0.5, y=0.5, scale=1.0))
        item.effects = [default_visual_fx("Smooth Zoom")]
        item.effects[0]["duration"] = 2.0
        item.effects[0]["zoom_target"] = 1.30

        keys = visual_fx_synthetic_keyframes(item)
        self.assertIn("scale", keys)
        self.assertIn("x", keys)
        self.assertIn("y", keys)
        self.assertGreater(len(keys["scale"]), 5)
        self.assertAlmostEqual(keys["scale"][-1]["value"], 1.30, places=2)


class VisualFXUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_inspector_visual_fx_controls(self):
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        w.resize(1200, 800)
        w.show()
        p = Project(
            media=[MediaItem("m1", "test.mp4", "video", "Test", 10.0)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 5.0, role="video")]
        )
        w.set_project(p)
        w.timeline.selected_id = "v1"
        w.timeline.selected_ids = {"v1"}
        
        # Apply Punch Zoom via apply_effect
        w.apply_effect("Punch Zoom")
        item = p.item_by_id("v1")
        self.assertEqual(len(item.effects), 1)
        self.assertEqual(item.effects[0]["name"], "Punch Zoom")
        self.assertEqual(item.effects[0]["category"], "Visual FX")

        # Check Inspector UI state
        w.inspector.select("v1")
        self.assertFalse(w.inspector.vfx_panel.isHidden())
        self.assertFalse(w.inspector.vfx_zoom_panel.isHidden())
        self.assertTrue(w.inspector.vfx_cam_panel.isHidden())
        self.assertTrue(w.inspector.vfx_shake_panel.isHidden())

        # Edit duration and target zoom via inspector
        w.inspector.vfx_duration.change(1.8, False)
        self.assertAlmostEqual(item.effects[0]["duration"], 1.8)

        w.inspector.vfx_zoom_target.change(1.65, False)
        self.assertAlmostEqual(item.effects[0]["zoom_target"], 1.65)

        # Test Ken Burns swap
        item.effects.append(default_visual_fx("Ken Burns"))
        w.inspector.select("v1")
        w.inspector.effect_picker.setCurrentIndex(1)
        self.assertTrue(w.inspector.vfx_cam_panel.isVisible())
        s1 = item.effects[1]["ken_burns_start_scale"]
        s2 = item.effects[1]["ken_burns_end_scale"]
        w.inspector.swap_ken_burns()
        self.assertEqual(item.effects[1]["ken_burns_start_scale"], s2)
        self.assertEqual(item.effects[1]["ken_burns_end_scale"], s1)

        # Test Bake to keyframes
        w.inspector.bake_vfx_effect()
        self.assertTrue(item.effects[1]["baked_to_keyframes"])
        self.assertIn("scale", item.keyframes)

        w.close()

    def test_drag_and_drop_effect_to_clip(self):
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        w.resize(1200, 800)
        w.show()
        p = Project(
            media=[MediaItem("m1", "test.mp4", "video", "Test", 10.0)],
            timeline=[
                TimelineItem("v1", "m1", "video_1", 0.0, 5.0, role="video"),
                TimelineItem("v2", "m1", "video_1", 5.0, 5.0, role="video"),
            ]
        )
        w.set_project(p)

        # Simulate dropping "Camera Shake" onto v1
        w.apply_effect_to("Camera Shake", "v1")
        item1 = p.item_by_id("v1")
        self.assertEqual(len(item1.effects), 1)
        self.assertEqual(item1.effects[0]["name"], "Camera Shake")
        self.assertEqual(item1.effects[0]["category"], "Visual FX")

        # Simulate dropping "Pan Left/Right" onto v2
        w.apply_effect_to("Pan Left/Right", "v2")
        item2 = p.item_by_id("v2")
        self.assertEqual(len(item2.effects), 1)
        self.assertEqual(item2.effects[0]["name"], "Pan Left/Right")

        w.close()

    def test_all_effects_does_not_contain_subsection_headers(self):
        """'All Effects' must not contain subsection headers, only pure effect items."""
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        w.resize(1200, 800)
        w.show()
        
        # Select 'All Effects'
        w.effects_panel.categories.setCurrentRow(0)
        self.assertEqual(w.effects_panel.categories.currentItem().text(), "All Effects")
        
        # None of the items should be empty-data header items
        header_items = [w.effects_panel.list.item(i).text() for i in range(w.effects_panel.list.count()) if not w.effects_panel.list.item(i).data(Qt.UserRole)]
        self.assertEqual(header_items, [], f"All Effects must not have subsection headers: {header_items}")
        
        # Select 'Visual FX'
        w.effects_panel.categories.setCurrentRow(1)
        self.assertEqual(w.effects_panel.categories.currentItem().text(), "Visual FX")
        
        # In Visual FX, should have exactly 3 clean subsection headers
        vfx_headers = [w.effects_panel.list.item(i).text() for i in range(w.effects_panel.list.count()) if not w.effects_panel.list.item(i).data(Qt.UserRole)]
        self.assertEqual(vfx_headers, ["Zooms", "Camera Movement", "Shake / Impact Effects"])
        
        w.close()

    def test_zoom_applied_to_video_canvas_paint_event_no_error(self):
        """Applying zoom effect onto a video clip and painting canvas must not raise NameError (e.g. copy)."""
        import tempfile
        from pathlib import Path
        from kinetic_cut.ui import MainWindow
        from PySide6.QtGui import QImage
        w = MainWindow()
        w.resize(1200, 800)
        w.show()

        temp_dir = tempfile.TemporaryDirectory()
        img_path = Path(temp_dir.name) / "frame.png"
        test_img = QImage(320, 180, QImage.Format_RGB32)
        test_img.fill(Qt.blue)
        test_img.save(str(img_path))
        
        p = Project(
            media=[MediaItem("m1", str(img_path), "image", "Test", 10.0, 320, 180)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 5.0, role="video")]
        )
        w.set_project(p)
        w.timeline.select_ids({"v1"}, "v1")
        w.seek(1.0)
        
        # Apply Punch Zoom
        w.apply_effect("Punch Zoom")
        
        # Call _visible_items and render a paint pass on the preview canvas
        visible = w.preview._visible_items()
        self.assertEqual(len(visible), 1)
        self.assertGreater(visible[0][0].transform.scale, 1.0)
        
        # Direct paint pass onto offscreen pixmap to ensure zero paintEvent exceptions
        pixmap = w.preview.grab()
        self.assertFalse(pixmap.isNull())
        
        w.close()

    def test_zoom_return_ease_out_curve(self):
        """Zoom-in effects with zoom_return=True must ease out back to 1.0x neutral scale."""
        from kinetic_cut.visual_fx import ZOOM_IN_EFFECTS, default_visual_fx, evaluate_single_effect
        self.assertIn("Punch Zoom", ZOOM_IN_EFFECTS)
        self.assertIn("Smooth Zoom", ZOOM_IN_EFFECTS)
        self.assertIn("Snap Zoom", ZOOM_IN_EFFECTS)
        self.assertNotIn("Slow Pull-Out", ZOOM_IN_EFFECTS, "Slow Pull-Out is a zoom out, must NOT have return")
        self.assertNotIn("Zoom Out Reveal", ZOOM_IN_EFFECTS, "Zoom Out Reveal is a zoom out, must NOT have return")

        # Create a Punch Zoom effect with duration=1.0, zoom_return=True, hold=0.2
        fx = default_visual_fx("Punch Zoom")
        fx.update(duration=1.0, zoom_start=1.0, zoom_target=1.4, zoom_return=True, zoom_hold_duration=0.2, bounce_amplitude=0.0)
        
        # At t = 0.0: neutral scale
        res_0 = evaluate_single_effect(fx, 0.0, 5.0)
        self.assertAlmostEqual(res_0.delta_scale, 0.0, places=2)

        # Attack phase ends around (1.0 - 0.2) / 2 = 0.4s
        # At t = 0.45s (during hold): peak scale reached (+0.4)
        res_hold = evaluate_single_effect(fx, 0.45, 5.0)
        self.assertAlmostEqual(res_hold.delta_scale, 0.4, places=2)

        # During release (e.g. t = 0.85s): scale delta decreases back towards 0
        res_release = evaluate_single_effect(fx, 0.85, 5.0)
        self.assertLess(res_release.delta_scale, 0.35)
        self.assertGreater(res_release.delta_scale, 0.0)

        # Past duration (t = 1.05s): completely returns to neutral (is_active False)
        res_after = evaluate_single_effect(fx, 1.05, 5.0)
        self.assertFalse(res_after.is_active)
        self.assertAlmostEqual(res_after.delta_scale, 0.0, places=3)

    def test_vfx_duration_clamping_to_media_duration(self):
        """Inspector duration & start offset sliders must be clamped to the media item duration."""
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        w.resize(1200, 800)
        w.show()

        # 3-second media clip
        p = Project(
            media=[MediaItem("m1", "dummy.mp4", "video", "ShortClip", 3.0, 1920, 1080)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 3.0, role="video")]
        )
        w.set_project(p)
        w.timeline.select_ids({"v1"}, "v1")
        w.apply_effect("Punch Zoom")

        # Verify duration spin and high are clamped to 3.0s, NOT 30.0s!
        self.assertAlmostEqual(w.inspector.vfx_duration.high, 3.0, places=2)
        self.assertAlmostEqual(w.inspector.vfx_duration.spin.maximum(), 3.0, places=2)
        self.assertAlmostEqual(w.inspector.vfx_start_time.high, 3.0, places=2)
        self.assertAlmostEqual(w.inspector.vfx_start_time.spin.maximum(), 3.0, places=2)

        # Setting duration to 10s must be clamped to 3.0
        w.inspector.vfx_duration.change(10.0)
        self.assertLessEqual(w.inspector.vfx_duration.spin.value(), 3.0)

        w.close()

    def test_crosshair_visibility_guards(self):
        """Crosshair must only be painted when paused, timeline clip selected, and on Effects tab."""
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        w.resize(1200, 800)
        w.show()

        p = Project(
            media=[MediaItem("m1", "dummy.mp4", "video", "TestClip", 5.0, 1920, 1080)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 5.0, role="video")]
        )
        w.set_project(p)
        w.timeline.select_ids({"v1"}, "v1")
        w.apply_effect("Punch Zoom")

        # 1. When paused and on Effects tab -> crosshair is drawn
        w.transport.playing = False
        w.inspector.tabs.setCurrentIndex(2)  # Effects tab
        self.assertEqual(w.inspector.tabs.tabText(w.inspector.tabs.currentIndex()), "Effects")

        # 2. When playing -> crosshair guard condition fails
        w.transport.playing = True
        win = w.preview.window()
        is_paused = getattr(win, "transport", None) is None or not getattr(win.transport, "playing", False)
        self.assertFalse(is_paused)

        # 3. When paused but switched to Video tab -> crosshair guard condition fails
        w.transport.playing = False
        w.inspector.tabs.setCurrentIndex(0)  # Video tab
        tabs = getattr(w.inspector, "tabs", None)
        effects_tab_active = tabs is not None and tabs.tabText(tabs.currentIndex()) == "Effects"
        self.assertFalse(effects_tab_active)

        w.close()

    def test_vfx_timing_dialog_interaction(self):
        """VFXTimingDialog must live-update timing and handle apply/cancel correctly."""
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.vfx_timing_dialog import VFXTimingDialog
        w = MainWindow()
        w.resize(1200, 800)
        w.show()

        p = Project(
            media=[MediaItem("m1", "dummy.mp4", "video", "TestClip", 4.0, 1920, 1080)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 4.0, role="video")]
        )
        w.set_project(p)
        w.timeline.select_ids({"v1"}, "v1")
        w.apply_effect("Punch Zoom")

        item = w.project.item_by_id("v1")
        effect = item.effects[0]
        dialog = VFXTimingDialog(w, item, effect)

        # Initial checks
        self.assertAlmostEqual(dialog.timeline_widget.start_time, effect["start_time"])
        self.assertAlmostEqual(dialog.timeline_widget.duration, effect["duration"])

        # Simulate dragging to start=0.6, duration=1.8
        dialog.on_range_changed(0.6, 1.8)
        self.assertAlmostEqual(effect["start_time"], 0.6)
        self.assertAlmostEqual(effect["duration"], 1.8)
        self.assertAlmostEqual(w.inspector.vfx_start_time.spin.value(), 0.6)
        self.assertAlmostEqual(w.inspector.vfx_duration.spin.value(), 1.8)

        # Test editing property in right panel (e.g. target zoom and zoom return)
        dialog.on_property_edited("zoom_target", 1.85)
        dialog.on_property_edited("zoom_return", True)
        self.assertTrue(dialog.timeline_widget.has_return_clamping)

        # Test Apply & Close saves changes to the project item
        dialog.accept()
        saved_item = w.project.item_by_id("v1")
        self.assertAlmostEqual(saved_item.effects[0]["start_time"], 0.6)
        self.assertAlmostEqual(saved_item.effects[0]["duration"], 1.8)
        self.assertAlmostEqual(saved_item.effects[0]["zoom_target"], 1.85)
        self.assertTrue(saved_item.effects[0]["zoom_return"])

        dialog.done(0)
        w.close()

    def test_vfx_timing_popout_buttons_and_ease_out_location(self):
        """Popout button must exist on both Start Offset and Duration, and ease out must be in Timing & Easing."""
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        w.resize(1200, 800)
        w.show()

        p = Project(
            media=[MediaItem("m1", "dummy.mp4", "video", "TestClip", 5.0, 1920, 1080)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 5.0, role="video")]
        )
        w.set_project(p)
        w.timeline.select_ids({"v1"}, "v1")

        # 1. Popout buttons exist on both Start Offset and Duration
        self.assertTrue(hasattr(w.inspector, "vfx_timing_popout_start"))
        self.assertTrue(hasattr(w.inspector, "vfx_timing_popout"))

        # 2. Select Punch Zoom (zoom-in effect)
        w.apply_effect("Punch Zoom")
        self.assertTrue(w.inspector.vfx_zoom_return.isVisible())

        # 3. Select Camera Shake (shake effect) -> Return to Normal must be HIDDEN
        w.apply_effect("Camera Shake")
        w.inspector.effect_picker.setCurrentIndex(1)
        self.assertFalse(w.inspector.vfx_zoom_return.isVisible(), "Return to normal must be hidden for non-zoom-in effects")

        w.close()

    def test_vfx_timing_dialog_preenabled_zoom_return(self):
        """VFXTimingDialog must instantiate without error when zoom_return is already True."""
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.vfx_timing_dialog import VFXTimingDialog
        w = MainWindow()
        p = Project(
            media=[MediaItem("m1", "dummy.mp4", "video", "TestClip", 4.0, 1920, 1080)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 4.0, role="video")]
        )
        w.set_project(p)
        w.timeline.select_ids({"v1"}, "v1")
        w.apply_effect("Punch Zoom")

        item = w.project.item_by_id("v1")
        effect = item.effects[0]
        effect["zoom_return"] = True
        effect["zoom_hold_duration"] = 0.25

        # Instantiating dialog must NOT raise AttributeError: 'VFXTimingDialog' object has no attribute 'timeline_widget'
        dialog = VFXTimingDialog(w, item, effect)
        self.assertIsNotNone(dialog.timeline_widget)
        self.assertTrue(dialog.timeline_widget.has_return_clamping)
        self.assertTrue(dialog.props_panel.zoom_return_check.isChecked())
        dialog.done(0)
        w.close()

    def test_zoom_attack_duration_curve_evaluation(self):
        """Customizable zoom_attack_duration must position the attack, hold, and release phases accurately."""
        effect = default_visual_fx("Punch Zoom")
        effect["duration"] = 1.0
        effect["zoom_return"] = True
        effect["zoom_start"] = 1.0
        effect["zoom_target"] = 1.50
        effect["zoom_hold_duration"] = 0.30
        effect["zoom_attack_duration"] = 0.20  # Attack: 0 to 0.2s; Hold: 0.2s to 0.5s; Release: 0.5s to 1.0s

        # At start of attack (t=0)
        tf0 = evaluate_single_effect(effect, 0.0, 5.0)
        self.assertAlmostEqual(tf0.delta_scale, 0.0, places=2)

        # Mid attack (t=0.1s): scale should be progressing
        tf_mid_att = evaluate_single_effect(effect, 0.1, 5.0)
        self.assertGreater(tf_mid_att.delta_scale, 0.1)
        self.assertLess(tf_mid_att.delta_scale, 0.5)

        # During hold (t=0.25s, 0.35s, 0.49s): peak scale (1.5 - 1.0 = 0.5)
        tf_hold1 = evaluate_single_effect(effect, 0.25, 5.0)
        tf_hold2 = evaluate_single_effect(effect, 0.45, 5.0)
        self.assertAlmostEqual(tf_hold1.delta_scale, 0.50, places=2)
        self.assertAlmostEqual(tf_hold2.delta_scale, 0.50, places=2)

        # During ease out release (t=0.75s): decreasing back to neutral
        tf_rel = evaluate_single_effect(effect, 0.75, 5.0)
        self.assertLess(tf_rel.delta_scale, 0.50)
        self.assertGreater(tf_rel.delta_scale, 0.0)

        # After duration (t=1.05s): returned to neutral (is_active=False or delta_scale=0)
        tf_end = evaluate_single_effect(effect, 1.05, 5.0)
        self.assertFalse(tf_end.is_active)

    def test_thin_clamper_and_draggable_hold_pill(self):
        """Ruler clamper must be thin (7px) on bottom line, scrub zone upper ruler unobstructed, and hold pill draggable."""
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.vfx_timing_dialog import VFXTimingDialog
        from PySide6.QtCore import QPointF
        w = MainWindow()
        p = Project(
            media=[MediaItem("m1", "dummy.mp4", "video", "TestClip", 5.0, 1920, 1080)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 5.0, role="video")]
        )
        w.set_project(p)
        w.timeline.select_ids({"v1"}, "v1")
        w.apply_effect("Punch Zoom")

        item = w.project.item_by_id("v1")
        effect = item.effects[0]
        effect["zoom_return"] = True
        effect["start_time"] = 0.5
        effect["duration"] = 2.0
        effect["zoom_hold_duration"] = 0.4
        effect["zoom_attack_duration"] = 0.3

        dialog = VFXTimingDialog(w, item, effect)
        tw = dialog.timeline_widget

        # Range bar is thin (height 7px) positioned at y=26
        rbar = tw.range_bar_rect()
        self.assertEqual(rbar.y(), 26.0)
        self.assertEqual(rbar.height(), 7.0)

        # In and out handles are at y=22
        in_h = tw.in_handle_rect()
        out_h = tw.out_handle_rect()
        self.assertEqual(in_h.y(), 22.0)
        self.assertEqual(out_h.y(), 22.0)

        # Upper ruler (y < 22) reserved for scrubbing:
        class DummyEvent:
            def __init__(self, x, y, button=Qt.LeftButton):
                self._pos = QPointF(x, y)
                self._btn = button
            def position(self): return self._pos
            def button(self): return self._btn

        # Click at y=10 (upper ruler) -> must engage playhead scrub
        tw.mousePressEvent(DummyEvent(tw.time_to_x(1.5), 10.0))
        self.assertEqual(tw.drag_mode, "playhead")
        tw.mouseReleaseEvent(DummyEvent(tw.time_to_x(1.5), 10.0))

        # Hold pill rect exists and is at y=21
        hpill = tw.hold_pill_rect()
        self.assertTrue(tw.has_return_clamping)
        self.assertEqual(hpill.y(), 21.0)
        self.assertGreater(hpill.width(), 10.0)

        # Click on hold pill -> must engage "hold" drag mode
        tw.mousePressEvent(DummyEvent(hpill.center().x(), hpill.center().y()))
        self.assertEqual(tw.drag_mode, "hold")

        # Drag hold pill forward by 0.2s
        drag_start_t = tw.x_to_time(hpill.center().x())
        new_x = tw.time_to_x(drag_start_t + 0.2)
        tw.mouseMoveEvent(DummyEvent(new_x, hpill.center().y()))
        self.assertAlmostEqual(effect["zoom_attack_duration"], 0.5, places=1)

        tw.mouseReleaseEvent(DummyEvent(new_x, hpill.center().y()))
        self.assertIsNone(tw.drag_mode)

        dialog.done(0)
        w.close()

    def test_timeline_clip_vfx_overlay_and_flash(self):
        """Timeline must support flash_vfx_overlay and paint clamper overlay for selected Visual FX clips."""
        from kinetic_cut.ui import MainWindow
        w = MainWindow()
        p = Project(
            media=[MediaItem("m1", "dummy.mp4", "video", "TestClip", 5.0, 1920, 1080)],
            timeline=[TimelineItem("v1", "m1", "video_1", 0.0, 5.0, role="video")]
        )
        w.set_project(p)
        w.timeline.select_ids({"v1"}, "v1")
        w.apply_effect("Punch Zoom")

        item = w.project.item_by_id("v1")
        effect = item.effects[0]

        # Verify default show_timeline_overlay is True
        self.assertTrue(effect.get("show_timeline_overlay", True))
        self.assertTrue(w.inspector.vfx_show_overlay.isChecked())

        # Test flash_vfx_overlay
        self.assertIsNone(w.timeline._vfx_flash_item_id)
        w.timeline.flash_vfx_overlay("v1")
        self.assertEqual(w.timeline._vfx_flash_item_id, "v1")
        self.assertTrue(w.timeline._vfx_flash_timer.isActive())

        # Clear flash
        w.timeline._clear_vfx_flash()
        self.assertIsNone(w.timeline._vfx_flash_item_id)

        # Test inspector edits trigger flash
        w.inspector.edit_effect("duration", 0.8)
        self.assertEqual(w.timeline._vfx_flash_item_id, "v1")

        # Test toggle show_timeline_overlay
        w.inspector.vfx_show_overlay.setChecked(False)
        self.assertFalse(effect.get("show_timeline_overlay"))

        w.close()


if __name__ == "__main__":
    unittest.main()


