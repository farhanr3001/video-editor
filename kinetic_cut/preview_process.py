"""One readonly composition child with a bounded request/response mailbox.

Bytes cross the pipe only on a retained bridge worker. Neither a GUI widget nor
a decoder-owned frame crosses process boundaries. EOF retires the helper if the
editor exits unexpectedly; normal close terminates/reaps only this owned child.
"""
import threading
import os
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage


def pack(image):
    return (image.width(),image.height(),image.bytesPerLine(),image.format().value,
            image.devicePixelRatioF(),bytes(image.constBits()))


def unpack(data):
    width,height,stride,format,scale,pixels=data
    image=QImage(pixels,width,height,stride,QImage.Format(format)).copy()
    image.setDevicePixelRatio(scale)
    return image


class SharedImages:
    """Single-flight reusable mappings; only the parent allocates/owns them."""
    def __init__(self):self.slots={}; self.identities={}
    def reserve(self,key,size):
        from multiprocessing.shared_memory import SharedMemory
        slot=self.slots.get(key)
        if slot is None or slot.size<size:
            total=sum(v.size for k,v in self.slots.items() if k!=key)
            if total+size>512*1024**2:raise MemoryError('Preview transfer budget exceeded')
            if slot:slot.close(); slot.unlink()
            slot=SharedMemory(create=True,size=size); self.slots[key]=slot
            self.identities.pop(key,None)
        return slot
    def write(self,key,image):
        slot=self.reserve(key,image.sizeInBytes())
        identity=(image.text('_kinetic_source_frame') or image.cacheKey(),image.sizeInBytes(),image.width(),image.height(),image.format().value)
        if self.identities.get(key)!=identity:
            slot.buf[:image.sizeInBytes()]=image.constBits(); self.identities[key]=identity
        return (image.width(),image.height(),image.bytesPerLine(),image.format().value,image.devicePixelRatioF(),slot.name,image.sizeInBytes())
    def close(self):
        for slot in self.slots.values():
            slot.close(); slot.unlink()
        self.slots.clear()
        self.identities.clear()


def mapped_image(data,mappings):
    from multiprocessing.shared_memory import SharedMemory
    width,height,stride,format,scale,name,count=data
    if name not in mappings:mappings[name]=SharedMemory(name=name)
    image=QImage(mappings[name].buf[:count],width,height,stride,QImage.Format(format))
    image.setDevicePixelRatio(scale)
    return image


def child(connection):
    from .process import install_desktop_process_policy
    install_desktop_process_policy()
    from PySide6.QtGui import QGuiApplication
    app=QGuiApplication([])
    from .caption_fonts import load_fonts
    load_fonts()
    from .model import Project
    from .preview_compositor import SceneContext,render
    previous=None; context=None; mappings={}
    try:
        while True:
            try:payload=connection.recv()
            except EOFError:break
            try:
                project,frames,active,fallback,interactive,raster,rect,size,scale,output,draw_captions=payload
                # Retain read-only scene assets and filter caches between frames.
                # Reconstructing the project and reloading stills on every tick
                # defeats worker composition on image-heavy motion scenes.
                at=project.pop('playhead',0.)
                signature=(project,interactive,raster,draw_captions)
                if context:
                    # Bound renderer methods form a reference cycle. Release
                    # mapped QImage views before replacing that context, rather
                    # than waiting for Python's cyclic collector.
                    context.frames.clear(); context.fallback_frames.clear()
                    context.crop_cache.clear(); context.effect_cache.clear()
                if signature!=previous:
                    context=SceneContext(Project.from_dict(project),{}, {}, {},interactive,raster,draw_captions)
                    previous=signature
                context.project.playhead=at
                # Mapped pixels are read-only during this single-flight render.
                # Clear cached views before replacing/reusing any source slot.
                context.frames={}; context.fallback_frames={}
                context.crop_cache.clear(); context.effect_cache.clear()
                if output:
                    used={v[5] for v in (*frames.values(),*fallback.values())}|{output[5]}
                    for name in list(mappings):
                        if name not in used:
                            mappings[name].close(); mappings.pop(name)
                decode=(lambda v:mapped_image(v,mappings)) if output else unpack
                context.frames={k:decode(v) for k,v in frames.items()}
                context.active_frames=active
                context.fallback_frames={k:decode(v) for k,v in fallback.items()}
                image,bounds,notice=render(context,QRectF(*rect),size,scale)
                if output:
                    mapped_image(output,mappings)
                    mappings[output[5]].buf[:image.sizeInBytes()]=image.constBits()
                connection.send(('ok',output or pack(image),[(k,(r.x(),r.y(),r.width(),r.height())) for k,r in bounds.items()],notice))
            except Exception:
                import traceback
                connection.send(('error',traceback.format_exc()))
    finally:
        if context:
            context.frames.clear(); context.fallback_frames.clear()
            context.crop_cache.clear(); context.effect_cache.clear()
        context=None
        for mapping in mappings.values():mapping.close()
        connection.close()
        app.quit()


