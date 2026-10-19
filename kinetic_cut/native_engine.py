"""Small C ABI bridge; native queries release the GIL and never call Python."""
import ctypes as C
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import weakref


def load():
    if os.name!='nt' or os.environ.get('KINETIC_NATIVE_ENGINE','1')!='1':return None
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
    path=root/'assets/native/kinetic_engine.dll'
    if not path.is_file():return None
    lib=C.CDLL(str(path));lib.kc_abi.restype=C.c_uint32
    if lib.kc_abi()!=2:raise RuntimeError('Unsupported native timeline engine ABI')
    signatures={
        'kc_create':(C.c_void_p,[]),'kc_destroy':(None,[C.c_void_p]),
        'kc_put':(C.c_int,[C.c_void_p,C.c_uint64,C.c_double,C.c_double]),
        'kc_remove':(None,[C.c_void_p,C.c_uint64]),
        'kc_query':(C.c_int64,[C.c_void_p,C.c_double,C.c_double,C.POINTER(C.c_uint64),C.c_uint64]),
        'kc_neighbors':(C.c_int,[C.c_void_p,C.c_double,C.POINTER(C.c_double),C.POINTER(C.c_double)]),
        'kc_duration':(C.c_double,[C.c_void_p]),'kc_visited':(C.c_uint64,[C.c_void_p]),
        'kc_submit':(C.c_uint64,[C.c_void_p,C.c_uint64,C.c_double]),
        'kc_take':(C.c_int,[C.c_void_p,C.POINTER(C.c_uint64),C.POINTER(C.c_uint64),C.POINTER(C.c_double)]),
        'kc_dropped':(C.c_uint64,[C.c_void_p])}
    for name,(result,args) in signatures.items():
        fn=getattr(lib,name);fn.restype=result;fn.argtypes=args
    return lib


try:LIB=load()
except (OSError,RuntimeError,AttributeError):
    import logging
    logging.exception('Native timeline engine unavailable; using indexed Python compatibility path')
    LIB=None


class NativeIntervalTree:
    def __init__(self):
        self.handle=LIB.kc_create()
        if not self.handle:raise MemoryError('Could not allocate native timeline index')
        self._finalizer=weakref.finalize(self,LIB.kc_destroy,self.handle)
        self.records={};self.buffer=(C.c_uint64*256)();self._fallback=None
    def put(self,ordinal,start,end,value):
        if self._fallback is not None:return self._fallback.put(ordinal,start,end,value)
        valid=math.isfinite(start) and math.isfinite(end) and end>=start
        if valid:self.records[ordinal]=SimpleNamespace(start=start,end=end,value=value)
        else:self.records.pop(ordinal,None)
        if not valid or LIB.kc_put(self.handle,ordinal,start,end)!=1:
            from .runtime_index import PythonIntervalTree
            self._fallback=PythonIntervalTree()
            for n,r in self.records.items():self._fallback.put(n,r.start,r.end,r.value)
    def query(self,left,right):
        if self._fallback is not None:return self._fallback.query(left,right)
        count=LIB.kc_query(self.handle,left,right,self.buffer,len(self.buffer))
        if count<0:return []
        if count>len(self.buffer):
            self.buffer=(C.c_uint64*count)();count=LIB.kc_query(self.handle,left,right,self.buffer,len(self.buffer))
        return [self.records[self.buffer[n]].value for n in range(count)]
    def remove(self,ordinal):
        self.records.pop(ordinal,None)
        if self._fallback is not None:self._fallback.remove(ordinal)
        else:LIB.kc_remove(self.handle,ordinal)
    @property
    def duration(self):return self._fallback.duration if self._fallback is not None else LIB.kc_duration(self.handle)
    @property
    def visited(self):return self._fallback.visited if self._fallback is not None else LIB.kc_visited(self.handle)
    def neighbors(self,at):
        if self._fallback is not None:return self._fallback.neighbors(at)
        left=C.c_double();right=C.c_double()
        if not LIB.kc_neighbors(self.handle,at,C.byref(left),C.byref(right)):return -math.inf,math.inf
        return left.value,right.value


class LatestRequest:
    """One native pending slot; superseded requests are discarded, never queued."""
    def __init__(self):
        if LIB is None:raise RuntimeError('Native engine unavailable')
        self.handle=LIB.kc_create()
        if not self.handle:raise MemoryError('Could not allocate preview mailbox')
        self._finalizer=weakref.finalize(self,LIB.kc_destroy,self.handle)
    def submit(self,epoch,at):return LIB.kc_submit(self.handle,epoch,at)
    def take(self):
        epoch=C.c_uint64();serial=C.c_uint64();at=C.c_double()
        return ((epoch.value,serial.value,at.value) if LIB.kc_take(self.handle,C.byref(epoch),C.byref(serial),C.byref(at)) else None)
    @property
    def dropped(self):return LIB.kc_dropped(self.handle)
