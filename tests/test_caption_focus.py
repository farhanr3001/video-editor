import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PySide6.QtCore import Qt,QEvent,QThreadPool,QMimeData,QPointF
from PySide6.QtGui import QImage,QColor,QDragMoveEvent,QDragLeaveEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption
from kinetic_cut.pool_tools import SourcePreview
from kinetic_cut.workspace import PowerBins,set_page


class CaptionFocusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.w=MainWindow(); self.w.resize(1400,850); self.w.show(); self.w.autosave_timer.stop()
        self.image=Path(self.temp.name)/'image.png'; image=QImage(320,180,QImage.Format_RGB32); image.fill(Qt.red); image.save(str(self.image))
        self.p=Project(media=[MediaItem('m',str(self.image),'image','Picture',5,320,180)],timeline=[TimelineItem('v','m','video_1',0,5)],captions=[Caption('one',1,2,'First caption'),Caption('two',3,4,'Second caption')])
        self.p.timeline[0].effects=[{'name':'Gaussian Blur','enabled':True}]
        self.w.set_project(self.p); QApplication.processEvents()
    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); QApplication.processEvents(); self.w.deleteLater(); QApplication.sendPostedEvents(None,QEvent.DeferredDelete); self.temp.cleanup()
    def test_selection_navigation_wrap_no_history_and_restore_view(self):
        w=self.w; w.preview.view_zoom=1.7; history=len(w._history); w.caption_focus_button.setChecked(True)
        w.timeline.select_captions({'two'},'two'); self.assertEqual(w.project.playhead,3)
        w.caption_focus.navigate(1); self.assertEqual(w.timeline.selected_caption,'one'); self.assertEqual(w.project.playhead,1)
        w.caption_focus.navigate(-1); self.assertEqual(w.timeline.selected_caption,'two'); self.assertEqual(len(w._history),history)
        w.caption_focus_button.setChecked(False); self.assertEqual(w.preview.view_zoom,1.7)
        w.timeline.select_captions({'one'},'one'); self.assertEqual(w.project.playhead,3)
    def test_focus_paint_never_enumerates_video_or_effects_and_paused_text_visible(self):
        w=self.w; self.p.captions[0].customize=True; self.p.captions[0].style.animation='fade'; w.caption_focus_button.setChecked(True); w.timeline.select_captions({'one'},'one')
        before=copy.deepcopy(self.p.to_dict())
        with patch.object(w.preview,'_visible_items',side_effect=AssertionError('Video path entered')),patch('kinetic_cut.vision_effects.apply',side_effect=AssertionError('Effect entered')):
            image=w.preview.grab().toImage()
        self.assertIn(('caption','one'),w.preview.text_rects); self.assertEqual(before,self.p.to_dict())
        rect=w.preview.composition_rect(); self.assertEqual(image.pixelColor(round(rect.center().x()),round(rect.top()+10)),QColor(Qt.black))
        self.assertEqual(w.preview._visible_items(),[])
    def test_transport_skips_active_and_warm_video_retains_audio(self):
        w=self.w; t=w.transport; self.p.media[0].kind='video'; self.p.media[0].has_audio=True
        self.p.timeline.extend([TimelineItem('future','m','video_1',5,2),TimelineItem('a','m','audio_1',0,5)])
        from kinetic_cut.transitions import Transition
        self.p.transitions=[Transition('focus-transition','Cross Dissolve',start=4.5,duration=1.,left_item_id='v',right_item_id='future')]
        created=[]
        def create(key,media,video,audio_path):
            player=Mock(); player.position.return_value=0; output=Mock(); output.property.return_value=.5
            t.decoders[key]=(player,output,Mock() if video else None); created.append(video)
        with patch.object(t,'create_decoder',side_effect=create),patch.object(t,'processed_audio',return_value=''),patch('kinetic_cut.transport.QMetaObject.invokeMethod'):
            t._project=self.p; t.position=4.5; t.sync(); self.assertIn(True,created)
            created.clear(); w.caption_focus_button.setChecked(True); t.position=4.6; t.sync(); t.poll_frames()
            self.assertNotIn(True,created); self.assertTrue(t.decoders); self.assertTrue(all(sink is None for _,_,sink in t.decoders.values())); self.assertFalse(t.frame_timer.isActive())
            w.caption_focus_button.setChecked(False); self.assertIn(True,created)
            self.p.timeline[0].muted=True; self.p.timeline[1].muted=True
            created.clear(); t.position=4.6; t.sync()
            self.assertNotIn(True,created); self.assertTrue(t.decoders)
            self.assertTrue(all(sink is None for _,_,sink in t.decoders.values()))
            t.decoders.clear(); t.frame_timer.stop()
    def test_deliver_disables_focus_and_delete_is_undoable(self):
        w=self.w; w.caption_focus_button.setChecked(True); w.timeline.select_captions({'one'},'one'); w.caption_focus.delete()
        self.assertEqual(len(w.project.captions),1); w.undo(); self.assertEqual(len(w.project.captions),2)
        set_page(w,1); self.assertFalse(w.caption_focus.active); self.assertFalse(w.caption_focus_button.isEnabled()); set_page(w,0)
    def test_source_popup_owns_space_and_returns_timeline_focus(self):
        d=SourcePreview(self.w.media_panel,self.p.media[0]); d.player=Mock(); d.player.playbackState.return_value=__import__('PySide6.QtMultimedia',fromlist=['QMediaPlayer']).QMediaPlayer.PlayingState
        with patch.object(self.w,'toggle_play') as timeline_play:
            d.show(); QApplication.processEvents(); d.player.play.assert_called_once()
            QTest.keyClick(d,Qt.Key_Space); d.player.pause.assert_called_once(); timeline_play.assert_not_called()
            d.close(); QApplication.processEvents(); self.assertTrue(self.w.timeline.viewport().hasFocus()); d.player.stop.assert_called()
    def test_folder_hover_tiles_tree_and_clear(self):
        panel=self.w.media_panel; panel.power=PowerBins(Path(self.temp.name)/'bins.json'); panel.power.add_folder('Master/Target'); panel.folder='Master'; panel.rebuild_tree(); panel.refresh(); QApplication.processEvents()
        mime=QMimeData(); mime.setData('application/x-kinetic-media-id',b'm')
        for view,item in [(panel.grid,panel.grid.item(0)),(panel.tree,panel.tree.topLevelItem(0).child(0))]:
            pos=view.visualItemRect(item).center(); event=QDragMoveEvent(pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
            view.dragMoveEvent(event); self.assertIsNotNone(view.folder_hover_rect); self.assertEqual(panel.folder,'Master')
            if view is panel.grid:view.eventFilter(view.viewport(),QDragLeaveEvent())
            else:view.dragLeaveEvent(QDragLeaveEvent())
            self.assertIsNone(view.folder_hover_rect)
