"""Isolated, read-only end-to-end AV1 timeline playback check."""
import json
import hashlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('KINETIC_CUT_HOME', str(ROOT / 'build' / 'av1-timeline-home'))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from kinetic_cut.media import probe
from kinetic_cut.model import Project, TimelineItem
from kinetic_cut.ui import MainWindow


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main():
    source = Path(sys.argv[1]).resolve()
    app = QApplication([])
    window = MainWindow()
    window.autosave_timer.stop()
    media = probe(source)
    project = Project(media=[media])
    project.timeline = [
        TimelineItem('video', media.id, 'video_1', 0, min(media.duration, 30)),
        TimelineItem('audio', media.id, 'audio_1', 0, min(media.duration, 30)),
    ]
    window.set_project(project)
    window.seek(2)
    deadline = time.monotonic() + 75
    ready_since = None
    while media.id not in window.proxies and time.monotonic() < deadline:
        wait(100)
        if media.id in window.preview_quality.compat_ready:
            ready_since = ready_since or time.monotonic()
            if time.monotonic() - ready_since > 3:
                break
    if media.id not in window.proxies:
        quality = window.preview_quality
        signature = quality._signature(media)
        raise AssertionError(dict(reason='AV1 compatibility preview was not selected',
                                  busy=quality.busy, job_kind=quality.job_kind,
                                  failed=list(quality.failed), ready=quality.compat_ready,
                                  ready_signatures=quality.compat_signatures,
                                  source_signature=signature, ready_match=quality._ready(media,signature,quality.compat_ready,quality.compat_signatures),
                                  proxies=dict(window.proxies),
                                  transport_paths=getattr(window.transport,'_media_source_paths',{}),
                                  settings=window.settings.get('optimized_preview'),
                                  media_codec=media.video_codec,
                                  project_media=[m.id for m in window.project.media],
                                  project_items=[(i.id, i.media_id, i.track) for i in window.project.timeline]))
    wait(600)
    window.transport.play()
    frames = 0
    frame_hashes = set()
    first_frame = False
    for _ in range(25):
        wait(100)
        visible = window.preview._visible_items()
        if visible and not visible[0][1].isNull():
            frames += 1
            first_frame = True
            key = window.preview.active_frames.get('video')
            image = window.preview.frames.get(key)
            if image is not None and not image.isNull():
                frame_hashes.add(hashlib.sha1(image.constBits()).hexdigest())
    audio_decoders = [key for key in window.transport.decoders if key[3].startswith('audio:')]
    result = dict(codec=media.video_codec, source=str(source), source_untouched=media.path == str(source),
                  proxy=window.proxies[media.id], valid_visual_samples=frames,
                  distinct_decoded_frames=len(frame_hashes),
                  audio_decoder_count=len(audio_decoders), playback_seconds=window.transport.position)
    window.transport.pause()
    window.close()
    print(json.dumps(result, indent=2))
    assert first_frame and frames >= 10 and len(frame_hashes)>=3, result
    assert audio_decoders, result


if __name__ == '__main__':
    main()
