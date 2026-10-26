"""Compatibility source decoding inside the private export process only.

Only codecs/alpha sources that cannot supply D3D11 textures use this adapter.
Pixels are uploaded once; scaling, effects and composition remain on the GPU.
"""
import ctypes
import logging
import math
import os
import subprocess


def _windows_pipe(capacity=1024*1024):
    """A bounded kernel pipe, rather than Popen's 4 KiB default.

    Python's BufferedReader size does not change the Windows pipe capacity.
    Transfer each handle to exactly one binary file; Popen duplicates only the
    write end for the child, and the caller closes its own write end after spawn.
    """
    import _winapi
    import msvcrt
    handles=list(_winapi.CreatePipe(None,capacity));files=[]
    try:
        for index,(flags,mode,buffering) in enumerate(((os.O_RDONLY,'rb',1024*1024),(os.O_WRONLY,'wb',0))):
            descriptor=msvcrt.open_osfhandle(handles[index],flags|os.O_BINARY)
            handles[index]=None
            try:
                os.set_inheritable(descriptor,False)
                stream=os.fdopen(descriptor,mode,buffering=buffering)
            except BaseException:
                os.close(descriptor)
                raise
            files.append(stream)
        return files
    except BaseException:
        for stream in files:stream.close()
        raise
    finally:
        for handle in handles:
            if handle is not None:_winapi.CloseHandle(handle)


class RawSource:
    """An exact overlay producer, streamed into the owned export process.

    The same FFmpeg ASS graph supplies lossless RGBA. Only one frame is retained;
    duplicate native requests (including initialisation) never advance the pipe.
    The controller's existing worker watchdog also covers a blocked producer.
    """
    def __init__(self,spec):
        import numpy as np
        from .process import popen
        from .export_process import ChildJob
        self.process=self.job=self.log=None
        self.index=-1;self.requested=-1;self.generation=0;self.failure=None
        self.width=int(spec['width']);self.height=int(spec['height'])
        self.fps=float(spec['fps']);self.frames=int(spec['frames'])
        if not (1<=self.width<=8192 and 1<=self.height<=8192 and 1<=self.fps<=240 and self.frames>0):
            raise ValueError('Invalid exact overlay dimensions or clock')
        self.samples=spec.get('sample_frames');self.cursor=0
        if self.samples is not None:
            if (not isinstance(self.samples,list) or not self.samples or len(self.samples)>min(self.frames,250000)
                or any(type(n) is not int for n in self.samples) or self.samples[0]!=0 or self.samples[-1]!=self.frames-1
                or any(a>=b for a,b in zip(self.samples,self.samples[1:]))):
                raise ValueError('Invalid exact overlay sample clock')
        command=spec['command']
        if not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command):
            raise ValueError('Invalid exact overlay command')
        self.buffer=np.empty((self.height,self.width,4),dtype=np.uint8)
        reader=writer=None
        try:
            self.log=open(spec['log'],'wb')
            if os.name=='nt':reader,writer=_windows_pipe(max(1024*1024,min(16*1024*1024,self.buffer.nbytes*2)))
            self.process=popen(command,stdout=writer if writer is not None else subprocess.PIPE,stderr=self.log,bufsize=1024*1024)
            if reader is not None:self.process.stdout=reader;reader=None
            self.job=ChildJob(self.process)
            if os.name=='nt' and self.job.handle is None:
                raise RuntimeError('Could not own the exact overlay producer safely')
        except BaseException:
            self.close()
            raise
        finally:
            if writer is not None:writer.close()
            if reader is not None:reader.close()

    def frame(self,seconds):
        if self.failure is not None:raise RuntimeError('Exact overlay producer has failed') from self.failure
        if not math.isfinite(seconds):raise ValueError('Invalid exact overlay timestamp')
        index=math.floor(seconds*self.fps+1e-7)
        if index<self.requested or not 0<=index<self.frames:raise ValueError('Exact overlay timestamp is outside its forward clock')
        try:
            while self.index<index:
                next_frame=self.index+1 if self.samples is None else self.samples[self.cursor] if self.cursor<len(self.samples) else self.frames
                if next_frame>index:break
                view=memoryview(self.buffer).cast('B');offset=0
                while offset<len(view):
                    size=self.process.stdout.readinto(view[offset:])
                    if not size:raise RuntimeError('Exact overlay producer returned an incomplete frame; see its render log')
                    offset+=size
                self.index=next_frame;self.cursor+=1;self.generation+=1
                if self.index==self.frames-1:
                    # A destructor callback cannot report failure to native code.
                    # Validate producer success before publishing its final pixels.
                    if self.process.wait(timeout=15):raise RuntimeError('Exact overlay producer failed; see its render log')
        except BaseException as error:
            self.failure=error
            raise
        self.requested=index
        return self.buffer

    def close(self):
        from .export_process import stop
        try:
            if self.process is not None:
                if self.process.poll() is None:
                    if self.job is not None and (os.name!='nt' or self.job.handle is not None):
                        stop(self.process,self.job);self.process.wait(timeout=15)
                    else:self.process.kill();self.process.wait(timeout=15)
                else:self.process.wait()
        finally:
            if self.job is not None:self.job.close();self.job=None
            if self.process is not None and self.process.stdout is not None:self.process.stdout.close()
            if self.log is not None:self.log.close();self.log=None


