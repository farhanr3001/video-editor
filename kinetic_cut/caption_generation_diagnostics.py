"""Opt-in real-media caption workflow using a disposable, shortened project."""
def run(output,project_path):
    import os,sys,json,time,copy,hashlib,traceback
    from pathlib import Path
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home')
    from PySide6.QtCore import QTimer,QEventLoop,QEvent
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from .model import Project
    from .ui import MainWindow
    from .icons import resource_path
    from .caption_style_dialog import CaptionStyleDialog
    from .caption_progress import CaptionProgressDialog
    from .theme_widgets import apply_application_theme
    from .config import DATA_DIR
    # Private test homes may reuse only the owner's already-installed CUDA DLLs.
    # Hard links do not modify/download a runtime or expose the owner's settings.
    owner=Path(os.environ.get('LOCALAPPDATA',''))/'KineticCut/KineticCut/components/ai-enhance-v1/Lib/site-packages/torch/lib'
    target=DATA_DIR/'components/ai-enhance-v1/Lib/site-packages/torch/lib'
    if all((owner/n).is_file() for n in ('cublasLt64_12.dll','cublas64_12.dll')):
        target.mkdir(parents=True,exist_ok=True)
        for name in ['cublasLt64_12.dll','cublas64_12.dll',*(p.name for p in owner.glob('cudnn*.dll'))]:
            if not (target/name).exists():os.link(owner/name,target/name)
    app=QApplication.instance() or QApplication([]);app.setProperty('kineticTestDiscardUnsaved',True)
    app.setQuitOnLastWindowClosed(False)
    window=MainWindow();window.autosave_timer.stop();window.resize(1350,850);window.show()
    path=Path(project_path).resolve();before=hashlib.sha256(path.read_bytes()).hexdigest()
    report=dict(frozen=bool(getattr(sys,'frozen',False)),passed=False)
    timer=QTimer();timer.setInterval(50);texts=[];screens=[];ticks=[];errors=[];finished=[]
    themes=['default','final_cut_obsidian','ableton_gray']
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def monitor():
        ticks.append(time.monotonic())
        for dialog in app.topLevelWidgets():
            if isinstance(dialog,CaptionStyleDialog) and dialog.isVisible():
                dialog.words.setValue(2);dialog.accept()
            if isinstance(dialog,CaptionProgressDialog) and dialog.isVisible():
                texts.append(dialog.labelText())
    try:
        project=copy.deepcopy(Project.load(path));project.path='';project.captions=[]
        project.timeline=[item for item in project.timeline if item.start<20]
        for item in project.timeline:item.duration=min(item.duration,20-item.start)
        window.request_waveform=lambda media:None
        window.queue_proxy=lambda media:None
        window.preview_quality.request=lambda:None
        window.set_project(project);window.timeline.select_ids(set(),'')
        model=resource_path('assets','caption-models','base.en')
        if not (model/'model.bin').is_file():model=Path.cwd()/'dist/KineticCut/_internal/assets/caption-models/base.en'
        assert (model/'model.bin').is_file(),'No existing local speech model; no download attempted'
        window.settings['whisper_model']=str(model)
        # Theme application rebuilds the whole main window. Inspect the dialog
        # separately so that test setup cannot obstruct the live progress clock.
        sample=CaptionProgressDialog(window)
        for theme in themes:
            apply_application_theme(theme);sample.show();sample.set_progress(64,'Transcribing… 8.6s / 20.0s')
            wait(100);filename=theme+'-progress.png';sample.grab().save(str(output/filename));screens.append(filename)
        sample.close();sample.deleteLater();wait(1500)
        timer.timeout.connect(monitor);timer.start();started=time.monotonic()
        worker=window.generate_captions()
        assert worker is not None
        worker.signals.error.connect(errors.append);worker.signals.finished.connect(lambda:finished.append(True))
        deadline=time.monotonic()+120
        while not finished and time.monotonic()<deadline:wait(50)
        timer.stop()
        report['observed_progress']=list(dict.fromkeys(texts))
        assert finished and not errors,(finished,errors)
        assert project.captions and len(screens)==3
        for caption in project.captions:
            assert 1<=len(caption.text.split())<=2 and caption.word_timings
            assert caption.end-caption.start+1e-6>=max(w['end'] for w in caption.word_timings)
        assert all(a.end<=b.start+1e-6 for a,b in zip(project.captions,project.captions[1:]))
        assert any('Elapsed' in text and 'remaining' in text for text in texts)
        assert len(ticks)>10
        caption_count=len(project.captions);window.undo();assert not window.project.captions
        window.redo();assert len(window.project.captions)==caption_count
        window.project.save(output/'review.kcut')
        report.update(passed=True,captions=caption_count,seconds=time.monotonic()-started,progress_texts=list(dict.fromkeys(texts)),screenshots=screens,
            words_per_card=2,all_spoken_tails_contained=True,undo_redo=True,heartbeat_ticks=len(ticks),source_preserved=True)
    except Exception:report['error']=traceback.format_exc()
    finally:
        timer.stop();window.close()
        deadline=time.monotonic()+15
        while (window.isVisible() or window._workers) and time.monotonic()<deadline:wait(50)
        assert not window._workers and not window.isVisible(),'Diagnostic did not close gracefully'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before
        app.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
