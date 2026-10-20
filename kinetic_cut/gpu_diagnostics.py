"""Native rendering correctness checks. No timing/performance qualification."""
def run(output,project_path=None):
    import os,json,hashlib
    from pathlib import Path
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home')
    from PySide6.QtCore import Qt,QEventLoop,QTimer,QUrl,QRect,QObject,QEvent
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtWidgets import QApplication,QWidget
    from .quick_surface import Surface
    from .qt_native import NativeClips,ClipProxy,LIB
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    background=os.environ.get('KINETIC_DIAGNOSTIC_BACKGROUND')=='1'
    class BackgroundWindows(QObject):
        def eventFilter(self,obj,event):
            if background and event.type()==QEvent.Polish and isinstance(obj,QWidget) and obj.isWindow():
                obj.setAttribute(Qt.WA_ShowWithoutActivating)
                obj.setWindowFlag(Qt.WindowDoesNotAcceptFocus,True)
                obj.move(-30000,-30000)
            return False
    background_windows=BackgroundWindows(app);app.installEventFilter(background_windows)
    app.setProperty('kineticTestDiscardUnsaved',True)
    assert app.platformName()=='windows' and LIB,'Requires native Windows RHI renderer'
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    report={'checks':[],'performance_measured':False,'background_only':background,
            'onscreen_presentation_verified':False,'verification_desktop':'private' if os.environ.get('KINETIC_DIAGNOSTIC_PRIVATE_DESKTOP')=='1' else 'current'}
    def check(name,condition):
        report['checks'].append(dict(name=name,passed=bool(condition)))
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        assert condition,name
    if os.environ.get('KINETIC_NUMERIC_FOCUS_SELFTEST')=='1':
        from .ui import MainWindow
        import time
        window=MainWindow();window.resize(1700,1000);window.autosave_timer.stop();window.show();wait(350)
        timeline_polish_checks(window,out,check,wait)
        peer=window.preview.gpu.peer
        window.close();deadline=time.monotonic()+10
        while (window.isVisible() or peer.active) and time.monotonic()<deadline:wait(50)
        check('native window and renderer close gracefully',not window.isVisible() and not peer.active and peer.exitcode==0 and not peer.forced_shutdown)
        report['passed']=all(c['passed'] for c in report['checks']);report['scope']='numeric focus and timeline polish'
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        return 0
    asset=QImage(64,64,QImage.Format_RGBA8888);asset.fill(QColor('#ec2030'))
    asset.save(str(out/'thumbnail.png'))
    wave=QImage(32,1,QImage.Format_RGBA8888);wave.fill(QColor(255,255,0,255))
    widget=QWidget();widget.resize(600,210)
    surface=Surface(widget,'GpuTimeline.qml')
    surface.properties(surface.root,dict(bodyX=0.,bodyY=0.,nativeRuler=True,playhead=-100.))
    native=NativeClips(surface.item('body'));native.view(600,210,100,0)
    def clip(**values):
        proxy=ClipProxy();proxy.setVisible(True)
        proxy.values=dict(duration=2.,laneY=10.,laneHeight=75.,sectionTop=0.,sectionBottom=210.,label='Visible clip',color='#3c6c90',**values)
        return proxy
    url='image://prepared/check-wave';native.image(url,wave)
    clips=[clip(selected=True),clip(startTime=2.2,thumbnail=QUrl.fromLocalFile(str(out/'thumbnail.png')).toString()),
           clip(startTime=0.,audio=True,waveform=url,waveCount=32.,waveResolution=.125)]
    clips[2].values.update(laneY=105.,color='#326951',duration=4.)
    native.publish(clips);widget.show();surface.geometry(widget.rect());wait(700)
    image=surface.view.grabWindow();image.save(str(out/'native-clips.png'))
    blue=image.pixelColor(30,30);red=image.pixelColor(240,30);peak=image.pixelColor(40,135);outline=image.pixelColor(0,45)
    check('clip body is visible',blue.blue()>110 and blue.blue()>blue.red()*1.5)
    check('thumbnail texture is visible',red.red()>180 and red.green()<70)
    check('waveform texture is visible',peak.green()>200 and peak.red()>180)
    check('selected clip outline is visible',outline.red()>150 and outline.red()>outline.green()*1.5)
    # Native surfaces must start at their laid-out dimensions, including after
    # hide/show, rather than exposing the default tiny black child window.
    widget.hide();widget.resize(740,260);widget.show();surface.geometry(widget.rect());wait(100)
    check('native child follows initialized geometry',surface.container.geometry()==widget.rect() and surface.view.width()==740)
    surface.close();widget.close();wait(100)
    if project_path:
        from .model import Project
        from .ui import MainWindow
        from .waveforms import waveform
        source=Path(project_path).resolve();before=hashlib.sha256(source.read_bytes()).hexdigest()
        window=MainWindow();window.resize(1700,1000);window.autosave_timer.stop()
        window.request_waveform=lambda _:None;window.preview_quality.request=lambda:None
        project=Project.load(source);project.path='';window.set_project(project)
        for media in project.media:
            if media.has_audio:window.timeline.set_waveform(media.id,waveform(media.path,window.settings.get('ffmpeg','ffmpeg')))
        window.show()
        if not background:window.showMinimized();window.showNormal()
        wait(250);window.seek(162.6);window.timeline.set_zoom(35)
        window.timeline.horizontalScrollBar().setValue(round(150*35));wait(1500)
        import time
        initial_gpu=window.preview.gpu;deadline=time.monotonic()+8
        while not initial_gpu.frames and time.monotonic()<deadline:wait(30)
        (out/'initial-preview-pipeline.json').write_text(json.dumps(initial_gpu.diagnostics(),indent=2),encoding='utf-8')
        check('preview renderer becomes ready before capture',initial_gpu.frames>0)
        gpu=window.timeline.gpu
        # Capture the parent HWND, not just QQuickWindow's render target. This
        # detects a correct renderer hidden behind a wrongly parented HWND.
        # Complete the renderer's requested readback before observing its host.
        # Capturing the host first can compare a pre-upload image with the next
        # frame's just-loaded still/logo, especially during cold child startup.
        renderer_image=window.preview.gpu.view.grabWindow()
        check('explicit initial preview capture returns pixels',not renderer_image.isNull())
        host=capture_native_host(window,out/'embedded-window.png')
        preview=window.preview;origin=preview.mapTo(window,preview.rect().topLeft())
        ratio=host.width()/window.width()
        frame=preview.composition_rect()
        host_rect=QRect(round((origin.x()+frame.x())*ratio),round((origin.y()+frame.y())*ratio),round(frame.width()*ratio),round(frame.height()*ratio))
        actual=host.copy(host_rect).convertToFormat(QImage.Format_RGBA8888)
        expected=renderer_image.copy(frame.toRect()).scaled(actual.size()).convertToFormat(QImage.Format_RGBA8888)
        expected.save(str(out/'embedded-reference.png'))
        import numpy as np
        a=np.frombuffer(actual.constBits(),np.uint8).reshape(actual.height(),actual.width(),4).astype(float)
        b=np.frombuffer(expected.constBits(),np.uint8).reshape(expected.height(),expected.width(),4).astype(float)
        host_error=float(np.abs(a[:,:,:3]-b[:,:,:3]).mean())
        visible=float(np.mean(np.max(a[:,:,:3],axis=2)>45))
        report['native_host_presentation']=dict(verified=True,capture='PrintWindow render-full-content',mean_pixel_error=host_error,visible_video_fraction=visible)
        report['native_host_presentation']['verified']=host_error<3 and visible>.15
        check('native parent window actually contains the preview pixels',report['native_host_presentation']['verified'])
        preview_gpu=window.preview.gpu
        check('embedded preview belongs to its own native container',preview_gpu.view.parent() is preview_gpu.container.windowHandle())
        check('embedded timeline belongs to its own native container',gpu.view.parent() is gpu.container.windowHandle())
        image=gpu.view.grabWindow();image.save(str(out/'owner-timeline.png'))
        window.preview.gpu.view.grabWindow().save(str(out/'owner-preview.png'))
        import numpy as np
        rgba=image.convertToFormat(QImage.Format_RGBA8888)
        pixels=np.frombuffer(rgba.constBits(),np.uint8).reshape(image.height(),image.width(),4)
        check('owner timeline has blue clip bodies',int(((pixels[:,:,2]>pixels[:,:,0]*1.35)&(pixels[:,:,2]>80)).sum())>3000)
        check('owner timeline has green audio bodies',int(((pixels[:,:,1]>pixels[:,:,0]*1.35)&(pixels[:,:,1]>70)&(pixels[:,:,2]<130)).sum())>1000)
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint,QPointF,QEvent
        from PySide6.QtGui import QMouseEvent
        timeline=window.timeline
        candidates=[i for i in project.runtime_index.query('timeline',155,175) if i.track in project.video_tracks
                    and timeline.visible_item_rect(i).width()>40 and timeline.visible_item_rect(i).height()>25]
        candidate=max(candidates,key=lambda i:timeline.visible_item_rect(i).width())
        rect=timeline.visible_item_rect(candidate);point=rect.center().toPoint()
        timeline.select_ids(set());QTest.mouseClick(gpu.view,Qt.LeftButton,pos=point);wait(80)
        check('native window click selects the visible clip',candidate.id in timeline.selected_ids)
        timeline.toggle_retime();wait(80)
        check('retime controls remain available',candidate.id in timeline.retime_ids)
        gpu.view.grabWindow().save(str(out/'retime-controls.png'));timeline.toggle_retime()
        # A real native-window key must reach the existing editor handlers.
        before_playhead=window.project.playhead
        QTest.keyClick(gpu.view,Qt.Key_Right);wait(50)
        check('native window frame-step key reaches editor',window.project.playhead>before_playhead)
        content=window.project.to_dict();content.pop('playhead');content.pop('modified_at',None)
        at=candidate.start+candidate.duration/2
        window.split_at(candidate.id,at);wait(50);window.undo();wait(50)
        restored=window.project.to_dict();restored.pop('playhead');restored.pop('modified_at',None)
        check('split and undo preserve the full document',content==restored)
        from PySide6.QtCore import QMimeData
        from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDropEvent
        window.seek(162.6);timeline.set_zoom(35);timeline.horizontalScrollBar().setValue(5250);wait(100)
        (out/'drop-geometry.json').write_text(json.dumps([dict(id=i.id,track=i.track,effects=i.effects,rect=timeline.visible_item_rect(i).getRect()) for i in window.project.runtime_index.active('timeline',162.6)],indent=2))
        drop_item=next(i for i in window.project.runtime_index.active('timeline',162.6) if i.track in window.project.video_tracks
                       and timeline.visible_item_rect(i).width()>40 and timeline.visible_item_rect(i).height()>25)
        point=timeline.visible_item_rect(drop_item).center().toPoint();old_count=len(drop_item.effects)
        mime=QMimeData();mime.setData('application/x-kinetic-effect',b'Gaussian Blur')
        for event in (QDragEnterEvent(point,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier),
                      QDragMoveEvent(point,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier),
                      QDropEvent(QPointF(point),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)):
            app.sendEvent(gpu.view,event)
        wait(100)
        check('effect drag/drop crosses the native window bridge',len(window.project.item_by_id(drop_item.id).effects)==old_count+1)
        window.undo();wait(80)
        # Switch an active source to exact effect preparation and back. Reusing
        # an old GPU-only decoder here used to leave the effect worker pixel-less.
        window.seek(162.6);item=window.project.item_by_id(drop_item.id);original_contrast=item.contrast
        prepared=window.preview.gpu.completed;item.contrast=1.15;window.transport.sync(True)
        import time
        deadline=time.monotonic()+8
        while window.preview.gpu.completed<=prepared and time.monotonic()<deadline:wait(40)
        check('adding a CPU-prepared operation produces a complete preview',window.preview.gpu.completed>prepared)
        key=window.preview.active_frames[item.id]
        if getattr(window.preview.gpu,'remote',False):
            # Pixels deliberately stay in the compositor process. Its status
            # reports actual non-null decoded source dimensions, not readbacks.
            deadline=time.monotonic()+5
            while key not in window.preview.gpu.cpu_ready and time.monotonic()<deadline:wait(30)
            size=window.preview.gpu.cpu_ready.get(key,(0,0))
            check('required CPU source pixels arrive',size[0]>0 and size[1]>0)
            check('preview child is embedded and native input remains with the editor',
                window.preview.gpu.native_status['parent']==int(window.preview.gpu.view.winId()) and window.preview.gpu.native_status['disabled'])
        else:check('required CPU source pixels arrive',key in window.preview.frames and not window.preview.frames[key].isNull())
        check('processed media keeps its transform hit target',item.id in {i.id for i,_,_ in window.preview._visible_items()})
        pipeline=window.preview.gpu.diagnostics()
        check('software handoff diagnostics do not retain old hardware evidence',pipeline['hardware_decode'] is False and pipeline['active_decoders'] and all(d['engine']=='PyAV/libav worker' for d in pipeline['active_decoders']))
        check('retired native sources cannot override replacement video',not any(v.get('ready') for v in window.preview.gpu.sources.values()))
        item.contrast=original_contrast;window.transport.sync(True)
        deadline=time.monotonic()+5
        while not window.preview.gpu.sources.get(key,{}).get('ready') and time.monotonic()<deadline:wait(40)
        check('removing that operation restores native video',window.preview.gpu.sources.get(key,{}).get('ready',False))
        interaction_checks(window,out,check,wait)
        from .theme import PALETTES
        for theme in PALETTES:
            window.apply_theme(theme,save=False);wait(100)
            image=gpu.view.grabWindow();image.save(str(out/f'timeline-{theme}.png'))
            check(f'{theme} native surface covers its initialized viewport',gpu.container.geometry().width()==timeline.viewport().width()-12 and gpu.frames>0)
        window.apply_theme('default',save=False)
        from .playback_diagnostics_ui import show as show_diagnostics
        show_diagnostics(window);wait(80)
        check('playback diagnostics are accessible',window._playback_diagnostics_dialog.isVisible() and 'Direct3D11' in window._playback_diagnostics_dialog.details.toPlainText())
        window._playback_diagnostics_dialog.close()
        # Play/Pause correctness only; deliberately no latency/FPS benchmark.
        window.seek(162.6);wait(300);window.transport.play()
        pictures=[];brightness=[]
        for number in range(12):
            wait(90)
            picture=window.preview.gpu.view.grabWindow().copy(window.preview.composition_rect().toRect()).convertToFormat(QImage.Format_RGBA8888)
            if picture.isNull():
                (out/'capture-failure.json').write_text(json.dumps(window.preview.gpu.diagnostics(),indent=2),encoding='utf-8')
            check('playback capture '+str(number)+' returns an actual frame',not picture.isNull())
            pictures.append(hashlib.sha256(picture.constBits()).hexdigest())
            rgb=np.frombuffer(picture.constBits(),np.uint8).reshape(picture.height(),picture.width(),4)[:,:,:3]
            brightness.append(float(np.mean(np.max(rgb,axis=2)>20)))
            if number in (0,5,11):picture.save(str(out/f'playing-video-{number}.png'))
        window.transport.pause();wait(80)
        check('native playback advances and pauses',window.project.playhead>162.6 and not window.transport.playing)
        check('rendered video pixels advance during playback',len(set(pictures))>=4)
        check('rendered video does not become a blank canvas',min(brightness)>.15)
        report['video_processing']=dict(distinct_displayed_pictures=len(set(pictures)),sampled_pictures=len(pictures),minimum_visible_fraction=min(brightness))
        check('owner project is unchanged',before==hashlib.sha256(source.read_bytes()).hexdigest())
        report['owner_project']=dict(path=source.name,sha256=before,clips=len(window.project.timeline))
        from .creative_diagnostics import preview_checks
        preview_checks(window,out,check,wait)
        from .transition_diagnostics import preview_checks as transition_checks
        transition_checks(window,out,check,wait)
        composition_checks(window,out,check,wait)
        preview_gpu=window.preview.gpu
        if getattr(preview_gpu,'remote',False):
            check('main editor owns no video decoders',all(key[3]!='video' for key in window.transport.decoders))
            previous_helper=preview_gpu.diagnostics()['effect_helper_pid'];prepared=preview_gpu.completed
            preview_gpu.invalidate_caches();deadline=time.monotonic()+8
            while (preview_gpu.completed<=prepared or preview_gpu.diagnostics().get('effect_helper_pid') in (None,previous_helper)) and time.monotonic()<deadline:wait(40)
            check('cache clear replaces the isolated effect helper',preview_gpu.diagnostics().get('effect_helper_pid') not in (None,previous_helper) and preview_gpu.completed>prepared)
            check('cache clear rebuilds caption hit bounds',('caption','caption') in window.preview.text_rects)
            previous=preview_gpu.peer;previous_pid=preview_gpu.native_status['pid']
            # Exercise a genuine renderer/device failure using only this
            # retained test child. Editing/document state must survive it.
            with previous.process_lock:previous.process.terminate()
            deadline=time.monotonic()+12
            while (preview_gpu.peer is previous or preview_gpu.native_status['pid']==previous_pid or not preview_gpu.frames) and time.monotonic()<deadline:wait(40)
            check('owned renderer failure restarts without losing editor',preview_gpu.peer is not previous and not preview_gpu.peer.error and preview_gpu.native_status['pid']!=previous_pid and preview_gpu.frames>0)
            while ('caption','caption') not in window.preview.text_rects and time.monotonic()<deadline:wait(40)
            picture=preview_gpu.view.grabWindow()
            check('restarted renderer presents the current composition',not picture.isNull() and ('caption','caption') in window.preview.text_rects)
        text_focus_checks(window,check,wait)
        marquee_checks(window,out,check,wait)
        small_item_checks(window,check,wait)
        timeline_polish_checks(window,out,check,wait)
        last_track_checks(window,check,wait)
        blade_snap_checks(window,out,check,wait)
        blade_caption_priority_checks(window,out,check,wait)
        window.close();deadline=time.monotonic()+8
        while (window.isVisible() or getattr(preview_gpu,'remote',False) and preview_gpu.peer.active) and time.monotonic()<deadline:wait(30)
        check('editor and owned GPU preview close completely',not window.isVisible() and (not getattr(preview_gpu,'remote',False) or not preview_gpu.peer.active))
        if getattr(preview_gpu,'remote',False):
            check('normal GPU helper close exits gracefully without forced termination',preview_gpu.peer.exitcode==0 and not preview_gpu.peer.forced_shutdown)
        # Check the real export graph on a short disposable window of the owner
        # project, including its crops/layers/blur. Never export the full edit.
        from .rendergraph import command
        from .exporter import PRESETS
        from .export_process import render
        movie=out/'owner-short-render.mp4'
        args=command(Project.load(source),str(movie),next(iter(PRESETS.values())),False,'CPU',window.settings.get('ffmpeg','ffmpeg'),None,False,window=(162.6,163.2))
        code,tail=render(args,.6,None,None)
        check('short real-project export completes',code==0)
        import av
        with av.open(str(movie)) as decoder:frames=[frame.to_ndarray(format='rgb24') for frame in decoder.decode(video=0)]
        check('export contains moving nonblack video',len(frames)>5 and np.mean(frames[0])>10 and not np.array_equal(frames[0],frames[-1]))
        report['video_processing']['exported_frames']=len(frames)
    report['passed']=all(v['passed'] for v in report['checks'])
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0


