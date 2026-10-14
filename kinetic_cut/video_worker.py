"""Worker-owned libav decoder. GUI receives detached images, never native frames.

The existing timeline clock/audio transport remains authoritative. Commands are
coalesced; each stream owns its container, iterator and conversion on one worker.
"""
import os
import time
import threading
from collections import deque
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaPlayer


def enabled():
    return os.environ.get('KINETIC_WORKER_PREVIEW', '1') == '1'


def enabled_for(window, media_id):
    from .playback_config import MODES
    # Explicit hardware decoding retains Qt's device-owned presentation path.
    # Downloading D3D surfaces through libav was slower in the measured prototype.
    return (enabled() and hasattr(window,'start_worker')
            and window.settings.get('playback_decoder',MODES[0])!=MODES[1]
            and os.environ.get('QT_FFMPEG_DECODING_HW_DEVICE_TYPES') in (None,',')
            and media_id not in getattr(getattr(window,'transport',None),'_worker_failed_media',set()))


def shared_file(path):
    if os.name != 'nt':
        return open(path, 'rb')
    import ctypes, msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    handle = create(os.path.abspath(path), 0x80000000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close = kernel.CloseHandle; close.argtypes = [wintypes.HANDLE]; close(handle)
        raise
    return os.fdopen(fd, 'rb')


class CpuFrame:
    def __init__(self, image=None, start=0., end=0., generation=0):
        self.image = image or QImage()
        self.start = round(start * 1_000_000)
        self.end = round(end * 1_000_000)
        self.generation = generation
    def isValid(self): return not self.image.isNull()
    def startTime(self): return self.start
    def endTime(self): return self.end
    def toImage(self): return QImage(self.image)


class VideoEngine:
    """Bounded command mailbox and source-frame window; no Qt objects owned here."""
    def __init__(self, path, hardware=False):
        self.path = path; self.hardware = hardware
        self.condition = threading.Condition()
        self.closed = False; self.loaded = False; self.error = ''
        self.playing = False; self.rate = 1.; self.origin = 0.; self.started = time.monotonic()
        self.generation = 0; self.latest = CpuFrame(); self.last_request = -1
        self.cache = deque(); self.cache_bytes = 0
        self.hardware_active = False; self.decoded = 0; self.cache_hits = 0
        try:
            info=os.stat(path); self.source_identity=(os.path.abspath(path),info.st_size,info.st_mtime_ns)
        except OSError:self.source_identity=(os.path.abspath(path),None)

    def position(self):
        return max(0., self.origin + ((time.monotonic()-self.started)*self.rate if self.playing else 0.))

    def command(self, position=None, playing=None, rate=None):
        with self.condition:
            now = time.monotonic(); current = self.position()
            if position is not None:
                current = max(0., position); self.generation += 1
            self.origin = current; self.started = now
            if playing is not None: self.playing = playing
            if rate is not None: self.rate = rate
            self.condition.notify_all()

    def stop(self):
        with self.condition:
            self.closed = True; self.condition.notify_all()

    def frame(self):
        with self.condition:
            return self.latest

    def run(self):
        import av
        try:
            with shared_file(self.path) as source:
                accel = None
                if self.hardware:
                    from av.codec.hwaccel import HWAccel
                    accel = HWAccel('d3d11va', allow_software_fallback=True)
                with av.open(source, hwaccel=accel) as container:
                    stream = container.streams.video[0]
                    stream.codec_context.thread_count = 2
                    stream.thread_type = 'AUTO'
                    self.hardware_active = stream.codec_context.is_hwaccel
                    fps = float(stream.average_rate or 30)
                    offset = float((stream.start_time or 0) * stream.time_base)
                    step = 1 / max(1, fps)
                    iterator = None; current = -1.; eof = False
                    with self.condition: self.loaded = True
                    while True:
                        with self.condition:
                            if self.closed: break
                            target = self.position(); generation = self.generation
                            if not self.playing and generation == self.last_request:
                                self.condition.wait(.1); continue
                        cached = next((f for f in reversed(self.cache)
                                       if f.startTime()/1e6 <= target + .000001 < f.endTime()/1e6), None)
                        if cached:
                            result = CpuFrame(cached.image, cached.start/1e6, cached.end/1e6, generation)
                            self.cache_hits += 1
                        else:
                            if iterator is None or target < current - .000001 or target > current + .5 or eof:
                                container.seek(max(0, int((target+offset)/stream.time_base)), stream=stream, backward=True)
                                iterator = container.decode(stream); eof = False; current = -1.
                            result = None
                            for frame in iterator:
                                with self.condition:
                                    if self.closed or generation != self.generation: break
                                if frame.pts is None: continue
                                at = float(frame.pts * frame.time_base) - offset
                                length = float(frame.duration * frame.time_base) if frame.duration else step
                                end = at + max(.000001, length)
                                current = at
                                if end <= target + .000001: continue
                                pixels = frame.to_ndarray(format='rgba')
                                image = QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0], QImage.Format_RGBA8888).copy()
                                image.setText('_kinetic_source_frame',repr((self.source_identity,round(at*1e6),round(end*1e6))))
                                result = CpuFrame(image, at, end, generation); self.decoded += 1
                                self.cache.append(result); self.cache_bytes += image.sizeInBytes()
                                while len(self.cache)>32 or self.cache_bytes>64*1024**2:
                                    old=self.cache.popleft(); self.cache_bytes-=old.image.sizeInBytes()
                                break
                            else:
                                eof = True
                                if self.cache and target < self.cache[-1].end/1e6 + step:
                                    f=self.cache[-1]; result=CpuFrame(f.image,f.start/1e6,f.end/1e6,generation)
                        with self.condition:
                            if self.closed: break
                            if generation != self.generation: continue
                            if result is not None: self.latest = result
                            self.last_request = generation
                            # Wake promptly on seek/pause; no spin or unbounded frames.
                            remaining=step
                            if result is not None and self.playing:
                                remaining=((result.end/1e6-self.position()) if self.rate>=0 else
                                           (self.position()-result.start/1e6))/max(.1,abs(self.rate))
                            self.condition.wait(max(.001,min(.02,remaining)))
        except Exception as error:
            with self.condition: self.error = f'{type(error).__name__}: {error}'
        finally:
            self.cache.clear(); self.cache_bytes = 0


