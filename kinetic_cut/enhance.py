"""Non-destructive temporal restoration caches; no inference on the UI thread."""
from .creative_effects import NAMES as CREATIVE_NAMES, apply as apply_creative, clock_offset
import copy,hashlib,json,math,os,tempfile,threading
from pathlib import Path
from fractions import Fraction
from PySide6.QtCore import Qt,QRect
from PySide6.QtGui import QImage
from .image_cache import FileImageCache

NAME='AI Enhance'
DEFAULTS=dict(enhancement_strength=93.,detail_recovery=100.,denoise=71.,deblur=94.,sharpen=100.,compression_cleanup=100.,face_restore=False,face_restore_strength=25.,temporal_stability=80.,upscale=4.,quality_mode='High',mix=100.)
LABELS={'enhancement_strength':'Enhancement Strength','detail_recovery':'Detail Recovery','denoise':'Denoise','deblur':'Deblur','sharpen':'Sharpen','compression_cleanup':'Compression Cleanup','face_restore_strength':'Face Restore Strength','temporal_stability':'Temporal Stability','mix':'Mix'}
_images=FileImageCache(64*1024*1024,max_entries=48)

def default_effect():return dict(name=NAME,enabled=True,**DEFAULTS)

LEGACY_DEFAULTS=dict(DEFAULTS,enhancement_strength=65.,detail_recovery=40.,denoise=35.,deblur=20.,sharpen=10.,compression_cleanup=35.,upscale=1.,quality_mode='Balanced')

def parameters(effect):
    result={}
    for key,default in LEGACY_DEFAULTS.items():
        value=effect.get(key,default)
        if key=='face_restore':result[key]=bool(value)
        elif key=='quality_mode':result[key]=value if value in ('Preview','Balanced','High','Maximum') else default
        else:
            try:value=float(value)
            except (ValueError,TypeError):value=default
            if not math.isfinite(value):value=default
            result[key]=value if key=='upscale' and value in (1.,1.5,2.,4.) else default if key=='upscale' else max(0.,min(100.,value))
    return result

def active(item):
    return [(n,e) for n,e in enumerate(item.effects) if e.get('name')==NAME and e.get('enabled',True) and parameters(e)['mix']>0 and parameters(e)['enhancement_strength']>0]

def signature(media,item,index,fps,include_range=True,schema=5):
    from .vision_effects import fingerprint
    effects=[{k:v for k,v in e.items() if not k.startswith('_')} for e in item.effects[:index+1]]
    for effect in effects:
        if effect.get('name')==NAME:
            effect.update(parameters(effect));effect['enabled']=bool(effect.get('enabled',True))
    for key in ('mix','enhancement_strength'):effects[-1].pop(key,None)
    payload=[schema,fingerprint(media),{k:float(v) for k,v in vars(item.crop.clamped()).items()},float(fps),effects,bool(item.grayscale),float(item.brightness),float(item.contrast),float(item.saturation),float(item.sharpen)]
    if include_range:payload+=[float(item.in_point),float(item.source_duration)]
    # The cached pixels are in the crop's source coordinate system. Ordinary
    # placement/rotation/scale, clip movement and opacity must not invalidate it.
    return hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest()

def sample_fps(project,media,item):return max(1.,min(240.,float(media.fps or project.settings.fps)))

def cache_path(project,media,item,index):
    from .config import CACHE_DIR
    return CACHE_DIR/'ai-enhance'/signature(media,item,index,sample_fps(project,media,item))

def ranges(project,media,item,index):
    from .config import CACHE_DIR
    try:
        family=signature(media,item,index,sample_fps(project,media,item),False)
        families=(family,signature(media,item,index,sample_fps(project,media,item),False,schema=4))
    except (OSError,AttributeError,ValueError):return []
    parent=CACHE_DIR/'ai-enhance'
    try:stamp=parent.stat().st_mtime_ns
    except OSError:return []
    key=(str(parent),stamp,family)
    cached=_range_indexes.get(key)
    if cached is not None:return cached
    records=[]
    for root in parent.iterdir():
        if not root.is_dir() or root.is_symlink() or len(root.name)!=64:continue
        try:
            record=json.loads((root/'info.json').read_text())
            valid=(isinstance(record.get('frames'),int) and 0<record['frames']<=10000000
                   and isinstance(record.get('fps'),(int,float)) and math.isfinite(record['fps']) and 0<record['fps']<=240
                   and isinstance(record.get('source_start'),(int,float)) and math.isfinite(record['source_start']) and record['source_start']>=0)
            if valid and record.get('family') in families and record['key']==root.name:
                records.append(dict(record,root=str(root)))
        except (OSError,ValueError,TypeError,KeyError):continue
    if len(_range_indexes)>32:_range_indexes.clear()
    records.sort(key=lambda r:r.get('engine')=='compact-v1',reverse=True)
    _range_indexes[key]=records
    return records

