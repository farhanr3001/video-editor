"""Whole-timeline range edits and layout helpers for the MCP edit batch.

ripple_delete_range removes a time range from every unlocked track, closes the gap
and keeps captions and transitions in step, using the same ripple clock as a
manual Ripple Delete.  fit_region turns "this part of the source goes in that box
of the frame" into crop and transform values.
"""
import copy
import re

from .model import Caption, Crop, uid

EDGE = .035          # fragments shorter than this are not worth splitting off


def split_caption_at(caption, at):
    """Split a caption at a timeline time. Each fragment keeps only the words that fall on its side."""
    words = caption.text.split()
    timed = caption.word_timings if len(caption.word_timings) == len(words) else []
    if timed:
        side = [caption.start + (w['start'] + w['end']) / 2 >= at for w in timed]
    else:
        cut = round(len(words) * (at - caption.start) / max(1e-6, caption.end - caption.start))
        side = [i >= cut for i in range(len(words))]
    fragments = []
    for right, (begin, finish) in ((False, (caption.start, at)), (True, (at, caption.end))):
        chosen = [i for i, flag in enumerate(side) if flag == right]
        if not chosen:
            continue
        fragment = Caption(uid(), begin, finish, ' '.join(words[i] for i in chosen), copy.deepcopy(caption.style),
                           caption.is_hook, caption.customize)
        if timed:
            for i in chosen:
                word = dict(timed[i], text=words[i])
                word['start'] = max(0., round(caption.start + word['start'] - begin, 4))
                word['end'] = min(finish - begin, max(word['start'], round(caption.start + word['end'] - begin, 4)))
                fragment.word_timings.append(word)
        fragments.append(fragment)
    return fragments


def ripple_delete_range(stage, start, end):
    if not (0 <= start < end):
        raise ValueError('ripple_delete_range needs 0 <= start < end (timeline seconds)')
    if end - start < .05:
        raise ValueError('The range is too short to delete')
    if start >= stage.duration:
        raise ValueError('The range starts after the end of the timeline')
    locked = sorted({i.track for i in stage.timeline if stage.track_states.get(i.track, {}).get('locked')
                     and i.start + i.duration > start})
    length = end - start
    for at in (start, end):
        crossing = [i.id for i in stage.timeline if not stage.track_states.get(i.track, {}).get('locked')
                    and i.start + EDGE < at < i.start + i.duration - EDGE]
        if crossing:
            stage.split_selection(crossing, at, linked=True)
    removed = [i.id for i in stage.timeline if not stage.track_states.get(i.track, {}).get('locked')
               and i.start >= start - EDGE and i.start + i.duration <= end + EDGE]
    caption_ids, captions_locked = [], bool(stage.track_states.get('subtitle_1', {}).get('locked'))
    if not captions_locked:
        for at in (start, end):
            for caption in list(stage.captions):
                if caption.start + .02 < at < caption.end - .02:
                    stage.captions = [c for c in stage.captions if c.id != caption.id] + split_caption_at(caption, at)
        caption_ids = [c.id for c in stage.captions if c.start >= start - .02 and c.end <= end + .02]
    before = (len(stage.timeline), len(stage.captions))
    stage.delete(removed, ripple=True, caption_ids=caption_ids)
    return dict(removed_seconds=round(length, 3), items_removed=len(removed), captions_removed=len(caption_ids),
                items_after=len(stage.timeline), captions_after=len(stage.captions), new_duration=round(stage.duration, 3),
                locked_tracks_not_shifted=locked + (['subtitle_1'] if captions_locked and stage.captions else []))


