"""Isolated native timeline/playback scheduling benchmark; never modifies its project."""
def run(output, project_path, with_waveforms=True):
    import os, sys, json, time, math, hashlib, cProfile, pstats
    from pathlib import Path
    
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['KINETIC_CUT_HOME'] = str(out / 'home')
    from kinetic_cut.process import install_desktop_process_policy
    install_desktop_process_policy()
    from PySide6.QtCore import Qt, QTimer, QEventLoop, QPointF, QEvent, QThreadPool
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from kinetic_cut.model import Project
    from kinetic_cut.ui import MainWindow
    
    source = Path(project_path).resolve()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    p = Project.load(source)
    p.path = ''  # Any app autosave belongs only to the isolated diagnostic home.
    app = QApplication([])
    w = MainWindow()
    screen = app.primaryScreen().availableGeometry()
    w.resize(min(1900, screen.width()), min(1080, screen.height()))
    w.show()
    w.autosave_timer.stop()
    # Exclude fresh 13-minute waveform generation from playback/event-loop diagnosis.
    w.request_waveform = lambda media: None
    w.set_project(p)
    t = w.timeline
    if with_waveforms:
        from kinetic_cut.waveforms import waveform
        for media in p.media:
            if media.has_audio or media.kind=='audio':
                t.set_waveform(media.id,waveform(media.path,w.settings.get('ffmpeg','ffmpeg')))
    t.pixels_per_second = (t.viewport().width()-t.LABEL_WIDTH-90)/p.duration
    t._range()
    
    def wait(ms):
        loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()
    
    def mouse(kind, pos, button=Qt.NoButton, buttons=Qt.LeftButton):
        global_pos = QPointF(t.viewport().mapToGlobal(pos.toPoint()))
        app.sendEvent(t.viewport(), QMouseEvent(kind, pos, global_pos, button, buttons, Qt.NoModifier))
    
    def stats(values):
        values = sorted(values)
        return dict(count=len(values), mean_ms=round(sum(values)/max(1,len(values)),3),
                    p95_ms=round(values[min(len(values)-1,int(len(values)*.95))],3) if values else 0,
                    max_ms=round(max(values,default=0),3))
    
    samples = {}; positions = []; paints = []; pending = [None]; no_readback = [False]
    delivered=[]
    original_frame=w.transport.frame
    def frame(key,image):
        delivered.append((time.perf_counter(),key,image.cacheKey()))
        original_frame(key,image)
    w.transport.frame=frame
    def timed(name, function):
        def wrapper(*args):
            start = time.perf_counter()
            try: return function(*args)
            finally: samples.setdefault(name, []).append((time.perf_counter()-start)*1000)
        return wrapper
    
    original_paint = t.paintEvent
    def timeline_paint(event):
        start = time.perf_counter(); original_paint(event)
        samples.setdefault('timeline_paint', []).append((time.perf_counter()-start)*1000)
        now = time.perf_counter(); paints.append(now)
        if pending[0] is not None:
            samples.setdefault('pointer_to_paint', []).append((now-pending[0])*1000)
            pending[0] = None
    t.paintEvent = timeline_paint
    w.preview.paintEvent = timed('preview_paint', w.preview.paintEvent)
    t.marquee_controller.update = timed('marquee_update', t.marquee_controller.update)
    original_poll = w.transport.poll_frames
    def poll():
        if not no_readback[0]: timed('frame_readback', original_poll)()
    w.transport.frame_timer.timeout.disconnect()
    w.transport.frame_timer.timeout.connect(poll)
    
    wait(1400)
    report = {'project':source.name, 'project_sha256':before, 'frozen':bool(getattr(sys,'frozen',False)), 'window':[w.width(),w.height()],
              'source':[(m.name,m.width,m.height,m.fps) for m in p.media],
              'clips':len(p.timeline), 'waveform_generation_excluded':True,
              'waveforms_present':bool(t.waveforms), 'runs':[]}
    for name in ('paused','playing','playing_no_canvas','playing_no_readback','paused_again'):
        w.transport.pause(); no_readback[0]=False; w.preview.setUpdatesEnabled(True)
        w.seek(162.6); wait(500)
        if name.startswith('playing'): w.transport.play(); wait(500)
        if name=='playing_no_canvas': w.preview.setUpdatesEnabled(False)
        if name=='playing_no_readback': no_readback[0]=True; w.preview.setUpdatesEnabled(False)
        section=t._sections()['video']
        anchor=QPointF(t.x_for_time(p.duration)+35,section.center().y())
        mouse(QEvent.MouseButtonPress,anchor,Qt.LeftButton)
        assert t.drag_mode=='marquee', (name,t.drag_mode,anchor)
        samples.clear(); paints.clear(); positions.clear(); delivered.clear(); pending[0]=None
        audio_before={str(k):player.position() for k,(player,_,sink) in w.transport.decoders.items() if sink is None}
        previous=[time.perf_counter()]; started=previous[0]; n=[0]
        timer=QTimer(); timer.setTimerType(Qt.PreciseTimer); timer.setInterval(7)
        def move():
            now=time.perf_counter(); samples.setdefault('input_interval',[]).append((now-previous[0])*1000); previous[0]=now
            # Continuous expanding/contracting box, safely away from edge autoscroll.
            phase=(now-started)*2.5
            pos=QPointF(t.LABEL_WIDTH+70+(t.viewport().width()-t.LABEL_WIDTH-210)*(.5+.45*math.sin(phase)),
                        section.top()+30+(section.height()-60)*(.5+.4*math.cos(phase)))
            pending[0]=now; positions.append(pos); mouse(QEvent.MouseMove,pos); n[0]+=1
        timer.timeout.connect(move)
        profile=cProfile.Profile(); profile.enable(); timer.start(); wait(4000); timer.stop(); profile.disable()
        elapsed=time.perf_counter()-started
        values={key:stats(value) for key,value in samples.items()}
        values['paint_interval']=stats([(b-a)*1000 for a,b in zip(paints,paints[1:])])
        audio_after={str(k):player.position() for k,(player,_,sink) in w.transport.decoders.items() if sink is None}
        report['runs'].append(dict(mode=name,seconds=elapsed,input_events=n[0],
                                   delivered_frames=len(delivered),audio_advance_ms={k:v-audio_before.get(k,v) for k,v in audio_after.items()},
                                   selection_paints_per_second=round(len(paints)/elapsed,2),metrics=values))
        w.grab().save(str(out/(name+'.png')))
        with (out/(name+'-profile.txt')).open('w') as stream:
            pstats.Stats(profile,stream=stream).sort_stats('cumtime').print_stats(45)
        mouse(QEvent.MouseButtonRelease,positions[-1] if positions else anchor,Qt.LeftButton,Qt.NoButton)
        print(json.dumps(report['runs'][-1]),flush=True)
    no_readback[0]=False; w.preview.setUpdatesEnabled(True); w.transport.pause()
    w.close(); QThreadPool.globalInstance().waitForDone(15000); app.processEvents()
    report['project_unchanged']=before==hashlib.sha256(source.read_bytes()).hexdigest()
    live=next(r for r in report['runs'] if r['mode']=='playing')
    report['passed']=report['project_unchanged'] and live['delivered_frames']>20 and all(v>3000 for v in live['audio_advance_ms'].values())
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert report['passed']
    return 0
