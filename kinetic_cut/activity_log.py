"""Fixed-size action history that survives abrupt process termination.

Pointer/transport callbacks only copy a small JSON record into a preallocated
local file mapping: no disk flush, file open, background queue wait or Qt call.
Each line has a sequence number; sort by it after the ring wraps.
"""
import atexit
import json
import math
import mmap
import os
import threading
import time
from datetime import datetime,timezone
from pathlib import Path

_active=None
SLOT_BYTES=1024
CAPACITY=512


class ActivityLog:
    def __init__(self,path,*,capacity=CAPACITY):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():self.path.replace(self.path.with_suffix(self.path.suffix+'.1'))
        self.file=self.path.open('w+b');self.capacity=capacity
        self.file.truncate(capacity*SLOT_BYTES)
        self.mapping=mmap.mmap(self.file.fileno(),capacity*SLOT_BYTES,access=mmap.ACCESS_WRITE)
        self.mapping[:]=(b' '*(SLOT_BYTES-1)+b'\n')*capacity
        self.sequence=0;self.closed=False;self.lock=threading.Lock();self.last={}
        from .version import VERSION
        self.record('session.start',pid=os.getpid(),version=VERSION)
        atexit.register(self.close)

    def record(self,action,*,throttle=0.,**details):
        if self.closed:return
        now=time.monotonic();action=str(action)[:80]
        if throttle and now-self.last.get(action,-math.inf)<throttle:return
        if not self.lock.acquire(blocking=False):return
        try:
            if self.closed:return
            self.last[action]=now
            if len(self.last)>64:self.last.pop(next(iter(self.last)))
            self.sequence+=1
            values={}
            for key,value in list(details.items())[:8]:
                if isinstance(value,str):value=value[:180]
                elif isinstance(value,float) and not math.isfinite(value):value=str(value)
                elif not isinstance(value,(int,float,bool,type(None))):value=type(value).__name__
                values[str(key)[:40]]=value
            row=dict(sequence=self.sequence,time_utc=datetime.now(timezone.utc).isoformat(),action=action,details=values)
            payload=json.dumps(row,ensure_ascii=True,separators=(',',':')).encode('utf-8')
            if len(payload)>=SLOT_BYTES:
                row['details']={'note':'Details exceeded record limit'}
                payload=json.dumps(row,separators=(',',':')).encode('utf-8')
            offset=((self.sequence-1)%self.capacity)*SLOT_BYTES
            self.mapping[offset:offset+SLOT_BYTES]=payload.ljust(SLOT_BYTES-1,b' ')+b'\n'
        finally:self.lock.release()

    def close(self):
        global _active
        if self.closed:return
        self.record('session.end',pid=os.getpid());self.closed=True
        if _active is self:_active=None
        # Only normal process exit/explicit diagnostic cleanup flushes the map.
        self.mapping.flush();self.mapping.close();self.file.close()
        atexit.unregister(self.close)


def install(directory):
    global _active
    if _active is None or _active.closed:_active=ActivityLog(Path(directory)/'user-actions.log')
    return _active


def record(action,*,throttle=0.,**details):
    recorder=_active
    if recorder is None:return
    try:recorder.record(action,throttle=throttle,**details)
    except Exception:
        # Diagnostics must never interrupt the operation being diagnosed.
        pass


def read(path):
    rows=[]
    for line in Path(path).read_text(encoding='utf-8',errors='replace').splitlines():
        try:
            row=json.loads(line)
            if isinstance(row,dict) and isinstance(row.get('sequence'),int):rows.append(row)
        except (ValueError,TypeError):pass
    return sorted(rows,key=lambda row:row.get('sequence',0))
