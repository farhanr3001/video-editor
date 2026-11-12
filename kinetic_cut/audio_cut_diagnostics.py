"""Disposable native audio-cut/seek checks. Never uses owner media or settings."""
import json
import os
import sys
import time
import wave
from pathlib import Path


def run(output):
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ.update(KINETIC_CUT_HOME=str(out/"home"), QT_QPA_PLATFORM="windows",
                      QSG_RHI_BACKEND="d3d11")
    import numpy as np
    from PySide6.QtCore import QEventLoop, QTimer, Qt
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtWidgets import QApplication
    from .model import MediaItem, Project, ProjectSettings, TimelineItem
    from .process import run as process

    # Optional source-only baseline uses the previously accepted frozen class.
    baseline = os.environ.get("KINETIC_AUDIO_BASELINE_EXE")
    if baseline:
        from PyInstaller.archive.readers import CArchiveReader
        from . import transport
        archive = CArchiveReader(baseline)
        pyz = archive.open_embedded_archive(next(n for n, v in archive.toc.items() if v[-1] == "z"))
        exec(pyz.extract("kinetic_cut.transport"), transport.__dict__)

    from .ui import MainWindow
    app = QApplication([])
    app.setProperty("kineticTestDiscardUnsaved", True)
    app.setQuitOnLastWindowClosed(False)
    report = dict(frozen=bool(getattr(sys, "frozen", False)), baseline=bool(baseline),
                  checks=[], cases=[], captured_buffers=[], speaker_loopback=False)

    def save():
        (out/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def check(name, passed):
        report["checks"].append(dict(name=name, passed=bool(passed)))
        save()
        if not passed and not baseline:
            raise AssertionError(name)

    def wait(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def until(condition, seconds=6):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            if condition():
                return True
            wait(5)
        return False

    rate = 48000
    times = np.arange(rate*3)/rate
    signal = .25*np.sin(2*np.pi*220*times)
    removed = (times >= .9) & (times < 1.04)
    signal[removed] = .65*np.sin(2*np.pi*1300*times[removed])
    pcm = np.repeat((signal*32767).astype("<i2")[:, None], 2, axis=1)
    source = out/"marked-source.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(pcm.tobytes())
    compressed = out/"marked-source.m4a"
    process(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-c:a", "aac",
             "-b:a", "192k", str(compressed)], check=True, capture_output=True)

    window = MainWindow()
    window.autosave_timer.stop()
    window.preview_quality.request = lambda: None
    window.resize(1200, 800)
    window.show()
    transport = window.transport
    transport.set_monitor_gain(0)  # Decode normally without playing test tones to the owner.
    original_create = transport.create_decoder
    records = []
    case_name = ""

    def capture(key, buffer):
        decoder = transport.decoders.get(key)
        if not decoder or not transport.playing or key in transport.warm_keys or not buffer.isValid():
            return
        player, output, _ = decoder
        if output.isMuted() or not output.property("monitor_base_gain"):
            return
        records.append(dict(case=case_name, key=repr(key), source_us=buffer.startTime(),
                            duration_us=buffer.duration(), timeline=transport.position,
                            player_ms=player.position()))

    def create(key, media, video, audio_path):
        result = original_create(key, media, video, audio_path)
        if not video:
            player = transport.decoders[key][0]
            player.audioBufferOutput().audioBufferReceived.connect(lambda buffer: capture(key, buffer), Qt.QueuedConnection)
        return result

    transport.create_decoder = create
    for path in (source, compressed):
        media = MediaItem("m", str(path), "audio", path.name, 3, has_audio=True)
        project = Project(media=[media], timeline=[TimelineItem("left", "m", "audio_1", 0, .9),
                          TimelineItem("right", "m", "audio_1", 1.04, 1.96, in_point=1.04)])
        window.set_project(project)
        for repetition in range(3):
            for start in (.82, 1.065, 1.30, 1.045):
                case_name = f"{path.suffix}-{repetition}-{start}"
                transport.pause()
                transport.seek(start)
                check(case_name+" source loaded", until(lambda: all(d[0].mediaStatus() != QMediaPlayer.LoadingMedia
                      for d in transport.decoders.values()) and not getattr(transport, "_loading_audio_seeks", {})))
                wait(35)
                before = len(records)
                transport.play()
                check(case_name+" advances", until(lambda: transport.position >= max(1.35, start+.22)))
                transport.pause()
                rows = records[before:]
                right = [r for r in rows if r["timeline"] >= 1.055]
                wrong = [r for r in right if r["source_us"]+r["duration_us"] < 1_038_000]
                report["cases"].append(dict(name=case_name, buffers=len(rows), right_buffers=len(right),
                    stale_buffers=len(wrong), first_right_us=right[0]["source_us"] if right else None))
                check(case_name+" receives real decoded audio", bool(right))
                check(case_name+" no removed audio after right clip activation", not wrong)

        # Rapid realistic paused seek/play/pause must not restart a stale load.
        for start in (1.08, .95, 1.12, .88, 1.06):
            transport.seek(start)
            transport.play()
            wait(30)
            transport.pause()
        transport.seek(.96)
        transport.play()
        wait(25)
        check(path.suffix+" gap seek remains silent", all(output.isMuted() or output.volume() == 0
              for _, output, sink in transport.decoders.values() if sink is None))
        transport.pause()

    transport.pause()
    report["captured_buffers"] = records
    check("no audio preparation for plain trims", not transport.audio_pending and not transport.audio_cache)
    check("decoder count stays bounded", len(transport.decoders) <= 3)

    # Deliberately distinguish the two retained intervals visually. Reusing an
    # unpositioned player would otherwise leave a plausible-looking old frame.
    video = out/"marked-video.mp4"
    process(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=blue:s=640x360:r=60:d=3",
             "-vf", "drawbox=color=red:t=fill:enable='between(t,0.9,1.0399)',drawbox=color=green:t=fill:enable='gte(t,1.04)'",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
    media = MediaItem("video", str(video), "video", video.name, 3, 640, 360, 60)
    project = Project(settings=ProjectSettings(width=640, height=360, fps=60), media=[media], timeline=[
        TimelineItem("left-video", "video", "video_1", 0, .9),
        TimelineItem("right-video", "video", "video_1", 1.04, 1.96, in_point=1.04)])
    window.set_project(project)
    window.seek(.85)
    gpu = window.preview.gpu

    def colour_matches(channel):
        image = gpu.view.grabWindow()
        if image.isNull():
            return False
        colour = image.pixelColor(image.width()//2, image.height()//2)
        return colour.blue() > 200 if channel == "blue" else colour.green() > 90 and colour.blue() < 40 and colour.red() < 40

    blue = until(lambda: colour_matches("blue"), seconds=15)
    report["video_initial_diagnostics"] = gpu.diagnostics()
    gpu.view.grabWindow().save(str(out/"video-before.png"))
    check("native video initially shows retained blue section", blue)
    # Sample inside the retained frame, separately from Qt's tolerance for a
    # frame ending exactly on a millisecond-rounded seek boundary.
    transport.position = 1.06
    project.playhead = 1.06
    transport.sync()  # No explicit user-seek flag, as with a tick skipping a gap.
    green = until(lambda: colour_matches("green"))
    report["video_state"] = dict(timeline=transport.position, playhead=project.playhead,
        previous=repr(transport.previous_video), pending=repr(transport._pending_video_seeks),
        floors=repr(transport._video_seek_floor),
        sources=repr(getattr(gpu, "sources", {})), decoders=[dict(key=repr(key), position=player.position(),
        status=player.mediaStatus().name, state=player.playbackState().name, stamp=getattr(sink, "_frame_stamp", None))
        for key, (player, _, sink) in transport.decoders.items()])
    gpu.view.grabWindow().save(str(out/"video-after.png"))
    check("native video shared decoder enters retained green section", green)
    report["video_diagnostics"] = gpu.diagnostics()
    check("video remains GPU rendered", report["video_diagnostics"].get("graphics_backend") == "Direct3D11")
    window._project_clean = True
    window.close()
    check("normal diagnostic close", until(lambda: not window.isVisible()))
    report["passed"] = all(row["passed"] for row in report["checks"])
    save()
    return 0 if report["passed"] else 1
