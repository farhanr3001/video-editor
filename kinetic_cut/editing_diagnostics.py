"""Opt-in native checks for precise placement and inspector editing (isolated home)."""
def run(output,project_path=None):
    import os,sys,json,traceback,hashlib,copy
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home')
    os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    report={'frozen':bool(getattr(sys,'frozen',False)),'native':os.name=='nt'}
    window=None; app=None
    try:
        from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QEventLoop,QTimer,QThreadPool
        from PySide6.QtGui import QImage,QColor,QMouseEvent
        from PySide6.QtWidgets import QApplication,QScrollArea
        from PySide6.QtTest import QTest
        from .model import Project,MediaItem,TimelineItem,Caption
        from .ui import MainWindow
        from .timeline import TimelineWidget
        from .attributes import PasteAttributesDialog
        from .theme_widgets import apply_application_theme
        from .mixed_move import snap_move
        app=QApplication([]); app.setQuitOnLastWindowClosed(False); app.setStyle('Fusion')
        def wait(ms):
            loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
        window=MainWindow(); window.autosave_timer.stop(); window.resize(1400,850); window.show()
        still=output/'fixture.png'; image=QImage(640,360,QImage.Format_RGB32); image.fill(QColor('#486e79')); image.save(str(still))
        p=Project(media=[MediaItem('m',str(still),'image','Editing fixture',30,640,360)],
                  timeline=[TimelineItem('v','m','video_1',1,2),TimelineItem('neighbor','m','video_1',8.0137,2)],
                  captions=[Caption('c',1,3,'Caption'),Caption('n',8.0137,9,'Neighbor')])
        window.set_project(p)
        t=TimelineWidget(); t.resize(1300,550); t.set_project(p); t.set_zoom(100); t.setProperty('snapping',True); t.show(); wait(100)
        for caption in (False,True):
            t.select_ids(set()); t.select_captions(set())
            wait(30)
            origin=(t.visible_caption_rect(p.captions[0]) if caption else t.visible_item_rect(p.item_by_id('v'))).center().toPoint()
            QTest.mousePress(t.viewport(),Qt.LeftButton,pos=origin); QTest.mouseMove(t.viewport(),origin+QPoint(470,0))
            mode=t.drag_mode
            QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=origin+QPoint(503,0))
            end=next(c.end for c in p.captions if c.id=='c') if caption else p.item_by_id('v').start+2
            assert abs(end-8.0137)<1e-12,(end,caption,mode,origin,t.viewport().size())
        report['native_release_adjacency']=True
        t.close(); t=window.timeline; t.select_ids({'v'},'v'); panel=window.inspector
        panel.link.setChecked(False); panel.zoom_x.spin.setValue(1.908); panel.zoom_y.spin.setValue(1.190); panel.link.setChecked(True)
        panel.zoom_x.spin.setValue(1.909); tr=p.item_by_id('v').transform
        assert abs(tr.scale/tr.effective_scale_y-1.908/1.190)<1e-12
        spin=panel.zoom_x.spin; line=spin.lineEdit()
        QTest.mouseDClick(line,Qt.LeftButton); QTest.keyClicks(spin,'1.95'); QTest.keyClick(spin,Qt.Key_Return); wait(20)
        assert not line.hasFocus() and not line.hasSelectedText() and spin.keyboardTracking()
        assert abs(tr.scale-1.95)<1e-9
        point=QPoint(10,10); origin=line.mapToGlobal(point); QTest.mousePress(line,Qt.LeftButton,pos=point)
        assert spin._drag_start is not None
        QApplication.sendEvent(line,QMouseEvent(QEvent.MouseMove,QPointF(point+QPoint(10,0)),QPointF(origin+QPoint(10,0)),Qt.NoButton,Qt.LeftButton,Qt.ShiftModifier))
        QTest.mouseRelease(line,Qt.LeftButton,pos=point); assert tr.scale>1.95
        report['zoom_ratio_and_type_then_drag']=True
        window.apply_effect('Gaussian Blur'); panel.blur_h.slider.setSliderDown(True); panel.blur_h.slider.setValue(700)
        assert panel.blur_h.slider.value()==panel.blur_v.slider.value()
        assert panel.blur_h.spin.value()==panel.blur_v.spin.value()
        panel.blur_h.slider.setSliderDown(False); report['live_linked_blur']=True
        old=list(p.video_tracks); new=window.add_video_track('video_1'); assert p.video_tracks==[old[0],new]
        window.undo(); assert window.project.video_tracks==old
        window.redo(); assert window.project.video_tracks==[old[0],new]; report['track_insert_undo']=True
        screenshots=[]
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            apply_application_theme(theme); wait(40)
            window.grab().save(str(output/(theme+'-inspector.png')))
            for category in ('video','audio','text'):
                dialog=PasteAttributesDialog('xQc livestream clip','Selected '+category+' clips',category,window,{'position','effects','font','gain_db'})
                dialog.show(); wait(30)
                for small in (False,True):
                    dialog.resize(560,420 if small else 520); wait(30)
                    assert dialog.buttons.geometry().bottom()<=dialog.height()
                    filename=theme+'-'+category+('-compact' if small else '')+'.png'
                    dialog.grab().save(str(output/filename)); screenshots.append(filename)
                dialog.reject(); dialog.deleteLater()
        report['screenshots']=screenshots
        if project_path:
            path=Path(project_path).resolve(); before=hashlib.sha256(path.read_bytes()).hexdigest(); real=Project.load(path)
            # In-memory copy only; avoid whole-recording waveform generation and
            # unrelated cache jobs. Ordinary media decoding still runs natively.
            real=copy.deepcopy(real); real.path=''
            candidates=[]
            for item in real.timeline:
                media=real.media_by_id(item.media_id)
                if item.track in real.video_tracks and media and not media.compound and Path(media.path).is_file():candidates.append(item)
            assert candidates,'No available real video fixture'
            chosen=next((i for i in candidates if 'NoPixel5' in real.media_by_id(i.media_id).path),candidates[0])
            actual=real.media_by_id(chosen.media_id)
            actual.thumbnail=''  # Regenerate under this diagnostic's isolated cache.
            # Keep the three existing crops of this source at the chosen time.
            moment=chosen.start+min(.3,chosen.duration/2)
            real.timeline=[i for i in real.timeline if i.media_id==chosen.media_id and i.start<=moment<i.start+i.duration]
            real.media=[actual]; real.captions=[]; real.transitions=[]
            original_request=window.request_waveform; window.request_waveform=lambda media:None
            try:window.set_project(real)
            finally:window.request_waveform=original_request
            window.seek(moment); wait(1000)
            decoded=[id for id,key in window.preview.active_frames.items() if key in window.preview.frames and not window.preview.frames[key].isNull()]
            assert decoded,window.preview.active_frames
            # Test source project's fractional boundaries across each real lane.
            original=Project.load(path)
            for media in original.media:media.thumbnail=''
            t.set_project(original); t.set_zoom(100); t.setProperty('snapping',True)
            cases=0
            for track in original.video_tracks+original.audio_tracks:
                clips=sorted((i for i in original.timeline if i.track==track),key=lambda i:i.start)
                for moving,neighbor in zip(clips,clips[1:]):
                    t._move_snap=None; edge=moving.start+moving.duration
                    delta=snap_move(t,neighbor.start-edge+.03,[moving.start,edge],{moving.id},destination_tracks={track})
                    assert abs(edge+delta-neighbor.start)<1e-10,(track,edge+delta,neighbor.start)
                    cases+=1
            t.set_project(real); window.grab().save(str(output/'real-xqc-preview.png'))
            after=hashlib.sha256(path.read_bytes()).hexdigest(); assert before==after
            report['real_project']={'path':str(path),'hash':after,'unchanged':True,'boundary_cases':cases,'decoded_items':decoded,'source':actual.path}
        report['passed']=True
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:
        if window:window.close()
        if app:
            QThreadPool.globalInstance().waitForDone(10000); app.processEvents(); QApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report.get('passed') else 1
