"""Benchmark GTA.kcut scrubbing before and after optimization."""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build" / "gta-scrub-compare"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project
from kinetic_cut.theme import STYLESHEET

def run_comparison():
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

    # Region with Remove Person Background: ~51s to ~72s
    start_time = 51.5
    end_time = 71.5
    start_x = round(tl.x_for_time(start_time))
    end_x = round(tl.x_for_time(end_time))
    
    # 100 rapid scrub events across the person background removal region
    steps = 100
    points = [start_x + int((end_x - start_x) * (i / steps)) for i in range(steps)]

    # --- TEST 1: Baseline behavior ---
    tl.start_scrub(start_x)
    app.processEvents()

    t0 = time.perf_counter()
    baseline_latencies = []
    for px in points:
        t_start = time.perf_counter()
        tl.scrub_at(px)
        app.processEvents()
        baseline_latencies.append(time.perf_counter() - t_start)
    t_baseline = time.perf_counter() - t0
    tl.drag_mode = ""
    app.processEvents()

    # --- TEST 2: With Scrub Optimization ---
    # Implement prototype scrub logic
    transport.scrubbing = False
    transport._last_scrub_sync = 0.0
    transport._pending_scrub_pos = None

    orig_seek = transport.seek
    orig_sync = transport.sync

    def opt_sync(force=False):
        if transport.scrubbing:
            # During scrub: only sync active visible video decoders, skip warm-up churn!
            p = transport.window.project
            t = transport.position
            preview = transport.window.preview
            active = set()
            for item in p.timeline:
                if item.muted or not item.start <= t < item.start + item.duration:
                    continue
                state = p.track_states.get(item.track, {})
                if not state.get("visible", True):
                    continue
                media = p.media_by_id(item.media_id)
                if not media or media.kind != "video":
                    continue
                if item.track not in p.video_tracks:
                    continue
                key = (media.id, round(item.in_point - item.start * item.speed, 4), item.speed, "video")
                active.add(key)
                desired = round(item.source_time(t) * 1000)
                created = key not in transport.decoders
                if created:
                    transport.create_decoder(key, media, True, "")
                player, output, _ = transport.decoders[key]
                preview.active_frames[item.id] = key
                output.setVolume(0.0)
                if created or abs(player.position() - desired) > 40:
                    player.setPosition(desired)
                if created:
                    player.play()
                elif player.playbackState() == player.PlaybackState.PlayingState:
                    player.pause()
            for key in list(transport.decoders):
                if key not in active and key not in transport.warm_keys:
                    transport.retire_decoder(key)
            preview.update()
            return
        return orig_sync(force)

    transport.sync = opt_sync

    def opt_scrub(pos):
        transport.scrubbing = True
        transport.position = max(0.0, pos)
        transport.origin = transport.position
        transport.started = time.monotonic()
        now = time.monotonic()
        if now - transport._last_scrub_sync >= 0.025:
            transport._last_scrub_sync = now
            transport.sync(True)
            transport.changed.emit(transport.position)
        else:
            transport._pending_scrub_pos = pos

    transport.scrub = opt_scrub

    def opt_finish_scrub():
        transport.scrubbing = False
        transport._pending_scrub_pos = None
        transport.seek(transport.position)

    transport.finish_scrub = opt_finish_scrub

    # Run optimized scrub
    tl.drag_mode = "playhead"
    tl.scrub_x = start_x
    app.processEvents()

    t0 = time.perf_counter()
    opt_latencies = []
    for px in points:
        t_start = time.perf_counter()
        tl.scrub_x = px
        moment = max(0, tl.time_for_x(px))
        tl.project.playhead = moment
        transport.scrub(moment)
        tl.viewport().update()
        app.processEvents()
        opt_latencies.append(time.perf_counter() - t_start)
    t_opt = time.perf_counter() - t0

    transport.finish_scrub()
    tl.drag_mode = ""
    app.processEvents()

    print("=== GTA SCRUB PERFORMANCE COMPARISON (Webcam with Person Background Remover) ===")
    print(f"Total events: {steps}")
    print(f"Baseline total time: {t_baseline * 1000:.1f} ms | Avg per event: {sum(baseline_latencies)/len(baseline_latencies)*1000:.2f} ms | Max: {max(baseline_latencies)*1000:.2f} ms")
    print(f"Optimized total time: {t_opt * 1000:.1f} ms | Avg per event: {sum(opt_latencies)/len(opt_latencies)*1000:.2f} ms | Max: {max(opt_latencies)*1000:.2f} ms")
    print(f"Speedup: {t_baseline / t_opt:.2f}x faster!")

    w.close()

if __name__ == "__main__":
    run_comparison()
