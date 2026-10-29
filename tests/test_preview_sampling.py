"""Stable preview sampling contracts; actual RHI pixels use the native selftest."""
import unittest
from pathlib import Path
from PySide6.QtCore import QUrl,QSizeF
from PySide6.QtQml import QQmlComponent,QQmlEngine
from PySide6.QtQuick import QQuickItem
from kinetic_cut.gpu_preview import sampling_size

class PreviewSamplingTests(unittest.TestCase):
    def test_source_replacement_without_frontend_quality_controller(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.model import Project,MediaItem,TimelineItem
        window=MainWindow();quality=window.preview_quality
        try:
            project=Project(media=[MediaItem('reused','missing-first.png','image','first',2,320,180)],timeline=[TimelineItem('clip','reused','video_1',0,2)])
            window.set_project(project);window.transport.sync(True)
            window.preview_quality=None;window.proxies['reused']='stale-proxy.mp4'
            window.transport._worker_failed_media.add('reused')
            project.media[0].path='missing-replacement.png';project.touch();window.transport.sync(True)
            self.assertNotIn('reused',window.proxies);self.assertNotIn('reused',window.transport._worker_failed_media)
        finally:window.preview_quality=quality;window.close();window.deleteLater()
    def test_intermediate_budget_preserves_source_aspect_and_native_detail(self):
        self.assertEqual(sampling_size(941,1672,324,576),QSizeF(649,1152))
        self.assertEqual(sampling_size(941,1672,941,1672),QSizeF(941,1672))
        self.assertEqual(sampling_size(320,180,1920,1080,2),QSizeF(320,180))
        for w,h in [(8192,4320),(1,1),(0,0),(941,1672),(2049,1025)]:
            for dpr in [1,1.25,1.5,2]:
                s=sampling_size(w,h,640,720,dpr)
                self.assertTrue(2<=s.width()<=2048 and 2<=s.height()<=2048)
    def test_dpi_and_manual_view_zoom_raise_budget_without_upsampling_source(self):
        small=sampling_size(3840,2160,320,568)
        dpi=sampling_size(3840,2160,320,568,1.5)
        zoom=sampling_size(3840,2160,320,568,1,1.5)
        self.assertEqual(dpi,zoom);self.assertGreater(dpi.width(),small.width())
        self.assertEqual(sampling_size(941,1672,320,568,2,4),QSizeF(941,1672))
    def test_procedural_detail_is_not_limited_to_low_resolution_source(self):
        self.assertEqual(sampling_size(722,406.125,640,720),QSizeF(722,407))
        self.assertEqual(sampling_size(320,180,640,720),QSizeF(320,180))
    def test_qml_grid_does_not_follow_fractional_animated_geometry(self):
        engine=QQmlEngine();objects=[];components=[]
        for name in ['GpuLayer.qml','GpuCreativeLayer.qml']:
            c=QQmlComponent(engine,QUrl.fromLocalFile(str((Path.cwd()/'assets/qml'/name).resolve())))
            components.append(c);obj=c.create();self.assertIsNotNone(obj,[e.toString() for e in c.errors()]);objects.append(obj)
            obj.setProperty('processingSize',QSizeF(941,1672));sizes=[]
            for n in range(61):
                obj.setWidth(324+n*.061);obj.setHeight(576+n*.109);sizes.append(obj.property('rasterSize'))
            self.assertTrue(all(s==QSizeF(941,1672) for s in sizes))
            self.assertAlmostEqual(obj.width(),327.66)
            obj.setProperty('rasterScale',.5);self.assertEqual(obj.property('rasterSize'),QSizeF(471,836))
        for obj in objects:obj.deleteLater()
    def test_zero_blur_detaches_intermediates_and_keeps_opacity_shape(self):
        engine=QQmlEngine();c=QQmlComponent(engine,QUrl.fromLocalFile(str((Path.cwd()/'assets/qml/GpuLayer.qml').resolve())))
        obj=c.create();self.assertIsNotNone(obj,[e.toString() for e in c.errors()])
        try:
            graded=obj.findChild(QQuickItem,'gradedTexture');horizontal=obj.findChild(QQuickItem,'horizontalTexture')
            self.assertIsNone(graded.property('sourceItem'));self.assertIsNone(horizontal.property('sourceItem'))
            obj.setProperty('alpha',.4);obj.setProperty('ellipse',True)
            obj.setProperty('blurX',3.5);self.assertIsNotNone(graded.property('sourceItem'));self.assertIsNotNone(horizontal.property('sourceItem'))
            self.assertTrue(graded.property('mipmap'));self.assertTrue(horizontal.property('mipmap'))
            obj.setProperty('blurMix',0.);self.assertIsNone(graded.property('sourceItem'));self.assertAlmostEqual(obj.property('alpha'),.4);self.assertTrue(obj.property('ellipse'))
            obj.setProperty('blurMix',1.);obj.setProperty('blurX',0.);self.assertIsNone(graded.property('sourceItem'))
        finally:obj.deleteLater()
