import copy,tempfile,unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project
from kinetic_cut.headline import paths
from kinetic_cut.exporter import write_ass


class HeadlineControlsTests(unittest.TestCase):
    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.autosave_timer.stop()
        self.w.add_title_object('Headline');self.id=self.w.timeline.selected_id
        self.app=QApplication.instance();self.app.processEvents()
    def tearDown(self):
        self.w.close();self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
    def item(self):return self.w.project.item_by_id(self.id)
    def drag(self,factor=1.4):
        view=self.w.preview;view.grab()
        rect=view.text_rects['title',self.id];origin=rect.bottomRight();end=rect.center()+(origin-rect.center())*factor
        for kind,pos,button,buttons in ((QEvent.MouseButtonPress,origin,Qt.LeftButton,Qt.LeftButton),
                (QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton),
                (QEvent.MouseButtonRelease,end,Qt.LeftButton,Qt.NoButton)):
            self.app.sendEvent(view,QMouseEvent(kind,pos,view.mapToGlobal(pos.toPoint()),button,buttons,Qt.NoModifier))
        self.app.processEvents()
    def test_corner_drag_changes_size_and_one_undo_restores_it(self):
        before=copy.deepcopy(self.item().title_style);index=self.w._history_index
        self.drag()
        self.assertAlmostEqual(self.item().title_style.zoom_x,1.4,delta=.005)
        self.assertEqual(self.item().title_style.zoom_x,self.item().title_style.zoom_y)
        self.assertAlmostEqual(self.w.inspector.headline_size.spin.value(),140,delta=.5)
        self.assertEqual((self.item().title_style.position_x,self.item().title_style.position_y),(before.position_x,before.position_y))
        self.assertEqual(self.w._history_index,index+1)
        self.w.undo();self.assertEqual(self.item().title_style.zoom_x,before.zoom_x)
        self.w.redo();self.assertAlmostEqual(self.item().title_style.zoom_x,1.4,delta=.005)
    def test_size_field_changes_visible_bounds_then_drag_uses_current_size(self):
        view=self.w.preview;view.grab();original=view.text_rects['title',self.id].width()
        self.w.inspector.headline_size.change(150);view.grab()
        self.assertAlmostEqual(view.text_rects['title',self.id].width(),original*1.5,delta=2)
        self.drag(1.2);self.assertAlmostEqual(self.item().title_style.zoom_x,1.8,delta=.01)
    def test_locked_and_hidden_controls_do_not_resize(self):
        self.w.project.track_states[self.item().track]={'locked':True}
        self.drag();self.assertEqual(self.item().title_style.zoom_x,1)
        self.w.project.track_states[self.item().track]={};self.w.preview.transform_controls_visible=False
        self.drag();self.assertEqual(self.item().title_style.zoom_x,1)
    def test_multiple_titles_resize_together_and_skip_locked(self):
        first=self.id;self.w.add_title_object('Headline');second=self.w.timeline.selected_id
        self.w.timeline.select_ids({first,second},first);self.w.inspector.select(first);self.w.preview.select_item(first)
        self.drag();self.assertAlmostEqual(self.w.project.item_by_id(second).title_style.zoom_x,1.4,delta=.005)
    def test_bold_toggle_changes_shared_paths_and_export_and_persists(self):
        item=self.item();style=item.title_style
        # Offscreen Qt does not load Windows Arial, and falls back to single-face
        # Anton. Use bundled regular/bold Poppins for this glyph comparison.
        style.font='Poppins'
        self.assertTrue(self.w.inspector.headline_bold.isChecked())
        bold=paths(item.title_text,style,1080,1920)[0]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'headline.ass';write_ass(self.w.project,path,False);bold_ass=path.read_text(encoding='utf-8-sig')
            self.w.inspector.headline_bold.click();self.assertEqual(style.font_face,'Regular')
            normal=paths(item.title_text,style,1080,1920)[0];self.assertNotEqual(bold,normal)
            write_ass(self.w.project,path,False);self.assertNotEqual(path.read_text(encoding='utf-8-sig'),bold_ass)
            project=Path(folder)/'headline.kcut';self.w.project.save(project)
            self.assertEqual(Project.load(project).item_by_id(item.id).title_style.font_face,'Regular')
        self.w.undo();self.assertEqual(self.item().title_style.font_face,'Bold')
        self.assertTrue(self.w.inspector.headline_bold.isChecked())
    def test_drag_clamps_to_inspector_range(self):
        self.drag(5);self.assertEqual(self.item().title_style.zoom_x,2.5)
        self.drag(.01);self.assertEqual(self.item().title_style.zoom_x,.2)