def text_focus_checks(window,check,wait):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from .model import Project,TimelineItem,Caption
    project=Project(timeline=[TimelineItem('text','','video_1',0,3,role='title',title_text='Native title')],captions=[Caption('caption',0,3,'Native subtitle')])
    window.set_project(project);timeline=window.timeline;timeline.set_zoom(70);timeline.horizontalScrollBar().setValue(0)
    QApplication.setActiveWindow(window);wait(250)
    for kind,obj,field in [('title',project.timeline[0],window.inspector.title_text),('caption',project.captions[0],window.inspector.caption_text)]:
        rect=timeline.visible_item_rect(obj) if kind=='title' else timeline.visible_caption_rect(obj)
        QTest.mouseDClick(timeline.gpu.view,Qt.LeftButton,pos=rect.center().toPoint());wait(100)
        check('native '+kind+' double-click focuses text field',field.hasFocus())
        check('native '+kind+' caret is at text end',field.textCursor().atEnd() and not field.textCursor().hasSelection())


def marquee_checks(window,out,check,wait):
    from PySide6.QtCore import Qt,QPointF,QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .model import Project,TimelineItem,Caption
    project=Project(timeline=[TimelineItem('box-a','','video_1',.5,1.4,role='title',title_text='First'),
                              TimelineItem('box-b','','video_1',3,1.2,role='title',title_text='Second')],
                    captions=[Caption('box-caption',.5,1.4,'Subtitle')])
    project.timeline.extend(TimelineItem('far-'+str(i),'','video_1',100+i*2,1,role='title',title_text='Far') for i in range(1000))
    window.set_project(project);t=window.timeline;t.linked_selection=False;t.set_zoom(80);t.horizontalScrollBar().setValue(0);wait(180)
    view=t.gpu.view;lane=t.track_rect('video_1');start=QPointF(t.x_for_time(5),lane.bottom()-5)
    QTest.mousePress(view,Qt.LeftButton,pos=start.toPoint())
    for moment in (4.5,3.8,3.1,2.,1.,.2):
        end=QPointF(t.x_for_time(moment),lane.top()+5)
        QApplication.sendEvent(view,QMouseEvent(QEvent.MouseMove,end,QPointF(t.gpu.container.mapToGlobal(end.toPoint())),Qt.NoButton,Qt.LeftButton,Qt.NoModifier));wait(25)
    check('native marquee selects the intended clips on a long timeline',t.selected_ids=={'box-a','box-b'})
    check('native marquee geometry matches original selection rectangle',t.gpu.root.property('marquee')==t.marquee_controller.rects()[0])
    uploads=getattr(t.gpu,'_affordance_revision',0)
    for n in range(10):
        end=QPointF(t.x_for_time(.2)+n*.1,lane.top()+5)
        QApplication.sendEvent(view,QMouseEvent(QEvent.MouseMove,end,QPointF(t.gpu.container.mapToGlobal(end.toPoint())),Qt.NoButton,Qt.LeftButton,Qt.NoModifier));wait(20)
    check('native moving selection box does not upload full timeline images',getattr(t.gpu,'_affordance_revision',0)==uploads)
    view.grabWindow().save(str(out/'native-marquee.png'))
    QTest.mouseRelease(view,Qt.LeftButton,pos=end.toPoint());wait(80)
    check('finished marquee refreshes the inspector for selected media',window.inspector.item_id in t.selected_ids and not t.drag_mode)
    check('marquee selection does not create edit history',len(window.project.timeline)==1002)


