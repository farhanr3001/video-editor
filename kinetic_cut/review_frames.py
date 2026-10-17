"""Bounded offline review frames using the production compositor, never seeking UI."""
import math
import json
import copy
from pathlib import Path
from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QImage,QPainter,QFont


def decode(media,target,cancel):
    import av
    from .video_worker import shared_file
    with shared_file(media.path) as source,av.open(source) as movie:
        stream=movie.streams.video[0]; stream.thread_type='AUTO'; stream.codec_context.thread_count=2
        origin=float((stream.start_time or 0)*stream.time_base)
        movie.seek(max(0,int((target+origin)/stream.time_base)),stream=stream,backward=True)
        chosen=None
        for frame in movie.decode(stream):
            if cancel.is_set():raise InterruptedError('Review cancelled.')
            if frame.pts is None:continue
            stamp=float(frame.pts*stream.time_base)-origin
            # Hold the frame containing this source instant (not the next frame).
            if stamp>target+1e-7 and chosen is not None:break
            chosen=frame
            if stamp>=target-1e-7:break
        if chosen is None:raise ValueError('No video frame decoded: '+media.name)
        array=chosen.to_ndarray(format='rgba')
        return QImage(array.data,array.shape[1],array.shape[0],array.strides[0],QImage.Format_RGBA8888).copy()


def audio_sample(project,settings,stamp,cancel):
    import numpy as np
    from .motion_audio import expanded
    from .rendergraph import audio_filters
    from .process import run_cancellable
    p=expanded(project); end=min(p.duration,stamp+.5); args=[settings.get('ffmpeg','ffmpeg'),'-hide_banner','-loglevel','error']
    filters=[]; labels=[]
    for item in p.timeline:
        state=p.track_states.get(item.track,{})
        if item.track not in p.audio_tracks or item.muted or state.get('muted',False) or not state.get('visible',True):continue
        left=max(item.start,stamp); right=min(item.start+item.duration,end)
        if right<=left:continue
        media=p.media_by_id(item.media_id)
        if not media or not media.has_audio:continue
        index=len(labels)
        sample=copy.copy(item); sample.duration=right-left; sample.fade_in=sample.fade_out=0
        args+=['-ss',str(item.source_time(left)),'-t',str((right-left)*item.speed),'-i',media.path]
        chain=audio_filters(sample); elapsed=left-item.start
        if item.fade_in:chain+=f",volume='min(1,(t+{elapsed:.6f})/{item.fade_in:.6f})':eval=frame"
        if item.fade_out:chain+=f",volume='min(1,max(0,({item.duration-elapsed:.6f}-t)/{item.fade_out:.6f}))':eval=frame"
        filters.append(f'[{index}:a]{chain},adelay={round((left-stamp)*1000)}:all=1[a{index}]')
        labels.append(f'[a{index}]')
    if not labels:return dict(start=stamp,end=end,peak_db=None,rms_db=None,warning='No active audio in this sample.')
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:duration=longest:normalize=0[out]')
    args+=['-filter_complex',';'.join(filters),'-map','[out]','-t',str(end-stamp),'-ac','1','-ar','16000','-f','f32le','pipe:1']
    result=run_cancellable(args,cancel_check=cancel.is_set,check=True,capture_output=True)
    values=np.frombuffer(result.stdout,dtype='<f4')
    peak=float(np.max(np.abs(values))) if len(values) else 0; rms=float(np.sqrt(np.mean(values**2))) if len(values) else 0
    return dict(start=stamp,end=end,peak_db=round(20*math.log10(max(1e-9,peak)),2),rms_db=round(20*math.log10(max(1e-9,rms)),2),
                warning='Possible clipping before master processing.' if peak>=1 else 'Near-silent sample.' if peak<.001 else '',
                scope='Timeline mix before master normalization/noise reduction/ducking; not final loudness certification.')


