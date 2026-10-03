"""Automated test for new features:
1. DaVinci Resolve trim & roll cursors (hover and drag across any layer type)
2. Ctrl+A timeline select all (across all tracks/layers)
3. Multi-selection effect drag-and-drop
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt, QPointF, QPoint
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QApplication

from kinetic_cut.model import Project, TimelineItem, MediaItem
from kinetic_cut.ui import MainWindow

def test_cursors():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    p = Project()
    p.video_tracks = ["video_1", "video_2"]
    p.audio_tracks = ["audio_1"]
    
    m_vid = MediaItem(id="m1", path="video.mp4", name="video.mp4", kind="video", duration=10.0, width=1920, height=1080)
    m_aud = MediaItem(id="m2", path="audio.mp3", name="audio.mp3", kind="audio", duration=10.0, has_audio=True)
    p.media = [m_vid, m_aud]
    
    # 2 adjacent video clips on video_1
    v1 = TimelineItem(id="v1", media_id="m1", track="video_1", start=0.0, duration=5.0)
    v2 = TimelineItem(id="v2", media_id="m1", track="video_1", start=5.0, duration=5.0)
    # 1 clip on video_2
    v3 = TimelineItem(id="v3", media_id="m1", track="video_2", start=2.0, duration=4.0)
    # 1 clip on audio_1
    a1 = TimelineItem(id="a1", media_id="m2", track="audio_1", start=0.0, duration=8.0)
    p.timeline = [v1, v2, v3, a1]
    
    w.set_project(p)
    t = w.timeline
    t.resize(1000, 600)
    
    # 1. Test cursor generation
    c_left = t._trim_cursor("left")
    c_right = t._trim_cursor("right")
    c_roll = t._roll_cursor()
    assert c_left is not None and not c_left.pixmap().isNull()
    assert c_right is not None and not c_right.pixmap().isNull()
    assert c_roll is not None and not c_roll.pixmap().isNull()
    print("[PASS] Custom cursors generate valid pixmaps")
    
    # 2. Test hover on left edge of video clip
    r_v1 = t.item_rect(v1)
    # Left edge hover (x = r_v1.left() + 2)
    from PySide6.QtGui import QMouseEvent
    ev_hover_left = QMouseEvent(QMouseEvent.MouseMove, QPointF(r_v1.left() + 2, r_v1.center().y()), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    t.mouseMoveEvent(ev_hover_left)
    assert t.viewport().cursor().pixmap().toImage() == c_left.pixmap().toImage(), "Hover left did not show left trim cursor"
    
    # Right edge hover of v3 (isolated video clip on video_2)
    r_v3 = t.item_rect(v3)
    ev_hover_right = QMouseEvent(QMouseEvent.MouseMove, QPointF(r_v3.right() - 2, r_v3.center().y()), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    t.mouseMoveEvent(ev_hover_right)
    assert t.viewport().cursor().pixmap().toImage() == c_right.pixmap().toImage(), "Hover right did not show right trim cursor"
    
    # Roll hover between v1 and v2
    roll_pos = QPointF(t.x_for_time(5.0), r_v1.center().y())
    ev_hover_roll = QMouseEvent(QMouseEvent.MouseMove, roll_pos, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    t.mouseMoveEvent(ev_hover_roll)
    assert t.viewport().cursor().pixmap().toImage() == c_roll.pixmap().toImage(), "Roll hover did not show roll cursor"
    
    # Hover on audio layer edge (a1)
    r_a1 = t.item_rect(a1)
    ev_hover_audio_left = QMouseEvent(QMouseEvent.MouseMove, QPointF(r_a1.left() + 2, r_a1.center().y()), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    t.mouseMoveEvent(ev_hover_audio_left)
    assert t.viewport().cursor().pixmap().toImage() == c_left.pixmap().toImage(), "Audio hover left did not show left trim cursor"
    print("[PASS] Hover cursors work across all layer types")
    
    # 3. Test active dragging cursor
    t.drag_mode = "trim_left"
    t.snapshots = {v1.id: v1}
    t.selected_id = v1.id
    ev_drag = QMouseEvent(QMouseEvent.MouseMove, QPointF(200, 200), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    t.mouseMoveEvent(ev_drag)
    assert t.viewport().cursor().pixmap().toImage() == c_left.pixmap().toImage(), "Drag trim_left did not maintain left cursor"
    
    t.drag_mode = "trim_right"
    t.mouseMoveEvent(ev_drag)
    assert t.viewport().cursor().pixmap().toImage() == c_right.pixmap().toImage(), "Drag trim_right did not maintain right cursor"
    
    t.drag_mode = "roll"
    t.roll_boundary = 5.0
    from kinetic_cut.timeline_gestures import roll_snapshots
    t.roll_members = roll_snapshots(w.project, v1, v2, False)
    t.mouseMoveEvent(ev_drag)
    assert t.viewport().cursor().pixmap().toImage() == c_roll.pixmap().toImage(), "Drag roll did not maintain roll cursor"
    
    t.cancel_drag()
    print("[PASS] Active drag maintains custom cursors")
    w.close()

def test_ctrl_a_select_all():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    p = Project()
    p.video_tracks = ["video_1", "video_2"]
    m1 = MediaItem(id="m1", path="dummy.mp4", name="dummy.mp4", kind="video", duration=10.0)
    p.media = [m1]
    v1 = TimelineItem(id="v1", media_id="m1", track="video_1", start=0.0, duration=5.0)
    v2 = TimelineItem(id="v2", media_id="m1", track="video_2", start=2.0, duration=4.0)
    a1 = TimelineItem(id="a1", media_id="m1", track="audio_1", start=1.0, duration=6.0)
    p.timeline = [v1, v2, a1]
    w.set_project(p)
    
    # Deselect all
    w.timeline.select_ids(set())
    assert len(w.timeline.selected_ids) == 0
    
    # 1. Via keyPressEvent on TimelineWidget
    ev = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_A, Qt.ControlModifier)
    w.timeline.keyPressEvent(ev)
    assert w.timeline.selected_ids == {"v1", "v2", "a1"}, f"Timeline keyPressEvent failed: {w.timeline.selected_ids}"
    
    # 2. Via window.select_all() (Edit menu action)
    w.timeline.select_ids(set())
    w.select_all()
    assert w.timeline.selected_ids == {"v1", "v2", "a1"}, f"Window select_all failed: {w.timeline.selected_ids}"
    print("[PASS] Ctrl+A Select All selects all clips across all tracks")
    w.close()

def test_multi_selection_effect_drop():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    p = Project()
    p.video_tracks = ["video_1", "video_2"]
    p.audio_tracks = ["audio_1"]
    
    m_vid = MediaItem(id="m1", path="video.mp4", name="video.mp4", kind="video", duration=10.0, width=1920, height=1080)
    m_aud = MediaItem(id="m2", path="audio.mp3", name="audio.mp3", kind="audio", duration=10.0, has_audio=True)
    p.media = [m_vid, m_aud]
    
    v1 = TimelineItem(id="v1", media_id="m1", track="video_1", start=0.0, duration=5.0)
    v2 = TimelineItem(id="v2", media_id="m1", track="video_2", start=1.0, duration=4.0)
    v3 = TimelineItem(id="v3", media_id="m1", track="video_2", start=6.0, duration=3.0)
    a1 = TimelineItem(id="a1", media_id="m2", track="audio_1", start=0.0, duration=8.0)
    p.timeline = [v1, v2, v3, a1]
    w.set_project(p)
    
    # Case 1: Multiple video clips selected (v1 and v2), drop "Gaussian Blur" on v1
    w.timeline.select_ids({"v1", "v2"}, primary="v1")
    w.apply_effect_to("Gaussian Blur", "v1")
    
    assert any(e["name"] == "Gaussian Blur" for e in v1.effects), "v1 missing Gaussian Blur"
    assert any(e["name"] == "Gaussian Blur" for e in v2.effects), "v2 missing Gaussian Blur"
    assert not any(e["name"] == "Gaussian Blur" for e in v3.effects), "v3 should not have Gaussian Blur"
    assert not any(e["name"] == "Gaussian Blur" for e in a1.effects), "a1 should not have Gaussian Blur"
    print("[PASS] Effect applied to all selected video clips")
    
    # Case 2: Mixed selection (v3 and a1), drop "Sepia" on v3
    w.timeline.select_ids({"v3", "a1"}, primary="v3")
    w.apply_effect_to("Sepia", "v3")
    assert any(e["name"] == "Sepia" for e in v3.effects), "v3 missing Sepia"
    assert not any(e["name"] == "Sepia" for e in a1.effects), "a1 should safely ignore video effect"
    print("[PASS] Incompatible clips in multi-selection safely skipped")
    
    # Case 3: Drop audio effect "Noise Clean" on selection {"a1", "v1"}
    w.timeline.select_ids({"a1", "v1"}, primary="a1")
    w.apply_effect_to("Noise Clean", "a1")
    assert any(e["name"] == "Noise Clean" for e in a1.effects), "a1 missing Noise Clean"
    assert not any(e["name"] == "Noise Clean" for e in v1.effects), "v1 should safely ignore audio effect"
    print("[PASS] Audio effect applies to selected audio clips in mixed selection")
    
    # Case 4: Drop on an unselected clip (e.g. drop "Light Boost" on v3 while v1 is selected)
    w.timeline.select_ids({"v1"}, primary="v1")
    w.apply_effect_to("Light Boost", "v3")
    assert w.timeline.selected_ids == {"v3"}, "Dropping on unselected clip should select that clip"
    assert any(e["name"] == "Light Boost" for e in v3.effects), "v3 missing Light Boost"
    print("[PASS] Drop on unselected clip selects only that clip and applies effect")
    w.close()

if __name__ == "__main__":
    test_cursors()
    test_ctrl_a_select_all()
    test_multi_selection_effect_drop()
    print("\nALL FEATURE TESTS PASSED SUCCESSFULLY!")
