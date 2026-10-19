"""Compatibility source decoding inside the private export process only.

Only codecs/alpha sources that cannot supply D3D11 textures use this adapter.
Pixels are uploaded once; scaling, effects and composition remain on the GPU.
"""
import ctypes
import logging


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
    def __init__(self):
        self.sources={};self.callback=CALLBACK(self.read)
    def read(self,path,key,seconds,width,height,pointer):
        try:
            if seconds<0:
                source=self.sources.pop(key,None)
                if source:source.close()
                return 0
            if key not in self.sources:
                if len(self.sources)>=16:raise RuntimeError('Compatibility decoder limit exceeded')
                self.sources[key]=Source(path,seconds)
            pixels=self.sources[key].frame(seconds)
            height[0],width[0]=pixels.shape[:2];pointer[0]=pixels.ctypes.data
            return 0
        except Exception:
            logging.exception('Compatibility export source failed: %s',path)
            return 1
    def close(self):
        for source in self.sources.values():source.close()
        self.sources.clear()
