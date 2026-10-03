"""Owner-reported placement, attribute and inspector interaction regressions."""
import copy
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint, QPointF, QEvent, QThreadPool, QTimer
from PySide6.QtGui import QMouseEvent, QContextMenuEvent
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMenu
from PySide6.QtTest import QTest
from kinetic_cut.model import Project, MediaItem, TimelineItem, Caption
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.ui import MainWindow
from kinetic_cut.controls import SafeDoubleSpinBox, SafeSpinBox
from kinetic_cut.attributes import PasteAttributesDialog, VIDEO, AUDIO, TEXT
from kinetic_cut import clipboard
from kinetic_cut.mixed_move import snap_move


class EditingFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def retire(self,widget):
        # Release each fixture while its Qt wrappers/signals are still alive,
        # rather than accumulating native windows until QApplication teardown.
        widget.close(); QThreadPool.globalInstance().waitForDone(10000)
        self.app.processEvents(); widget.deleteLater()
        QApplication.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()

    def window(self):
        w=MainWindow(); w.autosave_timer.stop()
        p=Project(media=[MediaItem('m','missing.png','image','fixture',30,1920,1080)],
                  timeline=[TimelineItem('v','m','video_1',0,2)])
        w.set_project(p); w.resize(1400,850); w.show(); self.app.processEvents()
        self.addCleanup(self.retire,w); return w

    def test_same_lane_neighbor_wins_over_offset_layer_and_playhead(self):
        t=TimelineWidget(); self.addCleanup(self.retire,t)
        p=Project(timeline=[TimelineItem('move','','video_1',1,2),TimelineItem('neighbor','','video_1',8.0137,2),
                           TimelineItem('other','','video_2',8.03,2)])
        t.set_project(p); t.set_zoom(100); t.setProperty('snapping',True); p.playhead=8.04
        delta=snap_move(t,5.04,[1,3],{'move'})
        self.assertEqual(1+delta+2,p.timeline[1].start)
        self.assertEqual(t.snap_guide,8.0137)
        t.setProperty('snapping',False)
        self.assertEqual(snap_move(t,5.04,[1,3],{'move'}),5.04)

    def test_new_destination_and_held_cross_lane_snap(self):
        t=TimelineWidget(); self.addCleanup(self.retire,t)
        p=Project(timeline=[TimelineItem('move','','video_1',1,2),TimelineItem('n','','video_2',8.0137,2)])
        t.set_project(p); t.set_zoom(100); t.setProperty('snapping',True); p.playhead=8.04
        t._move_snap=(3,8.04)
        delta=snap_move(t,5.04,[1,3],{'move'},destination_tracks={'video_2'})
        self.assertEqual(3+delta,8.0137)
        self.assertEqual(snap_move(t,5.12,[1,3],{'move'},destination_tracks={'video_2'}),delta)
        self.assertEqual(snap_move(t,5.3,[1,3],{'move'},destination_tracks={'video_2'}),5.3)

    def test_release_snaps_without_final_move_event_for_all_clip_types(self):
        for kind,role,track in [('video','normal','video_1'),('image','normal','video_1'),
                                ('image','title','video_1'),('image','graphic','video_1'),('audio','normal','audio_1')]:
            with self.subTest(kind=kind,role=role):
                p=Project(media=[MediaItem('m','missing',''+kind,'fixture',30,1920,1080)],
                          timeline=[TimelineItem('move','m',track,1,2,role=role),TimelineItem('n','m',track,8.0137,2)])
                t=TimelineWidget(); t.resize(1300,550); t.set_project(p); t.set_zoom(100); t.setProperty('snapping',True); t.show(); self.app.processEvents()
                try:
                    origin=t.visible_item_rect(p.timeline[0]).center().toPoint()
                    QTest.mousePress(t.viewport(),Qt.LeftButton,pos=origin)
                    QTest.mouseMove(t.viewport(),origin+QPoint(470,0))
                    QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=origin+QPoint(503,0))
                    self.assertAlmostEqual(p.item_by_id('move').start+2,8.0137,places=12)
                finally:self.retire(t)

    def test_caption_release_sticks_and_preserves_word_metadata(self):
        p=Project(captions=[Caption('c',1,3,'Hello'),Caption('n',8.0137,9,'Neighbor')])
        p.captions[0].word_timings=[{'text':'Hello','start':0,'end':1}]
        t=TimelineWidget(); self.addCleanup(self.retire,t); t.resize(1300,550); t.set_project(p); t.set_zoom(100); t.setProperty('snapping',True); t.show(); self.app.processEvents()
        origin=t.visible_caption_rect(p.captions[0]).center().toPoint()
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=origin); QTest.mouseMove(t.viewport(),origin+QPoint(470,0))
        QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=origin+QPoint(503,0))
        cap=next(c for c in p.captions if c.id=='c'); self.assertEqual(cap.end,8.0137)
        self.assertEqual(cap.word_timings,[{'text':'Hello','start':0,'end':1}])

    def test_context_track_insert_preserves_existing_ids_states_and_undo(self):
        w=self.window(); p=w.project
        for _ in range(3):p.add_track('video')
        p.track_states['video_4']['locked']=True; old=copy.deepcopy(p.to_dict()); w.model_changed()
        w.timeline_command('add_video','video_3')
        self.assertEqual(p.video_tracks,['video_1','video_2','video_3','video_5','video_4'])
        self.assertEqual(p.track_names['video_5'],'Video 4'); self.assertEqual(p.track_names['video_4'],'Video 5')
        self.assertTrue(p.track_states['video_4']['locked']); self.assertEqual(p.timeline[0].track,'video_1')
        w.undo(); self.assertEqual(w.project.video_tracks,old['video_tracks'])
        w.redo(); self.assertEqual(w.project.video_tracks[-2: ],['video_5','video_4'])

    def test_track_menu_forwards_clicked_lane(self):
        t=TimelineWidget(); self.addCleanup(self.retire,t); p=Project(); p.add_track('video'); t.set_project(p); t.resize(900,550); t.show(); self.app.processEvents()
        pos=t.track_rect('video_1').center().toPoint(); pos.setX(40)
        received=[]; t.commandRequested.connect(lambda cmd,arg:received.append((cmd,arg)))
        class ChoosingMenu(QMenu):
            def exec(self,*args):return next(a for a in self.actions() if a.text()=='Add Video Track')
        with patch('kinetic_cut.widgets.QMenu',ChoosingMenu):t.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse,pos,t.viewport().mapToGlobal(pos)))
        self.assertEqual(received,[('add_video','video_1')])

    def test_attribute_sections_are_complete_and_remember_initial_choices(self):
        for category,fields in [('video',VIDEO),('audio',AUDIO),('text',TEXT)]:
            d=PasteAttributesDialog('Source','Target',category,selected={fields[0][1]}); self.addCleanup(self.retire,d)
            self.assertEqual(set(d.checks),{k for _,k in fields}); self.assertEqual(d.selected(),{fields[0][1]})
            self.assertTrue(all(check.parentWidget() in d.section_boxes.values() for check in d.checks.values()))
        d=PasteAttributesDialog('Source','Target','video'); self.addCleanup(self.retire,d)
        self.assertEqual(d.checks['crop_left'].parentWidget(),d.section_boxes['Crop'])
        self.assertEqual(d.checks['position'].parentWidget(),d.section_boxes['Transform'])
        grid=d.section_boxes['Transform'].layout()
        self.assertEqual(grid.columnCount(),3)
        self.assertEqual([grid.getItemPosition(grid.indexOf(d.checks[key]))[:2] for key in ('position','rotation','anchor')],[(0,0),(0,1),(0,2)])

    def test_attribute_session_memory_only_after_successful_apply(self):
        w=self.window(); w.timeline.select_ids({'v'},'v'); clipboard.put(clipboard.capture(w.project,{'v'},set()))
        self.addCleanup(self.app.clipboard().clear)
        calls=[]
        def execute():
            dialog=self.app.activeModalWidget()
            calls.append(dialog.selected()); dialog.checks['position'].setChecked(True)
            dialog.accept() if len(calls)==1 else dialog.reject()
        for _ in range(3):
            QTimer.singleShot(0,execute); w.paste_attributes()
        self.assertEqual(calls,[set(),{'position'},{'position'}])
        self.assertEqual(w._paste_attribute_choices,{'video':{'position'}})
        for dialog in w.findChildren(PasteAttributesDialog):
            self.retire(dialog)
        other=self.window(); self.assertFalse(getattr(other,'_paste_attribute_choices',{}))

    def test_linked_zoom_preserves_ratio_in_both_directions_and_reset(self):
        w=self.window(); w.timeline.select_ids({'v'},'v'); panel=w.inspector; t=w.project.timeline[0].transform
        panel.link.setChecked(False); panel.zoom_x.spin.setValue(1.908); panel.zoom_y.spin.setValue(1.190)
        panel.link.setChecked(True); self.assertEqual((t.scale,t.scale_y),(1.908,1.190))
        panel.zoom_x.spin.setValue(1.909); self.assertAlmostEqual(t.scale_y,1.190*1.909/1.908)
        panel.zoom_y.spin.setValue(1.3); self.assertAlmostEqual(t.scale/t.scale_y,1.908/1.190)
        panel.reset_zoom(); self.assertEqual((t.scale,t.scale_y),(1.,1.))

    def test_unlinked_x_keeps_implicit_y(self):
        w=self.window(); w.timeline.select_ids({'v'},'v'); t=w.project.timeline[0].transform
        t.scale=2; t.scale_y=None; t.scale_linked=False; w.inspector.select('v')
        w.inspector.zoom_x.spin.setValue(3); self.assertEqual(t.effective_scale_y,2)

    def test_numeric_enter_blurs_and_next_drag_still_changes_value(self):
        for cls in (SafeDoubleSpinBox,SafeSpinBox):
            spin=cls(); self.addCleanup(self.retire,spin); spin.setRange(-1000,1000); spin.show(); self.app.processEvents(); line=spin.lineEdit()
            QTest.mouseDClick(line,Qt.LeftButton); QTest.keyClicks(line,'123'); QTest.keyClick(line,Qt.Key_Return); self.app.processEvents()
            self.assertEqual(spin.value(),123); self.assertFalse(line.hasFocus()); self.assertFalse(line.hasSelectedText()); self.assertTrue(spin.keyboardTracking())
            point=QPoint(10,10); origin=line.mapToGlobal(point); QTest.mousePress(line,Qt.LeftButton,pos=point)
            self.assertIsNotNone(spin._drag_start)
            QApplication.sendEvent(line,QMouseEvent(QEvent.MouseMove,QPointF(point+QPoint(10,0)),QPointF(origin+QPoint(10,0)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
            QTest.mouseRelease(line,Qt.LeftButton,pos=point); self.assertGreater(spin.value(),123)

    def test_linked_blur_updates_both_sliders_before_release_one_undo(self):
        w=self.window(); w.timeline.select_ids({'v'},'v'); w.apply_effect('Gaussian Blur'); panel=w.inspector
        count=len(w._history); panel.blur_h.slider.setSliderDown(True); panel.blur_h.slider.setValue(700)
        effect=w.project.timeline[0].effects[0]
        self.assertEqual(effect['horizontal'],effect['vertical']); self.assertEqual(panel.blur_h.slider.value(),panel.blur_v.slider.value())
        self.assertEqual(panel.blur_h.spin.value(),panel.blur_v.spin.value())
        panel.blur_h.slider.setSliderDown(False); self.assertEqual(len(w._history),count+1)
        panel.blur_link.setChecked(False); vertical=panel.blur_v.slider.value(); panel.blur_h.slider.setValue(600)
        self.assertEqual(panel.blur_v.slider.value(),vertical)
