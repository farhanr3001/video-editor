import copy,unittest,tempfile
from pathlib import Path
from PySide6.QtCore import Qt,QEvent,QPointF
from PySide6.QtGui import QMouseEvent,QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem
from kinetic_cut.graphics import GRAPHICS_CATALOG,default_graphic_data


class PreviewHandleFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance();self.w=MainWindow();self.w.resize(1480,900)
        self.w.show();self.w.autosave_timer.stop();self.app.processEvents()
        self.folder=tempfile.TemporaryDirectory();self.image_path=str(Path(self.folder.name)/'fixture.png')
        image=QImage(1920,1080,QImage.Format_RGB32);image.fill(Qt.gray);image.save(self.image_path)
    def tearDown(self):
        self.w.close();self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
        self.folder.cleanup()
    def event(self,kind,pos,button=Qt.NoButton,buttons=Qt.NoButton):
        view=self.w.preview
        self.app.sendEvent(view,QMouseEvent(kind,pos,view.mapToGlobal(pos.toPoint()),button,buttons,Qt.NoModifier))
    def title(self,name):
        self.w.set_project(Project());self.w.add_title_object(name);self.app.processEvents()
        return self.w.project.item_by_id(self.w.timeline.selected_id)
    def test_title_corners_arrow_and_only_dragged_corner_highlights(self):
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            self.w.apply_theme(theme,save=False)
            for name in ('Text','Headline'):
                item=self.title(name);view=self.w.preview;view.grab()
                rect=view.text_rects['title',item.id]
                for index,point in enumerate(view._handles(rect)):
                    with self.subTest(theme=theme,title=name,corner=index):
                        self.event(QEvent.MouseMove,QPointF(point));self.assertEqual(view.cursor().shape(),Qt.ArrowCursor)
                        self.event(QEvent.MouseButtonPress,QPointF(point),Qt.LeftButton,Qt.LeftButton)
                        self.assertEqual(view.drag_handle,index)
                        image=QImage(view.size(),QImage.Format_ARGB32);image.fill(Qt.black);painter=QPainter(image)
                        view._draw_text_box(painter,rect);painter.end()
                        for other,corner in enumerate(view._handles(rect)):
                            self.assertEqual(image.pixelColor(corner),QColor('#3d8cff' if other==index else '#f5f6fa'))
                        self.event(QEvent.MouseButtonRelease,QPointF(point),Qt.LeftButton)
                        self.assertIsNone(view.drag_handle)
    def test_all_graphic_and_media_corners_and_side_handles_use_arrow(self):
        for name in [*GRAPHICS_CATALOG,'media']:
            item=TimelineItem('g','m' if name=='media' else '','video_1',0,5,
                role='normal' if name=='media' else 'graphic',graphic_type='' if name=='media' else name,
                graphic_data={} if name=='media' else default_graphic_data(name))
            media=[MediaItem('m',self.image_path,'image','fixture',5,1920,1080)] if name=='media' else []
            self.w.set_project(Project(media=media,timeline=[item]));self.w.timeline.select_ids({'g'},'g');self.app.processEvents()
            view=self.w.preview
            if name=='media':
                image=QImage(1920,1080,QImage.Format_RGB32);image.fill(Qt.gray)
                view.frames={'fixture':image};view.active_frames={'g':'fixture'};view.set_frame(image)
            for rotation in (0,37):
                item.transform.rotation=rotation
                rect=view._visible_items()[0][2];geometry=view._transform_geometry(item,rect)
                for index,point in enumerate(geometry[1]):
                    with self.subTest(item=name,rotation=rotation,corner=index):
                        self.event(QEvent.MouseMove,point);self.assertEqual(view.cursor().shape(),Qt.ArrowCursor)
                        self.event(QEvent.MouseButtonPress,point,Qt.LeftButton,Qt.LeftButton)
                        self.assertEqual((view.drag_mode,view.drag_handle),('scale',index))
                        self.assertEqual(view.cursor().shape(),Qt.ArrowCursor)
                        image=QImage(200,200,QImage.Format_ARGB32);image.fill(Qt.black);painter=QPainter(image)
                        painter.translate(100-point.x(),100-point.y())
                        view._draw_transform_box(painter,item,rect);painter.end()
                        self.assertEqual(image.pixelColor(100,100),QColor('#3d8cff'))
                        self.event(QEvent.MouseButtonRelease,point,Qt.LeftButton)
                for point in geometry[2]:
                    self.event(QEvent.MouseMove,point);self.assertEqual(view.cursor().shape(),Qt.ArrowCursor)
    def test_text_resize_updates_character_size_and_single_undo(self):
        item=self.title('Text');view=self.w.preview;view.grab();before=copy.deepcopy(item.title_style);history=self.w._history_index
        rect=view.text_rects['title',item.id];origin=rect.topRight();end=rect.center()+(origin-rect.center())*1.4
        self.event(QEvent.MouseButtonPress,origin,Qt.LeftButton,Qt.LeftButton)
        self.event(QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton)
        self.event(QEvent.MouseButtonRelease,end,Qt.LeftButton)
        self.assertAlmostEqual(item.title_style.size,before.size*1.4,delta=.05)
        size=next(row for attr,row in self.w.inspector.style_bindings if attr=='size')
        self.assertAlmostEqual(size.spin.value(),item.title_style.size,delta=.5)
        view.grab();self.assertGreater(view.text_rects['title',item.id].width(),rect.width()*1.25)
        self.assertEqual((item.title_style.zoom_x,item.title_style.zoom_y),(before.zoom_x,before.zoom_y))
        self.assertEqual(self.w._history_index,history+1);self.w.undo()
        self.assertEqual(self.w.project.item_by_id(item.id).title_style.size,before.size)
        self.w.redo();self.assertAlmostEqual(self.w.project.item_by_id(item.id).title_style.size,before.size*1.4,delta=.05)
    def test_text_locked_hidden_and_range(self):
        item=self.title('Text');view=self.w.preview
        for locked,hidden in ((True,False),(False,True),(False,False)):
            self.w.project.track_states[item.track]={'locked':locked};view.transform_controls_visible=not hidden;view.grab()
            rect=view.text_rects['title',item.id];origin=rect.bottomRight();end=rect.center()+(origin-rect.center())*10
            before=item.title_style.size
            self.event(QEvent.MouseButtonPress,origin,Qt.LeftButton,Qt.LeftButton)
            self.event(QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton);self.event(QEvent.MouseButtonRelease,end,Qt.LeftButton)
            self.assertEqual(item.title_style.size,before if locked or hidden else 200)
    def test_multiple_text_titles_resize_inspector_targets(self):
        first=self.title('Text');self.w.add_title_object('Text');second=self.w.project.item_by_id(self.w.timeline.selected_id)
        self.w.timeline.select_ids({first.id,second.id},first.id);self.w.inspector.select(first.id);self.w.preview.select_item(first.id)
        view=self.w.preview;view.grab();rect=view.text_rects['title',first.id];origin=rect.bottomRight();end=rect.center()+(origin-rect.center())*1.2
        before=first.title_style.size
        self.event(QEvent.MouseButtonPress,origin,Qt.LeftButton,Qt.LeftButton);self.event(QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton);self.event(QEvent.MouseButtonRelease,end,Qt.LeftButton)
        self.assertAlmostEqual(first.title_style.size,before*1.2,delta=.05);self.assertEqual(first.title_style.size,second.title_style.size)