class WorkerVideoPlayer(QObject):
    mediaStatusChanged = Signal(object)
    def __init__(self, transport, path, hardware=False):
        super().__init__(transport)
        self.transport=transport
        self.engine = VideoEngine(path, hardware); self._reported = False
        self._frame_stamp = None
        from .ui import Worker
        worker = Worker(self.engine.run); worker.cancel_callback = self.engine.stop
        worker.maintenance = True; worker.preview_decoder=True; worker.pool = transport.video_pool
        transport.window.start_worker(worker)
    def mediaStatus(self):
        if self.engine.error: return QMediaPlayer.InvalidMedia
        return QMediaPlayer.BufferedMedia if self.engine.loaded else QMediaPlayer.LoadingMedia
    def playbackState(self):
        return QMediaPlayer.PlayingState if self.engine.playing else QMediaPlayer.PausedState
    def position(self): return round(self.engine.position()*1000)
    def setPosition(self, value): self.engine.command(position=value/1000)
    def setPlaybackRate(self, value):
        if value != self.engine.rate: self.engine.command(rate=value)
    @Slot()
    def play(self):
        # Qt needs muted playback to prime a paused seek. This worker decodes
        # the requested frame directly; advancing its clock would overwrite it
        # before the GUI can publish it, especially during long-GOP preroll.
        if self.transport.playing and not self.engine.playing:self.engine.command(playing=True)
    @Slot()
    def pause(self):
        if self.engine.playing: self.engine.command(playing=False)
    @Slot()
    def stop(self): self.engine.stop()
    def videoFrame(self):
        if self.engine.loaded and not self._reported:
            self._reported=True; self.mediaStatusChanged.emit(QMediaPlayer.LoadedMedia)
        frame=self.engine.frame()
        # Explicit seeks cannot publish an old generation even at an equal PTS.
        return frame if frame.generation==self.engine.generation else CpuFrame()
