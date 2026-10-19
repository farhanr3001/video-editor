"""Reference-aware reclamation of regenerable AI frames, never models/media.

Undo snapshots and other saved/open projects retain their frames. Closing drops
session-only undo references and reclaims orphaned ranges on a retained worker.
"""
import copy,json,os,re,threading,time,uuid
from pathlib import Path
from PySide6.QtCore import QObject,QTimer,Qt

HEX=re.compile(r'^[0-9a-f]{64}$')
TRASH=re.compile(r'^_gc-[0-9a-f]{32}-[0-9a-f]{64}(?:\.mkv)?$')

def reparse(path):
    try:return bool(getattr(path.lstat(),'st_file_attributes',0)&0x400) or path.is_symlink()
    except OSError:return False

def families(projects):
    from . import enhance
    from .model import Project
    result=set();movies={};visited=set()
    def visit(project,depth=0):
        if depth>8:raise ValueError('Unsafe nested cache references')
        used={i.media_id for i in project.timeline};media={m.id:m for m in project.media}
        for item in project.timeline:
            source=media.get(item.media_id)
            stages=[n for n,e in enumerate(item.effects) if e.get('name')==enhance.NAME]
            if not stages:continue
            if source is None or str(source.path).startswith(('\\\\','//')):raise ValueError('Unresolved enhancement source')
            token=(id(item),id(source),project.settings.fps)
            if token in visited:continue
            visited.add(token)
            item_families=set()
            for n in stages:
                restored=copy.copy(item);restored.effects=[dict(e) for e in item.effects];restored.effects[n]['enabled']=True
                for schema in (4,5):item_families.add(enhance.signature(source,restored,n,enhance.sample_fps(project,source,item),False,schema=schema))
            result.update(item_families)
            if enhance.active(item):
                key=enhance.export_key(project,item);movies[key+'.mkv']=item_families
        for m in project.media:
            if m.id not in used:continue
            for data in (m.compound,m.timeline_preset):
                if data:visit(Project.from_dict(data),depth+1)
    for project in projects:visit(project)
    return result,movies

def alive(record):
    import psutil
    if not isinstance(record.get('pid'),int) or record['pid']<=0:return False
    try:return abs(psutil.Process(record['pid']).create_time()-record['started'])<.01
    except psutil.AccessDenied:return True
    except (psutil.Error,KeyError,TypeError,ValueError):return False

class State:
    def __init__(self,parent):
        import psutil
        self.raw_parent=Path(parent).absolute();self.parent=self.raw_parent.resolve();self.identity=uuid.uuid4().hex;self.started=psutil.Process().create_time()
        self.lock=threading.RLock();self.io=threading.Lock();self.revision=0;self.projects=[];self.paths=[];self.identify=[];self.known=set();self.seen={};self.trash={};self.loaded=False
    def update(self,projects,paths,identify=None):
        with self.lock:self.projects=list(projects);self.paths=paths if callable(paths) else list(paths);self.identify=list({id(p):p for p in [*self.identify,*(identify or projects)]}.values());self.revision+=1
    def write(self,path,data):
        if reparse(path):raise ValueError('Unsafe cleanup metadata')
        pending=path.with_suffix('.tmp')
        if reparse(pending):raise ValueError('Unsafe cleanup metadata')
        pending.write_text(json.dumps(data),encoding='utf-8');pending.replace(path)
    def sweep(self,final=False):
        from .model import Project
        with self.io:
            with self.lock:revision=self.revision;projects=list(self.projects);paths=self.paths;identify=list(self.identify)
            if callable(paths):paths=paths()
            if reparse(self.raw_parent) or reparse(self.parent) or self.parent.name!='ai-enhance':return dict(deleted=0,unsafe=True)
            self.parent.mkdir(parents=True,exist_ok=True);leases=self.parent/'.sessions'
            if reparse(leases):return dict(deleted=0,unsafe=True)
            leases.mkdir(exist_ok=True);lease=leases/(self.identity+'.json');others=set()
            for path in leases.glob('*.json'):
                if path==lease or reparse(path):continue
                try:record=json.loads(path.read_text());valid=alive(record)
                except (OSError,ValueError,TypeError):continue
                if valid:others.update(record.get('families',[]))
                elif not self.loaded:
                    for name,values in record.get('seen',{}).items():
                        if HEX.fullmatch(name) or name.endswith('.mkv') and HEX.fullmatch(name[:-4]):self.seen[name]=set(values)
                    for name,values in record.get('trash',{}).items():
                        if TRASH.fullmatch(name):self.trash[name]=set(values)
            self.loaded=True
            try:
                current,movies=families(projects)
                observed,oldmovies=families(identify);self.known.update(observed);movies.update(oldmovies)
                with self.lock:
                    processed={id(p) for p in identify};self.identify=[p for p in self.identify if id(p) not in processed]
            except (OSError,ValueError,AttributeError,TypeError):return dict(deleted=0,unsafe=True)
            protected=current|others;unsafe=False
            for path in paths:
                if str(path).startswith(('\\\\','//')):unsafe=True;break
                try:
                    if Path(path).is_file():protected.update(families([Project.load(path)])[0])
                except (OSError,ValueError,TypeError,AttributeError):unsafe=True;break
            for root in self.parent.iterdir():
                if not root.is_dir() or not HEX.fullmatch(root.name) or reparse(root):continue
                try:
                    record=json.loads((root/'info.json').read_text())
                    if record.get('key')==root.name and record.get('family') in self.known:self.seen[root.name]={record['family']}
                except (OSError,ValueError,TypeError):continue
            for name,values in movies.items():
                if (self.parent/name).is_file():self.seen[name]=values
            record=dict(pid=os.getpid(),started=self.started,families=sorted(current),seen={k:sorted(v) for k,v in self.seen.items()},trash={k:sorted(v) for k,v in self.trash.items()})
            self.write(lease,record);deleted=0
            import shutil
            for name in list(self.trash):
                target=self.parent/name
                if not target.exists():self.trash.pop(name,None);continue
                if reparse(target) or target.resolve().parent!=self.parent:continue
                try:
                    if target.is_dir():
                        if any(reparse(p) for p in target.rglob('*')):continue
                        shutil.rmtree(target)
                    else:target.unlink()
                    self.trash.pop(name,None)
                except OSError:pass
            if not unsafe:
                for name,refs in list(self.seen.items()):
                    if refs&protected:continue
                    target=self.parent/name
                    if not target.exists():self.seen.pop(name,None);continue
                    if reparse(target) or target.resolve().parent!=self.parent:continue
                    with self.lock:
                        if revision!=self.revision:break
                        try:
                            if target.is_dir():
                                meta=json.loads((target/'info.json').read_text())
                                if meta.get('key')!=name or meta.get('family') not in refs:continue
                                if any(reparse(p) for p in target.rglob('*')):continue
                            retired=self.parent/('_gc-'+uuid.uuid4().hex+'-'+name)
                            self.trash[retired.name]=refs;record['trash']={k:sorted(v) for k,v in self.trash.items()};self.write(lease,record)
                            target.rename(retired)
                        except (OSError,ValueError):continue
                    try:
                        import shutil
                        if retired.is_dir():shutil.rmtree(retired)
                        else:retired.unlink()
                        self.seen.pop(name,None);self.trash.pop(retired.name,None);deleted+=1
                    except OSError:pass
            record['seen']={k:sorted(v) for k,v in self.seen.items()};record['trash']={k:sorted(v) for k,v in self.trash.items()};self.write(lease,record)
            if final:
                if self.seen or self.trash:
                    record['pid']=0;record['started']=0;record['families']=[];self.write(lease,record)
                else:lease.unlink(missing_ok=True)
            if deleted:
                from . import enhance
                # Referenced pixel buffers remain warm. Removed paths cannot
                # match file identities, and the bounded LRU expires old RAM.
                enhance._range_indexes.clear()
            return dict(deleted=deleted,unsafe=unsafe)

