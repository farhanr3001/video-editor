import copy,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox,QApplication
import test_pool_monitor_polish as fixture
from kinetic_cut.model import TimelineItem,MediaItem
from kinetic_cut.pool_tools import set_view


class PoolRemovalTests(unittest.TestCase):
    setUp=fixture.PoolMonitorTests.setUp
    tearDown=fixture.PoolMonitorTests.tearDown
    def select_all(self):
        self.panel.refresh()
        for n in range(self.panel.grid.count()):
            item=self.panel.grid.item(n)
            if item.data(Qt.UserRole+1)=='media':item.setSelected(True)
    def test_project_cancel_and_confirm_batch_in_use(self):
        self.panel.folder='project';self.select_all();before=self.w.project.to_dict();history=self.w._history_index
        with patch('kinetic_cut.pool_removal.QMessageBox.warning',return_value=QMessageBox.Cancel) as dialog:
            self.panel.remove_selected()
        self.assertEqual(self.w.project.to_dict(),before);self.assertIn('2 selected',dialog.call_args.args[2]);self.assertIn('1 timeline',dialog.call_args.args[2])
        with patch('kinetic_cut.pool_removal.QMessageBox.warning',return_value=QMessageBox.Ok):self.panel.remove_selected()
        self.assertEqual(self.w.project.media,[]);self.assertEqual(self.w.project.timeline,[]);self.assertEqual(self.w._history_index,history+1)
        self.assertTrue(all(__import__('pathlib').Path(m.path).exists() for m in self.media))
        self.w.undo();self.assertEqual(len(self.w.project.timeline),1);self.assertEqual(len(self.w.project.media),2)
    def test_power_bin_path_alias_cancel_confirm_and_other_folder_preserved(self):
        self.w.project.media[0].id='alias';self.w.project.timeline[0].media_id='alias';self.panel.power.add(self.media[0],'Master/B');self.select_all()
        before=copy.deepcopy(self.panel.power.data)
        with patch('kinetic_cut.pool_removal.QMessageBox.warning',return_value=QMessageBox.Cancel):self.panel.remove_selected()
        self.assertEqual(self.panel.power.data,before);self.assertEqual(len(self.w.project.timeline),1)
        with patch('kinetic_cut.pool_removal.QMessageBox.warning',return_value=QMessageBox.Ok):self.panel.remove_selected()
        self.assertEqual(self.w.project.timeline,[]);self.assertEqual(len(self.w.project.media),2)
        self.assertFalse(any(e['folder']=='Master/A' for e in self.panel.power.data['media']))
        self.assertTrue(any(e['folder']=='Master/B' for e in self.panel.power.data['media']))
    def test_locked_track_refuses_atomic_removal(self):
        self.w.project.track_states['video_1']={'locked':True};self.select_all();before=copy.deepcopy(self.panel.power.data)
        with patch('kinetic_cut.pool_removal.QMessageBox.information') as info,patch('kinetic_cut.pool_removal.QMessageBox.warning') as confirm:self.panel.remove_selected()
        info.assert_called_once();confirm.assert_not_called();self.assertEqual(self.panel.power.data,before);self.assertEqual(len(self.w.project.timeline),1)
    def test_nested_folder_disclosure_click_collapses_without_reorganizing(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint
        tree=self.panel.tree;node=tree.findItems('A',Qt.MatchExactly|Qt.MatchRecursive)[0];child=node.child(0)
        self.assertEqual(child.text(0),'Nested');before=copy.deepcopy(self.panel.power.data)
        self.assertGreaterEqual(tree.viewport().geometry().left(),6)
        rect=tree.visualItemRect(node);point=QPoint(rect.left()-tree.indentation()//2,rect.center().y())
        self.assertTrue(node.isExpanded());QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.NoModifier,point)
        self.assertFalse(node.isExpanded());self.assertFalse(tree.visualItemRect(child).isValid())
        QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.NoModifier,point);self.assertTrue(node.isExpanded())
        self.assertEqual(self.panel.power.data,before);self.assertFalse(node.icon(0).isNull())
    def test_refresh_preserves_scroll_selection_and_view_toggle_icons(self):
        for folder in ('project','Master/A'):
            self.panel.folder=folder
            for n in range(120):
                m=MediaItem('extra'+str(n),self.media[1].path,'image',f'Extra {n:03}',5,320,180)
                if folder=='project':self.w.project.media.append(m)
                else:
                    entry={'folder':folder,'media':__import__('dataclasses').asdict(m)};self.panel.power.data['media'].append(entry)
            for list_view in (False,True):
                set_view(self.panel,list_view,False);self.panel.refresh();QApplication.processEvents()
                self.assertLessEqual(self.panel.tree.indentation(),8);self.assertFalse(self.panel.view_button.icon().isNull());self.assertEqual(self.panel.view_button.toolButtonStyle(),Qt.ToolButtonTextBesideIcon)
                bar=self.panel.grid.verticalScrollBar();bar.setValue(bar.maximum()//2);before=bar.value();self.assertGreater(before,0)
                self.panel.append_item('0');QApplication.processEvents();self.assertEqual(bar.value(),before)
                self.w.refresh_media();QApplication.processEvents();self.assertEqual(bar.value(),before)

    def test_saved_filename_header_on_open_save_and_failed_open(self):
        from pathlib import Path
        from kinetic_cut.model import Project
        path=Path(self.media[0].path).parent/'Named edit.kcut'
        project=Project(name='Untitled Short');project.save(path)
        with patch.object(self.w,'confirm_project_switch',return_value=True):
            self.assertTrue(self.w.load_project_path(str(path)))
        self.assertEqual(self.w.project_label.text(),'Named edit')
        self.assertEqual(self.w.project.name,'Untitled Short')
        self.assertTrue(self.w.save_project());self.assertEqual(self.w.project_label.text(),'Named edit')
        with patch('kinetic_cut.ui.QMessageBox.critical'):
            self.assertFalse(self.w.load_project_path(str(path.parent/'missing.kcut')))
        self.assertEqual(self.w.project_label.text(),'Named edit')
        self.w.set_project(Project(name='Fresh project'));self.assertEqual(self.w.project_label.text(),'Fresh project')
