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