def small_item_checks(window,check,wait):
    from PySide6.QtCore import Qt,QPointF,QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .model import Project,TimelineItem,Caption
    project=Project(timeline=[TimelineItem('tiny-video','','video_1',1,.25),
                              TimelineItem('tiny-audio','','audio_1',1,.25,role='source_audio'),
                              TimelineItem('tiny-title','','video_1',2,.25,role='title',title_text='Tiny'),
                              TimelineItem('tiny-graphic','','video_1',3,.25,role='graphic',graphic_type='Square')],
                    captions=[Caption('tiny-caption',1,1.25,'Tiny')])
    window.set_project(project);t=window.timeline;t.linked_selection=False;t.set_zoom(20);t.horizontalScrollBar().setValue(0);wait(150)
    for item in [*project.timeline,*project.captions]:
        caption=isinstance(item,Caption);rect=t.visible_caption_rect(item) if caption else t.visible_item_rect(item)
        pos=rect.center();view=t.gpu.view
        QApplication.sendEvent(view,QMouseEvent(QEvent.MouseMove,pos,QPointF(t.gpu.container.mapToGlobal(pos.toPoint())),Qt.NoButton,Qt.NoButton,Qt.NoModifier));wait(20)
        check(item.id+' native center shows a selection cursor',t.gpu.container.cursor().shape()==Qt.ArrowCursor)
        QTest.mousePress(view,Qt.LeftButton,pos=pos.toPoint())
        check(item.id+' native center selects rather than trims',t.drag_mode==('caption_move' if caption else 'move'))
        QTest.mouseRelease(view,Qt.LeftButton,pos=pos.toPoint());wait(25)
    check('tiny center clicks preserve media and caption durations',all(i.duration==.25 for i in project.timeline) and project.captions[0].end==1.25)


