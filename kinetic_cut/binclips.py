"""Reusable Power Bin clips store a detached timeline snapshot, not a project link."""
from .model import MediaItem,uid
from .clipboard import capture,paste

MIME="application/x-kinetic-timeline-preset"

def snapshot(project,item_ids,caption_ids,primary_id=""):
    payload=capture(project,item_ids,caption_ids)
    if not payload:return None
    payload["primary_id"]=primary_id
    return payload

def asset(payload):
    items=payload.get("items",[]); captions=payload.get("captions",[])
    primary=next((i for i in items if i["id"]==payload.get("primary_id")),next(iter(items),None))
    media=next((m for m in payload.get("media",[]) if primary and m["id"]==primary.get("media_id")),{})
    name=(primary.get("title_text") if primary and primary.get("role")=="title" else media.get("name")) or (captions[0]["text"] if captions else "Saved clip")
    kind="title" if primary and primary.get("role")=="title" else "audio" if primary and payload["tracks"][primary["track"]]["kind"]=="audio" else media.get("kind","caption")
    starts=[i["start"] for i in items]+[c["start"] for c in captions]
    ends=[i["start"]+i["duration"] for i in items]+[c["end"] for c in captions]
    if not starts:raise ValueError("No timeline clips to save.")
    return MediaItem(uid(),media.get("path",""),kind,name.replace("\n"," ")[:120],max(ends)-min(starts),media.get("width",0),media.get("height",0),media.get("fps",0),any(info["kind"]=="audio" for info in payload.get("tracks",{}).values()),media.get("thumbnail",""),payload)

def restore(project,media,track,start):
    return paste(project,media.timeline_preset,start,target_track=track)
