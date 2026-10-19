"""Regenerable, source-time speech index; never writes projects or media."""
import copy
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from . import config

MAX_BYTES = 128 * 1024 * 1024


def identity(media, settings):
    path = Path(media.path).resolve()
    stat = path.stat()
    return dict(version=2, path=os.path.normcase(str(path)), size=stat.st_size,
                mtime=stat.st_mtime_ns, ctime=stat.st_ctime_ns,
                model=settings.get('whisper_model', 'small.en'),
                language=settings.get('caption_language', 'en'))


def cache_path(stamp):
    digest = hashlib.sha256(json.dumps(stamp, sort_keys=True).encode()).hexdigest()
    root=Path(config.CACHE_DIR); path=root/'transcripts'/(digest+'.json')
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Transcript index path leaves the app cache.')
    return path


def load(media, settings):
    try:
        stamp = identity(media, settings); path = cache_path(stamp)
        if path.stat().st_size > 16 * 1024 * 1024: return None
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('source') != stamp: return None
        if data.get('timing') not in ('word','estimated') or not isinstance(data.get('segments'),list):return None
        for row in data['segments']:
            if not (isinstance(row['text'], str) and math.isfinite(row['start'])
                    and math.isfinite(row['end']) and 0 <= row['start'] < row['end']): return None
        return data
    except (OSError, ValueError, KeyError, TypeError): return None


def generate(media, settings, cancel, progress=None, force=False):
    from .captions import transcribe, _check_cancel
    from .process import run_cancellable
    _check_cancel(cancel.is_set)
    if not media.has_audio: raise ValueError('This source has no audio stream.')
    stamp = identity(media, settings)
    cached = None if force else load(media, settings)
    if cached: return cached
    with tempfile.TemporaryDirectory(prefix='kinetic-transcript-') as directory:
        wav = str(Path(directory) / 'speech.wav')
        run_cancellable([settings.get('ffmpeg', 'ffmpeg'), '-hide_banner', '-loglevel', 'error',
                         '-y', '-i', media.path, '-vn', '-ac', '1', '-ar', '16000', wav],
                        cancel_check=cancel.is_set, check=True, capture_output=True)
        captions, backend = transcribe(wav, settings, words_per_caption=12, hold_seconds=0,
                                      cancel_check=cancel.is_set, progress=progress)
    _check_cancel(cancel.is_set)
    if stamp != identity(media, settings): raise ValueError('The source changed during transcription. Generate again.')
    data = dict(source=stamp, backend=backend, timing='word' if all(c.word_timings for c in captions) else 'estimated',
                segments=[dict(start=c.start, end=c.end, text=c.text,
                               words=[dict(text=w['text'], start=c.start+w['start'], end=c.start+w['end'])
                                      for w in c.word_timings]) for c in captions])
    path = cache_path(stamp); path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, ensure_ascii=False).encode('utf-8')
    if len(encoded) > 16 * 1024 * 1024: raise ValueError('Transcript is too large for the source index.')
    # Unique temporary names avoid collisions between independent app instances.
    fd, temporary = tempfile.mkstemp(prefix='transcript-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream: stream.write(encoded)
        _check_cancel(cancel.is_set); os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    files = sorted(path.parent.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)
    total = 0
    for entry in files:
        try:
            total += entry.stat().st_size
            if total > MAX_BYTES and entry != path: entry.unlink()
        except OSError: pass
    return data


def occurrences(project, media_id, start, end):
    """Map source speech to every visible cut, including trimmed/retimed repeats."""
    rows = []
    for item in project.timeline:
        if item.media_id != media_id or item.speed <= 0: continue
        a = max(start, item.in_point); b = min(end, item.in_point + item.source_duration)
        if b > a:
            rows.append(dict(item_id=item.id, track=item.track,
                             start=item.start+(a-item.in_point)/item.speed,
                             end=item.start+(b-item.in_point)/item.speed))
    return rows


def search(project, settings, query='', media_ids=None, limit=200, offset=0):
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1 <= limit <= 500 or isinstance(offset,bool) or not isinstance(offset,int) or offset < 0: raise ValueError('Use limit 1–500 and a nonnegative integer offset.')
    wanted = None if media_ids is None else set(media_ids)
    terms = str(query).casefold().split(); matches = []; indexed = []; missing = []
    for media in project.media:
        if not media.has_audio or wanted is not None and media.id not in wanted: continue
        data = load(media, settings)
        if data is None: missing.append(media.id); continue
        indexed.append(media.id)
        for index, row in enumerate(data['segments']):
            if all(term in row['text'].casefold() for term in terms):
                matches.append(dict(media_id=media.id, name=media.name, segment=index,
                                    timing=data['timing'], **copy.deepcopy(row),
                                    occurrences=occurrences(project,media.id,row['start'],row['end'])))
    return dict(matches=matches[offset:offset+limit], total=len(matches), offset=offset,
                indexed_media_ids=indexed, missing_media_ids=missing,
                coordinates='Source seconds; occurrences are timeline seconds.')
