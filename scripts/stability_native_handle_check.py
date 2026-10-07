"""Minimal real Qt backend lifetime ablation; no owner state or native census.

Samples this process with documented GetProcessHandleCount only. Disposal and
sampling run inside QApplication.exec(), with native stop/delete slots queued.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--decoder', choices=('cpu', 'd3d11', 'd3d12', 'dxva2', 'cuda'), default='cpu')
parser.add_argument('--input', choices=('shared', 'url'), default='shared')
parser.add_argument('--pipeline', choices=('none', 'audio', 'video', 'image', 'both', 'unattached'), default='both')
parser.add_argument('--detach', action='store_true')
parser.add_argument('--reuse-audio', action='store_true')
parser.add_argument('--reuse-player', action='store_true')
parser.add_argument('--reset-source', action='store_true')
parser.add_argument('--pause-only', action='store_true')
parser.add_argument('--clear-frame', action='store_true')
parser.add_argument('--clear-source', action='store_true')
parser.add_argument('--idle-ms', type=int, default=1500)
parser.add_argument('--cycles', type=int, default=40)
parser.add_argument('--play-ms', type=int, default=220)
parser.add_argument('--report-tag', default='')
args = parser.parse_args()
assert not args.report_tag or re.fullmatch(r'[a-zA-Z0-9_-]+', args.report_tag), 'Invalid report tag'
label=f'{args.decoder}-{args.input}-{args.pipeline}' + ('-detach' if args.detach else '') + ('-reuse' if args.reuse_audio else '')
label+=('-player' if args.reuse_player else '')+('-reset' if args.reset_source else '')
label+=('-pause' if args.pause_only else '')+f'-{args.cycles}' + (f'-idle{args.idle_ms}' if args.idle_ms!=1500 else '')
label+=('-clearframe' if args.clear_frame else '')+('-clearsource' if args.clear_source else '')
if args.report_tag:label+='-'+args.report_tag
if args.play_ms!=220:label+=f'-play{args.play_ms}'
out = ROOT / 'build' / 'native-handle-ablation' / label
out.mkdir(parents=True, exist_ok=True)
os.environ['KINETIC_CUT_HOME'] = str(out / 'home')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES'] = ',' if args.decoder == 'cpu' else {'d3d11':'d3d11va','d3d12':'d3d12va'}.get(args.decoder,args.decoder)
os.environ['QT_DISABLE_HW_TEXTURES_CONVERSION'] = '1'
from ctypes import wintypes as wt
from PySide6.QtCore import QTimer, QUrl, QMetaObject, Qt, QObject, qVersion
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink, QAudioOutput, QVideoFrame
from kinetic_cut.media_source import set_media_source

source = ROOT / 'build' / 'stability-delivery-home' / 'generated-av.mp4'
assert source.is_file(), source
alternative=out/'generated-av2.mp4'
if args.reset_source:alternative.write_bytes(source.read_bytes())
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
owner = QObject()
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.GetCurrentProcess.restype = wt.HANDLE
kernel.GetProcessHandleCount.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
kernel.GetProcessHandleCount.restype = wt.BOOL
process = kernel.GetCurrentProcess()
report = {'decoder': args.decoder, 'input': args.input, 'pipeline': args.pipeline,
          'qt_version':qVersion(), 'report_tag':args.report_tag,
          'detach':args.detach,'reuse_audio':args.reuse_audio,
          'reuse_player':args.reuse_player,'reset_source':args.reset_source,
          'pause_only':args.pause_only,'idle_ms':args.idle_ms,
          'clear_frame':args.clear_frame,'clear_source':args.clear_source,
          'play_ms':args.play_ms,
          'samples': [], 'frames': 0, 'images': 0, 'errors': []}
def unexpected(*exc):
    report['failure']=''.join(traceback.format_exception(*exc))
    print(report['failure'],flush=True)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    app.exit(1)
sys.excepthook=unexpected
player = None
sink = None
cycle = 0
started = time.monotonic()
reusable_audio=QAudioOutput(owner) if args.reuse_audio else None
if reusable_audio:reusable_audio.setMuted(True)
reusable_player=QMediaPlayer(owner) if args.reuse_player else None


def sample(label):
    count = wt.DWORD()
    assert kernel.GetProcessHandleCount(process, ctypes.byref(count))
    value = {'cycle': cycle, 'label': label, 'handles': count.value,
             'players': len(owner.findChildren(QMediaPlayer)),
             'seconds': round(time.monotonic() - started, 3)}
    report['samples'].append(value)
    print(json.dumps(value), flush=True)


def read_frame():
    if sink is None:
        return
    frame = sink.videoFrame()
    if not frame.isValid():
        return
    report['frames'] += 1
    if args.pipeline in ('image', 'both'):
        image = frame.toImage().copy()
        if not image.isNull():
            report['images'] += 1
            if 'sample_image' not in report:
                sample_path=out/'decoded-frame.png'
                assert image.save(str(sample_path)), 'Could not save decoded test frame'
                colors={image.pixelColor(x,y).rgb() for x in range(0,image.width(),max(1,image.width()//16))
                        for y in range(0,image.height(),max(1,image.height()//8))}
                assert len(colors)>8, 'Generated test pattern decoded as a blank frame'
                report['sample_image']={'path':str(sample_path),'width':image.width(),
                                        'height':image.height(),'distinct_sample_colors':len(colors)}


timer = QTimer()
timer.setInterval(30)
timer.timeout.connect(read_frame)


def next_cycle():
    global cycle, player, sink
    cycle += 1
    player = reusable_player or QMediaPlayer(owner)
    if args.pipeline in ('audio', 'both', 'unattached'):
        audio = reusable_audio or getattr(player,'_check_audio',None) or QAudioOutput(player)
        player._check_audio=audio
        audio.setMuted(True)
        if args.pipeline!='unattached':player.setAudioOutput(audio)
    if args.pipeline in ('video', 'image', 'both', 'unattached'):
        sink = getattr(player,'_check_sink',None) or QVideoSink(player)
        player._check_sink=sink
        player.setVideoSink(sink)
    else:
        sink = None
    if not args.reuse_player or cycle==1:
        player.errorOccurred.connect(lambda *values: report['errors'].append(str(values)), Qt.QueuedConnection)
    if not args.reuse_player or cycle==1 or args.reset_source:
        url = QUrl.fromLocalFile(str(alternative if args.reset_source and cycle%2==0 else source))
        if args.input == 'shared':set_media_source(player, url)
        else:player.setSource(url)
    if args.pipeline in ('none', 'audio'):
        player.setActiveVideoTrack(-1)
    if args.pipeline in ('none', 'video', 'image', 'unattached'):
        player.setActiveAudioTrack(-1)
    if args.reuse_player and args.pause_only:player.setPosition(0)
    QMetaObject.invokeMethod(player, 'play', Qt.QueuedConnection)
    timer.start()
    QTimer.singleShot(args.play_ms, retire)


def retire():
    global player, sink
    timer.stop()
    if args.detach:
        player.setAudioOutput(None)
        player.setVideoSink(None)
    QMetaObject.invokeMethod(player, 'pause', Qt.QueuedConnection)
    if not args.pause_only:QMetaObject.invokeMethod(player, 'stop', Qt.QueuedConnection)
    if args.clear_frame or args.clear_source:
        # Let the queued native stop finish before releasing the sink's cached
        # frame/source, then dispose this player's QObject on the GUI thread.
        retiring_player,retiring_sink=player,sink
        def release_outputs():
            if args.clear_frame and retiring_sink is not None:retiring_sink.setVideoFrame(QVideoFrame())
            if args.clear_source:retiring_player.setSource(QUrl())
            if not args.reuse_player:QMetaObject.invokeMethod(retiring_player,'deleteLater',Qt.QueuedConnection)
        QTimer.singleShot(0,release_outputs)
    elif not args.reuse_player:QMetaObject.invokeMethod(player, 'deleteLater', Qt.QueuedConnection)
    player = None
    sink = None
    QTimer.singleShot(150, settled)


def settled():
    assert len(owner.findChildren(QMediaPlayer))==(1 if args.reuse_player else 0), 'Player not retired'
    if cycle == 1 or cycle % 5 == 0:
        sample('settled')
    if cycle < args.cycles:
        next_cycle()
    else:
        if args.reuse_player:QMetaObject.invokeMethod(reusable_player,'deleteLater',Qt.QueuedConnection)
        QTimer.singleShot(args.idle_ms, finish)


def finish():
    sample('final-idle')
    report['growth_after_warmup'] = report['samples'][-1]['handles'] - report['samples'][min(2, len(report['samples']) - 1)]['handles']
    (out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}), flush=True)
    app.quit()


sample('baseline')
QTimer.singleShot(0, next_cycle)
sys.exit(app.exec())
