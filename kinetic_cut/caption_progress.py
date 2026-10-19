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
        self._clock=clock;self._started=clock();self._phase_started=None
        self._message='Preparing timeline audio…';self._fraction=None
        self._timer=QTimer(self);self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh_time);self.canceled.connect(self._timer.stop)
        self._timer.start();self.refresh_time()

    def set_progress(self,percent,message):
        now=self._clock()
        # 45–90 is actual source audio processed, rather than arbitrary setup
        # percentages. Do not include audio extraction/model loading in its rate.
        if str(message).startswith('Transcribing…'):
            if self._phase_started is None:self._phase_started=now
            self._fraction=max(0.,min(1.,(percent-45)/45))
        else:self._phase_started=None;self._fraction=None
        self._message=str(message);self.setValue(percent);self.refresh_time()

    def refresh_time(self):
        now=self._clock();elapsed=now-self._started
        estimate='Estimating…'
        if self._phase_started is not None and self._fraction and self._fraction>=.03:
            spent=now-self._phase_started
            if spent>=1:estimate='About '+duration_text(spent*(1-self._fraction)/self._fraction)+' remaining'
        self.setLabelText(self._message+'\nElapsed '+duration_text(elapsed)+' · '+estimate)

    def closeEvent(self,event):
        self._timer.stop();super().closeEvent(event)

    def hideEvent(self,event):
        self._timer.stop();super().hideEvent(event)
