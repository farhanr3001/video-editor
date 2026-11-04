"""Look at and listen to imported SOURCE media without touching the project or the playhead.

Three independent analyses, all offline and cancellable:
  * frames  - a labelled contact sheet of source frames (evenly spaced, at shot
              changes, or at loud moments)
  * audio   - a loudness curve, silent ranges and unusually loud moments
  * shots   - cut times found by scene-change detection

Times are source seconds.  Loudness is level, not meaning: a loud moment may be
a shout, laughter, a game sound or music, so the frames and transcript should be
checked before it is used.
"""
import json
import math
import re
from pathlib import Path

RATE = 8000            # analysis sample rate (Hz)
WINDOW = .25           # loudness window (s)
MAX_RANGE = 3600.      # longest range analysed in one job (s)
SILENCE_DB = -55.      # below this a window counts as silent
MIN_SILENCE = .5       # shortest silence reported (s)
RISE_DB = 8.           # a moment must be this much above its surroundings
LOUD_FLOOR_DB = -32.   # ...and at least this loud in absolute terms
SHOT_FPS = 12          # frame rate scene detection samples at
KINDS = ('frames', 'audio', 'shots')
SAMPLING = ('even', 'shots', 'loud_moments')


def clock(seconds):
    seconds = max(0., float(seconds))
    return f'{int(seconds) // 60:02d}:{seconds % 60:06.3f}'


def audio_profile(path, ffmpeg, start, end, cancel, bucket=None):
    import numpy as np
    from .process import run_cancellable
    args = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', f'{start:.3f}', '-t', f'{end - start:.3f}',
            '-i', str(path), '-vn', '-ac', '1', '-ar', str(RATE), '-f', 'f32le', 'pipe:1']
    result = run_cancellable(args, cancel_check=cancel.is_set, check=True, capture_output=True)
    values = np.frombuffer(result.stdout, dtype='<f4')
    size = int(WINDOW * RATE)
    count = len(values) // size
    if count < 2:
        return dict(available=False, note='No audio in this range.')
    block = values[:count * size].reshape(count, size).astype(np.float64)
    db = 20 * np.log10(np.maximum(np.sqrt((block ** 2).mean(axis=1)), 1e-5))
    span = end - start
    bucket = float(bucket or max(1., round(span / 240.)))
    group = max(1, round(bucket / WINDOW))
    curve = [round(float(db[i:i + group].max()), 1) for i in range(0, count, group)]

    silences, run = [], None
    for index, level in enumerate(db):
        if level < SILENCE_DB:
            run = index if run is None else run
        elif run is not None:
            if (index - run) * WINDOW >= MIN_SILENCE:
                silences.append([round(start + run * WINDOW, 2), round(start + index * WINDOW, 2)])
            run = None
    if run is not None and (count - run) * WINDOW >= MIN_SILENCE:
        silences.append([round(start + run * WINDOW, 2), round(start + count * WINDOW, 2)])

    smooth = np.convolve(db, np.ones(2) / 2, mode='same')
    half = int(5 / WINDOW)
    rise = np.zeros(count)
    for index in range(count):
        rise[index] = smooth[index] - float(np.median(smooth[max(0, index - half):index + half + 1]))
    hot = (rise >= RISE_DB) & (smooth >= LOUD_FLOOR_DB)
    raw_rise = np.array([db[i] - float(np.median(db[max(0, i - half):i + half + 1])) for i in range(count)])
    firm = (raw_rise >= RISE_DB - 2) & (db >= LOUD_FLOOR_DB)    # a lone loud window is a click, not a moment
    moments, index = [], 0
    while index < count:
        if not hot[index]:
            index += 1
            continue
        first = last = index
        while last + 1 < count and (hot[last + 1] or (last + 2 < count and hot[last + 2])):
            last += 1
        if not any(firm[i] and firm[i + 1] for i in range(first, min(last + 1, count - 1))):
            index = last + 1
            continue
        peak = first + int(np.argmax(smooth[first:last + 1]))
        length = (last - first + 1) * WINDOW
        moments.append(dict(start=round(start + first * WINDOW, 2), end=round(start + (last + 1) * WINDOW, 2),
                            peak_time=round(start + (peak + .5) * WINDOW, 2), peak_db=round(float(smooth[peak]), 1),
                            rise_db=round(float(rise[first:last + 1].max()), 1), duration=round(length, 2),
                            shape='sudden burst' if length < .75 else 'sustained'))
        index = last + 1
    moments = sorted(sorted(moments, key=lambda m: -m['rise_db'])[:40], key=lambda m: m['start'])
    return dict(available=True, start=round(start, 3), end=round(end, 3), bucket=bucket,
                loudness_db=curve, median_db=round(float(np.median(db)), 1),
                p95_db=round(float(np.percentile(db, 95)), 1),
                peak_db=round(20 * math.log10(max(1e-9, float(np.abs(values).max()))), 1),
                silences=silences, loud_moments=moments,
                note='Level only. Loud can be a shout, laughter, a game sound or music: check the frame and transcript.')


