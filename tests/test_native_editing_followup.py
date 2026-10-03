"""Real spin-box event targets, graphic handles and Windows delete-sharing."""
import os,tempfile,unittest
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QThreadPool,QUrl
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem,MediaItem
from kinetic_cut.graphics import GRAPHICS_CATALOG,default_graphic_data
from kinetic_cut.media_source import open_shared_media,set_media_source


class NativeEditingFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.w=MainWindow(); self.w.autosave_timer.stop(); self.w.resize(1480,900); self.w.show(); self.app.processEvents()

    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); self.w.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()

    def move(self,widget,point):
        QApplication.sendEvent(widget,QMouseEvent(QEvent.MouseMove,QPointF(point),QPointF(widget.mapToGlobal(point)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))

    def test_inspector_enter_on_spin_box_not_line_edit_retains_scrubbing(self):
        p=Project(media=[MediaItem('m','missing.png','image','fixture',10,1920,1080)],timeline=[TimelineItem('v','m','video_1',0,5)])
        self.w.set_project(p); self.w.timeline.select_ids({'v'},'v'); self.app.processEvents()
        spin=self.w.inspector.zoom_x.spin; line=spin.lineEdit()
        for value,key in [('1.234',Qt.Key_Return),('1.456',Qt.Key_Enter)]:
            QTest.mouseDClick(line,Qt.LeftButton); QTest.keyClicks(spin,value); QTest.keyClick(spin,key); self.app.processEvents()
            self.assertAlmostEqual(p.timeline[0].transform.scale,float(value),places=3)
            self.assertFalse(line.hasFocus()); self.assertFalse(line.hasSelectedText()); self.assertFalse(spin._typing)
            QTest.mousePress(line,Qt.LeftButton,pos=QPoint(10,10)); self.assertIsNotNone(spin._drag_start)
            self.move(line,QPoint(20,10)); QTest.mouseRelease(line,Qt.LeftButton,pos=QPoint(20,10))
            self.assertGreater(spin.value(),float(value))

    def test_all_graphic_catalog_items_resize_rotate_move_and_sync_inspector(self):
        for name in GRAPHICS_CATALOG:
            with self.subTest(graphic=name):
                item=TimelineItem('g','','video_1',0,5,role='graphic',graphic_type=name,graphic_data=default_graphic_data(name))
                p=Project(timeline=[item]); p.playhead=.5; self.w.set_project(p); self.w.timeline.select_ids({'g'},'g'); self.app.processEvents()
                preview=self.w.preview; rect=preview._visible_items()[0][2]; anchor,corners,_,handle,_=preview._transform_geometry(item,rect)
                corner=corners[1].toPoint(); dest=(anchor+(corners[1]-anchor)*1.3).toPoint()
                QTest.mousePress(preview,Qt.LeftButton,pos=corner); self.assertEqual(preview.drag_mode,'scale')
                self.move(preview,dest); QTest.mouseRelease(preview,Qt.LeftButton,pos=dest); self.app.processEvents()
                self.assertGreater(item.transform.scale,1); self.assertAlmostEqual(self.w.inspector.gtr_scale.spin.value(),item.transform.scale,places=3)
                rect=preview._visible_items()[0][2]; anchor,_,_,handle,_=preview._transform_geometry(item,rect)
                dest=(anchor+QPointF(50,0)).toPoint(); QTest.mousePress(preview,Qt.LeftButton,pos=handle.toPoint()); self.assertEqual(preview.drag_mode,'rotate')
                self.move(preview,dest); QTest.mouseRelease(preview,Qt.LeftButton,pos=dest); self.app.processEvents()
                self.assertAlmostEqual(item.transform.rotation,90,delta=2); self.assertEqual(self.w.inspector.gtr_rot.spin.value(),round(item.transform.rotation))
                rect=preview._visible_items()[0][2]; center=preview._transform_geometry(item,rect)[1][0]
                # Body hit away from anchor/resize/rotate handles.
                body=(center+preview._transform_geometry(item,rect)[1][2])/2
                body+=(preview._transform_geometry(item,rect)[1][1]-center)*.25+(preview._transform_geometry(item,rect)[1][3]-center)*.25
                old=item.transform.x; QTest.mousePress(preview,Qt.LeftButton,pos=body.toPoint()); self.assertEqual(preview.drag_mode,'move'); self.move(preview,(body+QPointF(10,0)).toPoint()); QTest.mouseRelease(preview,Qt.LeftButton,pos=(body+QPointF(10,0)).toPoint())
                self.assertNotEqual(item.transform.x,old)

    @unittest.skipUnless(os.name=='nt','Windows handle sharing')
    def test_seekable_read_handle_allows_rename_delete_without_losing_open_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.mp4'; source.write_bytes(b'0123456789'); renamed=source.with_name('renamed.mp4')
            device=open_shared_media(str(source),self.w)
            try:
                source.rename(renamed); renamed.unlink()
                self.assertFalse(source.exists()); self.assertTrue(device.seek(4)); self.assertEqual(bytes(device.read(3)),b'456')
            finally:device.close(); device.deleteLater()

    def test_graphic_side_resize_preserves_other_axis_updates_inspector_and_resets(self):
        item=TimelineItem('g','','video_1',0,5,role='graphic',graphic_type='Rectangle',graphic_data=default_graphic_data('Rectangle'))
        p=Project(timeline=[item]); p.playhead=.5; self.w.set_project(p); self.w.timeline.select_ids({'g'},'g'); self.app.processEvents()
        preview=self.w.preview
        for side,mode in [(1,'scale_x'),(0,'scale_y')]:
            rect=preview._visible_items()[0][2]; anchor,_,sides,_,_=preview._transform_geometry(item,rect)
            before=(item.transform.scale,item.transform.effective_scale_y); handle=sides[side].toPoint(); dest=(anchor+(sides[side]-anchor)*1.5).toPoint()
            QTest.mousePress(preview,Qt.LeftButton,pos=handle); self.assertEqual(preview.drag_mode,mode)
            self.move(preview,dest); QTest.mouseRelease(preview,Qt.LeftButton,pos=dest)
            if mode=='scale_x':self.assertEqual(item.transform.effective_scale_y,before[1]); self.assertGreater(item.transform.scale,before[0])
            else:self.assertEqual(item.transform.scale,before[0]); self.assertGreater(item.transform.effective_scale_y,before[1])
            self.assertAlmostEqual(self.w.inspector.gtr_scale_y.spin.value(),item.transform.effective_scale_y,places=3)
        self.w.inspector.reset_graphic_transform(); self.assertEqual((item.transform.scale,item.transform.effective_scale_y),(1,1))

    def test_graphic_export_preserves_preview_axis_scales_and_clockwise_rotation(self):
        from kinetic_cut.graphics import graphic_to_ass_events
        for name in GRAPHICS_CATALOG:
            with self.subTest(graphic=name):
                item=TimelineItem('g','','video_1',0,5,role='graphic',graphic_type=name,graphic_data=default_graphic_data(name))
                item.transform.scale=1.4; item.transform.scale_y=1.8; item.transform.rotation=37
                events=graphic_to_ass_events(Project(timeline=[item]),item)
                self.assertTrue(events)
                self.assertTrue(all('\\fscx140.000\\fscy180.000\\frz-37.000' in event for event in events))

    @unittest.skipUnless(os.name=='nt','Windows handle sharing')
    def test_player_device_replacement_and_clear_close_old_handles(self):
        from PySide6.QtMultimedia import QMediaPlayer
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'fixture.mp4'; source.write_bytes(b'invalid-media')
            player=QMediaPlayer(self.w); url=QUrl.fromLocalFile(str(source)); set_media_source(player,url)
            old=player._shared_media_device; self.assertIs(player.sourceDevice(),old); self.assertEqual(player.source(),url)
            set_media_source(player,QUrl()); self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
            self.assertIsNone(player.sourceDevice()); self.assertIsNone(player._shared_media_device); source.unlink(); player.deleteLater()