_range_indexes={}

def info(project,media,item,index):
    """A prepared range covering this entire clip, independent of its placement."""
    for record in ranges(project,media,item,index):
        if record['source_start']<=item.in_point+1e-5 and record['source_start']+record['frames']/record['fps']>=item.in_point+item.source_duration-1e-4:
            root=Path(record['root'])
            if (root/'frames/00000000.png').is_file() and (root/'frames'/f"{record['frames']-1:08d}.png").is_file():return record
    return None

def range_at(project,media,item,index,at):
    candidates=[r for r in ranges(project,media,item,index) if r['source_start']-1e-5<=at<r['source_start']+r['frames']/r['fps']-1e-5]
    return max(candidates,key=lambda r:(r.get('engine')=='compact-v1',r['frames'])) if candidates else None

def cached_frame(project,media,item,index,at):
    record=range_at(project,media,item,index,at)
    if not record:return QImage()
    number=max(0,min(record['frames']-1,round((at-record['source_start'])*record['fps'])))
    return read_frame(record,number,parameters(item.effects[index]))

def read_frame(record,number,p,size=None):
    root=Path(record['root'])
    def load(path):
        if size is None:return _images.load(path)
        from PySide6.QtGui import QImageReader
        reader=QImageReader(str(path));native=reader.size()
        if native.isValid():reader.setScaledSize(native.scaled(size,Qt.KeepAspectRatio).boundedTo(native))
        return reader.read()
    image=load(root/'frames'/f'{number:08d}.png')
    alpha=root/'alpha'/f'{number:08d}.png'
    if not image.isNull() and alpha.is_file():
        image=image.copy();mask=_images.load(alpha)
        if mask.isNull():return QImage()
        image.setAlphaChannel(mask.scaled(image.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation))
    if not image.isNull() and record.get('original_frames'):
        original=load(root/'original'/f'{number:08d}.png')
        if original.isNull():return QImage()
        original=original.scaled(image.size(),Qt.IgnoreAspectRatio,Qt.SmoothTransformation).convertToFormat(QImage.Format_RGBA8888)
        image=image.convertToFormat(QImage.Format_RGBA8888).copy()
        if size is not None:
            # Display-only blend uses Pillow's native contiguous pixel loop.
            # It differs from full-resolution round-to-even by at most one
            # channel level; export retains the exact original NumPy path.
            from PIL import Image
            raw=Image.frombytes('RGBA',(original.width(),original.height()),bytes(original.constBits()))
            restored=Image.frombytes('RGBA',(image.width(),image.height()),bytes(image.constBits()))
            amount=p['mix']/100*p['enhancement_strength']/100
            mixed=Image.blend(raw,restored,amount);mixed.putalpha(raw.getchannel('A'))
            return QImage(mixed.tobytes(),mixed.width,mixed.height,mixed.width*4,QImage.Format_RGBA8888).copy()
        import numpy as np
        enhanced=np.frombuffer(image.bits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4)
        raw=np.frombuffer(original.constBits(),np.uint8).reshape(original.height(),original.bytesPerLine())[:,:original.width()*4].reshape(original.height(),original.width(),4)
        amount=p['mix']/100*p['enhancement_strength']/100
        enhanced[:,:,:3]=np.rint(raw[:,:,:3].astype(np.float32)*(1-amount)+enhanced[:,:,:3].astype(np.float32)*amount).clip(0,255).astype(np.uint8)
        enhanced[:,:,3]=raw[:,:,3]
    return image

def status(project,item):
    media=project.media_by_id(item.media_id)
    stages=active(item)
    if not stages:return ''
    if any(info(project,media,item,index) is None for index,_ in stages):
        if any(ranges(project,media,item,index) for index,_ in stages):return 'AI Enhance covers the prepared source range. Newly exposed frames use original quality; Prepare selected clips to enhance them.'
        return 'AI Enhance needs preparation — open Effects and choose Prepare selected clips.'
    return ''

