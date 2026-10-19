"""Input and selection-only GPU regressions reported after the refactor."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtCore import Qt,QEvent,QPointF,QPoint,QRectF
from PySide6.QtGui import QMouseEvent,QContextMenuEvent
from kinetic_cut.quick_surface import Surface
from kinetic_cut.gpu_preview import GpuPreview,shader_supported
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.model import Project,TimelineItem,Caption


class GpuInteractionRegressions(unittest.TestCase):
    def test_small_media_and_captions_have_a_matching_body_cursor_and_click(self):
        for track,role in [('video_1','facecam'),('audio_1','source_audio'),('video_1','title'),('video_1','graphic'),('subtitle_1','caption')]:
            for pixels in (5,10,16,23,24,80):
                with self.subTest(track=track,role=role,pixels=pixels):
                    t=TimelineWidget();t.resize(900,420);t.pixels_per_second=20
                    item=TimelineItem('small','',track,2,pixels/20,role=role)
                    cap=Caption('small',2,2+pixels/20,'Small')
                    p=Project(captions=[cap]) if role=='caption' else Project(timeline=[item])
                    t.set_project(p);t.linked_selection=False
                    try:
                        rect=t.caption_rect(cap) if role=='caption' else t.item_rect(item)
                        point=rect.center()
                        t.viewport().setCursor(Qt.SizeHorCursor)
                        t.mouseMoveEvent(QMouseEvent(QEvent.MouseMove,point,point,Qt.NoButton,Qt.NoButton,Qt.NoModifier))
                        self.assertEqual(t.viewport().cursor().shape(),Qt.ArrowCursor)
                        t.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress,point,point,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
                        self.assertEqual(t.drag_mode,'caption_move' if role=='caption' else 'move')
                        self.assertEqual(t.viewport().cursor().shape(),Qt.ArrowCursor)
                        t.cancel_drag()
                        if pixels>=24:
                            edge=QPointF(rect.left()+2,rect.center().y())
                            t.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress,edge,edge,Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
                            self.assertEqual(t.drag_mode,'caption_left' if role=='caption' else 'trim_left')
                    finally:t.cancel_drag();t.close();t.deleteLater()

    def test_tiny_adjacent_media_centers_do_not_become_a_rolling_cut(self):
        from kinetic_cut.timeline_gestures import roll_pair
        t=TimelineWidget();t.resize(900,420);t.pixels_per_second=20
        p=Project(timeline=[TimelineItem('a','','video_1',2,.15),TimelineItem('b','','video_1',2.15,.15)])
        t.set_project(p)
        try:
            for item in p.timeline:self.assertIsNone(roll_pair(t,t.item_rect(item).center()))
        finally:t.close();t.deleteLater()

    def test_marquee_defers_inspector_rebuild_until_release(self):
        from kinetic_cut.ui import MainWindow
        p=Project(timeline=[TimelineItem('a','','video_1',0,3)])
        t=TimelineWidget();t.resize(900,420);t.set_project(p)
        window=SimpleNamespace(project=p,timeline=t,inspector=Mock(),preview=Mock(),update_keyframe_button=Mock())
        try:
            t.drag_mode='marquee';t.selected_ids={'a'};t.selected_id='a'
            t.itemSelected.connect(lambda identifier:MainWindow.select_item(window,identifier))
            MainWindow.select_item(window,'a');window.inspector.select.assert_not_called()
            self.assertEqual(t.selected_ids,{'a'});window.preview.select_item.assert_called_with('a')
            event=QMouseEvent(QEvent.MouseButtonRelease,QPointF(500,150),QPointF(500,150),Qt.LeftButton,Qt.NoButton,Qt.NoModifier)
            t.mouseReleaseEvent(event)
            window.inspector.select.assert_called_once_with('a')
            self.assertEqual(t.drag_mode,'')
        finally:t.close();t.deleteLater()

    def test_right_release_opens_original_menu_once_with_viewport_coordinates(self):
        owner=Mock();surface=SimpleNamespace(closed=False,viewport=Mock(),owner=owner,
            view=Mock(),container=Mock(),offset=QPointF(30,20))
        event=QMouseEvent(QEvent.MouseButtonRelease,QPointF(50,60),QPointF(500,600),
                          Qt.RightButton,Qt.NoButton,Qt.ControlModifier)
        self.assertTrue(Surface.eventFilter(surface,surface.view,event))
        context=owner.contextMenuEvent.call_args.args[0]
        self.assertEqual(context.pos(),QPoint(80,80));self.assertEqual(context.globalPos(),QPoint(500,600))
        self.assertEqual(context.modifiers(),Qt.ControlModifier)
        Surface.eventFilter(surface,surface.container,QContextMenuEvent(QContextMenuEvent.Mouse,QPoint(50,60),QPoint(500,600)))
        owner.contextMenuEvent.assert_called_once()
        Surface.eventFilter(surface,surface.view,QContextMenuEvent(QContextMenuEvent.Keyboard,QPoint(10,20),QPoint(300,400)))
        self.assertEqual(owner.contextMenuEvent.call_count,2)
        self.assertEqual(owner.contextMenuEvent.call_args.args[0].pos(),QPoint(40,40))

    def test_sharpen_never_changes_source_decoder_eligibility_at_zero(self):
        p=Project(timeline=[TimelineItem('a','source','video_1',0,3),TimelineItem('b','source','video_2',0,3)])
        surface=SimpleNamespace(canvas=SimpleNamespace(project=p))
        for value in (0,.01,.8,2.,.01,0):
            p.timeline[0].sharpen=value
            self.assertTrue(shader_supported(p.timeline[0]))
            self.assertFalse(GpuPreview.cpu_media(surface,'source'))
        p.timeline[0].contrast=1.4
        self.assertTrue(GpuPreview.cpu_media(surface,'source'),'Unsupported operations retain exact compatibility')

    def test_marquee_movement_does_not_upload_a_viewport_texture(self):
        from kinetic_cut.gpu_timeline_controls import refresh
        t=TimelineWidget();t.resize(900,420);t.set_project(Project())
        surface=SimpleNamespace(timeline=t,images=Mock(),create=Mock(return_value=Mock()),view=t.viewport())
        try:
            t.drag_mode='marquee';t.marquee=QRectF(0,0,20,30)
            refresh(surface,t.viewport().rect());count=surface.images.put.call_count
            for size in range(30,100):
                t.marquee=QRectF(0,0,size,30);refresh(surface,t.viewport().rect())
            self.assertEqual(surface.images.put.call_count,count)
        finally:t.close();t.deleteLater()

    def test_marquee_queries_only_time_candidates_and_clears_departed_captions(self):
        t=TimelineWidget();t.resize(900,420)
        p=Project(timeline=[TimelineItem(str(i),'','video_1',i*4,1,link_id='') for i in range(2000)],
                  captions=[Caption('caption',1,2,'A caption')])
        t.set_project(p);t.linked_selection=False
        t.drag_mode='marquee';t.marquee_initial=set();t.marquee_caption_initial=set()
        band=t.marquee_controller;lane=t.track_rect('video_1');start=QPointF(t.x_for_time(3),lane.center().y())
        try:
            band.begin(start)
            with patch.object(t,'item_rect',wraps=t.item_rect) as geometry:
                band.move(QPointF(t.x_for_time(.5),lane.center().y()+8))
                self.assertLess(geometry.call_count,10)
            self.assertEqual(t.selected_ids,{'0'})
            self.assertEqual(p.runtime_index.trees['timeline'].records.__len__(),2000)
            # Removing a caption from the box still damages its former pixels.
            band.caption_items={'caption':p.captions[0]};t.selected_caption_ids={'caption'}
            with patch.object(t,'caption_rect',wraps=t.caption_rect) as geometry:
                band.move(start+QPointF(8,5))
                self.assertTrue(any(c.args[0].id=='caption' for c in geometry.call_args_list))
        finally:band.stop();t.close();t.deleteLater()
