"""Shared native title painting and lossless animated overlay preparation."""
import copy,hashlib,json,math,os,tempfile
from contextlib import contextmanager
from threading import RLock
from pathlib import Path
from fractions import Fraction
from PySide6.QtCore import QRectF,Qt,QPointF
from PySide6.QtGui import QImage,QPainter,QTransform

_render_lock=RLock()

@contextmanager
def prepared(project,progress,cancel):
    # Serialize native preparation/consumption so cache eviction cannot remove
    # an overlay another export is still reading. Ordinary exports do not wait.
    if not any(required(i) for i in project.timeline):
        yield project; return
    with _render_lock:
        try:yield prepare(project,progress,cancel)
        finally:
            from .config import CACHE_DIR
            prune(CACHE_DIR/'motion-renders',set())

def prune(directory,used):
    files=[]
    for path in directory.glob('*.mkv'):
        try:
            if path.is_symlink():continue
            stat=path.stat(); files.append((stat.st_mtime,stat.st_size,path))
        except OSError:continue
    total=sum(size for _,size,_ in files)
    for _,size,path in sorted(files):
        if total<=1024**3:break
        if str(path) not in used:
            try:path.unlink(missing_ok=True); total-=size
            except OSError:continue

def draw_title(painter,project,item,rect,at):
    from .keyframes import evaluated
    from .model import Caption,Transform
    from .visuals import draw_caption
    from .title_fades import opacity
    item=evaluated(item,at-item.start); style=copy.deepcopy(item.title_style)
    style.position_x+=item.transform.x-Transform().x; style.position_y+=item.transform.y-Transform().y
    style.zoom_x*=item.transform.scale; style.zoom_y*=item.transform.effective_scale_y
    caption=Caption(item.id,item.start,item.start+item.duration,item.title_text,style,False,True)
    pivot=QPointF(rect.left()+style.position_x*rect.width(),rect.top()+style.position_y*rect.height())
    transform=QTransform(); transform.translate(pivot.x(),pivot.y()); transform.rotate(item.transform.rotation); transform.translate(-pivot.x(),-pivot.y())
    painter.save()
    try:
        painter.setTransform(transform,True); painter.setOpacity(painter.opacity()*opacity(item,at))
        return transform.mapRect(draw_caption(painter,project,caption,rect))
    finally:painter.restore()

def required(item):
    from .model import Transform
    return item.role in ('title','graphic') and (bool(item.keyframes) or item.graphic_type.lower() in ('motion','motion composition') or item.role=='title' and item.transform!=Transform())

def frame(project,item,t,size=None):
    from .graphics import draw_graphic
    width,height=size or (project.settings.width,project.settings.height)
    image=QImage(width,height,QImage.Format_RGBA8888); image.fill(Qt.transparent)
    painter=QPainter(image); painter.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing|QPainter.SmoothPixmapTransform)
    context=copy.copy(project); context.playhead=item.start+t
    try:
        rect=QRectF(0,0,image.width(),image.height())
        if item.role=='title':draw_title(painter,context,item,rect,context.playhead)
        else:draw_graphic(painter,context,item,rect,context.playhead)
    finally:painter.end()
    return image

def prepare(project,progress,cancel):
    items=[i for i in project.timeline if required(i) and not i.muted and project.track_states.get(i.track,{}).get('visible',True)]
    if not items:return project
    import av,numpy as np,shutil
    from dataclasses import asdict
    from .config import CACHE_DIR
    from .model import MediaItem,Transform,Crop
    stage=copy.deepcopy(project); directory=CACHE_DIR/'motion-renders'; directory.mkdir(parents=True,exist_ok=True)
    fps=project.settings.fps
    def check():
        if cancel and cancel.is_set():raise RuntimeError('Export cancelled. Native animation preparation stopped safely.')
    for item in items:
        check(); assets=[]
        for node in item.graphic_data.get('scene',{}).get('nodes',[]):
            if node.get('kind')=='image':
                source=Path(node.get('source',''))
                if not source.is_file():raise ValueError('Motion image is missing: '+str(source))
                stat=source.stat(); assets.append((str(source),stat.st_size,stat.st_mtime_ns))
        key=hashlib.sha256(json.dumps([3,asdict(item),asdict(project.settings),assets],sort_keys=True).encode()).hexdigest()
        target=directory/(key+'.mkv')
        if not target.is_file():
            if shutil.disk_usage(directory).free<256*1024**2:raise RuntimeError('Free at least 256 MB for native animation preparation')
            count=math.ceil(item.duration*fps-1e-7)
            with tempfile.TemporaryDirectory(prefix='pending-',dir=directory) as temp:
                pending=Path(temp)/'animation.mkv'
                with av.open(str(pending),'w') as movie:
                    stream=movie.add_stream('ffv1',rate=Fraction(str(fps))); stream.width=project.settings.width; stream.height=project.settings.height; stream.pix_fmt='bgra'; stream.options={'level':'3'}
                    for n in range(count):
                        check(); image=frame(project,item,n/fps)
                        pixels=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()
                        video=av.VideoFrame.from_ndarray(pixels,format='rgba'); video.pts=n
                        for packet in stream.encode(video):movie.mux(packet)
                        if n%15==0 and progress:progress(0,f'Preparing motion graphics · {n/fps:.1f}s / {item.duration:.1f}s')
                        if n%60==0 and shutil.disk_usage(directory).free<128*1024**2:raise RuntimeError('Not enough space to continue native animation preparation')
                    for packet in stream.encode():movie.mux(packet)
                check(); pending.replace(target)
        current=stage.item_by_id(item.id)
        media=MediaItem('__native_'+item.id,str(target),'video','Rendered '+(item.title_text or item.graphic_type),item.duration,project.settings.width,project.settings.height,fps)
        media.has_alpha=True; stage.media.append(media)
        current.role='normal'; current.media_id=media.id; current.keyframes={}; current.transform=Transform(x=.5,y=.5)
        current.crop=Crop(); current.in_point=0.; current.speed=1.; current.opacity=100.; current.fade_in=current.fade_out=0.; current.effects=[]
    # Source documents never reference these regenerable files. Bound stale cache
    # retention, but keep all assets of the current export until it completes.
    used={m.path for m in stage.media if m.id.startswith('__native_')}
    prune(directory,used)
    return stage
