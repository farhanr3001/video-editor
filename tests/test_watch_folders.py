import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtCore import Qt, QPoint, QPointF, QMimeData, QThreadPool, QEvent
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QDragLeaveEvent
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtTest import QTest

from kinetic_cut.model import MediaItem, Project
from kinetic_cut.watch_folders import Folder, folder_key, index_folders
from kinetic_cut.ui import MainWindow
from kinetic_cut.workspace import PowerBins


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name); self.key=folder_key(self.path)
        self.state={self.key:Folder(str(self.path))}; self.cancel=threading.Event()
        self.loader=Mock(side_effect=lambda p,*a,**kw:MediaItem('original',p,Path(p).suffix[1:],Path(p).name))
    def scan(self,now,**kw):
        self.state,more=index_folders(self.state,'ffprobe','ffmpeg',self.cancel,now=now,loader=self.loader,**kw)
        return self.state[self.key].media(),more
    def file(self,name='Clip.MP4'):path=self.path/name; path.write_bytes(b'fixture'); return path
    def test_supported_direct_files_and_stability(self):
        for name in ('Clip.MP4','Photo.PNG','Sound.WAV','notes.txt'):self.file(name)
        sub=self.path/'Sub'; sub.mkdir(); (sub/'nested.mp4').write_bytes(b'x')
        self.assertFalse(self.scan(0)[0]); self.assertEqual(self.loader.call_count,0)
        media,_=self.scan(1.1)
        self.assertEqual({m.name for m in media},{'Clip.MP4','Photo.PNG','Sound.WAV'})
        self.assertTrue(all(m.id.startswith('watch:') for m in media))
        self.scan(2); self.assertEqual(self.loader.call_count,3)
    def test_growing_copy_waits_and_replacement_keeps_identity(self):
        p=self.file(); self.scan(0); p.write_bytes(b'longer ongoing copy')
        self.assertFalse(self.scan(1.1)[0]); self.assertFalse(self.scan(1.5)[0])
        first=self.scan(2.2)[0][0]; p.write_bytes(b'replacement completed media')
        self.assertFalse(self.scan(3.3)[0]); second=self.scan(4.5)[0][0]
        self.assertEqual(first.id,second.id); self.assertEqual(self.loader.call_count,2)
    def test_bad_file_retry_and_changed_file_resets_backoff(self):
        p=self.file(); self.loader.side_effect=ValueError('partial video')
        self.scan(0); self.scan(1.1); self.scan(2); self.assertEqual(self.loader.call_count,1)
        self.loader.side_effect=lambda p,*a,**kw:MediaItem('ok',p,'video',Path(p).name)
        self.assertTrue(self.scan(3.2)[0]); self.assertEqual(self.loader.call_count,2)
        p.write_bytes(b'new'); self.scan(4); self.assertTrue(self.scan(5.1)[0])
    def test_post_probe_change_is_not_published(self):
        p=self.file(); self.scan(0)
        def changing(path,*a,**kw):
            p.write_bytes(b'changed while ffprobe was running')
            return MediaItem('ok',path,'video','Clip')
        self.loader.side_effect=changing
        self.assertFalse(self.scan(1.1)[0]); self.assertEqual(self.loader.call_count,1)
    def test_delete_unavailable_recreate_and_batch_bound(self):
        for n in range(9):self.file(f'{n}.png')
        self.scan(0); media,more=self.scan(1.1,batch=3)
        self.assertEqual(len(media),3); self.assertTrue(more)
        self.scan(1.2,batch=3); self.assertEqual(len(self.scan(1.3,batch=3)[0]),9)
        self.path.rename(self.path.with_name(self.path.name+'-moved'))
        try:
            self.assertFalse(self.scan(2)[0]); self.assertFalse(self.state[self.key].available)
            self.path.mkdir(); p=self.file('returned.png'); self.scan(3)
            self.assertEqual(len(self.scan(4.1)[0]),1); p.unlink(); self.assertFalse(self.scan(5)[0])
        finally:
            moved=self.path.with_name(self.path.name+'-moved')
            for file in moved.iterdir():file.unlink()
            moved.rmdir()
    def test_cancellation_and_input_state_are_immutable(self):
        self.file(); original=self.state; self.scan(0)
        self.assertFalse(original[self.key].entries)
        before=copy.deepcopy(self.state); self.scan(1.1)
        self.assertEqual(self.state[self.key].entries.keys(),before[self.key].entries.keys())
        self.assertFalse(next(iter(before[self.key].entries.values())).media)
        self.cancel.set(); state,_=index_folders(self.state,'','',self.cancel,loader=self.loader)
        self.assertFalse(state)
    def test_same_leaf_name_separate_paths_and_duplicate_normalization(self):
        other=self.path/'Other'; other.mkdir()
        self.assertNotEqual(folder_key(self.path),folder_key(other))
        self.assertEqual(folder_key(self.path),folder_key(self.path/'..'/self.path.name))


class WatchPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.w=MainWindow(); self.w.resize(1480,900); self.w.show(); self.w.autosave_timer.stop()
        self.panel=self.w.media_panel; self.watch=self.panel.watch_folders
        self.watch.timer.stop(); self.watch.debounce.stop(); self.watch.folders={}
        self.panel.power=PowerBins(self.root/'power.json')
        self.folder=self.root/'My Clips'; self.folder.mkdir()
        self.image=self.folder/'Photo One.png'; Image.new('RGB',(160,90),'blue').save(self.image)
        self.saved=patch('kinetic_cut.config.save_settings'); self.save=self.saved.start(); self.addCleanup(self.saved.stop)
        self.key=self.watch.add(str(self.folder)); self.watch.debounce.stop()
        self.index()
        self.panel.folder=self.key; self.panel.rebuild_tree(); self.panel.refresh()
        QApplication.processEvents()
    def index(self):
        state,_=index_folders(self.watch.folders,'ffprobe','ffmpeg',self.watch.cancel,now=0)
        state,_=index_folders(state,'ffprobe','ffmpeg',self.watch.cancel,now=2)
        self.watch.folders=state
    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); QApplication.processEvents()
        self.w.deleteLater(); QApplication.sendPostedEvents(None,QEvent.DeferredDelete); QApplication.processEvents()
        self.temp.cleanup()
    def mime(self):
        ids=[m.id for m in self.watch.folders[self.key].media()]
        mime=QMimeData(); mime.setData('application/x-kinetic-media-id',ids[0].encode())
        mime.setData('application/x-kinetic-media-ids',json.dumps(ids).encode()); return mime
    def drag(self,widget,mime,pos,drop=True):
        self._mime=mime
        enter=QDragEnterEvent(pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(widget,enter)
        self.assertTrue(enter.isAccepted())
        move=QDragMoveEvent(pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(widget,move)
        if not drop:return move
        event=QDropEvent(QPointF(pos),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(widget,event); return event
    def test_context_chooser_duplicate_and_persistence(self):
        self.panel.project_context(QPoint(10,110)); menu=self.panel._menu
        self.assertEqual(menu.actions()[0].text(),'Watch Folder…'); menu.close()
        with patch.object(QFileDialog,'getExistingDirectory',return_value=str(self.folder)):
            menu.actions()[0].trigger()
        self.assertEqual(len(self.watch.folders),1); self.assertEqual(self.panel.folder,self.key)
        self.assertEqual(self.panel.project_tree.topLevelItem(1).text(0),'My Clips')
        self.assertEqual(self.w.settings['media_watch_folders'],[str(self.folder)])
        from kinetic_cut.watch_folders import WatchFolders
        restored=WatchFolders(self.panel); self.assertEqual(set(restored.folders),{self.key}); restored.stop(); restored.deleteLater()
    def test_watch_option_is_only_in_upper_folder_area(self):
        self.panel.project_context(QPoint(10,110))
        self.assertIn('Watch Folder…',[a.text() for a in self.panel._menu.actions()]); self.panel._menu.close()
        for pos in (QPoint(10,10),self.panel.grid.visualItemRect(self.panel.grid.item(0)).center()):
            self.panel.media_context(pos)
            self.assertEqual([a.text() for a in self.panel._menu.actions()],['Open Folder in Explorer','Refresh Folder']); self.panel._menu.close()
        tree=self.panel.project_tree
        self.panel.project_context(tree.visualItemRect(tree.topLevelItem(1)).center())
        self.assertEqual([a.text() for a in self.panel._menu.actions()],['Remove Watch Folder']); self.panel._menu.close()
        self.panel.context(QPoint(10,110))
        self.assertNotIn('Watch Folder…',[a.text() for a in self.panel._menu.actions()]); self.panel._menu.close()
    def test_selection_and_cancelled_drag_do_not_import(self):
        before=self.w.project.to_dict(); item=self.panel.grid.item(0); item.setSelected(True)
        self.assertEqual(self.panel.materialize(item.data(Qt.UserRole)),item.data(Qt.UserRole))
        t=self.w.timeline; pos=QPoint(round(t.x_for_time(2)),round(t.track_rect('video_1').center().y()))
        self.drag(t.viewport(),self.mime(),pos,False); QApplication.sendEvent(t.viewport(),QDragLeaveEvent())
        self.assertEqual(self.w.project.to_dict(),before); self.assertFalse(t.incoming_preview)
    def test_actual_drag_payload_retains_watch_source_without_importing(self):
        self.panel.grid.item(0).setSelected(True)
        with patch('kinetic_cut.workspace.QDrag') as drag:
            self.panel.grid.startDrag(Qt.CopyAction)
            data=drag.return_value.setMimeData.call_args.args[0]
            source=json.loads(bytes(data.data('application/x-kinetic-power-source')))
            self.assertEqual(source['folder'],self.key)
            self.assertEqual(source['ids'],[self.panel.grid.item(0).data(Qt.UserRole)])
            self.assertEqual(bytes(data.data('application/x-kinetic-media-id')).decode(),source['ids'][0])
        self.assertFalse(self.w.project.media)
    def test_timeline_drop_imports_once_and_undo_redo(self):
        t=self.w.timeline; t.video_scroll.setValue(t.video_scroll.maximum()); QApplication.processEvents()
        pos=QPoint(round(t.x_for_time(2)),round(t.track_rect('video_1').center().y()))
        self.assertTrue(self.drag(t.viewport(),self.mime(),pos).isAccepted())
        self.assertEqual(len(self.w.project.media),1); self.assertEqual(len(self.w.project.timeline),1)
        self.w.undo(); self.assertFalse(self.w.project.media); self.assertFalse(self.w.project.timeline)
        self.w.redo(); self.assertEqual(len(self.w.project.media),1)
        self.w.add_media_to_track(self.mime().data('application/x-kinetic-media-id').data().decode(),'video_1',8)
        self.assertEqual(len(self.w.project.media),1); self.assertEqual(len(self.w.project.timeline),2)
    def test_master_sidebar_and_grid_drops_are_undoable(self):
        tree=self.panel.project_tree; pos=tree.visualItemRect(tree.topLevelItem(0)).center()
        self.assertTrue(self.drag(tree.viewport(),self.mime(),pos).isAccepted())
        self.assertEqual(len(self.w.project.media),1); self.assertFalse(self.w.project.timeline)
        self.w.undo(); self.assertFalse(self.w.project.media)
        mime=self.mime(); self.panel.folder='project'; self.panel.refresh()
        self.assertTrue(self.drag(self.panel.grid.viewport(),mime,QPoint(150,130)).isAccepted())
        self.assertEqual(len(self.w.project.media),1)
        self.assertTrue(self.panel.import_to_master(mime)); self.assertEqual(len(self.w.project.media),1)
    def test_live_refresh_preserves_selection_and_does_not_rebuild_unchanged(self):
        first=self.panel.grid.item(0); first.setSelected(True); self.panel.grid.setCurrentItem(first)
        Image.new('RGB',(160,90),'red').save(self.folder/'Later.png'); self.index(); self.panel.watches_changed()
        self.assertEqual(self.panel.grid.count(),2)
        self.assertEqual(self.panel.grid.selectedItems()[0].text(),'Photo One.png')
        with patch.object(self.panel,'refresh') as refresh:self.panel.watches_changed(); refresh.assert_not_called()
        self.assertFalse(self.w.project.media)
    def test_watched_bins_cannot_delete_or_write_into_source_folder(self):
        self.panel.grid.item(0).setSelected(True); before=copy.deepcopy(self.panel.power.data)
        QTest.keyClick(self.panel.grid,Qt.Key_Delete); self.assertTrue(self.image.is_file())
        self.panel.on_import([MediaItem('x','elsewhere.png','image','Elsewhere')])
        self.assertEqual(self.panel.power.data,before)
        enter=QDragEnterEvent(QPoint(10,10),Qt.CopyAction,self.mime(),Qt.LeftButton,Qt.NoModifier)
        self.panel.grid.dragEnterEvent(enter); self.assertFalse(enter.isAccepted())
        self.assertIsNone(self.panel.power_bin_target(self.panel.grid.viewport().mapToGlobal(QPoint(10,10))))
    def test_remove_watch_retains_imported_media_and_ignores_late_result(self):
        self.panel.import_to_master(self.mime()); before=self.w.project.to_dict(); indexed=copy.deepcopy(self.watch.folders)
        self.panel.remove_watch_folder(self.key); self.assertEqual(self.panel.folder,'project')
        self.watch.indexed((indexed,False)); self.assertFalse(self.watch.folders)
        self.assertEqual(self.w.project.to_dict(),before); self.assertTrue(self.image.is_file())
    def test_worker_discovers_addition_automatically_and_stops_on_close(self):
        Image.new('RGB',(180,100),'green').save(self.folder/'Auto.png')
        self.watch.timer.setInterval(200); self.watch.timer.start(); self.watch.schedule()
        deadline=time.monotonic()+8
        while self.panel.grid.count()!=2 and time.monotonic()<deadline:QTest.qWait(25)
        self.assertEqual(self.panel.grid.count(),2); self.assertFalse(self.w.project.media)
        self.w.close(); self.assertTrue(self.watch.closed); self.assertTrue(self.watch.cancel.is_set())
        self.assertFalse(self.watch.timer.isActive()); self.assertFalse(self.watch.watcher.directories())
