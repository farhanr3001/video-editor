"""Source-footage analysis: frames, loudness and shot changes on a synthetic clip with known content."""
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from kinetic_cut import source_analysis as sa
from kinetic_cut.model import MediaItem

app = QApplication.instance() or QApplication([])
FFMPEG = shutil.which('ffmpeg')


def make_clip(path):
    """12 s: red, blue, green, yellow in 3 s blocks; a quiet tone, a loud burst at 7.0-7.6 s, silence 9.0-10.5 s."""
    colors = ['red', 'blue', 'green', 'yellow']
    args = [FFMPEG, '-y', '-loglevel', 'error']
    for color in colors:
        args += ['-f', 'lavfi', '-i', f'color=c={color}:s=320x180:r=30:d=3']
    expr = '(1-between(t\\,9\\,10.5))*(0.02*sin(2*PI*220*t)+between(t\\,7\\,7.6)*0.8*sin(2*PI*440*t))'
    args += ['-f', 'lavfi', '-i', f'aevalsrc=exprs={expr}:s=8000:d=12',
             '-filter_complex', '[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]', '-map', '[v]', '-map', '4:a',
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(path)]
    subprocess.run(args, check=True)


@unittest.skipUnless(FFMPEG, 'ffmpeg is required')
class SourceAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.clip = cls.dir / 'clip.mp4'
        make_clip(cls.clip)
        cls.media = MediaItem(id='m1', path=str(cls.clip), kind='video', name='clip.mp4', duration=12.0,
                              width=320, height=180, fps=30.0, has_audio=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_audio_profile_finds_burst_and_silence(self):
        audio = sa.audio_profile(self.clip, FFMPEG, 0, 12, threading.Event())
        self.assertTrue(audio['available'])
        moments = audio['loud_moments']
        self.assertEqual(len(moments), 1, moments)
        self.assertTrue(6.9 <= moments[0]['peak_time'] <= 7.7, moments[0])
        self.assertGreaterEqual(moments[0]['rise_db'], 8)
        self.assertTrue(any(abs(a - 9.0) < .4 and abs(b - 10.5) < .4 for a, b in audio['silences']), audio['silences'])

    def test_audio_range_offsets_times(self):
        audio = sa.audio_profile(self.clip, FFMPEG, 6, 12, threading.Event())
        self.assertTrue(6.9 <= audio['loud_moments'][0]['peak_time'] <= 7.7)

    def test_shots_found_at_colour_changes(self):
        shots = sa.detect_shots(self.clip, FFMPEG, 0, 12, .3, threading.Event())
        self.assertEqual(shots['cut_count'], 3, shots)
        for found, wanted in zip(shots['cuts'], (3, 6, 9)):
            self.assertAlmostEqual(found, wanted, delta=.2)

    def test_pick_times_modes(self):
        times, _ = sa.pick_times('even', 4, 0, 12)
        self.assertEqual(times, [1.5, 4.5, 7.5, 10.5])
        times, labels = sa.pick_times('shots', 8, 0, 12, shots=[3, 6, 9])
        self.assertEqual(len(times), 4)
        self.assertEqual(labels[0], 'start')
        times, labels = sa.pick_times('loud_moments', 3, 0, 12, moments=[dict(peak_time=7.3, rise_db=20)])
        self.assertEqual(times, [7.3])
        self.assertEqual(sa.pick_times('shots', 3, 0, 12)[0], sa.pick_times('even', 3, 0, 12)[0])

    def test_analyze_builds_labelled_sheet_with_the_right_frames(self):
        out = Path(tempfile.mkdtemp()) / 'cache'
        with patch('kinetic_cut.config.CACHE_DIR', out):
            report = sa.analyze(self.media, FFMPEG, ('frames', 'audio', 'shots'), 0, 12, 'even', 4, None, 320, .3,
                                threading.Event(), lambda *_: None, out / 'source-analysis' / 'job1')
        self.assertEqual(report['shots']['cut_count'], 3)
        self.assertEqual(len(report['audio']['loud_moments']), 1)
        tiles = report['frames']['tiles']
        self.assertEqual([t['time'] for t in tiles], [1.5, 4.5, 7.5, 10.5])
        sheet = QImage(report['frames']['sheet'])
        self.assertFalse(sheet.isNull())
        cell = sheet.height() // 2 if sheet.height() > 200 else sheet.height()
        height = 180 + 0   # 320x180 source scaled to width 320
        cell = height + 30
        wanted = ['red', 'blue', 'green', 'yellow']
        for index, name in enumerate(wanted):
            x = (index % 3) * 320 + 160
            y = (index // 3) * cell + 90
            c = sheet.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            ok = {'red': r > 150 > g and r > b, 'blue': b > 150 > r, 'green': g > 90 and g > r and g > b,
                  'yellow': r > 150 and g > 150 and b < 100}[name]
            self.assertTrue(ok, (name, (r, g, b)))

    def test_frames_at_manual_times_and_audio_only_media(self):
        out = Path(tempfile.mkdtemp()) / 'cache'
        with patch('kinetic_cut.config.CACHE_DIR', out):
            report = sa.analyze(self.media, FFMPEG, ('frames',), 0, 12, 'even', 4, [1.0, 8.0], 320, .3,
                                threading.Event(), lambda *_: None, out / 'source-analysis' / 'job2')
            self.assertEqual(report['frames']['sampling'], 'manual')
            self.assertNotIn('audio', report)
            sound = MediaItem(id='a1', path=str(self.clip), kind='audio', name='s', duration=12.0, has_audio=True)
            report = sa.analyze(sound, FFMPEG, ('frames', 'shots', 'audio'), 0, 12, 'even', 4, None, 320, .3,
                                threading.Event(), lambda *_: None, out / 'source-analysis' / 'job3')
        self.assertIn('note', report['frames'])
        self.assertIn('note', report['shots'])
        self.assertTrue(report['audio']['available'])

    def test_cancel_and_cache_boundary(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            sa.audio_profile(self.clip, FFMPEG, 0, 12, cancel)
        with self.assertRaises(ValueError):
            sa.analyze(self.media, FFMPEG, ('audio',), 0, 12, 'even', 4, None, 320, .3,
                       threading.Event(), lambda *_: None, self.dir / 'elsewhere')


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(FFMPEG, 'ffmpeg is required')
class SourceAnalysisToolTests(unittest.TestCase):
    """The MCP tools: job lifecycle, validation, no change to the project, and a slim get_state."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.clip = cls.dir / 'clip.mp4'
        make_clip(cls.clip)
        cls.pic = cls.dir / 'pic.png'
        QImage(10, 10, QImage.Format_RGB32).save(str(cls.pic))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        from kinetic_cut.model import Project
        from kinetic_cut.ui import MainWindow
        self.w = MainWindow()
        self.w.autosave_timer.stop()
        self.w.settings['ffmpeg'] = FFMPEG
        self.w.set_project(Project(media=[MediaItem('m1', str(self.clip), 'video', 'clip.mp4', 12.0, 320, 180, 30.0, True),
                                          MediaItem('i1', str(self.pic), 'image', 'pic', 1.0, 10, 10)]))

    def tearDown(self):
        import time
        from PySide6.QtCore import QThreadPool
        self.w.close()
        deadline = time.monotonic() + 10
        while self.w._workers and time.monotonic() < deadline:
            app.processEvents()
        QThreadPool.globalInstance().waitForDone(10000)

    def wait(self, api, job_id):
        import time
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            app.processEvents()
            job = api.jobs[job_id]
            if job['state'] not in ('Running', 'Cancelling'):
                return job
            time.sleep(.02)
        self.fail('analysis did not finish')

    def test_get_state_has_no_diagnostics_unless_asked(self):
        from kinetic_cut.assistant_api import EditorAPI
        api = EditorAPI(self.w)
        self.assertNotIn('playback_diagnostics', api.call_get_state())
        self.assertIn('project', api.call_get_state())
        summary = api.call_get_state('summary')
        self.assertNotIn('project', summary)
        self.assertNotIn('playback_diagnostics', summary)
        with self.assertRaises(ValueError):
            api.call_get_state('everything')

    def test_job_lifecycle_returns_report_and_image_without_touching_project(self):
        from kinetic_cut.assistant_api import EditorAPI, revision
        api = EditorAPI(self.w)
        before, playhead = revision(self.w.project), self.w.project.playhead
        job = api.call_analyze_source_media('m1', sample='loud_moments', count=3)
        self.assertEqual(self.wait(api, job['id'])['state'], 'Complete', api.jobs[job['id']])
        self.assertNotIn('loudness_db', str(api.call_get_jobs()))          # job list stays small
        result = api.call_get_source_analysis(job['id'])['_mcp_content']
        import json
        report = json.loads(result[0]['text'])['report']
        self.assertEqual(report['shots']['cut_count'], 3)
        self.assertEqual(report['frames']['sampling'], 'loud_moments')
        self.assertTrue(6.9 <= report['frames']['tiles'][0]['time'] <= 7.7)
        self.assertEqual(result[1]['type'], 'image')
        self.assertEqual(revision(self.w.project), before)
        self.assertEqual(self.w.project.playhead, playhead)

    def test_validation_and_cancel(self):
        from kinetic_cut.assistant_api import EditorAPI
        api = EditorAPI(self.w)
        for bad in (dict(media_id='nope'), dict(media_id='i1'), dict(media_id='m1', kinds=[]),
                    dict(media_id='m1', kinds=['frames', 'frames']), dict(media_id='m1', kinds=['x']),
                    dict(media_id='m1', start=5, end=4), dict(media_id='m1', end=99), dict(media_id='m1', count=13),
                    dict(media_id='m1', timestamps=[20]), dict(media_id='m1', width=50),
                    dict(media_id='m1', sample='random'), dict(media_id='m1', shot_threshold=2)):
            with self.assertRaises(ValueError, msg=bad):
                api.call_analyze_source_media(**bad)
        job = api.call_analyze_source_media('m1', kinds=['shots'])
        with self.assertRaises(ValueError):
            api.call_analyze_source_media('m1', kinds=['audio'])         # one at a time
        api.call_source_analysis_job_control(job['id'])
        self.assertIn(self.wait(api, job['id'])['state'], ('Cancelled', 'Complete'))
        with self.assertRaises(ValueError):
            api.call_source_analysis_job_control(job['id'])
        with self.assertRaises(ValueError):
            api.call_get_source_analysis('unknown')
