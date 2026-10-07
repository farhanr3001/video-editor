"""Speech cancellation, popup destruction and transactional audio publication."""
import asyncio
import gc
import os
import sys
import tempfile
import threading
import time
import unittest
import weakref
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QThread, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

from kinetic_cut import tts
from kinetic_cut.dialog_jobs import active_dialog_threads, cancel_dialog_threads, wait_dialog_threads
from kinetic_cut.tts_dialog import TTSDialog
from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog
from kinetic_cut.model import MediaItem, Project, TimelineItem


def settle(until, timeout=3):
    deadline = time.monotonic() + timeout
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(5)
    timer.timeout.connect(lambda: loop.quit() if until() or time.monotonic() >= deadline else None)
    timer.start()
    loop.exec()
    timer.stop()
    if not until():
        raise AssertionError("Background work did not settle")


class TestTTSCancellation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        cancel_dialog_threads()
        self.assertTrue(wait_dialog_threads())
        settle(lambda: not active_dialog_threads())
        self.app.processEvents()

    def test_all_user_dismissals_are_responsive_and_discard_late_dialogue(self):
        for dialog_type, module in ((TTSDialogueDialog, "tts_dialogue_dialog"), (TTSDialog, "tts_dialog")):
            for dismissal in ("cancel", "escape", "x"):
                with self.subTest(dialog=module, dismissal=dismissal):
                    started = threading.Event()
                    release = threading.Event()
                    received = []
                    def delayed(**kwargs):
                        started.set()
                        # Simulates a library completing after cancellation.
                        release.wait(2)
                        return "late-speech.mp3"
                    function = "synthesize_dialogue_batches" if module == "tts_dialogue_dialog" else "synthesize_speech"
                    with patch(f"kinetic_cut.{module}.{function}", delayed):
                        dialog = dialog_type(initial_text="A speech request under load.")
                        dialog.speechGenerated.connect(received.append)
                        dialog.show()
                        dialog._on_generate_clicked()
                        settle(started.is_set)
                        self.assertTrue(dialog.cancel_btn.isEnabled())
                        begin = time.monotonic()
                        if dismissal == "cancel":
                            QTest.mouseClick(dialog.cancel_btn, Qt.LeftButton)
                        elif dismissal == "escape":
                            QTest.keyClick(dialog, Qt.Key_Escape)
                        else:
                            dialog.close()
                        self.assertLess(time.monotonic() - begin, .2)
                        self.assertEqual(dialog.result(), QDialog.Rejected)
                        self.assertTrue(active_dialog_threads(), "Closed popup must retain its unfinished job")
                        dialog.deleteLater()
                        self.app.processEvents()
                        release.set()
                        settle(lambda: not active_dialog_threads())
                        self.assertEqual(received, [], "Canceled audio must never be inserted")

    def test_actual_cooperative_cancel_reaches_pending_network_and_cleans_partial(self):
        started = threading.Event()
        cancel = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "speech.mp3"
            class PendingService:
                def __init__(self, *args, **kwargs):
                    pass
                async def save(self, target):
                    Path(target).write_bytes(b"partial")
                    started.set()
                    await asyncio.Future()
            timer = threading.Timer(.12, cancel.set)
            timer.start()
            begin = time.monotonic()
            try:
                with patch("kinetic_cut.tts.edge_tts.Communicate", PendingService):
                    with self.assertRaises(InterruptedError):
                        tts.synthesize_speech("Pending request", "en-US-GuyNeural", output_path=output, cancel_check=cancel.is_set)
                self.assertTrue(started.is_set())
                self.assertLess(time.monotonic() - begin, .8)
                self.assertFalse(output.exists())
                self.assertEqual(list(Path(directory).iterdir()), [])
            finally:
                timer.cancel()

    def test_cancel_reaps_owned_audio_process(self):
        cancel = threading.Event()
        timer = threading.Timer(.12, cancel.set)
        timer.start()
        begin = time.monotonic()
        try:
            with self.assertRaises(InterruptedError):
                tts._run_audio_process([sys.executable, "-c", "import time; time.sleep(20)"], cancel.is_set)
            self.assertLess(time.monotonic() - begin, 2)
        finally:
            timer.cancel()

    def test_batch_cancel_prevents_concat_and_removes_only_owned_parts(self):
        cancel = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owner_audio = root / "existing-dialogue.mp3"
            owner_audio.write_bytes(b"owner audio")
            target = root / "new.mp3"
            calls = []
            def first_batch(text, *args, **kwargs):
                calls.append(text)
                Path(kwargs["output_path"]).write_bytes(b"chunk")
                cancel.set()
            with patch.object(tts, "synthesize_speech", first_batch), patch.object(tts, "_run_audio_process") as encoder:
                with self.assertRaises(InterruptedError):
                    tts.synthesize_dialogue_batches("First sentence. " * 100, output_path=target, cancel_check=cancel.is_set)
            self.assertEqual(len(calls), 1)
            encoder.assert_not_called()
            self.assertFalse(target.exists())
            self.assertEqual(owner_audio.read_bytes(), b"owner audio")
            self.assertEqual(list(root.iterdir()), [owner_audio])

    def test_same_text_concurrent_requests_have_independent_temporary_files(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "same.mp3"
            barrier = threading.Barrier(2)
            work_targets = []
            failures = []
            async def write_audio(text, voice, rate, pitch, path, cancel_check=None):
                work_targets.append(path)
                barrier.wait(timeout=2)
                path.write_bytes(b"complete-speech")
            def request():
                try:
                    tts.synthesize_speech("Same preview", "en-US-GuyNeural", output_path=target)
                except Exception as err:
                    failures.append(err)
            with patch.object(tts, "_synthesize_async", write_audio):
                workers = [threading.Thread(target=request) for _ in range(2)]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join(3)
            self.assertEqual(failures, [])
            self.assertEqual(len(set(work_targets)), 2)
            self.assertEqual(target.read_bytes(), b"complete-speech")
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_failure_restores_controls_and_retry_delivers_captured_inputs_on_gui_thread(self):
        dialog = TTSDialogueDialog(initial_text="Original script")
        dialog.show()
        error_threads = []
        received = []
        def warning(*args):
            error_threads.append(QThread.currentThread())
        with patch("kinetic_cut.tts_dialogue_dialog.synthesize_dialogue_batches", side_effect=RuntimeError("offline")), \
             patch.object(QMessageBox, "critical", warning):
            dialog._on_generate_clicked()
            settle(lambda: not dialog._is_generating)
            self.assertTrue(dialog.generate_btn.isEnabled())
            self.assertFalse(dialog.script_edit.isReadOnly())
            self.assertEqual(error_threads, [self.app.thread()])
        def complete(**kwargs):
            return "ready.mp3"
        dialog.speechGenerated.connect(lambda value: received.append((value, QThread.currentThread())))
        with patch("kinetic_cut.tts_dialogue_dialog.synthesize_dialogue_batches", complete):
            dialog._on_generate_clicked()
            self.assertTrue(dialog.script_edit.isReadOnly())
            dialog.script_edit.setPlainText("Changed after request")
            settle(lambda: dialog.result() == QDialog.Accepted)
        self.assertEqual(received[0][0]["text"], "Original script")
        self.assertEqual(received[0][1], self.app.thread())
        dialog.deleteLater()

    def test_repeated_preview_cancel_generate_does_not_retain_payloads_or_deliver_preview(self):
        dialog = TTSDialogueDialog(initial_text="A preview sentence.")
        dialog.show()
        preview_started = threading.Event()
        release = threading.Event()
        received = []
        def preview(**kwargs):
            preview_started.set()
            release.wait(2)
            return "obsolete-preview.mp3"
        def dialogue(**kwargs):
            return "dialogue.mp3"
        with patch("kinetic_cut.tts_dialogue_dialog.synthesize_speech", preview), \
             patch("kinetic_cut.tts_dialogue_dialog.synthesize_dialogue_batches", dialogue), \
             patch("kinetic_cut.media_source.set_media_source") as playback:
            dialog.speechGenerated.connect(received.append)
            dialog._toggle_preview()
            settle(preview_started.is_set)
            previous_worker = weakref.ref(dialog._preview_worker)
            dialog._on_generate_clicked()
            dialog._on_generate_clicked()  # Rapid repeat must not launch another job.
            release.set()
            settle(lambda: not active_dialog_threads())
            self.app.processEvents()
            self.assertEqual(len(received), 1)
            playback.assert_not_called()
            gc.collect()
            self.assertIsNone(previous_worker())
        dialog.deleteLater()

    def test_canceled_cached_request_never_consumes_or_deletes_existing_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            cached = Path(directory) / "speech.mp3"
            cached.write_bytes(b"valid existing speech")
            with self.assertRaises(InterruptedError):
                tts.synthesize_speech("Cached", output_path=cached, cancel_check=lambda: True)
            with self.assertRaises(InterruptedError):
                tts.synthesize_dialogue_batches("Cached", output_path=cached, cancel_check=lambda: True)
            self.assertEqual(cached.read_bytes(), b"valid existing speech")


class TestTitleTTSCancellation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.window = MainWindow()
        self.title = TimelineItem("voice-title", "", "video_1", 0, 2, role="title",
                                  title_text="Original title speech", tts_enabled=True)
        self.window.project.timeline.append(self.title)
        self.window.timeline.select_ids({self.title.id}, self.title.id)
        self.window.inspector.select(self.title.id)
        self.window.commit_history()
        self.window.request_waveform = lambda media: None
        self.generated_media = MediaItem("generated-voice", "dummy-speech.wav", "audio", "Speech", 3, has_audio=True)

    def tearDown(self):
        self.window.inspector.cancel_title_tts()
        settle(lambda: not self.window._workers)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_cancel_title_generation_is_responsive_no_insertion(self):
        started = threading.Event()
        cancelled = threading.Event()
        heartbeats = []
        def pending(*args, **kwargs):
            started.set()
            while not kwargs["cancel_check"]():
                time.sleep(.01)
            cancelled.set()
            raise InterruptedError("Cancelled")
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: heartbeats.append(time.monotonic()))
        timer.start()
        with patch("kinetic_cut.properties.synthesize_speech", pending), patch("kinetic_cut.properties.probe") as probing:
            begin = time.monotonic()
            self.window.inspector.generate_title_tts()
            self.assertLess(time.monotonic() - begin, .1)
            settle(lambda: started.is_set() and len(heartbeats) >= 3)
            self.assertIn("Cancel", self.window.inspector.title_tts_generate_btn.text())
            self.window.inspector.generate_title_tts()
            settle(cancelled.is_set)
            settle(lambda: not self.window._workers)
            probing.assert_not_called()
        timer.stop()
        self.assertEqual(self.window.project.media, [])
        self.assertEqual(self.window.project.timeline, [self.title])

    def test_title_jobs_discard_changed_deleted_locked_or_switched_destinations(self):
        for change in ("title", "delete", "lock", "project", "page", "closing"):
            with self.subTest(change=change):
                original = self.window.project
                original.timeline = [self.title]
                self.title.title_text = "Original title speech"
                original.track_states["video_1"]["locked"] = False
                self.window.current_page = 0
                self.window._closing = False
                self.window.inspector.item_id = self.title.id
                started = threading.Event()
                release = threading.Event()
                def delayed(*args, **kwargs):
                    started.set()
                    release.wait(2)
                    return "dummy-speech.wav"
                with patch("kinetic_cut.properties.synthesize_speech", delayed), \
                     patch("kinetic_cut.properties.probe", return_value=self.generated_media):
                    self.window.inspector.generate_title_tts()
                    settle(started.is_set)
                    if change == "title":self.title.title_text = "Changed title"
                    elif change == "delete":original.timeline.clear()
                    elif change == "lock":original.track_states["video_1"]["locked"] = True
                    elif change == "project":self.window.project = Project()
                    elif change == "page":self.window.current_page = 1
                    elif change == "closing":self.window._closing = True
                    release.set()
                    settle(lambda: not self.window._workers)
                self.assertEqual(original.media, [])
                self.assertFalse(any(clip.media_id == self.generated_media.id for clip in original.timeline))
                self.window.project = original
        self.window._closing = False
        self.window.current_page = 0

    def test_valid_linked_title_generation_commits_once_and_undo_redo_preserve_link(self):
        before = self.window._history_index
        with patch("kinetic_cut.properties.synthesize_speech", return_value="dummy-speech.wav"), \
             patch("kinetic_cut.properties.probe", return_value=self.generated_media):
            self.window.inspector.generate_title_tts()
            settle(lambda: not self.window._workers)
        self.assertEqual(self.window._history_index, before + 1)
        linked = [item for item in self.window.project.timeline if item.media_id == self.generated_media.id]
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0].link_id, self.title.link_id)
        self.assertEqual(self.title.duration, self.generated_media.duration)
        self.window.undo()
        self.assertEqual(len(self.window.project.timeline), 1)
        self.window.redo()
        self.assertEqual(len(self.window.project.timeline), 2)

    def test_preview_cancel_on_selection_switch_cannot_start_old_audio(self):
        started = threading.Event()
        release = threading.Event()
        def delayed(*args, **kwargs):
            started.set()
            release.wait(2)
            return "obsolete-preview.wav"
        with patch("kinetic_cut.properties.synthesize_speech", delayed), \
             patch("kinetic_cut.properties.set_media_source") as playback:
            self.window.inspector.preview_title_tts()
            settle(started.is_set)
            self.window.inspector.select("")
            release.set()
            settle(lambda: not self.window._workers)
            playback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