def blade_snap_checks(window,out,check,wait):
    from PySide6.QtCore import Qt,QPointF,QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from .model import Project,TimelineItem,Caption
    for kind in ('video','audio','caption'):
        project=Project(video_tracks=['video_1','video_2'],timeline=[TimelineItem('target','','video_1' if kind!='audio' else 'audio_1',0,10,role='title' if kind!='audio' else 'source_audio',title_text='Snap target'),TimelineItem('above','','video_2',0,5,role='title',title_text='Existing cut'),TimelineItem('after','','video_2',5,5,role='title',title_text='Existing cut')],captions=[Caption('caption',0,10,'Caption snap target')] if kind=='caption' else [])
        project.timeline.extend([TimelineItem('stagger-one','','video_2',5.12,2,role='title',title_text='Staggered cut'),TimelineItem('stagger-two','','video_2',5.24,2,role='title',title_text='Staggered cut')])
        project.playhead=9;window.set_project(project);t=window.timeline;t.linked_selection=False;t.set_zoom(100);t.horizontalScrollBar().setValue(0);t.setProperty('snapping',True);window.set_timeline_tool('blade');wait(100)
        item=project.captions[0] if kind=='caption' else project.timeline[0]
        rect=t.visible_caption_rect(item) if kind=='caption' else t.visible_item_rect(item);view=t.gpu.view
        def move(at):
            pos=QPointF(t.x_for_time(at),rect.center().y());QTest.mouseMove(view,pos.toPoint());wait(20);return pos
        move(4.89);check(kind+' blade acquires cross-layer cut',t.blade_hover_time==5)
        pos=move(5.02);check(kind+' blade holds through small mouse motion',t.blade_hover_time==5)
        if kind=='video':t.gpu.view.grabWindow().save(str(out/'sticky-blade.png'))
        for sequence,direction in ((range(490,535),'right'),(range(534,489,-1),'left')):
            aligned=True;seen=set()
            for step in sequence:
                pointer=step/100;move(pointer);nearest=min((5.,5.12,5.24),key=lambda edge:abs(edge-pointer))
                aligned=aligned and t.blade_hover_time is not None and abs(abs(t.blade_hover_time-pointer)-abs(nearest-pointer))<1e-6
                seen.add(t.blade_hover_time)
            check(kind+' continuous '+direction+' blade sweep follows every nearest staggered cut',aligned and {5.,5.12,5.24}<=seen)
        pos=move(5.13);check(kind+' blade hands off without leaving the timeline',t.blade_hover_time==5.12)
        QTest.mouseClick(view,Qt.LeftButton,pos=pos.toPoint());wait(50)
        if kind=='caption':aligned=any(c.start==5.12 for c in project.captions) and any(c.end==5.12 for c in project.captions)
        else:aligned=any(i.track==item.track and i.start==5.12 for i in project.timeline) and any(i.track==item.track and i.start+i.duration==5.12 for i in project.timeline)
        check(kind+' blade click splits at the displayed snapped timestamp',aligned)
        window.undo();wait(30);check(kind+' snapped cut remains undoable',len(window.project.captions)==1 if kind=='caption' else len(window.project.timeline)==5)
    window.set_timeline_tool('select')


