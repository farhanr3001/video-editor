"""Native input/event-loop benchmark on a disposable, unsaved project copy."""
def run(output, project_path):
    import os, sys, json, time, math, hashlib, cProfile, pstats
    from pathlib import Path
    out=Path(output).resolve(); out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    from PySide6.QtCore import Qt,QTimer,QEventLoop,QPointF,QPoint,QEvent,QThreadPool
    from PySide6.QtGui import QMouseEvent,QWheelEvent
    from PySide6.QtWidgets import QApplication
    from .model import Project
    from .ui import MainWindow
    source=Path(project_path).resolve(); before=hashlib.sha256(source.read_bytes()).hexdigest()
    project=Project.load(source); project.path=''
    if os.environ.get('KINETIC_INTERACTION_CROPS_ONLY')=='1':
        for item in project.timeline:item.effects=[]
    app=QApplication([]); app.setProperty('kineticTestDiscardUnsaved',True)
    window=MainWindow(); screen=app.primaryScreen().availableGeometry()
    window.resize(min(1900,screen.width()),min(1080,screen.height())); window.setAttribute(Qt.WA_ShowWithoutActivating)
    # Windows STARTUPINFO may hide the initial show in a packaged launch.
    # Exercise a genuinely displayed window; hidden widgets do not receive the
    # normal update paints and would produce falsely fast input measurements.
    window.show();window.showMinimized();window.showNormal();window.autosave_timer.stop()
    window.request_waveform=lambda media:None
    # Measure steady-state editing, not an unrelated full-recording proxy encode.
    window.preview_quality.request=lambda:None
    window.set_project(project); timeline=window.timeline
    from .waveforms import waveform
    for media in project.media:
        if media.has_audio or media.kind=='audio':
            timeline.set_waveform(media.id,waveform(media.path,window.settings.get('ffmpeg','ffmpeg')))
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def stats(values):
        values=sorted(values)
        return dict(count=len(values),mean_ms=round(sum(values)/max(1,len(values)),3),
                    p95_ms=round(values[min(len(values)-1,int(len(values)*.95))],3) if values else 0,
                    max_ms=round(max(values,default=0),3))
    samples={}; paints=[]; pending=[None]; delivered=[]; errors=[]; presented=[]; audio_buffers=[]
    hook=sys.excepthook
    def exception(kind,value,traceback):
        errors.append(str(value)); hook(kind,value,traceback)
    sys.excepthook=exception
    def timed(name,fn):
        def call(*args,**kwargs):
            start=time.perf_counter()
            try:return fn(*args,**kwargs)
            finally:samples.setdefault(name,[]).append((time.perf_counter()-start)*1000)
        return call
    paint=timeline.paintEvent
    def painted(event):
        timed('timeline_paint',paint)(event); now=time.perf_counter(); paints.append(now)
        if pending[0] is not None:
            samples.setdefault('input_to_paint',[]).append((now-pending[0])*1000); pending[0]=None
    timeline.paintEvent=painted
    preview_paint=window.preview.paintEvent
    def preview_painted(event):
        timed('preview_paint',preview_paint)(event)
        stamp=window.preview.composition_cache.last_frame
        if window.transport.playing and stamp is not None:presented.append(stamp)
    window.preview.paintEvent=preview_painted
    window.transport.sync=timed('transport_sync',window.transport.sync)
    frame=window.transport.frame
    def received(key,image):
        delivered.append((time.perf_counter(),str(key),image.cacheKey())); frame(key,image)
    window.transport.frame=received
    audio_buffer=window.transport.receive_audio_buffer
    def audio_received(key,buffer):
        if window.transport.playing and key not in window.transport.warm_keys and buffer.isValid():
            audio_buffers.append((str(key),buffer.startTime(),buffer.duration()))
        audio_buffer(key,buffer)
    window.transport.receive_audio_buffer=audio_received
    def mouse(kind,pos,button=Qt.NoButton,buttons=Qt.MiddleButton):
        app.sendEvent(timeline.viewport(),QMouseEvent(kind,pos,QPointF(timeline.viewport().mapToGlobal(pos.toPoint())),button,buttons,Qt.NoModifier))
    wait(1600)
    report=dict(project=source.name,sha256=before,clips=len(project.timeline),duration=project.duration,
                frozen=bool(getattr(sys,'frozen',False)),window=[window.width(),window.height()],runs=[])
    modes=os.environ.get('KINETIC_INTERACTION_MODES','paused_zoom,playing_idle,playing_zoom,playing_pan,paused_pan').split(',')
    duration=int(os.environ.get('KINETIC_INTERACTION_MS','4000'))
    for mode in modes:
        window.transport.pause(); window.seek(162.6)
        timeline.set_zoom(20); timeline.horizontalScrollBar().setValue(round(150*timeline.pixels_per_second))
        wait(600)
        if mode.startswith('playing'):window.transport.play(); wait(600)
        section=timeline._sections()['video']; anchor=QPointF((timeline.LABEL_WIDTH+timeline.viewport().width())/2,section.center().y())
        if mode.endswith('pan'):mouse(QEvent.MouseButtonPress,anchor,Qt.MiddleButton)
        samples.clear(); paints.clear(); delivered.clear(); presented.clear(); audio_buffers.clear(); pending[0]=None
        previous=[time.perf_counter()]; started=previous[0]; count=[0]
        audio_start={str(k):p.position() for k,(p,_,sink) in window.transport.decoders.items() if sink is None}
        def step():
            now=time.perf_counter(); samples.setdefault('input_interval',[]).append((now-previous[0])*1000); previous[0]=now
            pending[0]=pending[0] or now; count[0]+=1
            if mode.endswith('zoom'):
                direction=1 if (count[0]//8)%2==0 else -1
                app.sendEvent(timeline.viewport(),QWheelEvent(anchor,QPointF(timeline.viewport().mapToGlobal(anchor.toPoint())),QPoint(),QPoint(0,120*direction),Qt.NoButton,Qt.AltModifier,Qt.NoScrollPhase,False))
            elif mode.endswith('pan'):
                mouse(QEvent.MouseMove,anchor+QPointF(140*math.sin((now-started)*3),0))
        timer=QTimer(); timer.setTimerType(Qt.PreciseTimer); timer.setInterval(16); timer.timeout.connect(step)
        profile=cProfile.Profile()
        if os.environ.get('KINETIC_INTERACTION_PROFILE','1')=='1':profile.enable()
        timer.start(); wait(duration); timer.stop(); profile.disable()
        elapsed=time.perf_counter()-started
        result=dict(mode=mode,seconds=elapsed,input_events=count[0],delivered_frames=len(delivered),cache_entries=len(timeline._clip_surfaces),
                    composition_presentations=len(presented),backwards_presentations=sum(b<a for a,b in zip(presented,presented[1:])),
                    valid_audio_buffers=len(audio_buffers),audio_buffer_duration_ms=sum(b[2] for b in audio_buffers)/1000,
                    audio_advance_ms={str(k):p.position()-audio_start.get(str(k),p.position()) for k,(p,_,sink) in window.transport.decoders.items() if sink is None},
                    metrics={k:stats(v) for k,v in samples.items()})
        result['metrics']['paint_interval']=stats([(b-a)*1000 for a,b in zip(paints,paints[1:])])
        report['runs'].append(result); print(json.dumps(result),flush=True)
        if os.environ.get('KINETIC_INTERACTION_PROFILE','1')=='1':
            with (out/(mode+'-profile.txt')).open('w') as stream:pstats.Stats(profile,stream=stream).sort_stats('cumtime').print_stats(65)
        if mode.endswith('pan'):mouse(QEvent.MouseButtonRelease,anchor,Qt.MiddleButton,Qt.NoButton)
        window.grab().save(str(out/(mode+'.png')))
    window.transport.pause()
    from PySide6.QtTest import QTest
    # Rapid owner-style input on the disposable copy, including real edit/Undo.
    def content():
        value=window.project.to_dict(); value.pop('playhead',None); value.pop('modified_at',None); return value
    original=content(); workflow=[]
    for cycle in range(3):
        window.seek(162.65+cycle*.15); timeline.viewport().setFocus()
        window.transport.play(); wait(100)
        canvas=window.preview; pan=QPointF(canvas.view_pan)
        QTest.mousePress(canvas,Qt.MiddleButton,pos=QPoint(80,80))
        QTest.mouseMove(canvas,QPoint(120,100)); QTest.mouseRelease(canvas,Qt.MiddleButton,pos=QPoint(120,100))
        assert canvas.view_pan==pan,'Preview pan moved during Play'
        zoom=canvas.view_zoom; point=QPointF(canvas.width()/2,canvas.height()/2)
        app.sendEvent(canvas,QWheelEvent(point,point,QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False))
        assert canvas.view_zoom>zoom,'Preview zoom locked during Play'
        window.transport.pause(); wait(50)
        QTest.mousePress(canvas,Qt.MiddleButton,pos=QPoint(80,80))
        QTest.mouseMove(canvas,QPoint(120,100)); QTest.mouseRelease(canvas,Qt.MiddleButton,pos=QPoint(120,100))
        assert canvas.view_pan!=pan,'Preview pan did not unlock on Pause'
        canvas.reset_view()
        at=window.project.playhead
        clip=next(i for i in window.project.timeline if i.track in window.project.video_tracks and i.role=='content' and i.start+.03<at<i.start+i.duration-.03)
        old_count=len(window.project.timeline); started=time.perf_counter(); window.split_at(clip.id,at)
        split_ms=(time.perf_counter()-started)*1000
        assert len(window.project.timeline)>old_count,'Split did not apply'
        window.undo(); assert content()==original,'Undo did not restore disposable edit'
        window.redo(); assert len(window.project.timeline)>old_count,'Redo did not restore split'
        window.undo(); assert content()==original,'Second Undo did not restore edit'
        workflow.append(dict(cycle=cycle,split_ms=round(split_ms,3),preview_pan_lock=True,preview_zoom=True,paused_pan=True,split_undo_redo=True))
    report['rapid_workflow']=workflow
    # Compare the desktop helper against the GUI renderer, including real
    # system fonts. Offscreen-to-offscreen tests cannot detect missing native
    # font database glyphs in a helper process.
    timeline.set_zoom(20);timeline.viewport().repaint();deadline=time.monotonic()+5
    while timeline._timeline_raster_busy and time.monotonic()<deadline:wait(20)
    timeline.viewport().repaint();cached=timeline._timeline_backing.toImage()
    from unittest.mock import patch
    with patch.object(timeline,'drag_mode','direct-reference'):
        timeline.viewport().repaint();reference=timeline._timeline_backing.toImage()
    import numpy as np
    a=np.frombuffer(cached.constBits(),np.uint8).astype(np.int16)
    b=np.frombuffer(reference.constBits(),np.uint8).astype(np.int16)
    delta=np.abs(a-b).reshape(cached.height(),cached.width(),4)
    edge=int(np.count_nonzero(delta[:,-1].max(axis=1)>2));delta[:,-1]=0
    report['native_timeline_pixels']=dict(max_channel_error=int(delta.max()),different_channels=int(np.count_nonzero(delta)),channels=int(delta.size),edge_pixels=edge)
    cached.save(str(out/'timeline-helper.png'));reference.save(str(out/'timeline-reference.png'))
    # A rounded thumbnail clipped at the pinned-header/device edge can differ
    # in a few antialiased corner pixels when cropped from the wider raster.
    ys,xs=np.where(delta.max(axis=2)>2)
    pixel_parity=(len(xs)<=8 and bool(np.all((xs<=timeline.LABEL_WIDTH+2)|(xs>=cached.width()-1)))
                  and np.count_nonzero(delta)/delta.size<.002 and edge<=8)
    report['native_timeline_pixels']['edge_corner_outliers']=len(xs)
    report['native_timeline_pixels']['passed']=pixel_parity
    from .video_worker import WorkerVideoPlayer
    report['preview_pipeline']=dict(composition='CPU QImage/QPainter',graphics_backend='Qt raster paint engine',window_system=app.platformName(),
        decoders=[dict(kind='PyAV/libav worker' if isinstance(player,WorkerVideoPlayer) else 'Qt Multimedia',
                       hardware_active=player.engine.hardware_active if isinstance(player,WorkerVideoPlayer) else None)
                  for player,_,sink in window.transport.decoders.values() if sink is not None])
    report['timeline_helper_started']=timeline._timeline_renderer is not None
    report['timeline_helper_failed']=timeline._timeline_raster_failed
    renderer=window.preview.composition_cache.renderer
    timeline_renderer=timeline._timeline_renderer
    window.close(); report['workers_finished']=QThreadPool.globalInstance().waitForDone(15000); app.processEvents()
    for helper in (renderer,timeline_renderer):
        if helper and helper.process:
            deadline=time.monotonic()+3
            while helper.process.is_alive() and time.monotonic()<deadline:wait(20)
    report['helpers_reaped']=all(not helper or not helper.process or not helper.process.is_alive() for helper in (renderer,timeline_renderer))
    report['project_unchanged']=before==hashlib.sha256(source.read_bytes()).hexdigest()
    report['errors']=errors; sys.excepthook=hook
    report['painted_workflow']=all(r['metrics'].get('timeline_paint',{}).get('count',0)>5 and r['metrics'].get('input_to_paint',{}).get('count',0)>5 and (not r['mode'].startswith('playing') or r['metrics'].get('preview_paint',{}).get('count',0)>5) for r in report['runs'])
    report['passed']=report['painted_workflow'] and pixel_parity and not errors and not report['timeline_helper_failed'] and report['project_unchanged'] and report['workers_finished'] and report['helpers_reaped'] and all(r['delivered_frames']>20 and r['backwards_presentations']==0 and r['valid_audio_buffers']>0 for r in report['runs'] if r['mode'].startswith('playing'))
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert report['passed'],report
    return 0
