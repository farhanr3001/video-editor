"""MCP ergonomics found by a real edit: caption coverage and report, compact status, text edits keep timing."""
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from kinetic_cut.caption_words import retime, set_text
from kinetic_cut.model import Caption, MediaItem, Project, TimelineItem, uid
from tests.test_source_analysis import FFMPEG, make_clip

app = QApplication.instance() or QApplication([])


def words(*spec):
    return [dict(text=t, start=a, end=b) for t, a, b in spec]


class RetimeTests(unittest.TestCase):
    OLD = words(('big', 0, .3), ('dog', .3, .6), ('needs', .6, 1.0), ('fifty', 1.0, 1.6))

    def test_same_count_keeps_every_timing(self):
        got = retime('big dog needs fifty', self.OLD, 'Big Dog needs 50')
        self.assertEqual([(w['start'], w['end']) for w in got], [(0, .3), (.3, .6), (.6, 1.0), (1.0, 1.6)])
        self.assertEqual(got[3]['text'], '50')

    def test_replaced_and_added_words_stay_inside_old_span(self):
        got = retime('big dog needs fifty', self.OLD, 'big dog really needs fifty')
        self.assertEqual(len(got), 5)
        self.assertEqual((got[0]['start'], got[1]['end']), (0, .6))           # untouched words keep their timing
        self.assertTrue(got[2].get('estimated'))
        self.assertTrue(.6 <= got[2]['start'] < got[2]['end'] <= .6 + .06 + 1e-9 or got[2]['end'] <= 1.0)
        self.assertEqual((got[4]['start'], got[4]['end']), (1.0, 1.6))
        starts = [w['start'] for w in got]
        self.assertEqual(starts, sorted(starts))

    def test_shorter_text_and_no_timings(self):
        got = retime('big dog needs fifty', self.OLD, 'big needs fifty')
        self.assertEqual([w['text'] for w in got], ['big', 'needs', 'fifty'])
        self.assertEqual(retime('a b', [], 'a b c'), [])

    def test_set_text_keeps_timings_instead_of_clearing(self):
        caption = Caption('c', 5, 6.6, 'big dog needs fifty', word_timings=self.OLD)
        set_text(caption, 'big dog really needs fifty')
        self.assertEqual(len(caption.word_timings), 5)
        self.assertEqual(caption.text, 'big dog really needs fifty')


class TranscriptSearchTests(unittest.TestCase):
    def test_range_and_text_detail(self):
        from kinetic_cut import transcripts
        media = MediaItem('m1', 'x.mp4', 'video', 'x', 60, 10, 10, 30, True)
        data = dict(timing='word', segments=[dict(start=i * 10., end=i * 10. + 5, text=f'line {i}', words=[dict(text='w')])
                                             for i in range(6)])
        with patch.object(transcripts, 'load', return_value=data), patch.object(transcripts, 'occurrences', return_value=[1]):
            project = Project(media=[media])
            everything = transcripts.search(project, {}, '')
            self.assertEqual(everything['total'], 6)
            ranged = transcripts.search(project, {}, '', start=20, end=36, detail='text')
            self.assertEqual([m['segment'] for m in ranged['matches']], [2, 3])
            self.assertEqual(set(ranged['matches'][0]), {'media_id', 'segment', 'start', 'end', 'text'})
            self.assertIn('words', everything['matches'][0])
            for bad in (dict(detail='x'), dict(start=-1), dict(start=9, end=3), dict(end='a')):
                with self.assertRaises(ValueError):
                    transcripts.search(project, {}, '', **bad)


