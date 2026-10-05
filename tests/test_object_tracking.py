import copy
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import av
import numpy as np

from kinetic_cut import object_tracking as tracking
from kinetic_cut.model import MediaItem, TimelineItem
from kinetic_cut.vocal_component import Cancelled


def fixture_frame(index, *, occluded=False, duplicate=False):
    rng = np.random.default_rng(810)
    background = rng.random((144, 216), dtype=np.float32) * .10 + .08
    texture = np.random.default_rng(811).random((28, 36), dtype=np.float32) * .75 + .2
    width = 36 + index // 6
    height = 28 + index // 11
    x, y = 24 + index * 2, 30 + index // 3
    texture = tracking._resize(texture, width, height)
    if not occluded:
        background[y:y + height, x:x + width] = texture
    if duplicate:
        background[100:100 + height, 18:18 + width] = texture
    return background, [x / 216, y / 144, width / 216, height / 144]


def video(path, count=45, fps=15, occlusion=(), offset=0):
    with av.open(str(path), "w") as container:
        stream = container.add_stream("ffv1", rate=fps)
        stream.width = 216
        stream.height = 144
        stream.pix_fmt = "bgr0"
        for index in range(count):
            gray, _ = fixture_frame(index, occluded=index in occlusion)
            rgb = np.repeat(np.clip(gray * 255, 0, 255).astype(np.uint8)[..., None], 3, axis=2)
            frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            frame.pts = index + offset
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return MediaItem("source", str(path), "video", "Moving target", count / fps, 216, 144, fps)


