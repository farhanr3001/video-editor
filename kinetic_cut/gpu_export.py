"""Offline D3D11 export recipes and an owned, cancellable native worker.

Unsupported operations explicitly retain the exact compatibility renderer.
No GUI objects, wall-clock playback or frame readbacks are used here.
"""
import ctypes
import copy
import json
import math
import os
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path


class Unsupported(ValueError):
    pass


def recipe(project, preset, directory, burn_captions=True, prepared=None):
    from .exporter import _target_size
    from .effects import MATRICES
    from .creative_effects import NAMES as CREATIVE_NAMES, descriptor
    if burn_captions and project.captions:raise Unsupported('caption rasterization')
    settings=project.settings; width=settings.width; height=settings.height
    rate=Fraction(str(settings.fps)).limit_denominator(1001000)
    if not 1<=float(rate)<=240 or not 1<=width<=8192 or not 1<=height<=8192:raise Unsupported('output dimensions or frame rate')
    order={track:n for n,track in enumerate(project.video_tracks)}
    layers=[]
    for item in sorted((i for i in project.timeline if i.track in order and not i.muted and project.track_states.get(i.track,{}).get('visible',True)),key=lambda i:(order[i.track],i.start)):
        media=project.media_by_id(item.media_id)
        if item.role in ('title','graphic'):raise Unsupported('text or graphics rasterization')
        if not media or media.kind not in ('video','image'):continue
        processed=(prepared or {}).get(item.id)
        from .enhance import active as enhance_active
        enhanced=bool(enhance_active(item))
        if enhanced and not processed:raise Unsupported('AI Enhance prepared source is missing')
        if processed and item.role=='background':raise Unsupported('prepared background geometry')
        from .visual_fx import VISUAL_FX_SET,visual_fx_synthetic_keyframes
        has_vfx=any(e.get('enabled',True) and (e.get('category')=='Visual FX' or e.get('name') in VISUAL_FX_SET) for e in item.effects)
        if has_vfx:
            item=copy.copy(item);item.keyframes={**visual_fx_synthetic_keyframes(item),**(item.keyframes or {})}
        if item.composite_mode!='Normal':raise Unsupported('blend mode '+item.composite_mode)
        if item.transform.pitch or item.transform.yaw:raise Unsupported('perspective')
        if abs(item.speed-1)>1e-7:raise Unsupported('exact retime frame cadence')
        effects=[e for e in item.effects if e.get('enabled',True)]
        operations=[];keys=[]
        if item.role!='background' and (item.transform.shape=='circle' or item.crop_softness):
            operations.append(dict(kind='mask',circle=item.transform.shape=='circle',softness=max(0.,item.crop_softness)))
        if item.role=='background':
            operations.extend([dict(kind='blur',x=max(.01,settings.blur),y=max(.01,settings.blur),reflect=True),
                dict(kind='grade',brightness=settings.background_brightness-1,contrast=settings.background_contrast,saturation=1)])
        if item.grayscale and not enhanced:operations.append(dict(kind='grade',brightness=0.,contrast=1.,saturation=0.))
        if not enhanced and (item.brightness or item.contrast!=1 or item.saturation!=1):
            operations.append(dict(kind='grade',brightness=item.brightness,contrast=item.contrast,saturation=item.saturation))
        if item.sharpen and not enhanced:operations.append(dict(kind='sharpen',amount=min(5.,max(0.,item.sharpen*2))))
        for effect in ([] if enhanced else effects):
            name=effect.get('name')
            if name in ('Chroma Key','Green Screen'):
                from .chroma import values
                color,similarity,softness=values(effect)
                keys.append(dict(color=[color.redF(),color.greenF(),color.blueF()],similarity=similarity,softness=softness))
            elif name in MATRICES:
                strength=max(0,min(1,float(effect.get('amount',100))/100));matrix=MATRICES[name]
                rows=[[matrix[r][c]*strength+(1-strength if r==c else 0) for c in range(3)] for r in range(3)]
                operations.append(dict(kind='matrix',rows=rows))
            elif name in CREATIVE_NAMES:operations.append(dict(kind='creative',**descriptor(effect,item)))
            elif name=='Gaussian Blur':
                if item.transform.rotation:raise Unsupported('blur on a rotated layer')
                operations.append(dict(kind='blur',x=max(.01,float(effect.get('horizontal',12))),y=max(.01,float(effect.get('vertical',12))),
                    blend=max(0,min(1,float(effect.get('blend',100))/100)),reflect=effect.get('border','Reflect')=='Reflect'))
            elif effect.get('category')=='Visual FX' or name in VISUAL_FX_SET:pass
            elif name in ('Black & White','Light Boost','Cinematic Contrast','Circle Facecam','Fade In / Out'):pass
            elif processed:
                from .vision_effects import NAMES as VISION_NAMES
                from .tracking_effect import NAME as TRACKING_NAME
                if name not in VISION_NAMES and name!=TRACKING_NAME:raise Unsupported('prepared effect stack: '+str(name))
            else:raise Unsupported('effect stack: '+str(name))
        if item.keyframes and (operations or item.role=='background'):raise Unsupported('animated effect geometry')
        crop=item.crop.clamped(); w,h=_target_size(item,media,width,.92 if item.role=='facecam' else 1.,height)
        if max(w,h)>8192 and operations:raise Unsupported('large transformed effect layer')
        tx=item.transform; x=tx.x*width-tx.anchor_x*(tx.scale-1); y=tx.y*height-tx.anchor_y*(tx.effective_scale_y-1)
        radians=math.radians(tx.rotation)
        x+=tx.anchor_x-math.cos(radians)*tx.anchor_x+math.sin(radians)*tx.anchor_y
        y+=tx.anchor_y-math.sin(radians)*tx.anchor_x-math.cos(radians)*tx.anchor_y
        if item.retain_image_position:
            x+=(crop.x+crop.width/2-.5)*w/crop.width; y+=(crop.y+crop.height/2-.5)*h/crop.height
        cx,cy,cw,ch=crop.x,crop.y,crop.width,crop.height
        if item.role=='background':
            factor=max(width/max(1,media.width),height/max(1,media.height))
            cw=width/(max(1,media.width)*factor);ch=height/(max(1,media.height)*factor);cx=(1-cw)/2;cy=(1-ch)/2
            w,h=width,height;x,y=width/2,height/2;radians=0.
        if processed:cx=cy=0.;cw=ch=1.
        if tx.flip_horizontal and item.role!='background':cx+=cw;cw=-cw
        if tx.flip_vertical and item.role!='background':cy+=ch;ch=-ch
        transitions=[]
        for transition in project.transitions_for_item(item.id):
            from .animated_transitions import NAMES as paired_names
            if transition.name in paired_names:continue
            length=min(item.duration,transition.duration);local_start=max(0.,transition.start-item.start)
            if length<=0:continue
            if transition.right_item_id==item.id and item.fade_in<=0:transitions.append(dict(start=local_start,duration=length,incoming=True))
            elif transition.left_item_id==item.id and item.fade_out<=0:transitions.append(dict(start=local_start,duration=length,incoming=False))
        geometry=[];first_frame=math.ceil(item.start*float(rate)-1e-7)
        if item.keyframes:
            from .keyframes import evaluated
            count=math.ceil((item.start+item.duration)*float(rate)-1e-7)-first_frame
            if count>100000:raise Unsupported('large animated geometry stream')
            for frame in range(first_frame,first_frame+count):
                current=evaluated(item,frame/float(rate)-item.start);t=current.transform
                gw,gh=_target_size(current,media,width,.92 if item.role=='facecam' else 1.,height)
                angle=math.radians(t.rotation)
                gx=t.x*width-t.anchor_x*(t.scale-1)+t.anchor_x-math.cos(angle)*t.anchor_x+math.sin(angle)*t.anchor_y
                gy=t.y*height-t.anchor_y*(t.effective_scale_y-1)+t.anchor_y-math.sin(angle)*t.anchor_x-math.cos(angle)*t.anchor_y
                if item.retain_image_position:
                    gx+=(crop.x+crop.width/2-.5)*gw/crop.width;gy+=(crop.y+crop.height/2-.5)*gh/crop.height
                geometry.append([gx-gw/2,gy-gh/2,gw,gh,angle,max(0,min(1,current.opacity/100))])
        layers.append(dict(id=item.id,track=item.track,path=processed or media.path,still=media.kind=='image' and not processed,cpu=media.has_alpha or bool(processed),
            clock=f'{item.in_point:.9f}|{item.start:.9f}|{item.speed:.9f}',start=item.start,end=item.start+item.duration,
            in_point=0. if processed else item.in_point,speed=item.speed,size=[w,h],crop=[cx,cy,cw,ch],box=[x-w/2,y-h/2,w,h],
            blend_mode={'Normal':0,'Add':1,'Multiply':2,'Screen':3}[item.composite_mode],rotation=radians,circle=False,opacity=max(0,min(1,item.opacity/100)),
            fade_in=min(item.duration,item.fade_in),fade_out=min(item.duration,item.fade_out),operations=operations,keys=keys,transitions=transitions,geometry=geometry,first_frame=first_frame,
            skip_ranges=getattr(project,'_transition_exclusions',{}).get(item.id,[])))
    from .transition_export import configure_layers
    layers=configure_layers(project,layers,Unsupported)
    directory=Path(directory)
    return dict(width=width,height=height,fps=float(rate),fps_num=rate.numerator,fps_den=rate.denominator,
        duration=project.duration,bitrate=round(preset.bitrate_mbps*1_000_000),quality=preset.quality,codec=preset.codec,
        output=str(directory/('video.hevc' if preset.codec=='h265' else 'video.h264')),
        status=str(directory/'gpu-status.json'),cancel=str(directory/'gpu-cancel'),layers=layers)


