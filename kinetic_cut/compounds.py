"""Editable nested timelines, stored with their media asset; lossless render caches."""
import copy,hashlib,json,threading
from pathlib import Path
from .model import Project,MediaItem,TimelineItem,Transform,uid

def content(project):
    data=project.to_dict()
    for name in ('path','playhead','created_at','modified_at','mark_in','mark_out'):data.pop(name,None)
    return data

def validate(data,ancestors=()):
    if len(ancestors)>=8:raise ValueError('Compound nesting is limited to eight levels.')
    if not isinstance(data,dict):raise ValueError('Invalid compound timeline.')
    for media in data.get('media',[]):
        if media.get('compound'):
            if media['id'] in ancestors:raise ValueError('A compound cannot contain itself.')
            validate(media['compound'],ancestors+(media['id'],))

def cache_path(data):
    from .config import CACHE_DIR
    validate(data)
    stamps=[]
    def sources(body):
        for m in body.get('media',[]):
            if m.get('compound'):sources(m['compound'])
            elif m.get('path'):
                try:
                    s=Path(m['path']).stat(); stamps.append((m['path'],s.st_size,s.st_mtime_ns))
                except OSError:stamps.append((m['path'],'missing'))
    sources(data)
    key=hashlib.sha256(json.dumps((data,stamps,'compound-alpha-v3'),sort_keys=True).encode()).hexdigest()
    return CACHE_DIR/'compounds'/(key+'.mkv')

def first_child_thumbnail(child):
    visual_items=sorted([i for i in child.timeline if i.track in child.video_tracks],key=lambda i:i.start)
    for item in visual_items:
        m=child.media_by_id(item.media_id)
        if m:
            if m.thumbnail and Path(m.thumbnail).exists():return m.thumbnail
            if m.kind=='image' and Path(m.path).exists():return m.path
    for m in child.media:
        if m.thumbnail and Path(m.thumbnail).exists():return m.thumbnail
        if m.kind=='image' and Path(m.path).exists():return m.path
    return ''

def update_asset(media,child):
    media.compound=content(child); validate(media.compound,(media.id,))
    media.duration=child.duration; media.width=child.settings.width; media.height=child.settings.height
    media.fps=child.settings.fps; target=cache_path(media.compound); media.path=str(target)
    if target.is_file():
        from .media import make_thumbnail
        media.thumbnail=make_thumbnail(str(target),'video')
    if not media.thumbnail or not Path(media.thumbnail).exists():
        media.thumbnail=first_child_thumbnail(child)
    media.has_alpha=True; media.has_audio=any(i.track in child.audio_tracks for i in child.timeline)

