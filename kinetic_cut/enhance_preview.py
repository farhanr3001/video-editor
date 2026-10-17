"""Bounded, display-resolution reads of prepared enhancement frames.

Export and preparation continue using original full-resolution cache pixels.
Workers own only immutable paths/parameters and QImages, never widgets/decoders.
"""
import threading
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,ThreadPoolExecutor
from PySide6.QtCore import QSize,QCoreApplication
from PySide6.QtGui import QImage
from .image_cache import ImageCache

def _reader_init():
    from .process import install_desktop_process_policy
    install_desktop_process_policy()
    import multiprocessing,os
    parent=multiprocessing.parent_process()
    if parent:
        def watch():
            while parent.is_alive():threading.Event().wait(.2)
            os._exit(0)
        threading.Thread(target=watch,name='enhance-reader-parent',daemon=True).start()

def _read_preview(record,number,p,dimensions):
    from .enhance import read_frame
    size=QSize(*dimensions);identity=PreviewFrames().identity(record,number,p,size)
    if identity is None:return None
    image=read_frame(record,number,p,size)
    if image.isNull():return None
    return identity,(image.width(),image.height(),image.bytesPerLine(),image.format().value,bytes(image.constBits()))


class PreviewFrames:
    def __init__(self):
        self.images=ImageCache(64*1024**2,48);self.lock=threading.RLock()
        self.executor=None;self.pending={};self.generation=0;self.closed=False;self.hooked=False;self.prepared={};self.last_warm={}
    def clear(self):
        with self.lock:
            self.generation+=1;self.images.clear();self.prepared.clear();self.last_warm={}
            for future in self.pending.values():future.cancel()
            self.pending.clear()
    def close(self):
        with self.lock:
            self.closed=True;self.clear()
            if self.executor:self.executor.shutdown(wait=False,cancel_futures=True)
            self.executor=None
    def identity(self,record,number,p,size):
        root=Path(record['root']);paths=[root/'info.json',root/'frames'/f'{number:08d}.png']
        if record.get('original_frames'):paths.append(root/'original'/f'{number:08d}.png')
        alpha=root/'alpha'/f'{number:08d}.png'
        try:
            stamps=[]
            for path in paths:
                stat=path.stat();stamps.append((str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns))
            stamps=tuple(stamps)
            if alpha.exists():
                stat=alpha.stat();stamps+=((str(alpha),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns),)
        except OSError:return None
        return (stamps,p['mix'],p['enhancement_strength'],size.width(),size.height())
    def get(self,record,number,p,size,prefetch=True):
        size=QSize(max(1,size.width()),max(1,size.height()));key=self.identity(record,number,p,size)
        if key is None:return QImage()
        image=self.images.get(key)
        if image is None:
            # Cold/random seeks remain exact rather than flashing an unrelated
            # or unenhanced frame. Sequential reads are warmed on three isolated CPU readers.
            from .enhance import read_frame
            image=read_frame(record,number,p,size)
            if not image.isNull():self.images.put(key,image)
        if prefetch:self.warm(record,number,p,size)
        return image
    def warm(self,record,number,p,size):
        with self.lock:
            if self.closed:return
            app=QCoreApplication.instance()
            if app and not self.hooked:app.aboutToQuit.connect(self.close);self.hooked=True
            if self.executor is None:
                import multiprocessing
                if multiprocessing.current_process().daemon:
                    # The composition helper already isolates the UI's GIL.
                    self.executor=ThreadPoolExecutor(max_workers=3,thread_name_prefix='enhance-composition-read')
                else:
                    from .process import install_desktop_process_policy
                    install_desktop_process_policy()
                    self.executor=ProcessPoolExecutor(max_workers=3,mp_context=multiprocessing.get_context('spawn'),initializer=_reader_init)
            request=(record['root'],number,p['mix'],p['enhancement_strength'],size.width(),size.height())
            family=(request[0],*request[2:]);previous=self.last_warm.get(family)
            if previous==number:return
            self.last_warm[family]=number
            while len(self.last_warm)>32:self.last_warm.pop(next(iter(self.last_warm)))
            if previous is not None and abs(previous-number)>16:
                for work,future in list(self.pending.items()):
                    if work[0]==request[0] and future.cancel():self.pending.pop(work,None)
            direction=-1 if previous is not None and 0<previous-number<=16 else 1
            generation=self.generation
            for key,future in list(self.pending.items()):
                obsolete=(key[0]==record['root'] and (key[1]-number)*direction<0)
                if future.done() or obsolete and future.cancel():self.pending.pop(key,None)
            while len(self.prepared)>96:self.prepared.pop(next(iter(self.prepared)))
            for distance in range(1,13):
                n=number+direction*distance
                if not 0<=n<record['frames']:break
                if len(self.pending)>=12:break
                work=(record['root'],n,p['mix'],p['enhancement_strength'],size.width(),size.height())
                cached=self.prepared.get(work)
                if work in self.pending or (cached is not None and self.images.get(cached) is not None):continue
                future=self.executor.submit(_read_preview,record,n,p,(size.width(),size.height()))
                def publish(future,work=work,generation=generation):
                    try:
                        result=future.result()
                        if result is None:return
                        key,data=result;width,height,stride,format,pixels=data
                        image=QImage(pixels,width,height,stride,QImage.Format(format)).copy()
                    except Exception:return
                    with self.lock:
                        if not self.closed and generation==self.generation:
                            self.images.put(key,image);self.prepared[work]=key
                self.pending[work]=future;future.add_done_callback(publish)


frames=PreviewFrames()

def frame(project,media,item,index,at,size):
    from .enhance import range_at,parameters
    record=range_at(project,media,item,index,at)
    if not record:return QImage()
    number=max(0,min(record['frames']-1,round((at-record['source_start'])*record['fps'])))
    return frames.get(record,number,parameters(item.effects[index]),size)
