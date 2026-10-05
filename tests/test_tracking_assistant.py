import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PySide6.QtCore import QEvent, QThreadPool
from PySide6.QtWidgets import QApplication

from kinetic_cut.assistant_api import EditorAPI, TOOLS, revision
from kinetic_cut.model import MediaItem, Project, TimelineItem
from kinetic_cut.object_tracking import analyze
from kinetic_cut.tracking_effect import MODES, default_effect
from kinetic_cut.vocal_component import Cancelled


class TrackingAssistantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.directory = tempfile.TemporaryDirectory()
        self.source = Path(self.directory.name) / "source.png"
        Image.new("RGB", (160, 100), "#e05020").save(self.source)
        self.w = MainWindow()
        self.w.show()
        self.w.autosave_timer.stop()
        self.api = EditorAPI(self.w)
        self.region = [.2, .25, .3, .35]
        self.reset_project()
        self.analysis = analyze(self.w.project.media[0], self.w.project.timeline[0], .5, self.region)

    def tearDown(self):
        if getattr(self.w, "_tracking_cancel", None):
            self.w._tracking_cancel.set()
        self.w.close()
        QThreadPool.globalInstance().waitForDone(10000)
        self.w.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.directory.cleanup()

    def reset_project(self):
        self.w.transport.closed = False
        self.w.current_page = 0
        media = MediaItem("m", str(self.source), "image", "source", width=160, height=100)
        item = TimelineItem("clip", media.id, "video_1", 0, 2)
        self.w.set_project(Project(media=[media], timeline=[item]))
        self.app.processEvents()

    def submit(self, **changes):
        values = dict(revision=revision(self.w.project), item_id="clip",
                      reference_source_time=.5, region=self.region)
        values.update(changes)
        return self.api.call_track_object(**values)

    def wait(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertTrue(predicate(), "Asynchronous job did not settle")

    def settled(self, job_id):
        self.wait(lambda: self.api.jobs[job_id]["state"] not in ("Running", "Cancelling")
                  and not self.api.jobs[job_id]["cancellable"])
        return self.api.jobs[job_id]

    def blocked(self):
        started, release = threading.Event(), threading.Event()
        analysis = copy.deepcopy(self.analysis)
        def work(media, item, reference, region, anchors=None, progress=None, cancel=None, **kwargs):
            self.assertIsNot(media, self.w.project.media[0])
            self.assertIsNot(item, self.w.project.timeline[0])
            progress(20, "Test analysis started")
            started.set()
            while not release.wait(.01):
                if cancel.is_set():
                    raise Cancelled("Cancelled test analysis")
            if cancel.is_set():
                raise Cancelled("Cancelled test analysis")
            return analysis
        return started, release, work

    def test_discoverable_schema_and_capabilities_match_available_modes(self):
        schema = next(tool["inputSchema"] for tool in TOOLS if tool["name"] == "track_object")
        self.assertEqual(schema["required"], ["revision", "item_id", "reference_source_time", "region"])
        self.assertEqual(schema["properties"]["mode"]["enum"], list(MODES))
        self.assertIn("Follow Crop", schema["properties"]["mode"]["enum"])
        self.assertEqual(schema["properties"]["sample_fps"]["maximum"], 60)
        self.assertFalse(schema["additionalProperties"])
        capabilities = self.api.call_get_capabilities()["object_tracking"]
        self.assertEqual(capabilities["tool"], "track_object")
        self.assertEqual(capabilities["cancel_tool"], "tracking_job_control")
        self.assertEqual(capabilities["modes"], list(MODES))
        self.assertIn("source seconds", capabilities["coordinates"])

    def test_real_image_async_success_one_undo_step_and_correction(self):
        before = copy.deepcopy(self.w.project)
        history_count = len(self.w._history)
        started = self.submit(mode="Label", properties=dict(label="Player", font_size=34, color="#f0a020"))
        self.assertEqual(started["state"], "Running")
        complete = self.settled(started["id"])
        self.assertEqual(complete["state"], "Complete", complete)
        effect = self.w.project.timeline[0].effects[0]
        self.assertEqual(effect["label"], "Player")
        self.assertEqual(effect["mode"], "Label")
        self.assertFalse(effect["loss_reviewed"])
        self.assertEqual(len(self.w._history), history_count + 1)
        self.assertEqual(complete["revision"], revision(self.w.project))
        self.assertNotIn("analysis", complete)
        self.w.undo()
        self.assertEqual(self.w.project.timeline[0].effects, before.timeline[0].effects)
        self.w.redo()
        corrected = self.submit(mode="Circle", existing_effect_index=0,
                                anchors=[dict(time=1.5, box=[.4, .3, .3, .3])])
        complete = self.settled(corrected["id"])
        self.assertEqual(complete["state"], "Complete", complete)
        self.assertEqual(len(self.w.project.timeline[0].effects), 1)
        self.assertEqual(self.w.project.timeline[0].effects[0]["mode"], "Circle")
        self.assertEqual(complete["effect_index"], 0)
        following = self.submit(mode="Follow Crop", existing_effect_index=0,
                                properties=dict(width=60, height=60))
        complete = self.settled(following["id"])
        self.assertEqual(complete["state"], "Complete", complete)
        self.assertEqual(self.w.project.timeline[0].effects[0]["loss_policy"], "Hold")
        unchanged_mode = self.settled(self.submit(existing_effect_index=0)["id"])
        self.assertEqual(unchanged_mode["state"], "Complete", unchanged_mode)
        self.assertEqual(self.w.project.timeline[0].effects[0]["mode"], "Follow Crop")

    def test_stale_revision_locked_source_invalid_properties_reject_before_worker(self):
        before = self.w.project.to_dict()
        with self.assertRaisesRegex(ValueError, "Project changed"):
            self.submit(revision="old")
        self.w.project.track_states["video_1"]["locked"] = True
        with self.assertRaisesRegex(ValueError, "unlocked"):
            self.submit()
        self.w.project.track_states["video_1"]["locked"] = False
        for changes in (dict(properties=dict(analysis={})), dict(properties=dict(loss_reviewed=True)),
                        dict(properties=dict(width=-1)), dict(region=[.9, .2, .3, .3]),
                        dict(anchors=[dict(time=20, box=self.region)]), dict(sample_fps=61),
                        dict(existing_effect_index=0)):
            with self.assertRaises(ValueError):
                self.submit(**changes)
        self.assertEqual(self.w.project.to_dict(), before)
        self.assertFalse(self.api.jobs)

    def test_late_result_rejects_project_clip_media_lock_page_and_closed_state(self):
        mutations = [lambda: setattr(self.w.project, "name", "Edited"),
                     lambda: setattr(self.w.project.timeline[0], "duration", 1.8),
                     lambda: setattr(self.w.project.media[0], "name", "Relinked"),
                     lambda: self.w.project.track_states["video_1"].update(locked=True),
                     lambda: setattr(self.w, "current_page", 1),
                     lambda: setattr(self.w.transport, "closed", True),
                     lambda: self.w.set_project(copy.deepcopy(self.w.project))]
        for mutate in mutations:
            self.reset_project()
            started, release, work = self.blocked()
            with patch("kinetic_cut.object_tracking.analyze", side_effect=work):
                job = self.submit(mode="Circle")
                self.wait(started.is_set)
                self.assertEqual(self.api.jobs[job["id"]]["progress"], 20)
                mutate()
                snapshot = self.w.project.to_dict()
                history = len(self.w._history)
                release.set()
                result = self.settled(job["id"])
            self.assertEqual(result["state"], "Failed", result)
            self.assertIn("changed", result["error"])
            self.assertEqual(self.w.project.to_dict(), snapshot)
            self.assertEqual(len(self.w._history), history)
        self.w.transport.closed = False

    def test_cancel_job_progress_concurrent_guard_and_no_partial_edit(self):
        before = self.w.project.to_dict()
        history = len(self.w._history)
        started, release, work = self.blocked()
        with patch("kinetic_cut.object_tracking.analyze", side_effect=work):
            job = self.submit(mode="Arrow")
            self.wait(started.is_set)
            with self.assertRaisesRegex(ValueError, "Another object analysis"):
                self.submit()
            cancelled = self.api.call_tracking_job_control(job["id"], "cancel")
            self.assertEqual(cancelled["state"], "Cancelling")
            result = self.settled(job["id"])
        self.assertEqual(result["state"], "Cancelled")
        self.assertFalse(result["cancellable"])
        self.assertIsNone(self.w._tracking_cancel)
        self.assertEqual(self.w.project.to_dict(), before)
        self.assertEqual(len(self.w._history), history)
        with self.assertRaises(ValueError):
            self.api.call_tracking_job_control(job["id"], "cancel")

    def test_editor_close_sets_cancel_and_never_applies_late_analysis(self):
        before = self.w.project.to_dict()
        before_revision = revision(self.w.project)
        started, release, work = self.blocked()
        with patch("kinetic_cut.object_tracking.analyze", side_effect=work):
            job = self.submit(mode="Rectangle")
            self.wait(started.is_set)
            event = self.w._tracking_cancel
            self.w.close()
            self.assertTrue(event.is_set())
            result = self.settled(job["id"])
        self.assertEqual(result["state"], "Cancelled")
        # Normal close autosave can touch modified_at; the edit revision and
        # actual project content remain unchanged by the cancelled worker.
        self.assertEqual(revision(self.w.project), before_revision)
        after = self.w.project.to_dict()
        before.pop("modified_at"); after.pop("modified_at")
        self.assertEqual(after, before)

    def test_invalid_trajectory_failed_analysis_and_unsafe_censor_loss_are_atomic(self):
        before = self.w.project.to_dict()
        history = len(self.w._history)
        invalid = copy.deepcopy(self.analysis)
        invalid["frames"][0]["box"] = [0, 0, 2, 2]
        lost = copy.deepcopy(self.analysis)
        lost["frames"][1]["status"] = "lost"
        scenarios = [(dict(return_value=invalid), {}),
                     (dict(side_effect=ValueError("Synthetic decoder error")), {}),
                     (dict(return_value=lost), dict(mode="Censor Bar", properties=dict(loss_policy="Hide")))]
        for mocked, changes in scenarios:
            with patch("kinetic_cut.object_tracking.analyze", **mocked):
                result = self.settled(self.submit(**changes)["id"])
            self.assertEqual(result["state"], "Failed", result)
            self.assertEqual(self.w.project.to_dict(), before)
            self.assertEqual(len(self.w._history), history)
        with patch("kinetic_cut.object_tracking.analyze", return_value=lost):
            result = self.settled(self.submit(mode="Blur")["id"])
        self.assertEqual(result["state"], "Complete", result)
        self.assertEqual(result["lost_samples"], 1)
        self.assertEqual(self.w.project.timeline[0].effects[0]["loss_policy"], "Full frame")

    def test_follow_crop_validates_proposed_final_combination_before_install(self):
        self.w.project.timeline[0].effects = [dict(name="Remove Person Background", enabled=True)]
        before = self.w.project.to_dict()
        history = len(self.w._history)
        result = self.settled(self.submit(mode="Follow Crop")["id"])
        self.assertEqual(result["state"], "Failed", result)
        self.assertIn("Follow Crop", result["error"])
        self.assertEqual(self.w.project.to_dict(), before)
        self.assertEqual(len(self.w._history), history)


if __name__ == "__main__":
    unittest.main()