def blade_caption_priority_checks(window,out,check,wait):
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtTest import QTest
    from .model import Project,TimelineItem,Caption
    for kind in ('video','audio'):
        for zoom in (50,200):
            project=Project(video_tracks=['video_1','video_2'],timeline=[TimelineItem('target','','video_1' if kind=='video' else 'audio_1',0,10,role='title' if kind=='video' else 'source_audio',title_text='Blade target'),TimelineItem('before','','video_2',0,5,role='title'),TimelineItem('after','','video_2',5,5,role='title'),TimelineItem('next','','video_2',5.24,2,role='title')],captions=[Caption('nearby',5.04,8,'Small subtitle offset')])
            project.playhead=9;window.set_project(project);t=window.timeline;t.linked_selection=False;t.set_zoom(zoom);t.horizontalScrollBar().setValue(0);t.setProperty('snapping',True);window.set_timeline_tool('blade');wait(80)
            item=project.timeline[0];rect=t.visible_item_rect(item);view=t.gpu.view
            def move(at):
                pos=QPointF(t.x_for_time(at),rect.center().y());QTest.mouseMove(view,pos.toPoint());wait(20);return pos
            pos=move(5.04);expected=5. if zoom==50 else 5.04
            check(kind+' zoom '+str(zoom)+' resolves near subtitle/video cuts by visual separation',t.blade_hover_time==expected)
            if zoom==50:
                move(5.14);check(kind+' priority hands off to the next video cut without a latch',t.blade_hover_time==5.24)
                pos=move(5.04)
                if kind=='video':view.grabWindow().save(str(out/'blade-caption-priority.png'))
            QTest.mouseClick(view,Qt.LeftButton,pos=pos.toPoint());wait(35)
            check(kind+' zoom '+str(zoom)+' click matches the priority hover timestamp',any(i.track==item.track and i.start==expected for i in project.timeline))
            window.undo();wait(20);check(kind+' zoom '+str(zoom)+' priority cut remains undoable',len(window.project.timeline)==4)
    window.set_timeline_tool('select')


