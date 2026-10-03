"""Capture actual Qt incoming ghosts, Power Bin drop surface and zoom limits."""
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["KINETIC_CUT_HOME"]=str(ROOT/"build/incoming-visual-check/home")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QMimeData,QPoint,QEvent
from PySide6.QtGui import QDragEnterEvent,QDragLeaveEvent,QFontDatabase
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import MediaItem,TimelineItem
from kinetic_cut.workspace import PowerBins
from kinetic_cut.theme import STYLESHEET
from kinetic_cut import binclips

def main():
    output=ROOT/"build/incoming-visual-check"; output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]); app.setQuitOnLastWindowClosed(False); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
    for font in ("arial.ttf","arialbd.ttf","segoeui.ttf","segoeuib.ttf"):QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+font)
    w=MainWindow(); w.resize(1680,1000); w.show(); app.processEvents(); panel=w.media_panel
    panel.power=PowerBins(output/"visual-bins.json"); panel.power.data={"folders":["Master","Master/Logos"],"media":[]}
    m=MediaItem("logo",str(ROOT/"build/bins-visual-check/transparent-logo.png"),"image","Stream logo.png",5,800,300)
    w.project.media=[m]; w.project.timeline=[TimelineItem("base",m.id,"video_1",0,4)]; w.project.timeline[0].transform.scale=.4; w.model_changed(); w.refresh_media(); w.timeline.select_ids({"base"},"base")
    saved=binclips.asset(binclips.snapshot(w.project,{"base"},set(),"base")); saved.name="Saved logo treatment"; panel.power.add(saved,"Master"); panel.folder="Master"; panel.rebuild_tree(); panel.refresh(); app.processEvents()
    mime=QMimeData(); mime.setData("application/x-kinetic-media-id",saved.id.encode()); mime.setData("application/x-kinetic-media-ids",json.dumps([saved.id,m.id]).encode())
    t=w.timeline; point=QPoint(round(t.x_for_time(6)),round(t.track_rect("video_1").top()-16)); event=QDragEnterEvent(point,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(t.viewport(),event); assert event.isAccepted() and len(t.incoming_preview)==2; w.grab().save(str(output/"incoming.png")); QApplication.sendEvent(t.viewport(),QDragLeaveEvent())
    payload=QMimeData(); payload.setData(binclips.MIME,json.dumps(binclips.snapshot(w.project,{"base"},set())).encode()); event=QDragEnterEvent(QPoint(190,210),Qt.CopyAction,payload,Qt.LeftButton,Qt.NoModifier)
    QApplication.sendEvent(panel.grid.viewport(),event); assert event.isAccepted(); w.grab().save(str(output/"power-bin-drop.png")); QApplication.sendEvent(panel.grid.viewport(),QDragLeaveEvent())
    w.project.timeline[0].duration=600; t.set_project(w.project); w.timeline_zoom.setValue(0); w.grab().save(str(output/"zoom-out.png"))
    assert w.inspector.tabs.tabIcon(3).isNull() is False
    app.clipboard().clear(); w.close()
    for widget in app.topLevelWidgets():widget.close(); widget.deleteLater()
    app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()
    from kinetic_cut.icons import lucide_icon
    lucide_icon.cache_clear(); print("PASS incoming ghost, Power Bin surface, palette and zoom captures")

if __name__=="__main__":main()
