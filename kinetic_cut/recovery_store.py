"""Independent session/project recovery copies; source files are never deleted."""
import copy,hashlib,json,os,re,time,uuid
from pathlib import Path


def root():
    from .config import DATA_DIR
    return DATA_DIR/'recovery'

def regular(path):
    try:return path.is_file() and not path.is_symlink() and not getattr(path.lstat(),'st_file_attributes',0)&0x400
    except OSError:return False


def managed_regular(path):
    """Accept Windows spelling aliases, but never a redirected directory/file."""
    path=Path(path).absolute()
    if '..' in path.parts or not regular(path):return False
    try:
        return all(not parent.is_symlink() and not getattr(parent.lstat(),'st_file_attributes',0)&0x400 for parent in path.parents)
    except OSError:return False

def atomic(path,body):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('Unsafe recovery storage')
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix(path.suffix+'.pending')
    with pending.open('w',encoding='utf-8') as stream:
        json.dump(body,stream,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
    pending.replace(path)

def session(register=True):
    import psutil
    token=uuid.uuid4().hex
    if register:atomic(root()/'sessions'/(token+'.json'),dict(pid=os.getpid(),created=psutil.Process().create_time()))
    return token

def finish(token):
    if token and len(token)==32:
        try:(root()/'sessions'/(token+'.json')).unlink(missing_ok=True)
        except OSError:
            import logging
            logging.exception('Could not retire recovery session marker')

def alive(token):
    import psutil
    if not re.fullmatch('[a-f0-9]{32}',token):return False
    try:
        data=json.loads((root()/'sessions'/(token+'.json')).read_text())
        return abs(psutil.Process(data['pid']).create_time()-data['created'])<.01
    except (OSError,ValueError,KeyError,psutil.Error):return False

def save(document,token):
    if not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('Invalid recovery session')
    marker=root()/'sessions'/(token+'.json')
    if not marker.is_file():
        import psutil
        atomic(marker,dict(pid=os.getpid(),created=psutil.Process().create_time()))
    body=document.to_dict();origin=body.get('path','')
    identity=os.path.normcase(os.path.abspath(origin)) if origin else str(body.get('created_at'))
    key=hashlib.sha256(identity.encode()).hexdigest()[:24]
    folder=root()/token/key;latest=folder/'latest.kcut'
    comparable=copy.deepcopy(body)
    for field in ('playhead','modified_at','render_history'):comparable.pop(field,None)
    fingerprint=hashlib.sha256(json.dumps(comparable,sort_keys=True).encode()).hexdigest()
    now=time.time();previous=None
    if regular(latest):
        try:previous=json.loads(latest.read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
    if previous and previous.get('_recovery',{}).get('fingerprint')==fingerprint:return latest
    # At most one historical checkpoint every five minutes; latest still saves
    # at the normal autosave cadence. No age-based removal of recovery history.
    archived=folder/'archive-clock.json'
    try:last=json.loads(archived.read_text())['time']
    except (OSError,ValueError,KeyError):last=0
    if previous and now-last>=300:
        atomic(folder/(str(time.time_ns())+'.kcut'),previous);atomic(archived,dict(time=now))
    body['portable_media']=False
    body['_recovery']=dict(session=token,source=origin,time=now,fingerprint=fingerprint)
    atomic(latest,body);return latest

def entries(include_legacy=True):
    paths=list(root().glob('*/*/*.kcut'))
    if include_legacy:
        from .config import AUTOSAVE_PATH,DATA_DIR,CACHE_DIR
        paths += [AUTOSAVE_PATH,DATA_DIR/'recovery_backup_user_work.kcut',*(CACHE_DIR/'recovered').glob('*.kcut')]
    result=[];sessions={};availability={}
    for path in paths:
        if not managed_regular(path):continue
        try:
            body=json.loads(path.read_text(encoding='utf-8'));meta=body.get('_recovery',{})
            if not isinstance(body.get('timeline',[]),list):continue
            token=meta.get('session','')
            if token not in sessions:sessions[token]=alive(token) if token else False
            def media_paths(document):
                for media in document.get('media',[]):
                    if media.get('compound'):yield from media_paths(media['compound'])
                    elif media.get('path'):yield media['path']
            missing=0
            for raw in set(media_paths(body)):
                source=Path(raw)
                if not source.is_absolute():source=Path(meta.get('source','')).parent/source
                if str(source).startswith('\\\\'):continue  # Avoid I/O on disconnected network shares.
                if os.name=='nt':
                    import ctypes
                    if ctypes.windll.kernel32.GetDriveTypeW(str(source.anchor))==4:continue
                if str(source) not in availability:availability[str(source)]=source.is_file()
                missing+=not availability[str(source)]
            result.append(dict(path=path,name=body.get('name','Untitled'),time=meta.get('time',path.stat().st_mtime),
                               source=meta.get('source',''),size=path.stat().st_size,
                               active=sessions[token] if token else legacy_active(),missing=missing,
                               crashed=session_crashed(token) if token else legacy_crashed()))
        except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
    return sorted(result,key=lambda row:row['time'],reverse=True)

def legacy_crashed():
    from .config import SESSION_LOCK_PATH,AUTOSAVE_PATH
    import psutil
    if not SESSION_LOCK_PATH.is_file() or not AUTOSAVE_PATH.is_file():return False
    try:
        match=re.search(r'pid=(\d+)',SESSION_LOCK_PATH.read_text())
        return not match or not psutil.pid_exists(int(match[1]))
    except OSError:return False

def legacy_active():
    from .config import SESSION_LOCK_PATH
    import psutil
    try:
        match=re.search(r'pid=(\d+)',SESSION_LOCK_PATH.read_text())
        return bool(match and psutil.pid_exists(int(match[1])))
    except OSError:return False

def has_crashed():
    return legacy_crashed() or any(session_crashed(p.stem) and any((root()/p.stem).glob('*/*.kcut')) for p in (root()/'sessions').glob('*.json'))

def session_crashed(token):
    if not re.fullmatch('[a-f0-9]{32}',token):return False
    try:marker=json.loads((root()/'sessions'/(token+'.json')).read_text())
    except (OSError,ValueError):return False
    return not marker.get('reviewed',False) and not alive(token)

def acknowledge(path):
    body=json.loads(Path(path).read_text(encoding='utf-8'));token=body.get('_recovery',{}).get('session','')
    if session_crashed(token):
        marker=root()/'sessions'/(token+'.json');data=json.loads(marker.read_text());data['reviewed']=True;atomic(marker,data)

def finish_legacy():
    from .config import SESSION_LOCK_PATH
    import psutil
    try:
        match=re.search(r'pid=(\d+)',SESSION_LOCK_PATH.read_text())
        if not match or int(match[1])==os.getpid() or not psutil.pid_exists(int(match[1])):SESSION_LOCK_PATH.unlink(missing_ok=True)
    except OSError:pass

def remove(path):
    path=Path(path)
    if not managed_regular(path):raise ValueError('Unsafe recovery file')
    allowed={row['path'].resolve():row for row in entries()}
    row=allowed.get(path.resolve())
    if row is None or row['active']:raise ValueError('This recovery copy is in use or is not managed by Kinetic Cut')
    if not managed_regular(row['path']):raise ValueError('Unsafe recovery file')
    row['path'].unlink()

def clear_inactive():
    count=size=0
    for row in entries():
        if row['active']:continue
        remove(row['path']);count+=1;size+=row['size']
    return count,size