def timeline_polish_checks(window,out,check,wait):
    import numpy as np
    from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QObject
    from PySide6.QtGui import QImage,QMouseEvent
    from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLineEdit
    from PySide6.QtTest import QTest
    from .controls import SafeDoubleSpinBox,SafeSpinBox
    from .model import Project,Caption,TimelineItem
    # Real focus transfer through the native spin-box proxy, with and without
    # new text. No synthetic FocusOut and no Enter key.
    host=QWidget(window);layout=QVBoxLayout(host);other=QLineEdit(host)
    spins=[SafeDoubleSpinBox(host),SafeSpinBox(host)]
    for spin in spins:spin.setRange(-100,100);spin.setValue(3);layout.addWidget(spin)
    layout.addWidget(other);host.setGeometry(400,100,240,150);host.show();host.raise_();wait(50)
    try:
        for spin in spins:
            for changed,blank in ((False,False),(True,False),(False,True),(True,True)):
                line=spin.lineEdit();QTest.mouseDClick(line,Qt.LeftButton)
                if changed:QTest.keyClicks(spin,'7')
                QTest.mouseClick(host,Qt.LeftButton,pos=QPoint(235,145)) if blank else QTest.mouseClick(other,Qt.LeftButton)
                wait(25)
                label=type(spin).__name__+(' edited' if changed else ' unchanged')+(' empty-space' if blank else ' other-field')
                check(label+' focus loss restores scrub mode',not spin._typing and spin.focusPolicy()==Qt.NoFocus and (not spin.hasFocus() if blank else other.hasFocus()))
                before=spin.value();pos=QPoint(8,8);QTest.mousePress(line,Qt.LeftButton,pos=pos)
                global_pos=spin._drag_start+QPoint(20,0) if spin._drag_start is not None else line.mapToGlobal(pos)
                QApplication.sendEvent(line,QMouseEvent(QEvent.MouseMove,QPointF(28,8),QPointF(global_pos),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
                QTest.mouseRelease(line,Qt.LeftButton,pos=pos)
                check(label+' immediately drags without Enter',spin.value()>before)
    finally:host.close();host.deleteLater()
    # Exercise the owner's first interaction after clip deselection/reselection
    # in the actual inspector, including events delivered to either Qt target.
    for theme in ('default','final_cut_obsidian','ableton_gray'):
        window.apply_theme(theme,save=False)
        for width in (1700,1100):
            window.resize(width,900)
            p=Project(timeline=[TimelineItem('audio-a','','audio_1',0,2,role='source_audio'),TimelineItem('audio-b','','audio_1',2,2,role='source_audio'),TimelineItem('video-a','','video_1',0,2),TimelineItem('video-b','','video_1',2,2)])
            window.set_project(p)
            for item_id,target_name in (('video-a','line'),('video-b','spin'),('audio-a','line'),('audio-b','spin')):
                t=window.timeline
                track=window.project.item_by_id(item_id).track
                blank=QPoint(t.LABEL_WIDTH+round(5*t.pixels_per_second),round(t.section_rect(track).center().y()))
                t.gpu.view.requestActivate();wait(20)
                QTest.mouseClick(t.gpu.view,Qt.LeftButton,pos=blank-t.gpu.offset.toPoint());wait(25)
                check(f'{theme} {width} native blank click deselects all before '+item_id,not t.selected_ids)
                clip_pos=t.item_rect(window.project.item_by_id(item_id)).center().toPoint()
                QTest.mouseClick(t.gpu.view,Qt.LeftButton,pos=clip_pos-t.gpu.offset.toPoint());wait(40)
                check(f'{theme} {width} native click selects '+item_id,t.selected_id==item_id)
                spin=window.inspector.volume.spin if track=='audio_1' else window.inspector.zoom_x.spin;line=spin.lineEdit()
                label=f'{theme} {width} {item_id} first {target_name} drag'
                # No pre-focus: the owner's first gesture crosses from the
                # native timeline window directly into the inspector edit.
                check(label+' rejects automatic text selection',not spin._typing and not line.hasSelectedText())
                check(label+' shows horizontal adjustment cursor',line.cursor().shape()==Qt.SizeHorCursor)
                def current_value():
                    item=window.project.item_by_id(item_id)
                    return item.gain_db if track=='audio_1' else item.transform.scale
                target=line if target_name=='line' else spin;pos=target.rect().center();before=current_value()
                # Route through the native top-level window and Qt hit-testing,
                # as a real mouse does, rather than send directly to the edit.
                native_window=window.windowHandle();local=window.mapFromGlobal(target.mapToGlobal(pos))
                QTest.mouseMove(native_window,local);wait(10)
                QTest.mousePress(native_window,Qt.LeftButton,pos=local)
                check(label+' starts immediately',spin._drag_start is not None)
                QTest.mouseMove(native_window,local+QPoint(8,0),delay=20)
                QTest.mouseRelease(native_window,Qt.LeftButton,pos=local+QPoint(8,0));wait(25)
                after=current_value()
                check(label+' changes actual clip without highlighting',after>before and not line.hasSelectedText())
                check(label+' restores adjustment cursor after drag',line.cursor().shape()==Qt.SizeHorCursor)
                window.undo();check(label+' remains undoable',current_value()==before)
                window.redo();check(label+' remains redoable',current_value()==after)
                QTest.mouseDClick(line,Qt.LeftButton);check(label+' explicit double-click selects text',spin._typing and line.hasSelectedText())
                check(label+' shows text cursor only while typing',line.cursor().shape()==Qt.IBeamCursor)
                QTest.mouseClick(window,Qt.LeftButton,pos=QPoint(window.width()-2,window.height()-2));wait(10)
                check(label+' blank click restores unselected drag mode',not spin._typing and not line.hasSelectedText())
                check(label+' restores adjustment cursor after typing',line.cursor().shape()==Qt.SizeHorCursor)
            window.grab().save(str(out/f'numeric-first-drag-{theme}-{width}.png'))
    window.resize(1700,1000)
    captions=[];at=.5
    for n,width in enumerate((8,18,24,32,40,80,150)):
        captions.append(Caption('label-'+str(width),at,at+width/40,'a very good caption with more words than fit'))
        at+=width/40+.3
    p=Project(captions=captions,timeline=[TimelineItem('fade-title','','video_1',.5,3,role='title',title_text='A longer title can wrap too')])
    window.set_project(p);t=window.timeline;t.set_zoom(40);t.horizontalScrollBar().setValue(0)
    for theme in ('default','final_cut_obsidian','ableton_gray'):
        window.apply_theme(theme,save=False);wait(140)
        image=t.gpu.view.grabWindow().convertToFormat(QImage.Format_RGBA8888);image.save(str(out/f'caption-labels-{theme}.png'))
        for cap in captions[1:]:
            rect=t.caption_rect(cap).adjusted(4,4,-4,-3).toAlignedRect();part=image.copy(rect)
            pixels=np.frombuffer(part.constBits(),np.uint8).reshape(part.height(),part.width(),4)
            check(theme+' partial caption label visible at '+cap.id,np.count_nonzero(np.max(pixels[:,:,:3],axis=2)<90)>2)
        cap=captions[0];rect=t.caption_rect(cap)
        check(theme+' caption uses reference cream',image.pixelColor(round(rect.center().x()),round(rect.center().y())).name()=='#b9b097')
    window.apply_theme('default',save=False);t.select_ids({'fade-title'},'fade-title');wait(80)
    image=t.gpu.view.grabWindow().convertToFormat(QImage.Format_RGBA8888);image.save(str(out/'fade-tab.png'))
    rect=t.item_rect(p.timeline[0]);x=round(rect.left()+5);y=round(rect.top())
    check('native fade tab has flat white shoulders',image.pixelColor(x-2,y+4).red()>220 and image.pixelColor(x+2,y+4).red()>220)
    check('native fade tab extends down from top edge',image.pixelColor(x,y+9).red()>220)


def last_track_checks(window,check,wait):
    import copy
    from PySide6.QtCore import QTimer,Qt
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtTest import QTest
    from .model import Project,TimelineItem
    def confirm():
        box=QApplication.activeModalWidget()
        if isinstance(box,QMessageBox):QTest.mouseClick(box.button(QMessageBox.Yes),Qt.LeftButton)
    def body(project):
        value=copy.deepcopy(project.to_dict());value.pop('modified_at',None);value.pop('playhead',None);return value
    for kind in ('video','audio'):
        track=kind+'_1';other='audio_1' if kind=='video' else 'video_1'
        p=Project(timeline=[TimelineItem('remove','',track,0,2,role='title' if kind=='video' else 'source_audio'),
                            TimelineItem('keep','',other,0,2,role='title' if kind=='audio' else 'source_audio')])
        p.track_names[track]='Custom Layer';p.track_states[track]={'visible':False,'locked':False,'muted':True}
        window.set_project(p);before=body(p)
        QTimer.singleShot(60,confirm);window.timeline_command('delete_track',track);wait(80)
        check(kind+' final layer remains one empty default layer',getattr(window.project,kind+'_tracks')==[track] and not any(i.track==track for i in window.project.timeline)
              and window.project.track_names[track]==kind.title()+' 1' and window.project.track_states[track]=={'visible':True,'locked':False,'muted':False})
        check(kind+' final-layer reset preserves the other media type',[i.id for i in window.project.timeline]==['keep'])
        window.undo();wait(40);check(kind+' final-layer reset is fully undoable',body(window.project)==before)
        window.redo();wait(40);check(kind+' final-layer reset can be redone',[i.id for i in window.project.timeline]==['keep'])
        p=Project();second=p.add_track(kind);p.timeline=[TimelineItem('remove','',track,0,2)]
        window.set_project(p);QTimer.singleShot(60,confirm);window.timeline_command('delete_track',track);wait(40)
        check(kind+' multiple-layer deletion still removes the chosen layer',getattr(window.project,kind+'_tracks')==[second] and window.project.track_names[second]==kind.title()+' 2')
        p=Project();second=p.add_track(kind);p.add_track(kind)
        p.timeline=[TimelineItem('populated','',second,0,2,role='title' if kind=='video' else 'source_audio')]
        window.set_project(p);window.timeline.selected_track=track;before=body(p)
        window.timeline_command('delete_empty_tracks',None);wait(40)
        check(kind+' empty bottom lane yields to populated lane',getattr(p,kind+'_tracks')==[second]
              and p.track_names[second]==kind.title()+' 1' and p.timeline[0].track==second and window.timeline.selected_track==second)
        window.undo();wait(40);check(kind+' delete-empty promotion is undoable',body(window.project)==before)


def composition_checks(window,out,check,wait):
    """Render real layout consumers, including cross-track legacy overlays."""
    import time,copy
    import numpy as np
    from PySide6.QtCore import QRectF,Qt
    from PySide6.QtGui import QImage,QPainter,QColor
    from .model import Project,MediaItem,TimelineItem,Caption,CaptionStyle,Transform
    from .graphics import default_graphic_data
    from .preview_compositor import SceneContext,render
    from .transitions import Transition
    image=QImage(320,180,QImage.Format_RGBA8888);image.fill(QColor('#285d80'))
    painter=QPainter(image);painter.fillRect(0,0,160,90,QColor('#ef3030'));painter.fillRect(160,90,160,90,QColor('#20d050'));painter.end()
    path=out/'composition-source.png';image.save(str(path))
    media=MediaItem('photo',str(path),'image','Composition image',4,320,180)
    project=Project(media=[media]);project.settings.width=360;project.settings.height=640
    for _ in range(4):project.add_track('video')
    base=TimelineItem('base','photo','video_1',0,4)
    shifted=TimelineItem('shifted','photo','video_2',0,4,opacity=65,transform=Transform(.55,.4,.55,rotation=12))
    title=TimelineItem('title','','video_3',0,4,role='title',title_text='HEADLINE',title_style=CaptionStyle(size=38,color='#ffffff',animation='none',position_y=.2,outline_width=0))
    graphic=TimelineItem('shape','','video_4',0,4,role='graphic',graphic_type='Square',graphic_data={**default_graphic_data('Square'),'fill_enabled':True,'fill_color':'#30ff70'},transform=Transform(.5,.6,.35))
    motion=TimelineItem('motion','','video_5',0,4,role='graphic',graphic_type='Motion Composition',transform=Transform(.5,.7,.4))
    project.timeline=[base,shifted,title,graphic,motion]
    project.captions=[Caption('caption',0,4,'CAPTION')];project.subtitle_style=CaptionStyle(size=36,color='#ffff00',animation='none',position_y=.88)
    window.set_project(project);window.preview.set_transform_controls_visible(False);window.seek(1.4)
    def parity(name):
        gpu=window.preview.gpu;previous=gpu.completed;gpu.signature=None;gpu.schedule();deadline=time.monotonic()+8
        while gpu.completed<=previous and time.monotonic()<deadline:wait(40)
        wait(150)
        picture=gpu.view.grabWindow().copy(window.preview.composition_rect().toRect()).convertToFormat(QImage.Format_RGBA8888)
        context=SceneContext(copy.deepcopy(window.project),{},{},{},True,1.)
        reference,_,_=render(context,QRectF(0,0,picture.width(),picture.height()),(picture.width(),picture.height()),1.)
        reference=reference.convertToFormat(QImage.Format_RGBA8888)
        actual=np.frombuffer(picture.constBits(),np.uint8).reshape(picture.height(),picture.width(),4).astype(float)
        expected=np.frombuffer(reference.constBits(),np.uint8).reshape(reference.height(),reference.width(),4).astype(float)
        difference=float(np.abs(actual[:,:,:3]-expected[:,:,:3]).mean())
        picture.save(str(out/f'{name}-gpu.png'));reference.save(str(out/f'{name}-reference.png'))
        check(name+' preserves composited pixels',difference<8)
        return gpu
    gpu=parity('titles-captions-motion-and-shapes')
    check('graphic/title/caption hit bounds survive',all(key in window.preview.text_rects for key in (('title','title'),('graphic','shape'),('graphic','motion'),('caption','caption'))))
    image.fill(QColor('#6a2248'));image.save(str(path));gpu.schedule()
    parity('externally-replaced-still-image')
    shifted.composite_mode='Multiply';window.transport.sync(True);parity('non-normal-blending')
    check('whole-scene fallback is reported honestly',window.preview.gpu.diagnostics()['composition']=='CPU whole-scene fallback / GPU presentation')
    shifted.composite_mode='Normal'
    project.timeline=[TimelineItem('left','photo','video_1',0,1.5),TimelineItem('right','photo','video_1',1.5,2.5,transform=Transform(.4,.5,.75)),title,graphic,motion]
    project.transitions=[Transition('dissolve','Cross Dissolve',track='video_1',start=1.2,duration=.6,left_item_id='left',right_item_id='right')]
    window.transport.sync(True);window.seek(1.4);parity('transition-with-overlays')
    window.caption_focus_button.setChecked(True);window.preview.select_caption('caption');wait(100)
    check('caption focus retains visible text and navigation controls',not gpu.container.isVisible() and ('caption','caption') in window.preview.text_rects and all(b.isVisible() for b in window.caption_focus.buttons))
    window.caption_focus_button.setChecked(False);wait(150)
    check('leaving caption focus restores the native preview',gpu.container.isVisible())


import ctypes
from ctypes import wintypes as W
from PySide6.QtGui import QImage
class INFOHEADER(ctypes.Structure):
 _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),('bitCount',W.WORD),('compression',W.DWORD),('sizeImage',W.DWORD),('xppm',W.LONG),('yppm',W.LONG),('used',W.DWORD),('important',W.DWORD)]
