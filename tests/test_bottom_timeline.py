import unittest
from PySide6.QtCore import QPoint,Qt,QEvent
from PySide6.QtTest import QTest
import test_timeline_workspace as workspace_tests


class BottomTimelineTests(workspace_tests.TimelineWorkspaceTests):
    # Inherit the existing layout/ownership regressions as neighboring checks.
    def test_bottom_row_order_scrub_and_normal_restore(self):
        w=self.w;self.enter();bottom=self.mode.bottom
        self.assertLess(bottom.body.y(),bottom.ruler.y())
        button_top=w.fullscreen_timeline.mapTo(w.timeline_panel,QPoint()).y()
        self.assertGreaterEqual(button_top,bottom.ruler.y()+bottom.ruler.height())
        self.assertEqual(w.timeline.y(),-w.timeline.RULER_HEIGHT-w.timeline.viewport().y())
        w.timeline.select_ids({'v'},'v');history=w._history_index
        start=QPoint(round(w.timeline.x_for_time(2))+bottom.ruler.offset(),10)
        end=QPoint(round(w.timeline.x_for_time(5))+bottom.ruler.offset(),10)
        QTest.mousePress(bottom.ruler,Qt.LeftButton,pos=start);self.assertEqual(w.timeline.drag_mode,'playhead')
        QTest.mouseMove(bottom.ruler,end);QTest.mouseRelease(bottom.ruler,Qt.LeftButton,pos=end)
        self.assertAlmostEqual(w.project.playhead,5,delta=1/w.timeline.pixels_per_second)
        self.assertEqual(w.timeline.selected_ids,{'v'});self.assertEqual(w._history_index,history)
        self.mode.set_active(False);self.wait()
        self.assertIs(w.timeline.parentWidget(),w.timeline_panel);self.assertGreater(w.timeline.y(),0)
        self.assertFalse(bottom.ruler.isVisible());self.assertLess(w.fullscreen_timeline.y(),w.timeline.y())
    def test_body_hit_coordinates_and_scroll_still_use_original_timeline(self):
        w=self.w;self.enter();item=w.project.timeline[0];point=w.timeline.visible_item_rect(item).center().toPoint()
        self.assertEqual(w.timeline._fast_hit_at(point)[0].id,item.id)
        body=self.mode.bottom.body;physical=w.timeline.viewport().mapTo(body,point)
        self.assertTrue(body.rect().contains(physical));self.assertGreaterEqual(physical.y(),0)
        bar=w.timeline.horizontalScrollBar();bar.setValue(100);self.wait()
        self.assertEqual(self.mode.bottom.ruler.offset(),w.timeline.viewport().x())


if __name__=='__main__':unittest.main()