def detect_shots(path, ffmpeg, start, end, threshold, cancel):
    from .process import run_cancellable
    chain = f"fps={SHOT_FPS},scale=320:-2,select='gt(scene,{threshold})',showinfo"
    args = [ffmpeg, '-hide_banner', '-nostats', '-ss', f'{start:.3f}', '-t', f'{end - start:.3f}', '-i', str(path),
            '-an', '-vf', chain, '-f', 'null', '-']
    result = run_cancellable(args, cancel_check=cancel.is_set, capture_output=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError('Shot detection failed: ' + result.stderr.decode('utf-8', 'replace')[-400:])
    times = []
    for stamp in re.findall(r'pts_time:([0-9.]+)', result.stderr.decode('utf-8', 'replace')):
        value = round(start + float(stamp), 3)
        if not times or value - times[-1] >= .4:
            times.append(value)
    edges = [start] + times + [end]
    lengths = [b - a for a, b in zip(edges, edges[1:])]
    return dict(threshold=threshold, precision=round(1 / SHOT_FPS, 3), cut_count=len(times),
                cuts=times[:400], truncated=len(times) > 400,
                average_shot_seconds=round(sum(lengths) / len(lengths), 2),
                note='Cut times are scene-change estimates (about 1/12 s). Slow pans, fades and flashes can be missed or over-reported.')


def pick_times(sample, count, start, end, shots=(), moments=()):
    limit = max(start, end - .05)
    clamp = lambda t: round(min(limit, max(start, t)), 3)
    span = end - start
    even = [clamp(start + (i + .5) * span / count) for i in range(count)]
    if sample == 'shots' and shots:
        points = [(clamp(c + .1), 'shot') for c in shots]
        if len(points) >= count:
            step = (len(points) - 1) / (count - 1) if count > 1 else 0
            points = [points[round(i * step)] for i in range(count)]
        else:
            points = [(clamp(start + .1), 'start')] + points
        points = sorted(set(points))[:count]
        return [t for t, _ in points], [l for _, l in points]
    if sample == 'loud_moments' and moments:
        best = sorted(moments, key=lambda m: -m['rise_db'])[:count]
        best = sorted(best, key=lambda m: m['peak_time'])
        return [clamp(m['peak_time']) for m in best], [f"+{m['rise_db']:.0f} dB" for m in best]
    return even, ['' for _ in even]


def contact_sheet(media, times, labels, width, cancel, progress, target):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter, QFont
    from .review_frames import decode
    tiles = []
    for n, stamp in enumerate(times):
        if cancel.is_set():
            raise InterruptedError('Analysis cancelled.')
        tiles.append(decode(media, stamp, cancel).scaledToWidth(width, Qt.SmoothTransformation))
        progress(50 + (n + 1) / len(times) * 45, f'Decoded frame {n + 1}/{len(times)}')
    height = max(t.height() for t in tiles)
    cell = height + 30
    columns = min(3, len(tiles))
    sheet = QImage(columns * width, math.ceil(len(tiles) / columns) * cell, QImage.Format_RGB32)
    sheet.fill(Qt.black)
    painter = QPainter(sheet)
    try:
        painter.setFont(QFont('Arial', 11))
        painter.setPen(Qt.white)
        for n, (tile, stamp, label) in enumerate(zip(tiles, times, labels)):
            x, y = (n % columns) * width, (n // columns) * cell
            painter.drawImage(x, y, tile)
            painter.drawText(QRectF(x + 6, y + height, width - 12, 30), Qt.AlignVCenter,
                             f'{clock(stamp)}  {label}'.strip())
    finally:
        painter.end()
    if not sheet.save(str(target)):
        raise OSError('Could not save the source contact sheet.')


def analyze(media, ffmpeg, kinds, start, end, sample, count, timestamps, width, threshold,
            cancel, progress, directory):
    from .config import CACHE_DIR
    directory = Path(directory)
    if not directory.resolve().is_relative_to(Path(CACHE_DIR).resolve()):
        raise ValueError('Analysis output must stay inside the app cache.')
    directory.mkdir(parents=True, exist_ok=True)
    path = Path(media.path)
    if not path.is_file():
        raise ValueError('Source file is missing: ' + str(path))
    report = dict(media=dict(id=media.id, name=media.name, kind=media.kind, duration=round(media.duration, 3),
                             width=media.width, height=media.height, fps=media.fps, has_audio=media.has_audio),
                  range=[round(start, 3), round(end, 3)])
    visual = media.kind == 'video'
    need_audio = 'audio' in kinds or (sample == 'loud_moments' and 'frames' in kinds)
    need_shots = visual and ('shots' in kinds or (sample == 'shots' and 'frames' in kinds))
    audio = shots = None
    if need_audio:
        progress(2, 'Measuring loudness…')
        audio = audio_profile(path, ffmpeg, start, end, cancel) if media.has_audio else dict(available=False, note='This media has no audio.')
    if need_shots:
        progress(10, 'Detecting shot changes…')
        shots = detect_shots(path, ffmpeg, start, end, threshold, cancel)
    if 'audio' in kinds:
        report['audio'] = audio
    if 'shots' in kinds:
        report['shots'] = shots if visual else dict(note='Audio-only media has no shots.')
    if 'frames' in kinds:
        if not visual:
            report['frames'] = dict(note='Audio-only media has no frames.')
        else:
            if timestamps:
                times, labels = [round(float(t), 3) for t in timestamps], ['' for _ in timestamps]
            else:
                times, labels = pick_times(sample, count, start, end,
                                           shots['cuts'] if shots else (),
                                           audio['loud_moments'] if audio and audio.get('available') else ())
            target = directory / 'source-sheet.png'
            contact_sheet(media, times, labels, width, cancel, progress, target)
            report['frames'] = dict(sheet=str(target), sampling='manual' if timestamps else sample,
                                    tiles=[dict(time=t, label=l) for t, l in zip(times, labels)])
    progress(100, 'Done')
    (directory / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    prune(directory.parent, directory)
    return report


def prune(root, keep, limit=128 * 1024 ** 2):
    """Keep this cache namespace bounded; only generated png/json files are ever removed."""
    files = []
    for folder in Path(root).iterdir():
        if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(Path(root).resolve()):
            continue
        for path in folder.iterdir():
            if path.is_file() and not path.is_symlink() and path.suffix in ('.png', '.json'):
                try:
                    files.append((path.stat().st_mtime, path.stat().st_size, path))
                except OSError:
                    pass
    total = 0
    for _, size, path in sorted(files, reverse=True):
        total += size
        if total > limit and path.parent != keep:
            try:
                path.unlink()
            except OSError:
                pass
