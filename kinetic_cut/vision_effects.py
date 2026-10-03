"""Cached face/person analysis and deterministic Qt preview/export effects."""
import json,hashlib,math,os,time,tempfile,subprocess
from pathlib import Path
from functools import lru_cache
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QImage,QPainter,QPainterPath,QColor,QPen,QPolygonF
import numpy as np

# Legacy accessory names remain readable in saved projects, but are no longer
# offered in the library. Do not silently rewrite the user's saved projects.
ACCESSORY_NAMES={'Puppy Ears & Nose','Cat Ears & Whiskers'}
AR_NAMES={'AR Plague Mask','AR Pixel Glasses'}
POSE_NAMES=ACCESSORY_NAMES|AR_NAMES
MESH_NAMES={'Custom Face'}
NAMES={'Remove Person Background','Party Hat','Face Mask','Big Eyes','Big Nose','Big Lips','Face Twist'} | POSE_NAMES | MESH_NAMES
FACE_NAMES=NAMES-{'Remove Person Background'}

def fingerprint(media):
    path=Path(media.path).resolve(); stat=path.stat()
    return [os.path.normcase(str(path)),stat.st_size,stat.st_mtime_ns]

def active(item):return [e for e in item.effects if e.get('name') in NAMES and e.get('enabled',True)]

def valid(analysis,media,item,require_geometry=False,require_mesh=False):
    try:
        return (isinstance(analysis['frames'],int) and analysis['frames']>0 and 0<analysis['fps']<=60 and analysis['source']==fingerprint(media) and analysis['crop']==vars(item.crop.clamped()) and item.in_point>=analysis['source_start']-1e-5 and item.in_point+item.source_duration<=analysis['source_end']+1e-4 and len(face_data(analysis['root']))==analysis['frames'] and (Path(analysis['root'])/'masks'/'00000000.png').is_file() and (not require_geometry or len(geometry_data(analysis['root']))==analysis['frames']) and (not require_mesh or mesh_data(analysis['root']).shape==(analysis['frames'],478,3)))
    except (KeyError,OSError,TypeError,AttributeError,ValueError):return False

@lru_cache(maxsize=8)
def _face_data(path,size,modified):
    records=json.loads(Path(path).read_text())
    if not isinstance(records,list):raise ValueError('Invalid face cache')
    for points in records:
        if points is None:continue
        if not isinstance(points,list) or len(points)!=10 or any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in p) for p in points):raise ValueError('Invalid face landmarks')
    return records

def face_data(root):
    path=Path(root)/'faces.json'; stat=path.stat()
    return _face_data(str(path),stat.st_size,stat.st_mtime_ns)

@lru_cache(maxsize=4)
def _geometry_data(path,size,modified):
    records=json.loads(Path(path).read_text())
    if not isinstance(records,list):raise ValueError('Invalid face geometry')
    for pose in records:
        if pose is None:continue
        if (not isinstance(pose,dict) or not isinstance(pose.get('points'),list) or len(pose['points'])!=10
            or any(not isinstance(p,list) or len(p)!=3 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in p) for p in pose['points'])
            or not isinstance(pose.get('matrix'),list) or len(pose['matrix'])!=4
            or any(not isinstance(row,list) or len(row)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in row) for row in pose['matrix'])):
            raise ValueError('Invalid face pose')
    return records

def geometry_data(root):
    path=Path(root)/'geometry.json'; stat=path.stat()
    return _geometry_data(str(path),stat.st_size,stat.st_mtime_ns)

@lru_cache(maxsize=2)
def _mesh_data(path,size,modified):
    # Loaded arrays do not hold an open Windows file mapping, so regenerating
    # or removing an analysis cache cannot fail merely because it was viewed.
    data=np.load(path,allow_pickle=False)
    if data.ndim!=3 or data.shape[1:]!=(478,3) or data.dtype!=np.float16:
        raise ValueError('Invalid face mesh')
    return data

def mesh_data(root):
    path=Path(root)/'mesh.npy'; stat=path.stat()
    return _mesh_data(str(path),stat.st_size,stat.st_mtime_ns)

def valid_effect(effect,media,item):
    analysis=effect.get('analysis',{})
    name=effect.get('name')
    return valid(analysis,media,item,name in POSE_NAMES,name in MESH_NAMES)

from .image_cache import FileImageCache

_mask_cache=FileImageCache(32*1024*1024, max_entries=512)

def mask_image(root,index):return _mask_cache.load(Path(root)/'masks'/f'{index:08d}.png')

mask_image.cache_clear=_mask_cache.clear

def frame_index(analysis,source_time):return max(0,min(analysis['frames']-1,round((source_time-analysis['source_start'])*analysis['fps'])))

