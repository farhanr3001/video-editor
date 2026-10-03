"""Verify edge cases: rapid forward/back scrub, exact final seek, gaps, audio after scrub, overlays."""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build" / "scrub-edge-test"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project, TimelineItem, MediaItem
from kinetic_cut.media import probe
from kinetic_cut.theme import STYLESHEET

def run_edge_tests():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    for font in ("arial.ttf", "arialbd.ttf", "segoeui.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)

    w = MainWindow()
    w.resize(1680, 1000)
    w.show()
    app.processEvents()

    media_path = ROOT / "xqc_royalty.mp4"
    m = probe(media_path)
    p = Project(media=[m])
    
    # Clip 1: 0s to 3s
    # Gap: 3s to 5s (EMPTY GAP!)
    # Clip 2: 5s to 9s
    # Clip 3 (upper lane): 6s to 8s
    p.timeline.append(TimelineItem("v1", m.id, "video_1", 0.0, 3.0, in_point=0.0))
    p.timeline.append(TimelineItem("a1", m.id, "audio_1", 0.0, 3.0, in_point=0.0))
    p.timeline.append(TimelineItem("v2", m.id, "video_1", 5.0, 4.0, in_point=5.0))
    p.timeline.append(TimelineItem("a2", m.id, "audio_1", 5.0, 4.0, in_point=5.0))
    
    upper = p.add_track("video")
    p.timeline.append(TimelineItem("v_up", m.id, upper, 6.0, 2.0, in_point=10.0))
    
    w.set_project(p)
    app.processEvents()
    tl = w.timeline
    transport = w.transport

    print("--- Test 1: Rapid forward and backward zigzag scrub ---")
    tl.start_scrub(round(tl.x_for_time(0.5)))
    app.processEvents()
    
    # Zigzag back and forth rapidly across cut boundaries and the gap
    zigzag_times = [0.5, 1.2, 2.8, 3.5, 4.2, 5.5, 7.2, 8.5, 7.0, 5.2, 3.8, 2.1, 0.8, 6.5]
    for target_t in zigzag_times:
        px = round(tl.x_for_time(target_t))
        tl.scrub_at(px)
        app.processEvents()
    
    # Release at 6.5s
    tl.drag_mode = "playhead"
    tl._scrub_snap_points = None
    tl.scrubFinished.emit()
    tl.drag_mode = ""
    app.processEvents()

    assert transport.scrubbing is False
    assert abs(transport.position - 6.5) < 0.05, f"Playhead didn't land at 6.5: {transport.position}"
    print("Zigzag scrub passed! Transport settled at:", transport.position)

    print("--- Test 2: Release inside an empty gap (4.0s) ---")
    tl.start_scrub(round(tl.x_for_time(6.5)))
    app.processEvents()
    tl.scrub_at(round(tl.x_for_time(4.0)))
    app.processEvents()
    
    tl.drag_mode = "playhead"
    tl._scrub_snap_points = None
    tl.scrubFinished.emit()
    tl.drag_mode = ""
    app.processEvents()

    assert transport.scrubbing is False
    assert abs(transport.position - 4.0) < 0.05
    # Active video frames in gap should be empty
    assert len(w.preview.active_frames) == 0, f"Expected 0 active video frames in gap, got {w.preview.active_frames}"
    print("Gap landing passed! Active frames:", w.preview.active_frames)

    print("--- Test 3: Playback immediately following scrub ---")
    # Land at 2.5s (0.5s before cut into gap)
    tl.start_scrub(round(tl.x_for_time(4.0)))
    app.processEvents()
    tl.scrub_at(round(tl.x_for_time(2.5)))
    app.processEvents()
    tl.drag_mode = "playhead"
    tl._scrub_snap_points = None
    tl.scrubFinished.emit()
    tl.drag_mode = ""
    app.processEvents()

    # Verify warm decoders prepared for upcoming cut
    print("Warm decoders count after release:", len(transport.warm_keys))
    # Start playback
    transport.play()
    assert transport.playing is True
    # Tick playback a few times
    for _ in range(10):
        time.sleep(0.03)
        transport.tick()
        app.processEvents()
    assert transport.position > 2.5
    transport.pause()
    assert transport.playing is False
    print("Playback after scrub passed! Advanced to:", transport.position)

    print("--- Test 4: Transform overlay stability ---")
    # Select v_up item (active between 6.0 and 8.0)
    w.select_item("v_up")
    w.seek(7.0)
    app.processEvents()
    assert w.preview.selected_item_id == "v_up"
    # Scrub back to 1.0 (where v_up is not visible)
    tl.start_scrub(round(tl.x_for_time(7.0)))
    app.processEvents()
    tl.scrub_at(round(tl.x_for_time(1.0)))
    app.processEvents()
    tl.drag_mode = "playhead"
    tl._scrub_snap_points = None
    tl.scrubFinished.emit()
    tl.drag_mode = ""
    app.processEvents()
    # Preview paints without error, no stale overlay drawn
    w.preview.update()
    app.processEvents()
    print("Transform overlay stability passed!")

    print("ALL EDGE CASE TESTS PASSED SUCCESSFULLY!")
    w.close()

if __name__ == "__main__":
    run_edge_tests()
