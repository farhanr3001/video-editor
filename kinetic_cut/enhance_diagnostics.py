"""Explicit native optional-model, range-extension and decoded-export check."""
def run(output,runtime):
    import os,sys,json,time,copy,subprocess,traceback,hashlib
    from pathlib import Path
    from unittest.mock import patch
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True);runtime=Path(runtime).resolve()
    os.environ['KINETIC_CUT_HOME']=str(out/'home');os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    import av,numpy as np
    from PySide6.QtCore import Qt,QPointF,QMimeData,QTimer,QEventLoop
    from PySide6.QtGui import QDropEvent,QImage
    from PySide6.QtWidgets import QApplication,QPushButton
    from .ui import MainWindow
    from .model import Project,MediaItem,TimelineItem,Crop
    from . import enhance,enhance_component,feature_packs
    from .exporter import export,ExportPreset
    app=QApplication([]);app.setQuitOnLastWindowClosed(False);app.setProperty('kineticTestDiscardUnsaved',True)
    w=MainWindow();w.autosave_timer.stop();w.resize(1480,1000);w.show()
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),themes=[])
    # Record/acknowledge only this diagnostic window's own failure popup, so a
    # failed worker cannot leave an unattended modal over the owner's desktop.
    from PySide6.QtWidgets import QMessageBox
    errors=[]
    def retire_error():
        for box in app.topLevelWidgets():
            if isinstance(box,QMessageBox) and box.parentWidget() is w and box.windowTitle()=='AI Enhance could not finish':
                errors.append(box.text());box.accept()
    error_timer=QTimer();error_timer.timeout.connect(retire_error);error_timer.start(100)
    confirmations=[]
    def confirm_storage():
        for box in app.topLevelWidgets():
            if isinstance(box,QMessageBox) and box.parentWidget() is w and box.windowTitle()=='AI Enhance · Storage':
                confirmations.append(box.informativeText());box.grab().save(str(out/'storage-confirmation.png'));box.button(QMessageBox.Ok).click()
    storage_timer=QTimer();storage_timer.timeout.connect(confirm_storage);storage_timer.start(30)
    def settle(ms=70):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    try:
        assert enhance_component.ready(runtime),'Explicit test runtime missing'
        source=out/'source.mkv'
        # A deterministic moving pattern exercises multiple frames and a hard cut.
        with av.open(str(source),'w') as movie:
            stream=movie.add_stream('ffv1',rate=6);stream.width=64;stream.height=64;stream.pix_fmt='bgr0'
            for n in range(3):
                pixels=np.zeros((64,64,3),np.uint8);pixels[:,:,0]=30+n*20;pixels[12:50,12+n*3:44+n*3]=[160,90,70]
                frame=av.VideoFrame.from_ndarray(pixels,format='rgb24');frame.pts=n
                for packet in stream.encode(frame):movie.mux(packet)
            for packet in stream.encode():movie.mux(packet)
        media=MediaItem('m',str(source),'video','Enhance fixture',.5,64,64);media.fps=6
        a=TimelineItem('a','m','video_1',0,1/3);b=TimelineItem('b','m','video_2',0,1/3)
        for item,y,scale in ((a,.28,1.1),(b,.72,.7)):
            item.crop=Crop(.125,.125,.75,.75);item.transform.y=y;item.transform.scale=scale
        p=Project(media=[media],timeline=[a,b]);p.settings.width=p.settings.height=128;p.settings.fps=6
        w.set_project(p);w.timeline.select_ids({'a','b'},'a');w.select_item('a');w.timeline.select_ids({'a','b'},'a');settle()
        before=[(vars(i.crop).copy(),vars(i.transform).copy(),i.start,i.duration,i.in_point) for i in p.timeline]
        ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start(30)
        oldroot=feature_packs.component_root
        with patch.object(enhance_component,'component_root',return_value=runtime),patch.object(feature_packs,'component_root',side_effect=lambda key:runtime if key=='enhance' else oldroot(key)):
            mime=QMimeData();mime.setData('application/x-kinetic-effect',enhance.NAME.encode())
            point=w.timeline.item_rect(a).center();event=QDropEvent(QPointF(point),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
            w.timeline.dropEvent(event);assert event.isAccepted();assert all(len(i.effects)==1 for i in p.timeline)
            deadline=time.monotonic()+120
            while getattr(w,'_enhance_job',None) and time.monotonic()<deadline:settle(50)
            assert not errors,errors
            assert not getattr(w,'_enhance_job',None),'Preparation did not settle'
        timer.stop();assert len(ticks)>3;report['ui_heartbeat_ticks']=len(ticks)
        assert before==[(vars(i.crop),vars(i.transform),i.start,i.duration,i.in_point) for i in p.timeline]
        assert all(not enhance.status(p,i) for i in p.timeline)
        record=enhance.info(p,media,a,0);report['inference']=record
        w.undo();assert all(not i.effects for i in w.project.timeline);w.redo();p=w.project;a=p.item_by_id('a');b=p.item_by_id('b');media=p.media_by_id('m')
        assert all(len(i.effects)==1 for i in p.timeline);report['multi_drop_undo']=True
        w.timeline.select_ids({'a','b'},'a');w.inspector.select('a');w.inspector.tabs.setCurrentIndex(2)
        panel=w.inspector.enhance_panel;key=enhance.cache_path(p,media,a,0)
        full=enhance.cached_frame(p,media,a,0,0);panel.edit('mix',50)
        assert enhance.cache_path(p,media,a,0)==key and enhance.info(p,media,a,0)
        half=enhance.cached_frame(p,media,a,0,0);assert full!=half
        panel.edit('mix',100);panel.face.setChecked(True);assert panel.rows['face_restore_strength'].isEnabled();panel.face.setChecked(False)
        report['live_mix']=True
        # Exercise the shipped inspector button and its independent playback,
        # not merely a source-only construction of the comparison widget.
        from PySide6.QtTest import QTest
        from .enhance_compare import DifferenceDialog
        state=copy.deepcopy(p.to_dict()['timeline']);playhead=p.playhead
        button=next(button for button in panel.findChildren(QPushButton) if button.text().startswith('View difference'))
        QTest.mouseClick(button,Qt.LeftButton);settle()
        dialog=w.inspector._enhance_difference
        assert isinstance(dialog,DifferenceDialog)
        deadline=time.monotonic()+5
        while dialog.canvas.before.isNull() and time.monotonic()<deadline:settle(20)
        assert not dialog.canvas.before.isNull() and not dialog.canvas.after.isNull()
        rect=dialog.canvas.image_rect();point=QPointF(rect.left()+rect.width()*.8,rect.center().y()).toPoint()
        QTest.mousePress(dialog.canvas,Qt.LeftButton,pos=rect.center().toPoint());QTest.mouseMove(dialog.canvas,point);QTest.mouseRelease(dialog.canvas,Qt.LeftButton,pos=point)
        assert dialog.canvas.split>.75
        QTest.keyClick(dialog,Qt.Key_Space);settle(220);assert dialog.playing
        dialog.grab().save(str(out/'difference-playing.png'))
        QTest.keyClick(dialog,Qt.Key_Escape);assert dialog._closed and not dialog.timer.isActive()
        settle();assert p.playhead==playhead and p.to_dict()['timeline']==state
        report['difference_wipe_local_playback']=True
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False)
            for width,height in ((1480,1000),(1120,760)):
                w.resize(width,height);settle(140);assert w.inspector.enhance_panel.isVisible();w.grab().save(str(out/f'enhance-{theme}-{width}.png'))
            assert panel.face.isHidden() and panel.upscale.isHidden()
            assert all(panel.rows[key].isHidden() for key in ('face_restore_strength','temporal_stability','mix'))
            from .enhance_ui import EnhanceProgress
            progress=EnhanceProgress(w);progress.setLabelText('Clip 1/1 · Restoring frame 891/1029 · CUDA');progress.setValue(85);progress.show();settle()
            assert progress.width()<600 and 'Estimated remaining' in progress.timing.text()
            progress.grab().save(str(out/f'progress-{theme}.png'));progress.close();progress.deleteLater()
            report['themes'].append(theme)
            from .cache_manager import CacheManagerDialog
            with patch.object(feature_packs,'component_root',side_effect=lambda key:runtime if key=='enhance' else oldroot(key)):
                manager=CacheManagerDialog(w);manager.show();settle()
                assert manager.component_rows['enhance'][0].text()=='AI Enhance'
                manager.grab().save(str(out/f'cache-manager-{theme}.png'));manager.close()
        # Real Cancel button during a new settings preparation leaves the clip
        # usable and never commits a half-written enhanced range.
        from .enhance_ui import begin
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtTest import QTest
        panel.edit('denoise',49)
        with patch.object(enhance_component,'component_root',return_value=runtime):
            begin(w,[a]);job=w._enhance_job
            cancel_button=next(button for button in job.dialog.findChildren(QPushButton) if button.text()=='Cancel')
            QTimer.singleShot(80,lambda:QTest.mouseClick(cancel_button,Qt.LeftButton))
            deadline=time.monotonic()+30
            while getattr(w,'_enhance_job',None) and time.monotonic()<deadline:settle(50)
            assert not getattr(w,'_enhance_job',None) and job.cancel.is_set()
        assert enhance.info(p,media,a,0) is None and a.effects
        panel.edit('denoise',enhance.DEFAULTS['denoise']);report['cancel_preserves_clip']=True
        key=enhance.cache_path(p,media,a,0);a.transform.rotation=17;a.transform.scale=1.5;assert enhance.cache_path(p,media,a,0)==key
        a.transform.rotation=0;a.transform.scale=1.1
        a.duration=.5
        assert not enhance.cached_frame(p,media,a,0,0).isNull();assert enhance.cached_frame(p,media,a,0,.4).isNull()
        assert 'Newly exposed' in enhance.status(p,a);report['extension_original_fallback']=True
        movie=out/'enhanced-export.mp4';export(p,str(movie),ExportPreset('AI test','h264',12,128,'test'),False,'CPU',ffmpeg=w.settings['ffmpeg'],export_audio=False)
        with av.open(str(movie)) as decoded:frames=[f.to_ndarray(format='rgb24') for f in decoded.decode(video=0)]
        assert len(frames)==3 and all(np.mean(frame)>2 for frame in frames)
        with av.open(str(source)) as original:source_frame=next(original.decode(video=0)).to_ndarray(format='rgb24')
        image=QImage(source_frame.data,64,64,source_frame.strides[0],QImage.Format_RGB888).copy()
        from .preview_compositor import SceneContext,render
        from PySide6.QtCore import QRectF
        context=SceneContext(p,{}, {},{i.id:image for i in p.timeline},False,1)
        preview=render(context,QRectF(0,0,128,128),(128,128),1)[0].convertToFormat(QImage.Format_RGB888)
        pixels=np.frombuffer(preview.constBits(),np.uint8).reshape(128,preview.bytesPerLine())[:,:384].reshape(128,128,3)
        error=float(np.mean(np.abs(pixels.astype(float)-frames[0].astype(float))));assert error<10,error
        preview.save(str(out/'preview.png'));QImage(frames[0].data,128,128,frames[0].strides[0],QImage.Format_RGB888).copy().save(str(out/'export.png'))
        report['decoded_export']=dict(frames=len(frames),preview_mean_absolute_error=error)
        saved=out/'roundtrip.kcut';p.save(saved);assert Project.load(saved).timeline[0].effects==a.effects
        owner_project=os.environ.get('KINETIC_ENHANCE_PLAYBACK_PROJECT')
        if owner_project:
            from .enhance_preview_check import run as check_preview
            report['owner_4x_preview']=check_preview(w,owner_project,out,settle)
        # Close the real editor while its owned worker holds a live CUDA context.
        # The outer preparation cancellation must reap it without a popup.
        import psutil
        marker=out/'closing-gpu.json';marker.unlink(missing_ok=True);script=out/'closing-gpu.py'
        script.write_text('import torch,time,os,json\nfrom pathlib import Path\nv=torch.ones((64,64),device="cuda")\nPath('+repr(str(marker))+').write_text(json.dumps(dict(pid=os.getpid())))\nprint(json.dumps(dict(frames=0,backend="CUDA")),flush=True)\nwhile True:\n v=v@v;v.zero_();time.sleep(.02)\n',encoding='utf-8')
        def closing_job(project,item,ffmpeg,progress,cancel,**kwargs):
            from .enhance_process import run
            run([str(runtime/'python.exe'),str(script)],out/'closing-gpu.log',progress,cancel,timeout=30)
        with patch.object(enhance_component,'component_root',return_value=runtime),patch.object(enhance,'prepare_item',side_effect=closing_job):
            begin(w,[a]);deadline=time.monotonic()+20
            while not marker.exists() and time.monotonic()<deadline:settle(20)
            assert marker.exists(),'GPU closing fixture did not start'
            pid=json.loads(marker.read_text())['pid'];assert psutil.pid_exists(pid)
            # A removed, Undo-retained range must be reclaimed only after the
            # real editor's outstanding preparation worker has stopped.
            orphan=copy.deepcopy(a);orphan.id='cleanup-fixture';orphan.effects[0]['denoise']=17
            orphan_root=enhance.cache_path(p,media,orphan,0);(orphan_root/'frames').mkdir(parents=True,exist_ok=True)
            image.save(str(orphan_root/'frames/00000000.png'))
            (orphan_root/'info.json').write_text(json.dumps(dict(key=orphan_root.name,family=enhance.signature(media,orphan,0,enhance.sample_fps(p,media,orphan),False),frames=1,fps=6,source_start=0)))
            p.timeline.append(orphan);w.model_changed();p.timeline.remove(orphan);w.model_changed()
            assert orphan_root.exists(),'Undo must retain its frames until close'
            w.close();deadline=time.monotonic()+5
            while getattr(w,'_enhance_job',None) and time.monotonic()<deadline:settle(20)
            assert not getattr(w,'_enhance_job',None) and not psutil.pid_exists(pid)
        deadline=time.monotonic()+15
        while w.isVisible() and time.monotonic()<deadline:settle(50)
        assert not w.isVisible() and not orphan_root.exists(),'Removed clip cache was not reclaimed on completed close'
        report['removed_clip_cache_reclaimed_on_close']=True
        report['editor_close_reaps_live_gpu_worker']=True
        assert confirmations and 'After your final render' in confirmations[0]
        report['storage_confirmation']=True
        report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        if getattr(w,'_enhance_cancel',None):w._enhance_cancel.set()
        deadline=time.monotonic()+15
        while getattr(w,'_enhance_job',None) and time.monotonic()<deadline:settle(50)
        from .enhance_preview import frames as enhanced_frames
        enhanced_frames.close()
        storage_timer.stop();error_timer.stop();w.close();deadline=time.monotonic()+15
        while w.isVisible() and time.monotonic()<deadline:settle(50)
        if w.isVisible():report.update(passed=False,error=report.get('error','')+'\nEditor shutdown did not complete')
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
