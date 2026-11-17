"""Popup job workers have exactly one owner once their thread ends.

Regression: RetainedThread also connected thread.finished to worker.deleteLater.
The finishing thread and the GUI thread (dropping the last Python reference in
_retire) could then destroy the same C++ worker: an intermittent access
violation after speech preview / voice-availability jobs.
"""
import os
import tempfile
import time
import unittest

os.environ.setdefault('KINETIC_CUT_HOME', tempfile.mkdtemp(prefix='kc-dialog-jobs-'))

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal, Slot
from PySide6.QtWidgets import QApplication

from kinetic_cut import dialog_jobs
from kinetic_cut.dialog_jobs import RetainedThread

app = QApplication.instance() or QApplication([])


class Job(QObject):
    settled = Signal()
    result = Signal(int)

    def __init__(self, value=0):
        super().__init__(); self.value = value; self.cancelled = False

    @Slot()
    def run(self):
        try: self.result.emit(self.value)
        finally: self.settled.emit()


def drain(condition, seconds=5.):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete); time.sleep(.002)
    return condition()


class DialogJobOwnership(unittest.TestCase):
    def test_finished_worker_stays_valid_while_python_still_references_it(self):
        worker = Job(7); seen = []; worker.result.connect(seen.append)
        job = RetainedThread(worker); done = []; job.finished.connect(lambda: done.append(True)); job.start()
        self.assertTrue(drain(lambda: bool(done)))
        self.assertEqual(seen, [7])
        # Qt must not have deleted it behind Python's back from the worker thread.
        for _ in range(20): app.processEvents(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertTrue(shiboken6.isValid(worker))
        self.assertIsNone(job.worker); self.assertIsNone(job.thread); self.assertNotIn(job, dialog_jobs._retained)
        self.assertEqual(dialog_jobs._stranded, [])

    def test_many_short_jobs_released_immediately_do_not_crash(self):
        finished = []
        for index in range(150):
            job = RetainedThread(Job(index)); job.finished.connect(lambda: finished.append(1)); job.start()
            del job
        self.assertTrue(drain(lambda: len(finished) == 150, 30.))
        self.assertFalse(dialog_jobs.active_dialog_threads()); self.assertEqual(len(dialog_jobs._retained), 0)

    def test_source_has_no_cross_thread_delete_of_the_worker(self):
        from pathlib import Path
        source = Path(dialog_jobs.__file__).read_text(encoding='utf-8')
        self.assertNotIn('finished.connect(worker.deleteLater)', source)


if __name__ == '__main__':
    unittest.main()