def prepare_recipe(project,preset,directory,burn_captions,prepared,ffmpeg,progress,cancel):
    """Keep exact CPU-only operations in isolated layers, not a whole-scene pass.

    Cached AI/vision/native graphics retain their existing rendering semantics.
    CPU islands are reported separately from D3D composition and NVENC encoding.
    """
    try:
        result=recipe(project,preset,directory,burn_captions,prepared)
        result['cpu_islands']=[]
        return result
    except Unsupported:pass
    if any(i.composite_mode!='Normal' and not i.muted and i.track in project.video_tracks and project.track_states.get(i.track,{}).get('visible',True) for i in project.timeline):raise Unsupported('non-normal scene blend parity')
    from .animated_transitions import NAMES as paired_names
    if any(t.name in paired_names and t.track in project.video_tracks and project.track_states.get(t.track,{}).get('visible',True) for t in project.transitions):
        from .transition_export import prepare
        exact=prepare(project,directory,preset,ffmpeg,prepared,progress,cancel)
        result=prepare_recipe(exact,preset,directory,burn_captions,prepared,ffmpeg,progress,cancel)
        result.setdefault('cpu_islands',[]).extend(t.name+' · exact paired transition' for t in project.transitions if t.name in paired_names)
        return result
    from .rendergraph import command
    from .export_process import render
    from .exporter import write_ass
    base=copy.copy(project);base.timeline=[];base.captions=[];base.transitions=[]
    result=recipe(base,preset,directory,False,{})
    result['duration']=project.duration;result['cpu_islands']=[]
    directory=Path(directory)
    titles=[i for i in project.timeline if i.role in ('title','graphic')]
    ordered={track:n for n,track in enumerate(project.video_tracks)}
    items=sorted((i for i in project.timeline if i.track in ordered and i.role not in ('title','graphic') and not i.muted and project.track_states.get(i.track,{}).get('visible',True)),key=lambda i:(ordered[i.track],i.start))
    def raster(stage,start,end,label,blend_mode=0):
        if cancel and cancel.is_set():raise RuntimeError('Export cancelled. Previous output is unchanged.')
        output=directory/f'island-{len(result["cpu_islands"]):04d}.mkv'
        ass=directory/(output.stem+'.ass')
        has_text=bool(stage.captions or any(i.role in ('title','graphic') for i in stage.timeline))
        if has_text:write_ass(stage,str(ass),burn_captions)
        args=command(stage,str(output),preset,burn_captions,'CPU',ffmpeg,str(ass) if has_text else None,False,prepared,
            window=None if has_text else (start,end),transparent=True)
        args=args[:args.index('-c:v')]+['-c:v','ffv1','-level','3','-pix_fmt','bgra','-threads','2','-frames:v',str(math.ceil((end-start)*stage.settings.fps-1e-7)),'-progress','pipe:1','-nostats',str(output)]
        update=(lambda value,text:progress(0,'Preparing exact effect layer · '+label+' · '+text)) if progress else None
        code,tail=render(args,end-start,update,cancel)
        if code:raise RuntimeError('Exact effect layer failed:\n'+'\n'.join(tail)[-3000:])
        width,height=stage.settings.width,stage.settings.height
        result['layers'].append(dict(id=output.stem,path=str(output),cpu=True,still=False,clock=output.stem,blend_mode=blend_mode,
            start=start,end=end,in_point=0.,speed=1.,size=[width,height],crop=[0,0,1,1],box=[0,0,width,height],opacity=1.,operations=[]))
        result['cpu_islands'].append(label)
    for item in items:
        one=copy.copy(project);one.timeline=[item];one.captions=[]
        one.transitions=[t for t in project.transitions if item.id in (t.left_item_id,t.right_item_id)]
        try:layer=recipe(one,preset,directory,False,prepared)['layers']
        except Unsupported as reason:raster(one,item.start,item.start+item.duration,item.id+' · '+str(reason))
        else:result['layers'].extend(layer)
    if titles or burn_captions and project.captions:
        overlay=copy.copy(project);overlay.timeline=titles;overlay.transitions=[]
        # Caption overlay clocks remain absolute, including silence at either end.
        # A harmless audio-only duration marker is not needed: rendergraph uses
        # the requested full document duration below.
        from .model import TimelineItem
        overlay.timeline=titles+[TimelineItem('__export_overlay_duration__','','__export_duration__',0,project.duration)]
        raster(overlay,0.,project.duration,'captions and titles')
    return result


