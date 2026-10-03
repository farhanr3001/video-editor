"""Benchmark scrubbing specifically on GTA.kcut."""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build" / "gta-scrub-home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project
from kinetic_cut.theme import STYLESHEET

def run_gta_benchmark():
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

    print("Loaded GTA.kcut:")
    print(f"Timeline items: {len(p.timeline)}")
    print(f"Captions: {len(p.captions)}")
    print(f"Video tracks: {p.video_tracks}")
    print(f"Duration: {p.duration:.2f} s")

    # Measure 60 scrub events across 50s to 75s (the exact region with Remove Person Background on video_3)
    start_time = 51.0
    end_time = 72.0
    
    # Calculate pixel positions for start and end
    start_x = round(tl.x_for_time(start_time))
    end_x = round(tl.x_for_time(end_time))
    
    tl.start_scrub(start_x)
    app.processEvents()

    steps = 60
    points = [start_x + int((end_x - start_x) * (i / steps)) for i in range(steps)]

    t0 = time.perf_counter()
    event_durations = []
    
    for px in points:
        t_event = time.perf_counter()
        tl.scrub_at(px)
        app.processEvents()
        event_durations.append(time.perf_counter() - t_event)

    total_time = time.perf_counter() - t0

    tl.drag_mode = ""
    app.processEvents()

    avg_ms = (sum(event_durations) / len(event_durations)) * 1000
    max_ms = max(event_durations) * 1000

    print("=== GTA SCRUB BENCHMARK RESULTS (Webcam Person Background Area) ===")
    print(f"Total scrub events: {len(points)}")
    print(f"Total time: {total_time * 1000:.1f} ms")
    print(f"Average time per scrub event: {avg_ms:.2f} ms")
    print(f"Max single event latency: {max_ms:.2f} ms")
    print(f"Approximate scrub frame rate: {1000 / avg_ms:.1f} FPS")

    w.close()

if __name__ == "__main__":
    run_gta_benchmark()