@unittest.skipUnless(FFMPEG, 'ffmpeg is required')
class ToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.clip = cls.dir / 'clip.mp4'
        make_clip(cls.clip)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.w = MainWindow()
        self.w.autosave_timer.stop()
        self.w.settings['ffmpeg'] = FFMPEG
        video = MediaItem('m1', str(self.clip), 'video', 'clip.mp4', 12., 320, 180, 30., True)
        music = MediaItem('m2', str(self.clip), 'audio', 'music.mp3', 12., 0, 0, 0., True)
        project = Project(media=[video, music])
        v, a = project.video_tracks, project.audio_tracks
        project.timeline = [
            TimelineItem('v1', 'm1', v[0], 0, 12, role='content'),
            TimelineItem('a1', 'm1', a[0], 0, 12, role='normal'),       # a video's own audio, role left at normal
            TimelineItem('a2', 'm2', a[1] if len(a) > 1 else a[0], 0, 12, role='normal'),   # music
        ]
        self.w.set_project(project)

    def tearDown(self):
        from PySide6.QtCore import QThreadPool
        self.w.close()
        deadline = time.monotonic() + 10
        while self.w._workers and time.monotonic() < deadline:
            app.processEvents()
        QThreadPool.globalInstance().waitForDone(10000)

    def wait(self, api, job_id, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            if api.jobs[job_id]['state'] != 'Running':
                return api.jobs[job_id]
            time.sleep(.02)
        self.fail('job did not finish')

    def test_captions_cover_video_audio_and_report_skips(self):
        from kinetic_cut.assistant_api import EditorAPI
        api = EditorAPI(self.w)
        calls = []

        def fake(wav, settings, offset, progress, words_per_card, gap, **kw):
            calls.append(offset)
            return [Caption(uid(), offset, offset + 2, 'hello there'), Caption(uid(), offset + 9, offset + 11.5, 'tail words')], 'fake'
        self.w.timeline.select_ids({'v1'}, 'v1')            # a stray selection must not narrow headless runs
        with patch('kinetic_cut.ui.transcribe', fake):
            job = api.call_editor_command('generate_captions', dict(headless=True, words_per_card=2))
            done = self.wait(api, job['id'])
        self.assertEqual(done['state'], 'Complete', done)
        report = done['report']
        self.assertEqual(report['state'], 'complete')
        self.assertEqual(report['captions'], 2)
        self.assertEqual(report['audio_range'], [0, 12])
        self.assertEqual([s['item_id'] for s in report['sources']], ['a1'])
        self.assertEqual([s['item_id'] for s in report['skipped']], ['a2'])
        self.assertEqual(len(report['caption_ids']), 2)
        self.assertEqual(len(self.w.project.captions), 2)

    def test_refusals_fail_the_job_with_a_reason(self):
        from kinetic_cut.assistant_api import EditorAPI
        self.w.project.track_states.setdefault('subtitle_1', {})['locked'] = True
        api = EditorAPI(self.w)
        job = api.call_editor_command('generate_captions', dict(headless=True))
        done = self.wait(api, job['id'])
        self.assertEqual(done['state'], 'Failed')
        self.assertIn('locked', done['error'])

    def test_command_job_lists_created_title_id(self):
        from kinetic_cut.assistant_api import EditorAPI
        api = EditorAPI(self.w)
        job = api.call_editor_command('add_title_object', dict(name='Text', start=1.0))
        done = self.wait(api, job['id'])
        self.assertEqual(done['state'], 'Complete', done)
        self.assertEqual(len(done['created_ids']), 1)
        self.assertEqual(self.w.project.item_by_id(done['created_ids'][0]).role, 'title')

    def test_get_jobs_is_compact_and_job_id_returns_all(self):
        from kinetic_cut.assistant_api import EditorAPI
        api = EditorAPI(self.w)
        for n in range(8):
            api.jobs[f'j{n}'] = dict(id=f'j{n}', label='x', state='Complete', result='r' * 5000 if n == 7 else 'ok')
        api.jobs['live'] = dict(id='live', label='y', state='Running', blob='b' * 5000)
        jobs = api.call_get_jobs()
        ids = [j['id'] for j in jobs['tasks']]
        self.assertEqual(ids, ['live', 'j3', 'j4', 'j5', 'j6', 'j7'])
        self.assertEqual(jobs['older_finished'], 3)
        self.assertLess(len(json.dumps(jobs['tasks'][1:])), 1500)
        self.assertIn('omitted', next(j for j in jobs['tasks'] if j['id'] == 'j7')['result'])
        self.assertEqual(len(api.call_get_jobs('j7')['tasks'][0]['result']), 5000)
        self.assertEqual(len(api.call_get_jobs(finished=0)['tasks']), 1)
        with self.assertRaises(ValueError):
            api.call_get_jobs('nope')
        with self.assertRaises(ValueError):
            api.call_get_jobs(finished=101)

    def test_state_captions_are_compact_and_section_returns_full(self):
        from kinetic_cut.assistant_api import EditorAPI
        api = EditorAPI(self.w)
        self.w.project.captions = [Caption(f'c{i}', i, i + .9, f'w{i}', word_timings=words(('w', 0, .4))) for i in range(30)]
        state = api.call_get_state()
        project = state['project']
        self.assertEqual(len(project['caption_styles']), 1)
        first = project['captions'][0]
        self.assertNotIn('style', first)
        self.assertNotIn('word_timings', first)
        self.assertEqual((first['style_id'], first['timed_words']), (0, 1))
        full = api.call_get_state('captions')
        self.assertEqual(len(full['caption_styles']), 1)
        self.assertNotIn('style', full['captions'][0])
        self.assertIn('word_timings', full['captions'][0])
        ranged = api.call_get_state('captions', start=10, end=12)['captions']
        self.assertEqual([c['id'] for c in ranged], ['c10', 'c11'])
        self.assertEqual(ranged[0]['word_timings'][0]['text'], 'w')
        with self.assertRaises(ValueError):
            api.call_get_state('captions', start=-1)

    def test_state_all_honours_range(self):
        from kinetic_cut.assistant_api import EditorAPI
        api = EditorAPI(self.w)
        self.w.project.captions = [Caption(f'c{i}', i, i + .9, f'w{i}') for i in range(30)]
        project = api.call_get_state(start=10, end=12)['project']
        self.assertEqual([c['id'] for c in project['captions']], ['c10', 'c11'])
        self.assertIn('range_note', project)
        self.assertEqual(len(api.call_get_state()['project']['captions']), 30)

    def test_mcp_text_edit_keeps_measured_timing(self):
        from kinetic_cut.assistant_api import EditorAPI, revision
        api = EditorAPI(self.w)
        self.w.project.captions = [Caption('c1', 5, 6.6, 'big dog needs fifty', word_timings=RetimeTests.OLD, highlighted_words=[0, 3])]
        rev = revision(self.w.project)
        api.call_apply_edits(rev, [dict(op='update', collection='captions', id='c1', values=dict(text='big dog really needs fifty'))])
        caption = self.w.project.captions[0]
        self.assertEqual([w['text'] for w in caption.word_timings], ['big', 'dog', 'really', 'needs', 'fifty'])
        self.assertEqual((caption.word_timings[0]['end'], caption.word_timings[4]['start']), (.3, 1.0))
        self.assertTrue(caption.word_timings[2]['estimated'])
        self.assertEqual(caption.highlighted_words, [0])          # index 3 now points at a different word
        explicit = [dict(text='x', start=0, end=1)]
        api.call_apply_edits(revision(self.w.project), [dict(op='update', collection='captions', id='c1', values=dict(text='x', word_timings=explicit))])
        self.assertEqual(self.w.project.captions[0].word_timings, explicit)    # caller-supplied timings win

    def test_revision_ignores_background_thumbnails(self):
        from kinetic_cut.assistant_api import revision
        before = revision(self.w.project)
        self.w.project.media[0].thumbnail = 'C:/cache/thumb.png'
        self.assertEqual(revision(self.w.project), before)
        self.w.project.media[0].name = 'renamed'
        self.assertNotEqual(revision(self.w.project), before)


if __name__ == '__main__':
    unittest.main()
