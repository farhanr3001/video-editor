"""Benchmark and diagnostic tool for timeline playhead dragging/scrubbing performance."""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build" / "scrub-benchmark-home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtGui import QFontDatabase
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project, TimelineItem, MediaItem, Caption
from kinetic_cut.media import probe
from kinetic_cut.theme import STYLESHEET

def setup_project():
    # Use real media if available, or generate a realistic multi-clip project
    media_path = ROOT / "xqc_royalty.mp4"
    if not media_path.exists():
        raise FileNotFoundError(f"Media not found: {media_path}")
    m = probe(media_path)
    p = Project(media=[m])
    # Build a timeline with multiple cuts across video and audio, plus captions and an upper track
    t = 0.0
    for i in range(12):
        dur = 2.0
        v = TimelineItem(f"v_{i}", m.id, "video_1", t, dur, in_point=i * 1.5, group_id=f"g_{i}")
        a = TimelineItem(f"a_{i}", m.id, "audio_1", t, dur, in_point=i * 1.5, group_id=f"g_{i}")
        p.timeline.extend([v, a])
        t += dur
    # Upper layer overlay
    upper_track = p.add_track("video")
    p.timeline.append(TimelineItem("overlay", m.id, upper_track, 2.0, 8.0, in_point=5.0))
    # Captions
    for i in range(10):
        p.captions.append(Caption(f"c_{i}", i * 2.0, i * 2.0 + 1.8, f"Caption text {i}"))
    return p

def run_benchmark():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    for font in ("arial.ttf", "arialbd.ttf", "segoeui.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + font)

    w = MainWindow()
    w.resize(1680, 1000)
    w.show()
    app.processEvents()

    p = setup_project()
    w.set_project(p)
    app.processEvents()

    tl = w.timeline
    transport = w.transport

    # Counters for diagnostics
    stats = {
        "scrub_calls": 0,
        "transport_seeks": 0,
        "sync_calls": 0,
        "decoder_set_positions": 0,
        "decoders_created": 0,
        "decoders_retired": 0,
        "preview_updates": 0,
        "timeline_updates": 0,
    }

    orig_scrub_at = tl.scrub_at
    def tracked_scrub_at(x):
        stats["scrub_calls"] += 1
        return orig_scrub_at(x)
    tl.scrub_at = tracked_scrub_at

    orig_transport_seek = transport.seek
    def tracked_transport_seek(pos):
        stats["transport_seeks"] += 1
        return orig_transport_seek(pos)
    transport.seek = tracked_transport_seek

    orig_sync = transport.sync
    def tracked_sync(force=False):
        stats["sync_calls"] += 1
        return orig_sync(force)
    transport.sync = tracked_sync

    orig_create_decoder = transport.create_decoder
    def tracked_create_decoder(key, media, video, audio_path):
        stats["decoders_created"] += 1
        return orig_create_decoder(key, media, video, audio_path)
    transport.create_decoder = tracked_create_decoder

    orig_retire_decoder = transport.retire_decoder
    def tracked_retire_decoder(key):
        stats["decoders_retired"] += 1
        return orig_retire_decoder(key)
    transport.retire_decoder = tracked_retire_decoder

    # Simulate user initiating scrub at x=200
    start_x = 200
    tl.start_scrub(start_x)
    app.processEvents()

    # Simulate 100 rapid mouse move events across the timeline (from x=200 to x=800 and back to x=400)
    points = [start_x + int(i * 6) for i in range(100)] + [800 - int(i * 8) for i in range(50)]
    
    t0 = time.perf_counter()
    event_durations = []
    
    for px in points:
        t_event_start = time.perf_counter()
        tl.scrub_at(px)
        app.processEvents()
        event_durations.append(time.perf_counter() - t_event_start)
    
    total_time = time.perf_counter() - t0

    # Simulate mouse release
    tl.drag_mode = ""
    tl.snap_guide = None
    tl.viewport().update()
    app.processEvents()

    avg_event_ms = (sum(event_durations) / len(event_durations)) * 1000
    max_event_ms = max(event_durations) * 1000

    print("=== SCRUB BENCHMARK RESULTS ===")
    print(f"Total simulated scrub events: {len(points)}")
    print(f"Total scrub time: {total_time * 1000:.1f} ms")
    print(f"Average time per scrub event: {avg_event_ms:.2f} ms")
    print(f"Max single event latency: {max_event_ms:.2f} ms")
    print(f"Scrub calls: {stats['scrub_calls']}")
    print(f"Transport seeks: {stats['transport_seeks']}")
    print(f"Transport sync calls: {stats['sync_calls']}")
    print(f"Decoders created: {stats['decoders_created']}")
    print(f"Decoders retired: {stats['decoders_retired']}")
    print(f"Current active decoders: {len(transport.decoders)}")
    
    w.close()
    return stats, avg_event_ms, max_event_ms

if __name__ == "__main__":
    run_benchmark()
