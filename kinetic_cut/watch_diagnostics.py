"""Native/package watch-folder check using only small generated fixtures."""
def run(output):
    import os, sys, json, time, traceback, wave, faulthandler
    faulthandler.enable(); faulthandler.dump_traceback_later(30,repeat=True)
    from pathlib import Path
    from unittest.mock import patch
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home')
    os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    from PIL import Image
    from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData,QThreadPool,QEvent,QEventLoop,QTimer
    from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDropEvent,QDragLeaveEvent,QFont
    from PySide6.QtWidgets import QApplication,QFileDialog
    from .ui import MainWindow
    from .model import Project
    from .pool_tools import set_view
    from .process import run as process
    from .config import load_settings
    app=QApplication([]); app.setQuitOnLastWindowClosed(False); app.setStyle('Fusion'); app.setFont(QFont('Segoe UI',9))
    w=MainWindow(); w.resize(1480,900); w.show(); w.autosave_timer.stop()
    report={'frozen':bool(getattr(sys,'frozen',False)), 'themes':[]}
    def checkpoint(stage):
        report['stage']=stage
        (output/'progress.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    panel=w.media_panel; watch=panel.watch_folders
    def settle(ms):
        # QTest.qWait holds Python's GIL through native queued player stop();
        # the desktop event loop releases it, letting decoder callbacks finish.
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def wait_for(predicate,timeout=12):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:settle(25)
        assert predicate(),'Timed out waiting for watched-media state'
    def mime(ids):
        data=QMimeData(); data.setData('application/x-kinetic-media-id',ids[0].encode())
        data.setData('application/x-kinetic-media-ids',json.dumps(ids).encode()); return data
    def drag(target,data,pos,drop=True):
        enter=QDragEnterEvent(pos,Qt.CopyAction,data,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(target,enter)
        assert enter.isAccepted(),'Drag enter rejected'
        move=QDragMoveEvent(pos,Qt.CopyAction,data,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(target,move)
        assert move.isAccepted(),'Drag move rejected'
        if drop:
            event=QDropEvent(QPointF(pos),Qt.CopyAction,data,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(target,event)
            assert event.isAccepted(),'Drop rejected'
        else:QApplication.sendEvent(target,QDragLeaveEvent())
    try:
        folder=output/'Watched Media'; folder.mkdir(exist_ok=True)
        Image.new('RGB',(640,360),'#428697').save(folder/'Reference Photo.png')
        process(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=royalblue:s=320x180:r=30:d=1.4',
                 '-f','lavfi','-i','sine=frequency=440:duration=1.4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(folder/'Video Clip.mp4')],check=True,capture_output=True,timeout=30)
        with wave.open(str(folder/'Audio Clip.wav'),'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000); f.writeframes(b'\x00\x00'*8000)
        (folder/'notes.txt').write_text('Not media',encoding='utf-8')
        child=folder/'Not Recursive'; child.mkdir(exist_ok=True)
        Image.new('RGB',(100,100),'red').save(child/'Nested.png')
        panel.project_context(QPoint(10,120)); panel._menu.close()
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(folder)):
            panel._menu.actions()[0].trigger()
        key=panel.folder
        wait_for(lambda:len(watch.folders[key].media())==3)
        assert panel.grid.count()==3 and not w.project.media
        assert {m.kind for m in watch.folders[key].media()}=={'video','audio','image'}
        assert load_settings()['media_watch_folders']==[str(folder)]
        report['initial_types_and_preferences']=True
        media=watch.folders[key].media(); first=panel.grid.item(0)
        first.setSelected(True); panel.grid.setCurrentItem(first); selected_id=first.data(Qt.UserRole)
        Image.new('RGB',(200,100),'orange').save(folder/'New Arrival.png')
        wait_for(lambda:panel.grid.count()==4)
        assert [i.data(Qt.UserRole) for i in panel.grid.selectedItems()]==[selected_id]
        assert not w.project.media; report['live_addition_selection_preserved']=True
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False)
            for size in ((1480,900),(1100,700)):
                w.resize(*size)
                for list_mode in (False,True):
                    set_view(panel,list_mode,False); settle(100)
                    panel.grab().save(str(output/f'{theme}-{size[0]}-{"list" if list_mode else "gallery"}.png'))
                    assert panel.watch_status.isVisible() and panel.grid.isVisible()
                tree=panel.project_tree
                contexts=(
                    ('sidebar-empty',panel.project_context,QPoint(10,120),['Watch Folder…']),
                    ('watch-row',panel.project_context,tree.visualItemRect(tree.topLevelItem(1)).center(),['Remove Watch Folder']),
                    ('pool-file',panel.media_context,panel.grid.visualItemRect(panel.grid.item(0)).center(),['Open Folder in Explorer','Refresh Folder']),
                    ('pool-empty',panel.media_context,QPoint(panel.grid.viewport().width()-15,panel.grid.viewport().height()-15),['Open Folder in Explorer','Refresh Folder']),
                )
                for name,context,pos,expected in contexts:
                    context(pos)
                    assert [a.text() for a in panel._menu.actions()]==expected,(theme,name)
                    settle(50); panel._menu.grab().save(str(output/f'{theme}-{size[0]}-{name}-menu.png')); panel._menu.close()
            report['themes'].append(theme)
        w.resize(1480,900); set_view(panel,False,False); settle(100)
        t=w.timeline; t.video_scroll.setValue(t.video_scroll.maximum()); settle(100)
        ids=[m.id for m in media]; data=mime(ids)
        pos=QPoint(round(t.x_for_time(0)),round(t.track_rect('video_1').center().y()))
        before=w.project.to_dict(); drag(t.viewport(),data,pos,False)
        assert before==w.project.to_dict()
        drag(t.viewport(),data,pos)
        assert len(w.project.media)==3 and len(w.project.timeline)==4
        assert len({m.path for m in w.project.media})==3
        settle(300)
        w.undo(); assert not w.project.timeline and not w.project.media; settle(300)
        w.redo(); assert len(w.project.media)==3 and len(w.project.timeline)==4; settle(300)
        report['all_type_drop_linked_av_undo_redo']=True
        video=next(m for m in w.project.media if m.kind=='video')
        clip=next(i for i in w.project.timeline if i.media_id==video.id and i.track in w.project.video_tracks)
        w.seek(clip.start+.4)
        wait_for(lambda:w.preview.active_frames.get(clip.id) in w.preview.frames and not w.preview.frames[w.preview.active_frames[clip.id]].isNull())
        assert video.id in w.timeline.waveforms or video.id in w.timeline.waveform_pending
        report['real_video_decoded']=True
        checkpoint('video decoded')
        w.transport.pause(); settle(300)
        w.set_project(Project()); assert panel.folder==key
        settle(300)
        tree=panel.project_tree; master_pos=tree.visualItemRect(tree.topLevelItem(0)).center()
        drag(tree.viewport(),data,master_pos); assert len(w.project.media)==3 and not w.project.timeline
        drag(tree.viewport(),data,master_pos); assert len(w.project.media)==3
        report['master_drop_dedup_across_projects']=True
        checkpoint('project switched; Master drops passed')
        (folder/'New Arrival.png').unlink(); wait_for(lambda:panel.grid.count()==3)
        assert len(w.project.media)==3; report['disk_delete_does_not_remove_imports']=True
        watch.debounce.stop(); wait_for(lambda:not watch.busy)
        moved=output/'Temporarily Away'; folder.rename(moved)
        wait_for(lambda:not watch.folders[key].available)
        assert panel.grid.count()==0 and 'unavailable' in panel.watch_status.text().lower()
        moved.rename(folder); wait_for(lambda:panel.grid.count()==3)
        report['folder_loss_and_return']=True
        checkpoint('folder returned')
        w.close(); settle(150)
        assert watch.closed and not watch.watcher.directories()
        w.deleteLater(); settle(100)
        w=MainWindow(); w.resize(1480,900); w.show(); w.autosave_timer.stop()
        panel=w.media_panel; watch=panel.watch_folders
        assert key in watch.folders
        panel.choose_folder(panel.project_tree.topLevelItem(1))
        wait_for(lambda:panel.grid.count()==3)
        assert not w.project.media; report['real_app_reopen_restores_watch_only']=True
        data=mime([m.id for m in watch.folders[key].media()])
        assert panel.import_to_master(data)
        before=w.project.to_dict(); panel.remove_watch_folder(key)
        assert before==w.project.to_dict() and all(Path(m.path).is_file() for m in w.project.media)
        assert load_settings()['media_watch_folders']==[]
        report['safe_remove_watch']=True
        checkpoint('watch removed')
        w.close(); assert watch.closed and not watch.watcher.directories()
        report['passed']=True
    except Exception:report['passed']=False; report['error']=traceback.format_exc()
    finally:
        checkpoint('closing diagnostic')
        w.close(); QThreadPool.globalInstance().waitForDone(20000); app.processEvents()
        checkpoint('deleting diagnostic window')
        w.deleteLater(); app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()
        faulthandler.cancel_dump_traceback_later()
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
