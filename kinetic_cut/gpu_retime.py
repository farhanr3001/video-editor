"""Presentation-only retime scheduling; pixels stay in the native decoder.

Matches FFmpeg trim / setpts / primary-clock overlay quantization. Equal
output ticks select their first source picture at that tick, then consume
remaining pictures before the next tick. Never infer cadence from average FPS.
"""
from bisect import bisect_left
from fractions import Fraction
from functools import lru_cache
import math
import os

@lru_cache(maxsize=32)
def _clock(path, size, mtime):
    import av
    with av.open(path) as movie:
        stream=movie.streams.video[0]
        tb=Fraction(stream.time_base)
        # These codecs carry one display picture per timestamped packet.
        if stream.codec_context.name not in ('h264','hevc','ffv1','vp9','av1'):
            raise ValueError('Unverified retime packet cadence')
        pts=sorted(packet.pts for packet in movie.demux(stream) if packet.size and packet.pts is not None)
        if not pts or any(a>=b for a,b in zip(pts,pts[1:])):
            raise ValueError('Ambiguous retime source timestamps')
        return tb,tuple(pts),stream.start_time if stream.start_time is not None else pts[0]

def source_clock(path):
    info=os.stat(path)
    return _clock(os.fspath(path),info.st_size,info.st_mtime_ns)

def retime_schedule(clock,in_point,duration,speed,fps,start=0.):
    tb,pts,origin=clock
    speed=Fraction(f'{speed:.8f}');rate=Fraction(str(fps)).limit_denominator(1001000)
    if speed<=0 or duration<=0:raise ValueError('Invalid retime interval')
    # The accepted graph serializes input seeking and timeline placement to 6 decimals.
    trim=Fraction(f'{in_point:.6f}')/tb+origin
    first=bisect_left(pts,trim)
    if first==len(pts):raise ValueError('Retime starts beyond source')
    base=pts[first];offset=0
    begin=math.ceil(start*float(rate)-1e-7);end=math.ceil((start+duration)*float(rate)-1e-7)
    mapped=[]
    for point in pts[first:]:
        tick=Fraction(int(Fraction(point-base)/speed)+offset)*tb*rate
        mapped.append(math.floor(tick+Fraction(1,2)))
        if mapped[-1]>end-begin:break
    times=[]
    for n in range(end-begin):
        index=bisect_left(mapped,n)
        if index==len(mapped) or mapped[index]!=n:index=max(0,index-1)
        times.append(float((pts[first+index]-origin)*tb))
    return dict(frame_start=begin,source_times=times)
