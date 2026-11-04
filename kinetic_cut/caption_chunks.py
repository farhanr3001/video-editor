"""Phrase-aware grouping of timed words into caption items.

`words_per_caption` is a maximum, not a quota.  A caption never runs across a
sentence end ("open! Jump!" becomes "open!" + "Jump!"), and a run of words is
split where speech naturally breaks (punctuation, small pauses) instead of
being cut every N words, which used to leave stray one-word leftovers.
"""
import re

HARD_GAP = .65     # a real pause always starts a new caption
REPEAT_GAP = .25   # the same word said twice with a breath between is two captions
SOFT_GAP = .18     # a short pause is a good place to split a long run
ABBREVIATIONS = {'mr', 'mrs', 'ms', 'dr', 'st', 'vs', 'jr', 'sr', 'etc', 'inc', 'no', 'prof'}

_END = re.compile(r'''[.!?…]+["'”’)\]]*$''')
_SOFT = re.compile(r'''[,;:—–-]["'”’)\]]*$''')


def ends_sentence(text):
    text = str(text).strip()
    if not _END.search(text):
        return False
    core = re.sub(r'\W', '', text).lower()
    if text.endswith('.') and core in ABBREVIATIONS:
        return False
    return True


def same_word(a, b):
    key = lambda w: re.sub(r'\W', '', str(w['text'])).casefold()
    return bool(key(a)) and key(a) == key(b)


