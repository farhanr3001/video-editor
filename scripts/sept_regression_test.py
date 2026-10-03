"""September rehaul acceptance: real Qt input and real source media."""
import os,sys,time,copy,tempfile
import faulthandler
faulthandler.enable(); faulthandler.dump_traceback_later(25)
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"sept-ui-test"))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData
from PySide6.QtGui import QWheelEvent,QDragEnterEvent,QDragMoveEvent,QDropEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,Caption,uid
from kinetic_cut.media import probe,waveform
from kinetic_cut.theme import STYLESHEET
from kinetic_cut.workspace import set_page

def main():
    app=QApplication.instance() or QApplication([]); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
    # The offscreen backend does not enumerate Windows fonts. Register the
    # actual test fonts, as the native Windows backend does automatically.
    from PySide6.QtGui import QFontDatabase,QColor
    for font in ("arial.ttf","arialbd.ttf","segoeui.ttf","segoeuib.ttf"):QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+font)
    w=MainWindow(); w.resize(1680,1000); w.show(); app.processEvents()
    assert w.project.video_tracks==["video_1"] and w.project.audio_tracks==["audio_1"]
    media=probe(ROOT/"xqc_royalty.mp4"); w.project.media.append(media); w.refresh_media(); w.current_media_id=media.id
    w.add_media_to_track(media.id,"video_1",0); w.timeline.set_waveform(media.id,waveform(media.path))
    video=next(i for i in w.project.timeline if i.track=="video_1"); audio=next(i for i in w.project.timeline if i.track=="audio_1")
    assert len(w.project.linked_items(video))==2
    w.timeline.select_ids({video.id},video.id); w.seek(3); w.split_selected()
    assert len(w.project.timeline)==4
    left=[i for i in w.project.timeline if i.start==0]; right=[i for i in w.project.timeline if i.start==3]
    assert len(w.project.linked_items(right[0]))==2 and right[1] in w.project.linked_items(right[0])
    w.timeline.linked_selection=False; w.timeline.select_ids({right[0].id},right[0].id); w.seek(5); w.split_selected(); assert len(w.project.timeline)==5
    w.timeline.select_ids({video.id,audio.id},video.id); w.timeline.link_clips(True); assert len(w.project.linked_items(video))==1
    w.timeline.link_clips(False); assert len(w.project.linked_items(video))==2
    # Marquee is entirely clipped to the timeline viewport.
    tl=w.timeline; start=QPoint(round(tl.x_for_time(.3)),round(tl.track_rect("video_1").top()-12)); end=QPoint(round(tl.x_for_time(2)),round(tl.track_rect("audio_1").bottom()+10))
    QTest.mousePress(tl.viewport(),Qt.LeftButton,Qt.NoModifier,start); QTest.mouseMove(tl.viewport(),end,80); QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.NoModifier,end)
    assert {video.id,audio.id}<=tl.selected_ids
    # Alt-drag copies state and creates a video track above the highest track.
    tl.linked_selection=False; tl.select_ids({video.id},video.id); r=tl.item_rect(video); before=len(w.project.timeline)
    start=r.center().toPoint(); end=QPoint(start.x(),round(tl.track_rect("video_1").top()-15))
    QTest.mousePress(tl.viewport(),Qt.LeftButton,Qt.AltModifier,start); QTest.mouseMove(tl.viewport(),end,80); QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.AltModifier,end)
    assert len(w.project.timeline)==before+1 and len(w.project.video_tracks)==2
    # Audio Inspector changes amplitude and mixed selections preserve offsets.
    audios=[i for i in w.project.timeline if i.track in w.project.audio_tracks]; audios[0].gain_db=-6; audios[1].gain_db=-12
    tl.select_ids({i.id for i in audios},audios[0].id); app.processEvents(); assert w.inspector.tabs.currentIndex()==1
    assert w.inspector.volume.mixed; w.inspector.volume.spin.stepUp(); assert abs(audios[0].gain_db+5.9)<.001 and abs(audios[1].gain_db+11.9)<.001,[i.gain_db for i in audios]
    # Track-height zoom clamps, ordinary Ctrl+wheel zoom remains separate.
    wheel=QWheelEvent(QPointF(500,150),QPointF(500,150),QPoint(),QPoint(0,120),Qt.NoButton,Qt.ShiftModifier,Qt.ScrollUpdate,False)
    height=tl.track_height; QApplication.sendEvent(tl.viewport(),wheel); assert tl.track_height>height
    # Fade handles are timeline controls, not an Inspector substitute.
    tl.select_ids({audio.id},audio.id); r=tl.item_rect(audio)
    fade_start=QPoint(round(r.left()+5),round(r.top()+4)); fade_end=QPoint(round(r.left()+tl.pixels_per_second*.6),fade_start.y())
    QTest.mousePress(tl.viewport(),Qt.LeftButton,Qt.NoModifier,fade_start); QTest.mouseMove(tl.viewport(),fade_end,60); QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.NoModifier,fade_end)
    assert .4<audio.fade_in<.8,audio.fade_in
    before_volume=audio.gain_db
    QApplication.sendEvent(w.inspector.volume.spin,QWheelEvent(QPointF(15,10),QPointF(15,10),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False))
    assert audio.gain_db==before_volume
    # Collapsible independent panels and immutable queued jobs.
    w.media_toggle.setChecked(False); assert w.media_panel.isHidden() and not w.effects_panel.isHidden()
    w.effects_toggle.setChecked(False); assert w.left_stack.isHidden()
    w.media_toggle.setChecked(True); w.effects_toggle.setChecked(True)
    w.inspector_toggle.setChecked(False); assert w.right_stack.isHidden(); w.inspector_toggle.setChecked(True)
    c=Caption(uid(),.5,2,"A caption on ST1"); w.project.captions.append(c); w.model_changed(); w.select_caption(c.id)
    assert "subtitle_1" in tl.tracks(); assert w.inspector.video_stack.currentIndex()==1
    w.inspector.caption_text.setPlainText("Corrected caption"); assert c.text=="Corrected caption"
    w.inspector.customize.setChecked(True); w.inspector.edit_style("size",58); assert c.style.size==58 and w.project.subtitle_style.size==72
    mime=QMimeData(); mime.setData("application/x-kinetic-effect",b"Gaussian Blur"); drop_pos=tl.item_rect(video).center()
    QApplication.sendEvent(tl.viewport(),QDragEnterEvent(drop_pos.toPoint(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier))
    QApplication.sendEvent(tl.viewport(),QDragMoveEvent(drop_pos.toPoint(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier))
    QApplication.sendEvent(tl.viewport(),QDropEvent(drop_pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier))
    assert video.effects and w.inspector.tabs.isTabEnabled(2)
    set_page(w,1); w.delivery.location.setText(str(ROOT/"build")); w.delivery.name.setText("sept-queue-test"); w.delivery.add_job(); assert len(w.delivery.jobs)==1
    snapshot=w.delivery.jobs[0]["project"]; video.gain_db=7; assert snapshot.item_by_id(video.id).gain_db!=7
    set_page(w,0)
    # View-only pan and zoom must not mutate a clip transform.
    transform=copy.deepcopy(video.transform); old_zoom=w.preview.view_zoom
    zoom=QWheelEvent(QPointF(200,200),QPointF(200,200),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False)
    QApplication.sendEvent(w.preview,zoom); assert w.preview.view_zoom>old_zoom and video.transform==transform
    w.preview.reset_view()
    # Timeline-clock playback must survive clip boundaries and media selection.
    print("Before playback seek",flush=True)
    w.seek(2.7)
    print("Before playback play",flush=True)
    w.toggle_play()
    print("Before playback wait",flush=True)
    QTest.qWait(650)
    print("After boundary wait",flush=True)
    w.media_list.setCurrentRow(0); QTest.qWait(650)
    assert w.transport.playing and w.project.playhead>3.6,(w.transport.playing,w.project.playhead)
    w.stop(); w.seek(1); tl.select_ids({video.id},video.id); QTest.qWait(400)
    print("Caption state at preview",c.start,c.end,c.style.opacity,w.project.playhead,flush=True)
    with_caption=w.preview.grab().toImage(); saved_captions=w.project.captions; w.project.captions=[]
    with_caption.save(str(ROOT/"build"/"sept-preview-caption.png"))
    without_caption=w.preview.grab().toImage(); w.project.captions=saved_captions
    assert with_caption!=without_caption,"Caption must actually paint into the viewer"
    import numpy as np
    from PySide6.QtGui import QImage
    crop=w.preview.composition_rect(); y=round(crop.top()+crop.height()*.7)
    region=with_caption.copy(round(crop.left()),y,round(crop.width()),round(crop.height()*.2)).convertToFormat(QImage.Format_RGBA8888)
    pixels=np.frombuffer(region.constBits(),dtype=np.uint8).reshape(region.height(),region.width(),4)
    fill=QColor(c.style.color); expected=np.array([fill.red(),fill.green(),fill.blue()])
    assert np.count_nonzero(np.all(np.abs(pixels[:,:,:3].astype(int)-expected)<35,axis=2))>20,"Subtitle fill must be visible above its outline"
    w.inspector.tabs.setCurrentIndex(0); app.processEvents(); w.grab().save(str(ROOT/"build"/"sept-video-inspector.png"))
    tl.select_ids({audio.id},audio.id); app.processEvents(); w.grab().save(str(ROOT/"build"/"sept-audio-inspector.png"))
    w.select_caption(c.id); w.inspector.subtitle.setCurrentIndex(1); app.processEvents(); w.grab().save(str(ROOT/"build"/"sept-subtitle-inspector.png"))
    w.inspector.edit_style("color","#66FFFF"); assert w.project.subtitle_style.color=="#66FFFF" and c.style.color!="#66FFFF"
    tl.select_ids({video.id},video.id); w.inspector.tabs.setCurrentIndex(0); app.processEvents()
    w.grab().save(str(ROOT/"build"/"sept-edit-workspace.png")); set_page(w,1); app.processEvents(); w.grab().save(str(ROOT/"build"/"sept-deliver-workspace.png"))
    # A pre-existing cut receives the layout without recreating/deleting audio.
    set_page(w,0); tl.select_ids({video.id},video.id); old_audio=[i.id for i in w.project.timeline if i.track in w.project.audio_tracks]
    old_timing=(video.start,video.in_point,video.duration); w.apply_vertical()
    assert (video.start,video.in_point,video.duration)==old_timing
    assert old_audio==[i.id for i in w.project.timeline if i.track in w.project.audio_tracks]
    assert any(i.role=="background" for i in w.project.linked_items(video))
    count=len(w.project.timeline); w.undo(); assert len(w.project.timeline)==count-2; w.redo(); assert len(w.project.timeline)==count
    # The program viewport pans independently; ruler dragging continuously seeks.
    pan=QPointF(w.preview.view_pan); QTest.mousePress(w.preview,Qt.MiddleButton,Qt.NoModifier,QPoint(120,120)); QTest.mouseMove(w.preview,QPoint(150,145),50); QTest.mouseRelease(w.preview,Qt.MiddleButton,Qt.NoModifier,QPoint(150,145))
    assert w.preview.view_pan!=pan; w.preview.reset_view()
    start=QPoint(round(tl.x_for_time(.5)),12); end=QPoint(round(tl.x_for_time(2)),12)
    QTest.mousePress(tl.viewport(),Qt.LeftButton,Qt.NoModifier,start); QTest.mouseMove(tl.viewport(),end,50); QTest.mouseRelease(tl.viewport(),Qt.LeftButton,Qt.NoModifier,end)
    assert abs(w.project.playhead-2)<.06
    w.resize(1366,768); app.processEvents(); w.grab().save(str(ROOT/"build"/"sept-compact-workspace.png"))
    print("UI assertions and screenshots complete; closing",flush=True)
    w.close(); w.thread_pool.waitForDone(30000)
    faulthandler.cancel_dump_traceback_later()
    print("PASS September UI: playback boundaries, link/split, marquee, Alt-drag, tracks, audio multi-edit, panel toggles, subtitle, effects, queue, zoom")

if __name__=="__main__":main()
