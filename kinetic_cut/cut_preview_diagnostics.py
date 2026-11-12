"""Real-project cut handoffs; isolated home, no owner project/media writes."""
def run(output,project_path):
    import os,sys,time,json,hashlib
    from pathlib import Path
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ.update(KINETIC_CUT_HOME=str(out/'home'),KINETIC_SAMPLING_DIAGNOSTIC='1')
    from PySide6.QtCore import QTimer,QEventLoop,Qt,QThreadPool
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    from .model import Project
    from . import close_guard
    close_guard.DIAGNOSTIC_CLEANUP=True
    app=QApplication.instance() or QApplication([]);app.setProperty('kineticTestDiscardUnsaved',True)
    source=Path(project_path).resolve();digest=hashlib.sha256(source.read_bytes()).hexdigest()
    p=Project.load(source);p.path=''
    w=MainWindow();w.resize(1500,950);w.show();w.autosave_timer.stop()
    w.request_waveform=lambda _:None;w.preview_quality.request=lambda:None
    w.set_project(p);t=w.transport;t.set_monitor_gain(0.)
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),project_sha256=digest,runs=[])
    try:
        wait(1000)
        cases=[(19.5,23.7),(28.7,34.)]*2
        if os.environ.get('KINETIC_CUT_LONG_PASS')=='1':cases.append((19.5,35.5))
        for n,(start,end) in enumerate(cases):
            w.seek(start);wait(1000);samples=[];last=[time.monotonic()]
            timer=QTimer();timer.setTimerType(Qt.PreciseTimer);timer.setInterval(12)
            def sample():
                now=time.monotonic();d=w.preview.gpu.diagnostics();at=d.get('sampling_time',t.position)
                item=next((i for i in p.timeline if i.track=='video_2' and i.start<=at<i.start+i.duration),None)
                key=str((item.media_id,round(item.in_point-item.start*item.speed,4),item.speed,'video')) if item else ''
                stamp=d.get('source_frame_us',{}).get(key)
                samples.append(dict(wall=now,gui_ms=(now-last[0])*1000,at=at,item=item.id if item else '',
                    stamp=stamp,error_ms=(item.source_time(at)*1e6-stamp)/1000 if item and stamp is not None else None,
                    backend=d.get('graphics_backend'),decoder=d.get('active_decoders'),error=d.get('renderer_error')))
                last[0]=now
            timer.timeout.connect(sample);timer.start();t.play();wait(round((end-start)*1000));t.pause();timer.stop()
            settled=[s for s in samples if start+.15<s['at']<end-.05]
            errors=[s['error_ms'] for s in settled if s['error_ms'] is not None]
            bad=sum(s['error_ms'] is None or abs(s['error_ms'])>150 for s in settled)
            result=dict(start=start,end=end,samples=samples,bad_samples=bad,
                max_abs_source_error_ms=max(map(abs,errors),default=999),
                max_gui_interval_ms=max(s['gui_ms'] for s in samples),
                passed=bool(errors and bad==0 and all(s['backend']=='Direct3D11' and not s['error'] for s in settled)))
            report['runs'].append(result);(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        # Settle actual native pixels at a cut, separately from the timing runs.
        w.seek(21.6);wait(800);image=w.preview.gpu.capture()
        image.save(str(out/'preview.png'));report['visible_preview']=not image.isNull()
        report['owner_project_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==digest
        report['passed']=report['visible_preview'] and report['owner_project_unchanged'] and all(r['passed'] for r in report['runs'])
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(dict(passed=report['passed'],runs=[{k:v for k,v in r.items() if k!='samples'} for r in report['runs']])),flush=True)
    finally:
        w.close();QThreadPool.globalInstance().waitForDone(15000);app.processEvents()
    return 0 if report['passed'] else 1
