"""Isolated, real-media three-layer playback/UI latency diagnostic."""
def run(output, source):
    import os, time, json, cProfile, pstats
    from pathlib import Path
    out = Path(output).resolve(); out.mkdir(parents=True, exist_ok=True)
    os.environ['KINETIC_CUT_HOME'] = str(out / 'home')
    from PySide6.QtCore import QTimer, QEventLoop, Qt, QThreadPool, QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    from .model import Project, TimelineItem, Crop, Transform
    from .media import probe
    app = QApplication.instance() or QApplication([])
    w = MainWindow(); w.resize(1500, 950); w.show(); w.autosave_timer.stop()
    media = probe(source)
    p = Project(); p.media = [media]; p.video_tracks = ['video_1', 'video_2', 'video_3']
    # Repeated source-time jumps exercise cut warmup and separate layout crops.
    for n in range(4):
        for lane in range(1, 4):
            i = TimelineItem(f'v{lane}-{n}', media.id, f'video_{lane}', n*3., 3., 10+n*5.)
            if lane == 1:
                i.transform = Transform(y=.5)
                i.effects = [{'name':'Gaussian Blur', 'enabled':True, 'horizontal':45., 'vertical':45., 'border':'Reflect'}]
            elif lane == 2:
                i.crop = Crop(.12,.04,.72,.92); i.transform = Transform(y=.65, scale=.55)
            else:
                i.crop = Crop(0.,.0,.25,.4); i.transform = Transform(y=.2, scale=1.2)
            p.timeline.append(i)
        p.timeline.append(TimelineItem(f'a{n}',media.id,'audio_1',n*3.,3.,10+n*5.,role='source_audio'))
    # This benchmarks playback, not simultaneous first-import whole-source audio
    # analysis (the real recordings can be hours long). No source file is changed.
    w.request_waveform = lambda media: None
    w.set_project(p)
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    wait(1500)
    paints=[]; frames=[]; ticks=[]; timeline_paints=[]; timeline_damage=[]; cache_misses=[]
    original_paint = w.preview.paintEvent
    def paint(event):
        start=time.perf_counter(); original_paint(event); paints.append((time.perf_counter()-start)*1000)
    w.preview.paintEvent=paint
    original_timeline_paint=w.timeline.paintEvent
    def timeline_paint(event):
        pending=getattr(w.timeline,'_playhead_damage',None)
        if pending is not None and len(cache_misses)<6 and not event.region().subtracted(pending).isEmpty():
            cache_misses.append(dict(dirty=[(r.x(),r.y(),r.width(),r.height()) for r in event.region()],pending=[(r.x(),r.y(),r.width(),r.height()) for r in pending]))
        timeline_damage.append(sum(r.width()*r.height() for r in event.region()) / max(1,w.timeline.viewport().width()*w.timeline.viewport().height()))
        start=time.perf_counter(); original_timeline_paint(event); timeline_paints.append((time.perf_counter()-start)*1000)
    w.timeline.paintEvent=timeline_paint
    original_frame=w.transport.frame
    def frame(key,image):
        frames.append((time.perf_counter(),key)); original_frame(key,image)
    w.transport.frame=frame
    previous=[time.perf_counter()]
    timer=QTimer(); timer.setTimerType(Qt.PreciseTimer); timer.setInterval(7)
    def heartbeat():
        now=time.perf_counter(); ticks.append((now-previous[0])*1000); previous[0]=now
    timer.timeout.connect(heartbeat)
    def stats(values):
        values=sorted(values)
        return dict(count=len(values),mean_ms=round(sum(values)/max(1,len(values)),3),
                    p95_ms=round(values[min(len(values)-1,int(len(values)*.95))],3) if values else 0,
                    max_ms=round(max(values,default=0),3))
    profiled=os.environ.get('KINETIC_PLAYBACK_PROFILE','1')!='0'
    report={'frozen':bool(getattr(__import__('sys'),'frozen',False)), 'profiled':profiled, 'media':media.name,
            'resolution':[media.width,media.height], 'source_fps':media.fps, 'runs':[]}
    profiler=cProfile.Profile()
    for theme in ('default','ableton_gray'):
        w.apply_theme(theme,save=False); w.seek(.3); wait(600)
        paints.clear(); frames.clear(); ticks.clear(); timeline_paints.clear(); timeline_damage.clear(); cache_misses.clear()
        previous[0]=time.perf_counter(); timer.start()
        if profiled:profiler.enable()
        w.transport.play(); start=time.perf_counter(); wait(7000)
        elapsed=time.perf_counter()-start; w.transport.pause(); profiler.disable(); timer.stop()
        report['runs'].append(dict(theme=theme,elapsed=elapsed,paint=stats(paints),gui=stats(ticks),
                                   timeline_paint=stats(timeline_paints), timeline_damage_fraction=sum(timeline_damage)/max(1,len(timeline_damage)), delivered_frames=len(frames),
                                   delivered_fps=round(len(frames)/elapsed,2),decoders=len(w.transport.decoders),cache_misses=list(cache_misses)))
        w.grab().save(str(out/(theme+'.png')))
    # Exercise real timeline interactions while video is running. Escape cancels
    # the drag so the fixture and all layer timings remain intact.
    w.seek(.5); wait(500); w.transport.play(); wait(300)
    timeline=w.timeline
    candidate=next(i for i in p.timeline if i.track in p.video_tracks and not timeline.visible_item_rect(i).isEmpty())
    origin=timeline.visible_item_rect(candidate).center().toPoint()
    QTest.mousePress(timeline.viewport(),Qt.LeftButton,pos=origin)
    drag=[]
    for n in range(40):
        start=time.perf_counter(); QTest.mouseMove(timeline.viewport(),origin+QPoint(n%20,0)); app.processEvents()
        drag.append((time.perf_counter()-start)*1000)
    QTest.keyClick(timeline.viewport(),Qt.Key_Escape); QTest.mouseRelease(timeline.viewport(),Qt.LeftButton,pos=origin)
    w.transport.pause()
    scrub=[]
    for n in range(80):
        at=.25+(n%30)*.21
        start=time.perf_counter(); w.transport.scrub(at); app.processEvents()
        scrub.append((time.perf_counter()-start)*1000)
    w.transport.scrub(4.25); w.transport.finish_scrub(); wait(800)
    report['drag_while_playing']=stats(drag); report['scrub']=stats(scrub)
    report['settled_playhead']=w.project.playhead
    report['settled_visible_layers']=len(w.preview._visible_items())
    report['passed']=(report['settled_visible_layers']==3 and abs(w.project.playhead-4.25)<1e-6
                      and all(r['delivered_frames']>20 for r in report['runs']))
    if profiled:
        with (out/'profile.txt').open('w') as stream:
            pstats.Stats(profiler,stream=stream).sort_stats('cumtime').print_stats(65)
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)
    w.close(); QThreadPool.globalInstance().waitForDone(15000); app.processEvents()
    return 0 if report['passed'] else 1
