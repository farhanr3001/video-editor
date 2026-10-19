"""Owned GPU renderer process and bounded control channel.

Only scene metadata crosses this channel during playback. Video textures stay
inside the renderer process; image transfer is an explicit capture operation.
The bridge is the sole owner of the parent pipe, including its closure.
"""
import atexit
import os
import threading
import time
import weakref
from collections import deque


PEERS=weakref.WeakSet()


class Peer:
    def __init__(self, desktop, host):
        self.desktop=desktop;self.host=host
        self.lock=threading.Lock();self.wake=threading.Event();self.stopping=threading.Event()
        self.process_lock=threading.Lock();self._stop_started=None
        self.latest=None;self.status=None;self.commands=deque();self.responses={}
        self.error='';self.pid=None;self.replaced=0;self.process=None
        self.exitcode=None;self.forced_shutdown=False
        self.thread=threading.Thread(target=self._run,name='gpu-preview-bridge',daemon=True)
        PEERS.add(self);self.thread.start()
        threading.Thread(target=self._supervise,name='gpu-preview-lifetime',daemon=True).start()

    def submit(self, scene):
        with self.lock:
            if self.stopping.is_set():return
            if self.latest is not None:
                self.replaced+=1;scene['force']|=self.latest.get('force',False)
            self.latest=scene
        self.wake.set()

    def command(self, command):
        with self.lock:
            if len(self.commands)>=8 or self.stopping.is_set():return False
            self.commands.append(command)
        self.wake.set();return True

    def take_status(self):
        with self.lock:
            result=self.status;self.status=None
        return result

    def take_response(self, serial):
        with self.lock:return self.responses.pop(serial,None)

    def close(self):
        if self._stop_started is None:self._stop_started=time.monotonic()
        self.stopping.set();self.wake.set()

    def _supervise(self):
        # A renderer stuck in a driver can also stop reading its control pipe.
        # Killing only our retained child unblocks the sole pipe owner's write;
        # never close that handle concurrently from the GUI or watchdog.
        while self.thread.is_alive():
            if self._stop_started is not None and time.monotonic()-self._stop_started>3:
                with self.process_lock:
                    process=self.process
                    if process and process.pid and process.is_alive():
                        self.forced_shutdown=True;process.terminate()
                return
            time.sleep(.05)

    @property
    def active(self):return self.thread.is_alive()

    def _run(self):
        import multiprocessing as mp
        connection=other=None;process=job=None
        try:
            connection,other=mp.get_context('spawn').Pipe()
            process=mp.get_context('spawn').Process(target=renderer,
                args=(other,self.desktop,self.host,os.getpid()),name='Kinetic GPU Preview')
            process.daemon=False
            with self.process_lock:self.process=process;process.start();self.pid=process.pid
            # multiprocessing registers a join hook lazily. Our retained
            # close/reap hook must run BEFORE that hook on exceptional exit.
            atexit.register(shutdown)
            other.close();other=None
            if os.name=='nt':
                from .export_process import ChildJob
                from types import SimpleNamespace
                job=ChildJob(SimpleNamespace(_handle=process._popen._handle))
            outstanding=False;sent=0.;published_signature=None;batch_signature=None
            while not self.stopping.is_set():
                # One acknowledged batch at a time. In particular, never
                # write a new scene while the child is returning a requested
                # large capture through this duplex pipe (cross-write deadlock).
                if not outstanding:
                    with self.lock:
                        scene=self.latest;self.latest=None
                        commands=list(self.commands);self.commands.clear()
                    if scene is not None or commands or time.monotonic()-sent>=.05:
                        if scene is not None:
                            batch_signature=scene['signature']
                            if batch_signature==published_signature:
                                scene=dict(scene,document=None)
                        connection.send(('batch',(scene,commands)));outstanding=True;sent=time.monotonic()
                while connection.poll(0):
                    kind,data=connection.recv()
                    with self.lock:
                        if kind=='status':self.status=data
                        elif kind=='error':self.error=data
                        elif kind=='capture':
                            self.responses[data[0]]=data[1]
                            while len(self.responses)>2:self.responses.pop(next(iter(self.responses)))
                        elif kind=='ack':outstanding=False;published_signature=batch_signature
                if not process.is_alive():
                    raise RuntimeError('GPU renderer exited with code '+str(process.exitcode))
                if outstanding and time.monotonic()-sent>8:
                    raise TimeoutError('GPU preview did not acknowledge its latest scene')
                self.wake.wait(.005);self.wake.clear()
        except Exception as error:
            if not self.stopping.is_set() and not self.error:self.error=str(error) or type(error).__name__
        finally:
            self.close()
            # Closing this one owned pipe also wakes an unresponsive renderer's
            # parent-lifetime/EOF guard. Never close it from the GUI thread.
            if connection:connection.close()
            if other:other.close()
            if process and process.pid:
                process.join(3)
                if process.is_alive() and job:self.forced_shutdown=True;job.close()
                if process.is_alive():self.forced_shutdown=True;process.terminate();process.join(3)
                if process.is_alive():self.forced_shutdown=True;process.kill();process.join(3)
                self.exitcode=process.exitcode
                with self.process_lock:
                    self.process=None;process.close()
            if job:job.close()


