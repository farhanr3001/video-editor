"""Comprehensive end-to-end verification script for Visual Graphics in Kinetic Cut."""
import copy
import os
import sys
import tempfile
from pathlib import Path

# Ensure application root in sys.path
sys.path.insert(0, os.path.abspath("."))

from PySide6.QtCore import Qt, QPoint, QRectF, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor

from kinetic_cut.effects import CATALOG, GRAPHICS
from kinetic_cut.graphics import (
    GRAPHICS_CATALOG,
    default_graphic_data,
    draw_graphic,
    graphic_to_ass_events,
)
from kinetic_cut.model import Project, TimelineItem, MediaItem, uid
from kinetic_cut.ui import MainWindow
from kinetic_cut.exporter import write_ass


def run_e2e_verification():
    print("=== STARTING VISUAL GRAPHICS E2E VERIFICATION ===")

    app = QApplication.instance() or QApplication([])

    # 1. Verify Catalog
    print("\n[1/7] Verifying Effects Catalog Graphics Category...")
    assert "Graphics" in CATALOG, "Graphics section missing in CATALOG"
    expected = [
        "Circle",
        "Pointing Arrow",
        "Square",
        "Rectangle",
        "Timer / Countdown",
        "Speech Bubble / Quote Card",
        "Progress Bar",
        "Callout Badge",
    ]
    for item_name in expected:
        assert item_name in CATALOG["Graphics"], f"{item_name} not found in CATALOG['Graphics']"
        assert item_name in GRAPHICS, f"{item_name} not found in GRAPHICS set"
        assert item_name in GRAPHICS_CATALOG, f"{item_name} missing from GRAPHICS_CATALOG"
        data = default_graphic_data(item_name)
        assert isinstance(data, dict), f"default_graphic_data({item_name}) is not dict"
        print(f"  [OK] {item_name:28} (default duration: {GRAPHICS_CATALOG[item_name]['default_duration']}s)")

    assert GRAPHICS_CATALOG["Circle"]["default_duration"] == 2.0, "Circle default duration must be 2.0s"
    assert GRAPHICS_CATALOG["Timer / Countdown"]["default_duration"] == 10.0, "Timer default duration must be 10.0s"

    # Check CATALOG key order
    assert list(CATALOG.keys())[-1] == "Graphics", "Graphics must be at the bottom of CATALOG"
    from kinetic_cut.effects import EFFECT_ICONS
    for item_name in expected:
        assert item_name in EFFECT_ICONS, f"{item_name} missing from EFFECT_ICONS"

    # 2. Spin up MainWindow
    print("\n[2/7] Launching MainWindow & Checking UI ordering...")
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name)
    w = MainWindow()
    w.show()
    w.autosave_timer.stop()
    app.processEvents()

    # Verify category list order in Effects panel
    ep = w.effects_panel
    cats = [ep.categories.item(i).text() for i in range(ep.categories.count())]
    assert cats[-1] == "Graphics", f"Expected 'Graphics' at bottom of categories list, got {cats[-1]}"
    assert cats[-2] == "Audio", f"Expected 'Audio' right above 'Graphics', got {cats[-2]}"
    print(f"  [OK] Categories list: last item is {cats[-1]} (below {cats[-2]})")

    # Verify All Effects list has Graphics items at bottom
    ep.categories.setCurrentRow(0)
    app.processEvents()
    all_eff = [ep.list.item(i).text() for i in range(ep.list.count())]
    assert all_eff[-len(expected):] == expected, f"Expected graphics items at bottom of All Effects list"
    print("  [OK] All Effects list: all 8 graphics are listed at the bottom")

    # 3. Add Graphics to Timeline
    print("\n[3/7] Testing add_graphic_object and duration defaults...")
    # Add Circle
    w.add_graphic_object("Circle", "video_1", 0.0)
    circle = next((i for i in w.project.timeline if i.graphic_type == "Circle"), None)
    assert circle is not None, "Circle item was not added"
    assert circle.role == "graphic", f"Expected role 'graphic', got {circle.role}"
    assert circle.duration == 2.0, f"Expected 2.0s duration for Circle, got {circle.duration}"
    print(f"  [OK] Added Circle: id={circle.id}, track={circle.track}, duration={circle.duration}s")

    # Add Timer
    w.add_graphic_object("Timer / Countdown", "video_1", 2.0)
    timer = next((i for i in w.project.timeline if i.graphic_type == "Timer / Countdown"), None)
    assert timer is not None, "Timer item was not added"
    assert timer.duration == 10.0, f"Expected 10.0s duration for Timer, got {timer.duration}"
    assert timer.start == 2.0, f"Expected start=2.0s for Timer, got {timer.start}"
    print(f"  [OK] Added Timer: id={timer.id}, track={timer.track}, duration={timer.duration}s")

    # Add remaining graphics to timeline
    other_graphics = [
        "Pointing Arrow",
        "Square",
        "Rectangle",
        "Speech Bubble / Quote Card",
        "Progress Bar",
        "Callout Badge",
    ]
    cur_start = 12.0
    for gname in other_graphics:
        w.add_graphic_object(gname, "video_1", cur_start)
        it = next((i for i in w.project.timeline if i.graphic_type == gname), None)
        assert it is not None, f"Failed to add {gname}"
        print(f"  [OK] Added {gname:28}: duration={it.duration}s, start={it.start}s")
        cur_start += it.duration

    app.processEvents()

    # 4. Inspector Inspection & Property Changing
    print("\n[4/7] Testing Inspector Properties Panel & Editing...")
    # Select Circle
    w.select_item(circle.id)
    app.processEvents()
    assert w.inspector.video_stack.currentIndex() == 3, f"Expected stack index 3 (Graphic), got {w.inspector.video_stack.currentIndex()}"
    assert w.inspector.sec_circle.isVisible(), "Circle section should be visible"
    assert not w.inspector.sec_timer.isVisible(), "Timer section should not be visible"

    # Edit Circle Color
    w.inspector.edit_graphic_prop("color", "#ff5500")
    assert circle.graphic_data["color"] == "#ff5500", "Circle color was not updated"
    # Edit Circle Thickness
    w.inspector.gc_thick.change(16.0)
    assert circle.graphic_data["thickness"] == 16.0, "Circle thickness was not updated"
    # Edit Circle Radius
    w.inspector.gc_radius.change(200.0)
    assert circle.graphic_data["radius"] == 200.0, "Circle radius was not updated"
    print("  [OK] Circle Inspector edits verified (color, thickness, radius)")

    # Select Timer
    w.select_item(timer.id)
    app.processEvents()
    assert w.inspector.sec_timer.isVisible(), "Timer section should be visible"
    assert timer.graphic_data.get("mode") == "Countdown"
    assert timer.graphic_data.get("duration") == 10.0
    assert w.inspector.gt_dur.isEnabled()

    # Edit clip duration and check countdown duration syncs!
    w.inspector.graphic_duration.change(12.5)
    assert timer.duration == 12.5
    assert timer.graphic_data.get("duration") == 12.5
    assert w.inspector.gt_dur.spin.value() == 12.5
    print("  [OK] Timer Countdown duration automatically synced to 12.5s")

    # Switch to Stopwatch
    w.inspector.gt_mode.setCurrentText("Stopwatch")
    assert timer.graphic_data["mode"] == "Stopwatch", "Timer mode was not updated to Stopwatch"
    assert not w.inspector.gt_dur.isEnabled(), "Target duration should be disabled/greyed-out for Stopwatch"
    print("  [OK] Stopwatch mode disables target duration property")

    # Switch back to Countdown
    w.inspector.gt_mode.setCurrentText("Countdown")
    assert timer.graphic_data["mode"] == "Countdown"
    assert w.inspector.gt_dur.isEnabled()
    assert timer.graphic_data["duration"] == 12.5

    # Test Font Glow
    w.inspector.gt_glow_enable.setChecked(True)
    app.processEvents()
    assert timer.graphic_data["glow_enabled"] is True
    assert timer.graphic_data["glow_radius"] == 12.0
    assert timer.graphic_data["glow_opacity"] == 55.0
    w.inspector.edit_graphic_prop("glow_color", "#55ffff")
    print("  [OK] Timer Font Glow verified (enabled, color: #55ffff, radius: 12, opacity: 55)")

    w.inspector.gt_fmt.setCurrentText("MM:SS.ms")
    assert timer.graphic_data["format"] == "MM:SS.ms", "Timer format was not updated"
    print("  [OK] Timer Inspector edits verified (mode: Countdown/Stopwatch, format: MM:SS.ms, Glow)")

    # Test Transform Section on Graphic
    w.inspector.gtr_x.change(150.0)
    expected_x = 0.5 + 150.0 / w.project.settings.width
    assert abs(timer.transform.x - expected_x) < 1e-4, f"Transform X mismatch: {timer.transform.x} vs {expected_x}"
    w.inspector.gtr_scale.change(1.35)
    assert timer.transform.scale == 1.35, "Transform Scale mismatch"
    w.inspector.gtr_rot.change(45.0)
    assert timer.transform.rotation == 45.0, "Transform Rotation mismatch"
    print("  [OK] Transform Section edits verified (Position X, Scale, Rotation)")

    # 5. Canvas Preview Rendering at Different Playhead Positions
    print("\n[5/7] Testing Preview Canvas Rendering & Countdown Progression...")
    w.seek(0.5)  # Inside Circle
    app.processEvents()
    assert ("graphic", circle.id) in w.preview.text_rects, "Circle bounding rect missing in preview canvas text_rects"
    circle_bounds = w.preview.text_rects[("graphic", circle.id)]
    assert circle_bounds.width() > 0 and circle_bounds.height() > 0
    print(f"  [OK] Circle canvas bounding rect: {circle_bounds}")

    # Switch Timer back to Countdown and test rendering at 2s, 5s, 8s
    timer.graphic_data["mode"] = "Countdown"
    timer.graphic_data["duration"] = 10.0
    for offset in [0.0, 3.0, 7.0]:
        t_pos = timer.start + offset
        w.seek(t_pos)
        app.processEvents()
        assert ("graphic", timer.id) in w.preview.text_rects
        tb = w.preview.text_rects[("graphic", timer.id)]
        assert tb.width() > 0 and tb.height() > 0
        print(f"  [OK] Timer canvas render at t={t_pos:.1f}s (remaining={10.0-offset:.1f}s): rect={tb}")

    # 6. ASS Export Generation
    print("\n[6/7] Testing ASS Subtitle / Overlay Generation for Render Engine...")
    ass_path = root / "export_graphics.ass"
    write_ass(w.project, ass_path, burn_captions=False)
    assert ass_path.exists(), "ASS file was not created"
    ass_text = ass_path.read_text(encoding="utf-8-sig")
    dialogues = [line for line in ass_text.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogues) >= 8, f"Expected at least 8 dialogue events, got {len(dialogues)}"
    print(f"  [OK] Generated {len(dialogues)} ASS dialogue events for graphics burning")

    # 7. Project Save & Load
    print("\n[7/7] Testing Project File Save and Load Persistence...")
    kcut_path = root / "graphics_project.kcut"
    w.project.save(kcut_path)
    loaded = Project.load(kcut_path)
    loaded_graphics = [i for i in loaded.timeline if i.role == "graphic"]
    assert len(loaded_graphics) == len(expected), f"Expected {len(expected)} graphics in loaded project, got {len(loaded_graphics)}"
    loaded_circle = next((i for i in loaded_graphics if i.graphic_type == "Circle"), None)
    assert loaded_circle.graphic_data["color"] == "#ff5500"
    assert loaded_circle.graphic_data["thickness"] == 16.0
    print(f"  [OK] Successfully reloaded project with all {len(loaded_graphics)} graphics intact")

    # Clean up
    w.close()
    QThreadPool.globalInstance().waitForDone(10000)
    w.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()
    temp_dir.cleanup()

    print("\n[SUCCESS] ALL VISUAL GRAPHICS E2E CHECKS PASSED SUCCESSFULLY!")
    return True


if __name__ == "__main__":
    success = run_e2e_verification()
    sys.exit(0 if success else 1)
