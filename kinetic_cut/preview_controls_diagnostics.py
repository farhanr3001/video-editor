"""Opt-in native selected-media overlay and prepared-texture regression checks."""
def run(out,app,report,check):
    import os,sys,time,traceback
    import numpy as np
    from PySide6.QtCore import Qt,QEvent,QEventLoop,QTimer,QPointF
    from PySide6.QtGui import QImage,QColor,QPainter,QMouseEvent
    from PySide6.QtTest import QTest
    from .model import Project,ProjectSettings,MediaItem,TimelineItem,Transform,Caption,Crop
    from .graphics import default_graphic_data
    from .icons import resource_path
    from .process import run as execute
    from .ui import MainWindow
    app.setProperty('kineticTestDiscardUnsaved',True)
    report.update(frozen=bool(getattr(sys,'frozen',False)),cases=[],scope='Native timeline selection, preview controls and prepared pixels')
    errors=[];previous=sys.excepthook
    sys.excepthook=lambda kind,value,tb:errors.append(''.join(traceback.format_exception(kind,value,tb)))
    def wait(ms):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def until(condition,timeout=10):
        deadline=time.monotonic()+timeout
        while not condition() and time.monotonic()<deadline:wait(25)
        assert condition(),'Preview did not become ready'
    def pixels(image):
        assert not image.isNull(),'Preview capture is empty'
        image=image.convertToFormat(QImage.Format_RGBA8888)
        return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.width(),4).copy()
    still=QImage(640,360,QImage.Format_RGBA8888);still.fill(QColor('#215a8e'))
    painter=QPainter(still);painter.fillRect(80,60,140,200,QColor('#cd7836'));painter.fillRect(390,130,160,90,QColor('#567f48'));painter.end()
    still_path=out/'source.png';still.save(str(still_path))
    video=out/'source.mp4'
    execute(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=30','-t','4',
        '-c:v','libx264','-pix_fmt','yuv420p',str(video)],capture_output=True,check=True)
    media=[MediaItem('video',str(video),'video','Video',4,640,360,30,video_codec='h264'),
           MediaItem('image',str(still_path),'image','Image',4,640,360)]
    items=[TimelineItem('video','video','video_1',0,4,transform=Transform(x=.5,y=.5,scale=.62)),
           TimelineItem('image','image','video_1',4,4,transform=Transform(x=.5,y=.5,scale=.62),
               crop=Crop(.08,.1,.8,.8),effects=[dict(name='Gaussian Blur',horizontal=12,vertical=12)]),
           TimelineItem('title','','video_1',8,4,role='title',title_text='Transform this title'),
           TimelineItem('graphic','','video_1',12,4,role='graphic',graphic_type='Circle',
               graphic_data=default_graphic_data('Circle'),transform=Transform(x=.5,y=.5,scale=.7)),
           TimelineItem('caption-base','image','video_1',16,4,transform=Transform(x=.5,y=.5,scale=.8))]
    project=Project(settings=ProjectSettings(width=960,height=540,fps=30),media=media,timeline=items,
        captions=[Caption('caption',16,20,'A prepared caption')])
    project.subtitle_style.animation='none'
    w=MainWindow();w.autosave_timer.stop();w.preview_quality.request=lambda:None;w.request_waveform=lambda _:None
    w.set_project(project);w.show();p=w.preview;t=w.timeline;gpu=p.gpu
    def capture():
        p.update();wait(140);shot=gpu.view.grabWindow();assert not shot.isNull();return shot
    def mouse_move(point):
        app.sendEvent(gpu.view,QMouseEvent(QEvent.MouseMove,point,QPointF(gpu.view.mapToGlobal(point.toPoint())),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
    try:
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False)
            for size in ((1480,920),(1100,760)):
                w.resize(*size);wait(150);t.set_zoom(32);t.horizontalScrollBar().setValue(0)
                for n,identifier in enumerate(('video','image','title','graphic','caption')):
                    at=n*4+.8;w.seek(at);t.select_ids(set());t.select_captions(set());wait(200)
                    if identifier=='caption':
                        target=project.captions[0];point=t.caption_rect(target).center().toPoint()
                    else:target=project.item_by_id(identifier);point=t.visible_item_rect(target).center().toPoint()
                    QTest.mouseClick(t.gpu.view,Qt.LeftButton,pos=point)
                    until(lambda:p.selected_caption_id=='caption' if identifier=='caption' else p.selected_item_id==identifier)
                    if identifier in ('title','graphic','caption'):
                        until(lambda:bool(p.text_rects))
                    else:until(lambda:bool(gpu.targets))
                    p.set_transform_controls_visible(False);plain=capture()
                    p.set_transform_controls_visible(True);selected=capture()
                    a=pixels(plain).astype(int);b=pixels(selected).astype(int)
                    delta=np.max(np.abs(a[:,:,:3]-b[:,:,:3]),axis=2)>30
                    colour=((b[:,:,2]>190)&(b[:,:,0]<140)&(b[:,:,1]>70))|((b[:,:,1]>160)&(b[:,:,0]<140)&(b[:,:,2]<170))
                    count=int((delta&colour).sum())
                    check(f'{theme} {size[0]} selected {identifier} has visible control pixels',count>35)
                    check(f'{theme} {size[0]} {identifier} renderer stays healthy',gpu.diagnostics().get('renderer_restarts',0)==0 and not errors)
                    selected.save(str(out/f'{theme}-{size[0]}-{identifier}.png'))
                    report['cases'].append(dict(theme=theme,size=size,item=identifier,control_pixels=count))
        w.resize(1480,920);w.seek(.8);t.select_ids({'video'},'video');wait(250)
        item=project.item_by_id('video')
        def geometry():
            target=next(rect for current,_,rect in gpu.targets if current.id=='video')
            return p._transform_geometry(item,target)
        anchor,corners,*_=geometry();point=corners[2];old=item.transform.scale
        QTest.mousePress(gpu.view,Qt.LeftButton,pos=point.toPoint());check('native corner starts resize',p.drag_mode=='scale')
        destination=anchor+(point-anchor)*1.12;mouse_move(destination);QTest.mouseRelease(gpu.view,Qt.LeftButton,pos=destination.toPoint());wait(180)
        check('native corner updates media scale',item.transform.scale>old*1.05)
        anchor,_,_,handle,_=geometry();QTest.mousePress(gpu.view,Qt.LeftButton,pos=handle.toPoint())
        check('native rotation handle starts rotation',p.drag_mode=='rotate')
        destination=anchor+QPointF(55,0);mouse_move(destination);QTest.mouseRelease(gpu.view,Qt.LeftButton,pos=destination.toPoint());wait(180)
        check('native rotation updates media angle',abs(item.transform.rotation)>45)
        w.transport.play();wait(200);check('play hides editing controls',not p.transform_controls_visible)
        w.transport.pause();wait(200);check('pause restores editing controls',p.transform_controls_visible)
        # Compare overlay stability over a stationary source. A video sink may
        # admit its final paused frame between captures; that is not a change
        # in transform controls and must not contaminate this exact pixel check.
        w.seek(4.8);t.select_ids({'image'},'image');wait(200)
        before=pixels(capture());w.transport.sync(True);wait(100);after=pixels(capture())
        check('paused control overlay remains stable',np.array_equal(before,after))
        check('no Qt callback exceptions',not errors)
        report['passed']=True
    except Exception as error:
        report.update(passed=False,error=repr(error),traceback=traceback.format_exc())
    finally:
        report['callback_errors']=errors;sys.excepthook=previous
        w.close();until(lambda:not w.isVisible() and not getattr(gpu,'peer',None).active if getattr(gpu,'peer',None) else not w.isVisible())
        report['graceful_renderer_close']=not gpu.peer.forced_shutdown if getattr(gpu,'peer',None) else True
        report['passed']=report.get('passed',False) and report['graceful_renderer_close']
        import json
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
