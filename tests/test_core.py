import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen

from kinetic_cut.delivery import WirelessShare
from kinetic_cut.exporter import write_ass
from kinetic_cut.model import Caption, Crop, MediaItem, Project, make_vertical_group, uid
from kinetic_cut.silence import keep_ranges, parse_silences


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.media = MediaItem("m1", "clip.mp4", "video", "clip.mp4", 10, 1920, 1080, 60, True)

    def test_vertical_group_and_split(self):
        project = Project(media=[self.media], timeline=make_vertical_group(self.media))
        self.assertEqual({x.track for x in project.timeline}, {"video_1", "video_2", "video_3", "audio_1"})
        self.assertEqual({x.role for x in project.timeline}, {"background", "content", "facecam", "source_audio"})
        group = project.timeline[0].group_id
        for item in list(project.timeline):
            project.split(item.id, 4)
        self.assertEqual(len(project.timeline), 8)
        self.assertEqual(sorted(i.duration for i in project.timeline), [4, 4, 4, 4, 6, 6, 6, 6])
        self.assertEqual(group, project.timeline[0].group_id)

    def test_project_roundtrip(self):
        project = Project(name="Roundtrip", media=[self.media], timeline=make_vertical_group(self.media))
        project.timeline[1].crop = Crop(.1, .2, .7, .6)
        project.add_track("video")
        project.track_states["video_1"] = {"visible": True, "locked": True, "muted": False}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.kcut"
            project.save(path)
            loaded = Project.load(path)
            self.assertEqual(loaded.name, "Roundtrip")
            self.assertAlmostEqual(loaded.timeline[1].crop.x, .1)
            self.assertEqual(loaded.settings.height, 1920)
            self.assertEqual(loaded.video_tracks, ["video_1","video_2","video_3","video_4"])
            self.assertTrue(loaded.track_states["video_1"]["locked"])

    def test_ripple_ranges_keeps_linked_layers(self):
        project = Project(media=[self.media], timeline=make_vertical_group(self.media))
        project.ripple_ranges(project.timeline[0].group_id, [(0, 2), (5, 8)])
        self.assertEqual(len(project.timeline), 8)
        self.assertAlmostEqual(project.duration, 5)
        self.assertEqual(sorted(set(x.start for x in project.timeline)), [0, 2])

    def test_generic_track_order_and_move(self):
        project=Project(); project.ensure_track_model(); added=project.add_track("video")
        self.assertEqual(added,"video_2")
        self.assertTrue(project.move_track("video_1",1))
        self.assertEqual(project.video_tracks[:2],["video_2","video_1"])
        self.assertEqual(project.track_names[added],"Video 2")


class SilenceTests(unittest.TestCase):
    def test_parse_and_padding(self):
        text = "[silencedetect] silence_start: 1.0\n[silencedetect] silence_end: 2.0 | silence_duration: 1"
        silences = parse_silences(text, 4)
        self.assertEqual(silences, [(1, 2)])
        self.assertEqual(keep_ranges(silences, 4, .1), [(0, 1.1), (1.9, 4)])

    def test_trailing_silence(self):
        self.assertEqual(parse_silences("silence_start: 3.2", 5), [(3.2, 5)])


class CaptionTests(unittest.TestCase):
    def test_ass_escapes_and_animates(self):
        project = Project(captions=[Caption(uid(), 0, 2, "hello {world}")])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "captions.ass"
            write_ass(project, target)
            text = target.read_text(encoding="utf-8-sig")
            self.assertIn(r"hello \{world\}", text)
            self.assertIn(r"\fscx72", text)


class DeliveryTests(unittest.TestCase):
    def test_wireless_share_serves_export_and_download(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "finished-short.mp4"
            target.write_bytes(b"kinetic-cut-test-video")
            share = WirelessShare(str(target))
            try:
                share.start()
                root = f"http://127.0.0.1:{share.server.server_port}"
                with urlopen(root + "/", timeout=3) as response:
                    self.assertIn(b"Download video", response.read())
                with urlopen(root + "/download", timeout=3) as response:
                    self.assertEqual(response.read(), target.read_bytes())
                    self.assertIn("finished-short.mp4", response.headers["Content-Disposition"])
            finally:
                share.stop()


if __name__ == "__main__":
    unittest.main()