def create(project,item_ids,caption_ids,name):
    item_ids=set(item_ids); caption_ids=set(caption_ids)
    selected=[i for i in project.timeline if i.id in item_ids]
    captions=[c for c in project.captions if c.id in caption_ids]
    if not selected and not captions:raise ValueError('Select clips or captions first.')
    if any(project.track_states.get(i.track,{}).get('locked') for i in selected) or captions and project.track_states.get('subtitle_1',{}).get('locked'):
        raise ValueError('Unlock the selected tracks first.')
    start=min([i.start for i in selected]+[c.start for c in captions])
    end=max([i.start+i.duration for i in selected]+[c.end for c in captions])
    remaining=[i for i in project.timeline if i not in selected]
    selected_ids={i.id for i in selected}; selected_tracks={i.track for i in selected}
    def contained(transition):return transition.start>=start-1e-7 and transition.end<=end+1e-7
    transferred=set()
    boundaries=[]
    for transition in project.transitions:
        references={x for x in (transition.left_item_id,transition.right_item_id) if x}
        if ((references and references<=selected_ids) or (not references and transition.track in selected_tracks)) and contained(transition):
            transferred.add(transition.id)
        elif references.intersection(selected_ids):boundaries.append(transition)
    # A transition to an unselected neighbour can stay on the outer compound
    # edge, provided it is still on the same compositing lane. Reject unsupported
    # interior/cross-lane edges before adding lanes or changing the parent.
    chosen=[i.track for i in selected if i.track in project.video_tracks]
    outer_lane=max(chosen,key=project.video_tracks.index) if chosen else project.video_tracks[-1]
    new_lane=project.track_states.get(outer_lane,{}).get('locked') or any(i.track==outer_lane and i.start<end and i.start+i.duration>start for i in remaining)
    for transition in boundaries:
        if new_lane or transition.track!=outer_lane:
            raise ValueError('Select both sides of the transition, or keep its clips on the same outer lane before creating a compound.')
        left=project.item_by_id(transition.left_item_id); right=project.item_by_id(transition.right_item_id)
        if (left and left.id in selected_ids and abs(left.start+left.duration-end)>1e-7) or (right and right.id in selected_ids and abs(right.start-start)>1e-7):
            raise ValueError('Select both sides of an interior transition before creating a compound.')
    child=copy.deepcopy(project); child.name=name.strip() or 'Compound Clip'; child.path=''; child.playhead=0
    child.timeline=[copy.deepcopy(i) for i in selected]; child.captions=[copy.deepcopy(c) for c in captions]
    # Parent transitions use parent time and clip identities. Only complete
    # selected edges belong inside the child; unrelated transitions must remain
    # outside or they extend child duration and target absent clips.
    child.transitions=[]
    for transition in project.transitions:
        if transition.id in transferred:
            clone=copy.deepcopy(transition); clone.start-=start; child.transitions.append(clone)
    for i in child.timeline:i.start-=start
    for c in child.captions:c.start-=start; c.end-=start
    used={i.media_id for i in child.timeline}; child.media=[m for m in child.media if m.id in used]
    asset=MediaItem(uid(),'','video',child.name,has_audio=any(i.track in child.audio_tracks for i in child.timeline))
    update_asset(asset,child)
    # Collapse into the highest selected video lane. Never overwrite an unselected
    # clip in an intervening gap; allocate a lane when the enclosing span conflicts.
    def lane(kind):
        tracks=getattr(project,kind+'_tracks'); chosen=[i.track for i in selected if i.track in tracks]
        target=max(chosen,key=tracks.index) if chosen and kind=='video' else chosen[0] if chosen else tracks[-1] if tracks else project.add_track(kind)
        if project.track_states.get(target,{}).get('locked') or any(i.track==target and i.start<end and i.start+i.duration>start for i in remaining):target=project.add_track(kind)
        return target
    video_lane=lane('video'); audio_lane=lane('audio') if asset.has_audio else None
    link=uid(); clips=[TimelineItem(uid(),asset.id,video_lane,start,end-start,transform=Transform(.5,.5,1),link_id=link)]
    if audio_lane:clips.append(TimelineItem(uid(),asset.id,audio_lane,start,end-start,link_id=link,role='source_audio'))
    project.transitions=[t for t in project.transitions if t.id not in transferred]
    for transition in boundaries:
        if transition.left_item_id in selected_ids:transition.left_item_id=clips[0].id
        if transition.right_item_id in selected_ids:transition.right_item_id=clips[0].id
    project.media.append(asset); project.timeline=remaining+clips; project.captions=[c for c in project.captions if c not in captions]; project.touch()
    return asset,clips

_locks={}; _lock_guard=threading.Lock()
def render_asset(media,ffmpeg='ffmpeg',progress=None,cancel=None):
    target=cache_path(media.compound); target.parent.mkdir(parents=True,exist_ok=True)
    with _lock_guard:lock=_locks.setdefault(str(target),threading.Lock())
    while not lock.acquire(timeout=.1):
        if cancel and cancel.is_set():raise RuntimeError('Compound preparation cancelled')
    try:
        if not target.is_file():
            from .exporter import export,PRESETS
            child=Project.from_dict(media.compound)
            if child.duration<=0:raise ValueError('The compound timeline is empty.')
            export(child,str(target),PRESETS['YouTube Shorts · Quality'],True,'CPU',ffmpeg,progress,cancel,True,lossless=True)
        return str(target)
    finally:lock.release()

def prepare(project,ffmpeg,progress,cancel):
    if not any(m.compound for m in project.media):return project
    stage=copy.deepcopy(project); used={i.media_id for i in stage.timeline}
    for m in stage.media:
        if m.compound and m.id in used:m.path=render_asset(m,ffmpeg,progress,cancel)
    return stage
