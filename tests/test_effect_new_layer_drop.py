import unittest
from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData,QEvent
from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDragLeaveEvent,QDropEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem
from kinetic_cut.effects import TITLES,GRAPHICS


class EffectNewLayerDropTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance();self.w=MainWindow();self.w.resize(1480,900);self.w.show();self.w.autosave_timer.stop();self.app.processEvents()
    def tearDown(self):
        self.w.close();self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
    def setup(self):
        self.w.set_project(Project(timeline=[TimelineItem('old','','video_1',0,2)]));self.app.processEvents()
        t=self.w.timeline
        return t,QPoint(round(t.x_for_time(3)),round(t.track_rect('video_1').top()-20))
    def hover(self,t,name,pos):
        mime=QMimeData();mime.setData('application/x-kinetic-effect',name.encode())
        enter=QDragEnterEvent(pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier);t.dragEnterEvent(enter)
        move=QDragMoveEvent(pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier);t.dragMoveEvent(move)
        return mime,move
    def test_every_title_and_graphic_creates_one_layer_on_drop_and_one_undo(self):
        for name in [*TITLES,*GRAPHICS]:
            with self.subTest(effect=name):
                t,pos=self.setup();before=self.w._history_index
                mime,move=self.hover(t,name,pos);self.assertTrue(move.isAccepted())
                self.assertEqual(t.provisional_track,'__new_video');self.assertEqual(len(self.w.project.video_tracks),1)
                self.assertEqual(len(self.w.project.timeline),1)
                drop=QDropEvent(QPointF(pos),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier);t.dropEvent(drop)
                self.assertTrue(drop.isAccepted());self.assertEqual(t.provisional_track,'')
                self.assertEqual(len(self.w.project.video_tracks),2);self.assertEqual(len(self.w.project.timeline),2)
                item=next(i for i in self.w.project.timeline if i.id!='old');id=item.id
                self.assertEqual(item.track,self.w.project.video_tracks[-1]);self.assertAlmostEqual(item.start,3,delta=.03)
                self.assertEqual(item.role,'graphic' if name in GRAPHICS else 'title')
                self.assertEqual(self.w._history_index,before+1)
                self.w.undo();self.assertEqual(len(self.w.project.video_tracks),1);self.assertIsNone(self.w.project.item_by_id(id))
                self.w.redo();self.assertEqual(len(self.w.project.video_tracks),2);self.assertIsNotNone(self.w.project.item_by_id(id))
    def test_leave_cancels_provisional_without_project_changes(self):
        t,pos=self.setup();before=self.w.project.to_dict();history=self.w._history_index
        self.hover(t,'Text',pos);t.dragLeaveEvent(QDragLeaveEvent())
        self.assertEqual(t.provisional_track,'');self.assertIsNone(t.effect_hover)
        self.assertEqual(self.w.project.to_dict(),before);self.assertEqual(self.w._history_index,history)
    def test_existing_lane_locked_and_invalid_targets(self):
        t,pos=self.setup();inside=t.track_rect('video_1').center();inside.setX(t.x_for_time(3))
        mime,move=self.hover(t,'Rectangle',inside.toPoint());self.assertTrue(move.isAccepted());self.assertEqual(t.provisional_track,'')
        drop=QDropEvent(inside,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier);t.dropEvent(drop)
        self.assertEqual(len(self.w.project.video_tracks),1);self.assertEqual(self.w.project.timeline[-1].track,'video_1')
        self.w.project.track_states['video_1']={'locked':True}
        self.assertIsNone(t.effect_target('Text',inside))
        for point in (QPointF(5,pos.y()),QPointF(pos.x(),5),t.track_rect('audio_1').center()):
            self.assertIsNone(t.effect_target('Text',point))
        self.assertIsNotNone(t.effect_target('Text',QPointF(pos)))
        t.set_read_only(True);self.assertIsNone(t.effect_target('Text',QPointF(pos)))
    def test_ordinary_effect_does_not_create_video_layer(self):
        t,pos=self.setup();mime,move=self.hover(t,'Sepia',pos)
        self.assertFalse(move.isAccepted());self.assertEqual(t.provisional_track,'')
        drop=QDropEvent(QPointF(pos),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier);t.dropEvent(drop)
        self.assertFalse(drop.isAccepted());self.assertEqual(len(self.w.project.video_tracks),1)
