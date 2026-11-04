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
    spec=json.loads(Path(path).read_text(encoding='utf-8'))
    # Streams with native graphics keep the real platform on Windows so Qt Quick renders motion graphics with Direct3D 11.
    os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' and (spec.get('native_animation') or spec.get('gpu_transition')) else os.environ.get('QT_QPA_PLATFORM','offscreen') if os.name!='nt' else 'offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QRectF,Qt
    from PySide6.QtGui import QImage,QPainter
    from .model import Project
    from .preview_compositor import SceneContext,render
    from .gpu_export_decode import Source
    if spec.get('gpu_transition'):
        app=QApplication.instance() or QApplication([])
        from .gpu_transition_stage import serve
        return serve(spec)
    project=Project.from_dict(spec['project']);item=project.timeline[0];media=project.media_by_id(item.media_id)
    app=QApplication.instance() or QApplication([]);reader=None;stage=None
    from .transitions import Transition
    transitions=[dict(x,trans=Transition.from_dict(x['transition'])) for x in spec.get('graphic_transitions',[])]
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
                from .motion_gpu import is_motion
                image=QImage(width,height,QImage.Format_RGBA8888);image.fill(Qt.transparent)
                g=spec['first']+n;active=next((x for x in transitions if x['first']<=g<x['last']),None)
                if active is not None:
                    # A transition between two motion graphics is composited here on the GPU with the preview's shader, so the
                    # native exporter never has to pre-render it.
                    from .animated_transitions import descriptor
                    from .transitions import apply_easing
                    left=project.item_by_id(active['transition']['left_item_id']);right=project.item_by_id(active['transition']['right_item_id'])
                    trans=active['trans'];data=descriptor(trans)
                    if stage is None:
                        from .motion_gpu_render import MotionStage
                        stage=MotionStage(width,height)
                    clamp=lambda i:min(max(at,i.start),i.start+i.duration-1/fps)-i.start
                    image=stage.render_transition(left,right,clamp(left),clamp(right),apply_easing(trans.progress(at),data['easing']),data['mode'],data['params'],project)
                    image=image.convertToFormat(QImage.Format_RGBA8888);write_pixels(bytes(image.constBits()));continue
                painter=QPainter(image);gpu_items=[]
                try:
                    for graphic in project.timeline:
                        if graphic.start<=at<graphic.start+graphic.duration:
                            local=(spec['first']+n-math.ceil(graphic.start*fps-1e-7))/fps
                            # Motion compositions are drawn by the GPU (same QML as the preview); only other graphics use the painter.
                            if is_motion(graphic):gpu_items.append((graphic,local));continue
                            painter.drawImage(0,0,frame(project,graphic,local))
                finally:painter.end()
                if gpu_items:
                    if stage is None:
                        from .motion_gpu_render import MotionStage
                        stage=MotionStage(width,height)
                    clock=dict((g.id,l) for g,l in gpu_items)
                    layer=stage.render([g for g,_ in gpu_items],project,lambda g:clock[g.id])
                    painter=QPainter(image);painter.drawImage(0,0,layer);painter.end()
            else:image,_,_=render(context,QRectF(0,0,width,height),(width,height),1.)
            image=image.convertToFormat(QImage.Format_RGBA8888);write_pixels(bytes(image.constBits()))
    finally:
        if reader:reader.close()
        if stage:stage.close()
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
