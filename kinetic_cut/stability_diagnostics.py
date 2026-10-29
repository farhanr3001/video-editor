"""Disposable real-media native interaction exercise, never touches owner projects."""
import os,sys,json,time,copy,hashlib,logging,traceback
from pathlib import Path
def run(output,project_path):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    assert not (out/'report.json').exists(),'Use a fresh diagnostic output folder'
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    os.environ['QT_QPA_PLATFORM']='windows'
    os.environ['KINETIC_GPU_PROCESS_TRACE']=str(out/'renderer-stacks.txt')
    os.environ['KINETIC_PREVIEW_PROCESS_TRACE']=str(out/'pixel-stacks.txt')
    from .process import install_desktop_process_policy
    install_desktop_process_policy()
    logging.basicConfig(filename=out/'application.log',level=logging.INFO)
    from .crash_logging import HangWatchdog
    from .activity_log import install as install_activity
    activity=install_activity(out)
    watchdog=HangWatchdog(out/'crash-trace.log')
    from PySide6.QtCore import QEventLoop,QTimer,QEvent,Qt,QPoint,QPointF,QThreadPool
    from PySide6.QtGui import QMouseEvent,QWheelEvent,QImage
    from PySide6.QtWidgets import QApplication
    from .model import Project
    from .ui import MainWindow
    from .assistant_api import validate
    source=Path(project_path).resolve()
    source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    project=Project.load(source);project.path=''
    for media in project.media:
        if media.kind in ('video','image'):media.thumbnail=''
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setProperty('kineticTestDiscardUnsaved',True)
    errors=[]
    def exception(kind,value,tb):
        errors.append(''.join(traceback.format_exception(kind,value,tb)))
        logging.error('Unhandled UI exception',exc_info=(kind,value,tb))
    sys.excepthook=exception
    journal=(out/'actions.jsonl').open('w',encoding='utf-8',buffering=1)
    report=dict(passed=False,checks=[],cycles=[],errors=errors,private_desktop=os.environ.get('KINETIC_DIAGNOSTIC_PRIVATE_DESKTOP'),source_sha=source_sha,frozen=bool(getattr(sys,'frozen',False)))
    started=time.monotonic();phase=['startup'];heartbeats=[];previous=[time.monotonic()]
    def write(kind,**data):journal.write(json.dumps(dict(time=time.monotonic()-started,kind=kind,phase=phase[0],**data))+'\n')
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def heartbeat():
        watchdog.beat();now=time.monotonic();delay=now-previous[0];previous[0]=now;heartbeats.append(delay)
        if delay>.4:write('heartbeat-delay',seconds=delay)
    timer=QTimer();timer.setInterval(25);timer.timeout.connect(heartbeat);timer.start()
    def action(name,fn):
        phase[0]=name;write('begin');t=time.monotonic();result=fn();write('end',seconds=time.monotonic()-t);return result
    def check(name,condition):
        report['checks'].append(dict(name=name,passed=bool(condition)))
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        if not condition:raise AssertionError(name)
    w=None
    try:
        w=action('create-window',MainWindow);w.resize(1700,1000);w.autosave_timer.stop()
        w.show();w.media_panel.folder='Master'
        action('load-owner-copy',lambda:w.set_project(project));w.transport.set_monitor_gain(0.)
        timeline=w.timeline
        native_messages=False
        def mouse(kind,x,y=8,button=Qt.NoButton,buttons=Qt.LeftButton):
            p=QPointF(x,y)
            if native_messages:
                import ctypes
                post=ctypes.windll.user32.PostMessageW
                post.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t];post.restype=ctypes.c_bool
                local=p-timeline.gpu.offset;ratio=timeline.gpu.view.devicePixelRatio()
                px,py=round(local.x()*ratio),round(local.y()*ratio)
                message={QEvent.MouseButtonPress:0x201,QEvent.MouseButtonRelease:0x202,QEvent.MouseMove:0x200}[kind]
                assert post(int(timeline.gpu.view.winId()),message,1 if buttons&Qt.LeftButton else 0,((py&0xffff)<<16)|(px&0xffff))
                return
            app.sendEvent(timeline.viewport(),QMouseEvent(kind,p,QPointF(timeline.viewport().mapToGlobal(p.toPoint())),button,buttons,Qt.NoModifier))
        def drag(a,b,n=32):
            mouse(QEvent.MouseButtonPress,timeline.x_for_time(a),button=Qt.LeftButton)
            for index in range(1,n+1):
                position=a+(b-a)*index/n
                action('scrub-move',lambda p=position:mouse(QEvent.MouseMove,timeline.x_for_time(p)))
                wait(18)
            action('scrub-release',lambda:mouse(QEvent.MouseButtonRelease,timeline.x_for_time(b),button=Qt.LeftButton,buttons=Qt.NoButton));wait(80)
            expected=b
            if timeline.property('snapping'):
                points=[0.]+[v for i in w.project.timeline for v in (i.start,i.start+i.duration)]+[v for c in w.project.captions for v in (c.start,c.end)]
                nearest=min(points,key=lambda v:abs(v-b))
                if abs(nearest-b)<=8/timeline.pixels_per_second:expected=nearest
            write('release-clock',requested=b,expected=expected,actual=w.transport.position)
            check('exact release clock including enabled snapping',abs(w.transport.position-expected)<1/w.project.settings.fps+.002)
        def payload():
            d=w.project.to_dict();d.pop('modified_at',None);d.pop('playhead',None);return d
        def rasters():
            return dict(waveforms=sorted(timeline.waveforms),pending=sorted(timeline.waveform_pending),failures=sorted(timeline.waveform_failures),thumbs=[dict(id=m.id,path=m.thumbnail,exists=bool(m.thumbnail and Path(m.thumbnail).is_file())) for m in w.project.media if m.kind in ('video','image')])
        wait(1800)
        duration=w.project.duration;assert duration>1.,'Use a project with at least one second of media'
        end=max(.1,duration-1/w.project.settings.fps)
        edges=sorted({i.start for i in w.project.timeline if duration*.1<i.start<duration*.9})
        cut=edges[len(edges)//2] if edges else duration/2
        zoom=max(4.,min(200.,(timeline.viewport().width()-timeline.LABEL_WIDTH-80)/duration))
        timeline.set_zoom(zoom);timeline.horizontalScrollBar().setValue(0)
        check('real native preview and timeline attached',bool(w.preview.gpu and timeline.gpu))
        check('preview renderer produced frames',w.preview.gpu.frames>0)
        deadline=time.monotonic()+30
        def thumbnails_ready():return all(m.thumbnail and Path(m.thumbnail).is_file() for m in w.project.media if m.kind in ('image','video'))
        while (not thumbnails_ready() or timeline.waveform_pending) and time.monotonic()<deadline:wait(50)
        check('cold project thumbnails generate while Power Bin is displayed',thumbnails_ready())
        check('cold waveform generation settles',not timeline.waveform_pending and not timeline.waveform_failures)
        w.preview.gpu.view.grabWindow().save(str(out/'initial-preview.png'))
        (out/'initial-rasters.json').write_text(json.dumps(rasters(),indent=2))
        # Reproduce old texture preparation completing after replacement while
        # paused. The new texture must arrive without another user interaction.
        import threading,numpy as np
        from unittest.mock import patch
        from .waveforms import Waveform
        from .gpu_timeline import peak_images
        audio=next((i for i in project.timeline if i.track in project.audio_tracks and i.media_id in timeline.waveforms),None)
        if audio:
            original=timeline.waveforms[audio.media_id]
            old=Waveform(np.tile(np.array([[-24000,24000]],dtype=np.int16),(1000,1)))
            latest=Waveform(np.tile(np.array([[-1000,1000]],dtype=np.int16),(1000,1)))
            entered=threading.Event();release=threading.Event()
            def delayed(samples):
                if samples is old:entered.set();release.wait(3)
                return peak_images(samples)
            try:
                with patch('kinetic_cut.gpu_timeline.peak_images',side_effect=delayed):
                    timeline.set_waveform(audio.media_id,old);timeline.gpu.refresh()
                    deadline=time.monotonic()+3
                    while not entered.is_set() and time.monotonic()<deadline:wait(20)
                    check('native stale-waveform fixture actually starts old preparation',entered.is_set())
                    timeline.set_waveform(audio.media_id,latest);timeline.gpu.refresh();release.set()
                    deadline=time.monotonic()+3
                    while timeline.gpu.waveforms.get(audio.media_id,(None,))[0]!=id(latest) and time.monotonic()<deadline:wait(30)
                    check('native idle timeline publishes replacement after stale peak job',timeline.gpu.waveforms.get(audio.media_id,(None,))[0]==id(latest))
                    image=timeline.gpu.waveforms[audio.media_id][1][0][0]
                    check('replacement waveform texture contains new peak values',image.pixelColor(0,0).red()==8 and image.pixelColor(0,0).green()==8)
            finally:release.set();timeline.set_waveform(audio.media_id,original)
        cycles=min(100,max(1,int(os.environ.get('KINETIC_STRESS_CYCLES','12'))))
        for cycle in range(cycles):
            native_messages=bool(cycle%2)
            begin=time.monotonic();write('cycle',index=cycle)
            action('seek-start',lambda:w.seek(.5));action('play',w.transport.play);wait(200)
            action('pause',w.transport.pause);wait(50)
            timeline.set_zoom(zoom);timeline.horizontalScrollBar().setValue(0)
            action('drag-forward',lambda:drag(end*.01,end*.97))
            action('drag-reverse',lambda:drag(end*.97,end*.01))
            action('drag-across-source-cut',lambda:drag(max(0,cut-.4),min(end,cut+.4),24))
            for position in [0.,max(0,cut-1/w.project.settings.fps),cut,min(end,cut+.1),end,end*.2]*3:
                action('click-seek',lambda p=position:w.seek(p));wait(30)
                if abs(position-min(end,cut+.1))<1e-9:action('resume-near-sfx',w.transport.play);wait(80);action('pause-near-sfx',w.transport.pause)
            action('normal-play-start',lambda:w.seek(max(0,cut-.5)));action('normal-play',w.transport.play);wait(550)
            for index in range(6):
                anchor=QPointF(500,150)
                action('wheel-zoom',lambda n=index:app.sendEvent(timeline.viewport(),QWheelEvent(anchor,QPointF(timeline.viewport().mapToGlobal(anchor.toPoint())),QPoint(),QPoint(0,120 if n%2 else -120),Qt.NoButton,Qt.AltModifier,Qt.NoScrollPhase,False)));wait(25)
            action('pause-after-zoom',w.transport.pause)
            if cycle%2==0:
                original=payload();item=next(i for i in w.project.timeline if i.track in w.project.video_tracks and i.duration>1.)
                timeline.selected_id=item.id;timeline.selected_ids={item.id}
                action('seek-for-split',lambda:w.seek(item.start+min(.5,item.duration/2)))
                action('split-selected',w.split_selected);action('undo-split',w.undo)
                check('split Undo restores document',payload()==original)
                action('redo-split',w.redo);action('undo-again',w.undo)
                check('redo Undo restores document',payload()==original)
            validate(w.project)
            import psutil,ctypes
            ctypes.windll.kernel32.GetCurrentProcess.restype=ctypes.c_void_p
            ctypes.windll.user32.GetGuiResources.argtypes=[ctypes.c_void_p,ctypes.c_uint]
            proc=psutil.Process();resources=dict(rss=proc.memory_info().rss,handles=proc.num_handles(),gdi=ctypes.windll.user32.GetGuiResources(ctypes.windll.kernel32.GetCurrentProcess(),0),user=ctypes.windll.user32.GetGuiResources(ctypes.windll.kernel32.GetCurrentProcess(),1))
            from PySide6.QtMultimedia import QMediaPlayer
            resources['threads']=proc.num_threads();resources['qt_players']=len(w.findChildren(QMediaPlayer))
            report['cycles'].append(dict(index=cycle,native_windows_input=native_messages,seconds=time.monotonic()-begin,frames=w.preview.gpu.frames,decoders=len(w.transport.decoders),workers=len(getattr(w,'_workers',{})),resources=resources))
            (out/'report.json').write_text(json.dumps(report,indent=2))
        for index in range(3):
            action('switch-to-empty',lambda:w.set_project(Project(name='Disposable empty')));wait(100)
            action('switch-back',lambda:w.set_project(copy.deepcopy(project)));w.transport.set_monitor_gain(0.);wait(300)
        deadline=time.monotonic()+30
        while timeline.waveform_pending and time.monotonic()<deadline:wait(100)
        report['rasters']=rasters()
        check('all audio waveforms generated',all(m.id in timeline.waveforms for m in w.project.media if m.has_audio or m.kind=='audio'))
        check('waveform jobs settled',not timeline.waveform_pending and not timeline.waveform_failures)
        timeline.gpu.view.grabWindow().save(str(out/'final-timeline.png'))
        w.preview.gpu.view.grabWindow().save(str(out/'final-preview.png'))
        check('no UI exception',not errors)
        peer=w.preview.gpu.peer;action('close',w.close)
        deadline=time.monotonic()+15
        while (w.isVisible() or peer.active) and time.monotonic()<deadline:wait(50)
        check('window and native renderer close gracefully',not w.isVisible() and not peer.active and peer.exitcode==0 and not peer.forced_shutdown)
        check('project input preserved',hashlib.sha256(source.read_bytes()).hexdigest()==source_sha)
        report.update(passed=True,seconds=time.monotonic()-started,max_heartbeat_seconds=max(heartbeats,default=0),heartbeat_count=len(heartbeats))
    except BaseException:
        report['error']=traceback.format_exc();write('failure',error=report['error']);print(report['error'],flush=True)
    finally:
        if w and w.isVisible():w.close()
        QThreadPool.globalInstance().waitForDone(10000);app.processEvents()
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        journal.close();watchdog.close();activity.close()
    return 0 if report['passed'] else 1

