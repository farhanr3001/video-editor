"""Live drag progress without flooding shared decoders or hiding timeline gaps."""
import copy
import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QWidget

from kinetic_cut.model import MediaItem, Project, TimelineItem
from kinetic_cut.transport import TimelineTransport


class LiveScrubbingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=QWidget()
        self.project=Project(media=[MediaItem('source','fixture.mp4','video','source',40,640,360,60)])
        self.project.video_tracks=['video_1','video_2','video_3']
        self.project.timeline=[TimelineItem('v'+str(n),'source',track,0,8)
                               for n,track in enumerate(self.project.video_tracks)]
        self.window.project=self.project; self.window.proxies={}; self.window.settings={}
        self.window.preview=SimpleNamespace(caption_focus=False,frames={},active_frames={},fallback_frames={},
                                            effect_cache={},update=Mock(),set_frame=Mock(),frame_work=Mock(return_value=None))
        self.transport=TimelineTransport(self.window); self.transport._project=self.project
        self.window.transport=self.transport
        self.transport.changed.connect(lambda value:setattr(self.project,'playhead',value))
        self.key=('source',0.,1.,'video'); self.created={}
        self.create(self.key)
        self.creator=patch.object(self.transport,'create_decoder',side_effect=self.create); self.creator.start()
        self.invoke=patch('kinetic_cut.transport.QMetaObject.invokeMethod'); self.invoker=self.invoke.start()
        self.image=QImage(16,9,QImage.Format_RGB32); self.image.fill(Qt.blue)

    def tearDown(self):
        self.transport.shutdown(); self.creator.stop(); self.invoke.stop()
        self.window.close(); self.window.deleteLater(); self.app.processEvents()

    def create(self,key,*args):
        player=Mock(); player.position.return_value=0
        player.playbackState.return_value=QMediaPlayer.PausedState
        player.mediaStatus.return_value=QMediaPlayer.BufferedMedia
        player.setPosition.side_effect=lambda value:setattr(player.position,'return_value',value)
        output=Mock(); output.property.return_value=0.
        sink=Mock() if key[3]=='video' else None
        if sink:
            sink._frame_stamp=None; sink.videoFrame.return_value.isValid.return_value=False
        decoder=(player,output,sink)
        self.transport.decoders[key]=decoder; self.created[key]=decoder

    def scrub(self,value):
        self.transport._last_scrub_sync=-100.
        self.transport.scrub(value); self.transport.frame_timer.stop()

    def frame(self,key,start,end=None,image=None):
        sink=self.transport.decoders[key][2]; frame=sink.videoFrame.return_value
        frame.isValid.return_value=True; frame.startTime.return_value=start
        frame.endTime.return_value=end if end is not None else start+16667
        frame.toImage.return_value=image if image is not None else self.image
        return frame

    def test_release_uses_timeline_transport_without_opening_legacy_source_player(self):
        from kinetic_cut.ui import MainWindow
        owner=SimpleNamespace(transport=Mock(),active_main=Mock(),player=Mock())
        MainWindow.finish_scrub(owner)
        owner.transport.finish_scrub.assert_called_once_with()
        owner.active_main.assert_not_called(); owner.player.setPosition.assert_not_called()

    def test_layout_copies_issue_one_native_seek_and_rate_change(self):
        self.transport.position=2.; self.transport.sync(True)
        player=self.created[self.key][0]
        player.setPosition.assert_called_once_with(2000)
        player.setPlaybackRate.assert_called_once_with(1.)
        self.assertEqual(set(self.window.preview.active_frames.values()),{self.key})
        self.assertEqual(len(self.window.preview.active_frames),3)

    def test_warming_layout_copies_primes_one_neighbour_decoder(self):
        for item in self.project.timeline:item.duration=2.
        for n,track in enumerate(self.project.video_tracks):
            self.project.timeline.append(TimelineItem('next'+str(n),'source',track,2,2,in_point=10))
        self.transport.position=1.5; self.transport.sync()
        warm=('source',8.,1.,'video'); player=self.created[warm][0]
        player.setPosition.assert_called_once_with(10000); player.play.assert_called_once()
        self.assertEqual(self.transport.warm_keys,{warm})

    def test_drag_publishes_inflight_frame_then_dispatches_only_latest_cursor(self):
        self.scrub(1.); epoch=self.transport._frame_epochs[self.key]
        for value in (2.,3.,5.):self.scrub(value)
        player=self.created[self.key][0]
        player.setPosition.assert_called_once_with(1000)
        self.assertEqual(self.transport._frame_epochs[self.key],epoch)
        self.assertEqual(self.transport._scrub_decoder_targets[self.key],5000)
        self.frame(self.key,1_000_000)
        with patch.object(self.transport,'sync',wraps=self.transport.sync) as sync:
            self.transport.poll_frames()
            sync.assert_not_called()  # publication never nests native controls
            self.assertEqual(self.window.preview.frames[self.key],self.image)
            self.assertTrue(self.transport._scrub_timer.isActive())
            self.app.processEvents(); self.transport.frame_timer.stop()
            sync.assert_called_once_with(True)
        self.assertEqual([call.args[0] for call in player.setPosition.call_args_list],[1000,5000])
        self.assertEqual(self.transport._pending_video_seeks[self.key],5000)

    def test_backward_drag_accepts_inflight_frame_before_latest_reverse_seek(self):
        self.scrub(5.); self.scrub(2.)
        self.frame(self.key,5_000_000); self.transport.poll_frames()
        self.assertIn(self.key,self.window.preview.frames)
        self.app.processEvents(); self.transport.frame_timer.stop()
        self.assertEqual(self.transport._pending_video_seeks[self.key],2000)
        old=self.frame(self.key,5_000_000); old.toImage.reset_mock()
        self.transport.poll_frames(); old.toImage.assert_not_called()
        self.frame(self.key,2_000_000); self.transport.poll_frames()
        self.assertNotIn(self.key,self.transport._pending_video_seeks)

    def test_release_supersedes_old_worker_and_displays_exact_final_frame(self):
        self.scrub(1.); epoch=self.transport._frame_epochs[self.key]
        future=Future(); future.set_result((self.image,{}))
        self.transport._frame_jobs=[(self.key,epoch,1,future)]
        self.scrub(4.); self.transport.finish_scrub(); self.transport.frame_timer.stop()
        self.assertFalse(self.transport.scrubbing); self.assertFalse(self.transport._scrub_decoder_targets)
        self.assertGreater(self.transport._frame_epochs[self.key],epoch)
        with patch.object(self.transport,'frame',wraps=self.transport.frame) as publish:
            self.transport.publish_frames(); publish.assert_not_called()
            stale=self.frame(self.key,1_000_000); self.transport.poll_frames(); stale.toImage.assert_not_called()
            exact=self.frame(self.key,4_000_000); self.transport.poll_frames(); exact.toImage.assert_called_once()
            publish.assert_called_once()
        self.assertEqual(self.transport._video_seek_floor[self.key],4_000_000)

    def test_explicit_reverse_seek_rejects_pending_scrub_frame(self):
        self.scrub(5.); self.scrub(7.)
        self.transport.seek(1.); self.transport.frame_timer.stop()
        self.assertFalse(self.transport._scrub_decoder_targets)
        frame=self.frame(self.key,5_000_000); self.transport.poll_frames(); frame.toImage.assert_not_called()
        self.frame(self.key,1_000_000); self.transport.poll_frames()
        self.assertIn(self.key,self.window.preview.frames)

    def add_distant_cut(self):
        for item in self.project.timeline:item.duration=5.
        for n,track in enumerate(self.project.video_tracks):
            self.project.timeline.append(TimelineItem('distant'+str(n),'source',track,10,5,in_point=30))
        self.transport.position=1.; self.transport.sync(True); self.transport.frame_timer.stop()
        self.transport.frame(self.key,self.image)
        self.transport._pending_video_seeks.clear()
        return ('source',20.,1.,'video')

    def test_distant_active_seek_holds_lane_image_until_valid_new_frame(self):
        incoming=self.add_distant_cut()
        self.transport.seek(11.); self.transport.frame_timer.stop()
        self.assertEqual(set(self.window.preview.active_frames.values()),{incoming})
        self.assertEqual(len(self.window.preview.fallback_frames),3)
        self.assertTrue(all(image==self.image for image in self.window.preview.fallback_frames.values()))
        stale=self.frame(incoming,0); self.transport.poll_frames(); stale.toImage.assert_not_called()
        self.assertIn((incoming,'video_1'),self.transport._seek_holds)
        self.frame(incoming,31_000_000); self.transport.poll_frames()
        self.assertFalse(self.transport._seek_holds); self.assertFalse(self.window.preview.fallback_frames)

    def test_hold_is_bounded_and_does_not_restart_on_each_sync(self):
        self.add_distant_cut()
        with patch('kinetic_cut.transport.time.monotonic',return_value=20.):
            self.transport.seek(11.); self.transport.frame_timer.stop()
        self.assertTrue(self.window.preview.fallback_frames)
        with patch('kinetic_cut.transport.time.monotonic',return_value=22.01):
            self.transport.sync(True)
        self.assertFalse(self.window.preview.fallback_frames); self.assertFalse(self.transport._seek_holds)
        with patch('kinetic_cut.transport.time.monotonic',return_value=23.):self.transport.sync(True)
        self.assertFalse(self.window.preview.fallback_frames)

    def test_shared_incoming_decoder_keeps_each_lanes_own_previous_image(self):
        incoming=self.add_distant_cut()
        red=QImage(16,9,QImage.Format_RGB32); red.fill(Qt.red)
        blue=QImage(16,9,QImage.Format_RGB32); blue.fill(Qt.blue)
        self.transport.previous_video['video_1'].update(key=('red',0,1,'video'),image=red)
        self.transport.previous_video['video_2'].update(key=('blue',0,1,'video'),image=blue)
        self.transport.seek(11.); self.transport.frame_timer.stop()
        self.assertEqual(self.window.preview.fallback_frames['distant0'],red)
        self.assertEqual(self.window.preview.fallback_frames['distant1'],blue)
        self.assertEqual(set(self.window.preview.active_frames.values()),{incoming})
        self.created[incoming][0].setPosition.assert_called_once_with(31000)

    def test_one_hidden_lane_discards_its_hold_even_if_decoder_stays_active(self):
        incoming=self.add_distant_cut(); self.transport.seek(11.); self.transport.frame_timer.stop()
        self.project.track_states.setdefault('video_1',{})['visible']=False
        self.transport.sync(True); self.transport.frame_timer.stop()
        self.assertNotIn((incoming,'video_1'),self.transport._seek_holds)
        self.assertIn((incoming,'video_2'),self.transport._seek_holds)
        self.project.track_states['video_1']['visible']=True
        self.transport.sync(True); self.transport.frame_timer.stop()
        self.assertNotIn('distant0',self.window.preview.fallback_frames)

    def test_missing_inflight_frame_retries_latest_target_after_bounded_deadline(self):
        with patch('kinetic_cut.transport.time.monotonic',return_value=0.):self.scrub(1.)
        epoch=self.transport._frame_epochs[self.key]
        with patch('kinetic_cut.transport.time.monotonic',return_value=.2):self.scrub(3.)
        with patch('kinetic_cut.transport.time.monotonic',return_value=1.999):self.transport._retry_scrub()
        self.assertEqual(self.transport._pending_video_seeks[self.key],1000)
        self.assertEqual(self.transport._frame_epochs[self.key],epoch)
        with patch('kinetic_cut.transport.time.monotonic',return_value=2.001):self.transport._retry_scrub()
        self.assertEqual(self.transport._pending_video_seeks[self.key],3000)
        self.assertGreater(self.transport._frame_epochs[self.key],epoch)
        stale=self.frame(self.key,1_000_000); self.transport.poll_frames(); stale.toImage.assert_not_called()
        self.frame(self.key,3_000_000); self.transport.poll_frames()
        self.assertNotIn(self.key,self.transport._pending_video_seeks)

    def test_inactive_same_source_video_reuses_player_and_invalidates_old_publication(self):
        incoming=('source',20.,1.,'video'); player=self.created[self.key][0]
        self.transport._required_video_keys={incoming}
        self.transport.position_decoder(self.key,1000); old_epoch=self.transport._frame_epochs[self.key]
        future=Future(); future.set_result((self.image,{}))
        self.transport._frame_jobs=[(self.key,old_epoch,1,future)]
        self.transport._scrub_decoder_targets[self.key]=2000
        TimelineTransport.create_decoder(self.transport,incoming,self.project.media[0],True,'')
        self.assertNotIn(self.key,self.transport.decoders)
        self.assertIs(self.transport.decoders[incoming][0],player)
        self.assertEqual(player._transport_key,incoming)
        self.assertFalse(self.transport._scrub_decoder_targets)
        self.transport.position_decoder(incoming,31000)
        with patch.object(self.transport,'frame') as publish:
            self.transport.publish_frames(); publish.assert_not_called()
        player.stop.assert_not_called(); self.invoker.assert_not_called()
        self.assertGreater(self.transport._frame_epochs[incoming],old_epoch)

    def test_simultaneous_clocks_and_warmed_neighbour_cannot_be_stolen(self):
        incoming=('source',20.,1.,'video')
        self.transport._required_video_keys={self.key,incoming}
        self.assertFalse(self.transport._reuse_video_decoder(incoming))
        self.transport._required_video_keys={incoming}; self.transport._protected_warm_video_keys={self.key}
        self.assertFalse(self.transport._reuse_video_decoder(incoming))
        self.assertEqual(set(self.transport.decoders),{self.key})

    def test_sync_protects_simultaneous_clocks_and_active_transition_edges(self):
        from kinetic_cut.transitions import Transition
        for item in self.project.timeline:item.duration=5.
        self.project.timeline[1].in_point=2.
        self.project.timeline.append(TimelineItem('next','source','video_1',5,5,in_point=15))
        self.project.transitions=[Transition(id='dissolve',name='Cross Dissolve',track='video_1',
                                             start=4.5,duration=1.,left_item_id='v0',right_item_id='next')]
        simultaneous=('source',2.,1.,'video'); edge=('source',10.,1.,'video')
        self.transport.position=4.8
        checked=[]
        def protected_create(key,*args):
            checked.append(set(self.transport._required_video_keys))
            self.assertEqual(self.transport._required_video_keys,{self.key,simultaneous,edge})
            self.assertFalse(self.transport._reuse_video_decoder(key))
            self.create(key)
        with patch.object(self.transport,'create_decoder',side_effect=protected_create):self.transport.sync(True)
        self.transport.frame_timer.stop()
        self.assertTrue(checked)
        self.assertEqual(set(self.transport.decoders),{self.key,simultaneous,edge})
        self.assertEqual(self.window.preview.active_frames['next'],edge)

    def test_source_relink_retires_player_before_same_media_reuse(self):
        original=self.created[self.key][0]
        self.transport._media_source_paths={'source':'fixture.mp4'}
        self.project.media[0].path='replacement.mp4'
        self.transport.position=1.; self.transport.sync(True); self.transport.frame_timer.stop()
        self.assertIsNot(self.transport.decoders[self.key][0],original)
        self.assertEqual([call.args[1] for call in self.invoker.call_args_list],['stop','deleteLater'])

    def test_proxy_switch_retires_existing_video_before_reopening(self):
        from kinetic_cut.preview_quality import PreviewQuality
        original=self.created[self.key][0]
        self.window.proxies={'source':'old-proxy.mp4'}
        quality=PreviewQuality(self.window)
        quality.apply(force=True); self.transport.frame_timer.stop()
        self.assertIsNot(self.transport.decoders[self.key][0],original)
        self.assertFalse(self.window.proxies)
        self.assertEqual([call.args[1] for call in self.invoker.call_args_list],['stop','deleteLater'])
        quality.close(); quality.deleteLater()

    def test_unrelated_source_audio_and_speed_cannot_be_rebound(self):
        for incoming in (('other',20.,1.,'video'),('source',20.,2.,'video')):
            self.assertFalse(self.transport._reuse_video_decoder(incoming))
        self.transport.decoders.clear(); audio=('source',0.,1.,'audio:audio_1')
        self.create(audio)
        self.assertFalse(self.transport._reuse_video_decoder(('source',20.,1.,'video')))

    def test_loaded_callback_uses_rebound_identity_and_latest_seek(self):
        player,output,sink=self.created[self.key]
        self.transport.decoders.clear()
        with patch('kinetic_cut.transport.QMediaPlayer',return_value=player), \
             patch('kinetic_cut.transport.QAudioOutput',return_value=output), \
             patch('kinetic_cut.transport.QVideoSink',return_value=sink), \
             patch('kinetic_cut.media_source.set_media_source'):
            TimelineTransport.create_decoder(self.transport,self.key,self.project.media[0],True,'')
        callback=player.mediaStatusChanged.connect.call_args.args[0]
        player.mediaStatus.return_value=QMediaPlayer.LoadingMedia
        self.transport.position_decoder(self.key,1000)
        incoming=('source',20.,1.,'video'); self.transport._required_video_keys={incoming}
        self.assertTrue(self.transport._reuse_video_decoder(incoming))
        self.transport.position_decoder(incoming,31000); player.reset_mock()
        self.transport.decoder_loaded(self.key,player,QMediaPlayer.LoadedMedia)
        player.setPosition.assert_not_called(); player.play.assert_not_called()
        # A notification connected before rebinding follows the current owner,
        # not its retired key or previous requested timestamp.
        callback(QMediaPlayer.LoadedMedia)
        player.setPosition.assert_called_once_with(31000); player.play.assert_called_once()
        self.transport.retire_decoder(incoming); player.reset_mock(); callback(QMediaPlayer.LoadedMedia)
        player.play.assert_not_called()
        self.assertFalse(self.transport.decoders); self.assertFalse(self.transport._pending_video_seeks)

    def test_video_load_preserves_native_stream_clock_and_positions_pending_seek(self):
        player=self.created[self.key][0];player.mediaStatus.return_value=QMediaPlayer.LoadingMedia
        self.transport.position_decoder(self.key,1000);player.reset_mock()
        self.transport.decoder_loaded(self.key,player,QMediaPlayer.LoadedMedia)
        player.setActiveAudioTrack.assert_not_called()
        player.setPosition.assert_called_once_with(1000);player.play.assert_called_once()

    def test_audio_load_retains_audio_and_disables_only_video_track(self):
        key=('source',0.,1.,'audio:audio_1'); self.create(key)
        player=self.created[key][0]
        self.transport.decoder_loaded(key,player,QMediaPlayer.LoadedMedia)
        player.setActiveVideoTrack.assert_called_once_with(-1)
        player.activeAudioTrack.assert_not_called(); player.setActiveAudioTrack.assert_not_called()
        player.setPosition.assert_not_called(); player.play.assert_not_called()

    def test_already_disabled_video_audio_is_not_changed_on_repeated_load(self):
        player=self.created[self.key][0]; player.activeAudioTrack.return_value=-1
        self.transport.decoder_loaded(self.key,player,QMediaPlayer.LoadedMedia)
        player.setActiveAudioTrack.assert_not_called()
        player.setPosition.assert_not_called(); player.play.assert_not_called()

    def test_gap_and_end_have_no_held_video(self):
        self.add_distant_cut(); self.transport.seek(11.); self.transport.frame_timer.stop()
        for moment in (7.,15.):
            self.transport.seek(moment); self.transport.frame_timer.stop()
            self.assertFalse(self.window.preview.active_frames)
            self.assertFalse(self.window.preview.fallback_frames); self.assertFalse(self.transport._seek_holds)

    def test_hidden_offline_and_replacement_projects_clear_pending_holds(self):
        incoming=self.add_distant_cut(); self.transport.seek(11.); self.transport.frame_timer.stop()
        self.scrub(12.); self.assertIn(incoming,self.transport._scrub_decoder_targets)
        for track in self.project.video_tracks:self.project.track_states.setdefault(track,{})['visible']=False
        self.transport.sync(); self.transport.frame_timer.stop()
        self.assertFalse(self.window.preview.active_frames); self.assertFalse(self.window.preview.fallback_frames)
        self.assertFalse(self.transport._scrub_decoder_targets); self.assertFalse(self.transport._seek_holds)
        for track in self.project.video_tracks:self.project.track_states[track]['visible']=True
        self.transport.seek(11.); self.transport.frame_timer.stop()
        with patch('kinetic_cut.missing_media.unavailable',return_value=True):self.transport.sync()
        self.assertFalse(self.window.preview.fallback_frames); self.assertFalse(self.transport._seek_holds)
        replacement=copy.deepcopy(self.project); replacement.created_at+=1
        self.window.project=replacement; self.transport.sync(True); self.transport.frame_timer.stop()
        self.assertFalse(self.window.preview.fallback_frames); self.assertFalse(self.transport._scrub_decoder_targets)

    def test_paused_and_drag_frames_use_bounded_pixel_jobs(self):
        for scrubbing in (False,True):
            with self.subTest(scrubbing=scrubbing):
                self.transport.scrubbing=scrubbing; self.transport.playing=False
                self.transport.decoders[self.key][2]._frame_stamp=None
                self.frame(self.key,0)
                self.window.preview.frame_work.return_value=(SimpleNamespace(),[])
                future=Future(); executor=Mock(); executor.submit.return_value=future
                self.transport._frame_executor=executor
                self.transport.poll_frames()
                executor.submit.assert_called_once()
                self.assertEqual(len(self.transport._frame_jobs),1)
                self.assertNotIn(self.key,self.window.preview.frames)
                future.set_result((self.image,{})); self.transport.publish_frames()
                self.window.preview.frames.clear()

    def test_playing_clock_does_not_flush_an_unfinished_native_seek(self):
        self.transport.playing=True; self.transport.position=2.
        self.transport._pending_video_seeks[self.key]=1000
        player=self.created[self.key][0]; player.position.return_value=1000
        player.setPosition.reset_mock()
        self.transport.sync(); self.transport.frame_timer.stop()
        player.setPosition.assert_not_called()
        self.transport.sync(True); self.transport.frame_timer.stop()
        player.setPosition.assert_called_once_with(2000)

    def test_valid_priming_frame_pauses_before_pixel_readback(self):
        player=self.created[self.key][0]; player.playbackState.return_value=QMediaPlayer.PlayingState
        frame=self.frame(self.key,0)
        order=[]; player.pause.side_effect=lambda:order.append('pause')
        frame.toImage.side_effect=lambda:(order.append('pixels'),self.image)[1]
        self.transport.poll_frames()
        self.assertEqual(order[:2],['pause','pixels'])

    def test_buffered_seek_loaded_status_does_not_repeat_seek_or_start_playback(self):
        player=self.created[self.key][0]
        self.transport.position_decoder(self.key,1000);player.reset_mock()
        self.transport.decoder_loaded(self.key,player,QMediaPlayer.LoadedMedia)
        player.setPosition.assert_not_called();player.play.assert_not_called()
        self.assertEqual(self.transport._pending_video_seeks[self.key],1000)

    def test_initial_source_load_replays_latest_target_only_once(self):
        player=self.created[self.key][0];player.mediaStatus.return_value=QMediaPlayer.LoadingMedia
        self.transport.position_decoder(self.key,1000);self.transport.position_decoder(self.key,2000)
        player.reset_mock()
        self.transport.decoder_loaded(self.key,player,QMediaPlayer.LoadedMedia)
        self.transport.decoder_loaded(self.key,player,QMediaPlayer.LoadedMedia)
        player.setPosition.assert_called_once_with(2000);player.play.assert_called_once()
        self.assertFalse(self.transport._loading_video_seeks)

    def test_playing_seek_admits_current_clock_frame_after_long_preroll(self):
        self.transport.playing=True;self.transport.position=5.
        self.transport.position_decoder(self.key,1000)
        good=self.frame(self.key,5_000_000);self.transport.poll_frames()
        good.toImage.assert_called_once();self.assertNotIn(self.key,self.transport._pending_video_seeks)
        self.transport.position_decoder(self.key,1000)
        wrong=self.frame(self.key,10_000_000);wrong.toImage.reset_mock();self.transport.poll_frames()
        wrong.toImage.assert_not_called()

    def test_cut_updates_preview_clip_map_before_clock_notification_despite_throttle(self):
        self.add_distant_cut()
        self.transport._last_scrub_sync=__import__('time').monotonic()
        observed=[]
        self.transport.changed.connect(lambda position:observed.append(set(self.window.preview.active_frames)))
        self.transport.scrub(11.);self.transport.frame_timer.stop()
        self.assertEqual(observed[-1],{'distant0','distant1','distant2'})
        self.assertEqual(set(self.window.preview.fallback_frames),observed[-1])

    def test_retired_decoder_cannot_restart_or_publish_queued_drag_result(self):
        self.scrub(1.); self.scrub(3.)
        player=self.created[self.key][0]
        self.transport.retire_decoder(self.key)
        self.transport.decoder_loaded(self.key,player,QMediaPlayer.LoadedMedia)
        player.play.assert_not_called()
        self.assertFalse(self.transport._scrub_decoder_targets); self.assertFalse(self.transport._pending_video_seeks)
        self.transport.frame(self.key,self.image)
        self.assertFalse(self.window.preview.frames)


if __name__=='__main__':unittest.main()
