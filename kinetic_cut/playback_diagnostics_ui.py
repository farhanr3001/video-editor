"""Read-only renderer/decoder diagnostics and bounded GUI heartbeat history."""
import json
import time
from collections import deque
from PySide6.QtCore import QObject,QTimer,Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QPlainTextEdit,QDialogButtonBox,QApplication


class EventMonitor(QObject):
    def __init__(self,window):
        super().__init__(window);self.delays=deque(maxlen=512);self.previous=time.perf_counter()
        self.timer=QTimer(self);self.timer.setTimerType(Qt.PreciseTimer);self.timer.setInterval(16)
        self.timer.timeout.connect(self.sample);self.timer.start()
    def sample(self):
        now=time.perf_counter();self.delays.append(max(0.,(now-self.previous)*1000-16.));self.previous=now
    def snapshot(self):
        values=sorted(self.delays)
        return dict(samples=len(values),event_delay_p95_ms=round(values[min(len(values)-1,int(len(values)*.95))],3) if values else None,
                    event_delay_max_ms=round(max(values),3) if values else None)


def snapshot(window):
    preview=getattr(window.preview,'gpu',None);timeline=getattr(window.timeline,'gpu',None)
    result=dict(preview=preview.diagnostics() if preview else dict(composition='CPU compatibility',graphics_backend='Qt raster'),
                timeline=timeline.diagnostics() if timeline else dict(surface='QWidget compatibility'),decoders=[])
    monitor=getattr(window,'event_monitor',None)
    if monitor:result['main_thread']=monitor.snapshot()
    from .qt_native import NativeVideoPlayer
    from .video_worker import WorkerVideoPlayer
    for key,(player,_,sink) in window.transport.decoders.items():
        if sink is None:continue
        item=dict(media_id=str(key[0]),warm=key in window.transport.warm_keys)
        media=window.project.media_by_id(key[0]);item['codec']=media.video_codec if media else None
        if isinstance(player,NativeVideoPlayer):
            state=player.engine.read();item.update(engine='Qt FFmpeg (native command thread)',delivered_frames=int(state[5]),seek_to_frame_ms=state[6])
        elif isinstance(player,WorkerVideoPlayer):item.update(engine='PyAV/libav worker',hardware_decode=player.engine.hardware_active)
        else:item.update(engine='Qt FFmpeg compatibility',readback='bounded background worker')
        result['decoders'].append(item)
    return result


class DiagnosticsDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.owner=window;self.setWindowTitle('Playback Diagnostics');self.resize(680,560)
        layout=QVBoxLayout(self);self.details=QPlainTextEdit();self.details.setReadOnly(True);layout.addWidget(self.details)
        buttons=QDialogButtonBox(QDialogButtonBox.Close);copy=buttons.addButton('Copy diagnostics',QDialogButtonBox.ActionRole)
        copy.clicked.connect(lambda:QApplication.clipboard().setText(self.details.toPlainText()));buttons.rejected.connect(self.close);layout.addWidget(buttons)
        self.timer=QTimer(self);self.timer.setInterval(750);self.timer.timeout.connect(self.refresh)
    def refresh(self):
        position=self.details.verticalScrollBar().value();self.details.setPlainText(json.dumps(snapshot(self.owner),indent=2))
        self.details.verticalScrollBar().setValue(position)
    def showEvent(self,event):self.refresh();self.timer.start();super().showEvent(event)
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)


def show(window):
    if not getattr(window,'_playback_diagnostics_dialog',None):window._playback_diagnostics_dialog=DiagnosticsDialog(window)
    window._playback_diagnostics_dialog.show();window._playback_diagnostics_dialog.raise_()
