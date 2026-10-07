"""Real native editing endurance; disposable media/profile, no owner data."""
def run(folder):
    import os, sys, json, time, copy, gc, traceback, ctypes, threading, faulthandler
    from pathlib import Path
    out=Path(folder).resolve(); out.mkdir(parents=True,exist_ok=True)
    diagnostic_trace=(out/'watchdog-stacks.log').open('w',encoding='utf-8')
    faulthandler.enable(diagnostic_trace)
    faulthandler.dump_traceback_later(30,repeat=True,file=diagnostic_trace)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    from .process import run as run_process
    from .config import save_settings
    save_settings({'update_check_on_startup':False})
    from PySide6.QtCore import QTimer, QEventLoop, Qt, QPoint, QEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QColor
    from .ui import MainWindow
    from .model import Project, TimelineItem, Caption, Crop, Transform
    from .media import probe
    from .workspace import set_page
    from .close_guard import DIAGNOSTIC_CLEANUP
    from .dialog_jobs import active_dialog_threads
    import kinetic_cut.close_guard as close_guard
    close_guard.DIAGNOSTIC_CLEANUP=True
    source=out/'generated-stress.mp4'
    run_process(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=1280x720:rate=60',
                 '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','12','-c:v','libx264','-preset','ultrafast',
                 '-crf','25','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True,capture_output=True)
    app=QApplication.instance() or QApplication([]); app.setQuitOnLastWindowClosed(False)
    errors=[]
    previous_exception=sys.excepthook
    sys.excepthook=lambda *exc:(errors.append(''.join(traceback.format_exception(*exc))),previous_exception(*exc))
    w=MainWindow(); w.resize(1480,900); w.show(); w.autosave_timer.stop()
    media=probe(str(source))
    # Hundreds of items; simultaneous same-source crops, blur, source jumps,
    # graphics/captions and actual waveform/proxy/missing-media services.
    p=Project(name='Disposable endurance'); p.media=[media]
    p.video_tracks=['video_1','video_2','video_3','video_4']
    p.settings.width=720; p.settings.height=1280
    for n in range(60):
        for lane in range(1,4):
            item=TimelineItem(f'v{lane}-{n}',media.id,f'video_{lane}',n*2.,2.,float(n%5))
            if lane==1:item.effects=[{'name':'Gaussian Blur','enabled':True,'horizontal':24.,'vertical':24.,'border':'Reflect'}]
            elif lane==2:item.crop=Crop(.1,.05,.7,.9); item.transform=Transform(y=.64,scale=.55)
            else:item.crop=Crop(0.,0.,.3,.45); item.transform=Transform(y=.22,scale=1.)
            p.timeline.append(item)
        p.timeline.append(TimelineItem(f'a{n}',media.id,'audio_1',n*2.,2.,float(n%5),role='source_audio'))
        p.captions.append(Caption(f'c{n}',n*2.,n*2.+1.8,f'Native stability cycle {n}'))
    base=copy.deepcopy(p); alternate=copy.deepcopy(p); alternate.created_at+=1; alternate.name='Second disposable project'
    w.set_project(p)
    report={'frozen':bool(getattr(sys,'frozen',False)),'seconds_requested':float(os.environ.get('KINETIC_STABILITY_SECONDS','900')),
            'source':str(source),'timeline_items':len(p.timeline),'samples':[],'actions':{},'errors':errors,'passed':False}
    def count(name):report['actions'][name]=report['actions'].get(name,0)+1
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def resources():
        from ctypes import wintypes as wt
        class Memory(ctypes.Structure):
            _fields_=[('cb',wt.DWORD),('faults',wt.DWORD),('peak_ws',ctypes.c_size_t),('ws',ctypes.c_size_t),
                      ('peak_pool',ctypes.c_size_t),('pool',ctypes.c_size_t),('peak_nonpool',ctypes.c_size_t),
                      ('nonpool',ctypes.c_size_t),('pagefile',ctypes.c_size_t),('peak_pagefile',ctypes.c_size_t),('private',ctypes.c_size_t)]
        kernel=ctypes.WinDLL('kernel32'); kernel.GetCurrentProcess.restype=wt.HANDLE
        proc=kernel.GetCurrentProcess(); handles=wt.DWORD(); memory=Memory(); memory.cb=ctypes.sizeof(memory)
        kernel.GetProcessHandleCount.argtypes=[wt.HANDLE,ctypes.POINTER(wt.DWORD)]
        psapi=ctypes.WinDLL('psapi'); psapi.GetProcessMemoryInfo.argtypes=[wt.HANDLE,ctypes.c_void_p,wt.DWORD]
        assert kernel.GetProcessHandleCount(proc,ctypes.byref(handles))
        assert psapi.GetProcessMemoryInfo(proc,ctypes.byref(memory),memory.cb)
        from PySide6.QtMultimedia import QMediaPlayer
        from PySide6.QtCore import QFile
        # Use documented process counters. Querying raw native object tables
        # can race decoder teardown and must not be part of the soak itself.
        return dict(private_bytes=memory.private,working_set=memory.ws,handles=handles.value,
                    qt_players=len(w.findChildren(QMediaPlayer)),qt_files=len(w.findChildren(QFile)),
                    python_threads=threading.active_count(),workers=len(w._workers),decoders=len(w.transport.decoders),
                    frame_jobs=len(w.transport._frame_jobs),history=len(w._history))
    frames=[0]; original_frame=w.transport.frame
    def frame(*args):frames[0]+=1; original_frame(*args)
    w.transport.frame=frame
    gaps=[]; previous=[time.monotonic()]; last_heartbeat=[0.]
    heartbeat=QTimer(w); heartbeat.setTimerType(Qt.PreciseTimer); heartbeat.setInterval(20)
    def beat():
        now=time.monotonic(); gaps.append(now-previous[0]); previous[0]=now
        if now-last_heartbeat[0]>1:
            (out/'gui-heartbeat.txt').write_text(str(time.time()),encoding='utf-8'); last_heartbeat[0]=now
    heartbeat.timeout.connect(beat); heartbeat.start()
    wait(1800); started=time.monotonic(); cycle=0
    try:
        while time.monotonic()-started<report['seconds_requested']:
            cycle+=1
            (out/'phase.txt').write_text(f'cycle={cycle} theme/play',encoding='utf-8')
            w.apply_theme(('default','final_cut_obsidian','ableton_gray')[cycle%3],save=False); count('theme')
            w.seek(.2); w.transport.play(); count('play')
            for n in range(20):
                (out/'phase.txt').write_text(f'cycle={cycle} edit={n}',encoding='utf-8')
                # Edit while actual decoded video/audio is playing; one-step
                # undo/redo preserves live playhead and source ownership.
                item=w.project.item_by_id(f'v2-{n%6}')
                item.transform.rotation=(n%5)-2; item.duration=1.9 if n%2 else 2
                w.model_changed(); count('property_trim'); w.undo(); w.redo(); count('undo_redo')
                wait(140)
            w.transport.pause(); count('pause')
            (out/'phase.txt').write_text(f'cycle={cycle} scrub',encoding='utf-8')
            for n in range(100):
                w.transport.scrub((n*1.371+cycle)%12); count('seek')
                wait(8)
            w.transport.scrub(4.25); w.transport.finish_scrub(); wait(300)
            assert abs(w.project.playhead-4.25)<1e-6
            # Real native mouse drag + Escape cancellation.
            tl=w.timeline
            clip=next(i for i in w.project.timeline if i.track in w.project.video_tracks
                      and not tl.visible_item_rect(i).isEmpty())
            rect=tl.visible_item_rect(clip)
            origin=rect.center().toPoint(); QTest.mousePress(tl.viewport(),Qt.LeftButton,pos=origin)
            QTest.mouseMove(tl.viewport(),origin+QPoint(30,0)); QTest.keyClick(tl.viewport(),Qt.Key_Escape)
            QTest.mouseRelease(tl.viewport(),Qt.LeftButton,pos=origin); count('native_drag_cancel')
            for page in (1,0,2,0):set_page(w,page); count('page_switch')
            (out/'phase.txt').write_text(f'cycle={cycle} save/switch',encoding='utf-8')
            # Remove an owned source while players have it open; relink/reload
            # independently covers recovery from actual Windows delete sharing.
            if cycle%3==0:
                duplicate=out/'delete-in-use.mp4'; duplicate.write_bytes(source.read_bytes())
                disposable=probe(str(duplicate)); lost=Project(media=[disposable],timeline=[TimelineItem('delete',disposable.id,'video_1',0,3)])
                w.set_project(lost); w.seek(1); wait(160)
                # The import's FFmpeg waveform job has its own file-sharing
                # policy. Finish that job, then delete with Qt playback live.
                deadline=time.monotonic()+10
                while w._workers and time.monotonic()<deadline:wait(50)
                assert not w._workers,'Import preparation did not finish'
                duplicate.unlink(); count('delete_in_use'); wait(300)
            saved=out/'endurance.kcut'; copy.deepcopy(base).save(str(saved)); loaded=Project.load(str(saved))
            assert len(loaded.timeline)==240 and len(loaded.captions)==60; count('save_load')
            w.set_project(copy.deepcopy(alternate if cycle%2 else base)); count('project_switch')
            wait(250); gc.collect()
            sample=resources(); sample.update(seconds=round(time.monotonic()-started,2),cycle=cycle,frames=frames[0])
            report['samples'].append(sample)
            (out/'heartbeat.json').write_text(json.dumps(sample),encoding='utf-8')
            if cycle==1 or cycle%20==0:w.grab().save(str(out/f'cycle-{cycle}.png'))
        heartbeat.stop(); w.transport.pause(); wait(1500); gc.collect()
        report['elapsed_seconds']=time.monotonic()-started
        report['cycles']=cycle; report['delivered_frames']=frames[0]
        report['gui_max_gap_seconds']=max(gaps,default=0)
        report['gui_p95_gap_seconds']=sorted(gaps)[int(len(gaps)*.95)] if gaps else None
        report['final_resources']=resources()
        warm=report['samples'][min(3,len(report['samples'])-1)]
        report['resource_growth_after_warmup']={k:report['final_resources'][k]-warm[k] for k in ('private_bytes','handles','python_threads')}
        w.grab().save(str(out/'final.png'))
        assert not errors,errors
        assert frames[0]>max(30,cycle*10),'Native decoder did not deliver frames'
        assert max(gaps,default=0)<10,'GUI stopped responding for more than 10 seconds'
        assert all(s['frame_jobs']<=2 and s['history']<=100 for s in report['samples'])
        assert report['resource_growth_after_warmup']['private_bytes']<256*1024**2,'Unexpected sustained private-memory growth; inspect samples'
        assert report['resource_growth_after_warmup']['handles']<250,'Native handles accumulated after warmup'
        report['passed']=True
    except BaseException:
        report['failure']=traceback.format_exc(); traceback.print_exc()
    finally:
        heartbeat.stop(); w.close()
        deadline=time.monotonic()+30
        while (w._workers or active_dialog_threads()) and time.monotonic()<deadline:wait(50)
        report['shutdown_workers']=len(w._workers); report['shutdown_dialog_threads']=len(active_dialog_threads())
        w.close(); wait(500)
        report['closed']=not w.isVisible()
        report['passed']=report['passed'] and report['closed'] and not report['shutdown_workers'] and not report['shutdown_dialog_threads']
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='samples'}),flush=True)
        sys.excepthook=previous_exception
        faulthandler.cancel_dump_traceback_later()
    return 0 if report['passed'] else 1
