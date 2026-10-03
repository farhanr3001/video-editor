import copy,unittest
from PySide6.QtCore import QPoint,QPointF,Qt,QEvent
from PySide6.QtTest import QTest
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.model import Project,TimelineItem,MediaItem,Caption
from kinetic_cut.timeline_gestures import roll,roll_snapshots,roll_pair


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance(); self.t=TimelineWidget(); self.t.resize(900,370); self.t.show(); self.t.linked_selection=False
        p=Project(); p.playhead=12
        for _ in range(9):p.add_track('video')
        for _ in range(5):p.add_track('audio')
        p.captions=[Caption('caption',1,3,'Test')]
        p.timeline=[TimelineItem('clip','','video_1',1,2,role='title',title_text='Test')]
        self.t.set_project(p); self.app.processEvents()
    def tearDown(self):self.t.close(); self.t.deleteLater(); self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
    def drag(self,start,end,modifiers=Qt.NoModifier):
        QTest.mousePress(self.t.viewport(),Qt.LeftButton,modifiers,start); QTest.mouseMove(self.t.viewport(),end)
    def test_video_alt_drag_scrolls_to_top_without_entering_subtitles(self):
        t=self.t; start=t.visible_item_rect(t.project.timeline[0]).center().toPoint(); end=QPoint(start.x()+35,round(t._sections()['subtitle'].center().y()))
        self.drag(start,end,Qt.AltModifier)
        for _ in range(100):t.clip_scroll.tick()
        self.assertEqual(t.video_scroll.value(),t.video_scroll.maximum()); self.assertEqual(t.subtitle_scroll.value(),0)
        self.assertTrue(t.move_preview); self.assertTrue(all(i.track in t.project.video_tracks for i in t.move_preview))
        QTest.mouseRelease(t.viewport(),Qt.LeftButton,Qt.AltModifier,end); self.assertEqual(len(t.project.timeline),2); self.assertFalse(t.clip_scroll.timer.isActive())
    def test_video_drag_over_audio_scrolls_down_video_only(self):
        t=self.t; t.project.timeline[0].track=t.project.video_tracks[-1]; t.video_scroll.setValue(t.video_scroll.maximum()); self.app.processEvents()
        start=t.visible_item_rect(t.project.timeline[0]).center().toPoint(); end=QPoint(start.x()+35,round(t._sections()['audio'].center().y())); self.drag(start,end)
        for _ in range(100):t.clip_scroll.tick()
        self.assertEqual(t.video_scroll.value(),0); self.assertEqual(t.audio_scroll.value(),0); self.assertEqual(t.move_preview[0].track,'video_1')
        QTest.keyClick(t.viewport(),Qt.Key_Escape); self.assertFalse(t.clip_scroll.timer.isActive())
    def test_middle_pan_owns_section_and_does_not_change_project(self):
        t=self.t; before=copy.deepcopy(t.project); t.horizontalScrollBar().setRange(0,1000); t.horizontalScrollBar().setValue(400)
        pos=QPoint(450,round(t._sections()['video'].center().y())); end=pos+QPoint(-50,40)
        QTest.mousePress(t.viewport(),Qt.MiddleButton,pos=pos); QTest.mouseMove(t.viewport(),end)
        self.assertEqual(t.drag_mode,'pan'); self.assertEqual(t.video_scroll.value(),40); self.assertEqual(t.audio_scroll.value(),0); self.assertEqual(t.horizontalScrollBar().value(),450)
        QTest.mouseRelease(t.viewport(),Qt.MiddleButton,pos=end); self.assertEqual(t.drag_mode,''); self.assertEqual(t.project.to_dict(),before.to_dict())
    def test_shift_wheel_changes_only_pointed_section_height(self):
        t=self.t; names={'video':'video_1','audio':'audio_1','subtitle':'subtitle_1'}
        for section in names:
            before={name:t._track_height(track) for name,track in names.items()}; zoom=t.pixels_per_second
            pos=t._sections()[section].center()
            event=QWheelEvent(pos,pos,QPoint(),QPoint(0,120),Qt.NoButton,Qt.ShiftModifier,Qt.NoScrollPhase,False)
            QApplication.sendEvent(t.viewport(),event)
            for name,track in names.items():self.assertEqual(t._track_height(track),before[name]+(8 if name==section else 0))
            self.assertEqual(t.pixels_per_second,zoom)
        # Section dividers keep their existing role and do not resize rows.
        before={name:t._track_height(track) for name,track in names.items()}
        pos=t._av_divider_rect().center().toPoint(); self.drag(pos,pos+QPoint(0,12)); QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=pos+QPoint(0,12))
        self.assertEqual(before,{name:t._track_height(track) for name,track in names.items()})
    def test_stationary_horizontal_drag_keeps_content_anchor(self):
        t=self.t; start=t.visible_item_rect(t.project.timeline[0]).center().toPoint(); end=QPoint(t.viewport().width()-2,start.y()); self.drag(start,end)
        first=t.move_preview[0].start
        for _ in range(8):t.clip_scroll.tick()
        self.assertGreater(t.horizontalScrollBar().value(),0); self.assertGreater(t.move_preview[0].start,first)
    def test_audio_drag_scrolls_audio_without_moving_video_scroll(self):
        t=self.t; t.project.timeline[0].track='audio_1'; self.app.processEvents()
        start=t.visible_item_rect(t.project.timeline[0]).center().toPoint(); end=QPoint(start.x()+30,t.viewport().height()-1); self.drag(start,end)
        for _ in range(60):t.clip_scroll.tick()
        self.assertEqual(t.audio_scroll.value(),t.audio_scroll.maximum()); self.assertEqual(t.video_scroll.value(),0)
        self.assertTrue(all(i.track in t.project.audio_tracks for i in t.move_preview)); t.cancel_drag()
    def test_caption_drag_scrolls_only_subtitle_section(self):
        t=self.t; t.subtitle_extent=30; t._range(); start=t.visible_caption_rect(t.project.captions[0]).center().toPoint(); end=QPoint(start.x()+30,round(t._sections()['video'].center().y()))
        self.drag(start,end)
        for _ in range(20):t.clip_scroll.tick()
        self.assertEqual(t.subtitle_scroll.value(),t.subtitle_scroll.maximum()); self.assertEqual(t.video_scroll.value(),0); self.assertEqual(t.drag_mode,'caption_move')
        t.cancel_drag(); self.assertEqual(t.project.captions[0].start,1)
    def pair(self):
        t=self.t; p=Project(media=[MediaItem('m','unused.mp4','video','clip',30,100,100,30,True)])
        p.timeline=[TimelineItem('l','m','video_1',0,5,0,link_id='left'),TimelineItem('r','m','video_1',5,5,5,link_id='right'),TimelineItem('al','m','audio_1',0,5,0,link_id='left'),TimelineItem('ar','m','audio_1',5,5,5,link_id='right')]
        t.set_project(p); t.linked_selection=True; self.app.processEvents(); return p
    def test_roll_updates_both_linked_sides_and_escape_restores(self):
        p=self.pair(); t=self.t; before=copy.deepcopy(p.timeline); r=t.item_rect(p.timeline[0]); pos=QPoint(round(t.x_for_time(5)),round(r.center().y()))
        self.assertIsNotNone(roll_pair(t,QPointF(pos))); self.drag(pos,pos+QPoint(20,0)); self.assertEqual(t.drag_mode,'roll')
        self.assertGreater(p.timeline[0].duration,5); self.assertEqual(p.timeline[0].duration,p.timeline[2].duration); self.assertEqual(p.timeline[1].start,p.timeline[3].start); self.assertAlmostEqual(p.timeline[1].start+p.timeline[1].duration,10)
        QTest.keyClick(t.viewport(),Qt.Key_Escape); self.assertEqual(p.timeline,before)
    def test_roll_source_handles_and_side_hit_zones(self):
        p=self.pair(); t=self.t; left,right=p.timeline[:2]; members=roll_snapshots(p,left,right,True)
        roll(p,*members,99); self.assertAlmostEqual(right.duration,.05); self.assertAlmostEqual(left.duration,9.95)
        roll(p,*members,-99); self.assertAlmostEqual(left.duration,.05); self.assertGreaterEqual(right.in_point,0)
        pos=QPointF(t.x_for_time(right.start)-4,t.item_rect(left).center().y()); self.assertIsNone(roll_pair(t,pos))
    def test_trim_visual_order_and_commit_keep_neighbour_source(self):
        p=self.pair(); t=self.t; left,right=p.timeline[:2]; pos=QPoint(round(t.x_for_time(5)-4),round(t.item_rect(left).center().y()))
        self.drag(pos,pos+QPoint(25,0)); self.assertEqual(t.drag_mode,'trim_right'); self.assertEqual(right.start,5)
        self.assertFalse(t.viewport().grab().isNull()); QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=pos+QPoint(25,0))
        right=p.item_by_id('r')
        self.assertAlmostEqual(right.start,left.start+left.duration); self.assertAlmostEqual(right.in_point,right.start)
    def test_trim_roll_and_fade_do_not_scroll_even_at_section_edges(self):
        p=self.pair(); t=self.t; t.audio_extent=30; t._range()
        for offset,mode in ((-4,'trim_right'),(0,'roll')):
            pos=QPoint(round(t.x_for_time(5)+offset),round(t.item_rect(p.timeline[0]).center().y()))
            self.drag(pos,QPoint(pos.x()+20,t.viewport().height()-1)); self.assertEqual(t.drag_mode,mode)
            before=(t.video_scroll.value(),t.audio_scroll.value(),t.horizontalScrollBar().value())
            for _ in range(30):t.clip_scroll.tick()
            wheel=QWheelEvent(QPointF(pos),QPointF(pos),QPoint(),QPoint(0,120),Qt.LeftButton,Qt.NoModifier,Qt.NoScrollPhase,False)
            QApplication.sendEvent(t.viewport(),wheel)
            self.assertEqual(before,(t.video_scroll.value(),t.audio_scroll.value(),t.horizontalScrollBar().value())); self.assertFalse(t.clip_scroll.timer.isActive()); t.cancel_drag()
        pos=QPoint(round(t.x_for_time(5)-5),round(t.item_rect(p.timeline[0]).top()+4))
        self.drag(pos,QPoint(pos.x()-20,t.viewport().height()-1)); self.assertEqual(t.drag_mode,'fade_out')
        before=(t.video_scroll.value(),t.audio_scroll.value(),t.horizontalScrollBar().value())
        for _ in range(30):t.clip_scroll.tick()
        self.assertEqual(before,(t.video_scroll.value(),t.audio_scroll.value(),t.horizontalScrollBar().value())); t.cancel_drag()
    def test_drag_and_alt_drag_can_create_top_video_lane_without_spare_space(self):
        for modifiers in (Qt.NoModifier,Qt.AltModifier):
            t=self.t; t.video_scroll.setValue(t.video_scroll.maximum()); t.project.timeline[0].track=t.project.video_tracks[-1]
            start=t.visible_item_rect(t.project.timeline[0]).center().toPoint(); end=QPoint(start.x()+30,round(t._sections()['video'].top()+3)); count=len(t.project.video_tracks)
            self.drag(start,end,modifiers); self.assertEqual(t.provisional_track,'__new_video')
            QTest.mouseRelease(t.viewport(),Qt.LeftButton,modifiers,end); self.assertEqual(len(t.project.video_tracks),count+1)
