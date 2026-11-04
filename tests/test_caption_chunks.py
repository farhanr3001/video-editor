import unittest
from kinetic_cut.caption_chunks import chunk_words, ends_sentence, unstretch_repeats, jump_cuts, respect_cuts, trim_stretched_tails


def words(*spec):
    t = 0.; out = []
    for text, gap in spec:
        t += gap; out.append(dict(text=text, start=t, end=t + .3)); t += .3
    return out


def texts(chunks):
    return [' '.join(w['text'] for w in c) for c in chunks]


class CaptionChunkTests(unittest.TestCase):
    def test_sentence_end_never_shares_a_caption_with_next_sentence(self):
        w = words(('Doors', 0), ('are', .05), ('open!', .05), ('Jump!', .12))
        self.assertEqual(texts(chunk_words(w, 2)), ['Doors are', 'open!', 'Jump!'])
        self.assertEqual(texts(chunk_words(w, 5)), ['Doors are open!', 'Jump!'])

    def test_speaker_change_without_pause(self):
        w = words(('So', 0), ('locked', .05), ('in!', .0), ("Let's", .0), ('go', .05))
        self.assertEqual(texts(chunk_words(w, 2)), ['So locked', 'in!', "Let's go"])

    def test_limit_is_a_maximum_and_splits_are_balanced(self):
        w = words(*[(t, .05) for t in 'I really do not think that this is going to work out'.split()])
        self.assertEqual(texts(chunk_words(w, 5)), ['I really do not', 'think that this is', 'going to work out'])

    def test_comma_and_pause_preferred_split_points(self):
        w = words(('Well,', 0), ('I', .2), ('guess', .05), ('so', .05))
        self.assertEqual(texts(chunk_words(w, 3))[0], 'Well, I')

    def test_long_pause_and_limit_one(self):
        w = words(('a', 0), ('b', .05), ('c', .9), ('d', .05))
        self.assertEqual(texts(chunk_words(w, 5)), ['a b', 'c d'])
        self.assertEqual(len(chunk_words(w, 1)), 4)

    def test_abbreviations_and_ellipsis(self):
        self.assertFalse(ends_sentence('Mr.'))
        self.assertTrue(ends_sentence('done.'))
        self.assertTrue(ends_sentence('what?"'))
        self.assertTrue(ends_sentence('wait...'))
        self.assertFalse(ends_sentence('3.5'))

    def test_order_and_words_preserved(self):
        w = words(*[(f'w{i}' + ('.' if i % 7 == 6 else ''), .03 * (i % 4)) for i in range(40)])
        for limit in (1, 2, 3, 5, 8):
            flat = [x for c in chunk_words(w, limit) for x in c]
            self.assertEqual(flat, w)
            self.assertTrue(all(len(c) <= limit for c in chunk_words(w, limit)))

    def test_repeated_word_with_a_breath_is_two_captions(self):
        w = words(('oh', 0), ('Oh,', .4), ('no', .05))
        self.assertEqual(texts(chunk_words(w, 3)), ['oh', 'Oh, no'])
        w = words(('no', 0), ('no', .05), ('no', .05))
        self.assertEqual(texts(chunk_words(w, 3)), ['no no no'])

    def test_repeated_stretched_word_starts_where_audio_does(self):
        import numpy as np
        audio = np.zeros(16000 * 3, dtype=np.float32)
        audio[int(.1 * 16000):int(.25 * 16000)] = .3
        audio[int(1.9 * 16000):int(2.2 * 16000)] = .3
        w = [dict(text='oh', start=.1, end=.25, confidence=.4), dict(text='Oh,', start=.26, end=2.2, confidence=.05)]
        unstretch_repeats(w, audio)
        self.assertAlmostEqual(w[1]['start'], 1.85, delta=.05)
        self.assertEqual(texts(chunk_words(w, 2)), ['oh', 'Oh,'])

    def test_non_repeats_and_missing_audio_are_untouched(self):
        import numpy as np
        audio = np.zeros(16000 * 3, dtype=np.float32)
        audio[int(1.9 * 16000):int(2.2 * 16000)] = .3
        w = [dict(text='check', start=.1, end=.4, confidence=.9), dict(text='failed', start=.5, end=2.2, confidence=.7)]
        unstretch_repeats(w, audio)
        self.assertEqual(w[1]['start'], .5)
        r = [dict(text='no', start=0., end=.2), dict(text='no', start=.2, end=1.5, confidence=.1)]
        unstretch_repeats(r, None)
        self.assertEqual(r[1]['start'], .2)

    def test_jump_cuts_ignore_continuous_razor_cuts(self):
        from types import SimpleNamespace as N
        mk = lambda m, s, d, i: N(media_id=m, start=s, duration=d, in_point=i, speed=1., source_duration=d)
        items = [mk('a', 10, 2, 5), mk('a', 12, 2, 7), mk('a', 14, 3, 20), mk('b', 17, 1, 0)]
        self.assertEqual(jump_cuts(items, 10), [4.0, 7.0])
        self.assertEqual(jump_cuts(items, 10, continuous_joins=True), [2.0])

    def test_straddling_word_goes_to_the_larger_side(self):
        w = words(('arrived', 0), ('tell', .0))
        w[1].update(start=.4, end=1.5)          # 'tell' spans a cut at 1.0: 45% after
        respect_cuts(w, [1.0])
        self.assertEqual(w[1]['start'], 1.0)
        w2 = [dict(text='failed', start=0., end=1.1)]   # 10% after: trimmed instead
        respect_cuts(w2, [1.0])
        self.assertEqual((w2[0]['start'], w2[0]['end']), (0., 1.0))

    def test_no_caption_spans_a_cut(self):
        w = [dict(text=t, start=a, end=b) for t, a, b in
             [('the', 0., .2), ('chad', .25, .45), ('arrived', .5, .8), ('tell', .85, 2.0), ('me', 2.3, 2.5)]]
        chunks = chunk_words(w, 5, cuts=[1.2])
        self.assertEqual(texts(chunks), ['the chad arrived', 'tell me'])
        for chunk in chunks:
            self.assertFalse(chunk[0]['start'] < 1.2 < chunk[-1]['end'])

    def test_captions_never_end_past_a_cut(self):
        from kinetic_cut.captions import _from_segments
        seg = dict(start=0., end=2.5, text='arrived tell me', words=[
            dict(text='arrived', start=.5, end=.8), dict(text='tell', start=.85, end=2.0), dict(text='me', start=2.3, end=2.5)])
        caps = _from_segments([seg], 100., words_per_caption=5, hold_seconds=.5, cuts=[1.2])
        self.assertEqual([c.text for c in caps], ['arrived', 'tell me'])
        self.assertLessEqual(caps[0].end, 101.2 + 1e-6)
        self.assertGreaterEqual(caps[1].start, 101.2 - 1e-6)

    def test_stretched_word_ends_where_its_sound_stops(self):
        import numpy as np
        audio = np.zeros(16000 * 4, dtype=np.float32)
        audio[:int(.3 * 16000)] = .2                      # the word
        audio[int(2.0 * 16000):int(2.4 * 16000)] = .6     # unrelated noise later
        w = [dict(text='failed', start=0., end=2.5, confidence=.7)]
        trim_stretched_tails(w, audio, [1.0])
        self.assertAlmostEqual(w[0]['end'], .4, delta=.1)
        keep = [dict(text='noooo', start=0., end=2.5, confidence=.95)]
        trim_stretched_tails(keep, audio, [1.0])
        self.assertEqual(keep[0]['end'], 2.5)
        far = [dict(text='failed', start=0., end=2.5, confidence=.7)]
        trim_stretched_tails(far, audio, [3.5])           # no clip join inside the word
        self.assertEqual(far[0]['end'], 2.5)
        none = [dict(text='x', start=0., end=2.5, confidence=.1)]
        self.assertEqual(trim_stretched_tails(none, None, [1.0])[0]['end'], 2.5)

    def test_captions_split_at_continuous_joins_without_moving_words(self):
        w = [dict(text='sick', start=.1, end=.4), dict(text='bro', start=.6, end=.8)]
        self.assertEqual(texts(chunk_words(w, 2, joins=[.5])), ['sick', 'bro'])
        self.assertEqual((w[0]['start'], w[1]['start']), (.1, .6))
        self.assertEqual(texts(chunk_words(w, 2)), ['sick bro'])


if __name__ == '__main__':
    unittest.main()
