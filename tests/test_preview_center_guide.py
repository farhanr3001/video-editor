import unittest
from PySide6.QtCore import Qt,QEvent,QPointF,QRectF
from PySide6.QtGui import QImage,QPainter,QColor,QPolygonF
import test_preview_handle_feedback as fixture
from kinetic_cut.model import Project,MediaItem,TimelineItem
from kinetic_cut.graphics import default_graphic_data


class PreviewCenterGuideTests(unittest.TestCase):
    setUp=fixture.PreviewHandleFeedbackTests.setUp
    tearDown=fixture.PreviewHandleFeedbackTests.tearDown
    event=fixture.PreviewHandleFeedbackTests.event
    title=fixture.PreviewHandleFeedbackTests.title

    def guide_pixels(self):
        view=self.w.preview;image=QImage(view.size(),QImage.Format_RGB32);image.fill(Qt.black)
        painter=QPainter(image);view._draw_center_guide(painter);painter.end()
        frame=view.composition_rect();y=int(frame.top()+15);x=int(frame.center().x())
        return any(image.pixelColor(xx,y)==QColor('#3d8cff') for xx in range(x-1,x+2))

    def test_titles_snap_visible_center_y_free_and_release_single_undo(self):
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            self.w.apply_theme(theme,save=False)
            for name in ('Text','Headline'):
                item=self.title(name);item.title_style.position_x=.32;self.w.model_changed();view=self.w.preview;view.grab()
                rect=view.text_rects['title',item.id];frame=view.composition_rect();origin=rect.center()
                # Integer mouse origins are the existing drag contract.
                end=QPointF(origin.toPoint())+QPointF(frame.center().x()-rect.center().x()+3,30)
                history=self.w._history_index;before_y=item.title_style.position_y
                self.assertFalse(self.guide_pixels())
                self.event(QEvent.MouseButtonPress,origin,Qt.LeftButton,Qt.LeftButton)
                self.assertEqual(view.drag_mode,'text_move')
                self.event(QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton)
                self.assertTrue(self.guide_pixels());view.grab()
                self.assertAlmostEqual(view.text_rects['title',item.id].center().x(),frame.center().x(),delta=1)
                self.assertAlmostEqual(item.title_style.position_y,before_y+30/frame.height())
                if getattr(self,'capture_dir',None):view.grab().save(str(self.capture_dir/f'{theme}-{name}-center.png'))
                self.event(QEvent.MouseButtonRelease,end,Qt.LeftButton)
                self.assertFalse(self.guide_pixels());self.assertEqual(self.w._history_index,history+1)
                self.w.undo();self.assertAlmostEqual(self.w.project.item_by_id(item.id).title_style.position_x,.32)

    def test_media_and_shapes_align_visible_bounds_with_anchor_rotation(self):
        for kind in ('media','Rectangle'):
            item=TimelineItem('g','m' if kind=='media' else '', 'video_1',0,5,
                role='normal' if kind=='media' else 'graphic',graphic_type='' if kind=='media' else kind,
                graphic_data={} if kind=='media' else default_graphic_data(kind))
            if kind!='media':item.graphic_data.update(width=1600,height=900)
            item.transform.x=.32;item.transform.scale=.5;item.transform.anchor_x=120;item.transform.rotation=17
            media=[MediaItem('m',self.image_path,'image','fixture',5,1920,1080)] if kind=='media' else []
            self.w.set_project(Project(media=media,timeline=[item]));self.w.timeline.select_ids({'g'},'g');self.app.processEvents()
            view=self.w.preview;view.grab();rect=view._visible_items()[0][2]
            bounds=QPolygonF(view._transform_geometry(item,rect)[1]).boundingRect();origin=bounds.center()+QPointF(bounds.width()*.22,bounds.height()*.22)
            frame=view.composition_rect();end=QPointF(origin.toPoint())+QPointF(frame.center().x()-bounds.center().x()+2,19)
            self.event(QEvent.MouseButtonPress,origin,Qt.LeftButton,Qt.LeftButton);self.assertEqual(view.drag_mode,'move')
            self.event(QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton);self.assertTrue(self.guide_pixels())
            rect=view._visible_items()[0][2];bounds=QPolygonF(view._transform_geometry(item,rect)[1]).boundingRect()
            self.assertAlmostEqual(bounds.center().x(),frame.center().x(),delta=.01)
            self.event(QEvent.MouseButtonRelease,end,Qt.LeftButton);self.assertFalse(self.guide_pixels())

    def test_small_snap_zone_pull_away_and_nonmove_controls(self):
        item=self.title('Headline');view=self.w.preview;frame=view.composition_rect()
        view._begin_center_drag(QRectF(frame.center().x()-30,50,60,20),.5)
        self.assertEqual(view._snap_drag_center(.5+4/frame.width()),.5)
        self.assertEqual(view._snap_drag_center(.5+7/frame.width()),.5)
        raw=.5+10/frame.width();self.assertEqual(view._snap_drag_center(raw),raw)
        self.assertFalse(view.center_guide_active)
        view.drag_origin=frame.center().toPoint();view.center_guide_active=True
        for mode in ('scale','title_scale','headline_scale','rotate','anchor'):
            view.drag_mode=mode;self.assertFalse(self.guide_pixels())
        view.drag_mode='text_move';self.assertTrue(self.guide_pixels())
        view.set_transform_controls_visible(False);self.assertFalse(self.guide_pixels())
        view.set_read_only(True);self.assertFalse(self.guide_pixels())
