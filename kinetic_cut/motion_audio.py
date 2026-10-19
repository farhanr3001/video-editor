"""Composition-owned sound cues projected into the established audio pipeline.

No stored timeline lane is created. Cue time lives in composition source seconds,
so ordinary graphic moves, trims, splits, duplication and re-time stay coherent.
"""
import copy
import hashlib
import math
from pathlib import Path
from .model import MediaItem,TimelineItem


def validate(cues):
    if not isinstance(cues,list) or len(cues)>32:raise ValueError('A composition supports at most 32 sound cues.')
    result=[]; ids=set()
    for raw in cues:
        if not isinstance(raw,dict) or set(raw)-{'id','source','time','in_point','duration','source_duration','gain_db','enabled','name','event','node_id','channel','key_time'}:
            raise ValueError('Unknown sound cue property.')
        cue=copy.deepcopy(raw)
        if not isinstance(cue.get('id'),str) or not cue['id'] or cue['id'] in ids:raise ValueError('Sound cues need unique IDs.')
        ids.add(cue['id'])
        if not isinstance(cue.get('source'),str) or not cue['source']:raise ValueError('Sound cues need an audio source path.')
        import re
        if len(cue['source'])>32768 or '\0' in cue['source'] or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://',cue['source']):raise ValueError('Sound cues require local file paths.')
        for key,default,low,high in [('time',0,0,100000),('in_point',0,0,100000),('duration',1,.01,100000),('source_duration',1,.01,100000),('gain_db',0,-60,0),('key_time',0,-100000,100000)]:
            value=cue.get(key,default)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Invalid sound cue '+key)
            cue[key]=float(value)
        if cue['in_point']+cue['duration']>cue['source_duration']+.001:raise ValueError('Sound cue exceeds its source audio.')
        if not isinstance(cue.get('enabled',True),bool):raise ValueError('Sound cue enabled must be boolean.')
        if cue.get('event','time') not in ('time','layer_start','layer_end','keyframe'):raise ValueError('Unknown cue event.')
        for key in ('node_id','channel','name'):
            if key in cue and not isinstance(cue[key],str):raise ValueError('Invalid sound cue '+key)
        result.append(cue)
    return result


def at(cue,scene):
    event=cue.get('event','time')
    if event=='time':return cue['time']
    node=next((n for n in scene.get('nodes',[]) if n['id']==cue.get('node_id')),None)
    if node is None:return None
    if event in ('layer_start','layer_end'):return node.get('start',0) if event=='layer_start' else node.get('end')
    key=next((k for k in node.get('keyframes',{}).get(cue.get('channel'),[]) if abs(k['time']-cue['key_time'])<1e-7),None)
    return key['time'] if key else None


def project_cues(project):
    items=[]; media=[]
    for graphic in project.timeline:
        scene=graphic.graphic_data.get('scene',{}) if graphic.role=='graphic' else {}
        cues=scene.get('sound_cues',[])
        if not cues:continue
        state=project.track_states.get(graphic.track,{})
        if graphic.muted or not state.get('visible',True) or state.get('muted',False):continue
        for cue in cues:
            if not cue.get('enabled',True):continue
            stamp=at(cue,scene)
            if stamp is None:continue
            left=max(stamp,graphic.in_point); right=min(stamp+cue['duration'],graphic.in_point+graphic.source_duration)
            if right<=left:continue
            # Different graphics must have independent gain/lane clocks even
            # when the same cash sound is reused at exactly the same timestamp.
            identifier='__cue__'+graphic.id+'_'+cue['id']; track=identifier
            fingerprint=hashlib.sha256(cue['source'].encode()).hexdigest()[:20]
            mid='__cue_source__'+fingerprint
            if not any(m.id==mid for m in media):media.append(MediaItem(mid,cue['source'],'audio',Path(cue['source']).name,cue['source_duration'],has_audio=True))
            items.append(TimelineItem(identifier,mid,track,graphic.start+(left-graphic.in_point)/graphic.speed,
                                      (right-left)/graphic.speed,cue['in_point']+left-stamp,
                                      speed=graphic.speed,role='sfx',gain_db=cue['gain_db']))
    return items,media


def expanded(project):
    items,media=project_cues(project)
    existing={i.id for i in project.timeline}; items=[i for i in items if i.id not in existing]
    if not items:return project
    known={m.id for m in project.media}; media=[m for m in media if m.id not in known]
    view=copy.copy(project); view.timeline=project.timeline+items; view.media=project.media+media
    view.audio_tracks=project.audio_tracks+[i.track for i in items]
    view.video_tracks=list(project.video_tracks); view.track_names=dict(project.track_names)
    view.track_states=copy.deepcopy(project.track_states)
    return view


def playback_view(project,previous=None):
    revision=(id(project),project.__dict__.get('_edit_revision',0),repr(project.track_states))
    if previous and previous[0]==revision:return previous[1],previous
    signature=[]
    for item in project.timeline:
        scene=item.graphic_data.get('scene',{}) if item.role=='graphic' else {}
        if not scene.get('sound_cues'):continue
        signature.append((item.id,item.start,item.duration,item.in_point,item.speed,item.muted,
                          repr(project.track_states.get(item.track,{})),repr(scene['sound_cues']),
                          repr([(n['id'],n.get('start'),n.get('end'),n.get('keyframes')) for n in scene.get('nodes',[])])))
    if not signature:return project,(revision,project)
    view=expanded(project)
    return view,(revision,view)


def rebase(scene,base,relative=False):
    import os
    for cue in scene.get('sound_cues',[]):
        path=cue.get('source','')
        if not path:continue
        if relative:
            try:cue['source']=os.path.relpath(path,base)
            except ValueError:pass
        elif not Path(path).is_absolute():cue['source']=str((Path(base)/path).resolve())
