"""Opt-in native Headline typography, transform and decoded export checks."""
def run(output):
    import os,sys,json,copy,traceback
    from pathlib import Path
    out=Path(output).resolve(); out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home'); os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    import av,numpy as np
    from PySide6.QtCore import Qt,QPointF,QEvent,QEventLoop,QTimer
    from PySide6.QtGui import QMouseEvent,QImage
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from .ui import MainWindow
    from .model import Project
    from .headline import geometry,paths
    from .native_animation import frame
    from .exporter import export,ExportPreset
    app=QApplication([]); app.setQuitOnLastWindowClosed(False); app.setProperty('kineticTestDiscardUnsaved',True)
    w=MainWindow(); w.autosave_timer.stop(); w.resize(1480,920); w.show()
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),themes=[],exports=[])
    def settle(ms=70):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def move(widget,point):
        QApplication.sendEvent(widget,QMouseEvent(QEvent.MouseMove,QPointF(point),QPointF(widget.mapToGlobal(point.toPoint())),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
    try:
        w.set_project(Project()); w.add_title_object('Headline'); item=w.project.item_by_id(w.timeline.selected_id)
        item.title_text='xQc enjoys Jaxx Padel at Swansea (South Wales)'; item.duration=1; w.project.settings.fps=10
        w.model_changed(); w.seek(.2); settle(); panel=w.inspector; sizes=[]
        # Keep one real numeric scrub gesture open: every intermediate font value
        # must produce fresh geometry before scrub release/one history commit.
        spin=panel.headline_size.spin; line=spin.lineEdit()
        QTest.mousePress(line,Qt.LeftButton,pos=line.rect().center()); assert spin._drag_start is not None
        for value in (24,48,72,120,180,240,120,72):
            spin.setValue(value); settle()
            style=item.title_style; local=geometry(item.title_text,1080,style.font,style.size,True)[1].boundingRect()
            assert style.size==value and style.zoom_x==1 and local.width()<=973
            sizes.append(dict(size=value,width=local.width(),height=local.height()))
        QTest.mouseRelease(line,Qt.LeftButton,pos=line.rect().center()); settle(); report['live_size']=sizes
        panel.headline_size.change(180); panel.headline_scale.change(150); panel.headline_rotation.change(20); settle()
        position=(item.title_style.position_x,item.title_style.position_y); base_size=item.title_style.size
        preview=w.preview; preview.set_transform_controls_visible(True); preview.update(); settle()
        target=preview._headline_rect(item); anchor,corners,sides,handle,_=preview._transform_geometry(item,target)
        QTest.mousePress(preview,Qt.LeftButton,pos=handle.toPoint()); assert preview.drag_mode=='rotate'
        dest=anchor+QPointF(65,0); move(preview,dest); QTest.mouseRelease(preview,Qt.LeftButton,pos=dest.toPoint()); settle()
        assert abs(item.transform.rotation-90)<1 and item.title_style.size==base_size and item.title_style.zoom_x==1.5
        target=preview._headline_rect(item); anchor,corners,*_=preview._transform_geometry(item,target)
        corner=corners[2]; dest=anchor+(corner-anchor)*1.15
        QTest.mousePress(preview,Qt.LeftButton,pos=corner.toPoint()); assert preview.drag_mode=='headline_scale'
        move(preview,dest); QTest.mouseRelease(preview,Qt.LeftButton,pos=dest.toPoint()); settle()
        assert item.title_style.zoom_x>1.65 and item.title_style.size==base_size and position==(item.title_style.position_x,item.title_style.position_y)
        assert abs(item.transform.rotation-90)<1; report['native_handles']=True
        panel.headline_scale.change(100); panel.headline_rotation.change(-12); panel.headline_size.change(120); settle()
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False)
            for width,height in ((1480,920),(1120,760)):
                w.resize(width,height); settle(140); assert w.grab().save(str(out/f'headline-{theme}-{width}.png'))
                assert panel.headline_scale.isVisible() and panel.headline_rotation.isVisible()
            report['themes'].append(theme)
        for case,(width,height,size,scale,x,y,rotation) in enumerate(((320,568,40,1.2,.5,.5,23),(568,320,40,1.2,.5,.5,23),(400,400,40,1.2,.5,.5,23),(320,568,72,2,.8,.3,45))):
            p=Project(); p.settings.width=width; p.settings.height=height; p.settings.fps=10
            title=copy.deepcopy(item); title.start=0; title.duration=.2; title.title_style.size=size; title.title_style.zoom_x=title.title_style.zoom_y=scale; title.title_style.position_x=x; title.title_style.position_y=y; title.transform.rotation=rotation
            p.timeline=[title]; expected=frame(p,title,0)
            rgba=np.frombuffer(expected.constBits(),np.uint8).reshape(height,width,4).copy()
            mask=(rgba[:,:,0]>220)&(rgba[:,:,1]>220)&(rgba[:,:,2]>220)&(rgba[:,:,3]>220)
            target=out/f'headline-export-{case}-{width}x{height}.mp4'
            export(p,str(target),ExportPreset('Headline parity','h264',12,128,'test'),False,'CPU',ffmpeg=w.settings['ffmpeg'],export_audio=False)
            with av.open(str(target)) as video:actual=np.ascontiguousarray(next(video.decode(video=0)).to_ndarray(format='rgb24'))
            actual_mask=np.all(actual>220,axis=2); iou=np.count_nonzero(mask&actual_mask)/max(1,np.count_nonzero(mask|actual_mask)); assert iou>.94,iou
            expected.save(str(out/f'preview-{case}-{width}x{height}.png')); QImage(actual.data,width,height,actual.strides[0],QImage.Format_RGB888).copy().save(str(out/f'export-{case}-{width}x{height}.png'))
            report['exports'].append(dict(width=width,height=height,white_mask_iou=iou,edge_case=case==3))
        report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        w.close(); settle(); (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return 0 if report['passed'] else 1
