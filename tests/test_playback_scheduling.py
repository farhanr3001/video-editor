import copy
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from kinetic_cut.model import Project, TimelineItem, MediaItem, Crop
from kinetic_cut.widgets import PreviewCanvas
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.transport import TimelineTransport
from kinetic_cut.preview_raster import RasterContext, prepare_layer_image, prepare_frame


class PlaybackSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([])
        self.owner=QWidget(); self.canvas=PreviewCanvas(); QVBoxLayout(self.owner).addWidget(self.canvas)
        self.owner.preview=self.canvas; self.owner.transport=SimpleNamespace(playing=True,scrubbing=False)
        self.p=Project(); self.p.media=[MediaItem('m','','video','fixture',20,640,360,60)]
        self.item=TimelineItem('v','m',self.p.video_tracks[0],0,20)
        self.p.timeline=[self.item]; self.canvas.set_project(self.p)
        self.image=QImage(640,360,QImage.Format_RGBA8888); self.image.fill(QColor('#275a98'))
        paint=QPainter(self.image); paint.fillRect(12,14,150,210,QColor('#eeae42')); paint.end()
        self.rect=QRectF(0,0,180,320); self.target=QRectF(0,0,570,320)
    def tearDown(self):
        self.owner.close(); self.owner.deleteLater(); self.app.processEvents()
    def test_worker_pixels_exactly_match_sync_for_same_quality(self):
        for role in ('','background'):
            for border in ('Reflect','Replicate'):
                self.item.role=role; self.item.crop=Crop(.08,.1,.7,.8)
                self.item.effects=[dict(name='Gaussian Blur',horizontal=12,vertical=8,blend=65,border=border)]
                self.item.saturation=.8; self.item.brightness=.1; self.item.crop_softness=3
                before=copy.deepcopy(self.item)
                for interactive in (False,True):
                    sync=RasterContext(self.p,interactive,1.)
                    expected=prepare_layer_image(sync,self.item,self.image,self.target,self.rect)
                    context=RasterContext(copy.deepcopy(self.p),interactive,1.)
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        raw,cache=executor.submit(prepare_frame,self.image,context,
                                                 [(copy.deepcopy(self.item),self.target,self.rect)]).result(5)
                    self.assertEqual(raw.cacheKey(),self.image.cacheKey())
                    self.assertEqual(cache[self.item.id][0],sync.effect_cache[self.item.id][0])
                    self.assertEqual(cache[self.item.id][1],expected)
                self.assertEqual(self.item,before)
    def test_prepared_frame_hits_cache_and_changes_invalidate(self):
        self.item.effects=[dict(name='Gaussian Blur',horizontal=12,vertical=12)]
        self.canvas.active_frames[self.item.id]='decoder'
        work=self.canvas.frame_work('decoder',self.image)
        self.assertIsNotNone(work)
        context,requests=work
        _,cache=prepare_frame(self.image,context,requests); self.canvas.effect_cache.update(cache)
        item,target,rect=requests[0]
        with patch('kinetic_cut.visuals.blur_image',side_effect=AssertionError('cache missed')):
            actual=self.canvas._prepare_layer_image(self.item,self.image,target,rect)
        self.assertEqual(actual,cache[self.item.id][1])
        self.item.effects[0]['horizontal']=24
        with patch('kinetic_cut.visuals.blur_image',wraps=__import__('kinetic_cut.visuals',fromlist=['blur_image']).blur_image) as blur:
            self.canvas._prepare_layer_image(self.item,self.image,target,rect)
            self.assertTrue(blur.called)
        self.assertEqual(item.effects[0]['horizontal'],12) # detached snapshot
    def test_time_dependent_filters_keep_existing_path(self):
        self.canvas.active_frames[self.item.id]='decoder'; self.item.effects=[dict(name='Gaussian Blur')]
        self.item.keyframes={'scale':[dict(time=0,value=1)]}
        self.assertIsNone(self.canvas.frame_work('decoder',self.image))
        self.item.keyframes={}; self.item.effects=[dict(name='Remove Person Background')]
        self.assertIsNone(self.canvas.frame_work('decoder',self.image))
        self.canvas.caption_focus=True
        self.assertIsNone(self.canvas.frame_work('decoder',self.image))
    def test_static_filter_snapshots_match_paused_scrub_and_playback_quality(self):
        self.canvas.active_frames[self.item.id]='decoder'
        self.item.effects=[dict(name='Gaussian Blur',horizontal=12.,vertical=12.)]
        for playing,scrubbing,interactive in ((False,False,False),(False,True,True),(True,False,True)):
            with self.subTest(playing=playing,scrubbing=scrubbing):
                self.owner.transport.playing=playing; self.owner.transport.scrubbing=scrubbing
                context,requests=self.canvas.frame_work('decoder',self.image)
                self.assertEqual(context.interactive,interactive)
                raw,cache=prepare_frame(self.image,context,requests)
                self.assertEqual(raw.cacheKey(),self.image.cacheKey())
                if not interactive:
                    self.assertEqual(cache[self.item.id][1].size(),self.image.size())
                self.canvas.effect_cache.update(cache)
                item,target,rect=requests[0]
                with patch('kinetic_cut.visuals.blur_image',side_effect=AssertionError('worker cache missed')):
                    prepared=self.canvas._prepare_layer_image(self.item,self.image,target,rect)
                self.assertEqual(prepared,cache[self.item.id][1])
    def test_worker_quality_snapshot_does_not_follow_later_transport_mode(self):
        self.canvas.active_frames[self.item.id]='decoder'
        self.item.effects=[dict(name='Gaussian Blur',horizontal=12.,vertical=12.)]
        self.owner.transport.playing=False; self.owner.transport.scrubbing=False
        context,requests=self.canvas.frame_work('decoder',self.image)
        self.owner.transport.scrubbing=True
        _,cache=prepare_frame(self.image,context,requests)
        self.assertFalse(context.interactive)
        self.assertEqual(cache[self.item.id][1].size(),self.image.size())
        self.canvas.effect_cache.update(cache)
        item,target,rect=requests[0]
        from kinetic_cut import visuals
        with patch('kinetic_cut.visuals.blur_image',wraps=visuals.blur_image) as blur:
            self.canvas._prepare_layer_image(self.item,self.image,target,rect)
        self.assertTrue(blur.called)  # A paused result cannot masquerade as scrub quality.
    def transport(self):
        transport=TimelineTransport(self.owner); self.owner.project=self.p
        self.addCleanup(transport.shutdown)
        return transport
    def test_stale_and_out_of_order_results_cannot_publish(self):
        t=self.transport(); key=('m',0,1,'video'); player=Mock(); sink=Mock()
        t.decoders[key]=(player,Mock(),sink)
        def job(epoch,sequence):
            future=Future(); future.set_result((self.image,{})); return (key,epoch,sequence,future)
        t._frame_epochs[key]=3; t._frame_jobs=[job(2,10),job(3,12),job(3,11)]
        with patch.object(t,'frame') as frame:
            t.publish_frames(); self.assertEqual(frame.call_count,1)
        self.assertEqual(t._published_sequences[key],12)
        t._frame_jobs=[job(3,13)]; t.position_decoder(key,2000)
        with patch.object(t,'frame') as frame:t.publish_frames(); frame.assert_not_called()
        t.decoders.clear()
    def test_pending_interactive_result_is_rejected_after_pause(self):
        t=self.transport(); self.owner.transport=t
        key=('m',0,1,'video'); player=Mock(); sink=Mock(); sink._frame_stamp=(0,16667)
        t.decoders[key]=(player,Mock(),sink); self.addCleanup(t.decoders.clear)
        t._frame_epochs[key]=3; t._pending_video_seeks[key]=0; t.playing=True
        future=Future(); future._kinetic_interactive=True
        t._frame_jobs=[(key,3,12,future)]
        with patch.object(t,'tick'):t.pause()
        future.set_result((self.image,{self.item.id:('interactive-cache',self.image)}))
        with patch.object(t,'frame') as frame:t.publish_frames(); frame.assert_not_called()
        self.assertNotIn(self.item.id,self.canvas.effect_cache)
        self.assertNotIn(key,t._published_sequences)
        self.assertEqual(t._pending_video_seeks[key],0)
        self.assertEqual(t._frame_epochs[key],3)
        self.assertIsNone(sink._frame_stamp)
        self.assertFalse(t._frame_jobs)
    def test_pending_paused_result_is_rejected_after_play_and_cannot_erase_newer_stamp(self):
        t=self.transport(); self.owner.transport=t
        key=('m',0,1,'video'); player=Mock(); sink=Mock(); sink._frame_stamp=(0,16667)
        t.decoders[key]=(player,Mock(),sink); self.addCleanup(t.decoders.clear)
        t._frame_epochs[key]=3
        future=Future(); future._kinetic_interactive=False
        t._frame_jobs=[(key,3,12,future)]
        with patch.object(t,'sync'):t.play()
        future.set_result((self.image,{self.item.id:('paused-cache',self.image)}))
        with patch.object(t,'frame') as frame:t.publish_frames(); frame.assert_not_called()
        self.assertNotIn(self.item.id,self.canvas.effect_cache)
        self.assertIsNone(sink._frame_stamp)
        sink._frame_stamp=(16667,33334); t._published_sequences[key]=13
        t._frame_jobs=[(key,3,12,future)]
        t.publish_frames()
        self.assertEqual(sink._frame_stamp,(16667,33334))
        self.assertEqual(t._published_sequences[key],13)
    def test_pending_scrub_result_is_rejected_when_drag_mode_ends(self):
        t=self.transport(); self.owner.transport=t
        key=('m',0,1,'video'); sink=Mock(); sink._frame_stamp=(0,16667)
        t.decoders[key]=(Mock(),Mock(),sink); self.addCleanup(t.decoders.clear)
        t._frame_epochs[key]=3; t.scrubbing=True
        future=Future(); future._kinetic_interactive=True
        t._frame_jobs=[(key,3,12,future)]
        with patch.object(t,'sync'):t.finish_scrub()
        future.set_result((self.image,{self.item.id:('scrub-cache',self.image)}))
        with patch.object(t,'frame') as frame:t.publish_frames(); frame.assert_not_called()
        self.assertFalse(t.scrubbing)
        self.assertNotIn(self.item.id,self.canvas.effect_cache)
        self.assertIsNone(sink._frame_stamp)
    def test_rejected_mode_result_retries_same_frame_with_full_paused_cache(self):
        t=self.transport(); self.owner.transport=t
        key=('m',0,1,'video'); player=Mock(); sink=Mock(); sink._frame_stamp=None
        frame=Mock(); frame.isValid.return_value=True; frame.startTime.return_value=0; frame.endTime.return_value=16667
        frame.toImage.return_value=self.image; sink.videoFrame.return_value=frame
        t.decoders[key]=(player,Mock(),sink); self.addCleanup(t.decoders.clear)
        t._frame_epochs[key]=3; t._pending_video_seeks[key]=0; t.playing=True
        self.canvas.active_frames[self.item.id]=key
        self.canvas.fallback_frames={}
        self.item.effects=[dict(name='Gaussian Blur',horizontal=12.,vertical=12.)]
        first,second=Future(),Future(); executor=Mock(); executor.submit.side_effect=[first,second]
        t._frame_executor=executor
        t.poll_frames()
        self.assertTrue(first._kinetic_interactive)
        with patch.object(t,'tick'):t.pause()
        first.set_result(prepare_frame(*executor.submit.call_args.args[1:]))
        t.publish_frames(); self.assertIsNone(sink._frame_stamp)
        t.poll_frames()
        self.assertFalse(second._kinetic_interactive)
        arguments=executor.submit.call_args.args[1:]
        second.set_result(prepare_frame(*arguments))
        t.publish_frames()
        self.assertEqual(t._frame_epochs[key],3)
        self.assertNotIn(key,t._pending_video_seeks)
        self.assertEqual(sink._frame_stamp,(0,16667))
        self.assertFalse(t._frame_jobs)
        published=self.canvas.frames[key]
        self.assertEqual(self.canvas.effect_cache[self.item.id][1].size(),published.size())
        item,target,rect=arguments[2][0]
        with patch('kinetic_cut.visuals.blur_image',side_effect=AssertionError('paused publication missed cache')):
            prepared=self.canvas._prepare_layer_image(self.item,published,target,rect)
        self.assertEqual(prepared,self.canvas.effect_cache[self.item.id][1])
    def test_pending_queue_is_bounded_before_readback(self):
        t=self.transport(); key=('m',0,1,'video'); frame=Mock(); frame.startTime.return_value=0; frame.endTime.return_value=16667
        sink=Mock(); sink._frame_stamp=None; sink.videoFrame.return_value=frame
        t.decoders[key]=(Mock(),Mock(),sink)
        t._frame_jobs=[(key,0,n,Future()) for n in (1,2)]
        t.poll_frames(); frame.toImage.assert_not_called()
        t.decoders.clear()
    def test_overlay_movement_reuses_tracks_and_cancellation_erases_box(self):
        t=TimelineWidget(); t.resize(1000,420); t.set_project(self.p); t.show(); self.app.processEvents()
        try:
            t.drag_mode='marquee'; t.marquee_initial=set(); t.marquee_caption_initial=set()
            section=t._sections()['video']; start=QPointF(t.x_for_time(23),section.center().y())
            t.marquee_controller.begin(start)
            t.marquee_controller.move(start-QPointF(5,15)); self.app.processEvents()
            with patch.object(t,'paint_track_header',wraps=t.paint_track_header) as headers:
                for n in range(3):
                    t.marquee_controller.move(start-QPointF(7+n,16+n)); self.app.processEvents()
                self.assertEqual(headers.call_count,0)
                t.viewport().update(); self.app.processEvents(); self.assertGreater(headers.call_count,0)
            self.assertFalse(t._painted_marquee.isEmpty())
            t.cancel_drag(); self.app.processEvents(); self.assertTrue(t._painted_marquee.isEmpty())
        finally:t.close(); t.deleteLater()

    def test_audio_meter_only_damage_reuses_static_tracks(self):
        t=TimelineWidget(); t.resize(1000,420); t.set_project(self.p); t.show(); self.app.processEvents()
        try:
            t.viewport().repaint(); self.assertIsNotNone(t._timeline_backing)
            self.assertTrue(t._playhead_damage.isEmpty())
            before=t.viewport().grab().toImage()
            with patch.object(t,'paint_track_header',wraps=t.paint_track_header) as headers:
                t.set_audio_levels({'audio_1':(.8,.5,True)})
                self.app.processEvents()
                self.assertEqual(headers.call_count,0)
            after=t.viewport().grab().toImage()
            self.assertNotEqual(before,after)  # live meter still paints
            with patch.object(t,'paint_track_header',wraps=t.paint_track_header) as headers:
                t.viewport().update(); self.app.processEvents()
                self.assertGreater(headers.call_count,0)  # ordinary edit damage
        finally:t.close(); t.deleteLater()

    def test_visible_region_cache_invalidates_for_rotation_flip_and_moves(self):
        from kinetic_cut import visuals
        self.item.effects=[dict(name='Gaussian Blur',horizontal=12.,vertical=12.)]
        self.target=QRectF(0,0,640,360)
        context=RasterContext(self.p,True,1.)
        with patch('kinetic_cut.visuals.blur_image',wraps=visuals.blur_image) as blur:
            prepare_layer_image(context,self.item,self.image,self.target,self.rect)
            self.assertIsNotNone(blur.call_args.kwargs['region']);count=blur.call_count
            moved=self.target.translated(-80,0)
            prepare_layer_image(context,self.item,self.image,moved,self.rect)
            self.assertGreater(blur.call_count,count)
            self.item.transform.rotation=10
            prepare_layer_image(context,self.item,self.image,moved,self.rect)
            self.assertIsNone(blur.call_args.kwargs['region'])
            self.item.transform.rotation=0;self.item.transform.flip_horizontal=True
            prepare_layer_image(context,self.item,self.image,moved,self.rect)
            self.assertIsNone(blur.call_args.kwargs['region'])
            self.item.transform.flip_horizontal=False;self.item.effects.append(dict(self.item.effects[0]))
            prepare_layer_image(context,self.item,self.image,moved,self.rect)
            self.assertIsNone(blur.call_args.kwargs['region'])
