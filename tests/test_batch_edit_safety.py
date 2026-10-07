import time,unittest
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt,QEventLoop,QTimer,QThreadPool,QEvent,QPoint,QPointF
from PySide6.QtGui import QImage,QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem,Caption
from kinetic_cut.timeline import TimelineWidget


class BatchEditSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000)
        loop=QEventLoop(); QTimer.singleShot(50,loop.quit); loop.exec()
        for w in self.app.topLevelWidgets():w.close(); w.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete)
    def window(self):
        w=MainWindow(); w.resize(1680,1000); w.show(); self.app.processEvents(); return w
    def project(self):
        p=Project(); p.add_track("video"); p.add_track("audio")
        p.timeline=[TimelineItem("v","","video_1",0,3,group_id="av"),TimelineItem("a","","audio_1",0,3,group_id="av"),TimelineItem("t","","video_2",1,2,role="title",title_text="Headline"),TimelineItem("locked","","audio_2",5,3)]
        p.captions=[Caption("c",0,3,"Caption")]; p.track_states["audio_2"]["locked"]=True
        return p
    def test_delete_mixed_selection_is_one_undoable_edit_and_respects_locks(self):
        w=self.window(); w.set_project(self.project()); t=w.timeline; t.select_ids({"v","t"},"v"); t.selected_caption_ids={"c"}; t.selected_caption="c"
        before=w._history_index; w.delete_selected(True)
        self.assertEqual([i.id for i in w.project.timeline],["locked"]); self.assertEqual(w.project.timeline[0].start,5)
        self.assertFalse(w.project.captions); self.assertFalse(t.selected_ids|t.selected_caption_ids); self.assertFalse(w.preview.selected_item_id or w.preview.selected_caption_id)
        self.assertEqual(w._history_index,before+1); w.undo(); self.assertEqual(len(w.project.timeline),4); self.assertEqual(len(w.project.captions),1)
        w.redo(); self.assertEqual(len(w.project.timeline),1)
    def test_delete_accepts_valid_selection_without_primary_and_empty_repeat(self):
        w=self.window(); w.set_project(self.project()); w.timeline.selected_ids={"v","a","t"}; w.timeline.selected_id="stale"
        w.delete_selected(); self.assertEqual([i.id for i in w.project.timeline],["locked"])
        before=w._history_index; w.delete_selected(); self.assertEqual(w._history_index,before)
    def test_model_batch_delete_does_not_delete_or_ripple_locked_lanes(self):
        p=self.project(); p.track_states["subtitle_1"]={"locked":True}
        p.delete((i.id for i in p.timeline),True,{"c"})
        self.assertEqual([i.id for i in p.timeline],["locked"]); self.assertEqual((p.captions[0].start,p.captions[0].end),(0,3))
    def test_link_expansion_is_linear_and_split_handles_generators(self):
        p=Project(timeline=[TimelineItem(str(n),"","video_1",0,2,group_id=str(n//2)) for n in range(10000)])
        t=TimelineWidget(); t.set_project(p)
        with patch.object(p,"linked_items",side_effect=AssertionError("Quadratic scan")):
            start=time.monotonic(); ids=t.expanded(str(n) for n in range(0,10000,2)); self.assertEqual(len(ids),10000); self.assertLess(time.monotonic()-start,1)
            self.assertEqual(len(p.split_selection((str(n) for n in range(0,10,2)),1)),10)
    def test_decoder_cleanup_is_queued_and_unpublished_before_backend_stop(self):
        w=self.window(); t=w.transport; key=("retired",); player=Mock(); output=Mock(); sink=Mock(); t.decoders[key]=(player,output,sink); t.window.preview.frames[key]=QImage(2,2,QImage.Format_RGB32)
        with patch("kinetic_cut.transport.QMetaObject.invokeMethod") as invoke:
            t.retire_decoder(key)
            self.assertNotIn(key,t.decoders); self.assertNotIn(key,w.preview.frames)
            player.stop.assert_not_called(); output.setMuted.assert_called_once_with(True)
            self.assertEqual([call.args[1] for call in invoke.call_args_list],["stop","deleteLater"])
            self.assertTrue(all(call.args[2]==Qt.QueuedConnection for call in invoke.call_args_list))
        t.frame(key,QImage(2,2,QImage.Format_RGB32)); self.assertNotIn(key,w.preview.frames)
    def test_mixed_marquee_retains_captions_and_keyboard_removes_both(self):
        w=self.window(); p=self.project(); w.set_project(p); self.app.processEvents(); t=w.timeline
        first=QPoint(round(t.x_for_time(4)),round(t.section_rect("subtitle_1").top()+12))
        last=QPoint(round(t.x_for_time(.1)),round(t.section_rect("audio_1").bottom()-1))
        # Start in empty subtitle space to the right of its last caption.
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=first)
        event=QMouseEvent(QEvent.MouseMove,QPointF(last),QPointF(t.viewport().mapToGlobal(last)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier)
        QApplication.sendEvent(t.viewport(),event); QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=last)
        self.assertIn("c",t.selected_caption_ids); self.assertIn("v",t.selected_ids)
        t.setFocus(); QTest.keyClick(t,Qt.Key_Backspace)
        self.assertFalse(w.project.captions); self.assertNotIn("v",[i.id for i in w.project.timeline])
    def test_frame_sampling_is_bounded_and_shutdown_rejects_late_results(self):
        w=self.window(); t=w.transport; key=("live",); player=Mock(); output=Mock(); sink=Mock(); sink._frame_stamp=None
        frame=Mock(); frame.isValid.return_value=True; frame.startTime.return_value=100; frame.endTime.return_value=200
        pixels=QImage(2,2,QImage.Format_RGB32); pixels.fill(Qt.red); frame.toImage.return_value=pixels; sink.videoFrame.return_value=frame
        t.decoders[key]=(player,output,sink); t.poll_frames(); t.poll_frames(); frame.toImage.assert_called_once()
        pixels.fill(Qt.blue); self.assertEqual(w.preview.frames[key].pixelColor(0,0).name(),"#ff0000")
        with patch("kinetic_cut.transport.QMetaObject.invokeMethod"):t.shutdown()
        with patch.object(t,"sync") as sync:t.audio_ready("late"); sync.assert_not_called()
        self.assertFalse(t.frame_timer.isActive()); self.assertFalse(t.decoders)
    def test_deliver_does_not_delete_or_cut(self):
        from kinetic_cut.workspace import set_page
        w=self.window(); w.set_project(self.project()); w.timeline.select_ids({"v","t"},"v"); before=w.project.to_dict(); set_page(w,1)
        w.delete_selected(True); w.timeline_clipboard("cut",True); self.assertEqual(w.project.to_dict(),before)
