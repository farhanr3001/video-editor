"""Plan bin insertions without changing the project; preview and drop share it."""
import copy,os
from .model import TimelineItem,Transform,Crop,uid

def source_key(path):return os.path.normcase(os.path.abspath(path)) if path else ""

def plan(project,assets,track,start):
    stage=copy.copy(project)
    for field in ("timeline","captions","media","video_tracks","audio_tracks"):setattr(stage,field,list(getattr(project,field)))
    stage.track_names=dict(project.track_names); stage.track_states=copy.deepcopy(project.track_states)
    placed=set(); placed_caps=set()
    # Discard unused compatibility wrappers from the old build, never source files.
    used={i.media_id for i in stage.timeline}; stage.media=[m for m in stage.media if not m.timeline_preset or m.id in used]
    if track in {"__new_video","__new_audio","__new_audio_top"}:
        kind="video" if track=="__new_video" else "audio"; at_top=track.endswith("_top"); track=stage.add_track(kind)
        if at_top:stage.audio_tracks.remove(track); stage.audio_tracks.insert(0,track)
    if stage.track_states.get(track,{}).get("locked"):raise ValueError("Unlock the destination track before adding media.")
    cursor=max(0.,float(start))
    for asset in assets:
        if asset.timeline_preset:
            from .binclips import restore
            ids,caps=restore(stage,asset,track or (stage.audio_tracks[0] if asset.kind=="audio" else stage.video_tracks[-1]),cursor)
            placed.update(ids); placed_caps.update(caps)
            cursor=max([cursor]+[i.start+i.duration for i in stage.timeline if i.id in ids]+[c.end for c in stage.captions if c.id in caps]); continue
        media=next((m for m in stage.media if not m.timeline_preset and source_key(m.path)==source_key(asset.path)),None)
        if not media:media=copy.deepcopy(asset); stage.media.append(media)
        video=media.kind in {"video","image"}
        destination=(track if track in stage.video_tracks else stage.video_tracks[-1]) if video else (track if track in stage.audio_tracks else stage.audio_tracks[0])
        if stage.track_states.get(destination,{}).get("locked"):raise ValueError("Unlock the destination track before adding media.")
        in_point=max(0,stage.mark_in)
        duration=(stage.mark_out-in_point) if stage.mark_out>in_point else max(.1,media.duration-in_point) if media.kind!="image" else 5.
        group=uid(); role=("content" if not any(i.role=="content" for i in stage.timeline) else "normal") if video else ("music" if media.duration>=20 else "sfx")
        stage.timeline.append(TimelineItem(uid(),media.id,destination,cursor,duration,in_point,group_id=group,role=role,transform=Transform(.5,.5,1),crop=Crop(),gain_db=0 if video else -10 if role=="music" else -3))
        placed.add(stage.timeline[-1].id)
        if video and media.has_audio:
            audio=track if track in stage.audio_tracks else next((lane for lane in stage.audio_tracks if not stage.track_states.get(lane,{}).get("locked") and not any(i.track==lane and i.start<cursor+duration and i.start+i.duration>cursor for i in stage.timeline)),None)
            if not audio:audio=stage.add_track("audio")
            if stage.track_states.get(audio,{}).get("locked"):raise ValueError("Unlock the linked audio destination before adding media.")
            stage.timeline.append(TimelineItem(uid(),media.id,audio,cursor,duration,in_point,group_id=group,role="source_audio"))
            placed.add(stage.timeline[-1].id)
        cursor+=duration
    return stage,placed&{i.id for i in stage.timeline},placed_caps&{c.id for c in stage.captions}

def commit(project,stage):
    for field in ("timeline","captions","media","video_tracks","audio_tracks","track_names","track_states"):setattr(project,field,getattr(stage,field))
    project.touch()
