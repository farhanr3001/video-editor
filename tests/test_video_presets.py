import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtCore import QEvent, QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtTest import QTest
from kinetic_cut.model import Project, MediaItem, TimelineItem, Crop
from kinetic_cut.ui import MainWindow
from kinetic_cut.video_presets import KEY, HIDDEN_KEY, capture, validate, apply, PresetNameDialog
from kinetic_cut.config import load_settings


class VideoPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000)
        self.app.processEvents(); self.w.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete); self.app.processEvents()

    def setUp(self):
        self.w = MainWindow(); self.w.autosave_timer.stop()
        self.w.settings[KEY] = []
        p = Project(media=[MediaItem('m', 'missing.mp4', 'video', 'fixture', 30, 1920, 1080),
                           MediaItem('large', 'missing.png', 'image', 'large', 30, 3840, 2160)],
                    timeline=[TimelineItem('v', 'm', 'video_1', 1, 2),
                              TimelineItem('v2', 'large', 'video_1', 4, 2),
                              TimelineItem('audio', 'm', 'audio_1', 1, 2)])
        self.w.set_project(p); self.w.resize(1400, 850); self.w.show(); self.app.processEvents()
        self.w.timeline.select_ids({'v'}, 'v'); self.w.select_item('v')
        self.strip = self.w.inspector.video_presets; self.strip.reload()

    def save(self, name):
        def enter():
            dialog = self.app.activeModalWidget()
            self.assertIsInstance(dialog, PresetNameDialog)
            dialog.name.setText(name); QTest.mouseClick(dialog.save, Qt.LeftButton)
        QTimer.singleShot(0, enter); self.strip.save_preset()

    def choose_prompt(self, label):
        def click():
            dialog = self.app.activeModalWidget(); self.assertIsInstance(dialog, QMessageBox)
            button = next(b for b in dialog.buttons() if b.text().replace('&', '') == label)
            QTest.mouseClick(button, Qt.LeftButton)
        QTimer.singleShot(0, click)

    def test_empty_saved_selection_and_default_on_reopen(self):
        self.assertEqual(self.strip.combo.currentText(), 'No presets saved')
        self.assertFalse(self.strip.combo.isEnabled()); self.assertFalse(self.strip.delete.isEnabled())
        history = len(self.w._history)
        self.save('Webcam')
        self.assertEqual(self.strip.combo.itemText(0), 'No preset selected')
        self.assertEqual(self.strip.combo.currentText(), 'Webcam'); self.assertTrue(self.strip.delete.isEnabled())
        self.assertEqual(len(self.w._history), history + 1)
        self.assertEqual(load_settings()[KEY], self.w.settings[KEY])
        self.strip.reload()
        self.assertEqual(self.strip.combo.currentText(), 'Webcam'); self.assertTrue(self.strip.delete.isEnabled())

    def test_selection_tracks_each_clip_without_applying_on_selection(self):
        self.save('Webcam'); identity = self.strip.records[0]['id']
        self.assertEqual(self.w.project.item_by_id('v').video_preset_id, identity)
        before = copy.deepcopy(self.w.project.to_dict()); history = len(self.w._history)
        self.w.timeline.select_ids({'v2'}, 'v2'); self.w.select_item('v2')
        self.assertEqual(self.strip.combo.currentText(), 'No preset selected')
        self.assertFalse(self.strip.delete.isEnabled())
        self.w.timeline.select_ids({'v'}, 'v'); self.w.select_item('v')
        self.assertEqual(self.strip.combo.currentText(), 'Webcam')
        self.assertEqual(self.w.project.to_dict(), before); self.assertEqual(len(self.w._history), history)
        self.w.timeline.select_ids({'v2'}, 'v2'); self.w.select_item('v2')
        self.strip.apply_selected(1)
        self.assertEqual(self.w.project.item_by_id('v2').video_preset_id, identity)
        self.w.undo(); self.assertEqual(self.strip.combo.currentText(), 'No preset selected')
        self.w.redo(); self.assertEqual(self.strip.combo.currentText(), 'Webcam')
        restored = Project.from_dict(self.w.project.to_dict())
        self.assertEqual(restored.item_by_id('v2').video_preset_id, identity)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'preset-association.kcut'
            restored.save(path); restored = Project.load(path)
            self.assertEqual(restored.item_by_id('v2').video_preset_id, identity)
        self.w.set_project(restored); self.w.timeline.select_ids({'v2'}, 'v2'); self.w.select_item('v2')
        self.assertEqual(self.strip.combo.currentText(), 'Webcam')

    def test_different_clips_keep_different_preset_names(self):
        self.save('Webcam')
        self.w.timeline.select_ids({'v2'}, 'v2'); self.w.select_item('v2')
        self.w.project.item_by_id('v2').transform.scale = 2.
        self.save('Gameplay')
        for identity, name in (('v', 'Webcam'), ('v2', 'Gameplay'), ('v', 'Webcam')):
            self.w.timeline.select_ids({identity}, identity); self.w.select_item(identity)
            self.assertEqual(self.strip.combo.currentText(), name)

    def test_full_video_values_multi_apply_undo_and_unrelated_data(self):
        item = self.w.project.item_by_id('v'); panel = self.w.inspector
        item.transform.scale = 1.908; item.transform.scale_y = 1.19; item.transform.scale_linked = True
        item.transform.rotation = 21; item.transform.anchor_x = 8; item.transform.anchor_y = -9
        item.transform.pitch = 12; item.transform.yaw = -14; item.transform.flip_horizontal = True
        item.transform.flip_vertical = True; item.transform.x = .6; item.transform.y = .2
        item.crop = Crop(.1, .2, .6, .5); item.crop_softness = 23; item.retain_image_position = True
        item.opacity = 72; item.composite_mode = 'Screen'
        item.effects = [dict(name='Gaussian Blur', inspector_background_blur=True, enabled=True,
                             horizontal=31., vertical=31., linked=True, border='Reflect', blend=100.)]
        values = capture(panel, item); self.w.model_changed(); self.save('Webcam')
        second = self.w.project.item_by_id('v2'); second.crop = Crop(.7, .7, .02, .02)
        second.effects = [{'name': 'Object Tracking', 'analysis': {'unchanged': True}}]
        second.brightness = .6; second.gain_db = -7; second.keyframes = {'opacity': [{'time': 0, 'value': 55}]}
        self.w.model_changed(); baseline = copy.deepcopy(self.w.project.to_dict()); old_history = len(self.w._history)
        self.w.timeline.select_ids({'v', 'v2', 'audio'}, 'v'); self.w.select_item('v')
        self.strip.apply_selected(1)
        second = self.w.project.item_by_id('v2')
        self.assertEqual(capture(panel, second), values)
        self.assertEqual(second.start, 4); self.assertEqual(second.duration, 2)
        self.assertEqual(second.gain_db, -7); self.assertEqual(second.brightness, .6)
        self.assertEqual(second.effects[0], baseline['timeline'][1]['effects'][0])
        self.assertEqual(second.keyframes, baseline['timeline'][1]['keyframes'])
        self.assertEqual(self.w.project.item_by_id('audio').transform.scale, 1.)
        self.assertEqual(len(self.w._history), old_history + 1)
        applied = copy.deepcopy(self.w.project.to_dict())
        self.w.undo(); self.assertEqual(self.w.project.timeline[1].crop, Crop(**baseline['timeline'][1]['crop']))
        self.w.redo(); self.assertEqual(self.w.project.timeline[1].crop, Crop(**applied['timeline'][1]['crop']))

    def test_locked_graphic_title_and_audio_not_modified(self):
        p = self.w.project; p.add_track('video'); p.track_states['video_2']['locked'] = True
        p.timeline.extend([TimelineItem('locked', 'm', 'video_2', 0, 1),
                           TimelineItem('graphic', 'm', 'video_1', 8, 1, role='graphic'),
                           TimelineItem('title', 'm', 'video_1', 10, 1, role='title')])
        p.item_by_id('v').transform.scale = 2; self.w.model_changed(); self.save('Zoom')
        self.w.timeline.select_ids({i.id for i in p.timeline}, 'v'); self.w.select_item('v')
        self.strip.apply_selected(1)
        for identity in ('locked', 'graphic', 'title', 'audio'):
            self.assertEqual(p.item_by_id(identity).transform.scale, 1.)
        self.assertEqual(p.item_by_id('v2').transform.scale, 2.)

    def test_overwrite_cancel_and_save_as_new(self):
        self.save('Webcam'); identity = self.strip.records[0]['id']
        self.w.project.item_by_id('v').transform.scale = 2
        self.choose_prompt('Cancel'); self.strip.save_preset()
        self.assertEqual(self.strip.records[0]['values']['scale'], 1.)
        self.choose_prompt('Overwrite'); self.strip.save_preset()
        self.assertEqual(self.strip.records[0]['values']['scale'], 2.)
        self.assertEqual(self.strip.records[0]['id'], identity)
        def new_prompt():
            dialog = self.app.activeModalWidget()
            next(b for b in dialog.buttons() if b.text() == 'Save as new').click()
            def name():
                dialog = self.app.activeModalWidget(); dialog.name.setText('Gameplay'); dialog.save.click()
            QTimer.singleShot(0, name)
        QTimer.singleShot(0, new_prompt); self.strip.save_preset()
        self.assertEqual([r['name'] for r in self.strip.records], ['Webcam', 'Gameplay'])

    def test_delete_cancel_confirm_and_last_placeholder(self):
        self.save('Webcam'); self.choose_prompt('Cancel'); self.strip.delete_preset()
        self.assertEqual(len(self.strip.records), 1)
        self.choose_prompt('Yes'); self.strip.delete_preset()
        self.assertEqual(self.strip.records, []); self.assertEqual(load_settings()[KEY], [])
        self.assertEqual(self.strip.combo.currentText(), 'No presets saved'); self.assertFalse(self.strip.delete.isEnabled())

    def test_blank_duplicate_names_cancel_and_preference_write_failure(self):
        self.save('Webcam')
        dialog = PresetNameDialog(self.strip, self.strip.records)
        self.assertFalse(dialog.save.isEnabled()); dialog.name.setText('  '); self.assertFalse(dialog.save.isEnabled())
        dialog.name.setText(' webcam '); self.assertFalse(dialog.save.isEnabled())
        dialog.name.setText('Other'); self.assertTrue(dialog.save.isEnabled()); dialog.deleteLater()
        before = copy.deepcopy(self.w.settings); records = copy.deepcopy(self.strip.records)
        with patch.object(self.strip, 'persist', side_effect=OSError('fixture full disk')), patch.object(QMessageBox, 'warning') as warning:
            self.assertFalse(self.strip.write([])); warning.assert_called_once()
        self.assertEqual(self.w.settings, before); self.assertEqual(self.strip.records, records)

    def test_no_preset_selected_does_not_change_project(self):
        self.save('Webcam'); before = copy.deepcopy(self.w.project.to_dict()); history = len(self.w._history)
        self.strip.apply_selected(0)
        self.assertEqual(self.w.project.to_dict(), before); self.assertEqual(len(self.w._history), history)
        self.assertFalse(self.strip.delete.isEnabled())

    def test_new_name_cancel_preserves_project_and_preferences(self):
        before = copy.deepcopy(self.w.settings); project = copy.deepcopy(self.w.project.to_dict())
        QTimer.singleShot(0, lambda: self.app.activeModalWidget().reject())
        self.strip.save_preset()
        self.assertEqual(self.w.settings, before); self.assertEqual(self.w.project.to_dict(), project)
        self.assertEqual(self.strip.records, [])

    def test_hide_show_button_persists_without_changing_presets_or_history(self):
        self.save('Webcam'); section = self.w.inspector.video_preset_section
        before = copy.deepcopy(self.strip.records); history = len(self.w._history)
        QTest.mouseClick(section.toggle, Qt.LeftButton)
        self.assertTrue(self.strip.isHidden()); self.assertTrue(section.toggle.isVisible())
        self.assertTrue(load_settings()[HIDDEN_KEY]); self.assertEqual(self.strip.records, before)
        QTest.mouseClick(section.toggle, Qt.LeftButton)
        self.assertFalse(self.strip.isHidden()); self.assertFalse(load_settings()[HIDDEN_KEY])
        self.assertEqual(len(self.w._history), history)
        with patch.object(self.strip, 'save_preferences', side_effect=OSError('fixture full disk')), patch.object(QMessageBox, 'warning'):
            QTest.mouseClick(section.toggle, Qt.LeftButton)
        self.assertTrue(section.toggle.isChecked()); self.assertFalse(self.strip.isHidden())
        self.assertFalse(self.w.settings[HIDDEN_KEY])

    def test_corrupted_values_are_ignored_and_crops_clamp_on_smaller_sources(self):
        values = capture(self.w.inspector, self.w.project.item_by_id('v'))
        broken = dict(values, scale=float('nan'))
        with self.assertRaises(ValueError): validate(broken)
        self.w.settings[KEY] = [None, dict(id='bad', name='Bad', values=broken),
                                dict(id='ok', name='Good', values=values), dict(id='ok', name='Duplicate', values=values)]
        self.strip.reload(); self.assertEqual([r['name'] for r in self.strip.records], ['Good'])
        values.update(crop_left=8192, crop_right=8192, crop_top=8192, crop_bottom=8192)
        item = self.w.project.item_by_id('v'); apply(self.w.project, item, values)
        self.assertGreaterEqual(item.crop.width, .02); self.assertLessEqual(item.crop.x + item.crop.width, 1)

    def test_page_guard_and_reselecting_same_preset(self):
        self.save('Webcam'); item = self.w.project.item_by_id('v'); item.transform.scale = 2.
        self.w.current_page = 1; self.strip.apply_selected(1); self.assertEqual(item.transform.scale, 2.)
        self.w.current_page = 0; self.strip.apply_selected(1); self.assertEqual(item.transform.scale, 1.)
        item.transform.scale = 3.; self.strip.combo.activated.emit(1); self.assertEqual(item.transform.scale, 1.)


if __name__ == '__main__': unittest.main()