def render_frame(project,item,source,at,stop=None,strict=False):
    """Shared ordered pixel path for enhanced clips, before canvas transforms."""
    from .preview_raster import RasterContext
    from .vision_effects import apply as vision
    from .tracking_effect import active as tracking,apply as track,effective_crop,crop_source,follow_effect
    from .visuals import grade_image,blur_image
    from .effects import MATRICES,apply_color_effect
    from .chroma import NAMES,apply_stack
    media=project.media_by_id(item.media_id)
    stages={n for n,_ in active(item)}
    image=QImage();start=0
    for index in sorted(stages,reverse=True):
        if stop is not None and index>=stop:continue
        image=cached_frame(project,media,item,index,at)
        if not image.isNull():start=index+1;break
    if image.isNull():
        from .model import Crop
        if follow_effect(item):image=crop_source(source,item,media,at)
        else:image=source if item.crop.clamped()==Crop() else RasterContext._source_crop(source,item.crop)
        if tracking(item):image=track(image,item,media,at,effective_crop(item,media,at))
        image=grade_image(image,item.grayscale,item.brightness,item.contrast,item.saturation,item.sharpen)
    for index,effect in enumerate(item.effects):
        if index<start:continue
        if stop is not None and index>=stop:break
        if not effect.get('enabled',True):continue
        name=effect.get('name')
        if index in stages:
            result=cached_frame(project,media,item,index,at)
            if result.isNull():
                if strict and (range_at(project,media,item,index,at) or not ranges(project,media,item,index)):raise RuntimeError('An enhanced frame is missing. Prepare this effect again.')
            else:image=result
        elif name in CREATIVE_NAMES:
            image=apply_creative(image,effect,(at-item.in_point)/max(.01,item.speed)+clock_offset(effect,item))
        elif name=='Gaussian Blur':image=blur_image(image,effect.get('horizontal',12),effect.get('vertical',12),effect.get('blend',100)/100,effect.get('border','Reflect'))
        elif name in MATRICES:image=apply_color_effect(image,effect)
        elif name in NAMES:
            snapshot=copy.copy(item);snapshot.effects=[effect];image=apply_stack(image,snapshot)
        else:
            from .vision_effects import NAMES as VISION
            if name in VISION:
                snapshot=copy.copy(item);snapshot.effects=[effect];image=vision(image,snapshot,media,at)
    return image

def _source_frames(project,item,ffmpeg,cancel,source_crop=None):
    from .process import popen
    from .export_process import ChildJob,stop
    from .vision_effects import decoded_frames
    import subprocess
    media=project.media_by_id(item.media_id);fps=sample_fps(project,media,item)
    width,height=media.width,media.height;filters=f'fps={fps:.10f},scale={width}:{height}'
    if source_crop is not None:
        crop=source_crop.clamped();x,y=round(crop.x*width),round(crop.y*height)
        width,height=min(width-x,max(1,round(crop.width*width))),min(height-y,max(1,round(crop.height*height)))
        # Convert before cropping: RGBA preserves exact odd-pixel QRect bounds,
        # whereas subsampled YUV crop filters can round them to even dimensions.
        filters+=f',format=rgba,crop={width}:{height}:{x}:{y}:exact=1'
    command=[ffmpeg,'-v','error','-ss',str(item.in_point),'-i',media.path,'-t',str(item.source_duration),'-vf',filters,'-an','-pix_fmt','rgba','-f','rawvideo','pipe:1']
    with tempfile.TemporaryFile() as log:
        process=popen(command,stdout=subprocess.PIPE,stderr=log);job=ChildJob(process)
        try:
            for number,raw in enumerate(decoded_frames(process.stdout,width*height*4,cancel)):
                yield number,QImage(raw,width,height,width*4,QImage.Format_RGBA8888).copy(),item.in_point+number/fps
            if process.wait(timeout=15):raise RuntimeError('Could not decode source for AI Enhance')
        finally:
            if process.poll() is None:stop(process,job)
            job.close();process.stdout.close()

