"""Isolated packaged regression/visual check; never touches user media or settings."""
def run(output):
    import os,sys,json,time,traceback,copy
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QEventLoop,QTimer,QThreadPool,Qt
    from .ui import MainWindow
    from .model import Project,MediaItem,TimelineItem
    from .pool_tools import set_view
    from .process import run as process
    from .media import probe
    from . import missing_media as mm
    from PySide6.QtGui import QFont
    app=QApplication([]); app.setStyle('Fusion'); app.setFont(QFont('Segoe UI',9)); w=MainWindow(); w.resize(1600,900); w.show(); w.autosave_timer.stop()
    report={'frozen':bool(getattr(sys,'frozen',False))}
    def settle(ms=100):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def wait(predicate,timeout=30):
        end=time.monotonic()+timeout
        while not predicate() and time.monotonic()<end:settle(40)
        assert predicate(),'Timed out waiting for background operation'
    try:
        ffmpeg=w.settings.get('ffmpeg','ffmpeg')
        replacement=output/'replacement.mp4'
        process([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','3','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(replacement)],capture_output=True,check=True)
        old=MediaItem('source',str(output/'missing-original.mp4'),'video','missing-original.mp4',12,320,180,30,True)
        missing_audio=MediaItem('offline-audio',str(output/'missing-song.wav'),'audio','missing-song.wav',12,has_audio=True)
        p=Project(name='Missing media verification',media=[old,missing_audio],timeline=[TimelineItem('v','source','video_1',0,2,0),TimelineItem('a','source','audio_1',0,2,0),TimelineItem('late','source','video_1',3,2,7)])
        w.set_project(p); panel=w.media_panel; monitor=panel.missing_media
        monitor.checked(mm.scan(mm.source_paths(p))); settle(200)
        assert panel.grid.item(0).text()=='missing-original.mp4 is missing'
        assert not w.transport.decoders; report['missing_video_audio_no_decoder']=True
        w.workspace_split.setSizes([600,1000]); w.timeline.pixels_per_second=95; w.timeline._range()
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,False); set_view(panel,False,False); settle(); w.grab().save(str(output/(theme+'-missing.png')))
            set_view(panel,True,False); settle(); panel.grab().save(str(output/(theme+'-list.png')))
        set_view(panel,False,False)
        pos=panel.grid.visualItemRect(panel.grid.item(0)).center(); panel.media_context(pos)
        assert len(panel._menu.actions())==3; report['offline_context_only_three_actions']=True; panel._menu.close()
        before=[copy.deepcopy(i) for i in p.timeline]; w.seek(1.25)
        monitor.start([(copy.deepcopy(old),str(replacement))]); wait(lambda:not monitor.relinking)
        assert [i.source_mismatch for i in p.timeline]==[False,False,True]
        assert [(i.start,i.duration,i.in_point,i.transform,i.effects) for i in before]==[(i.start,i.duration,i.in_point,i.transform,i.effects) for i in p.timeline]
        assert w.project.playhead==1.25; report['partial_relink_preserves_edit']=True
        w.undo(); assert w.project.media[0].path==str(output/'missing-original.mp4')
        w.redo(); assert w.project.timeline[2].source_mismatch; report['undo_redo']=True
        w.transport.play(); wait(lambda:bool(w.preview.frames),10); w.transport.pause()
        report['relinked_native_video_frame']=True
        settle(200); w.grab().save(str(output/'partial-mismatch.png'))
        # Batch rebase changes only direct entries of the selected Power Bin.
        panel.power.add_folder('Master/Sound'); panel.power.add_folder('Master/Sound/Nested'); panel.power.add_folder('Master/Other')
        missing=MediaItem('bin',str(output/'old-dir'/'replacement.mp4'),'video','replacement.mp4',10,320,180,30,True)
        for folder in ('Master','Master/Sound','Master/Sound/Nested','Master/Other'):panel.power.add(missing,folder)
        panel.folder='Master/Sound'; monitor.checked(mm.scan([missing.path])); panel.refresh()
        from unittest.mock import patch
        with patch('kinetic_cut.missing_media_ui.QFileDialog.getExistingDirectory',return_value=str(output)):monitor.choose_folder()
        wait(lambda:not monitor.relinking)
        for entry in panel.power.data['media']:
            assert entry['media']['path']==(str(replacement) if entry['folder']=='Master/Sound' else missing.path)
        report['power_bin_exact_folder_scope']=True
        panel.folder='project'; panel.refresh(); w.transport.pause(); report['passed']=True
    except Exception:report['passed']=False; report['error']=traceback.format_exc()
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(20000); app.processEvents()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