def shutdown():
    peers=list(PEERS)
    for peer in peers:peer.close()
    for peer in peers:peer.thread.join(10)


atexit.register(shutdown)


def desktop_name():
    import ctypes as C
    from ctypes import wintypes as W
    user=C.WinDLL('user32',use_last_error=True);kernel=C.WinDLL('kernel32')
    user.GetThreadDesktop.argtypes=[W.DWORD];user.GetThreadDesktop.restype=W.HANDLE
    user.GetUserObjectInformationW.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)]
    desktop=user.GetThreadDesktop(kernel.GetCurrentThreadId());buffer=C.create_unicode_buffer(512);size=W.DWORD()
    if not user.GetUserObjectInformationW(desktop,2,buffer,C.sizeof(buffer),C.byref(size)):
        raise C.WinError(C.get_last_error())
    return buffer.value


def renderer(connection, desktop, host, parent_pid):
    # A windowed frozen helper has no interactive error console. Return startup
    # failures to its owner rather than leaving an unseen bootloader error box.
    try:_renderer(connection,desktop,host,parent_pid)
    except Exception:
        import traceback
        try:connection.send(('error',traceback.format_exc()))
        except (OSError,EOFError):pass
        finally:connection.close()


def _renderer(connection, desktop, host, parent_pid):
    # Spawn does not inherit a private thread desktop. Select the parent's
    # desktop before constructing ANY Qt application/window. Never switch it.
    import ctypes as C
    from ctypes import wintypes as W
    import sys
    trace_path=os.environ.get('KINETIC_GPU_PROCESS_TRACE')
    if trace_path:
        import faulthandler
        trace=open(trace_path,'a',encoding='utf-8');faulthandler.enable(trace)
        faulthandler.dump_traceback_later(8,repeat=True,file=trace)
    user=C.WinDLL('user32',use_last_error=True);kernel=C.WinDLL('kernel32',use_last_error=True)
    user.OpenDesktopW.argtypes=[W.LPCWSTR,W.DWORD,W.BOOL,W.DWORD];user.OpenDesktopW.restype=W.HANDLE
    user.SetThreadDesktop.argtypes=[W.HANDLE];user.SetThreadDesktop.restype=W.BOOL
    handle=user.OpenDesktopW(desktop,0,False,0x00CF)
    if not handle:raise C.WinError(C.get_last_error())
    # Frozen bootloaders can own hidden windows before Python's target runs.
    # Leave an already-correct desktop alone; Windows rejects redundant switches
    # after those windows exist. A source diagnostic still switches when needed.
    if desktop_name()!=desktop and not user.SetThreadDesktop(handle):raise C.WinError(C.get_last_error())
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    parent=kernel.OpenProcess(0x100000,False,parent_pid)
    kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.WaitForSingleObject.restype=W.DWORD
    kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
    if not parent:raise RuntimeError('Preview owner no longer exists')
    # EOF and parent death are independent of Qt's renderer/event loop.
    exited=threading.Event()
    def watchdog():
        while not exited.wait(.2):
            if kernel.WaitForSingleObject(parent,0)==0:os._exit(0)
    threading.Thread(target=watchdog,name='preview-owner-watch',daemon=True).start()
    os.environ['KINETIC_GPU_RENDERER_CHILD']='1'
    from .process import install_desktop_process_policy
    install_desktop_process_policy()
    from .playback_config import configure
    configure({})
    from PySide6.QtCore import QTimer,QPointF,Qt,QThreadPool
    from PySide6.QtGui import QWindow
    from PySide6.QtWidgets import QApplication,QWidget
    from .caption_fonts import load_fonts
    from .model import Project
    from .widgets import PreviewCanvas
    from .transport import TimelineTransport
    from .gpu_preview import GpuPreview
    from types import SimpleNamespace
    app=QApplication([]);load_fonts()
    class PreviewProject(Project):
        @property
        def duration(self):return getattr(self,'_full_duration',super().duration)
    class RenderWindow(QWidget):
        def __init__(self):
            super().__init__();self._workers=set();self.settings={};self.thread_pool=QThreadPool(self)
        def start_worker(self,worker):
            self._workers.add(worker)
            def finished():
                self._workers.discard(worker);worker.signals.deleteLater()
            worker.signals.finished.connect(finished,Qt.QueuedConnection)
            getattr(worker,'pool',self.thread_pool).start(worker)
    class Tabs:
        def currentIndex(self):return self.index
        def tabText(self,index):return self.text
        index=0;text='Video'
    window=RenderWindow();window.project=PreviewProject();window.proxies={};window.preview_quality=None
    window.timeline=SimpleNamespace(selected_ids=set(),selected_caption_ids=set())
    window.inspector=SimpleNamespace(tabs=Tabs())
    window.inspector_toggle=SimpleNamespace(isChecked=lambda:window._inspector_open)
    window._inspector_open=True
    canvas=PreviewCanvas();canvas.setParent(window);canvas._gpu_renderer_child=True
    window.preview=canvas;canvas.project=window.project
    gpu=GpuPreview(canvas);canvas.gpu=gpu
    transport=TimelineTransport(window);transport.video_only=True;window.transport=transport
    transport.changed.connect(lambda at:(setattr(window.project,'playhead',at),canvas.update()))
    user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)];user.GetWindowThreadProcessId.restype=W.DWORD
    user.SetParent.argtypes=[W.HWND,W.HWND];user.SetParent.restype=W.HWND
    user.GetParent.argtypes=[W.HWND];user.GetParent.restype=W.HWND
    user.GetWindowLongW.argtypes=[W.HWND,C.c_int];user.GetWindowLongW.restype=C.c_long
    user.SetWindowLongW.argtypes=[W.HWND,C.c_int,C.c_long];user.SetWindowLongW.restype=C.c_long
    user.EnableWindow.argtypes=[W.HWND,W.BOOL];user.EnableWindow.restype=W.BOOL
    user.IsWindowEnabled.argtypes=[W.HWND];user.IsWindowEnabled.restype=W.BOOL
    owner=W.DWORD();user.GetWindowThreadProcessId(host,C.byref(owner))
    if owner.value!=parent_pid:raise RuntimeError('Preview host ownership changed')
    foreign=QWindow.fromWinId(host)
    if foreign is None:raise RuntimeError('Preview host window is unavailable')
    gpu.view.setParent(foreign)
    hwnd=int(gpu.view.winId())
    user.SetWindowLongW(hwnd,-16,user.GetWindowLongW(hwnd,-16)|0x08000000)
    if user.GetParent(hwnd)!=host:raise RuntimeError('Could not embed isolated preview')
    user.EnableWindow(hwnd,False)
    state={'signature':None,'closing':False,'sequence':0,'last_status':0.,'cache_epoch':0}
    def close():
        if state['closing']:return
        state['closing']=True;timer.stop();transport.shutdown()
        deadline=time.monotonic()+2
        def finish():
            from .qt_native import active
            if (active() or window._workers) and time.monotonic()<deadline:return
            transport.finish_gpu_shutdown();app.quit()
        close_timer=QTimer(window);close_timer.setInterval(16);close_timer.timeout.connect(finish);close_timer.start()
        state['close_timer']=close_timer
    def apply(payload):
        if payload['cache_epoch']!=state['cache_epoch']:
            gpu.invalidate_caches();state['cache_epoch']=payload['cache_epoch']
        signature=payload['signature']
        if signature!=state['signature']:
            project=Project.from_dict(payload['document']);project.__class__=PreviewProject
            project._full_duration=payload['duration'];window.project=project;canvas.project=project
            gpu.signature=None;state['signature']=signature
        window.project._full_duration=payload['duration']
        if window.proxies!=payload['proxies']:
            for key in list(transport.decoders):
                if window.proxies.get(key[0])!=payload['proxies'].get(key[0]):transport.retire_decoder(key)
            window.proxies=payload['proxies']
        gpu._forced_cpu_media=set(payload['cpu_media'])
        canvas.resize(*payload['size']);gpu.view.resize(*payload['size'])
        canvas.view_zoom=payload['zoom'];canvas.view_pan=QPointF(*payload['pan'])
        for name,value in payload['canvas'].items():setattr(canvas,name,value)
        canvas.drag_item=window.project.item_by_id(payload['drag_item'])
        window.timeline.selected_ids=set(payload['selected']);window.timeline.selected_caption_ids=set(payload['captions'])
        window.inspector.tabs.index,window.inspector.tabs.text=payload['inspector'];window._inspector_open=payload['inspector_open']
        canvas._viewer_bg=payload['background']
        clock=payload['clock'];transport.origin,transport.started,transport.rate,transport.playing,transport.scrubbing=clock
        transport.position=max(0.,transport.origin+(time.monotonic()-transport.started)*transport.rate) if transport.playing else payload['at']
        window.project.playhead=transport.position
        if canvas.caption_focus:gpu.container.hide()
        else:
            gpu.container.show();gpu.view.update()
        transport.sync(payload['force'])
        if transport.playing:transport.timer.start()
        else:transport.timer.stop()
        gpu.schedule();state['sequence']=payload['sequence']
    def poll():
        try:
            if not connection.poll(0):return
            kind,data=connection.recv()
            if kind!='batch':raise RuntimeError('Invalid preview command')
            latest,commands=data;captures=[value for command,value in commands if command=='capture']
            if latest is not None:apply(latest)
            from .preview_process import pack
            if captures:gpu.refresh()
            for serial in captures:connection.send(('capture',(serial,pack(gpu.view.grabWindow()))))
            now=time.monotonic()
            if now-state['last_status']>=.05:
                state['last_status']=now
                connection.send(('status',dict(sequence=state['sequence'],signature=state['signature'],hwnd=hwnd,pid=os.getpid(),
                    diagnostics=gpu.diagnostics(),completed=gpu.completed,bounds=gpu.bounds,
                    exposed=gpu.view.isExposed(),visible=gpu.view.isVisible(),parent=int(user.GetParent(hwnd) or 0),disabled=not user.IsWindowEnabled(hwnd),
                    sources={key:dict(ready=v['ready']) for key,v in gpu.sources.items()},
                    cpu_frames={key:(image.width(),image.height()) for key,image in canvas.frames.items() if not image.isNull()})))
            connection.send(('ack',None))
        except (EOFError,BrokenPipeError,OSError):close()
        except Exception:
            import traceback
            connection.send(('error',traceback.format_exc()));close()
    timer=QTimer(window);timer.setInterval(4);timer.timeout.connect(poll);timer.start()
    try:app.exec()
    finally:
        exited.set();connection.close();kernel.CloseHandle(parent)
