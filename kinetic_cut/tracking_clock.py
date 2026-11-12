"""Bounded packet-timestamp metadata for frame-exact tracking seeks; no pixel decode."""
import bisect
import math


def read_clock(path,start,end):
    import av
    times=[]
    with av.open(path,timeout=(2.,2.)) as movie:
        stream=movie.streams.video[0]
        origin=(movie.start_time or 0)/1000000
        movie.seek(round(max(0.,start+origin-2)*1000000),backward=True)
        for n,packet in enumerate(movie.demux(stream)):
            if n>=10000:
                # Refuse an incomplete index rather than claim an older frame
                # covers a source range beyond this bounded metadata scan.
                times=[];break
            if packet.pts is not None:
                stamp=float(packet.pts*stream.time_base)-origin
                if math.isfinite(stamp):times.append(max(0.,stamp))
            # DTS is monotonic even with B frames; retain an extra GOP margin.
            if packet.dts is not None and float(packet.dts*stream.time_base)-origin>end+2:break
    return dict(start=start,end=end,times=sorted(set(times)))


def frame_time(clock,at):
    if not clock or not clock['start']-1e-7<=at<=clock['end']+1e-7:return at
    times=clock['times']
    if not times:return at
    # In VFR gaps the prior image remains on screen until the next PTS. Packet
    # duration alone may be only1/60s despite a50ms presentation interval.
    index=bisect.bisect_right(times,at+1e-7)-1
    return times[max(0,index)]
