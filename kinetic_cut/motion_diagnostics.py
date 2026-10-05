"""Native three-theme and decoded export checks for the composition workflow."""
def run(output):
    import os,sys,json,time,traceback,copy
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    import numpy as np,av
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt,QEventLoop,QTimer,QThreadPool
    from PySide6.QtGui import QImage,QPainter,QColor
    from .ui import MainWindow
    from .model import Project,TimelineItem,MediaItem,Transform
    from .motion import validate,draw
    from .native_animation import frame
    from .motion_editor import MotionEditor
    from .keyframe_editor import KeyframeEditor
    from .keyframes import put
    from .exporter import export,PRESETS
    from .caption_fonts import load_fonts
    app=QApplication([]); app.setStyle('Fusion'); app.setQuitOnLastWindowClosed(False); load_fonts()
    w=MainWindow(); w.resize(1480,920); w.show(); w.autosave_timer.stop(); report={'frozen':bool(getattr(sys,'frozen',False)), 'themes':[], 'parity':[]}
    def settle(ms=70):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def array(image):
        image=image.convertToFormat(QImage.Format_RGBA8888)
        return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()
    try:
        scene=validate(dict(canvas=[320,568],nodes=[
            dict(id='group',kind='group',x=160,y=220,keyframes={'rotation':[dict(time=0,value=-25,interpolation='Back Out'),dict(time=.7,value=0)]}),
            dict(id='shape',kind='ellipse',parent='group',width=140,height=140,fill='none',stroke='#e8ff69',stroke_width=12,keyframes={'trim':[dict(time=0,value=0),dict(time=.6,value=1)]}),
            dict(id='text',kind='text',text='MAKE TIME',font='Poppins',font_size=39,x=160,y=365,fill='#ff688f',text_mode='word',stagger=.16,entry_duration=.3,entry_y=45,mask=dict(kind='rectangle',width=310,height=100)),
            dict(id='path',kind='path',parent='group',fill='#58e4dc',path=[['M',0,-35],['L',30,25],['L',-30,25],['Z']],path_to=[['M',35,0],['L',-25,30],['L',-25,-30],['Z']],keyframes={'morph':[dict(time=.7,value=0,interpolation='Bezier',bezier=[.2,0,.3,1]),dict(time=1.2,value=1)]})],motion_blur=dict(samples=4,shutter=180)))
        item=TimelineItem('scene','','video_1',0,2,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':scene},transform=Transform(.5,.5))
        p=Project(name='Native motion check',timeline=[item]); p.settings.width=320; p.settings.height=568; p.settings.fps=30; w.set_project(p); w.select_item(item.id)
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False); d=MotionEditor(w,item); d.show(); d.time.setValue(.7); settle()
            d.node_id='path'; d.channel.setCurrentText('morph'); d.seek(.7); d.refresh()
            for size in ((1180,820),(950,720)):
                d.resize(*size); settle(); path=output/f'motion-{theme}-{size[0]}.png'; assert d.grab().save(str(path)); report['themes'].append(path.name)
            d.reject(); settle()
            keys=KeyframeEditor(w,item); keys.show(); settle(); keys.add_key('rotation'); keys.change_mode('Bezier'); keys.seek(.8); keys.add_key('rotation'); keys.edit_value('rotation',15); keys.seek(0); settle()
            assert keys.grab().save(str(output/f'curves-{theme}.png')); keys.reject(); settle()
        w.apply_theme('default',save=False); w.preview.set_transform_controls_visible(False)
        target=output/'motion.mp4'; export(p,str(target),PRESETS['TikTok · Fast'],False,'CPU',export_audio=False)
        with av.open(str(target)) as movie:frames=list(movie.decode(video=0))
        assert len(frames)==60 and frames[0].width==320 and frames[0].height==568
        for n in (6,15,30,45):
            at=n/30; w.seek(at); settle(); rect=w.preview.composition_rect().toRect(); shot=w.preview.grab().toImage().copy(rect).scaled(320,568,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
            source=array(shot)[:,:,:3]; decoded=frames[n].to_ndarray(format='rgb24')
            sy,sx=np.where(source.max(axis=2)>90); ey,ex=np.where(decoded.max(axis=2)>90)
            error=abs(float(sx.mean()-ex.mean()))+abs(float(sy.mean()-ey.mean())); ratio=len(sx)/len(ex)
            report['parity'].append(dict(time=at,center_error_pixels=error,area_ratio=ratio)); assert error<4 and .85<ratio<1.15,report['parity']
            shot.save(str(output/f'preview-{n}.png')); QImage(decoded.data,320,568,320*3,QImage.Format_RGB888).copy().save(str(output/f'export-{n}.png'))
        # A higher media track must occlude the native scene in both routes.
        image=QImage(320,568,QImage.Format_RGB32); image.fill(QColor('#3255dd')); source=output/'above.png'; image.save(str(source)); above=p.add_track('video')
        p.media.append(MediaItem('above',str(source),'image','Above',2,320,568)); p.timeline.append(TimelineItem('above','above',above,0,2,transform=Transform(.5,.5))); w.set_project(p); w.seek(.8); w.preview.set_transform_controls_visible(False); settle()
        grab=w.preview.grab(); grab.save(str(output/'order-preview.png')); center=w.preview.composition_rect().center().toPoint(); color=grab.toImage().pixelColor(center); report['order_preview']={'color':color.name(),'tracks':p.video_tracks,'rect':str(w.preview.composition_rect()),'center':str(center),'dpr':grab.devicePixelRatio(),'source_color':w.preview.still_cache.load(str(source)).pixelColor(0,0).name(),'same_project':p is w.preview.project}; assert color.blue()>180 and color.red()<80,report['order_preview']
        export(p,str(output/'ordering.mp4'),PRESETS['TikTok · Fast'],False,'CPU',export_audio=False)
        with av.open(str(output/'ordering.mp4')) as movie:color=next(movie.decode(video=0)).to_ndarray(format='rgb24')[284,160]
        assert color[2]>180 and color[0]<80; report['track_order']=True
        # The packaged FFmpeg path must also handle all six rich media curves.
        moving=TimelineItem('curves','above','video_1',0,2,transform=Transform(.3,.4,.25))
        for name,a,b in [('x',.3,.7),('y',.4,.6),('scale',.25,.45),('scale_y',.25,.45),('rotation',0,25),('opacity',100,85)]:put(moving,name,0,a,'Bezier'); put(moving,name,2,b)
        curved=Project(media=[p.media[-1]],timeline=[moving]); curved.settings=copy.deepcopy(p.settings)
        export(curved,str(output/'media-curves.mp4'),PRESETS['TikTok · Fast'],False,'CPU',export_audio=False)
        with av.open(str(output/'media-curves.mp4')) as movie:curve_frames=list(movie.decode(video=0))
        assert len(curve_frames)==60
        centers=[]
        for n in (0,30):
            rgb=curve_frames[n].to_ndarray(format='rgb24'); _,x=np.where(rgb[:,:,2]>150); centers.append(float(x.mean()))
        assert centers[1]>centers[0]+50; report['simultaneous_media_curves']=True
        # New UI-design controls: native typing/counter/shadow UI in all themes,
        # and actual high-rate encoded output rather than an fps label alone.
        design=validate(dict(canvas=[320,320],nodes=[dict(id='panel',kind='rectangle',x=160,y=160,width=270,height=140,radius=28,fill='#f5f6f3',shadow=dict(enabled=True,blur=15,opacity=25,y=10)),dict(id='typing',kind='text',text='find a moment',x=48,y=130,font_size=24,bold=False,fill='#101315',text_mode='typewriter',text_align='left',caret=True,stagger=.05),dict(id='counter',kind='text',x=48,y=190,font_size=23,fill='#12866c',text_mode='counter',text_align='left',number_suffix=' views',keyframes={'number':[dict(time=0,value=0),dict(time=.8,value=12480)]})]))
        ui_item=TimelineItem('ui-design','','video_1',0,1,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':design},transform=Transform(.5,.5))
        ui_project=Project(timeline=[ui_item]); ui_project.settings.width=ui_project.settings.height=320; ui_project.settings.fps=120; w.set_project(ui_project)
        from .project_settings import ProjectSettingsDialog
        report['ui_design_themes']=[]
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False); d=MotionEditor(w,ui_item); d.show(); d.node_id='typing'; d.time.setValue(.4); d.refresh(); d.resize(950,720); settle()
            assert d.caret.isVisible() and d.text_align.currentText()=='left'; image=output/f'typing-{theme}.png'; assert d.grab().save(str(image)); report['ui_design_themes'].append(image.name)
            d.node_id='panel'; d.refresh(); settle(); assert d.shadow.isChecked(); assert d.grab().save(str(output/f'shadow-{theme}.png')); d.reject(); settle()
            settings=ProjectSettingsDialog(ui_project,w); settings.show(); settle(); assert settings.fps.findText('120')>=0; assert settings.grab().save(str(output/f'fps-{theme}.png')); settings.reject(); settle()
        target=output/'ui-120.mp4'; export(ui_project,str(target),PRESETS['TikTok · Fast'],False,'CPU',export_audio=False)
        with av.open(str(target)) as movie:
            assert str(movie.streams.video[0].average_rate)=='120'; high_rate=list(movie.decode(video=0))
        assert len(high_rate)==120
        errors=[]
        for n in (0,24,72,108):
            expected=array(frame(ui_project,ui_item,n/120)).astype(float); rgb=expected[:,:,:3]*expected[:,:,3:]/255
            error=float(np.abs(high_rate[n].to_ndarray(format='rgb24')-rgb).mean()); assert error<4; errors.append(error)
        report['ui_120fps_frames']=len(high_rate); report['ui_design_rgb_errors']=errors
        # Measure software drawing separately, without build/test concurrency.
        started=time.perf_counter()
        for n in range(30):draw(scene,.4+n/60,(360,640),30)
        report['preview_draw_ms']=round((time.perf_counter()-started)*1000/30,2)
        started=time.perf_counter(); draw(scene,.75,(1080,1920),30); report['full_frame_draw_ms']=round((time.perf_counter()-started)*1000,2)
        before=p.to_dict(); p.save(output/'editable.kcut'); loaded=Project.load(output/'editable.kcut'); assert loaded.timeline[0].graphic_data==p.timeline[0].graphic_data; report['roundtrip']=True
        assert 'motion_composition' in w.assistant_connection.api.call_get_capabilities(); report['mcp_schema']=True
        report['passed']=True
    except Exception:report['passed']=False; report['error']=traceback.format_exc()
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(10000); app.processEvents(); (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
