import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from kinetic_cut.model import Project, TimelineItem, MediaItem, Crop, Transform
from kinetic_cut.widgets import PreviewCanvas
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.visuals import blur_image
from kinetic_cut.theme import PALETTES


class LayeredPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([])
        self.owner=QWidget(); self.owner.transport=SimpleNamespace(playing=True,scrubbing=False)
        self.canvas=PreviewCanvas(); QVBoxLayout(self.owner).addWidget(self.canvas)
        self.p=Project(); self.p.media=[MediaItem('m','','video','fixture',20,1920,1080,60)]
        self.item=TimelineItem('v','m',self.p.video_tracks[0],0,20,transform=Transform(y=.5))
        self.p.timeline=[self.item]; self.canvas.set_project(self.p)
        self.image=QImage(1920,1080,QImage.Format_RGB32); self.image.fill(QColor('#678abc'))
        self.frame=QRectF(0,0,270,480); self.target=QRectF(0,0,854,480)
    def tearDown(self):
        self.owner.close(); self.owner.deleteLater(); self.app.processEvents()
    def prepare(self):
        return self.canvas._prepare_layer_image(self.item,self.image,self.target,self.frame)
    def test_filtered_motion_is_screen_sized_and_pause_restores_full_quality(self):
        self.item.effects=[{'name':'Gaussian Blur','horizontal':45,'vertical':45}]
        before=copy.deepcopy(self.item)
        moving=self.prepare()
        self.assertLessEqual(moving.width(),855*self.canvas.devicePixelRatioF())
        self.owner.transport.playing=False
        paused=self.prepare()
        self.assertEqual(paused.size(),self.image.size())
        self.assertEqual(self.item,before)
        self.owner.transport.playing=True; self.target=QRectF(0,0,1920,1080)
        self.assertEqual(self.prepare().size(),self.image.size())
    def test_unfiltered_crops_keep_source_resolution_and_cache_tracks_frame_and_crop(self):
        self.item.crop=Crop(.1,.2,.25,.4)
        first=self.prepare(); second=self.prepare()
        self.assertEqual(first.size(),self.canvas._source_rect(self.image,self.item.crop).size())
        self.assertEqual(first.cacheKey(),second.cacheKey())
        self.item.crop.x=.2
        self.assertNotEqual(self.prepare().cacheKey(),first.cacheKey())
        self.image.fill(Qt.red)
        self.assertEqual(self.prepare().pixelColor(5,5),QColor(Qt.red))
    def test_direct_foreground_drawing_does_not_allocate_cropped_buffers(self):
        self.item.crop=Crop(.1,.2,.25,.4)
        target=QImage(270,480,QImage.Format_RGB32); target.fill(Qt.black)
        painter=QPainter(target)
        with patch.object(self.canvas,'_prepare_layer_image',side_effect=AssertionError('unneeded pixel processing')):
            self.canvas._draw_layer_item(painter,self.item,self.image,self.target,self.frame)
        painter.end()
        self.assertEqual(target.pixelColor(100,100),QColor('#678abc'))
    def test_background_cache_and_property_invalidation(self):
        self.item.role='background'
        a=self.prepare(); self.assertEqual(a.cacheKey(),self.prepare().cacheKey())
        self.p.settings.background_brightness=.4
        self.assertNotEqual(a.cacheKey(),self.prepare().cacheKey())
        self.canvas.set_project(Project()); self.assertFalse(self.canvas.effect_cache)
    def test_fast_blur_retains_blend_border_and_anisotropic_appearance(self):
        image=QImage(320,180,QImage.Format_RGBA8888); image.fill(QColor('#275a98'))
        painter=QPainter(image); painter.fillRect(0,0,110,120,QColor('#efc47a')); painter.fillRect(150,70,70,60,Qt.white); painter.end()
        def pixels(im):return np.frombuffer(im.constBits(),np.uint8).astype(float)
        for border in ('Reflect','Replicate'):
            for blend in (.45,1.):
                exact=blur_image(image,24,12,blend,border)
                fast=blur_image(image,24,12,blend,border,preview_fast=True)
                self.assertEqual(exact.size(),fast.size())
                self.assertLess(np.abs(pixels(exact)-pixels(fast)).mean(),2.0)
        self.assertEqual(blur_image(image,45,45,0,preview_fast=True).cacheKey(),image.cacheKey())
    def test_opaque_surfaces_and_darker_grey_surround(self):
        timeline=TimelineWidget()
        self.assertTrue(self.canvas.testAttribute(Qt.WA_OpaquePaintEvent))
        self.assertTrue(timeline.viewport().testAttribute(Qt.WA_OpaquePaintEvent))
        self.assertEqual(PALETTES['ableton_gray']['viewer_bg'],'#505050')
        self.assertGreater(QColor(PALETTES['ableton_gray']['bg_viewer']).lightness(),QColor('#505050').lightness())
        timeline.close(); timeline.deleteLater()
    def test_timeline_reuses_static_pixels_only_for_clock_updates(self):
        timeline=TimelineWidget(); timeline.resize(1100,420); timeline.set_project(self.p); timeline.show()
        self.app.processEvents()
        with patch.object(timeline,'paint_track_header',wraps=timeline.paint_track_header) as headers:
            self.p.playhead=1; timeline.update_playhead(); self.app.processEvents()
            self.assertEqual(headers.call_count,0)
            self.item.start=2; timeline.viewport().update(); self.app.processEvents()
            self.assertGreater(headers.call_count,0)
        timeline.close(); timeline.deleteLater()
    def test_playback_follow_does_not_relayout_scrollbars_every_tick(self):
        timeline=TimelineWidget(); timeline.resize(1100,420); timeline.set_project(self.p)
        with patch.object(timeline,'_range',wraps=timeline._range) as ranges:
            for n in range(30):timeline.ensure_playhead_visible(n/60)
            ranges.assert_not_called()
            timeline.ensure_playhead_visible(40)
            self.assertEqual(ranges.call_count,1)
        timeline.close(); timeline.deleteLater()
