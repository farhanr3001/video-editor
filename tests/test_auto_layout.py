import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('KINETIC_CUT_HOME', tempfile.mkdtemp(prefix='kc-auto-layout-'))

from PySide6.QtWidgets import QApplication, QDialog

from kinetic_cut import auto_layout
from kinetic_cut.media_insert import plan
from kinetic_cut.model import MediaItem, Project
from kinetic_cut.video_presets import KEY, apply, validate

W, H = 1080, 1920


def media(width=1920, height=1080, audio=True):
    return MediaItem('m1', 'C:/fixtures/gameplay.mp4', 'video', 'gameplay.mp4', 30., width, height, 60., audio)


def preset_values():
    # A webcam preset made the way the inspector saves one: the source's top-left corner, fitted to the top.
    return validate(dict(position_x=0., position_y=546., scale=1.5, scale_y=1.5, rotation=0., anchor_x=0., anchor_y=0.,
        pitch=0., yaw=0., crop_left=0., crop_right=1500., crop_top=0., crop_bottom=760., crop_softness=0., opacity=100.,
        background_strength=12., scale_linked=True, flip_horizontal=False, flip_vertical=False,
        retain_image_position=False, background_enabled=False, composite_mode='Normal'))


def project_with_tracks(count=3):
    project = Project()
    while len(project.video_tracks) < count:
        project.add_track('video')
    return project


def layers(stage, placed):
    items = [i for i in stage.timeline if i.id in placed]
    video = sorted((i for i in items if i.track in stage.video_tracks), key=lambda i: stage.video_tracks.index(i.track))
    return video, [i for i in items if i.track in stage.audio_tracks]


class AutoLayoutPlanTests(unittest.TestCase):
    def preset_layout(self):
        return dict(mode='preset', id='p1', values=preset_values())

    def test_preset_layout_places_three_layers_and_one_audio_clip(self):
        project = project_with_tracks(3)
        stage, placed, _ = plan(project, [media()], 'video_3', 4., self.preset_layout())
        video, audio = layers(stage, placed)
        self.assertEqual([i.track for i in video], ['video_1', 'video_2', 'video_3'])
        self.assertEqual(len(audio), 1)
        self.assertEqual({(i.start, i.duration, i.in_point) for i in video + audio}, {(4., 30., 0)})
        self.assertEqual(len({i.group_id for i in video + audio}), 1)
        self.assertEqual(len(project.timeline), 0, 'planning must not touch the project')

    def test_background_is_blurred_full_frame_and_webcam_is_marked(self):
        stage, placed, _ = plan(project_with_tracks(3), [media()], 'video_3', 0., self.preset_layout())
        background, content, webcam = layers(stage, placed)[0]
        self.assertEqual(background.effects[0]['name'], 'Gaussian Blur')
        self.assertTrue(background.effects[0]['enabled'])
        self.assertEqual((background.crop.width, background.crop.height, background.transform.scale), (1., 1., 1.))
        self.assertTrue(webcam.is_webcam)
        self.assertEqual(webcam.video_preset_id, 'p1')
        self.assertEqual(content.effects, [])

    def test_content_is_uncropped_and_fills_the_space_below_the_webcam(self):
        project = project_with_tracks(3)
        stage, placed, _ = plan(project, [media()], 'video_3', 0., self.preset_layout())
        _, content, webcam = layers(stage, placed)[0]
        m = stage.media_by_id('m1')
        self.assertEqual((content.crop.x, content.crop.y, content.crop.width, content.crop.height), (0, 0, 1, 1))
        self.assertTrue(content.transform.scale_linked)
        webcam_bottom = auto_layout.webcam_bottom(stage, m, webcam)
        height = auto_layout.layer_height(stage, m, content)
        centre = content.transform.y * H
        self.assertAlmostEqual(centre - height / 2, webcam_bottom, delta=2)
        self.assertAlmostEqual(centre + height / 2, H, delta=2)
        from kinetic_cut.exporter import _target_size
        self.assertGreater(_target_size(content, m, W, 1., H)[0], W, 'a 16:9 source overflows the sides, as intended')

    def test_webcam_lane_follows_the_drop_layer_content_and_background_stay_low(self):
        stage, placed, _ = plan(project_with_tracks(4), [media()], 'video_4', 0., self.preset_layout())
        video, _ = layers(stage, placed)
        self.assertEqual([i.track for i in video], ['video_1', 'video_2', 'video_4'])
        self.assertTrue(video[2].is_webcam)

    def test_drop_on_the_lowest_layers_still_keeps_the_webcam_on_layer_three(self):
        for dropped in ('video_1', 'video_2'):
            stage, placed, _ = plan(project_with_tracks(3), [media()], dropped, 0., self.preset_layout())
            self.assertEqual([i.track for i in layers(stage, placed)[0]], ['video_1', 'video_2', 'video_3'], dropped)

    def test_missing_layers_are_created(self):
        project = Project()
        project.video_tracks = project.video_tracks[:1]
        stage, placed, _ = plan(project, [media()], '', 0., self.preset_layout())
        self.assertEqual([i.track for i in layers(stage, placed)[0]], stage.video_tracks[:3])
        self.assertGreaterEqual(len(stage.video_tracks), 3)

    def test_drawn_crop_is_fitted_to_the_width_and_the_top(self):
        project = project_with_tracks(3)
        layout = dict(mode='crop', crop=(0., 0., .25, .3))
        stage, placed, _ = plan(project, [media()], 'video_3', 0., layout)
        _, content, webcam = layers(stage, placed)[0]
        m = stage.media_by_id('m1')
        from kinetic_cut.exporter import _target_size
        width, height = _target_size(webcam, m, W, 1., H)
        self.assertAlmostEqual(width, W, delta=2)
        self.assertAlmostEqual(webcam.transform.y * H - height / 2, 0, delta=2)
        self.assertAlmostEqual(webcam.transform.x, .5)
        self.assertAlmostEqual(content.transform.y * H - auto_layout.layer_height(stage, m, content) / 2, height, delta=3)

    def test_oversized_webcam_still_leaves_the_content_a_minimum_share(self):
        stage, placed, _ = plan(project_with_tracks(3), [media()], 'video_3', 0., dict(mode='crop', crop=(0., 0., .2, 1.)))
        _, content, _ = layers(stage, placed)[0]
        m = stage.media_by_id('m1')
        self.assertGreaterEqual(auto_layout.layer_height(stage, m, content), H * auto_layout.MIN_CONTENT - 2)

    def test_locked_lane_blocks_the_layout_without_changing_the_project(self):
        project = project_with_tracks(3)
        project.track_states['video_2']['locked'] = True
        with self.assertRaisesRegex(ValueError, 'Unlock video layer 2'):
            plan(project, [media()], 'video_3', 0., self.preset_layout())
        self.assertEqual(project.timeline, [])

    def test_without_layout_media_is_placed_normally(self):
        stage, placed, _ = plan(project_with_tracks(3), [media()], 'video_2', 0.)
        video, audio = layers(stage, placed)
        self.assertEqual([i.track for i in video], ['video_2'])
        self.assertEqual(len(audio), 1)

    def test_images_and_audio_ignore_the_layout(self):
        image = MediaItem('i1', 'C:/fixtures/logo.png', 'image', 'logo.png', 5., 400, 400)
        stage, placed, _ = plan(project_with_tracks(3), [image], 'video_2', 0., self.preset_layout())
        self.assertEqual([i.track for i in layers(stage, placed)[0]], ['video_2'])

    def test_clip_without_audio_adds_no_audio_clip(self):
        stage, placed, _ = plan(project_with_tracks(3), [media(audio=False)], 'video_3', 0., self.preset_layout())
        self.assertEqual(layers(stage, placed)[1], [])

    def test_preset_flow_uses_the_actual_preset_geometry(self):
        project = project_with_tracks(3)
        stage, placed, _ = plan(project, [media()], 'video_3', 0., self.preset_layout())
        _, _, webcam = layers(stage, placed)[0]
        reference = layers(*plan(project, [media()], 'video_3', 0.)[:2])[0][0]
        apply(stage, reference, preset_values())
        self.assertEqual((webcam.crop, webcam.transform.scale, webcam.transform.y), (reference.crop, reference.transform.scale, reference.transform.y))


class AutoLayoutUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setProperty('kineticTestDiscardUnsaved', True)

    @classmethod
    def tearDownClass(cls):
        cls.app.setProperty('kineticTestDiscardUnsaved', None)

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.w = MainWindow()
        self.w.autosave_timer.stop()
        self.w.show()
        self.m = media()
        self.w.project.media.append(self.m)
        while len(self.w.project.video_tracks) < 3:
            self.w.project.add_track('video')

    def tearDown(self):
        self.w.close(); self.w.deleteLater(); self.app.processEvents()

    def run_deferred(self):
        for _ in range(5):
            self.app.processEvents()

    def test_button_is_off_by_default_and_sits_between_crop_and_blade(self):
        tool = self.w.auto_layout_tool
        self.assertTrue(tool.isCheckable())
        self.assertFalse(tool.isChecked())
        order = [self.w.select_tool, self.w.transform_box_tool, self.w.crop_tool, tool, self.w.blade_tool]
        panel = tool.parentWidget().layout()
        layout = next(panel.itemAt(i).layout() for i in range(panel.count())
                      if panel.itemAt(i).layout() is not None and panel.itemAt(i).layout().indexOf(tool) >= 0)
        positions = [layout.indexOf(widget) for widget in order]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(positions[3] - positions[2], 1)
        self.assertEqual(positions[4] - positions[3], 1)
        self.assertIn(tool, self.w.timeline_edit_tools)

    def test_toggle_off_drops_media_normally_without_a_prompt(self):
        with patch('kinetic_cut.auto_layout.ask') as ask:
            self.w.insert_media_assets([self.m], 'video_2', 0.)
            self.run_deferred()
        ask.assert_not_called()
        self.assertEqual(len([i for i in self.w.project.timeline if i.track in self.w.project.video_tracks]), 1)

    def test_toggle_on_confirmed_preset_creates_the_layout_as_one_undo_step(self):
        self.w.auto_layout_tool.setChecked(True)
        history = len(self.w._history)
        layout = dict(mode='preset', id='p1', values=preset_values())
        with patch('kinetic_cut.auto_layout.ask', return_value=layout) as ask:
            self.w.insert_media_assets([self.m], 'video_3', 2.)
            self.run_deferred()
        ask.assert_called_once()
        video = [i for i in self.w.project.timeline if i.track in self.w.project.video_tracks]
        self.assertEqual(sorted(i.track for i in video), ['video_1', 'video_2', 'video_3'])
        self.assertEqual(len([i for i in self.w.project.timeline if i.track in self.w.project.audio_tracks]), 1)
        self.w.undo(); self.run_deferred()
        self.assertEqual(self.w.project.timeline, [])
        self.assertGreater(len(self.w._history), history)

    def test_cancelling_the_prompt_places_the_media_as_a_normal_item_on_the_dropped_layer(self):
        self.w.auto_layout_tool.setChecked(True)
        with patch('kinetic_cut.auto_layout.ask', return_value=None):
            self.w.insert_media_assets([self.m], 'video_2', 0.)
            self.run_deferred()
        video = [i for i in self.w.project.timeline if i.track in self.w.project.video_tracks]
        self.assertEqual([i.track for i in video], ['video_2'])

    def dialog(self, records):
        from PySide6.QtGui import QImage, QColor
        image = QImage(192, 108, QImage.Format_RGB32); image.fill(QColor('gray'))
        return auto_layout.AutoLayoutDialog(self.w, records, image, self.m)

    def test_dialog_selects_the_first_saved_preset_and_shows_its_crop(self):
        records = [dict(id='a', name='First', values=preset_values()), dict(id='b', name='Second', values=preset_values())]
        dialog = self.dialog(records)
        self.assertEqual(dialog.combo.count(), 3)  # two presets + custom crop
        self.assertEqual(dialog.combo.currentData(), 'a')
        crop = dialog.canvas.crop
        self.assertAlmostEqual(crop.width, 420 / 1920); self.assertAlmostEqual(crop.height, 320 / 1080)
        result = dialog.result_options()
        self.assertEqual((result['mode'], result['id']), ('preset', 'a'))

    def test_choosing_a_preset_updates_the_crop_view(self):
        other = dict(preset_values()); other.update(crop_left=960., crop_right=0.)
        dialog = self.dialog([dict(id='a', name='First', values=preset_values()), dict(id='b', name='Second', values=validate(other))])
        dialog.combo.setCurrentIndex(1)
        self.assertAlmostEqual(dialog.canvas.crop.x, .5)
        self.assertEqual(dialog.result_options()['id'], 'b')

    def test_editing_the_crop_switches_to_custom_crop(self):
        from kinetic_cut.model import Crop
        dialog = self.dialog([dict(id='a', name='First', values=preset_values())])
        dialog.set_crop(Crop(.1, .1, .25, .25), user=True)
        self.assertEqual(dialog.combo.currentData(), auto_layout.CUSTOM)
        result = dialog.result_options()
        self.assertEqual(result['mode'], 'crop')
        for got, want in zip(result['crop'], (.1, .1, .25, .25)): self.assertAlmostEqual(got, want)
        dialog.combo.setCurrentIndex(0)  # back to the preset restores its crop
        self.assertAlmostEqual(dialog.canvas.crop.width, 420 / 1920)

    def test_without_presets_the_dialog_starts_on_custom_crop(self):
        dialog = self.dialog([])
        self.assertEqual(dialog.combo.count(), 1)
        self.assertEqual(dialog.combo.currentData(), auto_layout.CUSTOM)
        self.assertEqual(dialog.result_options()['mode'], 'crop')

    def test_ask_returns_the_dialog_result_and_none_when_cancelled(self):
        self.w.settings[KEY] = [dict(id='a', name='First', values=preset_values())]
        with patch.object(auto_layout, 'source_image', return_value=None), \
             patch.object(auto_layout.AutoLayoutDialog, '__init__', lambda self, *a, **k: QDialog.__init__(self)), \
             patch.object(auto_layout.AutoLayoutDialog, 'result_options', return_value=dict(mode='crop', crop=(0., 0., .3, .3))):
            with patch.object(auto_layout.AutoLayoutDialog, 'exec', return_value=QDialog.Accepted):
                self.assertEqual(auto_layout.ask(self.w, [self.m]), dict(mode='crop', crop=(0., 0., .3, .3)))
            with patch.object(auto_layout.AutoLayoutDialog, 'exec', return_value=QDialog.Rejected):
                self.assertIsNone(auto_layout.ask(self.w, [self.m]))

    def test_audio_only_drop_never_prompts(self):
        self.w.auto_layout_tool.setChecked(True)
        audio = MediaItem('a1', 'C:/fixtures/song.mp3', 'audio', 'song.mp3', 30.)
        with patch('kinetic_cut.auto_layout.ask') as ask:
            self.w.insert_media_assets([audio], 'audio_1', 0.)
            self.run_deferred()
        ask.assert_not_called()


if __name__ == '__main__':
    unittest.main()
