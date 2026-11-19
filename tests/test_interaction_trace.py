"""Optional diagnostics must observe events without changing their result."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import QCoreApplication, QEvent, QMetaObject, Qt
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication
from kinetic_cut.activity_log import read
from kinetic_cut.interaction_trace import InteractionTrace
from kinetic_cut.ui import MainWindow


class InteractionTraceTests(unittest.TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.temp = tempfile.TemporaryDirectory()
        self.window = MainWindow(); self.window.autosave_timer.stop()
        self.trace = InteractionTrace(self.window, self.temp.name)

    def tearDown(self):
        self.trace.stop(); self.trace.log.close()
        self.window.close(); self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents(); self.temp.cleanup()

    def test_wrapper_preserves_result_single_execution_and_exception(self):
        class Work:
            def __init__(self): self.calls = 0
            def compute(self, value):
                self.calls += 1
                if value < 0: raise ValueError('expected')
                return value * 3
        owner = Work(); original = owner.compute
        self.trace.wrap(owner, 'compute'); self.trace.arm()
        self.assertEqual(owner.compute(7), 21)
        with self.assertRaisesRegex(ValueError, 'expected'): owner.compute(-1)
        self.assertEqual(owner.calls, 2); self.assertEqual(self.trace.active, [])
        self.trace.stop(); self.assertEqual(owner.compute, original)
        rows = read(Path(self.temp.name) / 'editing-events.log')
        self.assertEqual(sum(r['action'] == 'work.begin' for r in rows), 2)
        self.assertEqual(sum(r['action'] == 'work.end' for r in rows), 2)

    def test_queued_player_event_is_observed_and_not_consumed(self):
        player = QMediaPlayer(self.window); self.trace.watch_player(player); self.trace.arm()
        self.assertFalse(self.trace.eventFilter(player, QEvent(QEvent.User)))
        self.assertTrue(QMetaObject.invokeMethod(player, 'pause', Qt.QueuedConnection))
        QCoreApplication.sendPostedEvents(player, QEvent.MetaCall)
        rows = read(Path(self.temp.name) / 'editing-events.log')
        self.assertTrue(any(r['action'] == 'qt.dispatch' and r['details']['event'] == int(QEvent.MetaCall) for r in rows))
        player.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.trace.stop()  # Deleted receivers must not break normal shutdown.

    def test_short_delay_records_active_phase_without_changing_project(self):
        before = self.window.project.to_dict()
        self.trace.arm(); self.trace.previous = time.monotonic() - .3
        self.trace.sample()
        rows = read(Path(self.temp.name) / 'editing-events.log')
        self.assertTrue(any(r['action'] == 'gui.delay' for r in rows))
        self.assertEqual(self.window.project.to_dict(), before)

    def test_watchdog_settings_restore_after_capture(self):
        self.trace.stop(); self.trace.log.close()
        guard = SimpleNamespace(timeout=5., interval=.5, max_reports=4, deadline=123.)
        self.app._kinetic_hang_watchdog = guard
        try:
            self.trace = InteractionTrace(self.window, self.temp.name)
            self.trace.arm(); self.assertEqual(guard.timeout, .18)
            self.trace.until = time.monotonic() - 1.; self.trace.sample()
            self.assertEqual(guard.timeout, 5.)
            self.trace.stop()
            self.assertEqual((guard.timeout, guard.interval, guard.max_reports), (5., .5, 4))
        finally:
            del self.app._kinetic_hang_watchdog
