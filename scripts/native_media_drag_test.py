"""Full Windows mouse gesture: icon grid -> native QDrag -> timeline drop."""
import os,sys,threading,time,ctypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"drag-test-home")); os.environ["QT_QPA_PLATFORM"]="windows"
from PySide6.QtCore import QPoint,Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.media import probe
from kinetic_cut.theme import STYLESHEET
from kinetic_cut.model import Project
from kinetic_cut.workspace import PowerBins

def native_drag(app,source,target):
    user=ctypes.windll.user32
    def gesture():
        user.SetCursorPos(source.x(),source.y()); time.sleep(.12); user.mouse_event(2,0,0,0,0)
        for n in range(1,31):
            user.SetCursorPos(round(source.x()+(target.x()-source.x())*n/30),round(source.y()+(target.y()-source.y())*n/30)); time.sleep(.025)
        time.sleep(.15); user.mouse_event(4,0,0,0,0)
    thread=threading.Thread(target=gesture); thread.start()
    while thread.is_alive():QTest.qWait(20)
    QTest.qWait(300)

def main():
    app=QApplication([]); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET); w=MainWindow(); w.setWindowFlag(Qt.WindowStaysOnTopHint,True); w.resize(1300,850); w.show(); w.raise_(); w.activateWindow(); ctypes.windll.user32.SetForegroundWindow(int(w.winId())); QTest.qWait(700)
    media=probe(ROOT/"xqc_royalty.mp4"); w.project.media.append(media); w.refresh_media(); app.processEvents()
    grid=w.media_list; start=grid.viewport().mapToGlobal(grid.visualItemRect(grid.item(0)).center())
    end=w.timeline.viewport().mapToGlobal(QPoint(round(w.timeline.x_for_time(0)+20),round(w.timeline.track_rect("video_1").center().y())))
    if app.widgetAt(start)!=grid.viewport():
        w.grab().save(str(ROOT/"build"/"drag-preflight.png"))
        print("DRAG PREFLIGHT",start,end,app.widgetAt(start),grid.viewport().geometry(),grid.visualItemRect(grid.item(0)),flush=True)
    assert app.widgetAt(start)==grid.viewport(),"Native drag source must be unobscured"
    assert app.widgetAt(end)==w.timeline.viewport(),"Native drop target must be unobscured"
    native_drag(app,start,end)
    assert len(w.project.timeline)==2,(grid.dragEnabled(),grid.dragDropMode(),len(w.project.timeline))
    assert {i.track for i in w.project.timeline}=={"video_1","audio_1"}
    selected=w.project.item_by_id(w.timeline.selected_id)
    assert selected.track=="video_1" and w.timeline.selected_ids=={i.id for i in w.project.timeline}
    assert w.inspector.item_id==selected.id and w.inspector.tabs.currentIndex()==0 and w.inspector.filename.text()==media.name
    w.seek(1); w.toggle_play(); QTest.qWait(650); assert w.transport.playing and w.project.playhead>1.4
    w.stop()
    # Drag a persistent item into a folder, then use it in a fresh project.
    panel=w.media_panel; panel.power=PowerBins(ROOT/"build"/f"power-drag-{time.time_ns()}.json"); panel.power.add(media,"Master"); panel.power.add_folder("Master/Reusable"); panel.rebuild_tree()
    master=panel.tree.topLevelItem(0); folder=master.child(0); panel.choose_folder(master); app.processEvents()
    start=grid.viewport().mapToGlobal(grid.visualItemRect(grid.item(0)).center()); end=panel.tree.viewport().mapToGlobal(panel.tree.visualItemRect(folder).center())
    native_drag(app,start,end)
    assert [entry["folder"] for entry in panel.power.data["media"]]==["Master/Reusable"]
    assert PowerBins(panel.power.path).data==panel.power.data
    w.set_project(Project()); app.processEvents(); assert w.project.timeline==[]
    start=grid.viewport().mapToGlobal(grid.visualItemRect(grid.item(0)).center()); end=w.timeline.viewport().mapToGlobal(QPoint(round(w.timeline.x_for_time(0)+20),round(w.timeline.track_rect("video_1").center().y())))
    native_drag(app,start,end); assert len(w.project.timeline)==2
    # Exercise the actual exposed menu action; append respects the target lane end.
    panel.media_context(grid.visualItemRect(grid.item(0)).center()); menu=panel._menu
    assert any(a.text()=="Create Folder…" for a in menu.actions())
    action=next(a for a in menu.actions() if a.text()=="Add to Timeline"); action.trigger(); menu.close()
    assert len([i for i in w.project.timeline if i.track=="video_1"])==2
    selected=w.project.item_by_id(w.timeline.selected_id)
    assert selected.start>0 and w.inspector.item_id==selected.id
    w.timeline.linked_selection=False; w.inspector_toggle.setChecked(False)
    w.add_media_to_track(media.id,"audio_1",w.project.duration)
    selected=w.project.item_by_id(w.timeline.selected_id)
    assert selected.track in w.project.video_tracks and len(w.project.linked_items(selected))==2
    assert w.inspector.tabs.currentIndex()==0 and w.inspector_toggle.isChecked()
    w.close(); w.thread_pool.waitForDone(10000); print("PASS full native media drag and playback",flush=True)
if __name__=="__main__":main()
