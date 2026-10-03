"""Versioned timeline clipboard. Paste is an atomic, non-ripple overwrite edit."""
import copy
import json
import math
from dataclasses import asdict
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication
from .model import TimelineItem, Caption, CaptionStyle, Crop, Transform, MediaItem, uid, _known

MIME="application/x-kinetic-cut-timeline-v1"


def capture(project,item_ids,caption_ids):
    items=[copy.deepcopy(i) for i in project.timeline if i.id in item_ids]
    captions=[copy.deepcopy(c) for c in project.captions if c.id in caption_ids]
    if not items and not captions:return None
    for caption in captions:
        caption.style=copy.deepcopy(project.caption_style(caption)); caption.customize=True
    tracks={}
    for item in items:
        kind="audio" if item.track in project.audio_tracks else "video"
        tracks[item.track]={"kind":kind,"index":getattr(project,kind+"_tracks").index(item.track),"name":project.track_names.get(item.track,item.track)}
    return {"version":1,"items":[asdict(i) for i in items],"captions":[asdict(c) for c in captions],
            "media":[asdict(m) for m in project.media if any(i.media_id==m.id for i in items)],"tracks":tracks}


def put(payload):
    mime=QMimeData(); mime.setData(MIME,json.dumps(payload).encode("utf-8")); QApplication.clipboard().setMimeData(mime)


def get():
    mime=QApplication.clipboard().mimeData()
    if not mime or not mime.hasFormat(MIME):return None
    raw=bytes(mime.data(MIME))
    if len(raw)>4_000_000:return None
    try:
        payload=json.loads(raw)
        if payload.get("version")!=1:return None
        return payload
    except (ValueError,AttributeError):return None


def paste(project,payload,position,target_track=""):
    """Stage the edit first: invalid data or locked lanes leave the project intact."""
    if not payload:raise ValueError("Copy a timeline clip first.")
    stage=copy.deepcopy(project)
    items=[]; captions=[]
    try:
        for raw in payload["items"]:
            data=_known(TimelineItem,raw); data["crop"]=Crop(**_known(Crop,data.get("crop",{}))); data["transform"]=Transform(**_known(Transform,data.get("transform",{})))
            items.append(TimelineItem(**data))
        for raw in payload["captions"]:
            data=_known(Caption,raw); data["style"]=CaptionStyle(**_known(CaptionStyle,data.get("style",{}))); captions.append(Caption(**data))
        moments=[i.start for i in items]+[c.start for c in captions]
        if not moments or len(moments)>10000:raise ValueError()
        durations=[i.duration for i in items]+[c.end-c.start for c in captions]
        if not all(math.isfinite(x) and x>=0 for x in moments+[position]) or not all(math.isfinite(x) and x>0 for x in durations):raise ValueError()
        track_map={}
        for old,info in payload["tracks"].items():
            kind=info["kind"]; index=info["index"]
            if kind not in {"audio","video"} or not isinstance(index,int) or not 0<=index<100:raise ValueError()
            lanes=getattr(stage,kind+"_tracks")
            if target_track:
                first=min(info["index"] for info in payload["tracks"].values() if info["kind"]==kind)
                index=index-first+(lanes.index(target_track) if target_track in lanes else 0)
            while index>=len(lanes):stage.add_track(kind)
            track_map[old]=lanes[index] if target_track else old if old in lanes else lanes[index]
        targets={track_map[i.track] for i in items}|({"subtitle_1"} if captions else set())
    except (KeyError,TypeError,AttributeError,ValueError,OverflowError) as error:
        raise ValueError("The clipboard does not contain valid timeline clips.") from error
    if any(stage.track_states.get(track,{}).get("locked",False) for track in targets):raise ValueError("Unlock the destination tracks before pasting.")
    media_map={}
    from .media_insert import source_key
    for raw in payload.get("media",[]):
        media=MediaItem(**_known(MediaItem,raw)); existing=next((m for m in stage.media if source_key(m.path)==source_key(media.path) and not m.timeline_preset),None)
        old=media.id; media.id=existing.id if existing else uid(); media_map[old]=media.id
        if not existing:stage.media.append(media)
    offset=position-min(moments); links={}; groups={}
    for item in items:
        item.id=uid(); item.start+=offset; item.track=track_map[item.track]; item.media_id=media_map.get(item.media_id,item.media_id)
        if item.group_id:item.group_id=groups.setdefault(item.group_id,uid())
        if item.link_id:item.link_id=links.setdefault(item.link_id,uid())
    for caption in captions:caption.id=uid(); caption.start+=offset; caption.end+=offset
    stage.timeline.extend(items); stage.overwrite({i.id for i in items})
    stage.captions.extend(captions); stage.overwrite_captions({c.id for c in captions})
    for attr in ("timeline","captions","media","video_tracks","audio_tracks","track_states","track_names"):
        setattr(project,attr,getattr(stage,attr))
    project.touch()
    return {i.id for i in items},{c.id for c in captions}
