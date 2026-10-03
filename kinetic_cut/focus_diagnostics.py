"""Real decoder, popup keyboard and focus-mode snapshots in an isolated profile."""
def run(output):
    import os,json,time,traceback,sys
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt,QEventLoop,QTimer,QThreadPool,QMimeData
    from PySide6.QtGui import QDragMoveEvent
    from PySide6.QtTest import QTest
    from PySide6.QtMultimedia import QMediaPlayer
    from .ui import MainWindow
    from .model import Project,MediaItem,TimelineItem,Caption
    from .pool_tools import SourcePreview
    from .theme import STYLESHEET
    from .process import run as process
    source=output/'sample.mp4'
    process(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=s=320x180:r=30:d=5','-f','lavfi','-i','sine=frequency=440:duration=5','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],capture_output=True,check=True)
    app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
    w=MainWindow(); w.resize(1450,850); w.show(); w.autosave_timer.stop(); report={'frozen':bool(getattr(sys,'frozen',False))}
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    try:
        media=MediaItem('m',str(source),'video','Focus fixture',5,320,180,30,True)
        p=Project(media=[media],timeline=[TimelineItem('v','m','video_1',0,5),TimelineItem('a','m','audio_1',0,5)],captions=[Caption('one',.5,2,'Review the caption while listening'),Caption('two',2.5,4.5,'No video layers or effects are processed')])
        p.timeline[0].effects=[{'name':'Gaussian Blur','enabled':True,'horizontal':40,'vertical':40}]
        w.set_project(p); wait(650); assert any(sink for _,_,sink in w.transport.decoders.values())
        w.timeline.select_captions({'one'},'one'); w.caption_focus_button.setChecked(True); wait(200)
        assert w.project.playhead==.5 and w.preview.text_rects
        w.grab().save(str(output/'focus-paused.png'))
        w.transport.play(); wait(400)
        assert w.transport.position>.7 and w.transport.decoders
        assert all(sink is None and player.activeVideoTrack()==-1 for player,_,sink in w.transport.decoders.values())
        assert not w.transport.frame_timer.isActive() and not w.preview._visible_items()
        w.grab().save(str(output/'focus-playing.png')); w.transport.pause(); report['real_audio_without_video_decoding']=True
        times=[]
        for n in range(30):
            start=time.perf_counter(); w.transport.scrub(.5+n/50); w.preview.grab(); times.append((time.perf_counter()-start)*1000)
        w.transport.finish_scrub(); report['focus_scrub_paint_mean_ms']=sum(times)/len(times); report['focus_scrub_paint_max_ms']=max(times)
        w.caption_focus.navigate(-1); assert w.timeline.selected_caption=='two' and p.playhead==2.5
        w.caption_focus.navigate(1); assert w.timeline.selected_caption=='one' and p.playhead==.5; report['wrap_selection_and_seek']=True
        w.caption_focus_button.setChecked(False); wait(600); assert any(sink for _,_,sink in w.transport.decoders.values()); assert w.preview._visible_items(); report['normal_video_restored']=True
        preview=SourcePreview(w.media_panel,media); preview.show(); wait(600)
        assert preview.player.playbackState()==QMediaPlayer.PlayingState and preview.player.position()>0
        QTest.keyClick(preview,Qt.Key_Space); wait(50); assert preview.player.playbackState()==QMediaPlayer.PausedState and not w.transport.playing
        QTest.keyClick(preview,Qt.Key_Space); wait(50); assert preview.player.playbackState()==QMediaPlayer.PlayingState
        preview.grab().save(str(output/'source-preview.png')); preview.close(); wait(50); assert w.timeline.viewport().hasFocus(); report['popup_autoplay_space_focus']=True
        panel=w.media_panel; panel.power.add_folder('Master/Target'); panel.folder='Master'; panel.rebuild_tree(); panel.refresh(); wait(50)
        mime=QMimeData(); mime.setData('application/x-kinetic-media-id',b'm')
        for name,view,item in [('tile',panel.grid,panel.grid.item(0)),('sidebar',panel.tree,panel.tree.topLevelItem(0).child(0))]:
            event=QDragMoveEvent(view.visualItemRect(item).center(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
            view.dragMoveEvent(event); assert view.folder_hover_rect; panel.grab().save(str(output/('hover-'+name+'.png'))); view.folder_hover_rect=None
        report['folder_hover']=True; report['passed']=True
    except Exception:report['passed']=False; report['error']=traceback.format_exc()
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(10000); app.processEvents(); (output/'report.json').write_text(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1
