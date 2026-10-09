import copy,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF,QSize,QEvent,QEventLoop,QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QListWidget,QListWidgetItem
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.workspace import BinMediaList
from kinetic_cut.model import Project,TimelineItem,Caption


class SelectionScrollTests(unittest.TestCase):
    def setUp(self):self.widgets=[]; self.app=QApplication.instance()
    def tearDown(self):
        for widget in self.widgets:widget.close(); widget.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
    def wait(self,ms=100):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def timeline(self):
        t=TimelineWidget(); self.widgets.append(t); t.resize(900,370); t.show(); p=Project(); p.playhead=9
        for _ in range(9):p.add_track('video')
        for _ in range(5):p.add_track('audio')
        p.timeline=[TimelineItem(track,'',track,1,2,link_id='') for track in p.video_tracks+p.audio_tracks]
        t.set_project(p); t.linked_selection=False; self.app.processEvents(); return t
    def wheel(self,view,point,delta):
        event=QWheelEvent(QPointF(point),QPointF(point),QPoint(),QPoint(0,delta),Qt.LeftButton,Qt.NoModifier,Qt.ScrollUpdate,False)
        self.app.sendEvent(view.viewport(),event)

    def test_marquee_lane_geometry_is_reused_and_stationary_center_does_no_work(self):
        t=self.timeline(); section=t._sections()['video']
        start=QPointF(t.x_for_time(5),section.center().y())
        t.drag_mode='marquee'; t.marquee_initial=set(); t.marquee_caption_initial=set()
        t.marquee_controller.begin(start)
        for n in range(100):t.project.timeline.append(TimelineItem('extra'+str(n),'','video_1',1,2,link_id=''))
        with patch.object(t,'track_rect',wraps=t.track_rect) as geometry:
            t.marquee_controller.move(start-QPointF(15,1))
            self.assertLessEqual(geometry.call_count,len(t.tracks()))
        with patch.object(t.marquee_controller,'update') as update:
            t.marquee_controller.scroll(); update.assert_not_called()
    def test_timeline_video_wheel_keeps_offscreen_selection_anchored(self):
        t=self.timeline(); original=copy.deepcopy(t.project.timeline); rect=t._sections()['video']
        start=QPoint(round(t.x_for_time(4)),round(rect.bottom()-3)); end=QPoint(round(t.x_for_time(.5)),round(rect.top()+3))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end)
        self.assertIn('video_1',t.selected_ids); count=len(t.selected_ids)
        # Fine layer scrolling now needs several notches to cross another lane.
        for _ in range(5):self.wheel(t,end,120)
        self.assertGreater(t.video_scroll.value(),0); self.assertGreater(len(t.selected_ids),count); self.assertIn('video_1',t.selected_ids)
        t.video_scroll.setValue(t.video_scroll.maximum()); self.assertEqual(t.selected_ids,set(t.project.video_tracks)); self.assertFalse(set(t.project.audio_tracks)&t.selected_ids)
        QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=end); self.assertFalse(t.marquee_controller.timer.isActive()); self.assertEqual(t.project.timeline,original)
    def test_timeline_stationary_edge_scrolls_both_video_directions(self):
        t=self.timeline(); rect=t._sections()['video']; start=QPoint(round(t.x_for_time(4)),round(rect.bottom()-3)); end=QPoint(round(t.x_for_time(.5)),round(rect.top()+2))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end); self.wait(180); self.assertGreater(t.video_scroll.value(),0)
        for _ in range(80):t.marquee_controller.scroll()
        self.assertEqual(t.selected_ids,set(t.project.video_tracks)); QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=end)
        start=QPoint(round(t.x_for_time(4)),round(rect.top()+3)); end=QPoint(round(t.x_for_time(.5)),round(rect.bottom()-2))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end)
        for _ in range(80):t.marquee_controller.scroll()
        self.assertEqual(t.video_scroll.value(),0); self.assertEqual(t.selected_ids,set(t.project.video_tracks))
        QTest.keyClick(t.viewport(),Qt.Key_Escape); self.assertFalse(t.marquee_controller.timer.isActive())
    def test_timeline_audio_wheel_and_horizontal_scroll_keep_anchor(self):
        t=self.timeline(); rect=t._sections()['audio']; start=QPoint(round(t.x_for_time(4)),round(rect.top()+3)); end=QPoint(round(t.x_for_time(.5)),round(rect.bottom()-3))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end); self.wheel(t,end,-120); self.assertGreater(t.audio_scroll.value(),0)
        t.audio_scroll.setValue(t.audio_scroll.maximum()); self.assertEqual(t.selected_ids,set(t.project.audio_tracks))
        anchor=QPointF(t.marquee_controller.anchor); t.horizontalScrollBar().setValue(40); self.assertEqual(t.marquee_controller.anchor,anchor)
        t.set_read_only(True); self.assertFalse(t.marquee_controller.timer.isActive())
    def cross_section_timeline(self):
        t=self.timeline(); t.project.captions=[Caption('caption',1,3,'Two words')]; t.subtitle_extent=30; t._range(); self.app.processEvents(); return t
    def test_one_continuous_rectangle_crosses_section_dividers(self):
        t=self.cross_section_timeline(); t.video_scroll.setValue(t.video_scroll.maximum()); sections=t._sections()
        start=QPoint(round(t.x_for_time(4)),round(sections['video'].top()+30)); end=QPoint(round(t.x_for_time(.5)),round(sections['subtitle'].top()+5))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end)
        rects=t.marquee_controller.rects(); self.assertEqual(len(rects),1)
        divider=t._subtitle_divider_rect(); self.assertTrue(rects[0].contains(QPointF((start.x()+end.x())/2,divider.center().y())))
        self.assertEqual(t.selected_caption_ids,{'caption'})
        point=QPoint(round((start.x()+end.x())/2),round(divider.top()+1)); shown=t.viewport().grab().toImage().pixelColor(point)
        marquee=t.marquee; t.marquee=None; baseline=t.viewport().grab().toImage().pixelColor(point); t.marquee=marquee
        self.assertGreater(shown.blue(),baseline.blue()+15) # divider cannot repaint over the selection
    def test_downward_crossing_scrolls_each_section_before_next(self):
        t=self.cross_section_timeline(); original=copy.deepcopy(t.project.timeline); t.video_scroll.setValue(t.video_scroll.maximum()); sections=t._sections()
        t.subtitle_scroll.setValue(t.subtitle_scroll.maximum()) # top of bottom-origin subtitle content
        start=QPoint(round(t.x_for_time(4)),round(sections['subtitle'].top()+3)); end=QPoint(round(t.x_for_time(.5)),round(sections['audio'].bottom()-2))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end)
        self.assertEqual(t.marquee_controller.active_section,'subtitle'); self.assertFalse(set(t.project.audio_tracks)&t.selected_ids)
        for _ in range(200):
            if t.marquee_controller.active_section=='video':break
            t.marquee_controller.scroll()
        self.assertEqual(t.subtitle_scroll.value(),0); self.assertEqual(t.marquee_controller.active_section,'video')
        self.assertFalse(set(t.project.audio_tracks)&t.selected_ids)
        for _ in range(200):
            if t.marquee_controller.active_section=='audio':break
            t.marquee_controller.scroll()
        self.assertEqual(t.video_scroll.value(),0); self.assertEqual(t.marquee_controller.active_section,'audio')
        for _ in range(100):t.marquee_controller.scroll()
        self.assertEqual(t.selected_ids,set(t.project.video_tracks+t.project.audio_tracks)); self.assertEqual(t.selected_caption_ids,{'caption'})
        self.assertEqual(len(t.marquee_controller.rects()),1); self.assertEqual(t.project.timeline,original)
        QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=end); self.assertFalse(t.marquee_controller.timer.isActive())
    def test_upward_crossing_scrolls_audio_then_video_then_subtitles(self):
        t=self.cross_section_timeline(); sections=t._sections(); t.subtitle_scroll.setValue(0); t.audio_scroll.setValue(t.audio_scroll.maximum())
        start=QPoint(round(t.x_for_time(4)),round(sections['audio'].bottom()-3)); end=QPoint(round(t.x_for_time(.5)),round(sections['subtitle'].top()+2))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end)
        self.assertEqual(t.marquee_controller.active_section,'audio'); self.assertFalse(t.selected_caption_ids)
        for _ in range(200):
            if t.marquee_controller.active_section=='video':break
            t.marquee_controller.scroll()
        self.assertEqual(t.audio_scroll.value(),0); self.assertEqual(t.marquee_controller.active_section,'video'); self.assertFalse(t.selected_caption_ids)
        for _ in range(200):
            if t.marquee_controller.active_section=='subtitle':break
            t.marquee_controller.scroll()
        self.assertEqual(t.video_scroll.value(),t.video_scroll.maximum()); self.assertEqual(t.marquee_controller.active_section,'subtitle')
        for _ in range(100):t.marquee_controller.scroll()
        self.assertEqual(t.subtitle_scroll.value(),t.subtitle_scroll.maximum()); self.assertEqual(t.selected_ids,set(t.project.video_tracks+t.project.audio_tracks)); self.assertEqual(t.selected_caption_ids,{'caption'})
    def test_wheel_beyond_video_boundary_scrolls_video_before_audio(self):
        t=self.cross_section_timeline(); sections=t._sections(); t.video_scroll.setValue(t.video_scroll.maximum()); t.subtitle_scroll.setValue(0)
        start=QPoint(round(t.x_for_time(4)),round(sections['subtitle'].center().y())); end=QPoint(round(t.x_for_time(.5)),round(sections['audio'].center().y()))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end); before=t.video_scroll.value()
        self.wheel(t,end,-120); self.assertLess(t.video_scroll.value(),before); self.assertEqual(t.audio_scroll.value(),0)
        self.assertFalse(set(t.project.audio_tracks)&t.selected_ids)
        t.video_scroll.setValue(0); self.wheel(t,end,-120); self.assertGreater(t.audio_scroll.value(),0)
    def test_reversing_drag_does_not_keep_scrolling_previous_direction(self):
        t=self.cross_section_timeline(); sections=t._sections(); t.video_scroll.setValue(t.video_scroll.maximum()); t.subtitle_scroll.setValue(0)
        start=QPoint(round(t.x_for_time(4)),round(sections['subtitle'].center().y())); end=QPoint(round(t.x_for_time(.5)),round(sections['audio'].center().y()))
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(t.viewport(),end)
        for _ in range(4):t.marquee_controller.scroll()
        before=t.video_scroll.value(); reverse=QPoint(end.x(),round(sections['subtitle'].top()+3)); QTest.mouseMove(t.viewport(),reverse); t.marquee_controller.scroll()
        self.assertGreater(t.video_scroll.value(),before)
        QTest.keyClick(t.viewport(),Qt.Key_Escape); self.assertFalse(t.marquee_controller.timer.isActive()); t.marquee_controller.scroll(); self.assertEqual(t.drag_mode,'')
    def grid(self):
        grid=BinMediaList(None); self.widgets.append(grid); grid.setViewMode(QListWidget.IconMode); grid.setMovement(QListWidget.Static); grid.setGridSize(QSize(100,90)); grid.setWrapping(True); grid.resize(320,260)
        for n in range(60):grid.addItem(QListWidgetItem('Media '+str(n)))
        grid.show(); self.app.processEvents(); return grid
    def test_pool_wheel_and_edge_scroll_extend_selection_past_visible_items(self):
        grid=self.grid(); start=QPoint(298,3); end=QPoint(5,grid.viewport().height()-3)
        self.assertIsNone(grid.itemAt(start)); QTest.mousePress(grid.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(grid.viewport(),end)
        initial={grid.row(item) for item in grid.selectedItems()}; self.assertTrue(initial)
        self.wheel(grid,end,-120); self.assertGreater(grid.verticalScrollBar().value(),0); self.assertTrue(initial.issubset({grid.row(item) for item in grid.selectedItems()}))
        before=grid.verticalScrollBar().value(); self.wait(180); self.assertGreater(grid.verticalScrollBar().value(),before)
        grid.verticalScrollBar().setValue(grid.verticalScrollBar().maximum()); self.assertEqual(len(grid.selectedItems()),60)
        QTest.mouseRelease(grid.viewport(),Qt.LeftButton,pos=end); before=grid.verticalScrollBar().value(); self.wait(); self.assertEqual(grid.verticalScrollBar().value(),before); self.assertFalse(grid.marquee_controller.timer.isActive())
    def test_pool_upward_selection_clear_and_hide_stop_scrolling(self):
        grid=self.grid(); grid.verticalScrollBar().setValue(grid.verticalScrollBar().maximum()); start=QPoint(298,grid.viewport().height()-3); end=QPoint(5,2)
        self.assertIsNone(grid.itemAt(start)); QTest.mousePress(grid.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(grid.viewport(),end)
        before=grid.verticalScrollBar().value(); self.wait(180); self.assertLess(grid.verticalScrollBar().value(),before)
        grid.verticalScrollBar().setValue(0); self.assertEqual(len(grid.selectedItems()),60)
        grid.clear(); self.assertIsNone(grid.marquee_controller.anchor); self.assertFalse(grid.marquee_controller.timer.isActive())