CALLBACK=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_double,
    ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_void_p))


class Source:
    def __init__(self,path,seconds):
        import av
        self.movie=av.open(path)
        try:
            self.stream=self.movie.streams.video[0];self.stream.thread_type='SLICE';self.stream.thread_count=2
            self.origin=float((self.stream.start_time or 0)*self.stream.time_base)
            self.epsilon=max(1e-7,float(self.stream.time_base)/2)
            self.movie.seek(round((seconds+self.origin)/float(self.stream.time_base)),stream=self.stream,backward=True)
            self.frames=iter(self.movie.decode(self.stream));self.current=self.next=None;self.phase=0.;self.buffer=None
            self.advance()
            while self.next and self.at(self.next)<seconds-1e-7:self.current=self.next;self.advance()
            if self.next:self.current=self.next;self.phase=self.at(self.current)-seconds;self.advance()
            if self.current is None:raise RuntimeError('No decoded frame at source in-point')
        except BaseException:self.movie.close();raise
    def at(self,frame):
        if frame.pts is None:raise ValueError('Source has no presentation timestamps')
        return float(frame.pts*frame.time_base)-self.origin
    def advance(self):self.next=next(self.frames,None)
    def frame(self,seconds):
        wanted=seconds+self.phase
        while self.next and self.at(self.next)<=wanted+self.epsilon:self.current=self.next;self.advance()
        self.buffer=self.current.to_ndarray(format='rgba')
        return self.buffer
    def close(self):self.movie.close()


class Decoder:
    def __init__(self,raw_sources=None,reuse_frames=False):
        self.sources={};self.raw_sources=raw_sources or {};self.reuse_frames=reuse_frames
        self.generations={};self.callback=CALLBACK(self.read)
    def read(self,path,key,seconds,width,height,pointer):
        try:
            if seconds<0:
                source=self.sources.pop(key,None)
                self.generations.pop(key,None)
                if source:source.close()
                return 0
            if key not in self.sources:
                if len(self.sources)>=16:raise RuntimeError('Compatibility decoder limit exceeded')
                self.sources[key]=RawSource(self.raw_sources[path]) if path in self.raw_sources else Source(path,seconds)
            pixels=self.sources[key].frame(seconds)
            height[0],width[0]=pixels.shape[:2];pointer[0]=pixels.ctypes.data
            if self.reuse_frames and isinstance(self.sources[key],RawSource):
                version=self.sources[key].generation
                if self.generations.get(key)==version:return 2
                self.generations[key]=version
            return 0
        except Exception:
            logging.exception('Compatibility export source failed: %s',path)
            return 1
    def close(self):
        for source in self.sources.values():source.close()
        self.sources.clear();self.generations.clear()