def worker(path):
    """Private process entry; native resources die with this owned process."""
    if sys.stderr is None:sys.stderr=open(Path(path).with_suffix('.python.log'),'a',encoding='utf-8')
    if sys.stdout is None:sys.stdout=sys.stderr
    dlls=decoder=None;parent_stop=None
    try:
        from .icons import resource_path
        import threading
        from ctypes import wintypes
        job=json.loads(Path(path).read_text(encoding='utf-8'))
        parent=job.get('parent_pid')
        if parent:
            api=ctypes.WinDLL('kernel32',use_last_error=True)
            api.SetErrorMode.argtypes=[wintypes.UINT];api.SetErrorMode.restype=wintypes.UINT
            api.SetErrorMode(0x0001|0x0002|0x8000)  # An isolated driver failure must not open a system dialog.
            api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
            api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];api.WaitForSingleObject.restype=wintypes.DWORD
            api.CloseHandle.argtypes=[wintypes.HANDLE]
            handle=api.OpenProcess(0x100000,False,parent)
            if not handle:raise RuntimeError('Export owner no longer exists')
            parent_stop=threading.Event()
            def watch():
                try:
                    while not parent_stop.is_set():
                        result=api.WaitForSingleObject(handle,200)
                        if result==0:os._exit(3)
                        if result!=258:os._exit(4)
                finally:api.CloseHandle(handle)
            threading.Thread(target=watch,name='gpu-export-owner-watch',daemon=True).start()
        import PySide6
        from .gpu_export_decode import Decoder,CALLBACK
        dlls=os.add_dll_directory(str(Path(PySide6.__file__).parent))
        decoder=Decoder()
        library=ctypes.CDLL(str(resource_path('assets','native','gpu_export.dll')))
        library.kc_export_abi.restype=ctypes.c_uint
        if library.kc_export_abi()!=2:raise RuntimeError('Unsupported native export ABI')
        library.kc_export_set_cpu_reader.argtypes=[CALLBACK];library.kc_export_set_cpu_reader.restype=None
        library.kc_export_set_cpu_reader(decoder.callback)
        library.kc_export_job.argtypes=[ctypes.c_wchar_p];library.kc_export_job.restype=ctypes.c_int
        return library.kc_export_job(str(path))
    except Exception as error:
        import traceback
        traceback.print_exc()
        try:
            job=json.loads(Path(path).read_text(encoding='utf-8'));status=Path(job['status']);pending=status.with_suffix('.pending.json')
            pending.write_text(json.dumps(dict(state='Failed',error=str(error))),encoding='utf-8');os.replace(pending,status)
        except (OSError,KeyError,ValueError):pass
        return 1
    finally:
        if parent_stop:parent_stop.set()
        if decoder:decoder.close()
        if dlls:dlls.close()


