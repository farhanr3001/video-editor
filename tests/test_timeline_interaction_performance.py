"""Retained clip pixels may accelerate navigation, never hide an edit."""
import copy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QColor,QPixmap,QWheelEvent,QMouseEvent
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout
from PySide6.QtTest import QTest
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.widgets import PreviewCanvas
from kinetic_cut.model import Project,TimelineItem,MediaItem


class InteractionPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance()
        self.timeline=TimelineWidget(); self.timeline.resize(1100,460)
        self.project=Project(); self.project.media=[MediaItem('m','fixture.mp4','video','Example',100,1920,1080,60)]
        self.project.timeline=[TimelineItem('v','m','video_1',6,2),TimelineItem('a','m','audio_1',6,2)]
        self.timeline.set_project(self.project)
        pix=QPixmap(80,45); pix.fill(QColor('#e9af43'))
        self.project.media[0].thumbnail='fixture-thumb'; self.timeline.thumbnails['fixture-thumb']=pix
        self.timeline.set_waveform('m',[.25,.6,.1,.8]*20)
        self.timeline.show(); self.app.processEvents()
    def tearDown(self):
        self.timeline.close(); self.timeline.deleteLater(); self.app.processEvents()
    def repaint(self):
        self.timeline.viewport().repaint(); return self.timeline._timeline_backing.toImage()
    def exact(self):
        with patch.object(self.timeline,'drag_mode','direct-reference'),patch.object(self.timeline,'_backing_view',None):
            return self.repaint()
    def assert_pixels(self,actual,expected):
        import numpy as np
        a=np.frombuffer(actual.constBits(),np.uint8).astype(np.int16)
        b=np.frombuffer(expected.constBits(),np.uint8).astype(np.int16)
        delta=np.abs(a-b)
        if int(delta.max())>2:
            from pathlib import Path
            out=Path('build/timeline-performance-20261017/pixel-failure');out.mkdir(exist_ok=True)
            actual.save(str(out/'actual.png')); expected.save(str(out/'expected.png'))
            pixels=delta.reshape(actual.height(),actual.width(),4)
            ys,xs=np.where(pixels.max(axis=2)>1)
            # Qt clips rounded thumbnail paths against the paint device too.
            # Cropping a wider device can differ at a few corner-edge pixels;
            # no interior pixel or structural discrepancy is allowed.
            self.assertLessEqual(len(xs),8)
            self.assertTrue(np.all(xs==actual.width()-1))
            pixels[:,-1]=0
        if int(delta.max())>2:
            from pathlib import Path
            out=Path('build/timeline-performance-20261017/pixel-failure');out.mkdir(exist_ok=True)
            actual.save(str(out/'actual.png')); expected.save(str(out/'expected.png'))
        # An intermediate premultiplied-alpha blend may round by two levels.
        self.assertLessEqual(int(delta.max()),2)
        self.assertLess(float(np.count_nonzero(delta))/len(delta),.002)
    def test_empty_unassigned_widget_can_be_shown_and_repainted(self):
        timeline=TimelineWidget(); timeline.resize(800,400)
        try:
            timeline.show(); self.app.processEvents(); timeline.viewport().repaint()
            self.assertIsNone(timeline.project)
        finally:
            timeline.close(); timeline.deleteLater(); self.app.processEvents()
    def test_cached_pixels_match_direct_paint_and_follow_all_visual_edits(self):
        self.repaint(); self.assertGreater(len(self.timeline._clip_surfaces),0)
        self.assert_pixels(self.repaint(),self.exact())
        for change in (
            lambda:setattr(self.project.timeline[0],'fade_in',.8),
            lambda:setattr(self.project.media[0],'name','Renamed source'),
            lambda:self.timeline.selected_ids.add('v'),
            lambda:setattr(self.timeline,'effect_hover',('Gaussian Blur','v','',0)),
            lambda:setattr(self.project.timeline[1],'gain_db',-14),
        ):
            change(); actual=self.repaint(); self.assert_pixels(actual,self.exact())
    def test_horizontal_pan_reuses_clip_pixels_without_reusing_clock_or_metadata(self):
        self.repaint(); bar=self.timeline.horizontalScrollBar(); bar.setValue(20)
        with patch.object(self.timeline,'_paint_clip',wraps=self.timeline._paint_clip) as draws:
            actual=self.repaint(); self.assertEqual(draws.call_count,0)
        self.assert_pixels(actual,self.exact())
        self.project.playhead=7
        with patch.object(self.timeline,'_paint_clip',wraps=self.timeline._paint_clip) as draws:
            self.timeline.drag_mode='pan'; self.timeline.update_playhead(); self.app.processEvents()
            self.assertEqual(draws.call_count,0)
    def test_partial_damage_cannot_poison_first_cached_waveform(self):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QRegion
        self.timeline._clip_surfaces.clear(); self.timeline._waveform_pixmaps.clear()
        rect=self.timeline.item_rect(self.project.timeline[1]).toAlignedRect()
        damage=QRegion(QRect(rect.left()+8,rect.top(),7,rect.height()))
        self.timeline._content_damage|=damage; self.timeline.viewport().repaint(damage)
        self.assert_pixels(self.repaint(),self.exact())
    def test_follow_never_fights_an_active_middle_pan(self):
        self.timeline.horizontalScrollBar().setValue(100); before=self.timeline.horizontalScrollBar().value()
        self.timeline.drag_mode='pan'; self.timeline.ensure_playhead_visible(90)
        self.assertEqual(self.timeline.horizontalScrollBar().value(),before)
    def test_navigation_tiles_match_fresh_render_and_invalidate_after_edits(self):
        t=self.timeline
        self.project.timeline[0].effects=[{'name':'Gaussian Blur'}]
        self.project.timeline.extend([TimelineItem(str(n),'m','video_1',12+n*3,2) for n in range(20)])
        t.set_project(self.project)
        for zoom,offset in ((45,0),(60,100),(45,30),(45,70),(60,115),(45,10),(45,280),(45,285)):
            t.set_zoom(zoom); t.horizontalScrollBar().setValue(offset)
            actual=self.repaint(); self.assert_pixels(actual,self.exact())
        self.project.timeline[0].title_text='Changed'; self.project.timeline[0].role='title'
        t.set_project(self.project); t.set_zoom(60); t.horizontalScrollBar().setValue(110)
        self.assert_pixels(self.repaint(),self.exact())
        self.assertLessEqual(len(t._view_rasters),32)
    def test_preview_pan_locks_during_play_but_zoom_and_paused_pan_work(self):
        owner=QWidget(); owner.transport=SimpleNamespace(playing=False,scrubbing=False)
        canvas=PreviewCanvas(); QVBoxLayout(owner).addWidget(canvas); canvas.set_project(self.project)
        canvas.composition_cache.close(); owner.show(); self.app.processEvents()
        def gesture():
            QTest.mousePress(canvas,Qt.MiddleButton,pos=QPoint(100,80))
            QTest.mouseMove(canvas,QPoint(130,95)); QTest.mouseRelease(canvas,Qt.MiddleButton,pos=QPoint(130,95))
        try:
            gesture(); before=QPointF(canvas.view_pan); self.assertNotEqual(before,QPointF())
            owner.transport.playing=True; canvas.set_playback_active(True); gesture(); self.assertEqual(canvas.view_pan,before)
            QTest.mouseDClick(canvas,Qt.MiddleButton,pos=QPoint(100,80)); self.assertEqual(canvas.view_pan,before)
            zoom=canvas.view_zoom; pos=QPointF(100,80)
            self.app.sendEvent(canvas,QWheelEvent(pos,pos,QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False))
            self.assertGreater(canvas.view_zoom,zoom)
            owner.transport.playing=False; gesture(); self.assertNotEqual(canvas.view_pan,before)
            QTest.mousePress(canvas,Qt.MiddleButton,pos=QPoint(100,80))
            owner.transport.playing=True; canvas.set_playback_active(True); self.assertIsNone(canvas.pan_origin)
        finally:owner.close(); owner.deleteLater(); self.app.processEvents()