class RendererProcess:
    def __init__(self):
        self.lock=threading.Lock(); self.closed=False; self.process=None; self.connection=None
        self.shared=SharedImages() if os.name=='nt' and os.environ.get('KINETIC_SHARED_PREVIEW','1')=='1' else None
    def render(self,context,rect,size,scale):
        with self.lock:
            if self.closed:raise InterruptedError('Preview renderer closed')
            if self.process is None:
                import multiprocessing
                from .process import install_desktop_process_policy
                install_desktop_process_policy()
                spawn=multiprocessing.get_context('spawn')
                parent,remote=spawn.Pipe()
                process=spawn.Process(target=child,args=(remote,),daemon=True,name='KineticCut-composition')
                self.connection=parent; self.process=process
                process.start(); remote.close()
            if self.closed:
                if self.process.is_alive():self.process.terminate()
                self.process.join(2)
                raise InterruptedError('Preview renderer closed')
            output=None
            if self.shared:
                frames={k:self.shared.write(('frame',n),v) for n,(k,v) in enumerate(context.frames.items())}
                fallback={k:self.shared.write(('fallback',n),v) for n,(k,v) in enumerate(context.fallback_frames.items())}
                image=QImage(size[0],size[1],QImage.Format_ARGB32_Premultiplied); image.setDevicePixelRatio(scale)
                slot=self.shared.reserve('output',image.sizeInBytes())
                output=(size[0],size[1],image.bytesPerLine(),image.format().value,scale,slot.name,image.sizeInBytes())
            else:
                frames={k:pack(v) for k,v in context.frames.items()}
                fallback={k:pack(v) for k,v in context.fallback_frames.items()}
            payload=(context.project.to_dict(),frames,context.active_frames,fallback,
                     context.interactive,context.raster_scale,(rect.x(),rect.y(),rect.width(),rect.height()),size,scale,output,context.draw_captions)
            self.connection.send(payload)
            # Bounded wait with an explicit failure rather than a permanently
            # stale preview if a device/library becomes unresponsive.
            if not self.connection.poll(8):raise TimeoutError('Composition helper did not respond')
            answer=self.connection.recv()
            if answer[0]!='ok':raise RuntimeError(answer[1])
            if output:
                data=answer[1]; slot=self.shared.slots['output']
                result=QImage(slot.buf[:data[6]],data[0],data[1],data[2],QImage.Format(data[3])).copy(); result.setDevicePixelRatio(data[4])
            else:result=unpack(answer[1])
            return result,{k:QRectF(*r) for k,r in answer[2]},answer[3]
    def close(self):
        self.closed=True
        process=self.process
        if process is not None:
            try:
                if process.is_alive():process.terminate()
            except (ValueError,AssertionError):pass
            # Reap off the GUI thread. A bridge in recv() is released by EOF.
            def reap():
                try:process.join(2)
                except (ValueError,AssertionError):pass
                with self.lock:
                    if self.shared:self.shared.close()
            threading.Thread(target=reap,name='preview-reap',daemon=True).start()
        if self.connection:
            try:self.connection.close()
            except OSError:pass
