"""Layout-only mode must preserve live editing widgets and their ownership."""
import copy,time,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QEvent,QEventLoop,QTimer
from PySide6.QtTest import QTest
from PySide6.QtCore import QMimeData
from PySide6.QtGui import QDragEnterEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption
from kinetic_cut.workspace import set_page


class TimelineWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.app.setQuitOnLastWindowClosed(False);cls.app.setProperty('kineticTestDiscardUnsaved',True)
    def wait(self,ms=25):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def setUp(self):
        self.w=MainWindow();self.w.autosave_timer.stop();self.w.request_waveform=lambda _:None;self.w.queue_proxy=lambda _:None;self.w.preview_quality.request=lambda:None
        self.w.set_project(Project(media=[MediaItem('m','missing.png','image','Still',0,640,360)],timeline=[TimelineItem('v','m','video_1',0,15)],captions=[Caption('c',0,2,'Caption')]))
        self.w.resize(1480,900);self.w.show();self.wait();self.mode=self.w.timeline_workspace
    def tearDown(self):
        self.w.transport.playing=False;self.w.close();end=time.monotonic()+10
        while self.w._workers and time.monotonic()<end:self.wait()
        self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete)
    def enter(self):self.w.fullscreen_timeline.click();self.wait()
    def test_button_follows_redo_and_mode_matches_left_timeline_right_preview(self):
        w=self.w;bar=w.timeline_bar;index=bar.indexOf(w.fullscreen_timeline)
        self.assertIn('Redo',bar.itemAt(index-1).widget().toolTip());self.enter()
        self.assertTrue(self.mode.active);self.assertIs(w.timeline_panel.parentWidget(),self.mode.split);self.assertIs(w.viewer_panel.parentWidget(),self.mode.split)
        self.assertGreater(w.timeline_panel.height(),650);self.assertGreater(w.timeline_panel.width(),w.viewer_panel.width()*2)
        self.assertFalse(w.left_stack.isVisible());self.assertFalse(w.right_stack.isVisible());self.assertIs(w.left_panels.header.parentWidget(),self.mode.page)
        self.assertFalse(any(o.isVisible() for o in self.mode.overlays.values()))
    def test_repeated_toggle_preserves_data_history_selection_and_playback(self):
        w=self.w;w.timeline.select_ids({'v'},'v');w.seek(3)
        project=w.project;before=project.to_dict();history=w._history;index=w._history_index;w.transport.playing=True;w.transport.rate=1.5
        for _ in range(5):
            self.mode.set_active(True);self.mode.set_active(False)
            self.assertIs(w.project,project);self.assertIs(w._history,history);self.assertEqual(w._history_index,index)
            self.assertEqual(project.to_dict(),before);self.assertEqual(w.timeline.selected_ids,{'v'});self.assertTrue(w.transport.playing);self.assertEqual(w.transport.rate,1.5)
        self.assertIs(w.timeline_panel.parentWidget(),w.center_split);self.assertIs(w.viewer_panel.parentWidget(),w.viewer_split)
    def test_library_overlays_toggle_without_resizing_and_outside_click_passes_through(self):
        w=self.w;self.enter();sizes=self.mode.split.sizes();height=w.timeline.height()
        w.media_toggle.click();self.wait();panel=self.mode.overlays['Library']
        self.assertTrue(panel.isVisible());self.assertIs(w.left_panels.stack.currentWidget(),w.media_panel)
        w.media_toggle.click();self.assertFalse(panel.isVisible());w.effects_toggle.click();self.wait()
        self.assertIs(w.left_panels.stack.currentWidget(),w.effects_panel);self.assertTrue(panel.isVisible())
        QTest.mouseClick(w.timeline.viewport(),Qt.LeftButton,pos=QPoint(w.timeline.viewport().width()-30,w.timeline.viewport().height()-20));self.wait()
        self.assertFalse(panel.isVisible());self.assertFalse(w.effects_toggle.isChecked());self.assertEqual(self.mode.split.sizes(),sizes);self.assertEqual(w.timeline.height(),height)
    def test_inspector_edits_and_numeric_scrub_commit_to_main_editor_history(self):
        w=self.w;w.timeline.select_ids({'v'},'v');w.select_item('v');self.enter();w.inspector_toggle.click();self.wait()
        overlay=self.mode.overlays['Inspector'];self.assertTrue(overlay.isVisible());self.assertIs(w.inspector.parentWidget(),overlay)
        below=w.inspector_toggle.mapToGlobal(QPoint(w.inspector_toggle.width(),w.inspector_toggle.height()))
        self.assertEqual(overlay.y(),below.y()+4)
        self.assertEqual(overlay.x()+overlay.width(),w.viewer_panel.mapToGlobal(QPoint()).x()-6)
        row=w.inspector.zoom_x;before=w._history_index
        row.scrub_history(True);self.assertTrue(w._property_scrubbing);row.spin.setValue(1.4);row.spin.setValue(1.5);row.scrub_history(False)
        self.assertFalse(w._property_scrubbing);self.assertEqual(w._history_index,before+1);self.assertAlmostEqual(w.project.timeline[0].transform.scale,1.5)
        w.undo();self.assertEqual(w.project.timeline[0].transform.scale,1.);w.inspector_toggle.click();self.assertFalse(overlay.isVisible())
    def test_restore_previous_panels_sizes_and_original_docked_toggle_behavior(self):
        w=self.w;w.left_panels.select('Effects');w.inspector_toggle.setChecked(False);sizes=w.center_split.sizes();upper=w.workspace_split.sizes()
        self.enter();w.media_toggle.click();w.inspector_toggle.click();self.wait();w.fullscreen_timeline.click();self.wait()
        self.assertEqual(w.left_panels.active,'Effects');self.assertFalse(w.inspector_toggle.isChecked());self.assertFalse(any(o.isVisible() for o in self.mode.overlays.values()))
        self.assertEqual(w.center_split.sizes(),sizes);self.assertEqual(w.workspace_split.sizes(),upper)
        self.assertIs(w.inspector.parentWidget(),w.right_stack);self.assertIs(w.left_panels.stack.parentWidget(),w.left_panels)
        self.assertIs(w.right_stack.currentWidget(),w.inspector)
        self.assertIs(w.left_stack.currentWidget(),w.left_panels)
        self.assertFalse(w.viewer_split.handle(1).isEnabled())
        w.media_toggle.click();w.inspector_toggle.click();self.wait();self.assertTrue(w.right_stack.isVisible());self.assertIs(w.left_panels.stack.currentWidget(),w.media_panel)
        self.assertFalse(any(o.isVisible() for o in self.mode.overlays.values()))
    def test_deliver_temporarily_restores_normal_and_return_keeps_edit_mode_choice(self):
        w=self.w;self.enter();w.effects_toggle.click();set_page(w,1);self.wait()
        self.assertFalse(self.mode.active);self.assertFalse(w.fullscreen_timeline.isEnabled());self.assertIs(w.timeline_panel.parentWidget(),w.center_split)
        self.assertFalse(any(o.isVisible() for o in self.mode.overlays.values()));self.assertTrue(w.timeline.read_only)
        set_page(w,0);self.wait();self.assertTrue(self.mode.active);self.assertFalse(w.timeline.read_only);self.assertTrue(w.fullscreen_timeline.isChecked())
    def test_timeline_switch_and_new_project_keep_workspace_without_stale_panels(self):
        w=self.w;first=w.project.active_timeline_id;self.enter();second=w.timeline_sessions.create('Another')
        self.assertTrue(self.mode.active);self.assertFalse(w.project.timeline);w.timeline_sessions.switch(first)
        self.assertEqual(w.project.timeline[0].id,'v');self.assertIs(w.timeline_selector.parentWidget(),w.timeline_panel)
        w.set_project(Project());self.assertTrue(self.mode.active);self.assertFalse(w.project.timeline)
        self.mode.set_active(False);self.assertIs(w.viewer_panel.parentWidget(),w.viewer_split)
    def test_compact_toolbar_splitter_and_overlay_geometry_fit_window(self):
        w=self.w;w.resize(1100,700);self.wait();self.enter()
        for sizes in ((800,290),(680,410)):
            self.mode.split.setSizes(sizes);self.wait();self.assertTrue(w.monitor_control.compact)
            for widget in (w.fullscreen_timeline,w.timeline_selector,w.monitor_control):
                rect=widget.geometry();self.assertGreaterEqual(rect.left(),0);self.assertLessEqual(rect.right(),w.timeline_panel.width())
            w.media_toggle.click();self.wait();overlay=self.mode.overlays['Library']
            self.assertTrue(w.frameGeometry().contains(overlay.frameGeometry()));w.media_toggle.click()
        self.mode.set_active(False);w.resize(1480,900);self.wait();self.assertFalse(w.monitor_control.compact);self.assertFalse(w.timeline_zoom.isHidden())
    def test_original_popup_commands_are_unchanged_in_fullscreen(self):
        w=self.w;callbacks=['generate_captions','generate_tts_dialogue','open_media_downloader'];self.enter()
        self.assertEqual([b.text() for b in w.edit_actions],['Generate Captions','Generate TTS Dialogue','Download Media'])
        self.assertTrue(all(b.isVisible() for b in w.edit_actions));self.assertIs(w.edit_actions[0].parentWidget(),w.left_panels.header)
    def test_drag_out_dismisses_library_so_short_clips_remain_reachable(self):
        self.enter();self.w.effects_toggle.click();self.wait();overlay=self.mode.overlays['Library'];self.assertTrue(overlay.isVisible())
        mime=QMimeData();mime.setData('application/x-kinetic-effect',b'Sepia')
        event=QDragEnterEvent(QPoint(self.w.timeline.viewport().width()-20,self.w.timeline.viewport().height()-20),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        self.assertFalse(self.mode.eventFilter(self.w.timeline.viewport(),event));self.assertFalse(overlay.isVisible());self.assertTrue(self.mode.active)
    def test_bottom_timeline_popup_opens_above_and_normal_popup_below(self):
        self.enter();combo=self.w.timeline_selector;animate=self.app.isEffectEnabled(Qt.UI_AnimateCombo);combo.showPopup();self.wait()
        self.assertTrue(combo.view().window().isVisible());self.assertEqual(self.app.isEffectEnabled(Qt.UI_AnimateCombo),animate)
        self.assertLessEqual(combo.view().window().geometry().bottom(),combo.mapToGlobal(QPoint()).y())
        combo.hidePopup();self.mode.set_active(False);self.wait();combo.showPopup();self.wait()
        self.assertGreaterEqual(combo.view().window().geometry().top(),combo.mapToGlobal(QPoint(0,combo.height())).y()-1);combo.hidePopup()
    def test_caption_auto_open_inspector_stays_left_of_preview_and_follows_splitter(self):
        w=self.w;self.enter();w.timeline.select_captions({'c'},'c');w.select_caption('c');self.wait()
        overlay=self.mode.overlays['Inspector'];self.assertTrue(overlay.isVisible())
        for sizes in ((950,520),(700,770)):
            self.mode.split.setSizes(sizes);self.wait()
            self.assertEqual(overlay.x()+overlay.width(),w.viewer_panel.mapToGlobal(QPoint()).x()-6)
            self.assertTrue(w.frameGeometry().contains(overlay.frameGeometry()))


if __name__=='__main__':unittest.main()
