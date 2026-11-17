"""Keep cancellable popup jobs alive until their native threads really finish.

Closing a popup must never destroy a running QThread. Results still belong to
the feature controller; this module only owns the worker/thread lifetime.
"""
from __future__ import annotations

import time
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

_retained: set["RetainedThread"] = set()
_stranded: list = []  # workers whose thread did not end in time; kept alive, never freed concurrently


class RetainedThread(QObject):
    finished = Signal()

    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.thread = QThread()  # Deliberately independent of the dialog.
        self._started = False
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        # quit() cannot interrupt run(). Every worker emits settled in finally,
        # including cancellation/failure; direct quit permits shutdown waits.
        worker.settled.connect(self.thread.quit, Qt.DirectConnection)
        # One owner deletes the worker: Python, on the GUI thread, after the
        # thread has ended (_retire). Also asking Qt to deleteLater() it from
        # the finishing thread let both threads destroy the same C++ object
        # when the last Python reference was dropped at that moment: an
        # intermittent access violation after a speech preview/availability job.
        self.thread.finished.connect(self._retire, Qt.QueuedConnection)

    def start(self):
        if self._started:
            return
        self._started = True
        _retained.add(self)
        self.thread.start()

    def isRunning(self):
        return self.thread is not None and self.thread.isRunning()

    def cancel(self):
        if self.worker is None:
            return
        cancel = getattr(self.worker, "cancel", None)
        if cancel:
            cancel()
        else:
            self.worker.cancelled = True

    @Slot()
    def _retire(self):
        thread = self.thread
        if thread is not None:
            # finished() is emitted just before the native thread exits. Join
            # it (already ending, so this is immediate) so the worker, which
            # lives in that thread, is only released once nothing runs there.
            thread.wait(2000)
        worker, self.worker = self.worker, None
        self.thread = None
        _retained.discard(self)
        if worker is not None and thread is not None and thread.isRunning():
            # Never observed; do not free an object under a still-running thread.
            _stranded.append(worker)
        del worker
        if thread is not None:
            thread.deleteLater()
        self.finished.emit()


def active_dialog_threads():
    return tuple(job for job in _retained if job.isRunning())


def cancel_dialog_threads():
    for job in tuple(_retained):
        job.cancel()


def wait_dialog_threads(timeout_ms=3000):
    """Bounded shutdown drain after cooperative cancellation; never terminate Qt."""
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    for job in tuple(_retained):
        if job.thread is not None:
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            job.thread.wait(remaining)
    return not active_dialog_threads()