def create(project,settings,timestamps,width,cancel,progress,directory):
    from .preview_compositor import SceneContext,render
    from .missing_media import export_issues
    issues=export_issues(project)
    if issues:raise ValueError('Cannot produce a complete contact sheet: '+'; '.join(issues[:10]))
    directory=Path(directory)
    from .config import CACHE_DIR
    if not directory.resolve().is_relative_to(Path(CACHE_DIR).resolve()):raise ValueError('Review output must stay inside the app cache.')
    directory.mkdir(parents=True,exist_ok=True)
    factor=min(width/project.settings.width,960/project.settings.height)
    width=max(2,round(project.settings.width*factor)); height=max(2,round(project.settings.height*factor)); cell_height=height+30
    columns=min(3,len(timestamps)); sheet=QImage(columns*width,math.ceil(len(timestamps)/columns)*cell_height,QImage.Format_RGB32); sheet.fill(Qt.black)
    samples=[]
    for n,stamp in enumerate(timestamps):
        if cancel.is_set():raise InterruptedError('Review cancelled.')
        project.playhead=stamp; frames={}; active={}; shared={}
        transitions=[t for t in project.transitions if t.contains_time(stamp)]
        extra={i for t in transitions for i in (t.left_item_id,t.right_item_id) if i}
        for item in project.timeline:
            if item.track not in project.video_tracks or item.muted or not project.track_states.get(item.track,{}).get('visible',True):continue
            if not item.start<=stamp<item.start+item.duration and item.id not in extra:continue
            media=project.media_by_id(item.media_id)
            if item.role in ('title','graphic'):
                for node in item.graphic_data.get('scene',{}).get('nodes',[]):
                    if node.get('kind')=='image' and node.get('source') and not Path(node['source']).is_file():raise ValueError('Missing graphic image: '+node['source'])
                continue
            if not media:raise ValueError('Missing media reference for '+item.id)
            if media.kind=='image':
                if QImage(media.path).isNull():raise ValueError('Could not load image source: '+media.name)
                continue
            if media.kind!='video':continue
            source=item.source_time(max(item.start,min(item.start+item.duration-1/project.settings.fps,stamp)))
            key=(media.id,round(source,7))
            if key not in shared:shared[key]=decode(media,source,cancel)
            frames[key]=shared[key]; active[item.id]=key
        context=SceneContext(project,frames,active,{},False,1)
        image,_,notice=render(context,QRectF(0,0,width,height),(width,height),1)
        if notice:raise ValueError('Incomplete review frame: '+notice)
        path=directory/f'frame-{n:02d}.png'
        if not image.save(str(path)):raise OSError('Could not save review frame.')
        painter=QPainter(sheet)
        try:
            x=(n%columns)*width; y=(n//columns)*cell_height
            painter.drawImage(x,y,image); painter.setPen(Qt.white); painter.setFont(QFont('Arial',11))
            painter.drawText(QRectF(x+6,y+height,width-12,30),Qt.AlignVCenter,f'{int(stamp)//60:02d}:{stamp%60:06.3f}')
        finally:painter.end()
        samples.append(dict(time=stamp,path=str(path),audio=audio_sample(project,settings,stamp,cancel)))
        progress((n+1)/len(timestamps)*100,f'Reviewed {n+1}/{len(timestamps)} timestamps')
    if cancel.is_set():raise InterruptedError('Review cancelled.')
    target=directory/'contact-sheet.png'
    if not sheet.save(str(target)):raise OSError('Could not save contact sheet.')
    report=dict(samples=samples,contact_sheet=str(target),note='Offline paused-quality production compositor frames. This checks content at sampled instants, not real-time playback performance. Audio checks sample only 0.5s at each instant.')
    (directory/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Retain a bounded cache. Only remove generated PNG/JSON files within this
    # exact cache namespace; never recurse through links or project assets.
    root=directory.parent; files=[]
    for folder in root.iterdir():
        if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(root.resolve()):continue
        for path in folder.iterdir():
            if path.is_file() and not path.is_symlink() and path.suffix in ('.png','.json'):
                try:files.append((path.stat().st_mtime,path.stat().st_size,path))
                except OSError:pass
    total=0
    for _,size,path in sorted(files,reverse=True):
        total+=size
        if total>128*1024**2 and path.parent!=directory:
            try:path.unlink()
            except OSError:pass
    return report
