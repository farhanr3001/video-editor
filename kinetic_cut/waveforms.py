"""Time-based signed audio peaks, streamed to a compact multiresolution cache."""
import hashlib
import math
import os
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from .process import popen

RATE=24000
BIN_SAMPLES=24  # One millisecond, independent of recording length.
BIN_SECONDS=BIN_SAMPLES/RATE
BIN_BYTES=BIN_SAMPLES*2*2  # Two channels, signed 16-bit samples.

def source_key(path):
    source=Path(path).resolve()
    try:
        stat=source.stat(); return (str(source),stat.st_size,stat.st_mtime_ns)
    except OSError:return (str(source),None,None)


class Waveform:
    def __init__(self,peaks):
        self.peaks=np.asarray(peaks,dtype=np.int16).reshape(-1,2)
        self.levels=[self.peaks]
        while len(self.levels[-1])>256:
            previous=self.levels[-1]; count=math.ceil(len(previous)/4)
            padded=np.zeros((count*4,2),dtype=np.int16); padded[:len(previous)]=previous
            blocks=padded.reshape(count,4,2)
            self.levels.append(np.column_stack((blocks[:,:,0].min(axis=1),blocks[:,:,1].max(axis=1))))
    def __len__(self):return len(self.peaks)
    def columns(self,times,width):
        """Aggregate every overlapping peak; never skip short transients."""
        times=np.asarray(times,dtype=float); width=max(0.,float(width)); level=0
        while level+1<len(self.levels) and BIN_SECONDS*4**(level+1)<=width/4:level+=1
        resolution=BIN_SECONDS*4**level; data=self.levels[level]
        first=np.floor(times/resolution).astype(np.int64)
        end=np.maximum(first+1,np.ceil((times+width)/resolution).astype(np.int64))
        low=np.zeros(len(times),dtype=np.int16); high=low.copy()
        if not len(data):return np.column_stack((low,high)).astype(float)
        first=np.clip(first,0,len(data)); end=np.clip(end,0,len(data))
        for offset in range(int(np.max(end-first,initial=0))):
            index=first+offset; valid=(index>=0)&(index<len(data))&(index<end)
            values=data[np.clip(index,0,len(data)-1)]
            low=np.minimum(low,np.where(valid,values[:,0],0)); high=np.maximum(high,np.where(valid,values[:,1],0))
        return np.column_stack((low,high)).astype(float)/32768.


def waveform(path,ffmpeg='ffmpeg',points=None):
    # points is accepted for old callers, but never caps detail by file length.
    from .config import CACHE_DIR
    source=Path(path).resolve(); stat=source.stat()
    key=hashlib.sha256(f'{source}:{stat.st_size}:{stat.st_mtime_ns}:signed-stereo-ms-v1'.encode()).hexdigest()[:24]
    folder=CACHE_DIR/'waveforms'; folder.mkdir(parents=True,exist_ok=True); target=folder/(key+'.npz')
    try:
        with np.load(target,allow_pickle=False) as cached:
            peaks=cached['peaks']
            if peaks.dtype==np.int16 and peaks.ndim==2 and peaks.shape[1]==2:return Waveform(peaks)
    except (OSError,ValueError,KeyError,EOFError):pass
    chunks=[]; pending=b''
    # Bound raw PCM memory regardless of source duration. stderr cannot fill a
    # pipe and deadlock decoding; the process follows our hidden-window policy.
    with tempfile.TemporaryFile() as errors:
        with popen([ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-i',str(source),
                    '-map','0:a:0','-vn','-ac','2','-ar',str(RATE),'-f','s16le','-'],
                   stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=errors) as process:
            try:
                while True:
                    raw=process.stdout.read(RATE*4)
                    if not raw:break
                    pending+=raw; usable=len(pending)//BIN_BYTES*BIN_BYTES
                    if usable:
                        blocks=np.frombuffer(pending[:usable],dtype='<i2').reshape(-1,BIN_SAMPLES*2)
                        chunks.append(np.column_stack((blocks.min(axis=1),blocks.max(axis=1)))); pending=pending[usable:]
                if process.wait()!=0:
                    errors.seek(0); raise RuntimeError('Waveform decoding failed: '+errors.read(2000).decode(errors='replace'))
            except BaseException:
                if process.poll() is None:process.kill(); process.wait()
                raise
    if pending:
        tail=np.frombuffer(pending[:len(pending)//2*2],dtype='<i2')
        if len(tail):chunks.append(np.array([[tail.min(),tail.max()]],dtype=np.int16))
    peaks=np.concatenate(chunks) if chunks else np.empty((0,2),dtype=np.int16)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=folder,suffix='.tmp',delete=False) as cache:
            temporary=Path(cache.name); np.savez_compressed(cache,peaks=peaks)
        os.replace(temporary,target)
    except OSError:pass  # Display still works when cache storage is unavailable.
    finally:
        if temporary and temporary.exists():temporary.unlink(missing_ok=True)
    return Waveform(peaks)


def paint_waveform(painter,rect,samples,media,item,pixels_per_second,left_bound,right_bound):
    from PySide6.QtCore import QPointF,Qt
    from PySide6.QtGui import QColor,QPainterPath,QPen
    left=max(math.ceil(rect.left()+3),math.ceil(left_bound)); right=min(math.floor(rect.right()-3),math.floor(right_bound))
    if right<=left:return
    xs=np.arange(left,right+1,dtype=float)
    elapsed=(xs-rect.left())/pixels_per_second
    times=item.in_point+elapsed*item.speed; width=item.speed/pixels_per_second
    if isinstance(samples,Waveform):values=samples.columns(times,width)
    else:  # Compatibility for in-memory legacy/tests; new imports use signed peaks.
        values=np.asarray(samples,dtype=float); indexes=np.clip((times/max(.01,media.duration)*len(values)).astype(int),0,len(values)-1)
        values=np.column_stack((-values[indexes],values[indexes]))
    fade=np.ones(len(xs))
    if item.fade_in:fade*=np.clip(elapsed/item.fade_in,0,1)
    if item.fade_out:fade*=np.clip((item.duration-elapsed)/item.fade_out,0,1)
    values=np.clip(values*(10**(item.gain_db/20))*fade[:,None],-1,1)
    # Reserve a separate name strip; the centre line stays legible through peaks.
    top=rect.top()+6; bottom=max(top+4,rect.bottom()-18); mid=(top+bottom)/2; amp=max(2,(bottom-top)/2-1)
    painter.save(); painter.setPen(Qt.NoPen)
    for column,sign in ((1,-1),(0,1)):
        baseline=mid+sign*.5; path=QPainterPath(); path.moveTo(left,baseline)
        for x,value in zip(xs,values[:,column]):path.lineTo(float(x),baseline-float(value)*amp)
        path.lineTo(right,baseline); path.closeSubpath(); painter.fillPath(path,QColor('#dceee3'))
    painter.setPen(QPen(QColor(213,238,223,95),.7,Qt.DotLine)); painter.drawLine(QPointF(left,mid),QPointF(right,mid)); painter.restore()
