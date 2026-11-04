"""ripple_delete_range, fit_region, insert_clip with_audio, compact timeline state, numeric-string arguments."""
import json
import unittest

from PySide6.QtWidgets import QApplication

from kinetic_cut.assistant_api import EditorAPI, coerce_numbers, edited
from kinetic_cut.model import Caption, MediaItem, Project, TimelineItem

app = QApplication.instance() or QApplication([])


def words(*spec):
    return [dict(text=t, start=a, end=b) for t, a, b in spec]


def base_project():
    video = MediaItem('m1', 'x.mp4', 'video', 'x', 300., 1920, 1080, 60., True)
    sound = MediaItem('m2', 'm.mp3', 'audio', 'm', 60., 0, 0, 0., True)
    silent = MediaItem('m3', 'v.mp4', 'video', 'v', 60., 1920, 1080, 30., False)
    project = Project(media=[video, sound, silent])
    project.add_track('video')
    return project


class RippleDeleteTests(unittest.TestCase):
    def setUp(self):
        self.project = base_project()
        p = self.project
        p.timeline = [
            TimelineItem('v1', 'm1', 'video_1', 0, 10, in_point=100, group_id='g', link_id='g'),
            TimelineItem('a1', 'm1', 'audio_1', 0, 10, in_point=100, role='source_audio', group_id='g', link_id='g'),
            TimelineItem('v2', 'm1', 'video_2', 0, 10, in_point=100),
        ]
        p.captions = [Caption('c1', 1, 2, 'one two'),
                      Caption('c2', 5, 7, 'a b c d', word_timings=words(('a', 0, .5), ('b', .5, 1), ('c', 1, 1.5), ('d', 1.5, 2))),
                      Caption('c3', 7, 8, 'late words')]

    def run_op(self, **kw):
        report = []
        stage, _ = edited(self.project, [dict(op='ripple_delete_range', **kw)], report)
        return stage, report[0]

    def test_all_tracks_shift_and_source_time_is_kept(self):
        stage, details = self.run_op(start=3, end=6)
        self.assertEqual(stage.duration, 7)
        self.assertEqual(details['removed_seconds'], 3)
        for track, offset in (('video_1', 100), ('audio_1', 100), ('video_2', 100)):
            parts = sorted((i for i in stage.timeline if i.track == track), key=lambda i: i.start)
            self.assertEqual([(i.start, i.duration) for i in parts], [(0, 3), (3, 4)], track)
            self.assertAlmostEqual(parts[1].in_point, offset + 6)           # picks up exactly where the cut ended
        video, audio = (next(i for i in stage.timeline if i.track == t and i.start == 3) for t in ('video_1', 'audio_1'))
        self.assertEqual(video.link_id, audio.link_id)                    # the surviving halves stay linked
        self.assertNotEqual(video.link_id, 'g')

    def test_captions_keep_only_words_outside_the_cut_and_shift(self):
        stage, details = self.run_op(start=3, end=6)
        by_text = {c.text: c for c in stage.captions}
        self.assertEqual((by_text['one two'].start, by_text['one two'].end), (1, 2))
        tail = by_text['c d']
        self.assertAlmostEqual(tail.start, 3.0)
        self.assertAlmostEqual(tail.end, 4.0)
        self.assertEqual([w['text'] for w in tail.word_timings], ['c', 'd'])
        self.assertAlmostEqual(tail.word_timings[0]['start'], 0)
        self.assertAlmostEqual(by_text['late words'].start, 4.0)
        self.assertNotIn('a b', by_text)                                  # 'a b' lay inside 5-6, which was cut

    def test_caption_inside_range_is_removed_and_counts_reported(self):
        stage, details = self.run_op(start=0.5, end=2.5)
        self.assertNotIn('one two', [c.text for c in stage.captions])
        self.assertGreaterEqual(details['captions_removed'], 1)
        self.assertEqual(details['new_duration'], 8)

    def test_locked_track_is_not_shifted_and_is_reported(self):
        self.project.track_states['video_2']['locked'] = True
        stage, details = self.run_op(start=3, end=6)
        self.assertEqual(details['locked_tracks_not_shifted'], ['video_2'])
        locked = [i for i in stage.timeline if i.track == 'video_2']
        self.assertEqual([(i.start, i.duration) for i in locked], [(0, 10)])

    def test_validation(self):
        for bad in (dict(start=5, end=4), dict(start=1, end=1.01), dict(start=-1, end=2), dict(start=20, end=30),
                    dict(start='a', end=3), dict(start=1)):
            with self.assertRaises(ValueError, msg=bad):
                self.run_op(**bad)

    def test_one_undoable_batch_leaves_source_project_untouched(self):
        before = json.dumps(self.project.to_dict(), sort_keys=True)
        self.run_op(start=3, end=6)
        self.assertEqual(json.dumps(self.project.to_dict(), sort_keys=True), before)


