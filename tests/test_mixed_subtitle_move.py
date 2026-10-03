import copy,unittest
from pathlib import Path
from PySide6.QtCore import QPoint,Qt,QEvent,QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption
from kinetic_cut.mixed_move import snap_move


class MixedSubtitleTests(unittest.TestCase):
    def setUp(self):
        self.w=MainWindow(); self.w.resize(1400,850); self.w.show(); self.w.autosave_timer.stop()
        self.p=Project(media=[MediaItem('m','missing.mp4','video','fixture',30,1920,1080,60,True)],
            timeline=[TimelineItem('v','m','video_1',2,2,group_id='av'),TimelineItem('a','m','audio_1',2,2,group_id='av')],
            captions=[Caption('c',2.4,3.2,'Hello'),Caption('next',8,9,'Neighbour')])
        self.p.captions[0].word_timings=[dict(text='Hello',start=0,end=.8)]
        self.w.set_project(self.p); self.t=self.w.timeline; self.t.set_zoom(40); self.t.setProperty('snapping',False); QApplication.processEvents()
    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); QApplication.processEvents()
        self.w.deleteLater(); QApplication.sendPostedEvents(None,QEvent.DeferredDelete)
    def point(self,kind):
        return (self.t.visible_caption_rect(self.w.project.captions[0]) if kind=='c' else self.t.visible_item_rect(self.w.project.item_by_id(kind))).center().toPoint()
    def select(self,first='c'):
        second='v' if first=='c' else 'c'
        QTest.mouseClick(self.t.viewport(),Qt.LeftButton,pos=self.point(first))
        QTest.mouseClick(self.t.viewport(),Qt.LeftButton,Qt.ShiftModifier,self.point(second))
        self.assertEqual(self.t.selected_ids,{'v','a'}); self.assertEqual(self.t.selected_caption_ids,{'c'})
    def drag(self,kind,alt=False,cancel=False):
        p=self.point(kind); mod=Qt.AltModifier if alt else Qt.NoModifier
        QTest.mousePress(self.t.viewport(),Qt.LeftButton,mod,p)
        self.assertEqual(self.t.drag_mode,'mixed_move')
        QTest.mouseMove(self.t.viewport(),p+QPoint(200,0))
        if cancel:QTest.keyClick(self.t.viewport(),Qt.Key_Escape)
        QTest.mouseRelease(self.t.viewport(),Qt.LeftButton,mod,p+QPoint(200,0))
    def test_shift_selection_both_directions_and_move_from_caption(self):
        self.select('v'); self.drag('c')
        self.assertAlmostEqual(self.w.project.item_by_id('v').start,7)
        self.assertAlmostEqual(self.w.project.item_by_id('a').start,7)
        c=next(c for c in self.w.project.captions if c.id=='c'); self.assertAlmostEqual(c.start,7.4)
        self.assertEqual(c.word_timings,[dict(text='Hello',start=0,end=.8)])
        self.assertEqual(self.t.selected_ids,{'v','a'}); self.assertEqual(self.t.selected_caption_ids,{'c'})
        self.w.undo(); self.assertEqual(self.w.project.item_by_id('v').start,2)
        self.assertEqual(self.w.project.captions[0].start,2.4)
        self.w.redo(); self.assertEqual(self.w.project.item_by_id('v').start,7)
    def test_move_from_video_cancel_and_alt_duplicate(self):
        self.select(); original=copy.deepcopy(self.w.project.to_dict()); self.drag('a',cancel=True)
        self.assertEqual(self.w.project.to_dict(),original)
        self.drag('v',alt=True)
        self.assertEqual(len(self.w.project.timeline),4); self.assertEqual(self.w.project.item_by_id('v').start,2)
        self.assertEqual(len(self.t.selected_ids),2); self.assertFalse(self.t.selected_ids&{'v','a'})
        self.assertEqual(len(self.t.selected_caption_ids),1); self.assertNotIn('c',self.t.selected_caption_ids)
    def test_locked_subtitle_blocks_whole_group(self):
        self.select(); self.w.project.track_states['subtitle_1']={'locked':True}
        p=self.point('v'); QTest.mousePress(self.t.viewport(),Qt.LeftButton,pos=p)
        self.assertEqual(self.t.drag_mode,''); QTest.mouseRelease(self.t.viewport(),Qt.LeftButton,pos=p)
        self.assertEqual(self.w.project.item_by_id('v').start,2)
    def test_sticky_start_and_end_edges_release_for_deliberate_overlap(self):
        self.t.setProperty('snapping',True); self.t._move_snap=None
        # Moving end 3.2 to neighbour start 8: acquire, hold, then release.
        self.assertAlmostEqual(snap_move(self.t,4.65,[2.4,3.2],{'v','a'},{'c'}),4.8)
        self.assertAlmostEqual(snap_move(self.t,5.1,[2.4,3.2],{'v','a'},{'c'}),4.8)
        self.assertAlmostEqual(snap_move(self.t,5.3,[2.4,3.2],{'v','a'},{'c'}),5.3)
    def test_custom_style_uses_full_outer_scroll_at_small_height(self):
        self.w.resize(1200,700); self.t.select_captions({'c'},'c'); panel=self.w.inspector
        panel.customize.setChecked(True); QApplication.processEvents()
        outer=panel.subtitle.widget(0)
        self.assertIsNone(panel.style_scroll.widget()); self.assertTrue(panel.style_scroll.isHidden())
        self.assertEqual(panel.style_content.parentWidget(),panel.custom_style_host)
        self.assertGreater(panel.style_content.height(),outer.viewport().height())
        self.assertGreater(outer.verticalScrollBar().maximum(),0)
        outer.verticalScrollBar().setValue(300); QApplication.processEvents()
        out=Path('build/mixed-subtitle-check'); out.mkdir(parents=True,exist_ok=True); panel.grab().save(str(out/'custom-small.png'))
        panel.subtitle.setCurrentIndex(1); self.assertIs(panel.style_scroll.widget(),panel.style_content)
        panel.subtitle.setCurrentIndex(0); panel.customize.setChecked(False); QApplication.processEvents()
        self.assertFalse(panel.custom_style_host.isVisible())
