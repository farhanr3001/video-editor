"""Render/pixel and native-widget checks for captions, keying and new timeline UI."""
import os,sys,json,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/"build/followup-visual-check"; OUT.mkdir(parents=True,exist_ok=True)
os.environ.setdefault("QT_QPA_PLATFORM","offscreen"); os.environ.setdefault("KINETIC_CUT_HOME",str(OUT/"home"))
from PIL import Image,ImageDraw
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QImage
from PySide6.QtCore import Qt,QEventLoop,QTimer,QPointF,QPoint,QMimeData,QUrl,QEvent
from PySide6.QtGui import QDragEnterEvent,QDragLeaveEvent
from kinetic_cut.process import run
from kinetic_cut.model import Project,MediaItem,TimelineItem,CaptionStyle
from kinetic_cut.ui import MainWindow
from kinetic_cut.caption_style_dialog import CaptionStyleDialog
from kinetic_cut.chroma_dialog import ChromaSampleDialog
from kinetic_cut.chroma import apply,filter_string
from kinetic_cut.rendergraph import command
from kinetic_cut.exporter import PRESETS
from kinetic_cut.theme import STYLESHEET

def wait(ms):
    loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()

def main():
    app=QApplication([]); app.setQuitOnLastWindowClosed(False); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
    for font in ("arial.ttf","arialbd.ttf","segoeui.ttf","segoeuib.ttf"):QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+font)
    report={}
    w=None
    try:
        # Includes pre-existing transparent pixels and soft-key edges.
        source=Image.new("RGBA",(320,180),(0,255,0,255)); d=ImageDraw.Draw(source)
        d.rectangle((105,45,215,135),fill=(255,0,0,255)); d.rectangle((0,0,20,20),fill=(255,255,255,0)); d.rectangle((30,30,60,60),fill=(25,215,35,140))
        source.save(OUT/"green.png"); effect=dict(name="Green Screen",color="#00ff00",similarity=10.,softness=20.,enabled=True)
        result=apply(QImage(str(OUT/"green.png")),effect); result.save(str(OUT/"key-qt.png"))
        run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(OUT/"green.png"),"-vf",filter_string(effect),"-frames:v","1",str(OUT/"key-ffmpeg.png")],check=True,capture_output=True)
        a=np.array(Image.open(OUT/"key-qt.png").convert("RGBA"),dtype=np.int16); b=np.array(Image.open(OUT/"key-ffmpeg.png").convert("RGBA"),dtype=np.int16)
        report["key_alpha_max_error"]=int(abs(a[:,:,3]-b[:,:,3]).max()); assert report["key_alpha_max_error"]<=1
        Image.new("RGBA",(320,180),(0,0,255,255)).save(OUT/"blue.png")
        p=Project(); p.settings.width=320; p.settings.height=180; p.settings.fps=30; p.add_track("video")
        p.media=[MediaItem(name,str(OUT/(name+".png")),"image",name,1,320,180) for name in ("blue","green")]
        lower=TimelineItem("blue","blue","video_1",0,1); upper=TimelineItem("green","green","video_2",0,1,effects=[effect]); p.timeline=[lower,upper]
        run(command(p,str(OUT/"keyed.mp4"),next(iter(PRESETS.values())),False,"CPU",export_audio=False),check=True,capture_output=True)
        from kinetic_cut.widgets import extract_frame
        frame=extract_frame(str(OUT/"keyed.mp4"),.2); frame.save(str(OUT/"composition-export.png"))
        assert frame.pixelColor(80,80).blue()>240 and frame.pixelColor(160,90).red()>240
        upper.brightness=.04; upper.transform.shape="circle"
        run(command(p,str(OUT/"keyed-graded-circle.mp4"),next(iter(PRESETS.values())),False,"CPU",export_audio=False),check=True,capture_output=True)
        graded=extract_frame(str(OUT/"keyed-graded-circle.mp4"),.2)
        assert graded.pixelColor(80,80).blue()>240 and graded.pixelColor(160,90).red()>240
        upper.brightness=0; upper.transform.shape="rectangle"
        w=MainWindow(); w.resize(1680,1000); w.show(); w.set_project(p); w.seek(.2); wait(80)
        w.preview.set_transform_controls_visible(False); view=w.preview.grab().toImage(); rect=w.preview.composition_rect()
        center=view.pixelColor(int(rect.center().x()),int(rect.center().y())); key=view.pixelColor(int(rect.left()+rect.width()*.25),int(rect.center().y()))
        assert center.red()>240 and key.blue()>240; report["key_composition_preview_export"]=True
        w.select_item(upper.id); w.inspector.tabs.setCurrentIndex(2); wait(30); w.grab().save(str(OUT/"key-workspace.png"))
        style=CaptionStyle(); dialog=CaptionStyleDialog(style,{},w); dialog.show(); wait(40); dialog.grab().save(str(OUT/"caption-preview-default.png"))
        dialog.animation.setCurrentText("word highlight"); dialog.background.setChecked(True); dialog.upper.setChecked(True); dialog.censor.setChecked(True); dialog.colors["background_color"]="#183245"; dialog.refresh(); wait(30)
        dialog.grab().save(str(OUT/"caption-preview-highlight.png")); dialog.reject()
        sampler=ChromaSampleDialog(w,upper); sampler.show(); wait(120); sampler.pick("#00ff00"); sampler.grab().save(str(OUT/"colour-sampler.png")); sampler.reject()
        mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(OUT/"green.png"))]); t=w.timeline
        point=QPoint(int(t.x_for_time(2)),int(t.track_rect("video_2").center().y()))
        event=QDragEnterEvent(point,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(t.viewport(),event)
        assert event.isAccepted() and t.incoming_preview; t.grab().save(str(OUT/"explorer-incoming.png")); QApplication.sendEvent(t.viewport(),QDragLeaveEvent())
        report["passed"]=True
    except Exception:report.update(passed=False,error=traceback.format_exc())
    finally:
        if w:w.close(); w.thread_pool.waitForDone(10000)
        wait(100); app.clipboard().clear()
        for widget in app.topLevelWidgets():widget.close(); widget.deleteLater()
        app.sendPostedEvents(None,QEvent.DeferredDelete); wait(30)
    (OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8"); print(json.dumps(report,indent=2)); return 0 if report.get("passed") else 1

if __name__=="__main__":sys.exit(main())