def render_native(job,directory,progress=None,cancel=None,stall_timeout=90):
    from .export_process import ChildJob,stop
    from .process import popen
    directory=Path(directory);config=directory/'gpu-job.json';job=dict(job,parent_pid=os.getpid())
    config.write_text(json.dumps(job,allow_nan=False),encoding='utf-8')
    command=[sys.executable]
    if not getattr(sys,'frozen',False):command.append(str(Path(__file__).resolve().parent.parent/'main.py'))
    command+=['--gpu-export-worker',str(config)]
    started=advanced=notice=time.monotonic();frame=-1;status={}
    with (directory/'gpu-worker.log').open('wb') as log:
        child=popen(command,stdout=log,stderr=subprocess.STDOUT);owner=ChildJob(child)
        try:
            while True:
                if cancel and cancel.is_set():raise RuntimeError('Export cancelled. Previous output is unchanged.')
                try:status=json.loads(Path(job['status']).read_text(encoding='utf-8'))
                except (OSError,ValueError):pass
                current=status.get('frame',0);now=time.monotonic()
                if current>frame:frame=current;advanced=now
                if child.poll() is not None:break
                if now-advanced>stall_timeout:raise RuntimeError('GPU export stopped advancing; its worker was stopped safely.')
                if progress and now-notice>=.5:
                    progress(min(.9,.9*current/max(1,status.get('frames',1))),f'GPU rendering · {current/max(1,job["fps"]):.1f}s / {job["duration"]:.1f}s')
                    notice=now
                time.sleep(.05)
            # Read the final atomic publication after observing process exit.
            try:status=json.loads(Path(job['status']).read_text(encoding='utf-8'))
            except (OSError,ValueError):pass
            if child.returncode or status.get('state')!='Complete':
                raise RuntimeError(status.get('error') or (directory/'gpu-worker.log').read_text(encoding='utf-8',errors='replace')[-2000:] or 'GPU export worker failed')
            status['wall_seconds']=time.monotonic()-started
            status['cpu_islands']=job.get('cpu_islands',[])
            status['hardware_decode_execution_seconds']=None
            status['source_gpu_frame_count_meaning']='Frames received as D3D11 textures, not a measurement of decoder execution time'
            from .config import CACHE_DIR
            reports=CACHE_DIR/'render-logs';reports.mkdir(parents=True,exist_ok=True)
            (reports/(str(time.time_ns())+'-gpu-export.json')).write_text(json.dumps(status,indent=2),encoding='utf-8')
            return status
        finally:
            if child.poll() is None:
                Path(job['cancel']).touch()
                try:child.wait(timeout=2)
                except subprocess.TimeoutExpired:stop(child,owner)
            owner.close()


def mux_command(project,job,output,preset,ffmpeg,export_audio):
    from .rendergraph import append_audio
    args=[ffmpeg,'-hide_banner','-y','-r',f'{job["fps_num"]}/{job["fps_den"]}','-i',job['output']]
    filters=[]
    if export_audio:
        final=append_audio(project,args,filters,1,project.duration)
        args+=['-filter_complex_threads','2','-filter_complex',';'.join(filters)]
    args+=['-map','0:v:0','-c:v','copy']
    if export_audio:args+=['-map',f'[{final}]','-c:a','aac','-b:a',f'{preset.audio_kbps}k']
    else:args+=['-an']
    return args+['-movflags','+faststart','-t',f'{project.duration:.6f}','-progress','pipe:1','-nostats',output]
