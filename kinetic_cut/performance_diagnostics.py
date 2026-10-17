"""Real-project Full Preview coverage and responsiveness; no owner data writes."""
def run(output, project_path):
    import os,sys,time,json,hashlib,copy
    if os.environ.get('KINETIC_BLUR_PAN_SELFTEST')=='1':return run_blur_pan(output,project_path)
    from pathlib import Path
    out=Path(output).resolve(); out.mkdir(parents=True,exist_ok=True)
    import faulthandler
    trace=(out/'threads.log').open('w',encoding='utf-8')
    faulthandler.dump_traceback_later(30,repeat=True,file=trace)
    os.environ['KINETIC_CUT_HOME']=os.environ.get('KINETIC_PERFORMANCE_CACHE_HOME',str(out/'home'))
    from PySide6.QtCore import Qt,QTimer,QEventLoop,QPoint,QThreadPool
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    from .model import Project
    from .video_worker import WorkerVideoPlayer
    source=Path(project_path).resolve(); digest=hashlib.sha256(source.read_bytes()).hexdigest()
    app=QApplication.instance() or QApplication([])
    class DiagnosticWindow(MainWindow):
        def check_crash_recovery(self):
            # A disposable benchmark may be interrupted between runs. Its
            # recovery prompt must not block automated input; owner startup
            # and the production recovery implementation remain unchanged.
            pass
    w=DiagnosticWindow(); w.resize(1500,950); w.show(); w.autosave_timer.stop()
    p=Project.load(source); p.path=''; w.request_waveform=lambda _:None
    w.set_project(p); t=w.transport
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def stats(values):
        ordered=sorted(values)
        return dict(count=len(values),mean_ms=round(sum(values)/max(1,len(values)),3),
                    p95_ms=round(ordered[min(len(ordered)-1,int(len(ordered)*.95))],3) if ordered else 0,
                    max_ms=round(max(values,default=0),3))
    def complete():
        active=[(item,key) for item,key in w.preview.active_frames.items()]
        return bool(active) and all(key in w.preview.frames and key not in t._pending_video_seeks for _,key in active)
    def seek(at):
        begin=time.perf_counter(); w.seek(at)
        deadline=time.monotonic()+5
        while not complete() and time.monotonic()<deadline:wait(5)
        return dict(at=at,latency_ms=round((time.perf_counter()-begin)*1000,3),
                    passed=complete(),lanes=len(w.preview.active_frames),
                    worker_decoders=sum(isinstance(v[0],WorkerVideoPlayer) for v in t.decoders.values()))
    report=dict(frozen=bool(getattr(sys,'frozen',False)),project=source.name,sha=digest,full_preview=w.preview_quality.currentIndex()==0,seeks=[],playback=[],scrub=[],drag=[])
    measured={}
    def measure(owner,name,label):
        original=getattr(owner,name)
        def invoke(*args,**kwargs):
            begin=time.perf_counter()
            try:return original(*args,**kwargs)
            finally:measured.setdefault(label,[]).append((time.perf_counter()-begin)*1000)
        setattr(owner,name,invoke)
    measure(w.preview,'_paint_scene','gui_scene')
    measure(w.preview.composition_cache,'request','composition_request')
    measure(t,'sync','transport_sync')
    # Every source-time segment, including AV1 and the final timeline portion.
    points=sorted({round(i.start+min(.3,i.duration/2),5) for i in p.timeline
                   if i.track in p.video_tracks and p.media_by_id(i.media_id)
                   and p.media_by_id(i.media_id).kind=='video' and not i.muted})
    limit=int(os.environ.get('KINETIC_PERFORMANCE_SEEK_LIMIT','0'))
    if limit>1 and len(points)>limit:
        points=[points[round(n*(len(points)-1)/(limit-1))] for n in range(limit)]
    for n,at in enumerate(points):
        result=seek(at); report['seeks'].append(result)
        if n in (0,len(points)//2,len(points)-1):w.grab().save(str(out/f'seek-{n}.png'))
    ticks=[]; previous=[time.perf_counter()]
    timer=QTimer(); timer.setTimerType(Qt.PreciseTimer); timer.setInterval(7)
    def beat():
        now=time.perf_counter(); ticks.append((now-previous[0])*1000); previous[0]=now
    timer.timeout.connect(beat)
    frames=[]; original=t.frame
    def frame(key,image):
        frames.append((time.perf_counter(),key)); original(key,image)
    t.frame=frame
    # A caption-heavy shot, an animated-card shot, and an AV1 shot.
    candidates=[162.6]
    candidates += [i.start+.3 for i in p.timeline if i.graphic_type.lower()=='motion composition'][:1]
    candidates += [i.start+.3 for i in p.timeline if i.track in p.video_tracks and p.media_by_id(i.media_id) and p.media_by_id(i.media_id).video_codec=='av1'][:1]
    for at in candidates:
        if at>=p.duration:continue
        seek(at); wait(100); frames.clear(); ticks.clear(); previous[0]=time.perf_counter(); timer.start()
        measured.clear(); begin=time.perf_counter(); t.play(); wait(3000); t.pause(); timer.stop()
        last={}; gaps=[]
        for delivered,key in frames:
            if key in last:gaps.append((delivered-last[key])*1000)
            last[key]=delivered
        report['playback'].append(dict(at=at,seconds=time.perf_counter()-begin,frames=len(frames),gui=stats(ticks),gaps=stats(gaps),measured={k:stats(v) for k,v in measured.items()}))
    # Ruler drag must keep producing frames, then settle to the exact release.
    for base in (10.,min(160.,p.duration-3)):
        seek(base); frames.clear(); ticks.clear(); timer.start(); previous[0]=time.perf_counter()
        for n in range(70):t.scrub(base+(n%35)*.035); wait(12)
        t.scrub(base+.723); t.finish_scrub(); deadline=time.monotonic()+5
        while not complete() and time.monotonic()<deadline:wait(5)
        timer.stop(); report['scrub'].append(dict(at=base,frames_while_dragging=len(frames),settled=complete(),position=t.position,gui=stats(ticks)))
    # Multiple placements including a full motion scene; Escape must restore all.
    timeline=w.timeline; timeline.pixels_per_second=8.; timeline._range(); seek(12.)
    items=[i for i in p.timeline if i.track in p.video_tracks and not timeline.visible_item_rect(i).isEmpty()]
    if items:
        chosen=items[:min(6,len(items))]; timeline.select_ids({i.id for i in chosen})
        before=copy.deepcopy(p.timeline); origin=timeline.visible_item_rect(chosen[0]).center().toPoint()
        QTest.mousePress(timeline.viewport(),Qt.LeftButton,pos=origin); timings=[]
        for n in range(45):
            begin=time.perf_counter(); QTest.mouseMove(timeline.viewport(),origin+QPoint(10+n%25,0)); app.processEvents()
            timings.append((time.perf_counter()-begin)*1000)
        QTest.keyClick(timeline.viewport(),Qt.Key_Escape); QTest.mouseRelease(timeline.viewport(),Qt.LeftButton,pos=origin)
        report['drag']=dict(selected=len(chosen),latency=stats(timings),cancel_preserved=p.timeline==before)
    report['cache']=dict(hits=w.preview.composition_cache.hits,misses=w.preview.composition_cache.misses,completed=w.preview.composition_cache.completed,failed=w.preview.composition_cache.closed,bytes=w.preview.composition_cache.images.byte_count)
    report['owner_project_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==digest
    report['passed']=(report['full_preview'] and report['owner_project_unchanged'] and all(x['passed'] for x in report['seeks'])
                      and all(x['frames']>20 for x in report['playback']) and all(x['settled'] and x['frames_while_dragging']>5 for x in report['scrub'])
                      and bool(report['drag']) and report['drag']['cancel_preserved'])
    from .video_worker import enabled
    if enabled():report['passed'] &= not report['cache']['failed'] and report['cache']['completed']>0
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps(report),flush=True)
    w.close(); deadline=time.monotonic()+10
    while w._workers and time.monotonic()<deadline:wait(20)
    QThreadPool.globalInstance().waitForDone(10000); app.processEvents()
    report['workers_closed']=not w._workers
    report['passed'] &= report['workers_closed']
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    faulthandler.cancel_dump_traceback_later(); trace.close()
    return 0 if report['passed'] else 1


def run_blur_pan(output,project_path):
    import os,sys,time,json,copy
    from pathlib import Path
    r=Path.cwd();sys.path.insert(0,str(r));out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True);os.environ['KINETIC_CUT_HOME']=str(out/'home');os.environ['QT_QPA_PLATFORM']='windows'
    import av
    from PySide6.QtCore import Qt,QEvent,QPointF
    from PySide6.QtGui import QImage,QMouseEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from unittest.mock import patch
    from types import SimpleNamespace
    from kinetic_cut.model import Project,MediaItem,TimelineItem
    from kinetic_cut.widgets import PreviewCanvas
    from kinetic_cut.visuals import blur_image
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    project=Project.load(project_path);media_path=next(m.path for m in project.media if m.kind=='video')
    with av.open(media_path) as movie:
     movie.seek(5300000);frame=next(movie.decode(video=0));pixels=frame.to_ndarray(format='rgb24')
    image=QImage(pixels.data,frame.width,frame.height,pixels.strides[0],QImage.Format_RGB888).copy()
    rows=[]
    for count,inspector,enhanced in ((1,False,False),(1,True,False),(6,False,False),(1,False,True)):
     c=PreviewCanvas();c.resize(1000,650);c.transport=SimpleNamespace(playing=False,scrubbing=False)
     p=Project(media=[MediaItem('m',media_path,'video','actual webcam source',17,frame.width,frame.height)]);p.video_tracks=[f'video_{n+1}' for n in range(count)]
     p.timeline=[TimelineItem(str(n),'m',track,0,10) for n,track in enumerate(p.video_tracks)]
     from .enhance import default_effect
     for item in p.timeline:item.effects=([default_effect()] if enhanced else [])+[dict(name='Gaussian Blur',enabled=True,horizontal=12,vertical=12,inspector_background_blur=inspector)]
     c.set_project(p);c.active_frames={i.id:'source' for i in p.timeline};c.frames={'source':image};c.transform_controls_visible=False
     with patch.object(c.composition_cache,'request',return_value=None) as warm:
      c.show();QTest.qWait(50);c.repaint();warm.reset_mock();samples=[]
      QTest.mousePress(c,Qt.MiddleButton,pos=__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint(400,300))
      with patch('kinetic_cut.visuals.blur_image',wraps=blur_image) as blur:
       for n in range(10):
        pos=QPointF(401.25+n*3.125,301.375+n*1.75);event=QMouseEvent(QEvent.MouseMove,pos,pos,Qt.NoButton,Qt.MiddleButton,Qt.NoModifier)
        start=time.perf_counter();QApplication.sendEvent(c,event);c.repaint();samples.append((time.perf_counter()-start)*1000)
       calls=blur.call_count
      QTest.mouseRelease(c,Qt.MiddleButton,pos=__import__('PySide6.QtCore',fromlist=['QPoint']).QPoint(440,320))
      rows.append(dict(layers=count,inspector_blur=inspector,enhance_stack=enhanced,median_ms=sorted(samples)[len(samples)//2],max_ms=max(samples),blur_calls_during_pan=calls,composition_warm_requests=warm.call_count,pan=[c.view_pan.x(),c.view_pan.y()]))
      c.grab().save(str(out/f'pan-{count}-{inspector}.png'))
     c.composition_cache.close();c.close();c.deleteLater();app.processEvents()
    report=dict(passed=all(row['blur_calls_during_pan']==0 and row['composition_warm_requests']==0 for row in rows),frozen=bool(getattr(sys,'frozen',False)),source=media_path,decoded_dimensions=[frame.width,frame.height],cases=rows)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
    
    return 0 if report['passed'] else 1
