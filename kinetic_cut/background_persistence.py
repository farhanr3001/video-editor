"""Coalesced editor persistence: one active write and one latest snapshot per lane.

Only immutable detached data crosses the worker boundary. Explicit project Save
remains synchronous; periodic recovery and registered editor preferences do not
perform filesystem I/O on the GUI thread. Existing worker ownership drains both
lanes on close, including a latest snapshot queued during shutdown.
"""
import copy
import threading
import weakref
from pathlib import Path
from PySide6.QtCore import QObject,Slot,QThreadPool,QThread
from PySide6.QtWidgets import QApplication

_owners=weakref.WeakValueDictionary()
_lock=threading.Lock()
_generation=0
_latest={}
_pending={}


def register(window):
    from . import config
    _owners[id(window.settings)]=window
    config._settings_dispatcher=request_settings
    config._settings_reader=pending_settings


def pending_settings(path):
    with _lock:value=_pending.get(str(Path(path)))
    return copy.deepcopy(value[1]) if value else None


def _write_settings(value):
    from . import config
    path,ticket,snapshot=value
    try:
        with _lock:current=_latest.get(str(path))
        if current==ticket:config._write_settings(snapshot,path)
    finally:
        with _lock:
            if _pending.get(str(path),(None,))[0]==ticket:_pending.pop(str(path),None)


def request_settings(settings):
    app=QApplication.instance();owner=_owners.get(id(settings))
    if owner is None or app is None or QThread.currentThread()!=app.thread():return False
    from shiboken6 import isValid
    if not isValid(owner):return False
    from . import config
    global _generation
    snapshot=copy.deepcopy(settings);path=Path(config.SETTINGS_PATH)
    with _lock:
        _generation+=1;ticket=_generation
        _latest[str(path)]=ticket;_pending[str(path)]=(ticket,snapshot)
    lane=getattr(owner,'_settings_save_lane',None)
    if lane is None:lane=owner._settings_save_lane=WriteLane(owner,_write_settings,'Save editor preferences')
    lane.submit((path,ticket,snapshot));return True


def _save_recovery(value):
    document,path=value
    document.save(path)


def recovery(window,path):
    document=window.compounds.root()
    if not (document.media or document.timeline):return
    snapshot=copy.deepcopy(document)
    lane=getattr(window,'_recovery_save_lane',None)
    if lane is None:lane=window._recovery_save_lane=WriteLane(window,_save_recovery,'Save recovery snapshot')
    lane.submit((snapshot,Path(path)))


class WriteLane(QObject):
    def __init__(self,owner,write,label):
        super().__init__(owner);self.owner=owner;self.write=write;self.label=label;self.active=False;self.pending=None
        app=QApplication.instance()
        pool=getattr(app,'_kinetic_persistence_pool',None)
        if pool is None:
            pool=app._kinetic_persistence_pool=QThreadPool(app);pool.setMaxThreadCount(1)
        self.pool=pool

    def submit(self,snapshot):
        if self.active:self.pending=snapshot;return
        from .ui import Worker
        self.active=True
        worker=Worker(self.write,snapshot);worker.pool=self.pool;worker.maintenance=True;worker.task_label=self.label
        # Connect before the generic finished owner so a pending write remains
        # owned throughout shutdown; there is never a gap with zero workers.
        worker.signals.finished.connect(self.finished)
        self.owner.start_worker(worker,shutdown=True)

    @Slot()
    def finished(self):
        self.active=False
        pending=self.pending;self.pending=None
        if pending is not None:self.submit(pending)
