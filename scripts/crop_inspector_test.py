"""Native acceptance for crop, inspector scrubbing, effects, colour, snapping and anchor."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"crop-inspector-home")); os.environ.setdefault("QT_QPA_PLATFORM","windows")
from PySide6.QtCore import Qt,QPoint,QPointF,QTimer
from PySide6.QtGui import QImage,QColor,QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.widgets import CropCanvas,CropDialog
from kinetic_cut.model import Project,MediaItem,TimelineItem,Crop
from kinetic_cut.theme import STYLESHEET
from kinetic_cut.exporter import build_command,PRESETS

def drag(widget,a,b):
    QTest.mousePress(widget,Qt.LeftButton,Qt.NoModifier,a); QTest.mouseMove(widget,b,80); QTest.mouseRelease(widget,Qt.LeftButton,Qt.NoModifier,b)

def main():
    app=QApplication([]); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
    image=QImage(800,400,QImage.Format_RGB32); image.fill(QColor("#477aae")); canvas=CropCanvas(image,Crop()); canvas.resize(900,580); canvas.show(); app.processEvents()
    r=canvas.image_rect(); drag(canvas,(r.topLeft()+QPointF(r.width()*.2,r.height()*.2)).toPoint(),(r.topLeft()+QPointF(r.width()*.7,r.height()*.75)).toPoint())
    assert .48<canvas.crop.width<.52 and .53<canvas.crop.height<.57
    old=Crop(**canvas.crop.__dict__); s=canvas.selection_rect(); drag(canvas,s.center().toPoint(),(s.center()+QPointF(25,15)).toPoint()); assert canvas.crop.x>old.x and canvas.crop.y>old.y
    s=canvas.selection_rect(); drag(canvas,s.bottomRight().toPoint(),(s.bottomRight()+QPointF(30,10)).toPoint()); assert canvas.crop.width>old.width
    before=canvas.view_zoom; wheel=QWheelEvent(QPointF(400,250),QPointF(400,250),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False); QApplication.sendEvent(canvas,wheel); assert canvas.view_zoom>before
    QTest.mousePress(canvas,Qt.MiddleButton,Qt.NoModifier,QPoint(400,250)); QTest.mouseMove(canvas,QPoint(430,270),40); QTest.mouseRelease(canvas,Qt.MiddleButton,Qt.NoModifier,QPoint(430,270)); assert canvas.view_pan!=QPointF()
    canvas.grab().save(str(ROOT/"build"/"crop-canvas.png"))
    canvas.close()
    with tempfile.TemporaryDirectory(prefix="kinetic-inspector-") as directory:
        path=Path(directory)/"still.png"; image.save(str(path)); media=MediaItem("m",str(path),"image","still.png",0,800,400)
        p=Project(media=[media],timeline=[TimelineItem("v","m","video_1",0,2),TimelineItem("next","m","video_1",5,2)])
        w=MainWindow(); w.resize(1400,900); w.show(); w.set_project(p); w.timeline.select_ids({"v"},"v"); app.processEvents()
        assert hasattr(w,"crop_tool") and w.snap_tool.isChecked() and w.timeline.property("snapping")
        def crop_popup():
            dialog=app.activeModalWidget(); assert isinstance(dialog,CropDialog); cr=dialog.canvas.image_rect(); drag(dialog.canvas,(cr.topLeft()+QPointF(cr.width()*.1,cr.height()*.15)).toPoint(),(cr.topLeft()+QPointF(cr.width()*.8,cr.height()*.85)).toPoint()); dialog.accept()
        QTimer.singleShot(150,crop_popup); w.crop_tool.click(); QTest.qWait(250); assert .68<p.item_by_id("v").crop.width<.72 and .68<p.item_by_id("v").crop.height<.72
        spin=w.inspector.zoom_x.spin; spin.setSingleStep(.01); start=spin.value(); line=spin.lineEdit(); QTest.mousePress(line,Qt.LeftButton,Qt.NoModifier,line.rect().center()); QTest.mouseMove(line,line.rect().center()+QPoint(40,0),60); QTest.mouseRelease(line,Qt.LeftButton,Qt.NoModifier,line.rect().center()+QPoint(40,0)); assert spin.value()>start+.3
        held=spin.value(); QApplication.sendEvent(line,QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)); assert spin.value()==held
        slider=w.inspector.zoom_x.slider; slider.setVisible(True); held=spin.value(); QApplication.sendEvent(slider,QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)); assert spin.value()==held
        QTest.mouseDClick(line,Qt.LeftButton,Qt.NoModifier,line.rect().center()); assert not spin.keyboardTracking(); QTest.keyClick(spin,Qt.Key_A,Qt.ControlModifier); QTest.keyClicks(spin,"1.25"); QTest.keyClick(spin,Qt.Key_Return); assert abs(spin.value()-1.25)<.01,(spin.value(),line.text())
        w.apply_effect("Circle Facecam"); assert p.item_by_id("v").effects and w.inspector.tabs.isTabEnabled(2) and w.inspector.effect_picker.currentText()=="Circle Facecam"
        w.inspector.remove_effect(); assert not p.item_by_id("v").effects and p.item_by_id("v").transform.shape=="rectangle"
        w.inspector.apply_color_preset((True,.04,1.16,0,.35)); item=p.item_by_id("v"); assert item.grayscale and item.sharpen==.35 and w.inspector.tabs.isTabEnabled(3)
        graph=build_command(p,str(Path(directory)/"out.mp4"),PRESETS["TikTok · Fast"]); filters=graph[graph.index("-filter_complex")+1]; assert "hue=s=0" in filters and "unsharp=" in filters
        # Snap the first clip's trailing edge against the second clip's leading edge.
        tl=w.timeline; tl.set_zoom(45); tl.select_ids({"v"},"v"); rect=tl.item_rect(item); a=rect.center().toPoint(); b=a+QPoint(round(3.05*45),0)
        QTest.mousePress(tl.viewport(),Qt.LeftButton,Qt.NoModifier,a); QTest.mouseMove(tl.viewport(),b,60); assert tl.snap_guide==5; QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.NoModifier,b); assert abs(item.start-3)<.001
        # The visible anchor is independently draggable and changes the transform pivot.
        w.seek(3.2); app.processEvents(); target=w.preview._visible_items()[0][2]; anchor=target.center().toPoint(); QTest.mousePress(w.preview,Qt.LeftButton,Qt.NoModifier,anchor); QTest.mouseMove(w.preview,anchor+QPoint(25,12),60); QTest.mouseRelease(w.preview,Qt.LeftButton,Qt.NoModifier,anchor+QPoint(25,12)); assert item.transform.anchor_x>0
        w.grab().save(str(ROOT/"build"/"crop-inspector-colour.png")); w.close(); w.thread_pool.waitForDone(10000)
    print("PASS crop draw/move/resize/zoom/pan, numeric scrub/double-click/wheel, effects/bin, colours, snap edges/guide, anchor",flush=True)
if __name__=="__main__":main()
