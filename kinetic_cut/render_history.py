"""Completed render metadata; never serialize executable jobs or edit snapshots."""
import copy
import json
import math
import os
import time
import uuid
import threading
from types import SimpleNamespace
from dataclasses import asdict
from pathlib import Path

_generation_lock=threading.Lock()
_disk_lock=threading.Lock()
_generations={}


def issue_write(project):
    if not project.path:return None
    key=os.path.normcase(os.path.abspath(project.path))
    with _generation_lock:
        token=_generations.get(key,0)+1;_generations[key]=token
    return SimpleNamespace(path=str(project.path),created_at=project.created_at,render_history=copy.deepcopy(project.render_history)),key,token


def publish_write(request):
    project,key,token=request
    with _disk_lock:
        with _generation_lock:
            if _generations.get(key)!=token:return True
        return persist(project)


def records(values):
    if not isinstance(values,list):return []
    result=[];seen=set()
    for value in values[-200:]:
        if not isinstance(value,dict) or value.get('state')!='Complete':continue
        if not all(isinstance(value.get(k),str) for k in ('id','output','name')):continue
        if not value['id'] or value['id'] in seen or not value['output'] or any(len(value[k])>32768 for k in ('id','output','name')):continue
        try:
            numeric={k:float(value[k]) for k in ('elapsed','completed_at','width','height','fps')}
            if not all(math.isfinite(v) and v>=0 for v in numeric.values()):continue
            if not 1<=numeric['fps']<=1000 or not 1<=numeric['width']<=32768 or not 1<=numeric['height']<=32768:continue
        except (KeyError,ValueError,TypeError):continue
        preset=value.get('preset',{})
        if not isinstance(preset,dict):continue
        try:
            bitrate=float(preset['bitrate_mbps']);audio=int(preset['audio_kbps'])
            if not math.isfinite(bitrate) or not .1<=bitrate<=500 or not 0<=audio<=1536:continue
            if preset.get('codec') not in ('h264','h265') or preset.get('quality','bitrate') not in ('auto','bitrate'):continue
            preset=dict(name=str(preset['name'])[:512],description=str(preset['description'])[:4096],codec=preset['codec'],
                bitrate_mbps=bitrate,audio_kbps=audio,quality=preset.get('quality','bitrate'))
        except (KeyError,ValueError,TypeError,OverflowError):continue
        row={k:value[k] for k in ('id','output','name')};row.update(numeric)
        row.update(state='Complete',preset=copy.deepcopy(preset),hardware=str(value.get('hardware','Auto'))[:64],burn=bool(value.get('burn',False)),audio=bool(value.get('audio',True)))
        result.append(row);seen.add(row['id'])
    return result


def completed_record(job):
    project=job['project'];settings=project.settings
    return dict(id=job.setdefault('history_id',uuid.uuid4().hex),state='Complete',output=job['output'],name=project.name,
        width=settings.width,height=settings.height,fps=settings.fps,elapsed=job.get('elapsed',0),completed_at=time.time(),
        preset=asdict(job['preset']),hardware=job.get('hardware','Auto'),burn=job.get('burn',False),audio=job.get('audio',True))


def restore(values):
    from .model import Project,ProjectSettings
    from .exporter import ExportPreset
    result=[]
    for row in records(values):
        fields={k:v for k,v in row['preset'].items() if k in ExportPreset.__dataclass_fields__}
        try:preset=ExportPreset(**fields)
        except (TypeError,ValueError):continue
        project=Project(name=row['name'],settings=ProjectSettings(width=int(row['width']),height=int(row['height']),fps=row['fps']))
        result.append(dict(project=project,output=row['output'],preset=preset,hardware=row['hardware'],burn=row['burn'],audio=row['audio'],
            state='Complete',elapsed=row['elapsed'],history_id=row['id'],history_only=True))
    return result


def persist(project):
    """Patch only metadata on disk; never auto-save unsaved timeline changes."""
    if not project.path:return True
    path=Path(project.path)
    try:
        if path.is_symlink() or not path.is_file() or path.suffix.lower()!='.kcut':return False
        for _ in range(2):
            before=path.stat();raw=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(raw,dict) or raw.get('created_at')!=project.created_at:return False
            raw['render_history']=records(project.render_history)
            pending=path.with_name(path.name+'.render-history-'+uuid.uuid4().hex+'.tmp')
            try:
                pending.write_text(json.dumps(raw,indent=2),encoding='utf-8')
                current=path.stat()
                if (current.st_size,current.st_mtime_ns)!=(before.st_size,before.st_mtime_ns):continue
                os.replace(pending,path);return True
            finally:pending.unlink(missing_ok=True)
    except (OSError,ValueError,TypeError):return False
    return False


def add(project,job,publish=True):
    row=completed_record(job)
    project.render_history=records([r for r in records(project.render_history) if r['id']!=row['id']]+[row])
    return persist(project) if publish else True


def remove(project,identifier,publish=True):
    project.render_history=[r for r in records(project.render_history) if r['id']!=identifier]
    return persist(project) if publish else True
