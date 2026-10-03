"""Offline media state and conservative relinking. Never retime or resize a cut.

Presence is published by the UI's background monitor. Painting and playback only
read this map: they never stat a disk/network file on each frame.
"""
import copy
import os
import weakref
from pathlib import Path
from dataclasses import fields,asdict
from .model import MediaItem, Project

_missing = {}
_nested_status = {}

def path_key(path):
    return os.path.normcase(os.path.abspath(path)) if path else ''

def scan(paths):
    result = {}
    for path in set(paths):
        if not path:continue
        try:result[path_key(path)] = not Path(path).is_file()
        except OSError:result[path_key(path)] = True
    return result

def publish(values):
    # An initial scan confirming an available file is not a media-state
    # transition. Invalidating it would discard a preview proxy that may have
    # finished while the background availability scan was in flight.
    changed = {key for key, value in values.items()
               if _missing.get(key) != value and (value or key in _missing)}
    _missing.update(values)
    if changed:_nested_status.clear()
    return changed

def is_missing(media):
    if not media:return True
    if media.compound or media.timeline_preset:
        body=media.compound or media.timeline_preset
        cached=_nested_status.get(id(media))
        if cached and cached[0]() is media and cached[1]==id(body):return cached[2]
        # Only inspect cached child state, never the regenerable compound cache.
        items=body.get('timeline',body.get('items',[])); used={i['media_id'] for i in items if i.get('role') not in {'title','graphic'}}
        result=any(i.get('source_mismatch') for i in items) or any(is_missing(MediaItem(**m)) for m in body.get('media',[]) if m['id'] in used)
        if len(_nested_status)>128:_nested_status.clear()
        _nested_status[id(media)]=(weakref.ref(media),id(body),result)
        return result
    if media.kind not in {'video','audio','image'}:return False
    return _missing.get(path_key(media.path), False)

def unavailable(media, item=None):
    if item and item.role in {'title','graphic'}:return False
    return bool(item and item.source_mismatch) or is_missing(media)

def label(media, item=None):
    name = (item.source_requirement.get('name') if item and item.source_mismatch else '') or (Path(media.path).name if media and media.path else media.name if media else 'Media')
    return name + (' mismatch' if item and item.source_mismatch else ' is missing')

def source_paths(project):
    paths=[]
    def walk(media):
        for m in media:
            if m.get('compound'):walk(m['compound'].get('media',[]))
            elif m.get('timeline_preset'):walk(m['timeline_preset'].get('media',[]))
            elif m.get('kind') in {'video','audio','image'} and m.get('path'):paths.append(m['path'])
    # Don't serialize/deepcopy the whole edit just to inspect file paths.
    for m in project.media:
        if m.compound:walk(m.compound.get('media',[]))
        elif m.timeline_preset:walk(m.timeline_preset.get('media',[]))
        elif m.kind in {'video','audio','image'} and m.path:paths.append(m.path)
    return paths

def iter_media(project):
    for media in project.media:
        yield media
        if media.compound:yield from iter_media(Project.from_dict(media.compound))

def leaf_media(media):
    body=media.compound or media.timeline_preset
    if body:
        for raw in body.get('media',[]):yield from leaf_media(MediaItem(**raw))
    else:yield media

def replace_bin_asset(media,old_path,replacement):
    if media.timeline_preset:
        payload=copy.deepcopy(media.timeline_preset)
        tracks=payload.get('tracks',{})
        child=Project.from_dict(dict(media=payload.get('media',[]),timeline=payload.get('items',[]),
            video_tracks=[t for t,v in tracks.items() if v['kind']=='video'],audio_tracks=[t for t,v in tracks.items() if v['kind']=='audio']))
        replace(child,old_path,replacement)
        payload['media']=[asdict(m) for m in child.media]; payload['items']=[asdict(i) for i in child.timeline]
        media.timeline_preset=payload
        if path_key(media.path)==path_key(old_path):
            for name in ('path','name','kind','width','height','fps','thumbnail'):setattr(media,name,getattr(replacement,name))
    elif media.compound:
        child=Project.from_dict(media.compound); replace(child,old_path,replacement)
        from .compounds import update_asset
        update_asset(media,child)
    else:
        for field in fields(MediaItem):
            if field.name not in {'id','pool_hidden'}:setattr(media,field.name,copy.deepcopy(getattr(replacement,field.name)))

def compatible(item, replacement, audio):
    kind=item.source_requirement.get('kind',replacement.kind)
    if audio:
        if not replacement.has_audio:return False
    elif kind=='image':
        if replacement.kind!='image':return False
    elif replacement.kind!='video' or replacement.width<=0 or replacement.height<=0:return False
    if kind=='image':return True
    # Only floating-point tolerance, never silently clamp a missing source frame.
    duration=replacement.stream_durations.get('audio' if audio else 'video',replacement.duration)
    return item.in_point>=-1e-7 and item.in_point+item.duration*item.speed<=duration+1e-6

def replace(project, old_path, replacement, media_ids=None):
    """Update matching assets (including nested edits), preserving every cut value.

    A blocked cut keeps its original requirement and is never decoded/exported
    using the incompatible replacement. A later replacement revalidates it.
    """
    restored=blocked=0
    for media in project.media:
        if media.compound:
            child=Project.from_dict(media.compound)
            counts=replace(child,old_path,replacement)
            if sum(counts):
                from .compounds import update_asset
                update_asset(media,child)
            restored+=counts[0]; blocked+=counts[1]
        if media.compound or media.timeline_preset or path_key(media.path)!=path_key(old_path) or media_ids is not None and media.id not in media_ids:continue
        for item in project.timeline:
            if item.media_id!=media.id or item.role in {'title','graphic'}:continue
            if not item.source_requirement:item.source_requirement={'kind':media.kind,'name':Path(media.path).name}
            item.source_mismatch=not compatible(item,replacement,item.track in project.audio_tracks)
            blocked+=int(item.source_mismatch); restored+=int(not item.source_mismatch)
        for field in fields(MediaItem):
            if field.name not in {'id','pool_hidden','compound','timeline_preset'}:setattr(media,field.name,copy.deepcopy(getattr(replacement,field.name)))
    return restored,blocked

def export_issues(project):
    issues=[]
    for item in project.timeline:
        if item.role in {'title','graphic'} or item.muted:continue
        state=project.track_states.get(item.track,{})
        if not state.get('visible',True) or state.get('muted',False):continue
        media=project.media_by_id(item.media_id)
        if media and media.compound:issues.extend(export_issues(Project.from_dict(media.compound)))
        elif item.source_mismatch:issues.append(label(media,item))
        elif not media or not media.path or not Path(media.path).is_file():issues.append(label(media))
    return sorted(set(issues))

def offline_icon(audio=False):
    from PySide6.QtCore import Qt,QRectF
    from PySide6.QtGui import QPixmap,QPainter,QColor,QPen,QIcon
    pix=QPixmap(110,65); pix.fill(QColor('#410b0d'))
    p=QPainter(pix); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor('#ef5c51'),2)); p.setBrush(Qt.NoBrush); p.drawRoundedRect(QRectF(1,1,108,63),4,4)
    p.setPen(QPen(QColor('#cf493f'),2))
    if audio:p.drawLine(10,32,100,32)
    else:
        p.drawRect(37,18,37,27); p.drawLine(31,49,80,13)
        for x in (41,50,59,68):p.drawLine(x,19,x,23); p.drawLine(x,40,x,44)
    p.end(); return QIcon(pix)
