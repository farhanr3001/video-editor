"""Read-only real-project high-speed playback check on an isolated profile."""
def run(output,project_path):
    import os,time,json,hashlib,sys
    from pathlib import Path
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    os.environ['KINETIC_SAMPLING_DIAGNOSTIC']='1'
    from PySide6.QtCore import QTimer,QEventLoop,Qt,QThreadPool
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    from .model import Project
    from . import close_guard
    close_guard.DIAGNOSTIC_CLEANUP=True
    app=QApplication.instance() or QApplication([])
    app.setProperty('kineticTestDiscardUnsaved',True)
    source=Path(project_path).resolve();digest=hashlib.sha256(source.read_bytes()).hexdigest()
    original=Project.load(source)
    fast=next(i for i in original.timeline if i.track in original.video_tracks and i.speed>3)
    report=dict(passed=False,project=source.name,project_sha256=digest,
                frozen=bool(getattr(sys,'frozen',False)),runs=[])
    w=MainWindow();w.resize(1500,950);w.show();w.autosave_timer.stop()
    w.request_waveform=lambda _:None;w.preview_quality.request=lambda:None
    w.transport.set_monitor_gain(0.)
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    cases=[fast.speed]*3
    if os.environ.get('KINETIC_SPEED_EXTENDED')=='1':cases += [1.,1.5,2.]
    try:
        for n,speed in enumerate(cases):
            p=Project.from_dict(original.to_dict());p.path=''
            for item in p.timeline:
                if item.link_id==fast.link_id and item.link_id:item.speed=speed
            w.set_project(p);t=w.transport;w.seek(max(0,fast.start-1.3));wait(1400)
            samples=[];heartbeat=[];last=[time.perf_counter()]
            timer=QTimer();timer.setTimerType(Qt.PreciseTimer);timer.setInterval(16)
            def sample():
                now=time.perf_counter();heartbeat.append((now-last[0])*1000);last[0]=now
                d=w.preview.gpu.diagnostics()
                samples.append(dict(at=t.position,time=now,frames=d.get('gpu_source_frames',0),
                    source=d.get('source_frame_us',{}),backend=d.get('graphics_backend'),
                    decoders=d.get('active_decoders',[]),error=d.get('renderer_error')))
            timer.timeout.connect(sample);timer.start();t.play();wait(round((fast.duration+2.6)*1000));t.pause();timer.stop()
            key=str((fast.media_id,round(fast.in_point-fast.start*speed,4),speed,'video'))
            interior=[s for s in samples if fast.start+.25<s['at']<fast.start+fast.duration-.1]
            changed=[];stamp=None
            for s in interior:
                current=s['source'].get(key)
                if current is not None and current!=stamp:changed.append(s['time']);stamp=current
            edges=([interior[0]['time']]+changed+[interior[-1]['time']]) if interior else []
            max_hold=max((b-a for a,b in zip(edges,edges[1:])),default=999)*1000
            ordered=sorted(heartbeat)
            result=dict(speed=speed,samples=samples,max_source_hold_ms=max_hold,
                heartbeat_p95_ms=ordered[int(len(ordered)*.95)],heartbeat_max_ms=max(heartbeat),
                changing_status_samples=len(changed),passed=bool(interior and len(changed)>15 and max_hold<300
                    and all(s['backend']=='Direct3D11' and not s['error'] for s in interior)))
            report['runs'].append(result)
            (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            if n==0:
                w.seek(fast.start+fast.duration*.5);wait(600)
                w.preview.gpu.capture().save(str(out/'preview.png'))
        report['owner_project_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==digest
        report['passed']=report['owner_project_unchanged'] and all(r['passed'] for r in report['runs'])
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(dict(passed=report['passed'],runs=[{k:v for k,v in r.items() if k!='samples'} for r in report['runs']])),flush=True)
    finally:
        w.close();QThreadPool.globalInstance().waitForDone(15000);app.processEvents()
    return 0 if report['passed'] else 1