def unstretch_repeats(words, audio, rate=16000, long_word=.8, confident=.75):
    """Move a repeated word ("oh Oh,") to where its audio really starts.

    The recognizer can stretch the second copy backwards over a silence, so it
    looks like it starts the instant the first one ends.  This is only done for
    a long, doubtful word that repeats the word before it, and only when the
    audio shows a clear silent lead; anything else keeps its recognized time.
    """
    import numpy as np
    if audio is None:
        return words
    step = max(1, rate // 100)
    for before, word in zip(words, words[1:]):
        length = word['end'] - word['start']
        score = word.get('confidence')
        doubtful = score < confident if isinstance(score, (int, float)) else True
        if length <= long_word or not doubtful or not same_word(before, word):
            continue
        a = max(0, int(word['start'] * rate)); b = min(len(audio), int(word['end'] * rate))
        clip = np.asarray(audio[a:b], dtype=float)
        frames = len(clip) // step
        if frames < 10:
            continue
        levels = np.sqrt((clip[:frames * step].reshape(frames, step) ** 2).mean(axis=1))
        levels = np.convolve(levels, np.ones(5) / 5, mode='same')   # ignore isolated clicks
        peak = float(levels.max())
        if peak < 1e-3:
            continue
        active = np.flatnonzero(levels > peak * .5)
        onset = word['start'] + int(active[0]) * step / rate - .05
        if onset - word['start'] >= .3:
            word['start'] = min(onset, word['end'] - .05)
    return words


def trim_stretched_tails(words, audio, joins, rate=16000, long_word=.8, confident=.75):
    """End a long, doubtful word where its own sound stops.

    The recognizer sometimes stretches a word over a later noise or silence.  If
    the word starts on sound, falls quiet for at least 0.3 s and its span goes on
    well past that, the span after the quiet gap is not the word, so its end is
    pulled back to where the sound died away.  Only words whose span crosses a
    clip join (`joins`, where the audio continues unbroken) are examined; words
    without that clear shape, and runs without audio, keep their recognized time.
    """
    import numpy as np
    if audio is None or not joins:
        return words
    step = max(1, rate // 100)
    for word in words:
        length = word['end'] - word['start']
        score = word.get('confidence')
        if length <= long_word or (isinstance(score, (int, float)) and score >= confident):
            continue
        if not any(word['start'] < j < word['end'] for j in joins):
            continue
        a = max(0, int(word['start'] * rate)); b = min(len(audio), int(word['end'] * rate))
        clip = np.asarray(audio[a:b], dtype=float)
        frames = len(clip) // step
        if frames < 60:
            continue
        levels = np.sqrt((clip[:frames * step].reshape(frames, step) ** 2).mean(axis=1))
        levels = np.convolve(levels, np.ones(5) / 5, mode='same')
        head = float(levels[:50].max())
        floor = float(np.quantile(levels, .1))
        if head < 1e-3 or levels[:10].max() < floor + .5 * (head - floor):
            continue                                   # does not start on sound
        quiet = levels < floor + .25 * (head - floor)
        run = 0
        for index in range(10, frames):
            run = run + 1 if quiet[index] else 0
            if run >= 30:
                end = word['start'] + (index - run + 1) / 100 + .1
                if word['end'] - end >= .3:
                    word['end'] = end
                break
    return words


def _boundary_value(words, index):
    """How good is a split between words[index] and words[index+1]? (higher = better)"""
    gap = max(0., words[index + 1]['start'] - words[index]['end'])
    value = min(gap, .6) * 4
    if gap >= SOFT_GAP:
        value += .4
    if _SOFT.search(str(words[index]['text']).strip()):
        value += 1.
    return value


def _split_run(words, limit):
    """Split one phrase (no sentence end inside) into balanced captions of <= limit words."""
    count = len(words)
    if count <= limit:
        return [words]
    pieces = -(-count // limit)
    target = count / pieces
    closing = ends_sentence(words[-1]['text'])
    values = [_boundary_value(words, i) for i in range(count - 1)]
    best = {0: (0., None)}
    for end in range(1, count + 1):
        options = []
        for start in range(max(0, end - limit), end):
            if start not in best:
                continue
            size = end - start
            cost = best[start][0] + 1. + .35 * (size - target) ** 2
            if size == 1:
                # A closing one-word sentence ("open!") reads fine alone; a
                # stranded first word or a mid-sentence leftover does not.
                cost += .3 if end == count and closing else 1.5
            if start:
                cost -= values[start - 1]
            options.append((cost, start))
        if options:
            cost, start = min(options)
            best[end] = (cost, start)
    result = []
    end = count
    while end:
        start = best[end][1]
        result.append(words[start:end])
        end = start
    return result[::-1]


def jump_cuts(items, offset=0., tolerance=.02, continuous_joins=False):
    """Times (relative to `offset`) where one audio clip ends and a non-continuous one begins.

    With `continuous_joins`, the joins where the audio carries on unbroken are returned instead.
    """
    cuts = []
    for a in items:
        for b in items:
            if a is b or abs((a.start + a.duration) - b.start) > tolerance:
                continue
            continuous = (a.media_id == b.media_id and abs(a.speed - b.speed) < 1e-6
                          and abs((a.in_point + a.source_duration) - b.in_point) <= .05)
            if continuous == continuous_joins:
                cuts.append(round(b.start - offset, 4))
    return sorted(set(cuts))


def respect_cuts(words, cuts, moves_after=.4):
    """Keep every word on one side of a jump cut.

    A word the recognizer stretched over a splice goes after the cut when at
    least `moves_after` of it lies there; otherwise its end is trimmed to the cut.
    """
    for word in words:
        for cut in cuts:
            if word['start'] < cut < word['end']:
                if (word['end'] - cut) / (word['end'] - word['start']) >= moves_after:
                    word['start'] = cut
                else:
                    word['end'] = cut
    return words


def next_cut(cuts, time):
    """The first cut at or after `time`, or None."""
    return next((c for c in cuts if c >= time - .001), None)


def chunk_words(words, limit, cuts=(), joins=()):
    """Group `words` (dicts with text/start/end) into caption-sized lists.

    `cuts` are jump-cut times in the same clock as the words; no caption spans
    one, and a word stretched across one is moved or trimmed.  `joins` are other
    clip boundaries where the audio carries on; captions are split there too, but
    words keep their times.
    """
    limit = max(1, int(limit))
    cuts = sorted(cuts)
    if cuts:
        respect_cuts(words, cuts)
    cuts = sorted(set(cuts) | set(joins))
    if limit == 1:
        return [[word] for word in words]
    runs, run = [], []
    for word in words:
        if run and (word['start'] - run[-1]['end'] > HARD_GAP
                    or any(run[-1]['start'] < c <= word['start'] for c in cuts)
                    or (same_word(run[-1], word) and word['start'] - run[-1]['end'] >= REPEAT_GAP)):
            runs.append(run)
            run = []
        run.append(word)
        if ends_sentence(word['text']):
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    chunks = []
    for run in runs:
        chunks.extend(_split_run(run, limit))
    return chunks
