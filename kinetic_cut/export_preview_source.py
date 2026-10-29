"""Owned lossless preview raster producer for effects lacking a native shader."""
import os,sys,json,math
from pathlib import Path

def write_pixels(data):
    if os.name!='nt':
        view=memoryview(data)
        while view:view=view[os.write(1,view):]
        return
    import ctypes as c
    from ctypes import wintypes as w
    api=c.WinDLL('kernel32',use_last_error=True);api.GetStdHandle.argtypes=[w.DWORD];api.GetStdHandle.restype=w.HANDLE
    api.WriteFile.argtypes=[w.HANDLE,c.c_void_p,w.DWORD,c.POINTER(w.DWORD),c.c_void_p]
    handle=api.GetStdHandle(w.DWORD(-11));payload=c.create_string_buffer(data);offset=0
    while offset<len(data):
        done=w.DWORD()
        if not api.WriteFile(handle,c.byref(payload,offset),min(len(data)-offset,0x7fffffff),c.byref(done),None) or not done.value:raise BrokenPipeError('Preview effect consumer closed')
        offset+=done.value

def _worker(path):
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QRectF,Qt
    from PySide6.QtGui import QImage,QPainter
    from .model import Project
    from .preview_compositor import SceneContext,render
    from .gpu_export_decode import Source
    spec=json.loads(Path(path).read_text(encoding='utf-8'));project=Project.from_dict(spec['project']);item=project.timeline[0];media=project.media_by_id(item.media_id)
    app=QApplication.instance() or QApplication([]);reader=None
    from .caption_fonts import load_fonts
    load_fonts()
    context=SceneContext(project,{},{},{},False,1.,draw_captions=False);context.transparent=True;context.strict_export=bool(spec.get('strict_effects'))
    width,height=project.settings.width,project.settings.height;fps=project.settings.fps
    try:
        if media and media.kind=='video':reader=Source(media.path,item.source_time(spec['first']/fps))
        for n in spec.get('sample_frames',range(spec['frames'])):
            at=(spec['first']+n)/fps;project.playhead=at
            if spec.get('strict_effects'):
                from .vision_effects import active,valid_effect,mask_image,frame_index
                from .tracking_effect import render_effects,export_error
                for effect in active(item):
                    if not valid_effect(effect,media,item):raise ValueError('Face/background analysis is missing or changed; re-analyse before exporting.')
                    if effect['name']=='Remove Person Background' and mask_image(effect['analysis']['root'],frame_index(effect['analysis'],item.source_time(at))).isNull():raise ValueError('Background analysis mask is missing; re-analyse before exporting.')
                for effect in render_effects(item):
                    error=export_error(effect,media,item)
                    if error:raise ValueError(error)
            if reader:
                data=reader.frame(item.source_time(at));h,w=data.shape[:2];context.frames[item.id]=QImage(data.data,w,h,w*4,QImage.Format_RGBA8888).copy();context.active_frames[item.id]=item.id
            if spec.get('native_animation'):
                from .native_animation import frame
                image=QImage(width,height,QImage.Format_RGBA8888);image.fill(Qt.transparent)
                painter=QPainter(image)
                try:
                    for graphic in project.timeline:
                        if graphic.start<=at<graphic.start+graphic.duration:
                            local=(spec['first']+n-math.ceil(graphic.start*fps-1e-7))/fps
                            painter.drawImage(0,0,frame(project,graphic,local))
                finally:painter.end()
            else:image,_,_=render(context,QRectF(0,0,width,height),(width,height),1.)
            image=image.convertToFormat(QImage.Format_RGBA8888);write_pixels(bytes(image.constBits()))
    finally:
        if reader:reader.close()
    return 0


def worker(path):
    """Return failure through the pipe protocol, never a bootloader dialog."""
    try:return _worker(path)
    except Exception:
        import traceback
        try:
            with Path(path).with_suffix('.producer-error.log').open('a',encoding='utf-8') as log:traceback.print_exc(file=log)
        except OSError:pass
        return 1