def estimate_space(project,items,applying=False):
    """Conservative uncompressed cache/temporary upper bounds, no decoding."""
    cached=0;peak=0;details=[];seen=set()
    for original in items:
        item=copy.deepcopy(original)
        if applying:item.effects.append(default_effect())
        media=project.media_by_id(item.media_id)
        if not media or media.kind!='video':continue
        width=max(1,round(media.width*item.crop.width));height=max(1,round(media.height*item.crop.height))
        for index,effect in active(item):
            scale=parameters(effect)['upscale'];key=cache_path(project,media,item,index).name
            prepared=info(project,media,item,index)
            if key not in seen and not (prepared and prepared.get('engine')=='compact-v1'):
                frames=max(1,math.ceil(sample_fps(project,media,item)*item.source_duration))
                pixels=width*height;final=int(pixels*(scale*scale*3+5)*frames*1.15)
                working=max(256*1024**2,int(pixels*(scale*scale*3+9)*frames*1.15))
                peak=max(peak,cached+working);cached+=final
                details.append(dict(name=media.name,cache_bytes=final,working_bytes=working))
            seen.add(key);width=max(1,round(width*scale));height=max(1,round(height*scale))
    return dict(cache_bytes=cached,peak_bytes=peak,clips=len(items),details=details)


def prepare_item(project,item,ffmpeg,progress,cancel,root=None):
    from .enhance_component import ready,component_root,model_paths
    from .vocal_component import check_cancel
    from .enhance_process import run as monitored
    from .icons import resource_path
    import av,numpy as np,shutil
    media=project.media_by_id(item.media_id)
    if not media or media.kind!='video':raise ValueError('AI Enhance needs a video source.')
    root=Path(root or component_root())
    if not ready(root):raise RuntimeError('Download AI Enhance explicitly from Optional downloads first.')
    fps=sample_fps(project,media,item)
    for index,effect in active(item):
        check_cancel(cancel)
        existing=info(project,media,item,index)
        if existing and existing.get('engine')=='compact-v1':continue
        destination=cache_path(project,media,item,index);destination.parent.mkdir(parents=True,exist_ok=True)
        width=max(1,round(media.width*item.crop.width));height=max(1,round(media.height*item.crop.height));scale=parameters(effect)['upscale']
        if max(width*scale,height*scale)>8192:raise RuntimeError('This crop would exceed 8192 pixels after enhancement. Choose a smaller Upscale value or crop before preparing.')
        needed=max(256*1024**2,int(width*height*(scale*scale*3+8)*fps*item.source_duration*1.15))
        if shutil.disk_usage(destination.parent).free<needed:raise RuntimeError(f'Free about {needed/1024**3:.1f} GB for this enhanced clip cache.')
        with tempfile.TemporaryDirectory(prefix='preparing-',dir=destination.parent) as temporary:
            stage=Path(temporary);frames=stage/'frames';frames.mkdir();alpha=stage/'alpha';alpha.mkdir();originals=stage/'original';originals.mkdir();movie=stage/'input.mkv'
            count=0
            from .tracking_effect import active as tracking_active
            from .model import Crop
            pre_crop=item.crop if index==0 and not tracking_active(item) else None
            pixel_item=copy.copy(item) if pre_crop is not None else item
            if pre_crop is not None:pixel_item.crop=Crop()
            with av.open(str(movie),'w') as output:
                stream=None
                for number,image,at in _source_frames(project,item,ffmpeg,cancel,source_crop=pre_crop):
                    check_cancel(cancel);image=render_frame(project,pixel_item,image,at,stop=index,strict=True).convertToFormat(QImage.Format_RGBA8888)
                    if not image.save(str(originals/f'{number:08d}.png'),'PNG',80):raise RuntimeError('Could not cache the untouched enhancement input')
                    values=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4)
                    if stream is None:
                        if max(image.width()*scale,image.height()*scale)>8192:raise RuntimeError('The stacked enhancement would exceed 8192 pixels. Reduce Upscale or remove the earlier upscale effect.')
                        actual_needed=int(image.width()*image.height()*(scale*scale*3+8)*fps*item.source_duration*1.15)
                        if shutil.disk_usage(destination.parent).free<actual_needed:raise RuntimeError(f'Free about {actual_needed/1024**3:.1f} GB for these enhanced frames.')
                        stream=output.add_stream('ffv1',rate=Fraction(str(fps)).limit_denominator(100000));stream.width=image.width();stream.height=image.height();stream.pix_fmt='bgra'
                    if np.any(values[:,:,3]!=255):
                        mask=QImage(values[:,:,3].copy().tobytes(),image.width(),image.height(),image.width(),QImage.Format_Grayscale8).copy()
                        if not mask.save(str(alpha/f'{number:08d}.png')):raise RuntimeError('Could not cache source alpha')
                    frame=av.VideoFrame.from_ndarray(values.copy(),format='rgba');frame.pts=number
                    for packet in stream.encode(frame):output.mux(packet)
                    count+=1
                    if number%30==0:progress((min(20,number/max(1,fps*item.source_duration)*20),'Preparing source pixels'))
                if not stream:raise RuntimeError('No source frames to enhance')
                for packet in stream.encode():output.mux(packet)
            config=dict(input=str(movie),output=str(frames),models=model_paths(root),parent_pid=os.getpid(),gpu_duty=.5,parameters=dict(parameters(effect),mix=100.,enhancement_strength=100.))
            config_path=stage/'job.json';config_path.write_text(json.dumps(config))
            def inference_progress(event):
                for line in reversed(event[1].splitlines()):
                    try:
                        update=json.loads(line)
                        if 'frames' in update:
                            progress((20+75*min(1,update['frames']/count),f"Restoring frame {update['frames']}/{count} · {update['backend']}"));return
                    except (ValueError,TypeError):pass
                progress(event)
            monitored([str(root/'python.exe'),str(resource_path('assets','enhance_fast_worker.py')),str(config_path)],stage/'inference.log',inference_progress,cancel,timeout=max(120,count*.5+90))
            record=json.loads((frames/'worker.json').read_text());assert record['frames']==count,'Restoration frame count mismatch'
            check_cancel(cancel)
            for number in range(count):
                if not (frames/f'{number:08d}.png').is_file():raise RuntimeError('Restoration output is incomplete')
            record.update(key=destination.name,family=signature(media,item,index,fps,False),fps=fps,source_start=item.in_point,original_frames=True)
            (stage/'info.json').write_text(json.dumps(record));movie.unlink();config_path.unlink()
            if destination.exists():
                # Invalid/disposable cache only, verified under its dedicated root.
                assert destination.resolve().parent==stage.parent.resolve() and not destination.is_symlink()
                shutil.rmtree(destination)
            # Windows scanners may retain a directory handle after inference.
            # Publish closed files individually and commit info.json LAST; a
            # cancelled/incomplete publication is never a usable cache range.
            destination.mkdir(exist_ok=True)
            for folder in ('frames','alpha','original'):
                (destination/folder).mkdir(exist_ok=True)
                for path in (stage/folder).iterdir():
                    check_cancel(cancel);path.replace(destination/folder/path.name)
            (stage/'inference.log').replace(destination/'inference.log')
            (stage/'info.json').replace(destination/'info.json')
            os.utime(destination.parent,None);_range_indexes.clear()
        progress((100,'AI Enhance ready · '+record['backend']))

