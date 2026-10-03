"""Atomic, source-preserving timeline operations used by audio actions and menus."""
import copy
from .model import uid


def merge_ranges(ranges):
    result=[]
    for start,end in sorted(ranges):
        if end<=start:continue
        if result and start<=result[-1][1]+1e-7:result[-1]=(result[-1][0],max(end,result[-1][1]))
        else:result.append((start,end))
    return result


def complement(duration, cuts):
    cursor=0.; keep=[]
    for start,end in merge_ranges((max(0,a),min(duration,b)) for a,b in cuts):
        if start>cursor:keep.append((cursor,start))
        cursor=max(cursor,end)
    if cursor<duration:keep.append((cursor,duration))
    return keep


def fragment(item,a,b,start):
    result=copy.deepcopy(item); result.id=uid(); result.start=start; result.duration=b-a
    result.in_point=item.in_point+a*item.speed
    from .keyframes import shift
    shift(result,a)
    result.fade_in=min(result.duration,item.fade_in) if a<1e-7 else 0.
    result.fade_out=min(result.duration,item.fade_out) if b>=item.duration-1e-7 else 0.
    return result


def aligned_linked_av(project,audio):
    if not audio or audio.track not in project.audio_tracks:
        raise ValueError("Drop Remove Silence onto an audio clip linked to a video clip.")
    linked=project.linked_items(audio)
    if not any(i.track in project.video_tracks and i.role!="title" for i in linked):
        raise ValueError("The audio clip must be linked to a video clip with the same timeline start and duration.")
    if any(abs(i.start-audio.start)>1e-5 or abs(i.duration-audio.duration)>1e-5 for i in linked):
        raise ValueError("All linked video and audio clips must have the same timeline start and duration before removing silence.")
    if any(project.track_states.get(i.track,{}).get("locked") for i in linked):
        raise ValueError("Unlock all linked video and audio layers before removing silence.")
    return linked


def keep_audio_ranges(project,audio,keep,pack=False):
    """Pack an aligned AV group locally, or cut audio alone without ripple."""
    targets=aligned_linked_av(project,audio) if pack else [audio]
    if any(project.track_states.get(i.track,{}).get("locked") for i in targets):raise ValueError("Unlock the audio layer first.")
    keep=merge_ranges((max(0,a),min(audio.duration,b)) for a,b in keep)
    if keep==[(0,audio.duration)]:return []
    generated=[]; cursor=audio.start
    for a,b in keep:
        group=uid()
        for item in targets:
            clip=fragment(item,a,b,cursor if pack else item.start+a)
            clip.group_id=group; clip.link_id=group if pack else ""
            generated.append(clip)
        if pack:cursor+=b-a
    ids={i.id for i in targets}
    project.timeline=[i for i in project.timeline if i.id not in ids]+generated
    project.touch(); return [i.id for i in generated]


def narrative_gaps(project):
    """Lowest story-video lane guides cuts; still/title/music overlays do not.

    Source audio and sound effects protect audible material inside a candidate
    gap. A long logo therefore cannot prevent closing a genuine story gap.
    """
    media={m.id:m for m in project.media}
    videos=[i for i in project.timeline if i.track in project.video_tracks and i.role not in {"title","background","facecam"} and media.get(i.media_id) and media[i.media_id].kind=="video"]
    if videos:
        content=[i for i in videos if i.role=="content"]
        candidates=content or videos
        lane=min((i.track for i in candidates),key=project.video_tracks.index)
        anchors=[i for i in videos if i.track==lane]
    else:
        audio=[i for i in project.timeline if i.track in project.audio_tracks and i.role!="music"]
        lane=min((i.track for i in audio),key=project.audio_tracks.index) if audio else None
        anchors=[i for i in audio if i.track==lane]
        if not anchors:
            lane=next((t for t in project.video_tracks if any(i.track==t for i in project.timeline)),None)
            anchors=[i for i in project.timeline if i.track==lane]
    if not anchors:return []
    end=max(i.start+i.duration for i in anchors)
    protected=anchors+[i for i in project.timeline if i.track in project.audio_tracks and i.role!="music" and not i.muted]
    return complement(end,[(i.start,i.start+i.duration) for i in protected])


def delete_gaps(project):
    gaps=narrative_gaps(project)
    if not gaps:return 0.,[]
    def mapped(time):return time-sum(max(0,min(time,b)-a) for a,b in gaps if time>a)
    affected=[i for i in project.timeline if i.start+i.duration>gaps[0][0]]
    if any(project.track_states.get(i.track,{}).get("locked") for i in affected) or (project.track_states.get("subtitle_1",{}).get("locked") and any(c.end>gaps[0][0] for c in project.captions)):
        raise ValueError("Unlock the affected layers before deleting gaps; nothing was changed.")
    timeline=[]; media={m.id:m for m in project.media}
    for item in project.timeline:
        cuts=[(a-item.start,b-item.start) for a,b in gaps]
        keep=complement(item.duration,cuts)
        if keep==[(0,item.duration)]:
            clip=copy.deepcopy(item); clip.start=mapped(item.start); timeline.append(clip); continue
        if item.role in {"title", "graphic"} or (media.get(item.media_id) and media[item.media_id].kind=="image"):
            if mapped(item.start+item.duration)>mapped(item.start):
                clip=copy.deepcopy(item); clip.start=mapped(item.start); clip.duration=mapped(item.start+item.duration)-clip.start
                from .keyframes import clean
                clip.keyframes=clean({name:[dict(k,time=mapped(item.start+k['time'])-clip.start) for k in keys] for name,keys in item.keyframes.items()})
                clip.fade_in=min(clip.fade_in,clip.duration); clip.fade_out=min(clip.fade_out,clip.duration); timeline.append(clip)
        else:
            timeline.extend(fragment(item,a,b,mapped(item.start+a)) for a,b in keep)
    captions=[]
    for original in project.captions:
        cap=copy.deepcopy(original); cap.start=mapped(cap.start); cap.end=mapped(cap.end)
        for word in cap.word_timings:
            word['start']=mapped(original.start+word['start'])-cap.start
            word['end']=mapped(original.start+word['end'])-cap.start
        if cap.end>cap.start:captions.append(cap)
    project.timeline=timeline; project.captions=captions; project.playhead=mapped(project.playhead)
    project.mark_in=mapped(project.mark_in); project.mark_out=mapped(project.mark_out); project.touch()
    return sum(b-a for a,b in gaps),gaps
