"""Test real scrub performance on GTA.kcut with integrated production changes."""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build" / "gta-scrub-real-test"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project
from kinetic_cut.theme import STYLESHEET

def run_test():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    for font in ("arial.ttf", "arialbd.ttf", "segoeui.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)

    w = MainWindow()
    w.resize(1680, 1000)
    w.show()
    app.processEvents()

    p = Project.load("GTA.kcut")
    w.set_project(p)
    app.processEvents()

    tl = w.timeline
    transport = w.transport

    # Track decoders created/retired
    orig_create = transport.create_decoder
    orig_retire = transport.retire_decoder
    created_count = [0]
    retired_count = [0]

    def count_create(*args, **kwargs):
        created_count[0] += 1
        return orig_create(*args, **kwargs)

    def count_retire(*args, **kwargs):
        retired_count[0] += 1
        return orig_retire(*args, **kwargs)

    transport.create_decoder = count_create
    transport.retire_decoder = count_retire

    # Region with Remove Person Background: ~51.5s to ~71.5s
    start_time = 51.5
    end_time = 71.5
    start_x = round(tl.x_for_time(start_time))
    end_x = round(tl.x_for_time(end_time))
    
    steps = 100
    points = [start_x + int((end_x - start_x) * (i / steps)) for i in range(steps)]

    # Simulate mouse press to start scrub
    tl.start_scrub(start_x)
    app.processEvents()

    created_before_drag = created_count[0]
    retired_before_drag = retired_count[0]

    t0 = time.perf_counter()
    latencies = []
    for px in points:
        t_event = time.perf_counter()
        tl.scrub_at(px)
        app.processEvents()
        latencies.append(time.perf_counter() - t_event)
    total_drag_time = time.perf_counter() - t0

    created_during_drag = created_count[0] - created_before_drag
    retired_during_drag = retired_count[0] - retired_before_drag

    # Simulate mouse release to finish scrub
    t_rel = time.perf_counter()
    tl.drag_mode = "playhead"
    if tl.drag_mode == "playhead":
        tl._scrub_snap_points = None
        tl.scrubFinished.emit()
    tl.drag_mode = ""
    app.processEvents()
    release_latency = time.perf_counter() - t_rel

    avg_ms = sum(latencies) / len(latencies) * 1000
    max_ms = max(latencies) * 1000
    min_ms = min(latencies) * 1000
    total_ms = total_drag_time * 1000

    print("=== REAL SCRUB PERFORMANCE TEST RESULTS (GTA.kcut Layer 3 Person Background Remover) ===")
    print(f"Events simulated: {steps}")
    print(f"Total scrub time: {total_ms:.1f} ms")
    print(f"Average latency per event: {avg_ms:.2f} ms")
    print(f"Min / Max event latency: {min_ms:.2f} ms / {max_ms:.2f} ms")
    print(f"Release latency: {release_latency * 1000:.2f} ms")
    print(f"Decoders created during drag: {created_during_drag}")
    print(f"Decoders retired during drag: {retired_during_drag}")
    print(f"Final playhead position: {transport.position:.3f} s (expected ~{end_time:.3f} s)")
    print(f"Transport scrubbing state: {transport.scrubbing} (expected False)")
    print(f"Warm decoders restored: {len(transport.warm_keys)}")

    assert transport.scrubbing is False, "Transport still in scrubbing mode after release!"
    assert avg_ms < 35.0, f"Average event latency too high: {avg_ms:.2f} ms"
    print("ALL PERFORMANCE AND STATE ASSERTIONS PASSED!")
    w.close()

if __name__ == "__main__":
    run_test()
