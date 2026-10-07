"""Isolated native Deliver success/cancellation/failure recovery diagnostic.

Uses only generated media under build/, never an owner's project or settings.
Run with .venv/Scripts/python.exe scripts/stability_delivery_check.py.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / 'build' / 'stability-delivery-home'
HOME.mkdir(parents=True, exist_ok=True)
os.environ['KINETIC_CUT_HOME'] = str(HOME)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, QEventLoop, QTimer, QThreadPool
from PySide6.QtWidgets import QApplication
from kinetic_cut.graphics import default_graphic_data
from kinetic_cut.media import probe
from kinetic_cut.model import Project, ProjectSettings, TimelineItem, Caption, CaptionStyle
from kinetic_cut.transitions import Transition
from kinetic_cut.ui import MainWindow
from kinetic_cut.workspace import set_page


def command(args, timeout=60):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(f'{args[0]} returned {result.returncode}: {result.stderr[-3000:]}')
    return result.stdout


def spin(ms=50):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(predicate, timeout=60):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise TimeoutError('Diagnostic did not settle before deadline')
        spin()


def fixture(media):
    style = CaptionStyle(font='Arial', size=24, color='#ffffff', outline_width=2,
                         shadow=0, shadow_enabled=False, animation='word highlight',
                         highlight='#ffff55', position_y=.73)
    p = Project(name='Generated stability render', settings=ProjectSettings(320, 568, 30),
                media=[media], video_tracks=['video_1', 'video_2', 'video_3'])
    first = TimelineItem('first', media.id, 'video_1', 0, 2, in_point=0, link_id='one')
    second = TimelineItem('second', media.id, 'video_1', 2, 2, in_point=2, link_id='two')
    first.effects = [{'name': 'Gaussian Blur', 'enabled': True, 'horizontal': 3,
                      'vertical': 3, 'linked': True, 'mix': 25}]
    first.saturation = .8
    second.transform.flip_horizontal = True
    second.brightness = .05
    overlay = TimelineItem('overlay', media.id, 'video_2', .6, 1.4, in_point=1)
    overlay.transform.scale = .3
    overlay.transform.y = .25
    overlay.opacity = 75
    arrow = TimelineItem('arrow', '', 'video_3', .3, 2.8, role='graphic',
                         graphic_type='Pointing Arrow',
                         graphic_data=default_graphic_data('Pointing Arrow'))
    arrow.transform.x = .65
    arrow.transform.y = .5
    arrow.transform.scale = .45
    arrow.keyframes = {'rotation': [{'time': 0., 'value': -15., 'easing': 'linear'},
                                   {'time': 2.8, 'value': 40., 'easing': 'linear'}]}
    p.timeline = [first, second, overlay, arrow,
                  TimelineItem('audio-first', media.id, 'audio_1', 0, 2,
                               role='source_audio', link_id='one', fade_in=.1),
                  TimelineItem('audio-second', media.id, 'audio_1', 2, 2, in_point=2,
                               role='source_audio', link_id='two', fade_out=.1)]
    p.transitions = [Transition(id='join', name='Cross Dissolve', track='video_1',
                                start=1.8, duration=.4, left_item_id='first',
                                right_item_id='second')]
    p.captions = [Caption('caption-a', .2, 1.8, 'GENERATED TEST', copy.deepcopy(style),
                          word_timings=[{'word': 'GENERATED', 'start': .2, 'end': .9},
                                        {'word': 'TEST', 'start': .9, 'end': 1.8}]),
                  Caption('caption-b', 2.1, 3.8, 'AFTER CANCEL', copy.deepcopy(style),
                          word_timings=[{'word': 'AFTER', 'start': 2.1, 'end': 2.8},
                                        {'word': 'CANCEL', 'start': 2.8, 'end': 3.8}])]
    p.subtitle_style = copy.deepcopy(style)
    return p


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setProperty('kineticTestDiscardUnsaved', True)
    source = HOME / 'generated-av.mp4'
    command(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
             '-i', 'testsrc2=size=320x180:rate=30:duration=8', '-f', 'lavfi',
             '-i', 'sine=frequency=440:sample_rate=48000:duration=8', '-c:v',
             'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
             '-shortest', str(source)])
    media = probe(str(source))
    p = fixture(media)
    w = MainWindow()
    w.autosave_timer.stop()
    w.show()
    report = {'source': str(source), 'fixture': {'layers': 3, 'captions': 2,
              'transition': 'Cross Dissolve', 'effects': ['Gaussian Blur', 'color',
                                                        'animated graphic']}}
    try:
        w.set_project(p)
        w.delivery.sync_project_settings()
        w.delivery.location.setText(str(HOME))
        w.delivery.hardware.setCurrentText('CPU')
        w.delivery.fps.setCurrentText('30')
        w.delivery.burn.setChecked(True)
        delivery = w.delivery

        def queue(name):
            delivery.name.setText(name)
            output = HOME / (name + '.mp4')
            output.unlink(missing_ok=True)  # Only this diagnostic's generated outputs.
            delivery.add_job()
            assert delivery.jobs[-1]['output'] == str(output)
            return delivery.jobs[-1]

        success = queue('mixed-success')
        started = time.monotonic()
        delivery.render_all()
        wait_until(lambda: not delivery.running, 120)
        assert success['state'] == 'Complete', success
        data = json.loads(command(['ffprobe', '-v', 'error', '-count_frames',
                                  '-show_streams', '-show_format', '-of', 'json',
                                  success['output']]))
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
        assert video['width'] == 320 and video['height'] == 568
        assert int(video['nb_read_frames']) == 120, video
        assert abs(float(data['format']['duration']) - 4.) < .1
        command(['ffmpeg', '-v', 'error', '-xerror', '-i', success['output'],
                 '-f', 'null', '-'], 60)
        report['mixed_render'] = {'state': success['state'], 'seconds': time.monotonic() - started,
                                  'frames': int(video['nb_read_frames']),
                                  'duration': data['format']['duration'],
                                  'video_codec': video['codec_name'],
                                  'audio_codec': audio['codec_name'],
                                  'bytes': Path(success['output']).stat().st_size,
                                  'full_decode': 'passed'}

        cancelled = queue('cancel-preserves-existing')
        previous = Path(success['output']).read_bytes()
        Path(cancelled['output']).write_bytes(previous)
        expected_hash = hashlib.sha256(previous).hexdigest()
        cancel_started = time.monotonic()
        delivery.render_all()
        QTimer.singleShot(75, delivery.cancel_current)
        wait_until(lambda: not delivery.running, 30)
        assert cancelled['state'] == 'Cancelled', cancelled
        assert hashlib.sha256(Path(cancelled['output']).read_bytes()).hexdigest() == expected_hash
        assert delivery.window.page_group.button(0).isEnabled()
        assert delivery.window.page_group.button(2).isEnabled()
        report['cancellation'] = {'state': cancelled['state'], 'previous_output_unchanged': True,
                                   'seconds': time.monotonic() - cancel_started,
                                   'editing_pages_enabled': True}

        failed = queue('missing-source')
        failed['project'].media[0].path = str(HOME / 'deleted-source.mp4')
        recovery = queue('recovery-success')
        delivery.render_all()
        wait_until(lambda: not delivery.running, 120)
        assert failed['state'] == 'Failed' and 'Relink missing' in failed['error'], failed
        assert not Path(failed['output']).exists()
        assert recovery['state'] == 'Complete', recovery
        command(['ffmpeg', '-v', 'error', '-xerror', '-i', recovery['output'],
                 '-f', 'null', '-'], 60)
        report['failure_recovery'] = {'failure_state': failed['state'],
                                     'partial_output_absent': True,
                                     'next_job_state': recovery['state'],
                                     'next_job_full_decode': 'passed'}
        set_page(w, 0)
        assert w.current_page == 0
        assert not list(HOME.glob('.kinetic-export-*')), 'Leaked export temporary directories'
        report['temporary_render_directories'] = 0
        report['result'] = 'passed'
    finally:
        w.close()
        wait_until(lambda: not w._workers, 30)
        w.close()
        w.deleteLater()
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        spin(50)
        assert QThreadPool.globalInstance().waitForDone(10000)
        (HOME / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
