"""Opt-in native selective-emoji checks using a disposable fixture project."""
def run(output,project_path,regenerate=False):
    import os,sys,json,time,copy,hashlib,traceback
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    from PySide6.QtCore import Qt,QRectF,QEventLoop,QTimer,QThreadPool,QEvent
    from PySide6.QtGui import QImage,QPainter
    from PySide6.QtWidgets import QApplication
    from .model import Project
    from .ui import MainWindow
    from .caption_emojis import emojis_for_caption
    from .visuals import draw_caption,caption_geometry
    from .subtitle_render import write
    from .theme_widgets import apply_application_theme
    from .process import run as process
    from PIL import Image
    app=QApplication([]); w=MainWindow(); w.autosave_timer.stop(); w.resize(1480,900); w.show()
    report={'frozen':bool(getattr(sys,'frozen',False)),'native':os.name=='nt'}
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    path=Path(project_path).resolve(); before=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        p=Project.load(path); p=copy.deepcopy(p); p.path=''
        original_style=copy.deepcopy(p.subtitle_style.__dict__)
        for media in p.media:media.thumbnail=''
        w.request_waveform=lambda media:None
        w.set_project(p); w.seek(0); wait(100)
        if regenerate:
            # Use an existing local model path so this test never downloads one.
            cache=Path.home()/'.cache/huggingface/hub/models--Systran--faster-whisper-base.en/snapshots'
            model=next((folder for folder in cache.iterdir() if (folder/'model.bin').is_file()),None)
            assert model,'Existing local base.en model not found; no download attempted'
            assert p.delete_track('subtitle_1') and not p.captions
            w.model_changed(); w.timeline.select_ids(set(),'')
            w.settings['whisper_model']=str(model); w.settings['caption_remove_periods']=False; w.settings['caption_censor']=False
            errors=[]; finished=[]; worker=w.generate_captions(headless=True,words_per_card=1)
            assert worker is not None
            worker.signals.error.connect(errors.append); worker.signals.finished.connect(lambda:finished.append(True))
            deadline=time.monotonic()+180
            while not finished and time.monotonic()<deadline:wait(100)
            assert finished and not errors and p.captions,(finished,errors)
            report['cleared_and_regenerated_with_local_speech_engine']=len(p.captions)
        assert p.subtitle_style.__dict__==original_style
        selections=[{'id':cap.id,'text':cap.text,'start':cap.start,'emojis':emojis_for_caption(p,cap)} for cap in p.captions if emojis_for_caption(p,cap)]
        assert selections and len(selections)<len(p.captions)/4,(len(selections),len(p.captions))
        assert all(not emojis_for_caption(p,c) for c in p.captions if c.text.strip('.,?!').casefold()=='okay')
        report.update(captions=len(p.captions),selected_captions=len(selections),selections=selections,style_unchanged=True)
        review=output/'caption_testing_emoji_review.kcut'; p.save(review); report['review_project']=str(review)
        chosen=next(c for c in p.captions if c.text.strip('.,?!').casefold()=='coffee' and emojis_for_caption(p,c))
        filler=next(c for c in p.captions if c.text.strip('.,?!').casefold()=='okay')
        from .caption_words import timings
        screenshots=[]
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            apply_application_theme(theme)
            for label,cap in (('filler',filler),('keyword',chosen)):
                onset,end=timings(cap)[0]; sample=(onset+end)/2
                w.timeline.select_captions({cap.id},cap.id); w.seek(sample)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    wait(100); w.preview.repaint()
                    if ('caption',cap.id) in w.preview.text_rects:break
                assert ('caption',cap.id) in w.preview.text_rects,(theme,label,sample,p.playhead)
                filename=theme+'-'+label+'.png'; w.preview.grab().save(str(output/filename)); screenshots.append(filename)
        report['screenshots']=screenshots
        # Preview and actual FFmpeg export must agree on emoji presence above text.
        evidence=[]
        for label,cap in (('filler',filler),('keyword',chosen)):
            # Keep the full transcript plan, but export only this short word window.
            onset,end=timings(cap)[0]; sample=(onset+end)/2; p.playhead=sample
            image=QImage(540,960,QImage.Format_ARGB32); image.fill(Qt.black); painter=QPainter(image)
            try:draw_caption(painter,p,cap,QRectF(0,0,540,960))
            finally:painter.end()
            preview_path=output/(label+'-caption-preview.png'); image.save(str(preview_path))
            # Same caption geometry at the export resolution determines the region
            # above the lettering; it excludes regular text highlighting/shadows.
            top=int(caption_geometry(p,cap,QRectF(0,0,540,960))[2].top())-12
            ass=output/(label+'.ass'); full=copy.deepcopy(p); full.settings.width=540; full.settings.height=960
            full.subtitle_style.size=original_style['size']*.5
            write(full,ass)
            video=output/(label+'-export.mp4'); decoded=output/(label+'-export.png')
            ass_filter=str(ass).replace('\\','/').replace(':','\\:')
            process(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color=black:s=540x960:r=60:d={p.duration+.1}','-vf',"ass='"+ass_filter+"'",'-ss',str(sample),'-t','0.05','-c:v','libx264','-pix_fmt','yuv420p',str(video)],capture_output=True,check=True)
            process(['ffmpeg','-v','error','-y','-i',str(video),'-frames:v','1',str(decoded)],capture_output=True,check=True)
            def count(file):
                frame=Image.open(file).convert('RGB'); region=frame.crop((0,0,540,max(1,top)))
                return sum(max(pixel)>90 for pixel in region.getdata())
            preview_pixels=count(preview_path); export_pixels=count(decoded)
            if label=='filler':assert preview_pixels==0 and export_pixels==0,(preview_pixels,export_pixels)
            else:assert preview_pixels>100 and export_pixels>100,(preview_pixels,export_pixels)
            evidence.append({'word':cap.text,'preview_emoji_pixels':preview_pixels,'export_emoji_pixels':export_pixels})
        report['decoded_preview_export_presence']=evidence
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before
        report.update(original_project_unchanged=True,passed=True)
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(10000); app.processEvents(); app.sendPostedEvents(None,QEvent.DeferredDelete)
        (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return 0 if report.get('passed') else 1
