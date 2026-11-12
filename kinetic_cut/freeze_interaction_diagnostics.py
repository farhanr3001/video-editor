"""Phase-one native freeze investigation: ordinary mixed editing at three cadences."""
def run(output):
    import os,sys,time,json,copy,wave,math,struct,hashlib,traceback,subprocess
    from pathlib import Path
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ.update(KINETIC_CUT_HOME=str(out/'home'),QT_QPA_PLATFORM='windows' if os.name=='nt' else 'offscreen',QSG_RHI_BACKEND='d3d11')
    from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QTimer,QEventLoop,QThreadPool
    from PySide6.QtGui import QImage,QMouseEvent
    from PySide6.QtWidgets import QApplication,QDialogButtonBox
    from .ui import MainWindow
    from .model import Project,ProjectSettings,MediaItem,TimelineItem,Caption,Transform,Crop
    from .effects_library import asset_directory
    from .crash_logging import HangWatchdog
    from .activity_log import install,read
    from .process import run as run_process
    from .icons import resource_path
    app=QApplication([]);app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False);app.setProperty('kineticTestDiscardUnsaved',True)
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),actions=[],speeds=[],checks=[],exceptions=[],os_pointer_control=False)
    import psutil
    process=psutil.Process();rounds=max(1,min(8,int(os.environ.get('KINETIC_FREEZE_ROUNDS','2'))));report['rounds_per_speed']=rounds;report['resources']=[]
    old_hook=sys.excepthook;sys.excepthook=lambda *args:report['exceptions'].append(''.join(traceback.format_exception(*args)))
    window=None;guard=None;timer=None;journal=install(out)
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def check(name,value):
        report['checks'].append(dict(name=name,passed=bool(value)));assert value,name
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    def event(widget,kind,pos,button,buttons,mod=Qt.NoModifier):
        app.sendEvent(widget,QMouseEvent(kind,QPointF(pos),QPointF(widget.mapToGlobal(pos)),button,buttons,mod))
    def drag(widget,start,end,mod=Qt.NoModifier,button=Qt.LeftButton):
        event(widget,QEvent.MouseButtonPress,start,button,button,mod)
        for n in range(1,7):
            pos=start+(end-start)*n/6;event(widget,QEvent.MouseMove,pos,Qt.NoButton,button,mod);wait(12)
        event(widget,QEvent.MouseButtonRelease,end,button,Qt.NoButton,mod)
    try:
        video=out/'editing-source.mp4';audio=out/'editing-source.wav'
        ffmpeg=resource_path('assets','tools','ffmpeg.exe')
        if not ffmpeg.is_file():ffmpeg='ffmpeg'
        run_process([str(ffmpeg),'-hide_banner','-loglevel','error','-y','-i',str(asset_directory()/'samples/moving-object.kcpreview'),'-t','12','-vf','scale=1280:720','-r','60','-c:v','libx264','-threads','2','-preset','ultrafast','-crf','19',str(video)],check=True,capture_output=True)
        with wave.open(str(audio),'wb') as f:
            f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b''.join(struct.pack('<h',round(math.sin(n*.057)*4500)) for n in range(288000)))
        protected={str(p):digest(p) for p in (video,audio)}
        media=[MediaItem('vsrc',str(video),'video','Editing source',12,1280,720,60,False,video_codec='h264'),MediaItem('asrc',str(audio),'audio','Editing audio',12,has_audio=True)]
        fixture=Project(name='Disposable editing session',settings=ProjectSettings(width=1080,height=1920,fps=60),media=media)
        for _ in range(3):fixture.add_track('video')
        fixture.timeline=[]
        for n in range(15):
            for layer in (1,2,3):
                item=TimelineItem(f'v{layer}-{n}','vsrc',f'video_{layer}',n*4,4,in_point=(n%3)*4,link_id=f'pair{n}',transform=Transform(.5,.5 if layer<3 else .2,1 if layer<3 else .45))
                if layer==1:item.effects=[dict(name='Gaussian Blur',enabled=True,horizontal=12.,vertical=12.,linked=True,border='Reflect',blend=100.)]
                fixture.timeline.append(item)
            fixture.timeline.append(TimelineItem(f'a{n}','asrc','audio_1',n*4,4,in_point=(n%3)*4,link_id=f'pair{n}'))
        fixture.timeline.append(TimelineItem('title','','video_4',1,2,role='title',title_text='Editing title',link_id=''))
        fixture.captions=[Caption('caption'+str(n),n*.6+.1,n*.6+.58,'Clear words') for n in range(100)]
        window=MainWindow();window.resize(1480,900);window.show();window.monitor_control.set_level(0)
        report['fixture']=dict(seconds=fixture.duration,video_layers=4,items=len(fixture.timeline),captions=len(fixture.captions),source=[1280,720,60])
        window.set_project(copy.deepcopy(fixture));window.center_split.setSizes([470,360]);window.timeline.set_zoom(95);window.snap_tool.click();wait(1200)
        guard=HangWatchdog(out/'crash-trace.log',timeout=3.,interval=.15,max_reports=6)
        gaps=[];last=time.monotonic()
        def beat():
            nonlocal last
            now=time.monotonic();gaps.append(now-last);last=now;guard.beat()
        timer=QTimer();timer.setInterval(20);timer.timeout.connect(beat);timer.start()
        def native_point(point):return point-window.timeline.gpu.offset.toPoint()
        def ensure_track(track):
            t=window.timeline;t._range();r=t.track_rect(track);section=t.section_rect(track)
            delta=section.center().y()-r.center().y();name=t._section_name(track);bar=getattr(t,name+'_scroll')
            bar.setValue(round(bar.value()+(-delta if name=='audio' else delta)));wait(20)
        def click_item(identifier):
            item=window.project.item_by_id(identifier);ensure_track(item.track);pos=window.timeline.visible_item_rect(item).center().toPoint();surface=window.timeline.gpu
            check('selected clip is visible',not window.timeline.visible_item_rect(item).isEmpty() and window.timeline.viewport().rect().contains(pos))
            pos=native_point(pos);event(surface.view,QEvent.MouseButtonPress,pos,Qt.LeftButton,Qt.LeftButton);event(surface.view,QEvent.MouseButtonRelease,pos,Qt.LeftButton,Qt.NoButton)
            check('native selection '+identifier+' inspector='+window.inspector.item_id+' selected='+str(window.timeline.selected_ids)+' point='+str(pos)+' offset='+str(surface.offset)+' tool='+str(window.timeline.tool),window.inspector.item_id==identifier)
        def undo():window.shortcut_actions['undo'].trigger()
        def caption(duplicate=False):
            t=window.timeline;ensure_track('subtitle_1');c=window.project.captions[2];old=c.start;before={x.id for x in window.project.captions};point=t.caption_rect(c).center().toPoint();local=native_point(point)
            drag(t.gpu.view,local,local+QPoint(24 if duplicate else 15,0),Qt.AltModifier if duplicate else Qt.NoModifier)
            if duplicate:check('Alt caption duplicate creates new item',bool({x.id for x in window.project.captions}-before))
            else:check('caption mouse drag moves item',abs(next(x for x in window.project.captions if x.id==c.id).start-old)>.02)
            undo()
        def move_clip():
            click_item('title');item=window.project.item_by_id('title');before=item.start;pos=native_point(window.timeline.visible_item_rect(item).center().toPoint())
            drag(window.timeline.gpu.view,pos,pos+QPoint(17,0));check('title drag moves item',abs(window.project.item_by_id('title').start-before)>.02);undo()
        def blade():
            t=window.timeline;ensure_track('video_2');window.shortcut_actions['blade_mode'].trigger();before=len(window.project.timeline);point=QPoint(round(t.x_for_time(2.2)),round(t.track_rect('video_2').center().y()));point=native_point(point)
            event(t.gpu.view,QEvent.MouseButtonPress,point,Qt.LeftButton,Qt.LeftButton);event(t.gpu.view,QEvent.MouseButtonRelease,point,Qt.LeftButton,Qt.NoButton)
            check('blade splits linked clips',len(window.project.timeline)>before);window.shortcut_actions['selection_mode'].trigger();undo()
        def property_drag(audio=False):
            click_item('v2-0');i=window.inspector
            if audio:i.tabs.setCurrentIndex(1);spin=i.volume.spin;old=window.project.item_by_id('a0').gain_db
            else:i.tabs.setCurrentIndex(0);spin=i.zoom_x.spin;old=window.project.item_by_id('v2-0').transform.scale
            wait(20);line=spin.lineEdit();drag(line,QPoint(8,line.height()//2),QPoint(18,line.height()//2))
            new=window.project.item_by_id('a0').gain_db if audio else window.project.item_by_id('v2-0').transform.scale
            check('audio numeric drag changes linked audio' if audio else 'video numeric drag changes zoom',new!=old);undo()
        def crop():
            click_item('v2-0');old=copy.deepcopy(window.project.item_by_id('v2-0').crop);window.shortcut_actions['crop_selected'].trigger();wait(35)
            dialog=next(d for d in window._crop_dialogs if d.isVisible());r=dialog.canvas.image_rect();start=QPoint(round(r.left()+r.width()*.15),round(r.top()+r.height()*.15));end=QPoint(round(r.left()+r.width()*.78),round(r.top()+r.height()*.72))
            drag(dialog.canvas,start,end,Qt.ShiftModifier)
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click();wait(20)
            check('crop dialog applies drawn crop',window.project.item_by_id('v2-0').crop!=old);undo()
        def pan():
            t=window.timeline;before=t.horizontalScrollBar().value();point=native_point(QPoint(550,100));drag(t.gpu.view,point,point-QPoint(30,0),button=Qt.MiddleButton);check('timeline pan changes scroll',t.horizontalScrollBar().value()!=before);t.horizontalScrollBar().setValue(0)
        def scrub():
            t=window.timeline;pos=native_point(QPoint(round(t.x_for_time(1.5)),12));drag(t.gpu.view,pos,pos+QPoint(70,0));check('scrub positions clock',window.project.playhead>1.5)
        def library():
            window.left_panels.buttons['Media'].click();window.media_panel.view_button.click();window.left_panels.buttons['Effects'].click();window.effects_panel.categories.setCurrentItem(window.effects_panel.categories.findItems('Visual FX',Qt.MatchExactly)[0])
        actions=[('play',window.play_button.click),('scrub',scrub),('select video',lambda:click_item('v2-0')),('move title',move_clip),('move caption',lambda:caption(False)),('duplicate caption',lambda:caption(True)),('blade/select',blade),('zoom property',lambda:property_drag(False)),('crop',crop),('audio property',lambda:property_drag(True)),('zoom timeline',lambda:window.timeline.set_zoom(125 if window.timeline.pixels_per_second<110 else 95)),('pan timeline',pan),('library views',library),('autosave',window.autosave),('play or pause',window.play_button.click)]
        for label,spacing in (('normal',420),('fast',160),('short bursts',75)):
            started=time.monotonic();first=len(report['actions'])
            for repetition in range(rounds):
                for name,call in actions:
                    at=time.monotonic();call();report['actions'].append(dict(speed=label,round=repetition,action=name,seconds=time.monotonic()-at));report['resources'].append(dict(rss=process.memory_info().rss,workers=len(window._workers),decoders=len(window.transport.decoders),frame_jobs=len(window.transport._frame_jobs)));wait(spacing)
            report['speeds'].append(dict(name=label,spacing_ms=spacing,actions=len(report['actions'])-first,seconds=time.monotonic()-started))
            window.transport.pause();window.timeline.horizontalScrollBar().setValue(0)
        window.transport.pause()
        # Measure ordinary editing separately from deliberate application-wide
        # stylesheet replacement; retain the latter's blocking duration explicitly.
        report['max_heartbeat_gap_ms']=max(gaps)*1000;report['heartbeat_count']=len(gaps);report['watchdog_reports']=guard.reports
        check('editing has no watchdog stall',guard.reports==0)
        timer.stop();guard.close();guard=None
        report['theme_crops']=[];report['theme_restyle_seconds']=[]
        from .auto_layout import ask as ask_layout,AutoLayoutDialog
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            at=time.monotonic();window.apply_theme(theme,save=False);report['theme_restyle_seconds'].append(dict(theme=theme,seconds=time.monotonic()-at));crop()
            result_errors=[]
            def choose_layout():
                dialog=app.activeModalWidget()
                if not isinstance(dialog,AutoLayoutDialog):result_errors.append('Auto-layout not visible');return
                try:
                    r=dialog.canvas.image_rect();start=QPoint(round(r.left()+r.width()*.12),round(r.top()+r.height()*.15));end=QPoint(round(r.left()+r.width()*.72),round(r.top()+r.height()*.75))
                    drag(dialog.canvas,start,end,Qt.ShiftModifier)
                    dialog.grab().save(str(out/f'auto-layout-{theme}.png'))
                    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
                except Exception:
                    result_errors.append(traceback.format_exc());dialog.reject()
            fuse=QTimer(window);fuse.setSingleShot(True);fuse.timeout.connect(lambda:app.activeModalWidget().reject() if isinstance(app.activeModalWidget(),AutoLayoutDialog) else None);fuse.start(8000)
            QTimer.singleShot(100,choose_layout)
            result=ask_layout(window,[window.project.media_by_id('vsrc')]);fuse.stop();fuse.deleteLater();check(theme+' auto-layout responds without GUI decode',bool(result) and not result_errors)
            for actual,expected in zip(result['crop'],(.12,.15,.6,.6)):check(theme+' auto-layout keeps drawn crop',abs(actual-expected)<.025)
            wait(40);report['theme_crops'].append(theme)
        timer.stop();window.transport.pause()
        report['timeline']=window.timeline.gpu.diagnostics();report['preview']=window.preview.gpu.diagnostics()
        check('no indefinite editing-loop stall',report['watchdog_reports']==0);check('Qt callbacks raise no exceptions',not report['exceptions'])
        check('GPU timeline continues drawing',report['timeline']['scene_graph_frames']>20)
        check('preview renderer did not fail',not report['preview'].get('renderer_error'))
        check('preview renderer did not restart',report['preview'].get('renderer_restarts',0)==0)
        check('video frames are decoded and presented',report['preview'].get('gpu_source_frames',0)+report['preview'].get('cpu_source_frames',0)>0)
        window.autosave();window.close();deadline=time.monotonic()+20
        while window.isVisible() and time.monotonic()<deadline:wait(30)
        check('normal close drains writes and workers',not window.isVisible() and not window._workers)
        from .config import AUTOSAVE_PATH,SETTINGS_PATH
        check('recovery file contains latest edit',Project.load(AUTOSAVE_PATH).name==window.project.name)
        check('preferences remain valid JSON',isinstance(json.loads(SETTINGS_PATH.read_text()),dict))
        check('test source media unchanged',all(digest(Path(p))==value for p,value in protected.items()))
        report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        if timer:timer.stop()
        if window is not None:
            window.close();deadline=time.monotonic()+20
            while window.isVisible() and time.monotonic()<deadline:wait(25)
        if guard:guard.close()
        report['workers_finished']=QThreadPool.globalInstance().waitForDone(10000);wait(100)
        report['actions_logged']=len(read(journal.path));journal.close();sys.excepthook=old_hook
        report['passed']=report['passed'] and report['workers_finished']
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:report[k] for k in ('passed','speeds','exceptions','error','max_heartbeat_gap_ms','watchdog_reports') if k in report}),flush=True)
    return 0 if report['passed'] else 1
