"""Real nested UI, lossless-alpha playback and export check in an isolated home."""
def run(output):
    import os,sys,json,time,traceback,wave,copy
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer,QEventLoop,QThreadPool
    from PySide6.QtGui import QImage,QColor,QFont
    from .ui import MainWindow
    from .model import Project,MediaItem,TimelineItem,Transform,Caption
    from .theme import STYLESHEET
    from .exporter import export,PRESETS
    from .process import run as process
    app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET); app.setFont(QFont('Segoe UI',9))
    w=MainWindow(); w.resize(1500,900); w.show(); w.autosave_timer.stop(); report={'frozen':bool(getattr(sys,'frozen',False))}
    def wait(ms=100):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    try:
        for name,color in [('blue','#2255cc'),('orange','#ee8833')]:
            image=QImage(320,180,QImage.Format_RGB32); image.fill(QColor(color)); image.save(str(output/(name+'.png')))
        audio=output/'tone.wav'
        with wave.open(str(audio),'wb') as f:
            f.setparams((1,2,48000,0,'NONE','not compressed')); f.writeframes((np.sin(np.arange(144000)*2*np.pi*440/48000)*3000).astype('<i2').tobytes())
        p=Project(name='Compound verification',media=[MediaItem('b',str(output/'blue.png'),'image','Unselected blue background',4,320,180),MediaItem('v',str(output/'orange.png'),'image','Orange inset',3,320,180),MediaItem('a',str(audio),'audio','Dialogue',3,has_audio=True)],timeline=[TimelineItem('base','b','video_1',0,4,transform=Transform(.5,.5,1)),TimelineItem('inset','v','video_2',1,2,transform=Transform(.5,.5,.5)),TimelineItem('sound','a','audio_1',1,2)],captions=[Caption('c',1.2,2.8,'Editable nested caption')],video_tracks=['video_1','video_2'])
        p.settings.width=320; p.settings.height=180; p.settings.fps=30
        w.set_project(p); w.timeline.select_ids({'inset','sound'},'inset'); w.timeline.selected_caption_ids={'c'}
        w.compounds.new('My Compound'); outer=next(i for i in p.timeline if p.media_by_id(i.media_id).compound and i.track in p.video_tracks)
        w.compounds.open(outer.id); w.project.captions[0].end=3; w.model_changed()
        deadline=time.monotonic()+10
        while 'a' not in w.timeline.waveforms and time.monotonic()<deadline:wait()
        assert len(w.timeline.waveforms.get('a',[]))>0, 'Internal audio waveform missing'
        report['internal_audio_waveform']=True
        assert outer.duration==2 and w.compounds.root().media_by_id(outer.media_id).duration==3
        w.seek(.5); wait(); w.grab().save(str(output/'child.png'))
        w.timeline.select_ids({i.id for i in w.project.timeline},w.project.timeline[0].id); w.timeline.selected_caption_ids={'c'}; w.compounds.new('Nested Compound')
        inner=next(i for i in w.project.timeline if w.project.media_by_id(i.media_id).compound and i.track in w.project.video_tracks)
        w.compounds.open(inner.id); wait(); w.grab().save(str(output/'nested.png')); assert len(w.compounds.stack)==2
        w.compounds.back(0); report['nested_edit_and_fixed_parent_length']=True
        deadline=time.monotonic()+45
        while w.compounds.pending and time.monotonic()<deadline:wait()
        assert not w.compounds.pending and not w.compounds.failed
        deadline=time.monotonic()+10
        while outer.media_id not in w.timeline.waveforms and time.monotonic()<deadline:wait()
        assert len(w.timeline.waveforms.get(outer.media_id,[]))>0, 'Parent mixed waveform missing'
        report['parent_audio_waveform']=True
        w.timeline.waveforms.pop(outer.media_id)
        w.compounds.request_caches()
        deadline=time.monotonic()+10
        while outer.media_id not in w.timeline.waveforms and time.monotonic()<deadline:wait()
        assert len(w.timeline.waveforms.get(outer.media_id,[]))>0, 'Existing compound cache skipped waveform loading'
        report['existing_cache_waveform_reload']=True
        w.seek(1.5); wait(800); w.grab().save(str(output/'parent.png'))
        asset=w.project.media_by_id(outer.media_id); assert Path(asset.path).is_file()
        rgba=process(['ffmpeg','-v','error','-i',asset.path,'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'],capture_output=True,check=True).stdout
        pixels=np.frombuffer(rgba,np.uint8).reshape(180,320,4); assert pixels[2,2,3]==0 and pixels[90,160,3]>240
        rgba=process(['ffmpeg','-v','error','-ss','0.5','-i',asset.path,'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'],capture_output=True,check=True).stdout
        pixels=np.frombuffer(rgba,np.uint8).reshape(180,320,4)
        assert np.count_nonzero(pixels[:40,:,3])>100, 'Caption alpha must extend beyond the inset video'
        assert w.preview.frames; report['lossless_alpha_and_native_playback']=True
        target=output/'compound.mp4'; export(w.project,str(target),PRESETS['TikTok · Fast'],hardware='CPU')
        result=process(['ffmpeg','-v','error','-i',str(target),'-f','null','-'],capture_output=True); assert result.returncode==0
        w.project.save(output/'Compound Verification.kcut'); report['export_decodes']=True; report['passed']=True
    except Exception:report['passed']=False; report['error']=traceback.format_exc()
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(15000); app.processEvents(); (output/'report.json').write_text(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1
