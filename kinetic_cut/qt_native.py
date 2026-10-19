"""Opaque native Qt ownership. All media commands run in C++, off the GUI."""
import ctypes as C
from pathlib import Path
import sys
import weakref
from PySide6.QtCore import QObject,Signal,Slot,QTimer,qVersion
from PySide6.QtMultimedia import QMediaPlayer


def load():
    if sys.platform!='win32':return None
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
    path=root/'assets/native/qt_media_engine.dll'
    if not path.is_file():return None
    from PySide6 import QtQuick  # Load matching dependent Qt DLLs before CDLL.
    lib=C.CDLL(str(path));lib.kc_qt_abi.restype=C.c_uint
    lib.kc_engine_abi.restype=C.c_uint
    if lib.kc_engine_abi()!=3:raise RuntimeError('Native media engine interface does not match this application')
    major,minor,patch=map(int,qVersion().split('.'))
    if lib.kc_qt_abi()!=(major<<16|minor<<8|patch):raise RuntimeError('Native media engine Qt ABI does not match the bundled Qt')
    signatures={
        'kc_surface_create':(C.c_void_p,[C.c_void_p]),'kc_surface_read':(None,[C.c_void_p,C.POINTER(C.c_double)]),'kc_surface_release':(None,[C.c_void_p]),
        'kc_player_create':(C.c_void_p,[C.c_void_p,C.c_wchar_p]),'kc_player_command':(None,[C.c_void_p,C.c_int,C.c_double]),
        'kc_player_read':(None,[C.c_void_p,C.POINTER(C.c_double)]),'kc_player_stop':(None,[C.c_void_p]),'kc_player_release':(None,[C.c_void_p]),
        'kc_player_error':(None,[C.c_void_p,C.c_char_p,C.c_uint]),'kc_players_active':(C.c_uint,[])}
    signatures.update(kc_ruler_create=(C.c_void_p,[C.c_void_p]),kc_ruler_view=(None,[C.c_void_p,C.c_double,C.c_double,C.c_double,C.c_double,C.c_double,C.c_double,C.c_char_p,C.c_uint,C.c_uint]))
    signatures.update(kc_surface_watch=(C.c_void_p,[C.c_void_p,C.c_void_p]),kc_probe_active=(None,[C.c_void_p,C.c_bool]),kc_probe_release=(None,[C.c_void_p]))
    signatures.update(kc_clips_create=(C.c_void_p,[C.c_void_p,C.c_char_p]),kc_clips_view=(None,[C.c_void_p,C.c_double,C.c_double,C.c_double,C.c_double]),kc_clips_set=(None,[C.c_void_p,C.c_void_p,C.c_uint]),kc_clips_image=(None,[C.c_void_p,C.c_uint64,C.c_void_p]),kc_clips_reset=(None,[C.c_void_p]))
    for name,(result,args) in signatures.items():getattr(lib,name).restype=result;getattr(lib,name).argtypes=args
    return lib


try:LIB=load()
except (OSError,RuntimeError,AttributeError):
    import logging
    logging.exception('Native Qt media engine unavailable')
    LIB=None


_retiring=set()
_retire_timer=None


def active():
    peers=sys.modules.get('kinetic_cut.gpu_preview_process')
    return (LIB.kc_players_active() if LIB else 0)+(sum(peer.active for peer in tuple(peers.PEERS)) if peers else 0)


def reap():
    for engine in tuple(_retiring):
        if engine.finished:
            _retiring.discard(engine);engine.release()
    if not _retiring and _retire_timer:_retire_timer.stop()


class Engine:
    def __init__(self,sink,path):
        import shiboken6
        self.handle=LIB.kc_player_create(shiboken6.getCppPointer(sink)[0],str(path))
        if not self.handle:raise RuntimeError('Could not create native video engine')
        self.finalizer=weakref.finalize(self,LIB.kc_player_release,self.handle)
        self.buffer=(C.c_double*8)();self.closed=False
    def read(self):
        if self.handle:LIB.kc_player_read(self.handle,self.buffer)
        return self.buffer
    @property
    def finished(self):return not self.handle or bool(self.read()[7])
    def command(self,kind,value):
        if self.handle and not self.closed:LIB.kc_player_command(self.handle,kind,value)
    def close(self):
        global _retire_timer
        if self.closed:return
        self.closed=True;LIB.kc_player_stop(self.handle);_retiring.add(self)
        if _retire_timer is None:
            from PySide6.QtCore import QCoreApplication
            _retire_timer=QTimer(QCoreApplication.instance());_retire_timer.setInterval(16);_retire_timer.timeout.connect(reap)
        _retire_timer.start()
    def release(self):
        if self.handle:self.finalizer();self.handle=None


class NativeVideoPlayer(QObject):
    mediaStatusChanged=Signal(object)
    def __init__(self,transport,sink,path):
        super().__init__(transport);self.engine=Engine(sink,path);self._loaded=0;self._status=None;self._rate=1.
        self._transport_key=None
    def poll(self):
        state=self.engine.read()
        if int(state[4])!=self._loaded:
            self._loaded=int(state[4]);self.mediaStatusChanged.emit(QMediaPlayer.LoadedMedia)
        status=QMediaPlayer.MediaStatus(int(state[1]))
        if status!=self._status:self._status=status;self.mediaStatusChanged.emit(status)
    def mediaStatus(self):return QMediaPlayer.MediaStatus(int(self.engine.read()[1]))
    def playbackState(self):return QMediaPlayer.PlaybackState(int(self.engine.read()[2]))
    def position(self):return round(self.engine.read()[0])
    def setPosition(self,value):self.engine.command(0,value)
    def setPlaybackRate(self,value):
        if value!=self._rate:self._rate=value;self.engine.command(2,value)
    @Slot()
    def play(self):self.engine.command(1,QMediaPlayer.PlayingState.value)
    @Slot()
    def pause(self):self.engine.command(1,QMediaPlayer.PausedState.value)
    @Slot()
    def stop(self):self.engine.close()
    def errorString(self):
        buffer=C.create_string_buffer(2048)
        if self.engine.handle:LIB.kc_player_error(self.engine.handle,buffer,len(buffer))
        return buffer.value.decode('utf-8',errors='replace')


