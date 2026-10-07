"""Real decoder pause/resume checks in a hidden, disposable native editor."""
def run(folder):
    import os, json, time, traceback
    from pathlib import Path
    out=Path(folder).resolve(); out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    from .process import run as process
    from .config import save_settings
    save_settings({'update_check_on_startup':False})
    from PySide6.QtCore import Qt, QTimer, QEventLoop
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    from .model import Project, MediaItem, TimelineItem, Crop, Transform
    source=out/'resume-fixture.mp4'
    process(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=30',
             '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','16',
             '-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-c:a','aac',str(source)],
            check=True,capture_output=True)
    app=QApplication.instance() or QApplication([]); app.setQuitOnLastWindowClosed(False)
    w=MainWindow(); w.setAttribute(Qt.WA_DontShowOnScreen); w.resize(1100,760); w.show()
    w.autosave_timer.stop(); w.transport.set_monitor_gain(0.)
    import sys
    report={'passed':False,'platform':app.platformName(),'frozen':bool(getattr(sys,'frozen',False)),'cases':[]}
    delivered=[]; original=w.transport.frame
    def frame(key,image):
        delivered.append((time.monotonic(),key,image.cacheKey()))
        original(key,image)
    w.transport.frame=frame
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    try:
        for layered in (False,True):
            media=MediaItem('resume',str(source),'video','Resume fixture',16,640,360,30,True)
            p=Project(media=[media]); p.settings.width=640;p.settings.height=360
            p.video_tracks=['video_1','video_2','video_3'] if layered else ['video_1']
            for lane in p.video_tracks:
                for n in range(2):
                    item=TimelineItem(lane+str(n),media.id,lane,n*4.,4.,n*6.)
                    if layered and lane=='video_1':item.effects=[dict(name='Gaussian Blur',horizontal=12,vertical=12)]
                    if layered and lane=='video_3':item.crop=Crop(0,0,.3,.5);item.transform=Transform(y=.2,scale=.5)
                    p.timeline.append(item)
            p.timeline.extend(TimelineItem('audio'+str(n),media.id,'audio_1',n*4.,4.,n*6.,role='source_audio') for n in range(2))
            w.set_project(p); w.seek(.5); w.toggle_play(); wait(1000)
            assert delivered and w.transport.playing,'Native video did not start'
            for cycle in range(6):
                w.toggle_play(); wait(100)
                paused=w.transport.position; wait(100)
                assert abs(w.transport.position-paused)<.02,'Paused clock moved'
                before=len(delivered); start=time.monotonic(); w.toggle_play()
                deadline=start+1
                while len(delivered)==before and time.monotonic()<deadline:wait(10)
                first_ms=(delivered[before][0]-start)*1000 if len(delivered)>before else None
                wait(250)
                active=[key for key,(_,_,sink) in w.transport.decoders.items() if sink and key not in w.transport.warm_keys]
                frames=[entry for entry in delivered[before:] if entry[1] in active]
                audio=[player for key,(player,_,sink) in w.transport.decoders.items() if sink is None and key not in w.transport.warm_keys]
                assert first_ms is not None and first_ms<1000,'Resume delivered no video while clock/audio continued'
                assert len(frames)>=3 and len({f[2] for f in frames})>=2,'Video froze after resuming'
                assert audio and any(player.position()>0 for player in audio),'Audio decoder did not advance'
                assert w.transport.position>paused+.15,'Resumed clock did not advance'
                report['cases'].append(dict(layered=layered,cycle=cycle,first_frame_ms=round(first_ms,1),frames=len(frames),video_changes=True,audio_advances=True))
            w.toggle_play(); w.seek(3.85); w.toggle_play(); wait(550)
            assert w.transport.position>4.2 and w.preview._visible_items(),'Resume/cut did not reach incoming video'
            w.toggle_play();w.transport.scrub(1.2);w.transport.finish_scrub();wait(100)
            before=len(delivered);w.toggle_play();wait(350)
            assert len(delivered)>before and w.preview._visible_items(),'Scrub then resume failed'
            w.toggle_play()
        reference=os.environ.get('KINETIC_RESUME_PROJECT')
        if reference:
            import hashlib
            original_path=Path(reference);before=hashlib.sha256(original_path.read_bytes()).hexdigest()
            project=Project.load(str(original_path));w.set_project(project);wait(1000)
            for position in (5.,21.,54.,72.):
                if position+1>=project.duration:continue
                # Prime at a fixed timestamp. A slow first decode must not run
                # past a short reference clip before the resume check starts.
                w.seek(position);wait(650)
                deadline=time.monotonic()+5
                def reference_frames(entries):
                    active=set(w.preview.active_frames.values())
                    return [f for f in entries if f[1] in active]
                while not reference_frames(delivered[-12:]) and time.monotonic()<deadline:wait(50)
                assert reference_frames(delivered[-12:]),'Reference source never decoded before pause/resume'
                w.toggle_play();wait(150)
                for cycle in range(2):
                    w.toggle_play();wait(100);start=time.monotonic();count=len(delivered);w.toggle_play()
                    wait(450)
                    active=set(w.preview.active_frames.values())
                    frames=[f for f in delivered[count:] if f[1] in active]
                    detail=dict(reference_position=position,cycle=cycle,frames=len(frames),frame_changes=len({f[2] for f in frames}),
                                first_frame_ms=round((frames[0][0]-start)*1000,1) if frames else None,
                                clock_position=w.transport.position,
                                delivered_total=len(delivered),active_keys=[str(k) for k in active],
                                pending_seeks={str(k):v for k,v in w.transport._pending_video_seeks.items()},
                                decoders=[dict(kind='video' if sink else 'audio',position=player.position(),state=str(player.playbackState()))
                                          for key,(player,_,sink) in w.transport.decoders.items() if key not in w.transport.warm_keys])
                    report['cases'].append(detail)
                    assert len(frames)>=3 and len({f[2] for f in frames})>=2,'Reference-project video froze after resume'
                    detail['video_changes']=True
                w.toggle_play()
            assert hashlib.sha256(original_path.read_bytes()).hexdigest()==before,'Reference project changed'
            report['reference_unchanged']=True
        report['passed']=True
    except Exception:
        report['passed']=False;report['error']=traceback.format_exc()
    finally:
        w.close();app.processEvents();(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
