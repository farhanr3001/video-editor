"""Bin drops place the whole source, whatever timeline marks the project holds.

Regression: pressing I (Mark in) at a timeline playhead of 33.5 s stored an
invisible project.mark_in. Every later Media Pool / Power Bin drop then used it
as the SOURCE in-point, so short sounds collapsed to 0.1 s and long media
started mid-file, in that project only, across saves and reopens.
"""
import os
import tempfile
import unittest

os.environ.setdefault('KINETIC_CUT_HOME', tempfile.mkdtemp(prefix='kc-insert-marks-'))

from kinetic_cut.media_insert import plan
from kinetic_cut.model import MediaItem, Project


def sound(seconds, name='bonk.mp3'):
    return MediaItem('a-' + name, 'C:/fixtures/' + name, 'audio', name, seconds, 0, 0, 0., True)


def video(seconds=30.):
    return MediaItem('v1', 'C:/fixtures/clip.mp4', 'video', 'clip.mp4', seconds, 1920, 1080, 60., True)


def image():
    return MediaItem('i1', 'C:/fixtures/still.png', 'image', 'still.png', 0., 800, 600, 0., False)


class InsertIgnoresTimelineMarks(unittest.TestCase):
    def placed(self, project, asset, track='', start=40.):
        stage, ids, _ = plan(project, [asset], track, start)
        return [i for i in stage.timeline if i.id in ids]

    def test_short_sound_keeps_its_full_length_with_a_mark_in_past_its_end(self):
        project = Project(); project.mark_in = 33.4770702550891; project.mark_out = 0.
        item, = self.placed(project, sound(.470204), 'audio_1')
        self.assertEqual((item.in_point, item.duration, item.start), (0., .470204, 40.))

    def test_long_sound_and_video_start_at_their_first_frame(self):
        project = Project(); project.mark_in = 5.; project.mark_out = 9.
        item, = self.placed(project, sound(18.416313, 'song.mp3'), 'audio_1')
        self.assertEqual((item.in_point, item.duration), (0., 18.416313))
        items = self.placed(project, video(), project.video_tracks[-1])
        self.assertEqual(len(items), 2)
        self.assertEqual({(i.in_point, i.duration) for i in items}, {(0., 30.)})

    def test_marks_are_left_untouched_and_images_keep_their_default_length(self):
        project = Project(); project.mark_in = 12.; project.mark_out = 3.
        item, = self.placed(project, image(), project.video_tracks[-1])
        self.assertEqual((item.in_point, item.duration), (0., 5.))
        self.assertEqual((project.mark_in, project.mark_out), (12., 3.))

    def test_unprobed_zero_length_media_still_gets_a_visible_clip(self):
        item, = self.placed(Project(), sound(0., 'unknown.mp3'), 'audio_1')
        self.assertEqual((item.in_point, item.duration), (0., .1))


if __name__ == '__main__':
    unittest.main()
