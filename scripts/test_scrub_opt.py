"""Test optimized scrubbing logic and measure latency and decoder count."""
import os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build" / "scrub-test-home"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project, TimelineItem, Caption
from kinetic_cut.media import probe
from kinetic_cut.theme import STYLESHEET

def setup_project():
    media_path = ROOT / "xqc_royalty.mp4"
    m = probe(media_path)
    p = Project(media=[m])
    t = 0.0
    for i in range(12):
        dur = 2.0
        v = TimelineItem(f"v_{i}", m.id, "video_1", t, dur, in_point=i * 1.5, group_id=f"g_{i}")
        a = TimelineItem(f"a_{i}", m.id, "audio_1", t, dur, in_point=i * 1.5, group_id=f"g_{i}")
        p.timeline.extend([v, a])
        t += dur
    upper_track = p.add_track("video")
    p.timeline.append(TimelineItem("overlay", m.id, upper_track, 2.0, 8.0, in_point=5.0))
    for i in range(10):
        p.captions.append(Caption(f"c_{i}", i * 2.0, i * 2.0 + 1.8, f"Caption text {i}"))
    return p

def run_experiment():
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

    # Test with prototype optimization:
    # 1. Flag transport.scrubbing
    transport.scrubbing = False
    transport._pending_scrub_pos = None
    transport._last_scrub_sync = 0.0

    orig_sync = transport.sync
    def optimized_sync(force=False):
        if transport.scrubbing:
            # During interactive scrubbing:
            # - Only sync active visible video decoders
            # - Skip warm candidate discovery and decoder creation churn!
            p = transport.window.project
            t = transport.position
            preview = transport.window.preview
            active = set()
            now = time.monotonic()
            for item in p.timeline:
                if item.muted or not item.start <= t < item.start + item.duration:
                    continue
                state = p.track_states.get(item.track, {})
                if not state.get("visible", True):
                    continue
                media = p.media_by_id(item.media_id)
                if not media or media.kind != "video":
                    continue
                video = item.track in p.video_tracks
                if not video:
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
                if created or abs(player.position() - desired) > 30:
                    player.setPosition(desired)
                if created:
                    player.play()
                elif player.playbackState() == player.PlaybackState.PlayingState:
                    player.pause()
            # Retire decoders that are no longer active
            for key in list(transport.decoders):
                if key not in active and key not in transport.warm_keys:
                    transport.retire_decoder(key)
            preview.update()
            return
        return orig_sync(force)

    transport.sync = optimized_sync

    def optimized_scrub(pos):
        transport.scrubbing = True
        transport.position = max(0.0, pos)
        transport.origin = transport.position
        transport.started = time.monotonic()
        now = time.monotonic()
        # Throttle decoder seeks to at most once per 25ms (~40 FPS)
        if now - transport._last_scrub_sync >= 0.025:
            transport._last_scrub_sync = now
            transport.sync(True)
            transport.changed.emit(transport.position)
        else:
            transport._pending_scrub_pos = pos

    transport.scrub = optimized_scrub

    def finish_scrub():
        transport.scrubbing = False
        transport._pending_scrub_pos = None
        transport.seek(transport.position)

    transport.finish_scrub = finish_scrub

    # Track decoders
    decoders_created = 0
    orig_create = transport.create_decoder
    def tracked_create(*args):
        nonlocal decoders_created
        decoders_created += 1
        return orig_create(*args)
    transport.create_decoder = tracked_create

    # Simulate scrubbing
    start_x = 200
    tl.start_scrub(start_x)
    app.processEvents()

    points = [start_x + int(i * 6) for i in range(100)] + [800 - int(i * 8) for i in range(50)]
    
    t0 = time.perf_counter()
    event_durations = []

    for px in points:
        t_event = time.perf_counter()
        tl.scrub_x = px
        moment = max(0, tl.time_for_x(px))
        tl.project.playhead = moment
        transport.scrub(moment)
        tl.viewport().update()
        app.processEvents()
        event_durations.append(time.perf_counter() - t_event)

    total_time = time.perf_counter() - t0

    # Finish scrub
    transport.finish_scrub()
    tl.drag_mode = ""
    app.processEvents()

    avg_ms = (sum(event_durations) / len(event_durations)) * 1000
    max_ms = max(event_durations) * 1000

    print("=== OPTIMIZED SCRUB RESULTS ===")
    print(f"Total simulated events: {len(points)}")
    print(f"Total scrub time: {total_time * 1000:.1f} ms")
    print(f"Average time per scrub event: {avg_ms:.2f} ms")
    print(f"Max single event latency: {max_ms:.2f} ms")
    print(f"Decoders created: {decoders_created}")
    print(f"Final playhead position: {transport.position:.3f} s")
    print(f"Final timeline playhead: {tl.project.playhead:.3f} s")

    w.close()

if __name__ == "__main__":
    run_experiment()
