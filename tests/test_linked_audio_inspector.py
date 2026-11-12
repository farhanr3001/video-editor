"""Linked video selection exposes only its linked, editable audio controls."""
import copy,unittest
from unittest.mock import patch
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.config import DEFAULT_SETTINGS
from kinetic_cut.model import Project,MediaItem,TimelineItem

class LinkedAudioInspectorTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([])
        self.load=patch('kinetic_cut.ui.load_settings',return_value=copy.deepcopy(DEFAULT_SETTINGS));self.load.start()
        self.wave=patch('kinetic_cut.ui.MainWindow.request_waveform');self.wave.start()
        self.audio_preview=patch('kinetic_cut.transport.TimelineTransport.processed_audio',return_value='');self.audio_preview.start()
        self.w=MainWindow();self.w.show();self.w.autosave_timer.stop()
        self.p=Project(media=[MediaItem('m','missing.mp4','video','Fixture',8,320,180,30,True)],timeline=[
            TimelineItem('v','m','video_1',0,4,group_id='legacy',link_id='pair'),
            TimelineItem('a','m','audio_1',0,4,gain_db=-8,pan=.25,link_id='pair'),
            TimelineItem('other','m','audio_1',4,4,gain_db=-3,link_id='other')])
        self.w.set_project(self.p);self.w.timeline.linked_selection=True;self.w.timeline.select_ids({'v','a'},'v');self.app.processEvents()
    def tearDown(self):
        self.w.close();self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents();self.load.stop();self.wave.stop();self.audio_preview.stop()
    def test_video_primary_exposes_linked_audio_without_changing_video_tab(self):
        i=self.w.inspector
        self.assertEqual(i.item_id,'v');self.assertEqual([x.id for x in i.targets(True)],['a'])
        self.assertEqual(i.volume.spin.value(),-8);self.assertTrue(i.audio.isEnabled());self.assertFalse(i.audio.isHidden())
        self.assertEqual(i.tabs.currentIndex(),0);i.tabs.setCurrentIndex(1);self.assertTrue(i.audio.isVisible())
        self.assertEqual([x.id for x in i.targets(False)],['v'])
    def test_audio_edit_reset_undo_redo_only_changes_linked_audio(self):
        i=self.w.inspector;self.w.commit_history();video=copy.deepcopy(self.p.item_by_id('v'))
        i.volume.spin.setValue(-12)
        self.assertEqual(self.p.item_by_id('a').gain_db,-12);self.assertEqual(self.p.item_by_id('other').gain_db,-3);self.assertEqual(self.p.item_by_id('v'),video)
        self.w.undo();self.assertEqual(self.w.project.item_by_id('a').gain_db,-8)
        self.w.redo();self.assertEqual(self.w.project.item_by_id('a').gain_db,-12)
        self.w.inspector.reset_audio_section('gain_db');self.assertEqual(self.w.project.item_by_id('a').gain_db,0)
        self.assertEqual(self.w.project.item_by_id('v'),video)
    def test_link_toggle_off_hides_linked_controls_but_direct_audio_still_works(self):
        self.w.link_toggle.click();self.w.refresh_inspector();i=self.w.inspector
        self.assertEqual(i.targets(True),[]);self.assertTrue(i.audio.isHidden())
        self.w.timeline.select_ids({'a'},'a');self.assertEqual([x.id for x in i.targets(True)],['a']);self.assertEqual(i.volume.spin.value(),-8)
    def test_legacy_links_explicit_unlink_and_locked_audio(self):
        self.p.item_by_id('v').link_id=None;self.p.item_by_id('a').link_id=None;self.p.item_by_id('a').group_id='legacy'
        self.w.refresh_inspector();self.assertEqual([x.id for x in self.w.inspector.targets(True)],['a'])
        self.p.item_by_id('a').link_id='';self.w.refresh_inspector();self.assertEqual(self.w.inspector.targets(True),[])
        self.p.item_by_id('a').link_id=None;self.p.track_states['audio_1']={'locked':True};self.w.refresh_inspector()
        self.assertEqual(self.w.inspector.targets(True),[]);self.w.inspector.edit_property('gain_db',-20,0);self.assertEqual(self.p.item_by_id('a').gain_db,-8)
    def test_unrelated_selected_audio_is_not_a_linked_target(self):
        self.w.timeline.select_ids({'v','a','other'},'v');self.assertEqual([x.id for x in self.w.inspector.targets(True)],['a'])
    def test_linked_meter_uses_audio_track(self):
        i=self.w.inspector;i.set_audio_levels({'audio_1':(.5,.25,True)})
        self.assertIn('-6.0',i.level_bars[0].format());self.assertIn('CLIP',i.level_clip.text())
