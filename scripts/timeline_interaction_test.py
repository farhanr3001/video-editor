"""Native input coverage for trim/fade/retime/overwrite and workspace bounds."""
import os,sys,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"timeline-input-home")); os.environ.setdefault("QT_QPA_PLATFORM","windows")
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem,MediaItem
from kinetic_cut.media import probe
from kinetic_cut.theme import STYLESHEET

def drag(tl,start,end,release=True):
    QTest.mousePress(tl.viewport(),Qt.LeftButton,Qt.NoModifier,start); QTest.mouseMove(tl.viewport(),end,60)
    if release:QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.NoModifier,end)

def main():
    app=QApplication([]); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET); w=MainWindow(); w.resize(1440,900); w.show(); QTest.qWait(250)
    m=probe(ROOT/"xqc_royalty.mp4"); p=Project(media=[m],timeline=[TimelineItem("v",m.id,"video_1",0,4,3,group_id="g"),TimelineItem("a",m.id,"audio_1",0,4,3,group_id="g"),TimelineItem("next",m.id,"video_1",4,6,10)])
    w.set_project(Project(media=[m])); w.inspector_toggle.setChecked(False); w.add_media_to_track(m.id,"video_1",0)
    primary=w.project.item_by_id(w.timeline.selected_id)
    assert primary.track=="video_1" and w.inspector.item_id==primary.id and w.inspector.tabs.currentIndex()==0 and w.inspector_toggle.isChecked()
    w.timeline.linked_selection=False; w.add_media_to_track(m.id,"audio_1",45)
    primary=w.project.item_by_id(w.timeline.selected_id)
    assert primary.track=="video_1" and len(w.project.linked_items(primary))==2 and w.inspector.tabs.currentIndex()==0
    w.timeline.linked_selection=True
    w.set_project(p); tl=w.timeline; tl.setProperty("snapping",False); tl.select_ids({"v"},"v"); tl.setFocus()
    QTest.keyClick(w,Qt.Key_R,Qt.ControlModifier); assert tl.retime_ids=={"v","a"}
    r=tl.item_rect(p.item_by_id("v")); start=QPoint(round(r.right()-2),round(r.center().y())); end=start+QPoint(90,0)
    drag(tl,start,end,False)
    assert p.item_by_id("next").start==4,"No overwrite until release"
    assert abs(p.item_by_id("v").duration-6)<.06 and p.item_by_id("a").speed==p.item_by_id("v").speed
    QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.NoModifier,end)
    assert abs(p.item_by_id("next").start-6)<.06 and abs(p.item_by_id("next").in_point-12)<.06
    tl.speed_menu(p.item_by_id("v"),tl.mapToGlobal(QPoint(300,50))); submenu=tl._menu.actions()[0].menu(); next(a for a in submenu.actions() if a.text()=="200%").trigger(); tl._menu.close()
    assert p.item_by_id("v").duration==2 and p.item_by_id("a").duration==2
    w.seek(.1); w.transport.play(); QTest.qWait(1000)
    assert w.transport.playing and w.transport.position>.8
    key=next(k for k in w.transport.decoders if k[-1]=="video")
    player=w.transport.decoders[key][0]
    assert player.playbackRate()==2 and abs(player.position()/1000-p.item_by_id("v").source_time(w.transport.position))<.5
    assert key in w.preview.frames and not w.preview.frames[key].isNull(),"Retimed preview must decode frames"
    w.transport.pause()
    for attr,row in w.inspector.bindings:
        assert row.height()>=28 and row.spin.height()>=24
    print("Inspector geometry",w.inspector.video.size(),w.inspector.video.minimumSizeHint(),flush=True)
    w.grab().save(str(ROOT/"build"/"retime-workspace.png"))
    tl.set_speed(1); tl.toggle_retime(); assert not tl.retime_ids
    QTest.qWait(700)
    assert not w.transport.playing
    assert any(k[-1]=="video" and k in w.preview.frames for k in w.transport.decoders),"Paused retime changes must refresh the viewer"
    # Video fade handle, linked audio fade, visible feedback, and source trim.
    r=tl.item_rect(p.item_by_id("v")); start=QPoint(round(r.left()+5),round(r.top()+4)); end=start+QPoint(30,0)
    drag(tl,start,end,False); assert p.item_by_id("v").fade_in>.5 and p.item_by_id("a").fade_in>.5
    w.grab().save(str(ROOT/"build"/"video-fade-drag.png")); QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.NoModifier,end)
    # Moving over another clip subtracts the overlap only on release.
    tl.linked_selection=False; tl.select_ids({"v"},"v"); r=tl.item_rect(p.item_by_id("v")); start=r.center().toPoint(); end=start+QPoint(6*45,0)
    before=copy.deepcopy(p.item_by_id("next")); drag(tl,start,end,False); assert p.item_by_id("next")==before
    QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.NoModifier,end); assert p.item_by_id("next") is None
    # Empty selection means no stale controls, and the timeline extends below Inspector.
    tl.select_ids(set()); assert all(not w.inspector.tabs.isTabEnabled(n) for n in range(3)); assert w.inspector.video.isHidden() and w.inspector.audio.isHidden() and w.inspector.effects.isHidden()
    app.processEvents(); assert tl.mapTo(w,QPoint(tl.width(),0)).x()>=w.right_stack.mapTo(w,QPoint(w.right_stack.width(),0)).x()-3
    assert tl.mapTo(w,QPoint(0,0)).y()>w.right_stack.mapTo(w,QPoint(0,w.right_stack.height())).y()
    w.center_split.setSizes([1,900]); app.processEvents(); assert w.viewer_split.height()>=230
    w.center_split.setSizes([900,1]); app.processEvents(); assert tl.height()>=140
    w.center_split.setSizes([440,350]); w.grab().save(str(ROOT/"build"/"full-width-timeline.png"))
    # Still-image edges extend both ways; video edges stop at their source bounds.
    still=MediaItem("still","unused.png","image","image.png",0,320,180)
    p.media.append(still); p.timeline=[TimelineItem("image",still.id,"video_1",3,2),TimelineItem("trim",m.id,"audio_1",3,2,1)]
    tl.select_ids({"image"},"image"); tl.viewport().update(); app.processEvents()
    r=tl.item_rect(p.item_by_id("image")); drag(tl,QPoint(round(r.right()-2),round(r.center().y())),QPoint(round(r.right()+88),round(r.center().y())))
    assert abs(p.item_by_id("image").duration-4)<.06
    r=tl.item_rect(p.item_by_id("image")); drag(tl,QPoint(round(r.left()+2),round(r.center().y())),QPoint(round(r.left()-88),round(r.center().y())))
    assert abs(p.item_by_id("image").start-1)<.06 and abs(p.item_by_id("image").duration-6)<.06
    tl.select_ids({"trim"},"trim"); r=tl.item_rect(p.item_by_id("trim")); drag(tl,QPoint(round(r.left()+2),round(r.center().y())),QPoint(round(r.left()-100),round(r.center().y())))
    assert p.item_by_id("trim").in_point==0 and p.item_by_id("trim").start==2
    w.close(); w.thread_pool.waitForDone(10000); print("PASS retime/presets/linked audio/video fades/release overwrite/empty inspector/full-width bounded timeline")
if __name__=="__main__":main()
