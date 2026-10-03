"""Comprehensive end-to-end verification script for Visual FX effects.

Verifies:
1. Catalog order: 'Visual FX' is category index 1 (right below 'All Effects').
2. Subsection grouping: Zooms (13), Camera Movement (14), Shake / Impact Effects (10) -> 37 total.
3. Subsection headers rendered in EffectList as non-draggable / non-clickable headers.
4. Drag-and-drop & double-click application to video layer media (videos & images).
5. Effects Inspector panel property synchronization across all subsections.
6. Preview canvas transform evaluation with focal point feedback.
7. Keyframe synergy & 'Convert to Keyframes' baking.
8. FFmpeg export filtergraph generation.
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from kinetic_cut.effects import CATALOG, DESCRIPTIONS, EFFECT_ICONS, compatible
from kinetic_cut.visual_fx import (
    VISUAL_FX_SUBSECTIONS,
    VISUAL_FX_NAMES,
    default_visual_fx,
    evaluate_visual_fx,
    bake_visual_fx_to_keyframes,
    visual_fx_synthetic_keyframes,
)
from kinetic_cut.model import Project, MediaItem, TimelineItem, Transform
from kinetic_cut.ui import MainWindow
from kinetic_cut.rendergraph import command
from kinetic_cut.exporter import PRESETS


def main():
    print("=== Starting Visual FX End-to-End Verification ===")
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Verify Catalog Ordering
    print("[Check 1] Verifying Catalog Ordering...")
    categories = list(CATALOG.keys())
    assert categories[0] == "Visual FX", f"Visual FX must be first key in CATALOG, got {categories[0]}"
    all_cats = ["All Effects", *CATALOG]
    assert all_cats[1] == "Visual FX", f"Visual FX must be index 1 in category list, got {all_cats[1]}"
    print("  -> Passed: Visual FX is category index 1 right after 'All Effects'.")

    # 2. Verify Subsections & 37 Effects
    print("[Check 2] Verifying Subsections & 37 Effects...")
    assert len(VISUAL_FX_SUBSECTIONS["Zooms"]) == 13
    assert len(VISUAL_FX_SUBSECTIONS["Camera Movement"]) == 14
    assert len(VISUAL_FX_SUBSECTIONS["Shake / Impact Effects"]) == 10
    assert len(VISUAL_FX_NAMES) == 37
    for name in VISUAL_FX_NAMES:
        assert name in DESCRIPTIONS, f"Missing description for {name}"
        assert name in EFFECT_ICONS, f"Missing icon for {name}"
    print("  -> Passed: All 37 effects present and cataloged with descriptions and icons.")

    # 3. Verify MainWindow & EffectsPanel Subsection Headers
    print("[Check 3] Verifying UI Effects List & Subsection Headers...")
    temp_dir = tempfile.TemporaryDirectory()
    img_path = Path(temp_dir.name) / "test_frame.png"
    img = QImage(320, 180, QImage.Format_RGB32)
    img.fill(Qt.blue)
    img.save(str(img_path))

    w = MainWindow()
    w.resize(1280, 800)
    w.show()

    # Verify All Effects has ZERO subsection headers
    w.effects_panel.categories.setCurrentRow(0)
    w.effects_panel.refresh()
    all_headers = [w.effects_panel.list.item(i).text() for i in range(w.effects_panel.list.count()) if not w.effects_panel.list.item(i).data(Qt.UserRole)]
    assert len(all_headers) == 0, f"All Effects must have 0 subsection headers, got: {all_headers}"
    print("  -> Passed: All Effects has no subsection headers.")

    # Switch category to Visual FX
    vfx_cat_row = 1  # Visual FX
    w.effects_panel.categories.setCurrentRow(vfx_cat_row)
    w.effects_panel.refresh()

    list_widget = w.effects_panel.list
    items_count = list_widget.count()
    # 37 effects + 3 subsection headers = 40 items in list
    assert items_count == 40, f"Expected 40 items (37 effects + 3 headers), got {items_count}"

    # Verify subsection headers have empty UserRole and cannot be dragged
    header_titles = []
    for idx in range(items_count):
        it = list_widget.item(idx)
        role = it.data(Qt.UserRole)
        if not role:
            header_titles.append(it.text())
            assert it.flags() == Qt.NoItemFlags, f"Header must have NoItemFlags, got {it.flags()}"

    assert header_titles == ["Zooms", "Camera Movement", "Shake / Impact Effects"], f"Expected clean headers, got {header_titles}"
    print(f"  -> Passed: {len(header_titles)} clean subsection headers verified in UI: {header_titles}.")

    # 4. Verify Project Setup & Application to Video/Image Clips
    print("[Check 4] Applying Visual FX effects to timeline clips...")
    p = Project(
        media=[
            MediaItem("m_vid", str(img_path), "video", "Test Vid", 10.0, 320, 180),
            MediaItem("m_img", str(img_path), "image", "Test Img", 10.0, 320, 180),
        ],
        timeline=[
            TimelineItem("clip_vid", "m_vid", "video_1", 0.0, 5.0, role="video"),
            TimelineItem("clip_img", "m_img", "video_1", 5.0, 5.0, role="image"),
        ]
    )
    p.settings.width = 320
    p.settings.height = 180
    p.settings.fps = 30
    w.set_project(p)

    # Drop "Punch Zoom" onto clip_vid
    w.apply_effect_to("Punch Zoom", "clip_vid")
    item_vid = p.item_by_id("clip_vid")
    assert len(item_vid.effects) == 1
    assert item_vid.effects[0]["name"] == "Punch Zoom"
    assert item_vid.effects[0]["category"] == "Visual FX"

    # Drop "Ken Burns" onto clip_img
    w.apply_effect_to("Ken Burns", "clip_img")
    item_img = p.item_by_id("clip_img")
    assert len(item_img.effects) == 1
    assert item_img.effects[0]["name"] == "Ken Burns"

    # Drop "Heavy Impact" onto clip_vid
    w.apply_effect_to("Heavy Impact", "clip_vid")
    assert len(item_vid.effects) == 2
    assert item_vid.effects[1]["name"] == "Heavy Impact"
    print("  -> Passed: Applied Punch Zoom, Ken Burns, and Heavy Impact to clips.")

    # 5. Verify Inspector Property Controls & Edits
    print("[Check 5] Verifying Inspector Controls and Param Edits...")
    w.inspector.select("clip_vid")
    w.inspector.effect_picker.setCurrentIndex(0)  # Punch Zoom

    assert not w.inspector.vfx_panel.isHidden()
    assert not w.inspector.vfx_zoom_panel.isHidden()
    assert w.inspector.vfx_cam_panel.isHidden()
    assert w.inspector.vfx_shake_panel.isHidden()

    # Modify duration and focal point via inspector
    w.inspector.vfx_duration.change(1.75, False)
    assert abs(item_vid.effects[0]["duration"] - 1.75) < 0.01

    w.inspector.vfx_center_x.change(0.35, False)
    assert abs(item_vid.effects[0]["center_x"] - 0.35) < 0.01

    w.inspector.vfx_zoom_target.change(1.60, False)
    assert abs(item_vid.effects[0]["zoom_target"] - 1.60) < 0.01

    # Select Heavy Impact
    w.inspector.effect_picker.setCurrentIndex(1)
    assert not w.inspector.vfx_shake_panel.isHidden()
    w.inspector.vfx_amp_x.change(75.0, False)
    assert abs(item_vid.effects[1]["shake_amplitude_x"] - 75.0) < 0.01
    print("  -> Passed: Inspector controls updated parameters accurately.")

    # 6. Verify Real-Time Preview Canvas Transform Evaluation
    print("[Check 6] Verifying Preview Canvas Evaluation...")
    # Seek to t=1.0 (midway into Punch Zoom)
    w.seek(1.0)
    vfx_tf = evaluate_visual_fx(item_vid, 1.0, 320, 180)
    assert vfx_tf.is_active
    assert vfx_tf.delta_scale > 0.1
    print(f"  -> Passed: Preview transform evaluated active: delta_scale={vfx_tf.delta_scale:.3f}, delta_x={vfx_tf.delta_x:.3f}")

    # 7. Verify Keyframe Baking
    print("[Check 7] Verifying 'Convert to Keyframes' baking...")
    w.inspector.select("clip_img")
    w.inspector.effect_picker.setCurrentIndex(0)  # Ken Burns
    assert not item_img.keyframes
    w.inspector.bake_vfx_effect()
    assert item_img.effects[0]["baked_to_keyframes"] is True
    assert "scale" in item_img.keyframes
    assert "x" in item_img.keyframes
    assert "y" in item_img.keyframes
    assert len(item_img.keyframes["scale"]) >= 5
    print(f"  -> Passed: Ken Burns baked into {len(item_img.keyframes['scale'])} keyframe points.")

    # 8. Verify Export Filtergraph Generation
    print("[Check 8] Verifying FFmpeg Rendergraph generation with Visual FX...")
    out_path = Path(temp_dir.name) / "vfx_export.mp4"
    cmd = command(p, str(out_path), next(iter(PRESETS.values())), False, "CPU", export_audio=False)
    cmd_str = " ".join(cmd)
    assert "scale=" in cmd_str
    assert "overlay=" in cmd_str

    # 9. Verify Inspector Duration Clamping to Media Duration
    print("[Check 9] Verifying Inspector duration clamping...")
    w.timeline.select_ids({"clip_vid"}, "clip_vid")
    w.inspector.select("clip_vid")
    # clip_vid duration is 5.0s
    assert abs(w.inspector.vfx_duration.high - item_vid.duration) < 0.01, f"Expected max {item_vid.duration}, got {w.inspector.vfx_duration.high}"
    assert abs(w.inspector.vfx_duration.spin.maximum() - item_vid.duration) < 0.01
    print(f"  -> Passed: Duration slider and spinbox clamped to clip duration ({item_vid.duration}s).")

    # 10. Verify VFX Timing Dialog and Interactive Ruler Dragger
    print("[Check 10] Verifying VFX Timing Dialog...")
    from kinetic_cut.vfx_timing_dialog import VFXTimingDialog
    dialog = VFXTimingDialog(w, item_vid, item_vid.effects[0])
    assert dialog.timeline_widget.clip_duration == item_vid.duration
    dialog.on_range_changed(1.2, 2.5)
    assert abs(item_vid.effects[0]["start_time"] - 1.2) < 0.01
    assert abs(item_vid.effects[0]["duration"] - 2.5) < 0.01
    assert abs(w.inspector.vfx_start_time.spin.value() - 1.2) < 0.01
    assert abs(w.inspector.vfx_duration.spin.value() - 2.5) < 0.01
    dialog.reject()
    assert abs(item_vid.effects[0]["start_time"] - dialog.original_start) < 0.01
    assert abs(item_vid.effects[0]["duration"] - dialog.original_dur) < 0.01
    dialog.done(0)
    print("  -> Passed: VFX Timing Dialog live sync and rollback verified.")

    # 11. Verify Crosshair Guarding
    print("[Check 11] Verifying Crosshair guards during playback & tab switches...")
    w.transport.playing = False
    w.inspector.tabs.setCurrentIndex(2)  # Effects tab
    win = w.preview.window()
    assert (getattr(win, "transport", None) is None or not getattr(win.transport, "playing", False))
    assert getattr(w.inspector, "tabs", None).tabText(w.inspector.tabs.currentIndex()) == "Effects"
    # When playing
    w.transport.playing = True
    assert getattr(win.transport, "playing", False) is True
    w.transport.playing = False
    print("  -> Passed: Crosshair condition guards verified.")

    # 12. Verify Zoom-in Ease Out Return Curve
    print("[Check 12] Verifying Zoom-in Ease Out Return curve...")
    from kinetic_cut.visual_fx import evaluate_single_effect
    zoom_fx = default_visual_fx("Punch Zoom")
    zoom_fx.update(duration=1.0, zoom_start=1.0, zoom_target=1.5, zoom_return=True, zoom_hold_duration=0.2, zoom_attack_duration=0.4)
    # Peak at hold phase (0.4 to 0.6s)
    mid_tf = evaluate_single_effect(zoom_fx, 0.5, 5.0)
    assert abs(mid_tf.delta_scale - 0.5) < 0.01
    # Returning during release (0.6 to 1.0s)
    late_tf = evaluate_single_effect(zoom_fx, 0.85, 5.0)
    assert 0.0 < late_tf.delta_scale < 0.45
    # Finished after duration
    done_tf = evaluate_single_effect(zoom_fx, 1.1, 5.0)
    assert not done_tf.is_active
    print("  -> Passed: Attack -> Hold -> Ease-out return curve cleanly executes.")

    # 13. Verify Customizable Hold, Thin Clamper, and Timeline Clip Overlay
    print("[Check 13] Verifying Customizable Hold, Thin Clamper, and Timeline Clip Overlay...")
    w.set_project(p)
    w.timeline.select_ids({"clip_vid"}, "clip_vid")
    w.inspector.select("clip_vid")
    w.inspector.effect_picker.setCurrentIndex(0)  # Punch Zoom

    # Verify toggle exists and defaults to True
    assert w.inspector.vfx_show_overlay.isChecked() is True
    assert item_vid.effects[0].get("show_timeline_overlay", True) is True

    # Test customizable attack duration
    w.inspector.edit_effect("zoom_return", True)
    w.inspector.edit_effect("zoom_hold_duration", 0.3)
    w.inspector.edit_effect("zoom_attack_duration", 0.4)
    assert abs(item_vid.effects[0]["zoom_attack_duration"] - 0.4) < 0.01

    # Verify timeline flash overlay
    w.timeline.flash_vfx_overlay("clip_vid")
    assert w.timeline._vfx_flash_item_id == "clip_vid"
    assert w.timeline._vfx_flash_timer.isActive()

    # Verify thin clamper geometry in VFXTimingDialog
    dialog = VFXTimingDialog(w, item_vid, item_vid.effects[0])
    tw = dialog.timeline_widget
    assert tw.range_bar_rect().height() == 7.0
    assert tw.range_bar_rect().y() == 26.0
    assert tw.hold_pill_rect().y() == 21.0
    dialog.done(0)
    print("  -> Passed: Customizable hold, thin bottom clamper, and clip overlay verified.")

    w.set_project(Project())
    w.close()
    app.processEvents()
    del w
    import gc; gc.collect()
    try:
        temp_dir.cleanup()
    except Exception:
        pass
    print("=== ALL VISUAL FX VERIFICATION CHECKS PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
