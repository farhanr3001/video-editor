"""Real decoder playback checks for adjacent clips and intentional gaps."""
def run(output):
    import os,json,time,traceback
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEventLoop,QTimer
    from .ui import MainWindow
    from .model import Project,MediaItem,TimelineItem,Transform
    from .process import run as process
    for name,color in (('red','red'),('blue','blue')):
        sentinel=['-vf',"drawbox=color=yellow:t=fill:enable='lt(t,1)'"] if name=='blue' else []
        process(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color=c={color}:s=320x180:r=30:d=3','-f','lavfi','-i','sine=frequency=440:duration=3']+sentinel+['-c:a','aac','-c:v','libx264','-pix_fmt','yuv420p',str(output/(name+'.mp4'))],capture_output=True,check=True)
    app=QApplication([]); w=MainWindow(); w.show(); w.autosave_timer.stop(); report={}
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    try:
        for case,same,gap in (('different_sources',False,0),('source_jump',True,0),('real_gap',False,.25),('blurred_sources',False,0)):
            media=[MediaItem(name,str(output/(name+'.mp4')),'video',name,3,320,180,30,True) for name in ('red','blue')]
            p=Project(media=media,timeline=[TimelineItem('left','red','video_1',0,1,transform=Transform(.5,.5)),TimelineItem('right','red' if same else 'blue','video_1',1+gap,1,1.5,transform=Transform(.5,.5))])
            p.timeline += [TimelineItem('audio-left','red','audio_1',0,1),TimelineItem('audio-right','red' if same else 'blue','audio_1',1+gap,1,1.5)]
            if case=='blurred_sources':
                for item in p.timeline:
                    if item.track in p.video_tracks:item.effects=[dict(name='Gaussian Blur',horizontal=12,vertical=12)]
            p.settings.width=320; p.settings.height=180; p.settings.fps=30; w.set_project(p)
            deadline=time.monotonic()+5
            while not w.preview._visible_items() and time.monotonic()<deadline:wait(20)
            assert w.preview._visible_items(),'First decoder did not produce a frame'
            w.transport.seek(0); w.transport.play(); samples=[]; primed_audio=None; audio_reused=False; invalid_source_frames=0
            audio_item=p.item_by_id('audio-right'); audio_key=(audio_item.media_id,round(audio_item.in_point-audio_item.start,4),1.,'audio:audio_1')
            deadline=time.monotonic()+4
            while w.transport.position<1.55 and time.monotonic()<deadline:
                wait(10); t=w.transport.position
                if not same:
                    for key,image in w.preview.frames.items():
                        if key[0]=='blue' and image.pixelColor(100,100).blue()<100:invalid_source_frames+=1
                if .5<t<1 and audio_key in w.transport.decoders:primed_audio=w.transport.decoders[audio_key][0]
                if 1+gap<t<1.5 and primed_audio is not None:audio_reused=w.transport.decoders.get(audio_key,(None,))[0] is primed_audio
                if .9<t<1.5:
                    visible=w.preview._visible_items(); samples.append((round(t,4),bool(visible)))
            w.transport.pause()
            assert primed_audio is not None and audio_reused,'Audio was not prepared before the cut and reused at activation'
            assert invalid_source_frames==0,'Trimmed-out yellow source prefix was published during cut preloading/playback'
            at_cut=[visible for t,visible in samples if .95<t<1.15]
            assert at_cut,'Missing cut samples'
            if gap:assert any(not visible for t,visible in samples if 1.02<t<1.2),'Real gap was incorrectly filled'
            else:assert all(at_cut),f'Black flash at cut: {samples}'
            assert any(visible for t,visible in samples if t>1.3),'Incoming clip did not decode'
            key=w.preview.active_frames.get('right'); incoming=w.preview.frames.get(key)
            assert incoming is not None and not incoming.isNull(),'Incoming clip is still relying on the outgoing frame'
            if not same:assert incoming.pixelColor(100,100).blue()>200,'Incoming blue clip was not displayed'
            scrub_samples=[]
            if not gap:
                for position in (1.05,.99,.95,1.01,1.05,.99):
                    w.transport.seek(position); scrub_samples.append(bool(w.preview._visible_items())); wait(80)
                assert all(scrub_samples),'Black frame while scrubbing backwards/forwards over adjacent clips'
            report[case]=dict(samples=len(samples),black_samples_at_cut=sum(not v for v in at_cut),scrub_black_samples=sum(not v for v in scrub_samples),incoming_frame_decoded=True,audio_prepared_and_reused=audio_reused,trimmed_out_source_frames=invalid_source_frames)
        report['passed']=True
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:
        w.close(); (output/'report.json').write_text(json.dumps(report,indent=2)); app.processEvents()
    return 0 if report.get('passed') else 1