class FitRegionTests(unittest.TestCase):
    def setUp(self):
        self.project = base_project()
        self.project.timeline = [TimelineItem('v1', 'm1', 'video_1', 0, 5), TimelineItem('a1', 'm2', 'audio_1', 0, 5),
                                 TimelineItem('t1', '', 'video_2', 0, 3, role='title')]

    def fit(self, **kw):
        report = []
        stage, _ = edited(self.project, [dict(op='fit_region', **kw)], report)
        return stage.item_by_id(kw.get('id', 'v1')), report[0]

    def test_fit_matches_the_framing_formula(self):
        item, d = self.fit(id='v1', source_rect=dict(x=.3, y=.025, width=.6, height=.95), target_rect=dict(x=0, y=.4, width=1, height=.6))
        self.assertAlmostEqual(item.transform.scale, 1080 / (1920 * .6 * (1920 / 1080)), places=3)
        self.assertEqual(item.transform.scale, item.transform.scale_y)
        self.assertAlmostEqual(d['layer_px'][0], 1080, delta=1)
        self.assertLessEqual(d['layer_px'][1], d['box_px'][1] + 1)
        self.assertAlmostEqual(item.transform.y, .7)
        self.assertAlmostEqual(item.transform.x, .5)
        self.assertAlmostEqual(item.crop.x, .3)

    def test_fill_covers_the_box_by_trimming_the_region(self):
        item, d = self.fit(id='v1', source_rect=dict(x=.3, y=.025, width=.6, height=.95), target_rect=dict(x=0, y=.4, width=1, height=.6), mode='fill')
        self.assertTrue(d['covers_box'])
        self.assertAlmostEqual(d['layer_px'][0], 1080, delta=1)
        self.assertAlmostEqual(d['layer_px'][1], 1152, delta=1)
        self.assertLess(item.crop.width, .6)
        self.assertAlmostEqual(item.crop.x + item.crop.width / 2, .6, places=3)   # trimmed around the region's centre

    def test_defaults_and_validation(self):
        item, d = self.fit(id='v1')
        self.assertAlmostEqual(item.transform.scale, 1080 / (1920 * 1920 / 1080), places=3)     # whole 16:9 source inside a 9:16 frame: width-limited
        for bad in (dict(id='nope'), dict(id='a1'), dict(id='t1'), dict(id='v1', mode='stretch'),
                    dict(id='v1', source_rect=dict(x=.8, y=0, width=.5, height=1)),
                    dict(id='v1', source_rect=dict(left=0)), dict(id='v1', target_rect=dict(width=0)),
                    dict(id='v1', target_rect=dict(x='a')), dict()):
            with self.assertRaises(ValueError, msg=bad):
                self.fit(**bad)


