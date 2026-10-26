"""Conservative ASS sampling keeps every possible whole-overlay change."""
import tempfile
import unittest
from pathlib import Path

from kinetic_cut.export_overlay_schedule import sample_frames


FORMAT = 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text'


class ExportOverlayScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / 'overlay.ass'

    def tearDown(self):
        self.temporary.cleanup()

    def script(self, events=(), info='', event_format=FORMAT):
        self.path.write_text(
            '[Script Info]\nScriptType: v4.00+\n' + info +
            '\n[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n'
            '\n[Events]\n' + event_format + '\n' + '\n'.join(events) + '\n',
            encoding='utf-8-sig',
        )
        return self.path

    def event(self, start='0:00:01.00', end='0:00:02.00', text='Static', effect=''):
        if '\\pos(' not in text and '\\move(' not in text:
            text = '{\\pos(100,200)}' + text
        return f'Dialogue: 0,{start},{end},Default,,0,0,0,{effect},{text}'

    def samples(self, events=(), fps=60., frames=600, **kwargs):
        return sample_frames(self.script(events, **kwargs), fps, frames)

    def test_empty_overlay_keeps_first_and_terminal_frame_only(self):
        self.assertEqual(self.samples(), [0, 599])

    def test_static_caption_keeps_neighbors_at_both_edges_and_blank_gaps(self):
        self.assertEqual(self.samples([self.event()]), [0, 59, 60, 61, 119, 120, 121, 599])

    def test_overlapping_static_events_preserve_every_membership_change(self):
        events = [self.event(), self.event('0:00:01.50', '0:00:03.00', '{\\pos(12,34)}Other')]
        samples = self.samples(events)
        for boundary in (60, 90, 120, 180):
            self.assertTrue({boundary - 1, boundary, boundary + 1} <= set(samples))
        self.assertNotIn(150, samples)
        self.assertEqual((samples[0], samples[-1]), (0, 599))

    def test_all_dynamic_tag_families_keep_entire_event_not_only_tag_window(self):
        for tag in ('\\t(0,100,\\fscx150)', '\\move(0,0,20,20,100,200)',
                    '\\fad(100,100)', '\\fade(255,0,255,0,100,800,1000)',
                    '\\k20', '\\K20', '\\kf20', '\\ko20', '\\kt20', '\\T(1,2,\\alpha&HFF&)'):
            with self.subTest(tag=tag):
                samples = self.samples([self.event(text='{'+tag+'}Dynamic')])
                self.assertTrue(set(range(59, 122)) <= set(samples))
                self.assertNotIn(122, samples)

    def test_nonempty_effects_including_unknown_effect_keep_entire_interval(self):
        for effect in ('Banner;40;0;50', 'Scroll up;0;600;10', 'Unknown future effect'):
            with self.subTest(effect=effect):
                samples = self.samples([self.event(effect=effect)])
                self.assertTrue(set(range(59, 122)) <= set(samples))

    def test_separate_dynamic_event_does_not_freeze_an_overlapping_static_caption(self):
        samples = self.samples([self.event('0:00:00.00', '0:00:05.00'),
                                self.event('0:00:02.00', '0:00:03.00', '{\\t(\\alpha&HFF&)}Glow')])
        self.assertTrue(set(range(119, 182)) <= set(samples))
        self.assertTrue({0, 1, 299, 300, 301, 599} <= set(samples))
        self.assertNotIn(200, samples)

    def test_fractional_rate_boundaries_use_original_absolute_clock(self):
        samples = self.samples([self.event('0:00:01.00', '0:00:02.00')], fps=60000/1001)
        self.assertTrue({59, 60, 61, 119, 120, 121} <= set(samples))
        high = self.samples([self.event('0:00:00.01', '0:00:00.02')], fps=240.)
        self.assertTrue({2, 3, 4, 5, 6} <= set(high))

    def test_events_outside_window_do_not_expand_large_ranges(self):
        self.assertEqual(self.samples([self.event('999999999:59:58.99', '999999999:59:59.99', '{\\t(1)}Far')]), [0, 599])
        samples = self.samples([self.event('0:00:09.98', '1:00:00.00', '{\\move(0,0,1,1)}Tail')])
        self.assertEqual(samples, [0, 598, 599])

    def test_zero_duration_events_are_conservative_and_never_remove_last_frame(self):
        samples = self.samples([self.event('0:00:04.00', '0:00:04.00')])
        self.assertTrue({239, 240, 241, 599} <= set(samples))
        self.assertEqual(samples, sorted(set(samples)))

    def test_dense_dynamic_script_uses_continuous_renderer(self):
        self.assertIsNone(self.samples([self.event('0:00:00.00', '0:00:10.00', '{\\k1}Dense')]))
        # 480 retained frames out of600 is exactly the80% fallback threshold.
        self.assertIsNone(self.samples([self.event('0:00:00.00', '0:00:07.95', '{\\k1}Dense')]))
        self.assertIsNotNone(self.samples([self.event('0:00:00.00', '0:00:07.93', '{\\k1}Sparse')]))

    def test_invalid_clocks_and_dialogue_fields_fall_back(self):
        for event in (self.event('0:00:01.0'), self.event('0:60:00.00'),
                      self.event('0:00:60.00'), self.event('-1:00:00.00'),
                      self.event('0:00:03.00', '0:00:02.00'),
                      self.event().replace('Dialogue: 0,', 'Dialogue: invalid,'),
                      'Dialogue: 0,0:00:01.00,0:00:02.00,Default',
                      self.event().replace('Default,,0,0,0,', 'Default,,x,0,0,')):
            with self.subTest(event=event):
                self.assertIsNone(self.samples([event]))

    def test_unknown_event_format_section_or_record_falls_back(self):
        for event_format in ('Format: Start, End, Text', FORMAT.replace('Layer, Start', 'Start, Layer')):
            self.assertIsNone(self.samples([self.event()], event_format=event_format))
        self.script([self.event()]); self.path.write_text(self.path.read_text(encoding='utf-8-sig')+'[Other]\nUnknown: 1\n')
        self.assertIsNone(sample_frames(self.path, 60., 600))
        self.assertIsNone(self.samples(['Picture: 0,0:00:00.00,Image']))

    def test_missing_format_duplicate_format_or_events_section_falls_back(self):
        self.assertIsNone(self.samples([self.event()], event_format=''))
        self.assertIsNone(self.samples([FORMAT, self.event()]))
        self.assertIsNone(self.samples([self.event(), '[Events]', FORMAT]))

    def test_timer_must_be_normal_and_known_script_type(self):
        for value in ('100', '100.0000'):
            self.assertIsNotNone(self.samples([self.event()], info=f'Timer: {value}\n'))
        for value in ('99.99', '101', 'nan', 'Infinity', 'invalid'):
            self.assertIsNone(self.samples([self.event()], info=f'Timer: {value}\n'))
        self.assertIsNone(self.samples([self.event()], info='ScriptType: v4.00\n'))

    def test_static_tags_and_commas_in_text_do_not_force_dynamic_sampling(self):
        static = '{\\pos(100,200)\\blur12\\bord7\\shad0\\fscx100\\fscy100\\p1}m 0 0 l 1 1, 2 2'
        self.assertEqual(self.samples([self.event(text=static)]), self.samples([self.event()]))

    def test_unpositioned_or_malformed_positions_keep_continuous_collision_history(self):
        for text in ('Unpositioned', '{\\pos(nan,2)}Text', '{\\pos(1)}Text',
                     '{\\move(1,2,3)}Text', 'Text{\\pos(1,2)}Later',
                     '{\\\\pos(1,2)}Escaped'):
            event = f'Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{text}'
            with self.subTest(text=text):
                self.assertIsNone(self.samples([event]))

    def test_malformed_encoding_missing_file_and_parameter_bounds_fall_back(self):
        self.script()
        for fps in (0, -1, 241, float('inf'), float('nan'), None, True):
            self.assertIsNone(sample_frames(self.path, fps, 600))
        for total in (0, -1, 250001, 1.5, True, None):
            self.assertIsNone(sample_frames(self.path, 60., total))
        for total in (1, 2):
            self.assertIsNone(sample_frames(self.path, 60., total))
        self.path.write_bytes(b'\xff\xfe\xff')
        self.assertIsNone(sample_frames(self.path, 60., 600))
        self.assertIsNone(sample_frames(self.path.with_name('missing.ass'), 60., 600))

    def test_comment_dialogues_are_not_rendered_and_bom_is_supported(self):
        comment = self.event(text='{\\t(1)}Ignored').replace('Dialogue:', 'Comment:')
        self.assertEqual(self.samples(['; metadata comment', comment]), [0, 599])


if __name__ == '__main__':
    unittest.main()