def status(item,media,source_time):
    effects=active(item)
    if not effects:return ''
    if any(not valid_effect(e,media,item) for e in effects):return 'Effect needs analysis — use Re-analyse in Effects'
    a=effects[0]['analysis']
    if any(e['name']=='Remove Person Background' for e in effects) and mask_image(a['root'],frame_index(a,source_time)).isNull():return 'Background cache missing — use Re-analyse in Effects'
    if any(e['name'] in FACE_NAMES for e in effects):
        if not face_data(a['root'])[frame_index(a,source_time)]:return 'Face not detected — face filter hidden'
    return ''

def apply(image,item,media,source_time):
    effects=active(item)
    if not effects or any(not valid_effect(e,media,item) for e in effects):return image
    if image.isNull():return image
    a=effects[0]['analysis']; index=frame_index(a,source_time); points=face_data(a['root'])[index]; names={e['name'] for e in effects}
    result=image.convertToFormat(QImage.Format_RGBA8888).copy(); width=result.width(); height=result.height()
    if 'Remove Person Background' in names:
        mask=mask_image(a['root'],index)
        if not mask.isNull():
            if mask.size()!=result.size():
                mask=mask.scaled(width,height,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
            mask=mask.convertToFormat(QImage.Format_Grayscale8)
            pixels=np.frombuffer(result.bits(),dtype=np.uint8).reshape(height,width,4)
            bpl=mask.bytesPerLine()
            values=np.frombuffer(mask.constBits(),dtype=np.uint8).reshape(height,bpl)[:,:width] if bpl!=width else np.frombuffer(mask.constBits(),dtype=np.uint8).reshape(height,width)
            pixels[:,:,3]=(pixels[:,:,3].astype(np.uint16)*values//255).astype(np.uint8)
    if points and names&MESH_NAMES:
        from .custom_face import apply_custom_face
        for effect in effects:
            if effect['name']=='Custom Face':
                mesh_analysis=effect['analysis']
                mesh_index=frame_index(mesh_analysis,source_time)
                apply_custom_face(result,mesh_data(mesh_analysis['root'])[mesh_index],effect)
    if points and 'Big Eyes' in names:
        pixels=np.frombuffer(result.bits(),dtype=np.uint8).reshape(height,width,4)
        original=pixels.copy(); face_width=abs(points[5][0]-points[4][0])*width
        for centre in (points[8],points[9]):
            cx,cy=centre[0]*width,centre[1]*height; radius=max(3,face_width*.18)
            x0=max(0,int(cx-radius)); x1=min(width,int(cx+radius+1)); y0=max(0,int(cy-radius)); y1=min(height,int(cy+radius+1))
            if x1<=x0 or y1<=y0:continue
            yy,xx=np.mgrid[y0:y1,x0:x1]; dx=xx-cx; dy=yy-cy; r=np.sqrt(dx*dx+dy*dy)/radius; factor=np.where(r<1,.55+.45*r*r,1.)
            sx=np.clip(cx+dx*factor,0,width-1); sy=np.clip(cy+dy*factor,0,height-1); ix=sx.astype(int); iy=sy.astype(int); fx=(sx-ix)[...,None]; fy=(sy-iy)[...,None]
            pixels[y0:y1,x0:x1]=np.rint(original[iy,ix]*(1-fx)*(1-fy)+original[iy,np.minimum(ix+1,width-1)]*fx*(1-fy)+original[np.minimum(iy+1,height-1),ix]*(1-fx)*fy+original[np.minimum(iy+1,height-1),np.minimum(ix+1,width-1)]*fx*fy).astype(np.uint8)
    if points:
        fw=max(3,math.hypot((points[5][0]-points[4][0])*width,(points[5][1]-points[4][1])*height))
        fh=max(3,math.hypot((points[3][0]-points[2][0])*width,(points[3][1]-points[2][1])*height))
        angle=math.atan2((points[1][1]-points[0][1])*height,(points[1][0]-points[0][0])*width)
        # Stable order, independent of inspector stack ordering, matches Big Eyes.
        for name,centre,rx,ry in (('Big Nose',points[6],fw*.26,fh*.23),('Big Lips',points[7],fw*.34,fh*.18),('Face Twist',points[6],fw*.62,fh*.58)):
            if name in names:warp_face(result,centre,rx,ry,angle,twist=name=='Face Twist')
    if points and names&ACCESSORY_NAMES:
        from .face_accessories import paint_accessories
        paint_accessories(result,geometry_data(a['root'])[index],names & ACCESSORY_NAMES)
    if points and names&AR_NAMES:
        from .ar_face_filters import paint_ar_filters
        paint_ar_filters(result,geometry_data(a['root'])[index],names & AR_NAMES)
    if points and names&{'Party Hat','Face Mask'}:
        painter=QPainter(result); painter.setRenderHint(QPainter.Antialiasing)
        left,right,forehead,chin,side1,side2,nose,mouth,*_=points
        fw=max(10,math.hypot((side2[0]-side1[0])*width,(side2[1]-side1[1])*height)); fh=max(10,math.hypot((chin[0]-forehead[0])*width,(chin[1]-forehead[1])*height))
        angle=math.degrees(math.atan2((right[1]-left[1])*height,(right[0]-left[0])*width))
        if 'Party Hat' in names:
            painter.save(); painter.translate(forehead[0]*width,forehead[1]*height); painter.rotate(angle)
            path=QPainterPath(); path.moveTo(-fw*.48,fh*.08); path.lineTo(0,-fh*.65); path.lineTo(fw*.48,fh*.08); path.closeSubpath()
            painter.setPen(QPen(QColor('#f4eeff'),max(1,fw*.012))); painter.setBrush(QColor('#a652ef')); painter.drawPath(path)
            painter.setPen(QPen(QColor('#55ffff'),max(2,fw*.07))); painter.drawLine(QPointF(-fw*.29,-fh*.2),QPointF(fw*.23,-fh*.3)); painter.setBrush(QColor('#ffdf55')); painter.setPen(Qt.NoPen); painter.drawEllipse(QPointF(0,-fh*.65),fw*.065,fw*.065); painter.restore()
        if 'Face Mask' in names:
            painter.save(); painter.translate((nose[0]+mouth[0])/2*width,(nose[1]+chin[1])/2*height); painter.rotate(angle)
            rect=QRectF(-fw*.43,-fh*.14,fw*.86,fh*.34); painter.setPen(QPen(QColor('#6fd9e5'),max(1,fw*.01))); painter.setBrush(QColor('#212b45')); painter.drawRoundedRect(rect,fw*.08,fh*.08)
            painter.setPen(QPen(QColor('#7086a0'),max(1,fw*.009)))
            for offset in (0,.07,.14):painter.drawLine(QPointF(-fw*.32,fh*(-.06+offset)),QPointF(fw*.32,fh*(-.06+offset)))
            painter.restore()
        painter.end()
    return result


def warp_face(image,centre,rx,ry,angle=0.,twist=False):
    """Bilinear, smooth-edge inverse warp, including alpha; no extra model."""
    width,height=image.width(),image.height(); cx,cy=centre[0]*width,centre[1]*height
    radius=max(3,rx,ry); rx=max(3,rx); ry=max(3,ry)
    x0=max(0,int(cx-radius-1)); x1=min(width,int(cx+radius+2)); y0=max(0,int(cy-radius-1)); y1=min(height,int(cy+radius+2))
    if x1<=x0 or y1<=y0:return
    pixels=np.frombuffer(image.bits(),dtype=np.uint8).reshape(height,width,4); original=pixels.copy()
    yy,xx=np.mgrid[y0:y1,x0:x1]; dx=xx-cx; dy=yy-cy; co,si=math.cos(angle),math.sin(angle)
    u=(co*dx+si*dy)/rx; v=(-si*dx+co*dy)/ry; radius2=u*u+v*v
    blend=np.maximum(0,1-radius2)**2
    if twist:
        theta=-.95*blend; c=np.cos(theta); s=np.sin(theta); u,v=u*c-v*s,u*s+v*c
    else:
        factor=1-.5*blend; u=u*factor; v=v*factor
    sx=np.clip(cx+co*u*rx-si*v*ry,0,width-1); sy=np.clip(cy+si*u*rx+co*v*ry,0,height-1)
    ix=sx.astype(int); iy=sy.astype(int); fx=(sx-ix)[...,None]; fy=(sy-iy)[...,None]
    sampled=original[iy,ix]*(1-fx)*(1-fy)+original[iy,np.minimum(ix+1,width-1)]*fx*(1-fy)+original[np.minimum(iy+1,height-1),ix]*(1-fx)*fy+original[np.minimum(iy+1,height-1),np.minimum(ix+1,width-1)]*fx*fy
    pixels[y0:y1,x0:x1]=np.where((radius2<1)[...,None],np.rint(sampled).astype(np.uint8),original[y0:y1,x0:x1])

def decoded_frames(stream,size,cancel,timeout=90):
    """Bounded reads keep Cancel responsive even when a decoder emits nothing."""
    import threading,queue
    from .vocal_component import check_cancel
    output=queue.Queue(maxsize=2); finished=threading.Event()
    def read():
        while not finished.is_set():
            try:value=stream.read(size)
            except Exception as error:value=error
            while not finished.is_set():
                try:output.put(value,timeout=.1); break
                except queue.Full:pass
            if not value or isinstance(value,Exception):break
    reader=threading.Thread(target=read,daemon=True); reader.start()
    try:
        started=time.monotonic()
        while True:
            check_cancel(cancel)
            try:value=output.get(timeout=.1)
            except queue.Empty:
                if time.monotonic()-started>timeout:raise TimeoutError('Video decoding stopped advancing. Cancelled effect preparation safely; please re-analyse the clip.')
                continue
            if isinstance(value,Exception):raise value
            if not value:return
            if len(value)!=size:raise RuntimeError('Incomplete video frame during effect rendering.')
            yield value
            started=time.monotonic()
    finally:finished.set()

def prepare_export(project,ffmpeg,progress,cancel):
    if not any(active(item) for item in project.timeline):return {}
    import threading
    cancel=cancel or threading.Event()
    from .config import CACHE_DIR
    from .process import popen
    from .export_process import ChildJob,stop
    from .vocal_component import check_cancel
    from .exporter import _crop_filter
    import av
    from fractions import Fraction
    result={}
    for item in project.timeline:
        effects=active(item)
        if not effects or item.muted or not project.track_states.get(item.track,{}).get('visible',True):continue
        media=project.media_by_id(item.media_id)
        if not media or any(not valid_effect(e,media,item) for e in effects):raise ValueError('Face/background analysis is missing or the crop/source changed. Select the clip and click Re-analyse in Effects before exporting.')
        if any(e['name']=='Remove Person Background' for e in effects):
            analysis=effects[0]['analysis']
            for index in range(frame_index(analysis,item.in_point),frame_index(analysis,item.in_point+item.source_duration)+1):
                check_cancel(cancel)
                if mask_image(analysis['root'],index).isNull():raise ValueError('Background analysis cache is missing or damaged. Select the clip and click Re-analyse in Effects.')
        fps=max(1,min(60,project.settings.fps/max(.05,item.speed))); crop=item.crop.clamped(); width=max(2,int(media.width*crop.width)//2*2); height=max(2,int(media.height*crop.height)//2*2)
        key=hashlib.sha256(json.dumps([fingerprint(media),vars(crop),item.in_point,item.source_duration,fps,effects],sort_keys=True).encode()).hexdigest()
        target=CACHE_DIR/'vision-renders'/(key+'.mkv'); target.parent.mkdir(parents=True,exist_ok=True)
        if target.is_file():result[item.id]=str(target); continue
        import shutil
        needed=max(50*1024**2,int(width*height*4*item.source_duration*fps/3))
        if shutil.disk_usage(target.parent).free<needed:raise RuntimeError(f'Please free about {needed/1024**3:.1f} GB for this lossless effect render cache.')
        if progress:progress(0,'Preparing cached face/background frames…')
        inputs=['-loop','1'] if media.kind=='image' else ['-ss',str(item.in_point)]
        command=[ffmpeg,'-v','error']+inputs+['-i',media.path,'-t',str(item.source_duration),'-vf',_crop_filter(item)+f',scale={width}:{height},fps={fps:.6f}','-an','-pix_fmt','rgba','-f','rawvideo','pipe:1']
        with tempfile.TemporaryDirectory(prefix='vision-render-',dir=target.parent) as directory:
            pending=Path(directory)/'effect.mkv'
            with (Path(directory)/'decode.log').open('wb') as log:
                decoder=popen(command,stdout=subprocess.PIPE,stderr=log); job=ChildJob(decoder)
                try:
                    with av.open(str(pending),'w') as movie:
                        stream=movie.add_stream('ffv1',rate=Fraction(str(round(fps,6)))); stream.width=width; stream.height=height; stream.pix_fmt='bgra'; stream.options={'level':'3'}
                        n=0
                        for raw in decoded_frames(decoder.stdout,width*height*4,cancel):
                            image=QImage(raw,width,height,width*4,QImage.Format_RGBA8888).copy(); image=apply(image,item,media,item.in_point+n/fps)
                            pixels=np.frombuffer(image.constBits(),dtype=np.uint8).reshape(height,width,4); frame=av.VideoFrame.from_ndarray(pixels,format='rgba'); frame.pts=n
                            for packet in stream.encode(frame):movie.mux(packet)
                            n+=1
                            if n%15==0 and progress:progress(0,f'Preparing face/background frames · {n/fps:.1f}s / {item.source_duration:.1f}s')
                        for packet in stream.encode():movie.mux(packet)
                    if decoder.wait(timeout=15) or n==0:raise RuntimeError('Could not decode this clip for effect rendering.')
                finally:
                    if decoder.poll() is None:stop(decoder,job)
                    job.close(); decoder.stdout.close()
            check_cancel(cancel); pending.replace(target)
        result[item.id]=str(target)
    return result