class Storage(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.job=None;self.finishing=False;self.final_started=False
        from .config import CACHE_DIR
        self.state=State(CACHE_DIR/'ai-enhance');self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.start)
    def capture(self,final=False):
        w=self.window
        history=list(w._history)
        for _,_,snapshots,_ in w.compounds.stack:history.extend(snapshots)
        projects=[copy.deepcopy(w.compounds.root())] if final else history
        from .project_manager import project_paths
        # Discovery is performed on the worker as well; capture only settings.
        settings=copy.deepcopy(w.settings);current=(w.compounds.stack[0][0] if w.compounds.stack else w.project).path
        self.state.update(projects,lambda:project_paths(settings,current),identify=history)
    def start(self,final=False):
        if self.finishing and not final or self.job is not None and not final:return
        if not final and (self.window.transport.playing or self.window.transport.scrubbing or self.window.preview.pan_origin is not None or getattr(self.window,"_property_scrubbing",False)):
            self.timer.start(1000);return
        from .ui import Worker
        def work():return self.state.sweep(final)
        worker=Worker(work);worker.maintenance=True
        if not final:self.job=worker;worker.signals.finished.connect(self.retire,Qt.QueuedConnection)
        self.window.start_worker(worker,shutdown=final)
    def retire(self):
        self.job=None
        if not self.finishing and not getattr(self.window,'_closing',False):self.timer.start(30000)
    def observe(self):
        self.capture();self.timer.start(300)
    def finish(self):
        self.finishing=True;self.timer.stop();self.capture(True)
    def finish_work(self):
        if self.final_started:return False
        self.final_started=True;self.start(True);return True

def history_has_enhancement(history):
    # Only immutable Undo snapshots may cache this answer. Live projects can
    # receive nested effect edits without replacing their timeline records.
    for project in history:
        immutable=project.__dict__.get('_history_snapshot',False)
        known=project.__dict__.get('_enhance_present') if immutable else None
        if known is None:
            known=any(e.get('name')=='AI Enhance' for item in project.timeline for e in item.effects)
            if immutable:object.__setattr__(project,'_enhance_present',known)
        if known:return True
    return False


def observe(window):
    if not hasattr(window,"_history") or not hasattr(window,"compounds"):return
    manager=getattr(window,'_enhance_storage',None)
    if manager is None:
        from .config import CACHE_DIR
        if not (CACHE_DIR/'ai-enhance/.sessions').exists() and not history_has_enhancement(window._history):return
        manager=Storage(window);window._enhance_storage=manager
    manager.observe()

def finish(window):
    manager=getattr(window,'_enhance_storage',None)
    if manager:manager.finish()

def finish_work(window):
    manager=getattr(window,"_enhance_storage",None)
    return bool(manager and manager.finish_work())