def fit_region(stage, item_ids, source_rect=None, target_rect=None, mode='fit'):
    if mode not in ('fit', 'fill'):
        raise ValueError('mode must be fit or fill')
    if not item_ids:
        raise ValueError('fit_region needs an item id')
    target = dict(x=0., y=0., width=1., height=1.)
    target.update(target_rect or {})
    source = dict(x=0., y=0., width=1., height=1.)
    source.update(source_rect or {})
    for rect, name in ((target, 'target_rect'), (source, 'source_rect')):
        extra = set(rect) - {'x', 'y', 'width', 'height'}
        if extra:
            raise ValueError(f'{name} takes x, y, width, height; got {sorted(extra)}')
        for value in rect.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f'{name} values must be numbers')
    if not (0 <= source['x'] < 1 and 0 <= source['y'] < 1 and .02 <= source['width'] <= 1 and .02 <= source['height'] <= 1
            and source['x'] + source['width'] <= 1.0001 and source['y'] + source['height'] <= 1.0001):
        raise ValueError('source_rect must lie inside the source (normalized 0-1, width/height >= 0.02)')
    if not (target['width'] > 0 and target['height'] > 0):
        raise ValueError('target_rect needs a positive width and height')
    W, H = stage.settings.width, stage.settings.height
    details = []
    for item_id in item_ids:
        item = stage.item_by_id(item_id)
        if item is None:
            raise ValueError('Unknown item: ' + str(item_id))
        media = stage.media_by_id(item.media_id)
        if item.track not in stage.video_tracks or item.role in ('title', 'graphic') or not media or media.kind not in ('video', 'image') \
                or not media.width or not media.height:
            raise ValueError(f'{item_id} is not a picture clip with known dimensions')
        if stage.track_states.get(item.track, {}).get('locked'):
            raise ValueError('Track is locked')
        sw, sh = media.width, media.height
        base = max(W / sw, H / sh)
        crop = dict(source)
        tw, th = target['width'] * W, target['height'] * H
        rw, rh = sw * crop['width'] * base, sh * crop['height'] * base
        scale = min(tw / rw, th / rh) if mode == 'fit' else max(tw / rw, th / rh)
        if mode == 'fill':                                  # trim the region to the box's shape, around its centre
            wanted_w = min(crop['width'], tw / (scale * sw * base))
            wanted_h = min(crop['height'], th / (scale * sh * base))
            crop['x'] += (crop['width'] - wanted_w) / 2
            crop['y'] += (crop['height'] - wanted_h) / 2
            crop['width'], crop['height'] = wanted_w, wanted_h
        crop = {k: round(v, 5) for k, v in crop.items()}
        item.crop = Crop(**crop)
        item.transform.scale = item.transform.scale_y = round(scale, 5)
        item.transform.scale_linked = True
        item.transform.anchor_x = item.transform.anchor_y = 0.
        item.transform.x = round(target['x'] + target['width'] / 2, 5)
        item.transform.y = round(target['y'] + target['height'] / 2, 5)
        layer_w, layer_h = sw * crop['width'] * base * scale, sh * crop['height'] * base * scale
        details.append(dict(id=item_id, crop=crop, transform=dict(x=item.transform.x, y=item.transform.y, scale=item.transform.scale),
                            layer_px=[round(layer_w, 1), round(layer_h, 1)], box_px=[round(tw, 1), round(th, 1)],
                            covers_box=layer_w >= tw - .5 and layer_h >= th - .5))
    stage.touch()
    return details


def compact_timeline(rows):
    """Drop fields that still hold their default value; ids, times and role always stay."""
    from dataclasses import asdict
    from .model import TimelineItem
    base = asdict(TimelineItem('', '', '', 0, 0))
    keep = {'id', 'media_id', 'track', 'start', 'duration', 'in_point', 'role'}
    out = []
    for row in rows:
        row = dict(row)
        if row.get('role') != 'title':
            row.pop('title_style', None)
        for key in list(row):
            if key in keep:
                continue
            value = row[key]
            if value == base.get(key):
                del row[key]
            elif isinstance(value, dict) and isinstance(base.get(key), dict):
                trimmed = {k: v for k, v in value.items() if v != base[key].get(k)}
                if trimmed:
                    row[key] = trimmed
                else:
                    del row[key]
        out.append(row)
    return out