class RenderTiming:
    def __init__(self,window):
        import shiboken6
        self.handle=LIB.kc_surface_create(shiboken6.getCppPointer(window)[0])
        self.finalizer=weakref.finalize(self,LIB.kc_surface_release,self.handle)
        self.buffer=(C.c_double*9)()
    def read(self):
        LIB.kc_surface_read(self.handle,self.buffer)
        frames,record,synchronize,submit,gpu,replaced,observed,deferred,in_flight=self.buffer
        return dict(rendered_frames=int(frames),render_command_ms=record,scene_synchronize_ms=synchronize,
                    frame_submit_ms=submit,gpu_composition_ms=gpu if gpu>=0 else None,
                    source_frames_coalesced_between_render_syncs=int(replaced),source_frames_observed=int(observed),
                    deferred_scene_sync_requests=int(deferred),render_in_flight=bool(in_flight))
    def watch(self,sink):return FrameProbe(self,sink)


class FrameProbe:
    def __init__(self,surface,sink):
        import shiboken6
        self.handle=LIB.kc_surface_watch(surface.handle,shiboken6.getCppPointer(sink)[0])
        self.finalizer=weakref.finalize(self,LIB.kc_probe_release,self.handle)
    def active(self,value):
        if self.handle:LIB.kc_probe_active(self.handle,bool(value))
    def close(self):
        if self.handle:self.finalizer();self.handle=None


class NativeRuler:
    def __init__(self,parent):
        import shiboken6
        self.handle=LIB.kc_ruler_create(shiboken6.getCppPointer(parent)[0])
    def update(self,width,pps,offset,at,body_x,body_y,stamp,foreground,background):
        from PySide6.QtGui import QColor
        LIB.kc_ruler_view(self.handle,width,pps,offset,at,body_x,body_y,stamp.encode('utf-8'),QColor(foreground).rgba(),QColor(background).rgba())


class ClipInput(C.Structure):
    _fields_=[(name,C.c_double) for name in ('start','duration','y','height','top','bottom','in_point','speed','gain','fade_in','fade_out','aspect')]+[('wave',C.c_uint64),('wave_count',C.c_double),('wave_resolution',C.c_double),('color',C.c_uint),('flags',C.c_uint),('label',C.c_char_p),('thumbnail',C.c_char_p)]


class ClipProxy:
    def __init__(self):self.values={};self.visible=False;self.z=0
    def setProperty(self,key,value):self.values[key]=value
    def setVisible(self,value):self.visible=value
    def setZ(self,value):self.z=value
    def deleteLater(self):self.values.clear()


class NativeClips:
    def __init__(self,parent):
        import shiboken6
        from .icons import resource_path
        self.handle=LIB.kc_clips_create(shiboken6.getCppPointer(parent)[0],str(resource_path('assets','shaders')).encode('utf-8'))
        self.count=0
    def view(self,width,height,pps,offset):LIB.kc_clips_view(self.handle,width,height,pps,offset)
    def reset(self):
        LIB.kc_clips_reset(self.handle)
        self.link_icon()
    def link_icon(self):
        import shiboken6
        from .icons import lucide_icon
        image=lucide_icon('link','@on_dark',13).pixmap(13,13).toImage()
        LIB.kc_clips_image(self.handle,0xffffffffffffffff,shiboken6.getCppPointer(image)[0])
    def image(self,url,image):
        import shiboken6
        LIB.kc_clips_image(self.handle,hash(url)&0xffffffffffffffff,shiboken6.getCppPointer(image)[0])
    def publish(self,proxies):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QColor
        records=[];strings=[]
        for proxy in sorted((v for v in proxies if v.visible),key=lambda v:v.z):
            v=proxy.values
            flags=sum(bit for bit,name in ((1,'audio'),(2,'selected'),(4,'hovered'),(8,'ghost'),(32,'retime'),(64,'linked'),(128,'hasEffects'),(256,'caption'),(1024,'textItem')) if v.get(name))
            if v.get('effectLabel'):flags|=512
            name=str(v.get('label','')).encode('utf-8');path=QUrl(v.get('thumbnail','')).toLocalFile().encode('utf-8');strings.extend((name,path))
            records.append(ClipInput(v.get('startTime',0),v.get('duration',1),v.get('laneY',0),v.get('laneHeight',60),v.get('sectionTop',0),v.get('sectionBottom',1000),v.get('sourceIn',0),v.get('sourceSpeed',1),v.get('gain',1),v.get('fadeIn',0),v.get('fadeOut',0),v.get('thumbnailAspect',16/9),hash(v.get('waveform',''))&0xffffffffffffffff,v.get('waveCount',0),v.get('waveResolution',.001),QColor(v.get('color','#3c6c90')).rgba(),flags,name,path))
        self.count=len(records);array=(ClipInput*len(records))(*records);LIB.kc_clips_set(self.handle,array,len(records))