def capture_native_host(widget,path=None):
 u=ctypes.WinDLL('user32');g=ctypes.WinDLL('gdi32');hwnd=int(widget.winId());r=W.RECT();u.GetClientRect(W.HWND(hwnd),ctypes.byref(r));width=r.right;height=r.bottom
 u.GetDC.restype=W.HDC;g.CreateCompatibleDC.restype=W.HDC;g.CreateCompatibleBitmap.restype=W.HBITMAP;g.SelectObject.restype=W.HGDIOBJ
 dc=u.GetDC(W.HWND(hwnd));memory=g.CreateCompatibleDC(W.HDC(dc));bitmap=g.CreateCompatibleBitmap(W.HDC(dc),width,height);prior=g.SelectObject(W.HDC(memory),W.HGDIOBJ(bitmap))
 try:
  ok=u.PrintWindow(W.HWND(hwnd),W.HDC(memory),3)
  header=INFOHEADER(ctypes.sizeof(INFOHEADER),width,-height,1,32,0,width*height*4,0,0,0,0);data=ctypes.create_string_buffer(width*height*4)
  lines=g.GetDIBits(W.HDC(memory),W.HBITMAP(bitmap),0,height,data,ctypes.byref(header),0)
  image=QImage(data.raw,width,height,width*4,QImage.Format_RGB32).copy();
  if path:image.save(str(path))
  if not ok or lines!=height:raise RuntimeError('Native host capture failed')
  return image
 finally:g.SelectObject(W.HDC(memory),W.HGDIOBJ(prior));g.DeleteObject(W.HGDIOBJ(bitmap));g.DeleteDC(W.HDC(memory));u.ReleaseDC(W.HWND(hwnd),W.HDC(dc))


