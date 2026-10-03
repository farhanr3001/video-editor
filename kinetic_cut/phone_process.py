"""Qt process supervisor: bounded metadata requests and cancellable transfers."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .phone_common import helper_command


def tool_path(settings, name):
    override = settings.get('phone_' + name, '')
    if override and Path(override).is_file():
        return str(Path(override).resolve())
    from .config import DATA_DIR
    for folder in ('phone-android-v1', 'phone-iphone-v1'):
        downloaded = DATA_DIR / 'components' / folder / (name + '.exe')
        if downloaded.is_file():
            return str(downloaded)
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    bundled_scrcpy = base / 'assets' / 'phone-tools' / 'scrcpy-win64-v4.1' / (name + '.exe')
    if bundled_scrcpy.is_file():
        return str(bundled_scrcpy)
    bundled_uxplay = base / 'assets' / 'phone-tools' / 'uxplay' / (name + '.exe')
    if bundled_uxplay.is_file():
        return str(bundled_uxplay)
    return shutil.which(name) or ''


class PhoneRequest(QObject):
    progress = Signal(int, int)  # percent, unused; byte totals use object to avoid 32-bit overflow
    bytesChanged = Signal(object, object)
    finished = Signal(bool, object)

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.request = dict(request)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.finished.connect(self._exited)
        self.process.errorOccurred.connect(self._error)
        self.process.started.connect(self._send)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self._timeout)
        self.kill_timer = QTimer(self); self.kill_timer.setSingleShot(True); self.kill_timer.timeout.connect(self.process.kill)
        self.buffer = b''; self.errors = b''; self.result = None; self.failure = ''; self.cancelled = False; self.done = False

    def start(self):
        program, args = helper_command()
        self.timer.start(60000 if self.request['op'] in {'push', 'pull'} else 35000)
        self.process.start(program, args)

    def _send(self):
        self.process.write((json.dumps(self.request) + '\n').encode('utf-8'))

    def _stderr(self):
        self.errors = (self.errors + bytes(self.process.readAllStandardError()))[-8000:]

    def _read(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                data = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if data.get('event') == 'progress':
                self.timer.start(60000)
                self.bytesChanged.emit(data['done'], data['total'])
            elif data.get('event') == 'result':
                self.result = data.get('value')
            elif data.get('event') == 'error':
                self.failure = data.get('message', 'Device request failed.')

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._finish(False, 'Could not start the phone helper: ' + self.process.errorString())

    def _exited(self, code, status):
        self._read(); self._stderr()
        # A published result wins over a late cancel click: do not mislabel a completed copy.
        if code == 0 and status == QProcess.NormalExit and self.result is not None:
            self._finish(True, self.result)
        else:
            detail = self.failure or ('Cancelled. An interrupted device transfer may leave a .kinetic-*.partial file.' if self.cancelled else
                                      'Phone helper exited unexpectedly. ' + self.errors.decode('utf-8', 'replace')[-1500:])
            self._finish(False, detail)

    def _finish(self, success, result):
        if self.done: return
        self.done = True; self.timer.stop(); self.kill_timer.stop()
        self.finished.emit(success, result)

    def _timeout(self):
        self.failure = 'Device stopped responding. Unlock/reconnect it, then retry. No completed transfer was confirmed.'
        self.cancel()

    def cancel(self):
        if self.done: return
        self.cancelled = True
        self.process.write(b'cancel\n')
        self.kill_timer.start(2500)

    def shutdown(self):
        self.timer.stop(); self.kill_timer.stop()
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1500)
