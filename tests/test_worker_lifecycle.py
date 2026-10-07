"""Finished jobs release their inputs/callbacks while pending jobs stay alive."""
import gc
import threading
import unittest
import weakref
from unittest.mock import patch

from PySide6.QtCore import QEvent, QObject, QThread, QThreadPool
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar
from types import SimpleNamespace

from kinetic_cut.ui import MainWindow, Worker


class _JobOwner(QObject):
    start_worker = MainWindow.start_worker
    worker_finished = MainWindow.worker_finished

    def __init__(self):
        super().__init__()
        self._workers = set()
        self.thread_pool = QThreadPool(self)
        self.status_threads = []

    def update_job_status(self):
        self.status_threads.append(QThread.currentThread())


class _Payload:
    pass


class WorkerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.owner = _JobOwner()

    def drain(self):
        self.assertTrue(self.owner.thread_pool.waitForDone(5000))
        self.app.processEvents()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        gc.collect()

    def tearDown(self):
        self.drain()
        self.owner.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_success_releases_inputs_and_result_callback_captures(self):
        payload, callback_payload = _Payload(), _Payload()
        input_ref, callback_ref = weakref.ref(payload), weakref.ref(callback_payload)
        received = []
        job = Worker(lambda value: 'done', payload)
        job_ref = weakref.ref(job)
        job.signals.result.connect(lambda value, captured=callback_payload: received.append(value))
        self.owner.start_worker(job)
        del job, payload, callback_payload
        self.drain()
        self.assertEqual(received, ['done'])
        self.assertFalse(self.owner._workers)
        self.assertIsNone(job_ref())
        self.assertIsNone(input_ref())
        self.assertIsNone(callback_ref())
        self.assertTrue(all(thread == self.app.thread() for thread in self.owner.status_threads))

    def test_error_delivered_before_inputs_are_released(self):
        def fail(value):
            raise ValueError('expected worker failure')

        payload = _Payload()
        input_ref = weakref.ref(payload)
        received = []
        job = Worker(fail, payload)
        job_ref = weakref.ref(job)
        job.signals.error.connect(received.append)
        with patch('kinetic_cut.ui.logging.exception'):
            self.owner.start_worker(job)
            del job, payload
            self.drain()
        self.assertEqual(len(received), 1)
        self.assertIn('expected worker failure', received[0])
        self.assertFalse(self.owner._workers)
        self.assertIsNone(job_ref())
        self.assertIsNone(input_ref())

    def test_active_job_keeps_inputs_until_completion_is_processed(self):
        started, release = threading.Event(), threading.Event()

        def work(value):
            started.set()
            if not release.wait(5):
                raise RuntimeError('test did not release worker')
            return 'done'

        payload = _Payload()
        input_ref = weakref.ref(payload)
        job = Worker(work, payload)
        job_ref = weakref.ref(job)
        self.owner.start_worker(job)
        del job, payload
        try:
            self.assertTrue(started.wait(5))
            self.app.processEvents()
            gc.collect()
            self.assertEqual(len(self.owner._workers), 1)
            self.assertIsNotNone(job_ref())
            self.assertIsNotNone(input_ref())
        finally:
            release.set()
        self.drain()
        self.assertFalse(self.owner._workers)
        self.assertIsNone(job_ref())
        self.assertIsNone(input_ref())

    def test_maintenance_is_retained_and_finishes_like_foreground_work(self):
        started, release = threading.Event(), threading.Event()
        job=Worker(lambda:(started.set(),release.wait(5)))
        job.maintenance=True; self.owner.start_worker(job)
        try:
            self.assertTrue(started.wait(5)); self.assertIn(job,self.owner._workers)
        finally:release.set()
        self.drain(); self.assertFalse(self.owner._workers)

    def test_only_user_work_shows_task_indicator(self):
        label=QLabel(); progress=QProgressBar()
        maintenance=Worker(lambda:None); maintenance.maintenance=True
        ordinary=Worker(lambda:None)
        owner=SimpleNamespace(_workers={maintenance},job_status=label,job_progress=progress)
        try:
            MainWindow.update_job_status(owner)
            self.assertTrue(label.isHidden()); self.assertTrue(progress.isHidden())
            owner._workers.add(ordinary); MainWindow.update_job_status(owner)
            self.assertFalse(label.isHidden()); self.assertFalse(progress.isHidden())
            self.assertEqual(label.text(),'1 background task')
            owner._workers.remove(ordinary); MainWindow.update_job_status(owner)
            self.assertTrue(label.isHidden()); self.assertTrue(progress.isHidden())
        finally:
            label.deleteLater(); progress.deleteLater()
            maintenance.signals.deleteLater(); ordinary.signals.deleteLater()