def interaction_checks(window,out,check,wait):
    """Native-surface editing correctness only; no performance measurements."""
    from PySide6.QtCore import Qt,QEvent,QPointF,QPoint
    from PySide6.QtGui import QMouseEvent,QWheelEvent
    from PySide6.QtTest import QTest
    timeline=window.timeline;view=timeline.gpu.view
    def document():
        value=window.project.to_dict();value.pop('playhead',None);value.pop('modified_at',None);return value
    window.transport.pause();window.seek(162.6);timeline.set_zoom(35);timeline.horizontalScrollBar().setValue(5250);wait(200)
    candidates=[i for i in window.project.runtime_index.query('timeline',155,175) if i.track in window.project.video_tracks
        and timeline.visible_item_rect(i).width()>60 and timeline.visible_item_rect(i).height()>25
        and timeline.item_rect(i).left()>timeline.LABEL_WIDTH+15 and timeline.item_rect(i).right()<view.width()-20]
    first=max(candidates,key=lambda i:i.duration);second=next(i for i in candidates if i.id!=first.id)
    linked=timeline.linked_selection;timeline.linked_selection=False
    try:
        # QQuickWindow does not create QWidget context events automatically.
        # Exercise real right-button input, not a direct menu-handler call.
        from PySide6.QtWidgets import QApplication,QMenu
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QContextMenuEvent
        point=timeline.visible_item_rect(first).center().toPoint()
        QTest.mouseClick(view,Qt.RightButton,pos=point);wait(80)
        menu=QApplication.activePopupWidget()
        check('native clip right click opens original editing menu',isinstance(menu,QMenu) and any('Retime Controls' in a.text() for a in menu.actions()))
        menu.close();wait(40)
        for name,point in [('layer header',QPoint(24,point.y())),('empty timeline',QPoint(view.width()-25,point.y()))]:
            # Header/empty menus use the original modal exec implementation.
            # Schedule dismissal before dispatching the physical right click.
            observed=[]
            def dismiss():
                popup=QApplication.activePopupWidget()
                observed.append(isinstance(popup,QMenu) and any(a.text()=='Add Video Track' for a in popup.actions()))
                if popup:popup.close()
            QTimer.singleShot(100,dismiss)
            # Guarantee genuinely empty horizontal space for the empty menu.
            if name=='empty timeline':
                timeline.horizontalScrollBar().setValue(round((window.project.duration+3)*timeline.pixels_per_second));wait(40)
            QTest.mouseClick(view,Qt.RightButton,pos=point);wait(50)
            check('native '+name+' right click opens layer actions',observed==[True])
        timeline.horizontalScrollBar().setValue(5250);wait(70)
        QTest.mouseClick(view,Qt.LeftButton,pos=timeline.visible_item_rect(first).center().toPoint())
        QTest.mouseClick(view,Qt.LeftButton,Qt.ControlModifier,pos=timeline.visible_item_rect(second).center().toPoint());wait(70)
        check('native timeline preserves additive multi-selection',{first.id,second.id}<=timeline.selected_ids)
        def drag(origin,target):
            QTest.mousePress(view,Qt.LeftButton,pos=origin.toPoint())
            event=QMouseEvent(QEvent.MouseMove,target,QPointF(timeline.gpu.container.mapToGlobal(target.toPoint())),Qt.NoButton,Qt.LeftButton,Qt.NoModifier)
            QApplication.sendEvent(view,event)
            QTest.mouseRelease(view,Qt.LeftButton,pos=target.toPoint());wait(90)
        from PySide6.QtWidgets import QApplication
        timeline.select_ids({first.id},first.id);before=document();old=window.project.item_by_id(first.id).start
        origin=timeline.visible_item_rect(window.project.item_by_id(first.id)).center()
        drag(origin,origin+QPointF(25,0))
        check('native clip body drag moves the clip',window.project.item_by_id(first.id).start!=old)
        window.undo();wait(80);check('native clip move is fully undoable',document()==before)
        item=window.project.item_by_id(first.id);timeline.select_ids({item.id},item.id);before=document();duration=item.duration
        rect=timeline.item_rect(item);origin=QPointF(rect.right()-1,rect.center().y())
        drag(origin,origin-QPointF(13,0))
        check('native clip edge drag trims the clip',window.project.item_by_id(item.id).duration<duration)
        window.undo();wait(80);check('native trim is fully undoable',document()==before)
        window.seek(162.6)
        item=next(i for i in window.project.runtime_index.active('timeline',162.6) if i.track in window.project.video_tracks and i.role not in ('graphic','title'))
        timeline.select_ids({item.id},item.id);window.select_item(item.id);wait(90)
        before=document();scale=item.transform.scale;spin=window.inspector.zoom_x.spin
        spin.setFocus();QTest.keyClick(spin,Qt.Key_Up);spin.clearFocus();wait(90)
        check('inspector spinner edits the GPU media transform',window.project.item_by_id(item.id).transform.scale!=scale)
        window.undo();wait(80);check('inspector transform remains undoable',document()==before)
        sharpen_checks(window,out,check,wait,item.id)
        preview=window.preview;native=preview.gpu.view
        def pan():
            QTest.mousePress(native,Qt.MiddleButton,pos=QPoint(80,80))
            QApplication.sendEvent(native,QMouseEvent(QEvent.MouseMove,QPointF(120,100),QPointF(preview.gpu.container.mapToGlobal(QPoint(120,100))),Qt.NoButton,Qt.MiddleButton,Qt.NoModifier))
            QTest.mouseRelease(native,Qt.MiddleButton,pos=QPoint(120,100));wait(60)
        initial=QPointF(preview.view_pan);pan();check('native preview pan works while paused',preview.view_pan!=initial);preview.reset_view()
        QTest.keyClick(view,Qt.Key_Space);wait(120);check('native timeline Space shortcut starts playback',window.transport.playing)
        initial=QPointF(preview.view_pan);pan();check('native preview pan locks during playback',preview.view_pan==initial)
        initial_zoom=preview.view_zoom;pos=QPointF(native.width()/2,native.height()/2)
        QApplication.sendEvent(native,QWheelEvent(pos,QPointF(preview.gpu.container.mapToGlobal(pos.toPoint())),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False));wait(60)
        check('native preview wheel zoom remains available during playback',preview.view_zoom>initial_zoom)
        QTest.keyClick(native,Qt.Key_Space);wait(100);check('native preview Space shortcut pauses playback',not window.transport.playing)
        preview.reset_view()
    finally:
        timeline.linked_selection=linked;window.transport.pause()


def sharpen_checks(window,out,check,wait,identifier):
    """Paused same-source crops must survive live Sharpen edits through zero."""
    import time
    import numpy as np
    from PySide6.QtGui import QImage
    item=window.project.item_by_id(identifier);gpu=window.preview.gpu
    original=item.sharpen;controls=window.preview.transform_controls_visible
    window.preview.set_transform_controls_visible(False);wait(100)
    frames=[];engines=[]
    try:
        for value in (.7,0,1.2,0,.3,0):
            item.sharpen=value;window.transport.sync(True)
            wait(100)
            picture=gpu.view.grabWindow().copy(window.preview.composition_rect().toRect()).convertToFormat(QImage.Format_RGBA8888)
            pixels=np.frombuffer(picture.constBits(),np.uint8).reshape(picture.height(),picture.width(),4)
            frames.append(float(np.mean(np.max(pixels[:,:,:3],axis=2)>20)))
            engines.append([d['engine'] for d in gpu.diagnostics().get('active_decoders',[])])
            picture.save(str(out/f'sharpen-{len(frames)}-{value}.png'))
        check('live Sharpen through zero never clears the composition',min(frames)>.15)
        check('Sharpen keeps every same-source crop on native GPU video',all(v and all('PyAV' not in e for e in v) for v in engines))
        # The effect genuinely changes selected pixels; a no-op is not a fix.
        a=QImage(str(out/'sharpen-1-0.7.png'));b=QImage(str(out/'sharpen-2-0.png'))
        check('GPU Sharpen changes actual cropped video pixels',a!=b)
    finally:
        item.sharpen=original;window.transport.sync(True);window.preview.set_transform_controls_visible(controls)
