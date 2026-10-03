"""Opt-in, isolated package verification; never runs during normal startup."""
def workflow_selftest(output):
    import os,json,sys,traceback,subprocess,hashlib
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ["KINETIC_CUT_HOME"]=str(output/"home")
    os.environ["QT_QPA_PLATFORM"]="offscreen"
    report={"frozen":bool(getattr(sys,"frozen",False))}
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFontDatabase
        from .startup import StartupSplash
        from .theme import STYLESHEET
        from .ui import MainWindow
        from .emoji import EmojiPicker,catalogue,image
        from .model import Project,TimelineItem,Caption,MediaItem,Transform
        from . import binclips
        from .headline import headline_style
        from .exporter import write_ass,_escape_ass_path
        app=QApplication([]); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
        for font in ("arial.ttf","arialbd.ttf","segoeui.ttf","segoeuib.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"/font))
        splash=StartupSplash(); splash.show(); splash.report(15,"Checking packaged workspace")
        window=MainWindow(startup_progress=splash.report); window.resize(1680,1000); window.show()
        window.add_title_object("Headline"); item=window.project.item_by_id(window.timeline.selected_id)
        item.title_text="Google emoji 🥹 👩🏽‍💻\n🇬🇧 👨‍👩‍👧‍👦 🦍"; window.model_changed(); app.processEvents()
        assert window.windowTitle()=="Kinetic Cut"
        assert not window.inspector.title_text.emoji_button.icon().isNull()
        window.grab().save(str(output/"workspace.png")); splash.close()
        picker=EmojiPicker(window); picker.show(); app.processEvents()
        rect=picker.grid.visualItemRect(picker.grid.item(0)); assert rect.width()>30
        pixels=picker.grid.viewport().grab(rect).toImage()
        assert any(pixels.pixelColor(x,y).red()-pixels.pixelColor(x,y).blue()>80 for x in range(pixels.width()) for y in range(pixels.height()))
        picker.grab().save(str(output/"picker.png")); picker.close()
        # Exercise the dynamically loaded FontTools tables and HarfBuzz extension.
        for sequence in ("🥹","👩🏽‍💻","🇬🇧","👨‍👩‍👧‍👦","🦍",catalogue()[0][-1][0]):assert not image(sequence).isNull()
        report["emoji_count"]=len(catalogue()[0])
        project=Project(timeline=[TimelineItem("t","","video_1",0,1,role="title",title_text=item.title_text,title_style=headline_style())])
        ass=output/"emoji.ass"; write_ass(project,ass)
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=c=0x202020:s=1080x1920:r=60:d=1","-vf","ass='"+_escape_ass_path(str(ass))+"'","-frames:v","1",str(output/"export.png")],check=True,capture_output=True)
        saved=binclips.asset(binclips.snapshot(project,{"t"},set(),"t")); restored=Project()
        restored_ids,_=binclips.restore(restored,saved,"video_1",3)
        assert restored.item_by_id(next(iter(restored_ids))).title_text==item.title_text
        report["power_bin_attribute_roundtrip"]=True
        highlighted=Project(captions=[Caption("c",0,1,"Word highlight check")]); highlighted.subtitle_style.animation="word highlight"
        highlight_ass=output/"word-highlight.ass"; write_ass(highlighted,highlight_ass)
        assert highlight_ass.read_text(encoding="utf-8").count("Dialogue: 1,")==3
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=c=0x202020:s=1080x1920:r=60:d=1","-vf","ass='"+_escape_ass_path(str(highlight_ass))+"'","-frames:v","1",str(output/"word-highlight.png")],check=True,capture_output=True)
        report["word_highlight_export"]=True
        assert highlighted.subtitle_style.color=="#55ffff" and highlighted.subtitle_style.outline=="#000000"
        assert not window.loop_button.icon().isNull() and not window.timeline._razor_cursor().pixmap().isNull()
        report["caption_defaults_and_new_controls"]=True
        # A moving clock is insufficient: verify that the frozen program renders
        # changing video pixels with an empty lane between two occupied layers.
        from PySide6.QtCore import QEventLoop,QTimer
        def wait(ms):
            loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
        source=output/"decoder-test.mp4"
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=s=320x180:r=60:d=3","-c:v","libx264","-pix_fmt","yuv420p",str(source)],check=True,capture_output=True)
        sample=Project(media=[MediaItem("probe",str(source),"video","Playback probe",3,320,180,60)])
        sample.add_track("video"); sample.add_track("video")
        sample.timeline=[TimelineItem("v1","probe","video_1",0,3),TimelineItem("v3","probe","video_3",0,2.5,.5,transform=Transform(.5,.25,.4))]
        window.set_project(sample); window.seek(.1); wait(200); window.transport.play(); hashes={"v1":set(),"v3":set()}
        for _ in range(6):
            wait(120)
            for id,key in window.preview.active_frames.items():
                if key in window.preview.frames:hashes[id].add(hashlib.sha1(window.preview.frames[key].constBits()).hexdigest())
        assert all(len(values)>=4 for values in hashes.values()),str(hashes)
        report["moving_video_frames_with_empty_middle_layer"]={id:len(values) for id,values in hashes.items()}
        assert not window.inspector.tabs.tabIcon(3).isNull()
        report["power_bin_grid_accepts_drops"]=window.media_panel.grid.viewport().acceptDrops()
        assert report["power_bin_grid_accepts_drops"]
        window.transport.pause(); window.grab().save(str(output/"moving-video.png"))
        from .caption_style_dialog import CaptionStyleDialog
        from .chroma import apply as apply_key
        from .profanity import censor_text
        from .effects import CATALOG
        from PySide6.QtGui import QImage,QColor
        dialog=CaptionStyleDialog(sample.subtitle_style,{},window); dialog.show(); wait(50)
        assert not dialog.form.isRowVisible(dialog.color_buttons["background_color"])
        dialog.animation.setCurrentText("word highlight"); assert dialog.form.isRowVisible(dialog.color_buttons["highlight"])
        dialog.grab().save(str(output/"caption-preview.png")); dialog.reject()
        keyed=QImage(2,1,QImage.Format_RGBA8888); keyed.fill(QColor("#00ff00"))
        assert apply_key(keyed,{"color":"#00ff00"}).pixelColor(0,0).alpha()==0
        assert censor_text("fuck shit")=="f*** sh**"
        assert all(name in CATALOG["Audio"] for name in ("Cut curse words","Remove Silence"))
        assert hasattr(window.timeline,"file_drop_controller")
        report["new_caption_audio_keying_and_explorer_controls"]=True
        from .vocal_component import ready,component_root
        from .icons import resource_path
        from .project_manager import ProjectManagerDialog,remember
        assert 'Vocal Only' in CATALOG['Audio'] and not ready()
        assert Path(resource_path('assets','vocal_worker.py')).is_file()
        assert 'torch' not in sys.modules
        report['vocal_component_is_optional_and_not_loaded']=True
        sample.save(output/'Package Test.kcut'); remember(window,sample.path,True)
        window.settings['project_folder']=str(output); window.settings['recent_projects']=[sample.path]
        manager=ProjectManagerDialog(window); manager.show()
        for _ in range(60):
            if manager.items.count()>1:break
            wait(50)
        assert manager.items.count()>1 and manager.items.item(0).text()=='New Project'
        manager.set_list(False); wait(30); manager.grab().save(str(output/'project-manager.png')); manager.set_list(True); wait(30); manager.grab().save(str(output/'project-manager-list.png')); manager.reject()
        window.delivery.refresh_estimate(); assert window.delivery.hardware.currentText()=='Auto' and not window.delivery.burn.isEnabled()
        window.select_item('v1'); assert hasattr(window.inspector,'background_blur_enabled')
        window.viewer_command('mark_webcam','v3'); assert window.project.item_by_id('v3').is_webcam
        window.grab().save(str(output/'track-headers-and-blur.png'))
        window.inspector.video_stack.widget(0).ensureWidgetVisible(window.inspector.background_blur_strength)
        wait(50); window.grab().save(str(output/'background-blur.png'))
        report['project_manager_and_editor_followup_controls']=True
        from .project_settings import ProjectSettingsDialog
        from PySide6.QtWidgets import QCheckBox,QDialogButtonBox
        dialog=ProjectSettingsDialog(Project(),window,new_project=True); dialog.setWindowTitle('New Project — Settings')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).setText('Create Project'); dialog.show(); wait(50)
        assert not dialog.findChildren(QCheckBox)
        _,settings=dialog.values(); assert not any((settings.normalize_audio,settings.noise_reduction,settings.auto_duck))
        dialog.grab().save(str(output/'new-project-simple.png')); dialog.reject(); report['new_project_has_no_audio_processing_controls']=True
        from .vision_component import ready as vision_ready
        from .vision_effects import fingerprint,prepare_export
        from .exporter import export,PRESETS
        assert not vision_ready() and 'mediapipe' not in sys.modules
        assert Path(resource_path('assets','vision_worker.py')).is_file()
        assert all(name in CATALOG['Face Filters'] for name in ('Big Eyes','Big Nose','Big Lips','Face Twist'))
        assert not {'Party Hat','Face Mask'} & set(CATALOG['Face Filters'])
        report['vision_component_is_optional_and_not_loaded']=True
        # Exercise bundled PyAV/FFV1 and the exact transparent export path without
        # downloading an optional model as a side effect of this package test.
        probe=Project(media=[sample.media[0]],timeline=[TimelineItem('fx','probe','video_1',0,1)])
        probe.settings.width=320; probe.settings.height=180; probe.settings.fps=2
        analysis=output/'vision-fixture'; (analysis/'masks').mkdir(parents=True,exist_ok=True)
        (analysis/'faces.json').write_text('[null,null]')
        mask=QImage(64,64,QImage.Format_RGBA8888); mask.fill(QColor('white'))
        for x in range(16):
            for y in range(64):mask.setPixelColor(x,y,QColor('black'))
        for n in range(2):mask.save(str(analysis/'masks'/f'{n:08d}.png'))
        info=dict(root=str(analysis),source=fingerprint(probe.media[0]),crop=vars(probe.timeline[0].crop),source_start=0,source_end=1,fps=2,frames=2,person_frames=2,face_frames=0)
        probe.timeline[0].effects=[dict(name='Remove Person Background',analysis=info)]
        prepared=prepare_export(probe,'ffmpeg',None,None)
        import av
        with av.open(prepared['fx']) as movie:
            frame=next(movie.decode(video=0)).to_ndarray(format='rgba')
            assert frame[80,0,3]==0 and frame[80,200,3]==255
        export(probe,str(output/'vision-export.mp4'),next(iter(PRESETS.values())),False,'CPU')
        report['vision_lossless_alpha_and_frozen_export']=True
        from .timeline import TimelineWidget
        from PySide6.QtCore import QPointF
        timeline=TimelineWidget(); timeline.resize(1000,420); timeline.show()
        layers=Project(captions=[Caption('sub',1,3,'Continuous selection')]); layers.playhead=9
        for _ in range(9):layers.add_track('video')
        for _ in range(5):layers.add_track('audio')
        layers.timeline=[TimelineItem(track,'',track,1,2,link_id='') for track in layers.video_tracks+layers.audio_tracks]
        timeline.set_project(layers); timeline.linked_selection=False; timeline.subtitle_extent=30; timeline._range(); wait(30)
        sections=timeline._sections(); controller=timeline.marquee_controller
        for direction in ('down','up'):
            timeline.video_scroll.setValue(timeline.video_scroll.maximum() if direction=='down' else 0)
            timeline.subtitle_scroll.setValue(0 if direction=='down' else timeline.subtitle_scroll.maximum())
            timeline.audio_scroll.setValue(0 if direction=='down' else timeline.audio_scroll.maximum())
            start_y=sections['subtitle'].top()+3 if direction=='down' else sections['audio'].bottom()-3
            end_y=sections['audio'].bottom()-2 if direction=='down' else sections['subtitle'].top()+2
            timeline.drag_mode='marquee'; timeline.marquee_initial=set(); timeline.marquee_caption_initial=set()
            controller.begin(QPointF(timeline.x_for_time(4),start_y)); controller.move(QPointF(timeline.x_for_time(.5),end_y))
            for _ in range(200):controller.scroll()
            assert timeline.selected_ids=={i.id for i in layers.timeline} and timeline.selected_caption_ids=={'sub'}
            assert len(controller.rects())==1
            timeline.viewport().grab().save(str(output/('continuous-selection-'+direction+'.png'))); timeline.cancel_drag()
        timeline.close(); report['continuous_selection_scrolls_through_all_sections_both_directions']=True
        from .workspace import set_page
        from .model import CaptionStyle
        import time
        title=TimelineItem('fade','','video_1',0,2,role='title',title_text='Fading headline 🥹',title_style=headline_style(),fade_in=.5,fade_out=.5)
        title.title_style.size=42
        delivery_project=Project(timeline=[title]); delivery_project.settings.width=320; delivery_project.settings.height=180; delivery_project.settings.fps=20
        window.set_project(delivery_project); set_page(window,1); window.resize(1100,700); wait(50)
        d=window.delivery; assert d.location.isEditable() and not window.workspace_split.handle(1).isEnabled()
        assert window.left_stack.width()==360 and d.settings_scroll.widget().width()<=d.settings_scroll.viewport().width()
        d.location.setText(str(output)); d.hardware.setCurrentText('CPU'); prefix='title-fade-'+str(time.time_ns())
        for n in range(2):d.name.setText(prefix+'-'+str(n)); d.add_job()
        window.grab().save(str(output/'deliver-small.png')); d.render_all(); deadline=time.monotonic()+60
        while d.running and time.monotonic()<deadline:wait(100)
        assert len(d.jobs)==2 and all(job['state']=='Complete' and job['elapsed']>0 and 'started_at' not in job for job in d.jobs)
        assert d.location.count()==1 and not d.clock.isActive()
        from .widgets import extract_frame
        import numpy as np
        sums=[]
        for moment in (.1,1,1.9):
            image=extract_frame(d.jobs[0]['output'],moment).convertToFormat(QImage.Format_RGBA8888)
            sums.append(int(np.frombuffer(image.constBits(),dtype=np.uint8).reshape(image.height(),image.width(),4)[:,:,:3].sum()))
        assert sums[0]<sums[1]*.6 and sums[2]<sums[1]*.6
        d.name.setText(prefix+'-queued'); d.add_job(); card=d.list.itemWidget(d.list.item(2)); assert not card.remove_button.isHidden()
        window.resize(1480,1000); wait(50); window.grab().save(str(output/'deliver-queue.png')); card.remove_button.click(); assert len(d.jobs)==2
        report['title_fades_and_deliver_queue_verified']=dict(fade_luma=sums,elapsed_seconds=[j['elapsed'] for j in d.jobs],recent_folders=d.location.count())
        if os.name=="nt":
            command='Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices; public class ConsoleProbe { [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow(); }\'; [ConsoleProbe]::GetConsoleWindow().ToInt64()'
            result=subprocess.run(["powershell","-NoProfile","-NonInteractive","-Command",command],capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NEW_CONSOLE)
            report["child_console_handle"]=int(result.stdout.strip()); assert report["child_console_handle"]==0
        report.update(title=window.windowTitle(),fps=project.settings.fps,resolution=[project.settings.width,project.settings.height],passed=True)
        app.setQuitOnLastWindowClosed(False); app.clipboard().clear(); window.close(); wait(100); app.processEvents()
    except Exception:
        report.update(passed=False,error=traceback.format_exc())
    (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return 0 if report["passed"] else 1
