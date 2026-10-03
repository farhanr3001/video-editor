"""Isolated packaged dialog and preview/export parity checks for animated clips."""
def run(output):
    import os,json,sys,time,traceback
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt,QTimer,QEventLoop,QThreadPool
    from PySide6.QtGui import QImage,QPainter,QColor
    from .ui import MainWindow
    from .keyframe_editor import KeyframeEditor
    from .model import Project,MediaItem,TimelineItem,Transform
    from .rendergraph import command
    from .exporter import PRESETS
    from .process import run as process
    from .theme import STYLESHEET
    source=output/'fixture.png'; image=QImage(160,90,QImage.Format_RGB32); image.fill(Qt.white)
    painter=QPainter(image); painter.fillRect(35,20,35,40,QColor('#ee5533')); painter.end(); image.save(str(source))
    app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
    w=MainWindow(); w.resize(1400,850); w.show(); w.autosave_timer.stop(); report={'frozen':bool(getattr(sys,'frozen',False))}
    def wait(ms=50):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    try:
        p=Project(media=[MediaItem('m',str(source),'image','Keyframe fixture',2,160,90)],timeline=[TimelineItem('v','m','video_1',0,2,transform=Transform(.3,.5,.3))])
        p.settings.width=320; p.settings.height=180; p.settings.fps=30; w.set_project(p)
        d=KeyframeEditor(w,p.timeline[0]); d.show(); wait()
        for n in ('scale','x','rotation','opacity'):d.add_key(n)
        d.seek(1)
        for n,v in [('scale',.6),('x',.65),('rotation',20),('opacity',70)]:d.add_key(n); d.edit_value(n,v)
        d.grab().save(str(output/'editor.png')); assert len(d.item.keyframes)==5
        d.accept(); assert p.timeline[0].keyframes; report['dialog_save']=True
        target=output/'animated.mp4'; result=process(command(p,str(target),next(iter(PRESETS.values())),False,'CPU',export_audio=False),capture_output=True)
        assert result.returncode==0,result.stderr.decode(errors='replace')[-3000:]
        raw=process(['ffmpeg','-v','error','-i',str(target),'-vf','select=eq(n\,0)+eq(n\,15)+eq(n\,30)','-vsync','0','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
        frames=np.frombuffer(raw,np.uint8).reshape(-1,180,320,3); comparisons=[]
        for at,frame in zip((0,.5,1),frames):
            w.seek(at); wait(); r=w.preview.composition_rect().toRect(); shot=w.preview.grab().toImage().copy(r).scaled(320,180,Qt.IgnoreAspectRatio,Qt.SmoothTransformation).convertToFormat(QImage.Format_RGB888)
            actual=np.frombuffer(shot.bits(),np.uint8).reshape(180,shot.bytesPerLine())[:,:960].reshape(180,320,3)
            ay,ax=np.where(actual.mean(axis=2)>60); ey,ex=np.where(frame.mean(axis=2)>60)
            center_error=abs(ax.mean()-ex.mean())+abs(ay.mean()-ey.mean()); area_ratio=len(ax)/len(ex)
            comparisons.append(dict(time=at,center_error_pixels=float(center_error),area_ratio=area_ratio))
            assert center_error<6 and .88<area_ratio<1.12,comparisons
            shot.save(str(output/f'preview-{at}.png')); QImage(frame.data,320,180,960,QImage.Format_RGB888).copy().save(str(output/f'export-{at}.png'))
        report['preview_export_parity']=comparisons
        w.undo(); assert not w.project.timeline[0].keyframes; w.redo(); assert w.project.timeline[0].keyframes; report['undo_redo']=True
        d=KeyframeEditor(w,w.project.timeline[0]); d.remove_all(); d.reject(); assert w.project.timeline[0].keyframes; report['cancel_remove_all']=True
        report['passed']=True
    except Exception:report['passed']=False; report['error']=traceback.format_exc()
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(10000); app.processEvents(); (output/'report.json').write_text(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1