class ObjectTrackingTests(unittest.TestCase):
    def test_translation_independent_size_changes_and_distractor(self):
        first, region = fixture_frame(0)
        tracker = tracking.RegionTracker(first, region)
        for index in range(1, 35):
            frame, expected = fixture_frame(index)
            # A different textured object remains visible in the search window.
            frame[90:116, 110:142] = np.random.default_rng(900).random((26, 32))
            result = tracker.update(frame)
            self.assertEqual(result["status"], "tracked", (index, result))
            np.testing.assert_allclose(result["box"], expected, atol=.012)
        self.assertGreater(result["box"][2], region[2] * 1.1)
        self.assertGreater(result["box"][3], region[3])

    def test_occlusion_is_explicit_and_recovery_keeps_identity(self):
        frame, region = fixture_frame(0)
        tracker = tracking.RegionTracker(frame, region)
        for index in range(1, 5):
            tracker.update(fixture_frame(index)[0])
        for index in range(5, 8):
            result = tracker.update(fixture_frame(index, occluded=True)[0])
            self.assertEqual(result["status"], "lost")
        frame, expected = fixture_frame(8)
        result = tracker.update(frame)
        self.assertEqual(result["status"], "tracked")
        np.testing.assert_allclose(result["box"], expected, atol=.012)
        frame, region = fixture_frame(0, duplicate=True)
        ambiguous = tracking.RegionTracker(frame, region, search_radius=.6).update(frame)
        self.assertEqual(ambiguous["status"], "lost")
        # Nonzero uniform cover used to turn numerical NCC residue into 1.0.
        flat = np.full_like(frame, .17)
        covered = tracking.RegionTracker(frame, region).update(flat)
        self.assertEqual(covered["status"], "lost")
        self.assertEqual(covered["confidence"], 0)

    def test_bidirectional_trim_speed_manual_corrections_and_portability(self):
        with tempfile.TemporaryDirectory() as directory:
            media = video(Path(directory) / "source.mkv", occlusion=range(19, 22))
            item = TimelineItem("clip", media.id, "video_1", 10, .9, in_point=.4, speed=2)
            reference = 12 / 15
            correction = 25 / 15
            _, region = fixture_frame(12)
            _, corrected = fixture_frame(25)
            progress = []
            result = tracking.analyze(media, item, reference, region,
                                      anchors=[dict(time=correction, box=corrected)],
                                      progress=lambda percent, message: progress.append((percent, message)), sample_fps=15)
            self.assertTrue(tracking.validate(result))
            self.assertTrue(tracking.valid(result, media, item))
            self.assertEqual(result["source_start"], .4)
            self.assertEqual(result["source_end"], 2.2)
            self.assertEqual(tracking.sample(result, reference)["status"], "manual")
            self.assertEqual(tracking.sample(result, correction)["status"], "manual")
            self.assertIsNone(tracking.sample(result, .39))
            self.assertIsNone(tracking.sample(result, 2.21))
            self.assertEqual(progress[-1][0], 100)
            self.assertTrue(any(record["status"] == "lost" for record in result["frames"]))
            for index in (6, 9, 12, 24, 25, 30, 33):
                point = tracking.sample(result, index / 15)
                self.assertNotEqual(point["status"], "lost", (index, point))
                np.testing.assert_allclose(point["box"], fixture_frame(index)[1], atol=.018)
            shifted = copy.deepcopy(item)
            shifted.start = 80
            shifted.in_point = .8
            shifted.duration = .6
            self.assertTrue(tracking.valid(result, media, shifted))
            source_time = shifted.source_time(80.2)
            np.testing.assert_allclose(tracking.sample(result, source_time)["box"],
                                       tracking.sample(result, 1.2)["box"], atol=1e-6)
            shifted.duration = 2
            self.assertFalse(tracking.valid(result, media, shifted))
            encoded = json.dumps(result)
            self.assertNotIn(str(Path(directory)), encoded)
            self.assertLess(len(encoded.encode()), tracking.MAX_BYTES)
            self.assertTrue(tracking.validate(json.loads(encoded)))

    def test_source_identity_caches_reads_and_preserves_normal_relink(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "large.bin"
            source.write_bytes(bytes(range(256)) * 4000)
            media = MediaItem("a", str(source), "video", "a", 2, 120, 80)
            tracking._digest.cache_clear()
            with patch.object(tracking, "_source", wraps=tracking._source) as reads:
                before = tracking.fingerprint(media)
                self.assertEqual(tracking.fingerprint(media), before)
                self.assertEqual(reads.call_count, 1)
            replacement = Path(directory) / "relinked.bin"
            shutil.copy2(source, replacement)
            relink = copy.copy(media)
            relink.path = str(replacement)
            self.assertEqual(tracking.fingerprint(relink), before)
            # Mtime makes even an unsampled middle-only same-size edit invalid.
            with replacement.open("r+b") as stream:
                stream.seek(350001)
                stream.write(b"changed")
            os.utime(replacement, ns=(before["mtime_ns"] + 1000000, before["mtime_ns"] + 1000000))
            self.assertNotEqual(tracking.fingerprint(relink), before)
            # Replacing the same path while preserving mtime must not reuse the
            # old cached digest: inode/creation metadata is part of cache keys.
            other = Path(directory) / "replacement.bin"
            other.write_bytes(b"\xff" * before["size"])
            os.utime(other, ns=(before["mtime_ns"], before["mtime_ns"]))
            other.replace(source)
            self.assertNotEqual(tracking.fingerprint(media), before)

    def test_sample_interpolation_loss_boundaries_and_malformed_data(self):
        frames = [dict(time=0, box=[.1, .1, .2, .2], confidence=1, status="manual"),
                  dict(time=1, box=[.3, .2, .3, .2], confidence=.8, status="tracked"),
                  dict(time=2, box=[.4, .3, .3, .2], confidence=.1, status="lost"),
                  dict(time=3, box=[.5, .3, .3, .2], confidence=.9, status="tracked")]
        analysis = dict(version=1, sample_fps=15, source_start=0, source_end=3, frames=frames)
        self.assertTrue(tracking.validate(analysis))
        np.testing.assert_allclose(tracking.sample(analysis, .5)["box"], [.2, .15, .25, .2])
        self.assertEqual(tracking.sample(analysis, 1.5)["status"], "lost")
        self.assertEqual(tracking.sample(analysis, 2.5)["status"], "lost")
        self.assertEqual(tracking.sample(analysis, 3)["status"], "tracked")
        self.assertIsNone(tracking.sample(analysis, 3.1))
        self.assertIsNone(tracking.sample(analysis, float("nan")))
        for mutation in (lambda a: a["frames"].reverse(),
                         lambda a: a["frames"][1].update(time=0),
                         lambda a: a["frames"][1].update(box=[0, 0, 5, 1]),
                         lambda a: a.update(sample_fps=61)):
            corrupt = copy.deepcopy(analysis)
            mutation(corrupt)
            self.assertFalse(tracking.validate(corrupt))

    def test_analysis_limits_featureless_selection_and_prompt_cancellation(self):
        blank = np.ones((100, 120), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "featureless"):
            tracking.RegionTracker(blank, [.1, .1, .2, .2])
        with tempfile.TemporaryDirectory() as directory:
            media = video(Path(directory) / "source.mkv")
            item = TimelineItem("clip", media.id, "video_1", 0, 3)
            region = fixture_frame(0)[1]
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(Cancelled):
                tracking.analyze(media, item, 0, region, cancel=cancel)
            cancel.clear()
            def stop(percent, message):
                cancel.set()
            with self.assertRaises(Cancelled):
                tracking.analyze(media, item, 0, region, progress=stop, cancel=cancel)
            # Both cancellation paths close source/decoder before returning.
            renamed = Path(directory) / "renamed.mkv"
            Path(media.path).rename(renamed)
            renamed.rename(media.path)
            for keywords in (dict(sample_fps=61), dict(search_radius=2), dict(confidence_threshold=1),
                             dict(anchors=[dict(time=4, box=region)])):
                with self.assertRaises(ValueError):
                    tracking.analyze(media, item, 0, region, **keywords)
            item.duration = 601
            with self.assertRaisesRegex(ValueError, "10 minutes"):
                tracking.analyze(media, item, 0, region)

    def test_shared_windows_handle_allows_rename_during_open_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.bin"
            path.write_bytes(b"shared source")
            renamed = Path(directory) / "renamed.bin"
            with tracking._source(path) as stream:
                path.rename(renamed)
                self.assertEqual(stream.read(6), b"shared")
                stream.seek(-6, os.SEEK_END)
                self.assertEqual(stream.read(6), b"source")
            renamed.unlink()

    def test_still_image_region_and_manual_animation_use_no_video_decoder(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            frame, region = fixture_frame(0)
            Image.fromarray((frame * 255).astype(np.uint8)).save(source)
            media = MediaItem("image", str(source), "image", "Image", 0, 216, 144)
            item = TimelineItem("clip", media.id, "video_1", 8, 4, in_point=2, speed=2)
            with patch.object(tracking, "_Frames", side_effect=AssertionError("No video decoder for images")):
                result = tracking.analyze(media, item, 4, region)
            self.assertTrue(tracking.valid(result, media, item))
            self.assertTrue(tracking.validate(result))
            for time in (2, 4, 7, 10):
                np.testing.assert_allclose(tracking.sample(result, time)["box"], region)
            changed = [.4, .3, .2, .3]
            result = tracking.analyze(media, item, 4, region, anchors=[dict(time=8, box=changed)])
            np.testing.assert_allclose(tracking.sample(result, 6)["box"],
                                       [(a + b) / 2 for a, b in zip(region, changed)])
            source.rename(Path(directory) / "moved.png")

    def test_120fps_source_and_nonzero_presentation_start_use_source_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            media = video(Path(directory) / "high-fps.mkv", fps=120, offset=360)
            item = TimelineItem("clip", media.id, "video_1", 5, .15, in_point=.025, speed=2)
            _, region = fixture_frame(15)
            result = tracking.analyze(media, item, .125, region, sample_fps=60)
            self.assertTrue(tracking.valid(result, media, item))
            self.assertEqual(result["sample_fps"], 60)
            for index in (3, 9, 15, 25, 33, 39):
                point = tracking.sample(result, index / 120)
                self.assertNotEqual(point["status"], "lost", (index, point))
                np.testing.assert_allclose(point["box"], fixture_frame(index)[1], atol=.016)

    def test_gradual_appearance_adapts_without_learning_occlusion_or_distractor(self):
        rng = np.random.default_rng(441)
        original = rng.random((32, 42), dtype=np.float32) * .8 + .15
        changed = rng.random((32, 42), dtype=np.float32) * .8 + .15
        background = rng.random((120, 200), dtype=np.float32) * .08 + .06
        first = background.copy(); first[34:66, 24:66] = original
        tracker = tracking.RegionTracker(first, [24 / 200, 34 / 120, 42 / 200, 32 / 120])
        for index in range(1, 31):
            fraction = index / 30
            frame = background.copy()
            texture = original * (1 - fraction) + changed * fraction
            x = 24 + index * 2
            frame[34:66, x:x + 42] = texture
            # A different visible textured distractor must not attract the box.
            frame[88:112, 110:146] = rng.random((24, 36))
            result = tracker.update(frame)
            self.assertEqual(result["status"], "tracked", (index, result))
            np.testing.assert_allclose(result["box"], [x / 200, 34 / 120, 42 / 200, 32 / 120], atol=.012)
        learned = tracker.template.copy()
        for value in (.15, .30, .60):
            covered = np.full_like(background, value)
            result = tracker.update(covered)
            self.assertEqual(result["status"], "lost")
            np.testing.assert_array_equal(tracker.template, learned)
        recovered = background.copy(); recovered[34:66, 92:134] = changed
        result = tracker.update(recovered)
        self.assertEqual(result["status"], "tracked")
        np.testing.assert_allclose(result["box"], [92 / 200, 34 / 120, 42 / 200, 32 / 120], atol=.012)


if __name__ == "__main__":
    unittest.main()