class InsertWithAudioTests(unittest.TestCase):
    def test_with_audio_adds_a_linked_source_audio_clip(self):
        project = base_project()
        stage, created = edited(project, [dict(op='insert_clip', media_id='m1', track='video_1', start=2, duration=4, in_point=30, with_audio=True)])
        self.assertEqual(len(created), 2)
        video, audio = (stage.item_by_id(i) for i in created)
        self.assertEqual((audio.track, audio.role, audio.start, audio.duration, audio.in_point), ('audio_1', 'source_audio', 2, 4, 30))
        self.assertTrue(video.link_id and video.link_id == audio.link_id)
        self.assertEqual(len(project.timeline), 0)

    def test_with_audio_rules(self):
        project = base_project()
        for bad in (dict(media_id='m3', track='video_1', with_audio=True),                       # no audio stream
                    dict(media_id='m1', track='video_1', with_audio=True, audio_track='video_2'),
                    dict(media_id='m1', track='video_1', with_audio=True, audio_track='nope')):
            with self.assertRaises(ValueError, msg=bad):
                edited(project, [dict(op='insert_clip', **bad)])
        stage, created = edited(project, [dict(op='insert_clip', media_id='m1', track='video_1', audio_id='mine', with_audio=True)])
        self.assertIn('mine', created)
        stage, created = edited(project, [dict(op='insert_clip', media_id='m1', track='video_1')])
        self.assertEqual(len(created), 1)


class CompactAndCoercionTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.w = MainWindow()
        self.w.autosave_timer.stop()
        project = base_project()
        project.timeline = [TimelineItem('v1', 'm1', 'video_1', 0, 5, in_point=3, role='normal'),
                            TimelineItem('a1', 'm1', 'audio_1', 0, 5, in_point=3, role='source_audio', gain_db=-3)]
        project.captions = [Caption(f'c{i}', i, i + .9, 'w') for i in range(15)]
        self.w.set_project(project)

    def tearDown(self):
        self.w.close()

    def test_compact_timeline_omits_defaults_but_keeps_what_matters(self):
        api = EditorAPI(self.w)
        compact = api.call_get_state()['project']['timeline']
        full = api.call_get_state(detail='full')['project']['timeline']
        self.assertLess(len(json.dumps(compact)) * 3, len(json.dumps(full)))
        video = next(i for i in compact if i['id'] == 'v1')
        for key in ('id', 'media_id', 'track', 'start', 'duration', 'in_point', 'role'):
            self.assertIn(key, video)
        self.assertNotIn('effects', video)
        self.assertNotIn('title_style', next(i for i in compact if i['id'] == 'a1'))
        self.assertEqual(next(i for i in compact if i['id'] == 'a1')['gain_db'], -3)
        self.assertIn('crop', next(i for i in full if i['id'] == 'v1'))
        with self.assertRaises(ValueError):
            api.call_get_state(detail='x')

    def test_compact_keeps_changed_nested_values_only(self):
        self.w.project.timeline[0].transform.y = .25
        row = next(i for i in EditorAPI(self.w).call_get_state()['project']['timeline'] if i['id'] == 'v1')
        self.assertEqual(row['transform'], dict(y=.25))

    def test_numeric_strings_are_accepted_where_the_schema_says_number(self):
        api = EditorAPI(self.w)
        got = api.dispatch('get_state', dict(section='captions', start='10', end='12'))
        self.assertEqual([c['id'] for c in got['captions']], ['c10', 'c11'])
        self.assertEqual(coerce_numbers('seek', dict(seconds='2.5')), dict(seconds=2.5))
        self.assertEqual(coerce_numbers('search_transcripts', dict(limit='5', offset='0', query='1')), dict(limit=5, offset=0, query='1'))
        self.assertEqual(coerce_numbers('create_edit_contact_sheet', dict(timestamps=['1', 2])), dict(timestamps=[1.0, 2]))
        self.assertEqual(coerce_numbers('seek', dict(seconds='abc')), dict(seconds='abc'))      # still rejected by the tool itself
        self.assertEqual(coerce_numbers('get_state', dict(section='1')), dict(section='1'))      # strings stay strings


if __name__ == '__main__':
    unittest.main()
