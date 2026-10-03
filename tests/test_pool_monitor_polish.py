import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt,QMimeData,QEvent,QPoint,QPointF,QThreadPool
from PySide6.QtGui import QImage,QColor,QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption
from kinetic_cut.workspace import PowerBins
from kinetic_cut.pool_tools import set_view,SourcePreview,wave_image
from kinetic_cut.waveforms import Waveform


class PoolMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.w=MainWindow(); self.w.resize(1450,850); self.w.show(); self.w.autosave_timer.stop()
        self.panel=self.w.media_panel; self.panel.power=PowerBins(Path(self.temp.name)/'bins.json')
        self.panel.power.add_folder('Master/A'); self.panel.power.add_folder('Master/B'); self.panel.power.add_folder('Master/A/Nested')
        self.media=[MediaItem(str(n),str(Path(self.temp.name)/f'{n}.png'),'image',f'Image {n}',5,320,180) for n in range(2)]
        for m in self.media:
            image=QImage(320,180,QImage.Format_RGB32); image.fill(QColor('#42748a')); image.save(m.path); self.panel.power.add(m,'Master/A')
        self.w.set_project(Project(media=copy.deepcopy(self.media),timeline=[TimelineItem('v','0','video_1',0,5)],captions=[Caption('c',0,5,'Hello there')]))
        self.panel.folder='Master/A'; self.panel.rebuild_tree(); self.panel.refresh(); QApplication.processEvents()
    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); QApplication.processEvents(); self.w.deleteLater(); QApplication.sendPostedEvents(None,QEvent.DeferredDelete); self.temp.cleanup()
    def mime(self,folder=False):
        mime=QMimeData()
        if folder:mime.setData('application/x-kinetic-bin-folders',json.dumps(['Master/A/Nested']).encode())
        else:
            mime.setData('application/x-kinetic-media-id',b'0'); mime.setData('application/x-kinetic-media-ids',b'["0","1"]')
            mime.setData('application/x-kinetic-power-source',b'{"folder":"Master/A","ids":["0","1"]}')
        return mime
    def test_batch_move_keeps_current_folder_and_all_sources(self):
        self.assertTrue(self.panel.move_drop(self.mime(),'Master/B'))
        self.assertEqual(self.panel.folder,'Master/A')
        self.assertEqual([e['folder'] for e in self.panel.power.data['media']],['Master/B','Master/B'])
        self.assertTrue(all(Path(m.path).exists() for m in self.media))
    def test_folder_move_cycle_guard_and_recursive_delete_keyboard(self):
        self.assertIsNone(self.panel.power.move_folder('Master/A','Master/A/Nested'))
        self.assertTrue(self.panel.move_drop(self.mime(True),'Master/B'))
        self.assertIn('Master/B/Nested',self.panel.power.data['folders'])
        self.panel.folder='Master'; self.panel.refresh()
        item=next(self.panel.grid.item(n) for n in range(self.panel.grid.count()) if self.panel.grid.item(n).data(Qt.UserRole+2)=='Master/A')
        item.setSelected(True); self.panel.grid.setFocus()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):QTest.keyClick(self.panel.grid,Qt.Key_Delete)
        self.assertNotIn('Master/A',self.panel.power.data['folders']); self.assertFalse(self.panel.power.data['media'])
        self.assertEqual(len(self.w.project.timeline),1); self.assertTrue(all(Path(m.path).exists() for m in self.media))
    def test_folder_tile_drop_in_both_views(self):
        for list_mode in (False,True):
            with self.subTest(list_mode=list_mode):
                for m in self.media:self.panel.power.add(m,'Master/A')
                self.panel.folder='Master'; self.panel.refresh(); set_view(self.panel,list_mode,False); QApplication.processEvents()
                item=next(self.panel.grid.item(n) for n in range(self.panel.grid.count()) if self.panel.grid.item(n).data(Qt.UserRole+2)=='Master/B')
                pos=self.panel.grid.visualItemRect(item).center(); mime=self.mime()
                enter=QDragEnterEvent(pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(self.panel.grid.viewport(),enter)
                self.assertTrue(enter.isAccepted())
                drop=QDropEvent(QPointF(pos),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(self.panel.grid.viewport(),drop)
                self.assertTrue(drop.isAccepted()); self.assertEqual(self.panel.folder,'Master')
    def test_view_preference_metadata_and_preview_cleanup(self):
        with patch('kinetic_cut.config.save_settings') as save:
            set_view(self.panel,True); save.assert_called_once(); self.assertTrue(self.w.settings['media_pool_list_view'])
        self.assertEqual(self.panel.column_header.model().headerData(2,Qt.Horizontal),'Resolution')
        QApplication.processEvents()
        a=self.panel.grid.visualItemRect(self.panel.grid.item(0)); b=self.panel.grid.visualItemRect(self.panel.grid.item(1))
        self.assertLess(a.bottom(),b.top()); self.assertEqual(self.panel.column_header.height(),26)
        item=next(self.panel.grid.item(n) for n in range(self.panel.grid.count()) if self.panel.grid.item(n).data(Qt.UserRole)=='0')
        self.assertEqual(item.data(Qt.UserRole+3)[2],'320 × 180')
        self.panel.open_grid_item(item); QApplication.processEvents()
        dialogs=self.panel.findChildren(SourcePreview); self.assertEqual(len(dialogs),1); dialogs[0].close()
        for kind in ('audio','video'):
            m=copy.copy(self.media[0]); m.kind=kind
            d=SourcePreview(self.panel,m); d.close(); self.assertTrue(d.player.source().isEmpty())
    def test_blade_undo_redo_preserve_playhead_for_media_and_subtitle(self):
        self.w.seek(1.25); self.w.split_at('v',2.5); self.assertEqual(self.w.project.playhead,1.25)
        self.assertEqual(len(self.w.project.timeline),2)
        self.w.seek(3.5); self.w.undo(); self.assertEqual(self.w.project.playhead,3.5); self.w.redo(); self.assertEqual(self.w.project.playhead,3.5)
        self.w.split_caption_at('c',2.5); self.assertEqual(self.w.project.playhead,3.5); self.assertEqual(len(self.w.project.captions),2)
    def test_monitor_does_not_modify_project_and_compacts(self):
        before=self.w.project.to_dict(); control=self.w.monitor_control
        control.set_level(37); self.assertEqual(self.w.transport.monitor_gain,.37)
        control.toggle(); self.assertEqual(self.w.transport.monitor_gain,0)
        control.toggle(); self.assertEqual(control.level,37); self.assertEqual(before,self.w.project.to_dict())
        self.w.resize(1100,750); QApplication.processEvents(); self.assertTrue(control.slider.isHidden())
        control.popup(); self.assertTrue(control._menu.isVisible()); control._menu.close()
    def test_media_snap_hold_and_fade_corner_priority(self):
        t=self.w.timeline; self.w.project.timeline.append(TimelineItem('other','1','video_1',8,2)); t.set_zoom(50); t.setProperty('snapping',True); t._range(); QApplication.processEvents()
        # The clip may be partly above the independently scrolled video pane.
        # Click its visible body, not its unclipped centre on the subtitle divider.
        visible=t.visible_item_rect(self.w.project.item_by_id('v'))
        self.assertFalse(visible.isEmpty())
        p=visible.center().toPoint()
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=p); QTest.mouseMove(t.viewport(),p+QPoint(145,0))
        self.assertAlmostEqual(t.move_preview[0].start+5,8)
        QTest.mouseMove(t.viewport(),p+QPoint(158,0)); self.assertAlmostEqual(t.move_preview[0].start+5,8)
        QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=p+QPoint(158,0)); self.assertEqual(self.w.project.item_by_id('v').start+5,8)
        QApplication.processEvents()
        t.video_scroll.setValue(t.video_scroll.maximum()); QApplication.processEvents()
        rect=t.item_rect(self.w.project.item_by_id('v')); corner=QPoint(round(rect.left()+4),round(rect.top()+5))
        self.assertTrue(t.visible_item_rect(self.w.project.item_by_id('v')).contains(corner),f'{rect}, {t.section_rect("video_1")}')
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=corner); self.assertEqual(t.drag_mode,'fade_in'); QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=corner)
    def test_wave_thumbnail_has_absolute_green_yellow_red_levels(self):
        samples=Waveform(np.tile([[-32767,32767]],(108,1)))
        with patch('kinetic_cut.waveforms.waveform',return_value=samples):image=wave_image('unused','ffmpeg')
        colours={image.pixelColor(50,y).name() for y in range(4,60)}
        self.assertTrue({'#73ae83','#c4b969','#da6560'}<=colours)
        with patch('kinetic_cut.waveforms.waveform',return_value=Waveform(np.tile([[-2000,2000]],(108,1)))):quiet=wave_image('unused','ffmpeg')
        self.assertEqual(quiet.pixelColor(50,5).name(),'#151719')
