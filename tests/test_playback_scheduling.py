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
