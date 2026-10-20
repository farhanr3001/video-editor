"""Live caption progress; elapsed time keeps advancing between worker messages."""
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QProgressDialog


def duration_text(seconds):
    seconds=max(0,round(seconds));minutes,seconds=divmod(seconds,60)
    return f'{minutes}:{seconds:02d}'


class CaptionProgressDialog(QProgressDialog):
    def __init__(self,parent=None,clock=time.monotonic):
        super().__init__('Preparing timeline audio…','Cancel',0,100,parent)
        self.setWindowTitle('Generating Auto Captions')
        self.setMinimumWidth(420)
        self._clock=clock;self._started=clock();self._percent=0
        self._message='Preparing timeline audio…'
        self._timer=QTimer(self);self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh_time);self.canceled.connect(self._timer.stop)
        self._timer.start();self.refresh_time()

    def set_progress(self,percent,message):
        self._percent=max(self._percent,percent)
        self._message=str(message);self.setValue(self._percent);self.refresh_time()

    def refresh_time(self):
        now=self._clock();elapsed=now-self._started
        self.setLabelText(self._message+'\nElapsed '+duration_text(elapsed))

    def closeEvent(self,event):
        self._timer.stop();super().closeEvent(event)

    def hideEvent(self,event):
        self._timer.stop();super().hideEvent(event)
