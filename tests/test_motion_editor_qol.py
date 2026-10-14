import copy,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData
from PySide6.QtGui import QDragEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPlainTextEdit
import test_motion_workbench as fixtures
from kinetic_cut.motion import curve

class MotionEditorQualityTests(unittest.TestCase):
    setUp=fixtures.MotionWorkbenchEditorTests.setUp
    tearDown=fixtures.MotionWorkbenchEditorTests.tearDown
    def shapes(self):
        self.d.scene['nodes']=[dict(id='a',kind='rectangle',x=80,y=180,width=30,height=30,fill='#ff0000'),dict(id='b',kind='rectangle',x=200,y=180,width=30,height=30,fill='#00ff00')]
        self.d.selected_ids=set(); self.d.node_id=''; self.d.rebuild(); self.d.seek(1)
    def point(self,x,y):return self.d.preview.from_scene(QPointF(x,y)).toPoint()
    def test_linked_scale_axes_preserve_ratio_and_local_history(self):
        self.shapes(); self.d.select_node('a'); node=self.d.node(); node.update(scale=2,scale_y=3); self.d.refresh()
        self.assertTrue(self.d.scale_link.isChecked()); before=copy.deepcopy(self.d.scene)
        self.d.spins['scale'].setValue(4)
        self.assertEqual(curve(node,'scale_y',1),6); self.d.local_history(-1); self.assertEqual(self.d.scene,before)
        self.d.scale_link.setChecked(False); self.d.spins['scale'].setValue(4)
        self.assertEqual(curve(self.d.node(),'scale_y',1),3)

    def test_inspector_multi_step_relative_but_typed_value_exact(self):
        from kinetic_cut.model import TimelineItem,Transform
        self.d.reject(); p=self.w.project
        p.timeline=[TimelineItem('a','','video_1',0,4,transform=Transform(scale=1,scale_y=2)),TimelineItem('b','','video_2',0,4,transform=Transform(scale=2,scale_y=3))]
        self.w.timeline.select_ids({'a','b'},'a'); panel=self.w.inspector; panel.select('a'); row=panel.zoom_x
        row.spin.stepBy(1); a,b=p.timeline
        self.assertAlmostEqual(a.transform.scale,1.01); self.assertAlmostEqual(b.transform.scale,2.01)
        self.assertAlmostEqual(a.transform.scale_y/a.transform.scale,2); self.assertAlmostEqual(b.transform.scale_y/b.transform.scale,1.5)
        row.spin._finish_keyboard_edit(); self.assertNotEqual(a.transform.scale,b.transform.scale)
        row.spin._typing=True; row.spin.lineEdit().setText('1.51'); row.spin._finish_keyboard_edit()
        self.assertAlmostEqual(a.transform.scale,1.51); self.assertAlmostEqual(b.transform.scale,1.51)
        row.spin._typing=True; row.spin.lineEdit().setText('3'); row.spin._finish_keyboard_edit()
        self.assertAlmostEqual(a.transform.scale,3); self.assertAlmostEqual(b.transform.scale,3)
        panel.select('a'); row.spin._typing=True; row.spin.lineEdit().setText('3'); row.spin._finish_keyboard_edit()
        self.assertEqual(a.transform.scale,b.transform.scale)
        position=next(r for attr,r in panel.bindings if attr=='position_x')
        a.transform.x=.3; b.transform.x=.7; panel.select('a'); position.spin.stepBy(1)
        self.assertAlmostEqual(b.transform.x-a.transform.x,.4)
        position.spin._typing=True; position.spin.lineEdit().setText('10'); position.spin._finish_keyboard_edit()
        self.assertAlmostEqual(a.transform.x,b.transform.x)

    def test_main_preview_draws_every_selected_visible_transform_box(self):
        from kinetic_cut.model import TimelineItem
        from PySide6.QtGui import QImage
        from PySide6.QtCore import QRectF
        self.d.reject(); p=self.w.project
        p.timeline=[TimelineItem('a','','video_1',0,4),TimelineItem('b','','video_2',0,4)]
        self.w.timeline.select_ids({'a','b'},'a'); preview=self.w.preview; preview.transform_controls_visible=True
        visible=[(i,QImage(),QRectF(30,30,50,50)) for i in p.timeline]
        drawn=[]
        def scene(canvas,painter,rect):return (p.timeline[0],visible[0][2]),''
        def boxes(canvas,painter,item,target):drawn.append(item.id)
        with patch.object(type(preview),'_paint_scene',scene),patch.object(type(preview),'_visible_items',lambda canvas:visible),patch.object(type(preview),'_draw_transform_box',boxes):
            preview.grab(); self.assertEqual(set(drawn),{'a','b'})
            p.timeline[1].keyframes={'rotation':[{'time':0,'value':0}]}; drawn.clear()
            preview.grab(); self.assertEqual(set(drawn),{'a','b'})
            drawn.clear(); preview.transform_controls_visible=False; preview.grab(); self.assertEqual(drawn,[])

    def test_canvas_matches_project_and_safe_guide_is_centered(self):
        self.d.scene['canvas']=[1920,1080]
        rect=self.d.preview.canvas_rect()
        self.assertAlmostEqual(rect.width()/rect.height(),320/568)
        safe=self.d.preview.safe_rect(); self.assertEqual(safe.center(),rect.center())
        center=self.d.preview.from_scene(QPointF(960,540)); self.assertEqual(center,rect.center())
    def test_retime_button_matches_shortcut_and_disables_on_selection_clear(self):
        self.d.reject(); self.w.timeline.select_ids(set()); button=self.w.retime_button
        self.assertFalse(button.isEnabled()); self.assertEqual(button.toolTip(),'select a media to re-time first')
        self.assertFalse(hasattr(self.w,'keyframe_button'))
        self.w.timeline.select_ids({'motion'},'motion'); self.assertTrue(button.isEnabled()); self.assertIn('Ctrl+R',button.toolTip())
        before=copy.deepcopy(self.w.project); QTest.mouseClick(button,Qt.LeftButton); self.assertEqual(self.w.timeline.retime_ids,{'motion'})
        self.w.shortcut_actions['retime_controls'].trigger(); self.assertEqual(self.w.timeline.retime_ids,set()); self.assertEqual(self.w.project,before)
        self.w.set_project(fixtures.Project()); self.assertFalse(button.isEnabled())
    def test_ctrl_click_syncs_tree_and_bulk_edit_is_one_local_undo(self):
        self.shapes(); p=self.d.preview
        QTest.mouseClick(p,Qt.LeftButton,Qt.NoModifier,self.point(80,180))
        QTest.mouseClick(p,Qt.LeftButton,Qt.ControlModifier,self.point(200,180))
        self.assertEqual(self.d.selected_ids,{'a','b'})
        self.assertEqual({i.data(0,Qt.UserRole) for i in self.d.tree.selectedItems()},{'a','b'})
        before=copy.deepcopy(self.d.scene); self.d.change('opacity',42)
        self.assertTrue(all(n['opacity']==42 for n in self.d.scene['nodes']))
        self.d.local_history(-1); self.assertEqual(self.d.scene,before)
        QTest.mouseClick(p,Qt.LeftButton,Qt.ControlModifier,self.point(80,180)); self.assertEqual(self.d.selected_ids,{'b'})
    def test_tree_ctrl_deselect_keeps_property_edit_on_selected_layer(self):
        self.shapes(); tree=self.d.tree; a,b=tree.topLevelItem(0),tree.topLevelItem(1)
        QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.NoModifier,tree.visualItemRect(a).center())
        QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.ControlModifier,tree.visualItemRect(b).center())
        self.assertEqual(self.d.selected_ids,{'a','b'})
        QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.ControlModifier,tree.visualItemRect(b).center())
        self.assertEqual(self.d.selected_ids,{'a'}); self.assertEqual(self.d.node_id,'a')
        self.d.layer_name.setText('Renamed')
        self.assertEqual(self.d.scene['nodes'][0]['name'],'Renamed'); self.assertNotEqual(self.d.scene['nodes'][1].get('name'),'Renamed')
        self.assertTrue(a.text(0).startswith('Renamed')); self.assertFalse(b.text(0).startswith('Renamed'))
    def test_marquee_and_multi_move_preserve_spacing(self):
        self.shapes(); p=self.d.preview
        QTest.mousePress(p,Qt.LeftButton,Qt.NoModifier,self.point(45,145)); QTest.mouseMove(p,self.point(235,215)); QTest.mouseRelease(p,Qt.LeftButton,Qt.NoModifier,self.point(235,215))
        self.assertEqual(self.d.selected_ids,{'a','b'}); self.assertIsNone(p.drag)
        before=copy.deepcopy(self.d.scene)
        QTest.mousePress(p,Qt.LeftButton,Qt.NoModifier,self.point(80,180)); QTest.mouseMove(p,self.point(100,200)); QTest.mouseRelease(p,Qt.LeftButton,Qt.NoModifier,self.point(100,200))
        a,b=self.d.scene['nodes']; self.assertAlmostEqual(b['x']-a['x'],120); self.assertGreater(a['x'],90)
        self.d.local_history(-1); self.assertEqual(self.d.scene,before)
    def test_keyboard_shortcuts_stay_local_and_typing_space_does_not_play(self):
        self.shapes(); self.d.activateWindow(); self.d.preview.setFocus(); self.app.processEvents()
        before=copy.deepcopy(self.w.project); self.d.change('x',123)
        QTest.keyClick(self.d.preview,Qt.Key_Z,Qt.ControlModifier); self.assertEqual(self.d.node()['x'],80)
        QTest.keyClick(self.d.preview,Qt.Key_Z,Qt.ControlModifier|Qt.ShiftModifier); self.assertEqual(self.d.node()['x'],123)
        self.assertEqual(self.w.project,before)
        QTest.keyClick(self.d.preview,Qt.Key_Space); self.assertTrue(self.d.timer.isActive())
        QTest.keyClick(self.d.preview,Qt.Key_Space); self.assertFalse(self.d.timer.isActive())
        self.d.layer_name.setFocus(); QTest.keyClick(self.d.layer_name,Qt.Key_Space); self.assertFalse(self.d.timer.isActive())
    def test_double_click_text_inline_edit_cancel_and_commit(self):
        self.d.scene['nodes']=[dict(id='text',kind='text',text='HELLO',x=160,y=180,font_size=32)]
        self.d.node_id='text'; self.d.selected_ids={'text'}; self.d.rebuild(); self.d.seek(1)
        p=self.d.preview; QTest.mouseDClick(p,Qt.LeftButton,Qt.NoModifier,self.point(160,180))
        edit=p.findChild(QPlainTextEdit); self.assertIsNotNone(edit); edit.setPlainText('NEW TEXT')
        self.assertEqual(self.d.node()['text'],'NEW TEXT'); QTest.keyClick(edit,Qt.Key_Escape); self.assertEqual(self.d.node()['text'],'HELLO')
        self.app.processEvents(); QTest.mouseDClick(p,Qt.LeftButton,Qt.NoModifier,self.point(160,180))
        edits=[e for e in p.findChildren(QPlainTextEdit) if e.isVisible()]; self.assertEqual(len(edits),1)
        edits[0].setPlainText('DONE'); QTest.keyClick(edits[0],Qt.Key_Return,Qt.ControlModifier); self.assertEqual(self.d.node()['text'],'DONE')
        self.d.local_history(-1); self.assertEqual(self.d.node()['text'],'HELLO')
    def test_duplicate_remove_multiple_branches_have_local_history(self):
        self.shapes(); self.d.select_nodes({'a','b'}); before=copy.deepcopy(self.d.scene)
        self.d.duplicate(); self.assertEqual(len(self.d.scene['nodes']),4); self.assertEqual(len(self.d.selected_ids),2)
        self.d.remove(); self.assertEqual(self.d.scene,before); self.d.local_history(-1); self.assertEqual(len(self.d.scene['nodes']),4)
    def test_motion_graphic_drag_entry_is_accepted(self):
        from kinetic_cut.effects import GRAPHICS
        for name in GRAPHICS:
            mime=QMimeData(); mime.setData('application/x-kinetic-effect',name.encode())
            event=QDragEnterEvent(QPoint(300,100),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
            self.w.timeline.dragEnterEvent(event); self.assertTrue(event.isAccepted(),name)
    def test_tree_drag_reparents_branches_atomically_and_rejects_cycles(self):
        from PySide6.QtWidgets import QAbstractItemView
        self.shapes(); self.d.scene['nodes'].insert(0,dict(id='group',kind='group')); self.d.rebuild(); self.d.select_node('a')
        tree=self.d.tree; target=tree.topLevelItem(0); point=tree.visualItemRect(target).center()
        class Drop:
            accepted=False
            def source(s):return tree
            def position(s):return QPointF(point)
            def ignore(s):s.accepted=False
            def acceptProposedAction(s):s.accepted=True
        before=copy.deepcopy(self.d.scene); event=Drop()
        with patch.object(tree,'dropIndicatorPosition',return_value=QAbstractItemView.OnItem):tree.dropEvent(event)
        self.assertTrue(event.accepted); self.assertEqual(self.d.node()['parent'],'group')
        self.d.select_node('group'); child=tree.topLevelItem(0).child(0); point=tree.visualItemRect(child).center()
        with patch.object(tree,'dropIndicatorPosition',return_value=QAbstractItemView.OnItem):tree.dropEvent(event)
        self.assertFalse(event.accepted); self.assertEqual(self.d.node().get('parent',''),'')
        self.d.local_history(-1); self.assertEqual(self.d.scene,before)
    def test_reorder_multiple_branches_keeps_descendants_and_selection(self):
        self.d.scene['nodes']=[dict(id='a',kind='group'),dict(id='child',parent='a',kind='rectangle'),dict(id='b',kind='rectangle'),dict(id='c',kind='rectangle')]
        self.d.selected_ids={'a','b'}; self.d.node_id='a'; self.d.rebuild(); before=copy.deepcopy(self.d.scene)
        self.d.reorder(1); self.assertEqual([n['id'] for n in self.d.scene['nodes']],['c','a','child','b'])
        self.assertEqual(self.d.selected_ids,{'a','b'}); self.d.local_history(-1); self.assertEqual(self.d.scene,before)
    def test_bulk_keys_preserve_distinct_values_and_undo_together(self):
        self.shapes(); self.d.select_nodes({'a','b'},'a'); self.d.channel.setCurrentText('x')
        self.d.add_key(); self.assertEqual([n['keyframes']['x'][0]['value'] for n in self.d.scene['nodes']],[80,200])
        self.d.change_mode('Bezier'); self.assertTrue(all(n['keyframes']['x'][0]['interpolation']=='Bezier' for n in self.d.scene['nodes']))
        self.d.bezier[0].setValue(.15); self.assertTrue(all(n['keyframes']['x'][0]['bezier'][0]==.15 for n in self.d.scene['nodes']))
        self.d.remove_key(); self.assertTrue(all(not n['keyframes']['x'] for n in self.d.scene['nodes']))
        self.d.local_history(-1); self.assertTrue(all(n['keyframes']['x'] for n in self.d.scene['nodes']))

if __name__=='__main__':unittest.main()
