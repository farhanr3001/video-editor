"""Native region input and transactional object-tracking controls."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from PySide6.QtCore import Qt, QPoint, QPointF, QEvent, Signal
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
        dialog.refresh_preview()
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

    def test_correction_edits_the_analysed_frame_without_a_worker(self):
        effect=default_effect('Circle')
        effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect)
        dialog.timeline.setValue(21)
        dialog._decode_timer.stop()
        self.ready(dialog)
        dialog.view.region=[.2,.2,.2,.2]
        workers=len(self.host.workers)
        dialog.region_changed(dialog.view.region)
        self.assertFalse(dialog.dirty_track)
        self.assertTrue(dialog.apply_button.isEnabled())
        self.assertEqual(len(self.host.workers),workers)
        from kinetic_cut.object_tracking import sample,validate
        self.assertEqual(sample(dialog.effect['analysis'],.7)['box'],[.2,.2,.2,.2])
        self.assertTrue(validate(dialog.effect['analysis']))
        self.assertEqual(effect['analysis'],self.analysis)

    def test_multiple_markers_keep_independent_appearance_and_shared_track(self):
        effect=default_effect('Circle')
        effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect)
        editor=dialog.marker_editor
        editor.kind.setCurrentText('Label')
        editor.add()
        editor.change('label','Follow me')
        editor.change('offset_x',75)
        result=dialog.result_effect()
        from kinetic_cut.tracking_effect import render_effects,export_error
        item=copy.deepcopy(self.item)
        item.effects=[result]
        markers=render_effects(item)
        self.assertEqual([m['mode'] for m in markers],['Circle','Label'])
        self.assertEqual(markers[1]['offset_x'],75)
        self.assertEqual(markers[0]['offset_x'],0)
        self.assertEqual(export_error(result,self.media,item),'')
        stamp=self.root/'marker.png'
        picture=QImage(24,24,QImage.Format_RGB32)
        picture.fill(Qt.red)
        picture.save(str(stamp))
        image_marker=default_effect('Image')
        image_marker['image']=str(stamp)
        result['markers'].append(image_marker)
        project=Project(media=[self.media],timeline=[item])
        item.effects=[result]
        project.portable_media=True
        saved=self.root/'markers.kcut'
        project.save(saved)
        loaded=Project.load(saved)
        restored=loaded.timeline[0].effects[0]
        self.assertEqual(Path(restored['markers'][2]['image']),stamp)
        self.assertEqual(export_error(restored,loaded.media[0],loaded.timeline[0]),'')

    def test_scrubbing_or_drawing_pauses_playback_before_correction(self):
        dialog=self.dialog()
        self.ready(dialog)
        dialog.player=Mock()
        dialog.playing=True
        dialog.timeline.setValue(21)
        dialog._decode_timer.stop()
        self.assertFalse(dialog.playing)
        dialog.player.pause.assert_called()
        self.assertEqual(dialog.timeline.value(),21)
        dialog.playing=True
        dialog.view.regionStarted.emit()
        self.assertFalse(dialog.playing)

    def test_play_at_clip_end_rewinds_to_the_trim_in_point(self):
        self.item.in_point=.5
        dialog=self.dialog()
        self.ready(dialog)
        dialog.player=Mock()
        dialog.timeline.setValue(dialog.timeline.maximum())
        dialog._decode_timer.stop()
        dialog.toggle_play()
        self.assertTrue(dialog.playing)
        self.assertEqual(dialog.timeline.value(),0)
        dialog.player.setPosition.assert_called_with(501)

    def test_play_immediately_after_scrub_consumes_latest_pending_seek(self):
        dialog=self.dialog();self.ready(dialog)
        dialog.player=Mock();dialog.video=Mock();dialog._primed=True
        dialog.timeline.setValue(45)
        self.assertTrue(dialog._decode_timer.isActive())
        dialog.toggle_play()
        self.assertTrue(dialog.playing)
        self.assertFalse(dialog._decode_timer.isActive())
        dialog.player.setPosition.assert_called_with(1501)
        self.assertEqual(dialog._play_seek_pending,1500000)
        dialog.pause_for_edit();self.assertIsNone(dialog._play_seek_pending)

    def test_loaded_notifications_do_not_reseek_every_pause(self):
        from PySide6.QtMultimedia import QMediaPlayer
        dialog=self.dialog()
        dialog.player=Mock()
        dialog.loaded(QMediaPlayer.LoadedMedia)
        dialog.player.setPosition.assert_called_once()
        dialog.player.reset_mock()
        dialog.loaded(QMediaPlayer.LoadedMedia)
        dialog.player.play.assert_not_called()
        dialog.player.setPosition.assert_not_called()

    def test_missed_initial_frame_retries_instead_of_leaving_monitor_stuck(self):
        dialog=self.dialog()
        dialog.timeline.setValue(21)
        dialog._decode_timer.stop()
        dialog.player=Mock()
        dialog.sink=Mock()
        frame=Mock()
        frame.isValid.return_value=True
        frame.startTime.return_value=1000000
        frame.endTime.return_value=1033333
        dialog.sink.videoFrame.return_value=frame
        dialog.video=Mock()
        dialog.surface=Mock()
        dialog.poll()
        dialog.player.pause.assert_called()
        dialog.player.setPosition.assert_called_with(701)

    def test_fresh_box_immediately_enables_analysis_and_updates_guidance(self):
        dialog=self.dialog();self.ready(dialog)
        dialog.view.region=None;dialog.set_busy(False)
        self.assertFalse(dialog.track_button.isEnabled())
        dialog.view.region=[.2,.2,.2,.3];dialog.region_changed(dialog.view.region)
        self.assertTrue(dialog.track_button.isEnabled())
        self.assertIn('Click Analyse target',dialog.info.text())

    def test_packet_clock_seeks_the_previous_real_frame_in_a_vfr_gap(self):
        import av
        import numpy as np
        from fractions import Fraction
        from kinetic_cut.tracking_clock import read_clock,frame_time
        path=self.root/'vfr.mp4'
        with av.open(str(path),'w') as movie:
            stream=movie.add_stream('libx264',rate=60);stream.width=32;stream.height=16;stream.pix_fmt='yuv420p'
            for n in range(10):
                frame=av.VideoFrame.from_ndarray(np.full((16,32,3),n*20,dtype=np.uint8),format='rgb24')
                frame.pts=n*50;frame.time_base=Fraction(1,1000)
                for packet in stream.encode(frame):movie.mux(packet)
            for packet in stream.encode():movie.mux(packet)
        clock=read_clock(str(path),0,.45)
        self.assertAlmostEqual(frame_time(clock,.133333),.1,places=5)
        self.assertAlmostEqual(frame_time(clock,.15),.15,places=5)
        self.assertEqual(frame_time(clock,1.2),1.2)
        self.assertEqual(frame_time(dict(clock,times=[]),.133333),.133333)

    def test_requested_thumb_keeps_its_time_while_vfr_decoder_targets_prior_pts(self):
        dialog=self.dialog();dialog.player=Mock();dialog.video=Mock();dialog._primed=True
        dialog._frame_clock=dict(start=0,end=2.8,times=[0.,.05,.1,.15])
        dialog.timeline.setValue(1);dialog._decode_timer.stop();dialog.request_frame()
        self.assertAlmostEqual(dialog.source_time(),1/30)
        self.assertEqual(dialog.frame_target(),0.)
        dialog.player.setPosition.assert_called_with(1)

    def test_late_timestamp_index_result_does_not_reopen_or_seek_closed_dialog(self):
        dialog=self.dialog();dialog.player=Mock();dialog.request_frame_clock()
        worker=self.host.workers[-1];dialog.reject();dialog.player.reset_mock()
        worker.signals.result.emit(dict(start=0,end=2.8,times=[0.,1.]))
        self.assertIsNone(dialog._frame_clock);dialog.player.setPosition.assert_not_called()

    def test_failed_timestamp_index_does_not_schedule_repeated_workers(self):
        dialog=self.dialog();dialog.player=Mock();dialog.request_frame_clock()
        worker=self.host.workers[-1];worker.signals.error.emit('unsupported metadata')
        count=len(self.host.workers);dialog.request_frame_clock()
        self.assertEqual(len(self.host.workers),count)

    def test_native_forwarded_mouse_cannot_draw_a_box_before_frame_is_ready(self):
        from PySide6.QtGui import QMouseEvent
        dialog=self.dialog();dialog.view.region=None;dialog.view.setEnabled(False)
        for kind,button,buttons,point in [(QEvent.MouseButtonPress,Qt.LeftButton,Qt.LeftButton,QPointF(100,100)),
                (QEvent.MouseMove,Qt.NoButton,Qt.LeftButton,QPointF(180,140)),
                (QEvent.MouseButtonRelease,Qt.LeftButton,Qt.NoButton,QPointF(180,140))]:
            event=QMouseEvent(kind,point,point,button,buttons,Qt.NoModifier)
            {QEvent.MouseButtonPress:dialog.view.mousePressEvent,QEvent.MouseMove:dialog.view.mouseMoveEvent,
             QEvent.MouseButtonRelease:dialog.view.mouseReleaseEvent}[kind](event)
        self.assertIsNone(dialog.view.region);self.assertIsNone(dialog.view.drag_start)

    def test_native_geometry_updates_even_with_no_decoded_frame(self):
        dialog=self.dialog();dialog.player=Mock();dialog.sink=Mock();dialog.surface=Mock()
        dialog.sink.videoFrame.return_value.isValid.return_value=False
        dialog._seek_retry_at=__import__('time').monotonic()
        dialog.view.resize(700,420);dialog.poll()
        dialog.surface.geometry.assert_called_with(dialog.view.rect())
        self.assertFalse(dialog.settled_frame())

    def test_first_frame_notification_pauses_priming_and_reseeks_latest_target(self):
        dialog=self.dialog();dialog.timeline.setValue(21);dialog._decode_timer.stop()
        dialog.player=Mock();dialog.sink=Mock();dialog.video=Mock()
        frame=Mock();frame.isValid.return_value=True
        frame.startTime.return_value=900000;frame.endTime.return_value=933334
        dialog.sink.videoFrame.return_value=frame
        dialog.frame_arrived(frame)
        self.assertTrue(dialog._primed);dialog.player.pause.assert_called_once()
        self.assertTrue(dialog._decode_timer.isActive())
        self.assertEqual(dialog._paused_reseek_target,700000)
        dialog._decode_timer.stop();dialog.request_frame()
        dialog.player.setPosition.assert_called_with(701)
        dialog.player.play.assert_not_called()
        dialog.frame_arrived(frame)
        self.assertFalse(dialog._decode_timer.isActive(),'Repeated stale notifications must not flood seek requests')

    def test_ready_decoder_retries_stay_paused_and_live_playback_is_not_stopped(self):
        dialog=self.dialog();dialog.player=Mock();dialog.sink=Mock();dialog._primed=True
        dialog.request_frame();dialog.request_frame()
        dialog.player.play.assert_not_called()
        dialog.playing=True;dialog.player.reset_mock()
        frame=Mock();frame.isValid.return_value=True
        dialog.frame_arrived(frame)
        dialog.player.pause.assert_not_called()

    def test_gpu_updates_only_send_appearance_and_skip_unchanged_markers(self):
        effect=default_effect('Circle')
        effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect)
        self.ready(dialog)
        dialog.surface=Mock()
        dialog.refresh_preview()
        dialog.refresh_preview()
        updates=[call.args[1] for call in dialog.surface.root.setProperty.call_args_list if call.args[0]=='markers']
        self.assertEqual(len(updates),1)
        self.assertTrue(updates[0])
        self.assertNotIn('analysis',updates[0][0])
        self.assertNotIn('anchors',updates[0][0])

    def test_monitor_does_not_replace_decoder_when_a_proxy_arrives(self):
        dialog=self.dialog()
        dialog.player=Mock()
        dialog.video=Mock()
        self.host.proxies={self.media.id:str(self.root/'compatible.mp4')}
        dialog.sink=Mock()
        dialog.sink.videoFrame.return_value.isValid.return_value=False
        original=dialog._playback_source
        with patch('kinetic_cut.media_source.set_media_source') as change:
            dialog.poll()
        change.assert_not_called()
        self.assertEqual(dialog._playback_source,original)

    def test_unanalysed_privacy_markers_do_not_black_out_source(self):
        from kinetic_cut.tracking_effect import MODES
        dialog=self.dialog()
        self.ready(dialog)
        dialog.view.region=None
        dialog.surface=Mock()
        for mode in MODES:
            dialog.mode.setCurrentText(mode)
            dialog.surface.reset_mock()
            dialog.refresh_preview()
            calls={call.args[0]:call.args[1] for call in dialog.surface.root.setProperty.call_args_list}
            self.assertFalse(calls['showMarkers'],mode)
            self.assertEqual(dialog._published_markers,[],mode)
        workers=len(self.host.workers)
        dialog.view.region=[.1,.2,.3,.4]
        for mode in MODES:
            dialog.mode.setCurrentText(mode)
            dialog.refresh_preview()
            self.assertTrue(dialog._published_markers,mode)
            self.assertLess(dialog._published_markers[0]['w'],.9,mode)
        self.assertEqual(len(self.host.workers),workers)
        self.assertFalse(dialog.effect.get('analysis'))

    def test_guided_range_limits_long_sources_and_passes_only_selected_interval(self):
        self.item.duration=3600
        dialog=self.dialog()
        self.ready(dialog)
        self.assertIn('Draw target',dialog.guide.accessibleName())
        self.assertEqual(dialog.analysis_item().duration,10)
        dialog.range_end.setValue(600)
        selected=dialog.analysis_item()
        self.assertLessEqual(selected.source_duration,30.001)
        dialog.range_start.setValue(12)
        dialog.range_end.setValue(17)
        dialog.timeline.setValue(12*30)
        dialog._decode_timer.stop()
        self.ready(dialog)
        def analyse(media,item,*args,**kwargs):
            self.assertEqual(item.in_point,12)
            self.assertEqual(item.duration,5)
            raise ValueError('Fixture stops before decoding')
        with patch('kinetic_cut.object_tracking.analyze',side_effect=analyse):
            dialog.track()
            self.host.workers[-1].run()
        self.assertFalse(dialog._busy)
        self.assertEqual(self.item.duration,3600)

    def test_loaded_source_without_a_frame_is_primed_again(self):
        from PySide6.QtMultimedia import QMediaPlayer
        dialog=self.dialog()
        dialog.timeline.setValue(21)
        dialog._decode_timer.stop()
        dialog.player=Mock()
        dialog.player.mediaStatus.return_value=QMediaPlayer.LoadedMedia
        dialog.sink=Mock()
        dialog.sink.videoFrame.return_value.isValid.return_value=False
        dialog.poll()
        dialog.player.setPosition.assert_called_with(701)
        dialog.player.play.assert_called_once()

    def test_transport_buttons_follow_previous_then_next_order(self):
        dialog=self.dialog()
        controls=dialog.transport_controls
        self.assertEqual(controls.itemAt(0).widget().text(),'Play')
        self.assertEqual([controls.itemAt(n).widget().toolTip() for n in (1,2)],
                         ['Previous frame','Next frame'])

    def test_three_panels_and_draw_cursor_are_local_to_tracking(self):
        dialog=self.dialog()
        self.assertEqual(dialog.splitter.count(),3)
        self.assertTrue(dialog.analysis_panel.isAncestorOf(dialog.anchor_list))
        self.assertTrue(dialog.marker_editor.isAncestorOf(dialog.mode))
        self.assertEqual(dialog.view.cursor().shape(),Qt.CrossCursor)
        self.assertIn('Click Analyse target',dialog.guide.accessibleName())
        self.assertNotIn('Step 1',dialog.range_hint.text())

    def test_marker_panel_collapses_and_restores_without_losing_properties(self):
        dialog=self.dialog();dialog.show();QApplication.processEvents()
        editor=dialog.marker_editor
        editor.change('offset_x',75)
        original=dialog.result_effect()
        width=dialog.view.width()
        dialog.marker_toggle.click();QApplication.processEvents()
        self.assertTrue(dialog.marker_panel.isHidden())
        self.assertGreater(dialog.view.width(),width)
        self.assertEqual(dialog.marker_toggle.accessibleName(),'Show marker properties')
        dialog.marker_toggle.click();QApplication.processEvents()
        self.assertFalse(dialog.marker_panel.isHidden())
        self.assertEqual(dialog.marker_toggle.accessibleName(),'Hide marker properties')
        self.assertEqual(dialog.result_effect(),original)

    def test_reference_cards_group_controls_and_colour_swatches_remain_live(self):
        dialog=self.dialog();dialog.show();QApplication.processEvents()
        from kinetic_cut.tracking_design import TrackingCard
        self.assertGreaterEqual(len(dialog.findChildren(TrackingCard)),8)
        self.assertIsNot(dialog.marker_editor.form,dialog.marker_editor.option_form)
        dialog.mode.setCurrentText('Circle')
        original=dialog.result_effect()
        dialog.marker_settings_card.toggle.click()
        self.assertTrue(dialog.marker_settings_card.body.isHidden())
        dialog.marker_settings_card.toggle.click()
        self.assertFalse(dialog.marker_settings_card.body.isHidden())
        self.assertEqual(dialog.result_effect(),original)
        dialog.marker_editor.change('color','#45ddaa')
        button=dialog.marker_editor.colours['color']
        self.assertFalse(button.icon().isNull())
        self.assertEqual(button.toolTip(),'#ff45ddaa')
        self.assertIs(dialog.marker_editor.fill.parentWidget(),dialog.marker_options_card.body)
        QTest.mouseClick(dialog.marker_editor.fill,Qt.LeftButton,pos=QPoint(8,dialog.marker_editor.fill.height()//2))
        self.assertTrue(dialog.marker_editor.current()['fill'])
        changed=dialog.result_effect()
        dialog.guide_toggle.click();dialog.guide_toggle.click()
        self.assertEqual(dialog.result_effect(),changed)

    def test_preview_expansion_and_escape_restore_collapsed_panel_state(self):
        dialog=self.dialog();dialog.show();QApplication.processEvents()
        dialog.marker_toggle.click();QApplication.processEvents()
        width=dialog.view.width()
        original=dialog.result_effect()
        dialog.preview_expand.click();QApplication.processEvents()
        self.assertGreater(dialog.view.width(),width)
        self.assertFalse(dialog.analysis_panel.isVisible())
        self.assertFalse(dialog.marker_toggle.isEnabled())
        QTest.keyClick(dialog,Qt.Key_Escape);QApplication.processEvents()
        self.assertFalse(dialog.preview_expand.isChecked())
        self.assertTrue(dialog.analysis_panel.isVisible())
        self.assertTrue(dialog.marker_panel.isHidden())
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.result_effect(),original)

    def test_saved_target_can_be_removed_before_analysis_and_clears_preview(self):
        dialog=self.dialog();self.ready(dialog)
        dialog.add_anchor()
        self.assertEqual(len(dialog.anchors),1)
        self.assertEqual(len(dialog.timeline.keyframes),1)
        dialog.anchor_list.selectRow(0)
        menu=dialog.analysis_menu()
        next(a for a in menu.actions() if a.text()=='Remove selected frames').trigger()
        self.assertFalse(dialog.anchors)
        self.assertIsNone(dialog.view.region)
        self.assertFalse(dialog.timeline.keyframes)
        self.assertFalse(dialog.effect.get('analysis'))

    def test_diamond_seeks_selects_and_deleting_correction_restores_original(self):
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect);dialog.show()
        dialog.timeline.setValue(42);dialog._decode_timer.stop();self.ready(dialog)
        dialog.view.region=[.2,.2,.2,.2]
        dialog.add_anchor()
        self.assertEqual(dialog.timeline.keyframes,[0,42,83])
        dialog.timeline.setValue(0);dialog._decode_timer.stop()
        QApplication.processEvents()
        point=dialog.timeline.keyframe_position(42).toPoint()
        QTest.mouseClick(dialog.timeline,Qt.LeftButton,pos=point)
        self.assertEqual(dialog.timeline.value(),42)
        self.assertEqual([i.row() for i in dialog.anchor_list.selectionModel().selectedRows()],[1])
        dialog.player=Mock()
        QTest.keyClick(dialog.anchor_list,Qt.Key_Space)
        self.assertTrue(dialog.playing)
        dialog.pause_for_edit()
        workers=len(self.host.workers)
        dialog.remove_selected_frames()
        from kinetic_cut.object_tracking import sample,validate
        self.assertEqual(sample(dialog.effect['analysis'],1.4)['box'],self.analysis['frames'][1]['box'])
        self.assertTrue(validate(dialog.effect['analysis']))
        self.assertFalse(dialog.dirty_track)
        self.assertTrue(dialog.apply_button.isEnabled())
        self.assertEqual(len(self.host.workers),workers)

    def test_deleting_endpoint_corrections_keeps_a_valid_analysis(self):
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        effect['anchors']=[dict(time=0,box=[.1,.3,.1,.2]),dict(time=2.8,box=[.7,.3,.1,.2])]
        dialog=self.dialog(effect)
        dialog.select_frame_rows([0,2]);dialog.remove_selected_frames()
        from kinetic_cut.object_tracking import validate
        self.assertTrue(validate(dialog.effect['analysis']))
        self.assertFalse(dialog.anchors)
        self.assertEqual(dialog.effect['analysis']['frames'][0]['time'],0)
        self.assertEqual(dialog.effect['analysis']['frames'][-1]['time'],2.8)

    def test_analysis_fills_every_sample_and_batch_edits_are_source_timed(self):
        from kinetic_cut.tracking_effect import render_effects
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect);self.ready(dialog)
        self.assertEqual(dialog.anchor_list.rowCount(),3)
        self.assertEqual(dialog.timeline.keyframes,[0,42,83])
        trajectory=copy.deepcopy(dialog.effect['analysis'])
        dialog.select_frame_rows([1,2]);dialog.seek_anchor(1);self.ready(dialog)
        dialog.mode.setCurrentText('Arrow');dialog.marker_editor.fields['opacity'].setValue(65)
        result=dialog.result_effect();item=copy.deepcopy(self.item);item.effects=[result]
        before=render_effects(item,1.39)[0];after=render_effects(item,1.4)[0]
        self.assertEqual(before['mode'],'Circle');self.assertEqual(after['mode'],'Arrow')
        self.assertEqual(after['opacity'],65)
        self.assertEqual([r['time'] for r in result['markers'][0]['appearance_keys']],[1.4,2.8])
        self.assertEqual(dialog.effect['analysis'],trajectory)
        self.assertEqual(self.item.effects,[])
        # Save/load uses the existing effect-data serialization, without changes
        # to project schemas or media paths.
        self.project.timeline[0].effects=[result]
        loaded=Project.from_dict(self.project.to_dict())
        self.assertEqual(render_effects(loaded.timeline[0],2)[0]['mode'],'Arrow')

    def test_table_ctrl_and_shift_selection_highlight_the_same_timeline_diamonds(self):
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect);dialog.show();QApplication.processEvents()
        table=dialog.anchor_list
        def click(row,mods=Qt.NoModifier):
            point=table.visualItemRect(table.item(row,0)).center()
            QTest.mouseClick(table.viewport(),Qt.LeftButton,mods,pos=point)
            return {i.row() for i in table.selectionModel().selectedRows()}
        self.assertEqual(click(0),{0});self.assertEqual(dialog.timeline.selected_rows,{0})
        self.assertEqual(click(2,Qt.ControlModifier),{0,2})
        self.assertEqual(dialog.timeline.selected_rows,{0,2})
        self.assertEqual(click(0),{0})
        self.assertEqual(click(2,Qt.ShiftModifier),{0,1,2})
        self.assertEqual(dialog.timeline.selected_rows,{0,1,2})
        self.assertEqual(click(1,Qt.ControlModifier),{0,2})
        self.assertEqual(dialog.timeline.selected_rows,{0,2})

    def test_timeline_drag_keeps_geometry_stable_and_tracks_pointer_both_directions(self):
        dialog=self.dialog();dialog.show();QApplication.processEvents()
        timeline=dialog.timeline;timeline.resize(420,54)
        width=timeline.width();label=dialog.time_label.minimumSizeHint().width()
        QTest.mousePress(timeline,Qt.LeftButton,pos=QPoint(40,41))
        forward=[]
        for x in range(50,370,20):
            QTest.mouseMove(timeline,QPoint(x,41));forward.append(timeline.value())
            self.assertEqual(timeline.width(),width)
        backward=[]
        for x in range(360,40,-20):
            QTest.mouseMove(timeline,QPoint(x,41));backward.append(timeline.value())
        QTest.mouseRelease(timeline,Qt.LeftButton,pos=QPoint(40,41))
        self.assertEqual(forward,sorted(forward));self.assertEqual(backward,sorted(backward,reverse=True))
        self.assertEqual(dialog.time_label.minimumSizeHint().width(),label)
        self.assertNotIn('Source',dialog.time_label.text())

    def test_timeline_zoom_ctrl_selection_wheel_and_blank_click_deselect(self):
        from PySide6.QtGui import QWheelEvent
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect);dialog.show();QApplication.processEvents()
        t=dialog.timeline;t.zoom_by(2);self.assertGreater(t.zoom,1)
        t.zoom_by(.5)
        QTest.mouseClick(t,Qt.LeftButton,pos=t.keyframe_position(0).toPoint())
        QTest.mouseClick(t,Qt.LeftButton,Qt.ControlModifier,pos=t.keyframe_position(42).toPoint())
        self.assertEqual(t.selected_rows,{0,1})
        QTest.mouseClick(t,Qt.LeftButton,pos=t.keyframe_position(0).toPoint())
        QTest.mouseClick(t,Qt.LeftButton,Qt.ShiftModifier,pos=t.keyframe_position(83).toPoint())
        self.assertEqual(t.selected_rows,{0,1,2})
        self.assertEqual({i.row() for i in dialog.anchor_list.selectionModel().selectedRows()},{0,1,2})
        QTest.mouseClick(t,Qt.LeftButton,Qt.ControlModifier,pos=t.keyframe_position(42).toPoint())
        self.assertEqual(t.selected_rows,{0,2})
        QTest.mouseClick(t,Qt.LeftButton,pos=t.keyframe_position(42).toPoint())
        event=QWheelEvent(QPointF(30,20),QPointF(30,20),QPoint(),QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        QApplication.sendEvent(t,event)
        self.assertEqual(t.selected_rows,{2});self.assertEqual(t.value(),83)
        QTest.mouseClick(t,Qt.LeftButton,pos=QPoint(20,41))
        self.assertFalse(t.selected_rows);self.assertFalse(dialog.selected_frame_times())

    def test_removing_all_analysis_frames_clears_track_and_requires_analysis(self):
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect);dialog.anchor_list.selectAll();dialog.remove_selected_frames()
        self.assertTrue(dialog.dirty_track);self.assertFalse(dialog.effect['analysis'])
        self.assertEqual(dialog.anchor_list.rowCount(),0)
        self.assertFalse(dialog.apply_button.isEnabled())

    def test_native_tool_cursor_follows_marker_hand_without_stale_crosshair(self):
        dialog=self.dialog();dialog.surface=Mock()
        dialog.view.set_tool('transform');dialog.view.setCursor(Qt.OpenHandCursor)
        self.assertEqual(dialog.surface.view.setCursor.call_args.args[0].shape(),Qt.OpenHandCursor)
        self.assertEqual(dialog.surface.container.setCursor.call_args.args[0].shape(),Qt.OpenHandCursor)

    def test_partial_range_analysis_can_be_reopened_and_applied(self):
        self.item.duration=60
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect)
        self.assertFalse(dialog.dirty_track)
        dialog.accept()
        self.assertEqual(dialog.result(),QDialog.Accepted)
        self.assertEqual(self.item.duration,60)

    def test_single_marker_has_one_type_chooser_and_multi_marker_picker_is_distinct(self):
        from kinetic_cut.tracking_effect import MODES
        dialog=self.dialog();dialog.show();QApplication.processEvents()
        editor=dialog.marker_editor
        self.assertEqual(dialog.mode.currentText(),'Censor Bar')
        self.assertEqual([dialog.mode.itemText(i) for i in range(dialog.mode.count())],list(MODES))
        self.assertTrue(editor.picker.isHidden())
        self.assertTrue(editor.single_label.isVisible())
        self.assertTrue(editor.kind.isHidden())
        action=next(a for a in editor.add_button.menu().actions() if a.text()=='Arrow')
        action.trigger();QApplication.processEvents()
        self.assertEqual(len(editor.markers),2)
        self.assertTrue(editor.picker.isVisible())
        self.assertTrue(editor.single_label.isHidden())
        self.assertEqual(dialog.mode.currentText(),'Arrow')
        editor.picker.setCurrentIndex(0)
        self.assertEqual(dialog.mode.currentText(),'Censor Bar')

    def test_type_popup_opens_below_and_mouse_selection_changes_the_marker(self):
        dialog=self.dialog();dialog.show();QApplication.processEvents()
        dialog.mode.showPopup();QApplication.processEvents()
        popup=dialog.mode.view().window()
        self.assertTrue(popup.isVisible())
        self.assertGreaterEqual(popup.y(),dialog.mode.mapToGlobal(QPoint(0,dialog.mode.height())).y())
        index=dialog.mode.model().index(dialog.mode.findText('Arrow'),0)
        dialog.mode.view().scrollTo(index);QApplication.processEvents()
        point=dialog.mode.view().visualRect(index).center()
        QTest.mouseClick(dialog.mode.view().viewport(),Qt.LeftButton,pos=point)
        self.assertEqual(dialog.mode.currentText(),'Arrow')
        self.assertEqual(dialog.marker_editor.current()['mode'],'Arrow')
        dialog.mode.hidePopup()

    def test_begin_commits_a_valid_selected_range_without_changing_clip_length(self):
        from kinetic_cut.tracking_ui import begin
        self.item.duration=60
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        with patch('kinetic_cut.tracking_dialog.TrackingDialog') as factory:
            factory.return_value.exec.return_value=QDialog.Accepted
            factory.return_value.result_effect.return_value=effect
            begin(self.host)
        self.assertEqual(self.item.effects,[effect])
        self.assertEqual(self.item.duration,60)
        self.host.model_changed.assert_called_once_with()

    def test_properties_toggle_is_after_source_name_and_uses_vertical_arrows(self):
        dialog=self.dialog();dialog.show();QApplication.processEvents()
        self.assertIs(dialog.marker_toggle.parentWidget(),dialog.source_label.parentWidget())
        self.assertGreaterEqual(dialog.marker_toggle.x(),dialog.source_label.geometry().right())
        self.assertEqual(dialog.marker_toggle.arrowType(),Qt.DownArrow)
        dialog.marker_toggle.click()
        self.assertEqual(dialog.marker_toggle.arrowType(),Qt.UpArrow)

    def test_real_modal_modes_and_deferred_deletes_do_not_change_headers(self):
        import gc
        from PySide6.QtCore import QTimer
        from kinetic_cut.tracking_design import TrackingCard
        dialog=self.dialog();self.ready(dialog)
        failures=[]
        def exercise():
            try:
                titles={card:card.title_label.text() for card in dialog.findChildren(TrackingCard)}
                for mode in ('Blur','Label','Arrow','Circle','Censor Bar'):
                    dialog.mode.setCurrentText(mode)
                    dialog.info.setText('Ready: this text belongs only in the status body.')
                    gc.collect();QApplication.sendPostedEvents(None,QEvent.DeferredDelete);QApplication.processEvents()
                    for card,title in titles.items():self.assertEqual(card.title_label.text(),title)
                    self.assertEqual(dialog.mode.count(),9)
                self.assertEqual(dialog._ui_cards['status'].title_label.text(),'Tracking status')
                # All visible root widgets must be intentional top-level layout entries.
                managed={dialog.layout().itemAt(i).widget() for i in range(dialog.layout().count())}
                for widget in dialog.findChildren(QWidget,options=Qt.FindDirectChildrenOnly):
                    if widget.isVisible() and not widget.isWindow():self.assertIn(widget,managed,widget.objectName())
            except Exception as error:failures.append(error)
            finally:dialog.reject()
        QTimer.singleShot(0,exercise)
        dialog.exec()
        if failures:raise failures[0]

    def test_all_analysis_actions_fit_supported_window_sizes(self):
        dialog=self.dialog();dialog.show()
        for size in ((980,700),(1100,760),(1280,850),(1440,1000)):
            dialog.resize(*size);QApplication.processEvents()
            panel=dialog.analysis_panel
            for widget in (dialog.track_button,dialog.anchor_list,dialog.anchor_button,dialog.remove_frame_button,dialog.clear_target_button,dialog.clear_button):
                top=widget.mapTo(panel,QPoint(0,0))
                self.assertGreaterEqual(top.y(),0,(size,widget.text() if hasattr(widget,'text') else 'table'))
                self.assertLessEqual(top.y()+widget.height(),panel.height(),(size,widget.objectName(),top.y(),widget.height(),panel.height()))

    def test_marker_gizmo_moves_scales_and_rotates_without_touching_track(self):
        import math
        effect=default_effect('Circle');effect['analysis']=copy.deepcopy(self.analysis)
        dialog=self.dialog(effect);self.ready(dialog)
        dialog.surface=Mock();dialog.view.resize(640,360);dialog.transform_tool.setChecked(True);dialog.refresh_preview()
        original=copy.deepcopy(dialog.effect['analysis']);workers=len(self.host.workers)
        geometry=dialog.view.selected();transform,rect=dialog.view.shape(geometry)
        center=transform.map(rect.center()).toPoint()
        QTest.mousePress(dialog.view,Qt.LeftButton,pos=center)
        QTest.mouseMove(dialog.view,center+QPoint(20,10))
        QTest.mouseRelease(dialog.view,Qt.LeftButton,pos=center+QPoint(20,10))
        self.assertAlmostEqual(dialog.marker_editor.current()['offset_x'],10,delta=.5)
        self.assertAlmostEqual(dialog.marker_editor.current()['offset_y'],5,delta=.5)
        point=dialog.view.handles(dialog.view.selected())['se'].toPoint()
        QTest.mousePress(dialog.view,Qt.LeftButton,pos=point)
        QTest.mouseMove(dialog.view,point+QPoint(20,20))
        QTest.mouseRelease(dialog.view,Qt.LeftButton,pos=point+QPoint(20,20))
        self.assertGreater(dialog.marker_editor.current()['width'],100)
        self.assertGreater(dialog.marker_editor.current()['height'],100)
        geometry=dialog.view.selected();transform,rect=dialog.view.shape(geometry)
        origin=transform.map(QPointF(0,0));knob=dialog.view.handles(geometry)['rotate']
        relative=knob-origin;target=origin+QPointF(-relative.y(),relative.x())
        QTest.mousePress(dialog.view,Qt.LeftButton,pos=knob.toPoint())
        QTest.mouseMove(dialog.view,target.toPoint())
        QTest.mouseRelease(dialog.view,Qt.LeftButton,pos=target.toPoint())
        self.assertAlmostEqual(dialog.marker_editor.current()['rotation'],90,delta=2)
        self.assertEqual(dialog.effect['analysis'],original)
        self.assertEqual(len(self.host.workers),workers)
        self.assertFalse(dialog.anchors)

    def test_text_and_arrow_gizmo_resize_their_actual_visual_properties(self):
        for mode,key in (('Arrow','arrow_length'),('Label','font_size')):
            effect=default_effect(mode);effect['analysis']=copy.deepcopy(self.analysis)
            effect.update(offset_x=100,font_size=14)
            dialog=self.dialog(effect);self.ready(dialog);dialog.surface=Mock()
            dialog.view.resize(640,360);dialog.transform_tool.setChecked(True);dialog.refresh_preview()
            before=dialog.marker_editor.current()[key]
            point=dialog.view.handles(dialog.view.selected())['e'].toPoint()
            QTest.mousePress(dialog.view,Qt.LeftButton,pos=point)
            QTest.mouseMove(dialog.view,point+QPoint(20,0))
            QTest.mouseRelease(dialog.view,Qt.LeftButton,pos=point+QPoint(20,0))
            self.assertGreater(dialog.marker_editor.current()[key],before,mode)
            self.assertEqual(dialog.effect['analysis'],self.analysis)

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
