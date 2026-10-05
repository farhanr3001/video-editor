"""Native region input and transactional object-tracking controls."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from PySide6.QtCore import Qt, QPoint, QEvent, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QDialog, QMessageBox

from kinetic_cut.model import Project, MediaItem, TimelineItem, Crop
from kinetic_cut.object_tracking import fingerprint
from kinetic_cut.tracking_dialog import TrackingDialog
from kinetic_cut.tracking_effect import default_effect


class TrackingHost(QWidget):
    def __init__(self, project):
        super().__init__()
        self.project = project
        self.settings = {'ffmpeg': 'ffmpeg'}
        self.workers = []
        self._tracking_cancel = None
        self.timeline = SimpleNamespace(selected_id='i')
        self.transport = SimpleNamespace(playing=False, closed=False)
        self.current_page = 0
        self.flush_text_edit = Mock()
        self.model_changed = Mock()
        self.select_item = Mock()
        self.inspector = SimpleNamespace(tabs=Mock(), effect_picker=Mock())
        self.status = Mock()

    def statusBar(self):
        return self.status

    def start_worker(self, worker):
        self.workers.append(worker)


class TrackingInspector(QWidget):
    changed = Signal()

    def __init__(self, host, item):
        super().__init__(host)
        self.window = host
        self.item = item
        self.item_id = item.id
        self.updating = False

    def effect(self):
        return self.item.effects[0]

    def effect_targets(self):
        return [(self.item, self.effect())]

    def edit_effect(self, key, value):
        self.effect()[key] = value
        self.changed.emit()


class TrackingDialogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = self.root / 'source.bin'
        source.write_bytes(b'original tracking source fixture')
        self.media = MediaItem('m', str(source), 'video', 'Source', 3, 320, 180, 30)
        self.item = TimelineItem('i', 'm', 'video_1', 10, 2.8)
        self.project = Project(media=[self.media], timeline=[self.item], playhead=10)
        self.project.settings.fps = 30
        self.host = TrackingHost(self.project)
        self.dialogs = []
        self.analysis = dict(version=1, source=fingerprint(self.media), source_start=0.,
            source_end=2.8, sample_fps=15., reference_time=0.,
            frames=[dict(time=0., box=[.1, .3, .1, .2], confidence=1., status='manual'),
                    dict(time=1.4, box=[.4, .3, .1, .2], confidence=.9, status='tracked'),
                    dict(time=2.8, box=[.7, .3, .1, .2], confidence=.9, status='tracked')])

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.reject()
            dialog.deleteLater()
        self.host.close()
        self.host.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QApplication.processEvents()
        self.temp.cleanup()

    def dialog(self, effect=None):
        dialog = TrackingDialog(self.host, self.media, self.item, effect)
        dialog._decode_timer.stop()
        self.dialogs.append(dialog)
        return dialog

    def ready(self, dialog):
        image = QImage(320, 180, QImage.Format_RGBA8888)
        image.fill(QColor('#44515d'))
        dialog.raw = image
        dialog._shown_time = dialog.source_time()
        dialog.view.image = image
        dialog.view.region = [.1, .3, .1, .2]
        dialog.set_busy(False)

    def test_region_drag_uses_full_source_coordinates_and_reverse_direction(self):
        self.item.crop = Crop(.25, .1, .5, .8)
        dialog = self.dialog()
        self.ready(dialog)
        dialog.view.resize(640, 360)
        dialog.view.show()
        QApplication.processEvents()
        rect = dialog.view.image_rect()
        end = QPoint(round(rect.x() + .2 * rect.width()), round(rect.y() + .25 * rect.height()))
        start = QPoint(round(rect.x() + .6 * rect.width()), round(rect.y() + .75 * rect.height()))
        QTest.mousePress(dialog.view, Qt.LeftButton, pos=start)
        QTest.mouseMove(dialog.view, end)
        QTest.mouseRelease(dialog.view, Qt.LeftButton, pos=end)
        for actual, expected in zip(dialog.view.region, [.2, .25, .4, .5]):
            self.assertAlmostEqual(actual, expected, delta=.006)
        self.assertTrue(dialog.dirty_track)
        self.assertEqual(dialog.view.crop, self.item.crop)

    def test_source_clock_and_manual_corrections_follow_trim_and_speed(self):
        self.item.in_point = .5
        self.item.speed = 2.
        self.item.duration = 1.
        dialog = self.dialog()
        dialog.timeline.setValue(15)
        dialog._decode_timer.stop()
        self.ready(dialog)
        dialog.add_anchor()
        self.assertAlmostEqual(dialog.source_time(), 1.5)
        self.assertEqual(dialog.anchors, [dict(time=1.5, box=[.1, .3, .1, .2])])
        self.assertEqual(dialog.anchor_list.rowCount(), 1)
        dialog.clear_anchors()
        self.assertFalse(dialog.anchors)
        self.assertTrue(dialog.dirty_track)
        self.assertFalse(self.item.effects)

    def test_stale_decoded_frame_is_not_published_or_used_as_an_anchor(self):
        dialog = self.dialog()
        dialog.request_frame()
        first = self.host.workers[-1]
        dialog.timeline.setValue(10)
        dialog._decode_timer.stop()
        dialog.view.region = [.1, .3, .1, .2]
        image = QImage(320, 180, QImage.Format_RGBA8888)
        image.fill(QColor('red'))
        first.signals.result.emit(image)
        self.assertTrue(dialog.raw.isNull())
        self.assertEqual(len(self.host.workers), 2)
        dialog.add_anchor()
        self.assertFalse(dialog.anchors)
        self.host.workers[-1].signals.result.emit(image)
        self.assertAlmostEqual(dialog._shown_time, dialog.source_time())
        dialog.add_anchor()
        self.assertEqual(len(dialog.anchors), 1)

    def test_real_worker_progress_signature_completes_transactional_draft(self):
        dialog = self.dialog()
        self.ready(dialog)
        original = copy.deepcopy(self.item.effects)
        def analyze(media, item, reference, region, anchors, progress, cancel, **options):
            progress(25., 'Tracking object fixture')
            progress(100., 'Tracking complete')
            return copy.deepcopy(self.analysis)
        with patch('kinetic_cut.object_tracking.analyze', side_effect=analyze):
            dialog.track()
            worker = self.host.workers[-1]
            progress = []
            worker.signals.progress.connect(progress.append)
            worker.run()
        self.assertFalse(dialog._busy)
        self.assertFalse(dialog.dirty_track, dialog.info.text())
        self.assertEqual(dialog.progress_bar.value(), 100)
        self.assertEqual(progress[-1], (100., 'Tracking complete'))
        self.assertEqual(self.item.effects, original)
        self.assertEqual(dialog.result_effect()['analysis'], self.analysis)

    def test_cancelled_analysis_late_result_cannot_mutate_draft_or_clip(self):
        dialog = self.dialog()
        self.ready(dialog)
        before = dialog.result_effect()
        dialog.track()
        worker = self.host.workers[-1]
        dialog.reject()
        worker.signals.result.emit(copy.deepcopy(self.analysis))
        self.assertTrue(dialog.cancel.is_set())
        self.assertEqual(dialog.result(), QDialog.Rejected)
        self.assertEqual(dialog.result_effect(), before)
        self.assertFalse(self.item.effects)
        self.assertIsNone(self.host._tracking_cancel)

    def test_existing_analysis_is_copied_and_changes_require_retracking(self):
        original = default_effect('Circle')
        analysis = copy.deepcopy(self.analysis)
        analysis['anchors'] = [dict(time=.7, box=[.2, .3, .1, .2])]
        original['analysis'] = analysis
        dialog = self.dialog(original)
        self.assertFalse(dialog.dirty_track)
        self.assertTrue(dialog.apply_button.isEnabled())
        self.assertEqual(dialog.progress_bar.value(), 100)
        self.assertIn('Tracking ready', dialog.info.text())
        self.assertEqual(dialog.anchors, analysis['anchors'])
        self.assertFalse(dialog.image_form.isRowVisible(dialog.image_button))
        dialog.mode.setCurrentText('Image')
        self.assertTrue(dialog.image_form.isRowVisible(dialog.image_button))
        dialog.mode.setCurrentText('Circle')
        self.assertFalse(dialog.image_form.isRowVisible(dialog.image_button))
        dialog.sample_fps.setValue(20)
        self.assertTrue(dialog.dirty_track)
        self.assertFalse(dialog.apply_button.isEnabled())
        dialog.mode.setCurrentText('Label')
        dialog.reject()
        self.assertEqual(original['mode'], 'Circle')
        self.assertEqual(original['analysis'], analysis)

    def test_apply_refuses_missing_analysis_and_unreviewed_unsafe_censor_loss(self):
        dialog = self.dialog()
        with patch.object(QMessageBox, 'information') as message:
            dialog.accept()
        self.assertEqual(dialog.result(), QDialog.Rejected)
        message.assert_called_once()
        effect = default_effect('Censor Bar')
        effect['analysis'] = copy.deepcopy(self.analysis)
        effect['analysis']['frames'][1]['status'] = 'lost'
        effect['loss_policy'] = 'Hide'
        lost = self.dialog(effect)
        with patch.object(QMessageBox, 'information') as message:
            lost.accept()
        self.assertEqual(lost.result(), QDialog.Rejected)
        message.assert_called_once()
        lost.loss_review.setChecked(True)
        lost.accept()
        self.assertEqual(lost.result(), QDialog.Accepted)
        self.assertTrue(lost.result_effect()['loss_reviewed'])

    def test_begin_commits_accepted_effect_once_and_cancel_commits_nothing(self):
        from kinetic_cut.tracking_ui import begin
        effect = default_effect('Circle')
        effect['analysis'] = copy.deepcopy(self.analysis)
        with patch('kinetic_cut.tracking_dialog.TrackingDialog') as factory:
            draft = factory.return_value
            draft.exec.return_value = QDialog.Rejected
            begin(self.host)
            self.assertFalse(self.item.effects)
            self.host.model_changed.assert_not_called()
            draft.exec.return_value = QDialog.Accepted
            draft.result_effect.return_value = effect
            begin(self.host)
        self.assertEqual(self.item.effects, [effect])
        self.host.model_changed.assert_called_once_with()
        self.host.select_item.assert_called_once_with('i')
        self.host.inspector.effect_picker.setCurrentIndex.assert_called_once_with(0)

    def test_begin_rejects_changed_clip_project_and_track_lock(self):
        from kinetic_cut.tracking_ui import begin
        effect = default_effect('Circle')
        effect['analysis'] = copy.deepcopy(self.analysis)
        for mutation in ('clip', 'project', 'lock', 'closed'):
            self.host.project = self.project
            self.item.duration = 2.8
            self.project.track_states['video_1']['locked'] = False
            self.host.transport.closed = False
            self.host.model_changed.reset_mock()
            def change_during_dialog():
                if mutation == 'clip': self.item.duration = 2.
                elif mutation == 'project': self.host.project = Project()
                elif mutation == 'lock': self.project.track_states['video_1']['locked'] = True
                else: self.host.transport.closed = True
                return QDialog.Accepted
            with patch('kinetic_cut.tracking_dialog.TrackingDialog') as factory:
                factory.return_value.exec.side_effect = change_during_dialog
                factory.return_value.result_effect.return_value = effect
                begin(self.host)
            self.assertFalse(self.item.effects, mutation)
            self.host.model_changed.assert_not_called()

    def test_marker_properties_remain_editable_and_show_only_applicable_controls(self):
        from kinetic_cut.tracking_ui import TrackingPanel
        effect = default_effect('Circle')
        effect['analysis'] = copy.deepcopy(self.analysis)
        self.item.effects = [effect]
        inspector = TrackingInspector(self.host, self.item)
        panel = TrackingPanel(inspector)
        for mode, visible, hidden in (
                ('Blur', 'blur', 'arrow_length'),
                ('Pixelate', 'pixel_size', 'blur'),
                ('Arrow', 'arrow_length', 'blur'),
                ('Circle', 'stroke_width', 'font_size'),
                ('Rectangle', 'radius', 'font_size'),
                ('Label', 'font_size', 'pixel_size'),
                ('Image', 'image', 'stroke_width'),
                ('Censor Bar', 'radius', 'blur'),
                ('Follow Crop', 'width', 'stroke_width')):
            effect['mode'] = mode
            panel.refresh(effect)
            shown = panel.controls.get(visible) or getattr(panel, visible)
            concealed = panel.controls.get(hidden) or getattr(panel, hidden)
            self.assertTrue(panel.form.isRowVisible(shown), mode)
            self.assertFalse(panel.form.isRowVisible(concealed), mode)
        panel.change('width', 155.)
        panel.change('offset_x', -48.)
        panel.change('follow_scale', False)
        self.assertEqual((effect['width'], effect['offset_x'], effect['follow_scale']),
                         (155., -48., False))
        effect['loss_reviewed'] = True
        panel.change_mode('Pixelate')
        self.assertEqual(effect['loss_policy'], 'Full frame')
        self.assertFalse(effect['loss_reviewed'])
        panel.change('loss_policy', 'Hide')
        self.assertFalse(effect['loss_reviewed'])
        panel.change_mode('Follow Crop')
        self.assertEqual(effect['loss_policy'], 'Hold')
        self.assertFalse(effect['loss_reviewed'])
        panel.deleteLater()
        inspector.deleteLater()

    def test_follow_crop_review_guide_keeps_selection_in_original_source_coordinates(self):
        from kinetic_cut.tracking_effect import effective_crop
        self.item.crop = Crop(.2, .15, .4, .6)
        effect = default_effect('Follow Crop')
        effect['analysis'] = copy.deepcopy(self.analysis)
        effect['follow_scale'] = False
        dialog = self.dialog(effect)
        dialog.timeline.setValue(21)
        dialog._decode_timer.stop()
        self.ready(dialog)
        dialog.before.setChecked(False)
        tracked = copy.deepcopy(self.item)
        tracked.effects = [effect]
        self.assertEqual(dialog.view.crop, effective_crop(tracked, self.media, .7))
        self.assertEqual(dialog.view.image.size(), dialog.raw.size())
        self.assertNotEqual(dialog.view.crop, self.item.crop)
        dialog.view.region = [.35, .4, .12, .15]
        dialog.region_changed(dialog.view.region)
        dialog.add_anchor()
        self.assertAlmostEqual(dialog.anchors[-1]['time'], .7)
        self.assertEqual(dialog.anchors[-1]['box'], [.35, .4, .12, .15])
        self.assertFalse(self.item.effects)
