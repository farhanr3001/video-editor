import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData,QEvent,QThreadPool
from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDropEvent,QDragLeaveEvent,QWheelEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption
from kinetic_cut.workspace import PowerBins
from kinetic_cut import binclips


class PreviewBinsDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.w=MainWindow(); self.w.resize(1680,1000); self.w.show(); self.app.processEvents()
        self.w.media_panel.power=PowerBins(Path(self.temp.name)/"bins.json"); self.w.media_panel.rebuild_tree()
    def tearDown(self):
        QApplication.sendEvent(self.w.timeline.viewport(),QDragLeaveEvent()); QApplication.sendEvent(self.w.media_panel.grid.viewport(),QDragLeaveEvent())
        QThreadPool.globalInstance().waitForDone(5000); self.app.processEvents(); self.app.clipboard().clear()
        for widget in self.app.topLevelWidgets():widget.close(); widget.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
    def source(self,id="image",kind="image",duration=5):return MediaItem(id,str(Path(self.temp.name)/(id+(".png" if kind=="image" else ".mp4"))),kind,id,duration,400,200,60,kind=="video")
    def saved(self):
        m=self.source(); self.w.project.media=[m]; c=TimelineItem("clip",m.id,"video_1",0,3); c.transform.x=.23; c.transform.scale=1.4; self.w.project.timeline=[c]; self.w.model_changed()
        saved=binclips.asset(binclips.snapshot(self.w.project,{"clip"},set(),"clip")); self.w.media_panel.power.add(saved,"Master"); return saved
    def mime(self,ids):
        mime=QMimeData(); mime.setData("application/x-kinetic-media-id",ids[0].encode()); mime.setData("application/x-kinetic-media-ids",json.dumps(ids).encode()); return mime
    def drag(self,widget,mime,pos,drop=False):
        self._drag_mime=mime
        pos=QPointF(pos); enter=QDragEnterEvent(pos.toPoint(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(widget,enter)
        if not enter.isAccepted():return enter
        move=QDragMoveEvent(pos.toPoint(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(widget,move)
        if drop:
            event=QDropEvent(pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(widget,event); return event
        return move
    def test_playback_sync_does_not_restart_unchanged_frame_timer(self):
        w=self.w; m=self.source(kind="video"); w.project.media=[m]; w.project.timeline=[TimelineItem("v",m.id,"video_1",0,5)]
        t=w.transport; player=Mock(); player.position.return_value=0; player.playbackState.return_value=0; sink=Mock(); t.decoders[(m.id,0,1.,"video")]=(player,Mock(),sink)
        try:
            with patch.object(t.frame_timer,"setInterval",wraps=t.frame_timer.setInterval) as set_interval,patch("kinetic_cut.transport.QMetaObject.invokeMethod"):
                for _ in range(10):t.sync()
                set_interval.assert_not_called(); w.project.settings.fps=30
                for _ in range(10):t.sync()
                set_interval.assert_called_once_with(33)
        finally:t.decoders.clear(); t.frame_timer.stop()
    def test_power_bin_background_accepts_timeline_drop_without_pool_mutation(self):
        self.saved(); w=self.w; panel=w.media_panel; panel.folder="Master"; panel.refresh(); before=copy.deepcopy(w.project.to_dict())
        payload=binclips.snapshot(w.project,{"clip"},set(),"clip"); mime=QMimeData(); mime.setData(binclips.MIME,json.dumps(payload).encode())
        self.assertTrue(panel.grid.acceptDrops(),"Grid does not accept drops"); self.assertTrue(panel.grid.viewport().acceptDrops(),"Viewport does not accept drops")
        event=self.drag(panel.grid.viewport(),mime,QPoint(210,190),True)
        self.assertTrue(event.isAccepted()); self.assertEqual(w.project.to_dict(),before); self.assertEqual(len(panel.power.data["media"]),2)
        panel.folder="project"; panel.refresh(); denied=self.drag(panel.grid.viewport(),mime,QPoint(210,190),True); self.assertFalse(denied.isAccepted())
    def test_power_bin_folder_tile_is_a_drop_target(self):
        self.saved(); panel=self.w.media_panel; panel.power.add_folder("Master/Saved"); panel.folder="Master"; panel.refresh()
        mime=QMimeData(); mime.setData(binclips.MIME,json.dumps(binclips.snapshot(self.w.project,{"clip"},set())).encode())
        folder=next(panel.grid.item(n) for n in range(panel.grid.count()) if panel.grid.item(n).data(Qt.UserRole+1)=="folder")
        event=self.drag(panel.grid.viewport(),mime,panel.grid.visualItemRect(folder).center(),True)
        self.assertTrue(event.isAccepted()); self.assertEqual(panel.power.data["media"][-1]["folder"],"Master/Saved")
    def test_saved_preset_selection_cancel_and_reinsert_never_import_wrapper(self):
        saved=self.saved(); w=self.w; panel=w.media_panel; panel.folder="Master"; panel.refresh(); panel.grid.item(0).setSelected(True); self.app.processEvents()
        self.assertEqual([m.id for m in w.project.media],["image"])
        self.assertEqual(panel.materialize(saved.id),saved.id); self.assertEqual(len(w.project.media),1)
        w.add_media_to_track(saved.id,"video_1",7); self.assertEqual(len(w.project.media),1); self.assertFalse(w.project.media[0].timeline_preset)
        placed=next(i for i in w.project.timeline if i.start==7); self.assertEqual((placed.transform.x,placed.transform.scale),(.23,1.4))
        panel.power=PowerBins(panel.power.path); w.set_project(Project()); w.add_media_to_track(saved.id,"video_1",0)
        self.assertEqual(len(w.project.media),1); self.assertFalse(w.project.media[0].timeline_preset)
    def test_normal_power_bin_cancel_does_not_import_file(self):
        panel=self.w.media_panel; m=self.source(); panel.power.add(m,"Master"); before=self.w.project.to_dict(); panel.materialize(m.id)
        t=self.w.timeline; pos=QPoint(round(t.x_for_time(2)),round(t.track_rect("video_1").center().y())); event=self.drag(t.viewport(),self.mime([m.id]),pos)
        self.assertTrue(event.isAccepted()); self.assertTrue(t.incoming_preview); QApplication.sendEvent(t.viewport(),QDragLeaveEvent())
        self.assertFalse(t.incoming_preview); self.assertEqual(self.w.project.to_dict(),before)
    def test_open_project_removes_only_unused_legacy_preset_wrappers(self):
        saved=self.saved(); p=copy.deepcopy(self.w.project); p.media.append(saved); self.w.set_project(p)
        self.assertEqual([m.id for m in self.w.project.media],["image"]); self.assertEqual(self.w.project.timeline[0].media_id,"image")
        self.assertTrue(self.w.media_panel.resolve_media(saved.id).timeline_preset)
    def test_incoming_batch_ghost_matches_commit_and_snap_toggle(self):
        w=self.w; p=w.project; p.media=[self.source("one"),self.source("two")]; p.timeline=[TimelineItem("base","one","video_1",0,3)]; w.model_changed(); t=w.timeline
        pos=QPoint(round(t.x_for_time(3.09)),round(t.track_rect("video_1").center().y())); mime=self.mime(["one","two"]); before=copy.deepcopy(p.to_dict())
        event=self.drag(t.viewport(),mime,pos); self.assertTrue(event.isAccepted()); self.assertEqual(p.to_dict(),before)
        expected=sorted((i.start,i.duration,i.track) for i in t.incoming_preview); self.assertEqual(expected,[(3.,5.,"video_1"),(8.,5.,"video_1")])
        self.assertTrue(all(i._drag_ghost for i in t.incoming_preview)); t.viewport().grab()
        event=self.drag(t.viewport(),mime,pos,True); self.assertTrue(event.isAccepted()); self.assertFalse(t.incoming_preview)
        actual=sorted((i.start,i.duration,i.track) for i in p.timeline if i.id!="base"); self.assertEqual(actual,expected)
        t.setProperty("snapping",False); event=self.drag(t.viewport(),mime,pos); self.assertGreater(t.incoming_drop[2],3)
    def test_provisional_video_and_linked_audio_lanes_are_visual_only_until_drop(self):
        w=self.w; w.project.media=[self.source("video","video",2)]; w.project.timeline=[TimelineItem("occupied","video","audio_1",0,10)]; w.model_changed(); t=w.timeline
        point=QPoint(round(t.x_for_time(2)),round(t.track_rect("video_1").top()-15)); before=copy.deepcopy(w.project.to_dict())
        with patch.object(w.transport,"sync"),patch.object(w,"start_worker"):
            event=self.drag(t.viewport(),self.mime(["video"]),point); self.assertTrue(event.isAccepted()); self.assertEqual(w.project.to_dict(),before)
            self.assertEqual(len(t.display_tracks("video")),2); self.assertEqual(len(t.display_tracks("audio")),2); t.viewport().grab()
            self.assertEqual({i.track for i in t.incoming_preview},{"video_2","audio_2"})
            QApplication.sendEvent(t.viewport(),QDragLeaveEvent()); self.assertEqual(t.display_tracks("video"),["video_1"]); self.assertEqual(t.display_tracks("audio"),["audio_1"])
            self.drag(t.viewport(),self.mime(["video"]),point,True)
            self.assertEqual({i.track for i in w.project.timeline if i.id!="occupied"},{"video_2","audio_2"}); self.assertFalse(t.incoming_preview)
    def test_saved_caption_has_a_grey_subtitle_preview(self):
        p=Project(captions=[Caption("c",0,2,"Saved caption")]); saved=binclips.asset(binclips.snapshot(p,set(),{"c"})); self.w.media_panel.power.add(saved,"Master")
        t=self.w.timeline; point=QPoint(round(t.x_for_time(2)),round(t.track_rect("video_1").center().y()))
        self.assertTrue(self.drag(t.viewport(),self.mime([saved.id]),point).isAccepted()); self.assertIn("subtitle_1",t.tracks()); self.assertEqual(t.incoming_preview[0].title_text,"Saved caption"); t.viewport().grab()
    def test_locked_drop_rejected_without_ghost_or_mutation(self):
        w=self.w; w.project.media=[self.source()]; w.project.track_states["video_1"]["locked"]=True; before=copy.deepcopy(w.project.to_dict()); t=w.timeline
        point=QPoint(round(t.x_for_time(2)),round(t.track_rect("video_1").center().y()))
        self.assertFalse(self.drag(t.viewport(),self.mime(["image"]),point).isAccepted()); self.assertFalse(t.incoming_preview); self.assertEqual(w.project.to_dict(),before)

    def test_entering_over_header_can_continue_to_valid_pool_drop(self):
        w=self.w; media=self.source(); w.project.media=[media]; w.refresh_media(); t=w.timeline
        mime=self.mime([media.id]); header=QPoint(20,round(t._sections()['video'].center().y()))
        enter=QDragEnterEvent(header,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(t.viewport(),enter); self.assertTrue(enter.isAccepted())
        target=QPoint(round(t.x_for_time(2)),round(t.track_rect('video_1').center().y()))
        move=QDragMoveEvent(target,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(t.viewport(),move); self.assertTrue(move.isAccepted())
        drop=QDropEvent(QPointF(target),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(t.viewport(),drop); self.assertTrue(drop.isAccepted()); self.assertTrue(w.project.timeline)
    def test_zoom_out_is_twenty_times_wider_and_old_limit_at_slider_midpoint(self):
        w=self.w; w.timeline_zoom.setValue(500); self.assertAlmostEqual(w.timeline.pixels_per_second,12)
        w.timeline_zoom.setValue(0); self.assertAlmostEqual(w.timeline.pixels_per_second,.6)
        w.timeline_zoom.setValue(1000); self.assertAlmostEqual(w.timeline.pixels_per_second,240)
        w.timeline.set_zoom(1); event=QWheelEvent(QPointF(500,180),QPointF(500,180),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.AltModifier,Qt.NoScrollPhase,False)
        QApplication.sendEvent(w.timeline.viewport(),event); self.assertLess(w.timeline.pixels_per_second,1); w.timeline.viewport().grab()
    def test_colours_tab_has_visible_palette_icon(self):self.assertFalse(self.w.inspector.tabs.tabIcon(3).isNull())