def export_key(project,item):
    media=project.media_by_id(item.media_id)
    return hashlib.sha256(json.dumps([cache_path(project,media,item,active(item)[-1][0]).name,item.effects,item.crop_softness,[[r['key'] for r in ranges(project,media,item,index)] for index,_ in active(item)]],sort_keys=True).encode()).hexdigest()


def prepare_export(project,ffmpeg,progress,cancel):
    """Bake only enhanced clips into existing prepared-video export substitution."""
    import av,numpy as np
    from .config import CACHE_DIR
    from .vocal_component import check_cancel
    result={};cancel=cancel or threading.Event()
    for item in project.timeline:
        if not active(item) or item.muted or not project.track_states.get(item.track,{}).get('visible',True):continue
        media=project.media_by_id(item.media_id)
        if any(not ranges(project,media,item,index) for index,_ in active(item)):
            raise RuntimeError('AI Enhance needs preparation. Open Effects and choose Prepare selected clips, or disable the effect to export original quality.')
        key=export_key(project,item)
        target=CACHE_DIR/'ai-enhance'/(key+'.mkv')
        if not target.is_file():
            pending=target.with_suffix('.pending.mkv');stream=None
            try:
                with av.open(str(pending),'w') as output:
                    fps=sample_fps(project,media,item)
                    for number,source,at in _source_frames(project,item,ffmpeg,cancel):
                        check_cancel(cancel);image=render_frame(project,item,source,at,strict=True).convertToFormat(QImage.Format_RGBA8888)
                        if stream is None:
                            stream=output.add_stream('ffv1',rate=Fraction(str(fps)).limit_denominator(100000));stream.width=image.width();stream.height=image.height();stream.pix_fmt='bgra'
                        values=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4)
                        frame=av.VideoFrame.from_ndarray(values.copy(),format='rgba');frame.pts=number
                        for packet in stream.encode(frame):output.mux(packet)
                    if not stream:raise RuntimeError('No enhanced frames to export')
                    for packet in stream.encode():output.mux(packet)
                check_cancel(cancel);pending.replace(target)
            finally:pending.unlink(missing_ok=True)
        result[item.id]=str(target)
    return result
