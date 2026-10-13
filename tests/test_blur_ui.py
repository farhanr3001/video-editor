import copy,unittest
from unittest.mock import patch
import test_pool_monitor_polish as fixture
from kinetic_cut.model import TimelineItem


class BlurUITests(unittest.TestCase):
    setUp=fixture.PoolMonitorTests.setUp
    tearDown=fixture.PoolMonitorTests.tearDown
    def selected(self):
        self.w.timeline.select_ids({'v'},'v');self.w.inspector.select('v');return self.w.project.item_by_id('v')
    def test_external_blur_blocks_inspector_and_removal_restores_control(self):
        item=self.selected();self.w.apply_effect_to('Gaussian Blur','v');self.w.inspector.select('v')
        self.assertFalse(self.w.inspector.background_blur_enabled.isEnabled());before=copy.deepcopy(item.effects)
        with patch('kinetic_cut.properties.QMessageBox.information') as message:self.w.inspector.edit_background_blur(True,30.)
        message.assert_called_once();self.assertEqual(item.effects,before)
        self.w.inspector.remove_effect();self.w.inspector.select('v');self.assertTrue(self.w.inspector.background_blur_enabled.isEnabled())
    def test_inspector_blocks_added_effect_until_disabled(self):
        item=self.selected();self.w.inspector.edit_background_blur(True,30.);before=copy.deepcopy(item.effects)
        with patch('kinetic_cut.ui.QMessageBox.information') as message:self.w.apply_effect_to('Gaussian Blur','v')
        message.assert_called_once();self.assertEqual(item.effects,before)
        self.w.inspector.edit_background_blur(False);self.w.apply_effect_to('Gaussian Blur','v')
        self.assertEqual(len(item.effects),2);self.assertFalse(item.effects[0]['enabled']);self.assertFalse(self.w.inspector.background_blur_enabled.isEnabled())
        self.w.inspector.effect_picker.setCurrentIndex(0)
        with patch('kinetic_cut.properties.QMessageBox.information'):
            self.w.inspector.edit_effect('enabled',True);self.w.inspector.reset_effect_section()
        self.assertFalse(item.effects[0]['enabled'])
    def test_batch_conflict_is_atomic_and_legacy_effects_preserved(self):
        item=self.selected();self.w.inspector.edit_background_blur(True,30.)
        second=TimelineItem('second',self.media[1].id,'video_1',2,2);self.w.project.timeline.append(second)
        self.w.timeline.select_ids({'v','second'},'v');before=self.w.project.to_dict()
        with patch('kinetic_cut.ui.QMessageBox.information'):self.w.apply_effect('Gaussian Blur')
        self.assertEqual(self.w.project.to_dict(),before)
        item.effects.append(dict(name='Gaussian Blur',enabled=False));before=copy.deepcopy(item.effects)
        self.w.timeline.select_ids({'v'},'v');self.w.inspector.select('v');self.assertEqual(item.effects,before)
        self.w.inspector.effect_picker.setCurrentIndex(1)
        with patch('kinetic_cut.properties.QMessageBox.information'):self.w.inspector.edit_effect('enabled',True)
        self.assertFalse(item.effects[1]['enabled']);self.w.inspector.edit_background_blur(False);self.assertFalse(item.effects[0]['enabled'])
    def test_preset_cannot_enable_second_blur(self):
        from kinetic_cut.video_presets import apply,capture
        item=self.selected();self.w.inspector.edit_background_blur(True,20.);values=capture(self.w.inspector,item)
        self.w.inspector.edit_background_blur(False);self.w.apply_effect_to('Gaussian Blur','v');before=self.w.project.to_dict()
        with self.assertRaises(ValueError):apply(self.w.project,item,values)
        self.assertEqual(self.w.project.to_dict(),before)
