"""Named timeline content; assets and document identity belong to the project."""
import copy
from dataclasses import asdict,is_dataclass,fields

STATE_FIELDS=('settings','timeline','captions','subtitle_style','extra_tracks','track_states',
              'video_tracks','audio_tracks','track_names','transitions','mark_in','mark_out','playhead')
IDENTITY_FIELDS=('active_timeline_id','timeline_name','timeline_number','other_timelines')
SHARED_FIELDS=('name','path','portable_media','created_at','render_history')


def capture(project):
    def encode(value):
        if is_dataclass(value):return asdict(value)
        if isinstance(value,(list,tuple)):return [encode(v) for v in value]
        if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
        return copy.deepcopy(value)
    return dict(id=project.active_timeline_id,name=project.timeline_name,number=project.timeline_number,
                data={key:encode(getattr(project,key)) for key in STATE_FIELDS})


def choices(project):
    current=dict(id=project.active_timeline_id,name=project.timeline_name,number=project.timeline_number)
    return sorted([current]+[{k:row[k] for k in ('id','name','number')} for row in project.other_timelines],key=lambda r:r['number'])


def default_name(project):
    number=max(row['number'] for row in choices(project))+1
    used={row['name'].casefold() for row in choices(project)}
    while f'Timeline {number}'.casefold() in used:number+=1
    return f'Timeline {number}'


def validated_name(project,name,identifier=None):
    name=str(name).strip()
    if not name:raise ValueError('Enter a timeline name.')
    if len(name)>120:raise ValueError('Use a timeline name of 120 characters or fewer.')
    if any(row['id']!=identifier and row['name'].casefold()==name.casefold() for row in choices(project)):
        raise ValueError('A timeline with that name already exists.')
    return name


def switch(project,identifier):
    if identifier==project.active_timeline_id:return False
    target=next((r for r in project.other_timelines if r['id']==identifier),None)
    if target is None:raise ValueError('This timeline no longer exists.')
    # Decode completely before touching the live document.
    from .model import Project
    decoded=Project.from_dict(target['data'])
    previous=capture(project)
    remaining=[r for r in project.other_timelines if r['id']!=identifier]+[previous]
    for key in STATE_FIELDS:setattr(project,key,copy.deepcopy(getattr(decoded,key)))
    project.active_timeline_id=target['id'];project.timeline_name=target['name'];project.timeline_number=target['number']
    project.other_timelines=sorted(remaining,key=lambda r:r['number'])
    project.ensure_track_model();project.touch();return True


def create(project,name=''):
    from .model import Project,uid
    name=validated_name(project,name.strip() or default_name(project))
    number=max(row['number'] for row in choices(project))+1
    fresh=Project(settings=copy.deepcopy(project.settings),subtitle_style=copy.deepcopy(project.subtitle_style),
                  active_timeline_id=uid(),timeline_name=name,timeline_number=number)
    project.other_timelines.append(capture(fresh));switch(project,fresh.active_timeline_id)
    return fresh.active_timeline_id


def active_snapshot(project):
    """A detached render/history/compound snapshot without inactive timelines."""
    from .model import Project
    return Project(**{f.name:copy.deepcopy(getattr(project,f.name)) for f in fields(Project) if f.name!='other_timelines'})


def decode_states(raw):
    from .model import Project,uid
    rows=raw.get('other_timelines',[])
    if not isinstance(rows,list):raise ValueError('Invalid project timelines.')
    seen={raw.get('active_timeline_id','timeline_1')};result=[]
    for index,row in enumerate(rows,2):
        if not isinstance(row,dict) or not isinstance(row.get('data'),dict):raise ValueError('Invalid saved timeline.')
        identifier=str(row.get('id') or uid())
        if identifier in seen:raise ValueError('Duplicate timeline identity in project.')
        seen.add(identifier)
        data={key:copy.deepcopy(row['data'][key]) for key in STATE_FIELDS if key in row['data']}
        decoded=Project.from_dict(data)
        decoded.active_timeline_id=identifier;decoded.timeline_name=str(row.get('name') or f'Timeline {index}')[:120]
        try:decoded.timeline_number=max(1,int(row.get('number',index)))
        except (TypeError,ValueError):decoded.timeline_number=index
        result.append(capture(decoded))
    return result


def inactive_media_ids(project):
    return {item.get('media_id') for row in project.other_timelines for item in row['data'].get('timeline',[])}
