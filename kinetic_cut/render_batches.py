"""Bounded video graphs; one continuous final pass for audio and captions.

Opening every cut at once makes framesync retain many full-resolution frames.
Render short lossless video batches instead, without changing the saved edit.
"""
import copy
import math
from pathlib import Path
from .model import MediaItem, TimelineItem, Transform


def needed(project):
    return sum(i.track in project.video_tracks and i.role!='title' for i in project.timeline)>12


def ranges(project):
    fps=project.settings.fps
    end=math.ceil(project.duration*fps-1e-7)
    boundaries={0,end}
    for item in project.timeline:
        if item.track in project.video_tracks and item.role!='title':
            boundaries.update(max(0,min(end,math.ceil(t*fps-1e-7))) for t in (item.start,item.start+item.duration))
    boundaries.update(range(0,end,max(1,round(fps*10))))
    frames=sorted(boundaries)
    return [(a/fps,b/fps) for a,b in zip(frames,frames[1:]) if b>a]


def prepare(project,directory,preset,ffmpeg,prepared,progress,cancel,transparent=False):
    from .rendergraph import command
    from .export_process import render
    import os,threading
    from concurrent.futures import ThreadPoolExecutor
    directory=Path(directory); parts=[]; spans=ranges(project)
    total=spans[-1][1]
    completed=[0.]*len(spans); progress_lock=threading.Lock(); abort=threading.Event()
    class Cancel:
        def is_set(self):return abort.is_set() or bool(cancel and cancel.is_set())
    token=Cancel()
    def batch(number):
        if token.is_set():raise RuntimeError('Export cancelled')
        start,end=spans[number]
        target=directory/f'part-{number:04d}.mkv'
        args=command(copy.deepcopy(project),str(target),preset,False,'CPU',ffmpeg,None,False,prepared,window=(start,end),transparent=transparent)
        # Lossless intermediate: no extra lossy generation before final encoding.
        threads=str(os.cpu_count() or 4)
        codec=['-c:v','ffv1','-level','3','-slices','16','-pix_fmt','bgra'] if transparent else ['-c:v','libx264','-preset','ultrafast','-crf','0']
        args=args[:args.index('-c:v')]+codec+['-threads',threads,'-frames:v',str(round((end-start)*project.settings.fps)),'-progress','pipe:1','-nostats',str(target)]
        def update(value,text):
            with progress_lock:
                completed[number]=max(completed[number],value*(end-start)); done=sum(completed)
                if progress:progress(.8*done/total,f'Rendering video · {done:.1f}s / {total:.1f}s')
        code,tail=render(args,end-start,update,token)
        if code:abort.set(); raise RuntimeError('Video batch failed:\n'+'\n'.join(tail)[-3000:])
        update(1.,''); return target
    # Two independent, bounded graphs use otherwise idle cores. Keep memory and
    # decoder counts bounded rather than launching every cut simultaneously.
    with ThreadPoolExecutor(max_workers=2 if (os.cpu_count() or 1)>=8 else 1) as pool:
        try:parts=list(pool.map(batch,range(len(spans))))
        except BaseException:abort.set(); raise
    listing=directory/'parts.txt'
    listing.write_text(''.join(f"file '{part.name}'\n" for part in parts),encoding='utf-8')
    flat=directory/'composited.mkv'
    code,tail=render([ffmpeg,'-hide_banner','-y','-f','concat','-safe','1','-i',str(listing),'-c','copy','-progress','pipe:1','-nostats',str(flat)],total,None,cancel)
    if code:raise RuntimeError('Could not join video batches:\n'+'\n'.join(tail)[-3000:])
    for part in parts:part.unlink()
    stage=copy.deepcopy(project)
    stage.timeline=[i for i in stage.timeline if i.track not in stage.video_tracks or i.role=='title']
    media=MediaItem('__render_batches__',str(flat),'video','Composited video',project.duration,project.settings.width,project.settings.height,project.settings.fps)
    media.has_alpha=transparent
    stage.media.append(media)
    stage.timeline.append(TimelineItem('__render_batches__',media.id,stage.video_tracks[0],0,project.duration,transform=Transform(x=.5,y=.5)))
    stage.track_states[stage.video_tracks[0]]={'visible':True,'muted':False,'locked':False}
    return stage
