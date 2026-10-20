"""GPU boundary contracts; real Windows rendering is covered by native checks."""
import math
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import QUrl,QEventLoop,QTimer,Qt
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlEngine,QQmlComponent
from PySide6.QtWidgets import QApplication,QWidget,QAbstractScrollArea
from kinetic_cut.model import TimelineItem,Project
from kinetic_cut.gpu_preview import shader_supported
from kinetic_cut.quick_surface import Surface
from kinetic_cut.native_engine import LIB as INDEX_LIB,LatestRequest


class GpuSurfaceTests(unittest.TestCase):
    def test_prepared_text_tracks_current_canvas_geometry_before_raster_finishes(self):
        from kinetic_cut.gpu_preview import GpuPreview
        from PySide6.QtCore import QRectF,QSizeF
        from unittest.mock import Mock
        layer=Mock();surface=SimpleNamespace(layers={'captions':layer},bounds={('caption','c'):QRectF(20,60,100,20)},_bounds_size=QSizeF(200,400))
        GpuPreview._fit_prepared_geometry(surface,[('captions',)],QRectF(0,0,100,200))
        layer.setWidth.assert_called_with(100);layer.setHeight.assert_called_with(200)
        self.assertEqual(surface.bounds[('caption','c')],QRectF(10,30,50,10))
        GpuPreview._fit_prepared_geometry(surface,[('captions',)],QRectF(0,0,400,800))
        self.assertEqual(surface.bounds[('caption','c')],QRectF(40,120,200,40))

    def test_image_texture_reloads_changed_file_without_recreating_its_layer(self):
        import tempfile
        from unittest.mock import Mock
        from kinetic_cut.gpu_preview import GpuPreview
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'still.png';path.write_bytes(b'first')
            values={};image=Mock();image.property.side_effect=lambda name:values.get(name)
            image.setProperty.side_effect=lambda name,value:values.__setitem__(name,value)
            surface=SimpleNamespace(_used_textures=set(),layer_images={},create=Mock(return_value=image))
            first=GpuPreview._file_texture(surface,str(path));url=values['source'];calls=image.setProperty.call_count
            self.assertIs(GpuPreview._file_texture(surface,str(path)),first);self.assertEqual(image.setProperty.call_count,calls)
            path.write_bytes(b'replaced image')
            self.assertIs(GpuPreview._file_texture(surface,str(path)),first);self.assertNotEqual(values['source'],url)
            self.assertEqual(Path(QUrl(values['source']).toLocalFile()),path);surface.create.assert_called_once()

    def test_retired_native_texture_is_not_reported_ready_after_backend_handoff(self):
        from kinetic_cut.gpu_preview import GpuPreview
        from unittest.mock import Mock
        key=('media',0,1,'video');record=dict(item=Mock(),ready=True,handle='RhiTextureHandle')
        surface=SimpleNamespace(sources={key:record})
        GpuPreview.retire(surface,key)
        self.assertFalse(record['ready']);self.assertTrue(record['retired'])

    def test_playback_meters_update_without_repainting_stationary_track_headers(self):
        from kinetic_cut.timeline import TimelineWidget
        from kinetic_cut.gpu_timeline import GpuTimeline
        from PySide6.QtCore import QRect
        from unittest.mock import Mock
        timeline=TimelineWidget();timeline.resize(900,420);timeline.set_project(Project())
        surface=SimpleNamespace(timeline=timeline,images=Mock(),root=Mock(),create=Mock(return_value=Mock()),updates=0)
        area=QRect(timeline.LABEL_WIDTH+1,timeline.RULER_HEIGHT+1,700,300)
        timeline.paint_track_header=Mock(wraps=timeline.paint_track_header)
        try:
            GpuTimeline._headers(surface,timeline._palette(),area);GpuTimeline._meters(surface,area)
            calls=timeline.paint_track_header.call_count
            timeline._audio_levels={timeline.project.audio_tracks[0]:(.7,.5,False)}
            GpuTimeline._headers(surface,timeline._palette(),area);GpuTimeline._meters(surface,area)
            self.assertEqual(timeline.paint_track_header.call_count,calls)
            self.assertEqual([c.args[0] for c in surface.images.put.call_args_list],['headers','meters','meters'])
            image=surface.images.put.call_args.args[1]
            self.assertTrue(any(image.pixelColor(120,y).green()>150 for y in range(image.height())))
            self.assertEqual(image.pixelColor(10,80).alpha(),0,'Meters must preserve labels underneath')
        finally:timeline.close();timeline.deleteLater()

    def test_navigation_does_not_reupload_empty_editing_overlay(self):
        from kinetic_cut.timeline import TimelineWidget
        from kinetic_cut.gpu_timeline_controls import refresh
        from PySide6.QtCore import QRect
        from unittest.mock import Mock
        timeline=TimelineWidget();timeline.resize(900,420);timeline.set_project(Project())
        surface=SimpleNamespace(timeline=timeline,images=Mock(),create=Mock(return_value=Mock()),view=timeline.viewport())
        area=QRect(0,0,900,420)
        try:
            refresh(surface,area);before=surface.images.put.call_count
            timeline.horizontalScrollBar().setRange(0,1000);timeline.horizontalScrollBar().setValue(50);timeline.pixels_per_second=23.
            refresh(surface,area);self.assertEqual(surface.images.put.call_count,before)
            timeline.selected_ids={'selected'};refresh(surface,area)
            self.assertGreater(surface.images.put.call_count,before)
        finally:timeline.close();timeline.deleteLater()

    def test_cached_ruler_preserves_original_pixels_during_navigation_and_dpi_changes(self):
        from kinetic_cut.timeline import TimelineWidget
        from kinetic_cut.gpu_timeline_chrome import RulerCache,image_for
        from PySide6.QtGui import QRegion
        from unittest.mock import patch
        timeline=TimelineWidget();timeline.resize(900,420);timeline.set_project(Project())
        timeline.horizontalScrollBar().setRange(0,100000)
        cache=RulerCache(timeline);palette=timeline._palette();width=880;height=timeline.RULER_HEIGHT+1
        try:
            for ratio in (1.,1.25,1.5,2.):
                with patch.object(timeline,'devicePixelRatioF',return_value=ratio):
                    for pps in (20.,23.,.6,240.):
                        timeline.pixels_per_second=pps
                        for offset in (0,17,21,400,411,550,3000,3013,31):
                            timeline.horizontalScrollBar().setValue(offset)
                            expected=image_for(timeline,width,height,lambda p:timeline._paint_ruler(p,palette,width,QRegion(0,0,width,height)))
                            actual=cache.image(palette,width,height)
                            self.assertEqual(actual,expected,(ratio,pps,offset))
            self.assertLessEqual(cache.bytes,cache.limit)
            with patch.object(timeline,'devicePixelRatioF',return_value=1.):
                timeline.pixels_per_second=20.;timeline.horizontalScrollBar().setValue(400);cache.image(palette,width,height);before=cache.renders
                for offset in range(401,430):timeline.horizontalScrollBar().setValue(offset);cache.image(palette,width,height)
                self.assertEqual(cache.renders,before,'Panning inside the strip must not rerasterize labels/ticks')
                bounded=RulerCache(timeline);bounded.limit=64
                actual=bounded.image(palette,width,height)
                expected=image_for(timeline,width,height,lambda p:timeline._paint_ruler(p,palette,width,QRegion(0,0,width,height)))
                self.assertEqual(actual,expected);self.assertEqual(bounded.bytes,0)
        finally:timeline.close();timeline.deleteLater()

    def test_preview_container_is_native_before_scroll_area_promotes_ancestors(self):
        root=QWidget();host=QWidget(root);preview=Surface(host,'GpuPreview.qml')
        scroll=QAbstractScrollArea(root);timeline=None
        try:
            self.assertTrue(preview.container.testAttribute(Qt.WA_NativeWindow))
            parent=preview.container.windowHandle()
            self.assertIsNotNone(parent)
            self.assertIsNotNone(host.windowHandle())
            timeline=Surface(scroll,'GpuTimeline.qml',scroll.viewport())
            self.assertIs(preview.container.windowHandle(),parent)
            self.assertIs(preview.container.nativeParentWidget(),host)
        finally:
            if timeline:timeline.close()
            preview.close();root.close();root.deleteLater()

    def test_gpu_cursor_texture_keeps_original_pointed_playhead_pixels(self):
        from kinetic_cut.timeline import TimelineWidget
        from kinetic_cut.gpu_timeline_chrome import cursor_image,image_for
        timeline=TimelineWidget();timeline.resize(900,420);timeline.set_project(Project(playhead=3.123))
        try:
            x=timeline.x_for_time(timeline.project.playhead)
            expected=image_for(timeline,timeline.viewport().width(),timeline.viewport().height(),timeline._paint_playhead)
            actual=cursor_image(timeline)
            ratio=timeline.devicePixelRatioF()
            expected=expected.copy(round((round(x)-9)*ratio),0,actual.width(),actual.height())
            self.assertEqual(actual,expected)
            center=round(9*ratio)
            self.assertGreater(actual.pixelColor(center,round(2*ratio)).red(),200)
            self.assertGreater(actual.pixelColor(center,round(70*ratio)).red(),200)
        finally:timeline.close();timeline.deleteLater()

    def test_requested_workspace_capture_includes_native_surface_pixels(self):
        from kinetic_cut.ui_capture import capture
        from unittest.mock import Mock
        from PySide6.QtGui import QColor
        widget=QWidget();widget.resize(80,60);widget.setStyleSheet('background: #101010')
        container=QWidget(widget);container.setGeometry(20,10,30,35)
        image=QImage(30,35,QImage.Format_RGBA8888);image.fill(QColor('#ed2436'))
        view=SimpleNamespace(grabWindow=Mock(return_value=image))
        surface=SimpleNamespace(closed=False,container=container,view=view)
        widget.show();QApplication.processEvents()
        try:
            actual=capture(widget,[surface])
            self.assertEqual(actual.pixelColor(25,15),QColor('#ed2436'))
            self.assertEqual(actual.pixelColor(5,5),QColor('#101010'))
            view.grabWindow.assert_called_once_with()
        finally:widget.close();widget.deleteLater()

    def test_playing_without_controls_does_not_prepare_an_invisible_ui_raster(self):
        from kinetic_cut.gpu_preview import GpuPreview
        from PySide6.QtCore import QRectF
        from unittest.mock import Mock
        canvas=SimpleNamespace(window=lambda:SimpleNamespace(transport=SimpleNamespace(playing=True)),transform_controls_visible=False)
        surface=SimpleNamespace(canvas=canvas,bounds={('title','a'):QRectF(1,2,30,40)},notice='',overlay=Mock(),images=Mock())
        GpuPreview._controls(surface,QRectF(10,20,100,200))
        surface.overlay.setVisible.assert_called_once_with(False)
        surface.images.put.assert_not_called()
        self.assertEqual(canvas.text_rects[('title','a')],QRectF(11,22,30,40))

    def test_all_qml_components_compile_against_bundled_qt(self):
        engine=QQmlEngine()
        try:
            for path in (Path(__file__).resolve().parents[1]/'assets/qml').glob('*.qml'):
                component=QQmlComponent(engine,QUrl.fromLocalFile(str(path)))
                self.assertEqual(component.status(),QQmlComponent.Ready,[e.toString() for e in component.errors()])
        finally:engine.deleteLater()

    def test_property_publication_preserves_bindings_when_values_are_unchanged(self):
        class Item:
            def __init__(self):self.published=[]
            def setProperty(self,key,value):self.published.append((key,value))
        item=Item()
        for step in range(100):Surface.properties(item,dict(startTime=10.,duration=3.,label='Same source'))
        self.assertEqual(len(item.published),3)
        Surface.properties(item,dict(startTime=11.,duration=3.,label='Same source'))
        self.assertEqual(item.published[-1],('startTime',11.))
        self.assertEqual(len(item.published),4)

    @unittest.skipUnless(INDEX_LIB,'Native Windows engine')
    def test_native_single_pending_request_replaces_obsolete_work(self):
        mailbox=LatestRequest()
        for at in range(500):mailbox.submit(1,at/60)
        self.assertEqual(mailbox.dropped,499)
        epoch,serial,at=mailbox.take();self.assertEqual(epoch,1);self.assertAlmostEqual(at,499/60)
        self.assertIsNone(mailbox.take())
        mailbox.submit(2,4);self.assertEqual(mailbox.take()[0],2)

    def test_unsupported_pixel_algorithms_use_exact_worker_instead_of_being_omitted(self):
        item=TimelineItem('clip','source','video_1',0,2)
        self.assertTrue(shader_supported(item))
        item.effects=[dict(name='Gaussian Blur',horizontal=55,vertical=6,blend=72)]
        self.assertTrue(shader_supported(item))
        for effect in ('AI Enhance','Green Screen','Face Blur','Tracking Blur','Film Color'):
            item.effects=[dict(name=effect)];self.assertFalse(shader_supported(item),effect)
        item.effects=[dict(name='Gaussian Blur'),dict(name='Gaussian Blur')]
        self.assertFalse(shader_supported(item))
        item.effects=[];item.composite_mode='Multiply';self.assertFalse(shader_supported(item))

    def test_peak_textures_preserve_transients_and_signed_envelopes_at_every_level(self):
        import numpy as np
        from kinetic_cut.gpu_timeline import peak_images
        from kinetic_cut.waveforms import Waveform
        peaks=np.zeros((20000,2),dtype=np.int16);peaks[7041]=[-32768,32767];peaks[9999]=[-8192,16384]
        waveform=Waveform(peaks);levels=peak_images(waveform)
        self.assertEqual(len(levels),len(waveform.levels))
        for index,(image,count,resolution) in enumerate(levels):
            pixels=np.frombuffer(image.constBits(),np.uint8).reshape(-1,4)[:count]
            reference=waveform.levels[index].astype(float)
            self.assertTrue(np.all(pixels[:,0]/255>=np.maximum(0,-reference[:,0])/32768-1e-6))
            self.assertTrue(np.all(pixels[:,1]/255>=np.maximum(0,reference[:,1])/32768-1e-6))
            self.assertEqual(int(pixels[:,0].max()),255)
            self.assertEqual(int(pixels[:,1].max()),255)
            self.assertEqual(resolution,.001*4**index)

    def test_effect_island_remains_transparent_between_layers(self):
        from kinetic_cut.preview_compositor import SceneContext,render
        from PySide6.QtCore import QRectF
        context=SceneContext(Project(),{},{},{},True,1.);context.transparent=True
        image,bounds,notice=render(context,QRectF(0,0,40,80),(40,80),1.)
        self.assertEqual(image.pixelColor(20,40).alpha(),0)
        context.transparent=False
        image,_,_=render(context,QRectF(0,0,40,80),(40,80),1.)
        self.assertEqual(image.pixelColor(20,40).alpha(),255)
    def test_effect_changes_retire_a_decoder_that_cannot_supply_required_pixels(self):
        from unittest.mock import Mock
        from kinetic_cut.transport import TimelineTransport
        sink=SimpleNamespace(_kinetic_gpu_texture=True)
        gpu=SimpleNamespace(cpu_media=lambda identifier:True)
        transport=SimpleNamespace(window=SimpleNamespace(preview=SimpleNamespace(gpu=gpu)),decoders={'key':(None,None,sink)},retire_decoder=Mock())
        TimelineTransport.ensure_video_backend(transport,'key',SimpleNamespace(id='source'))
        transport.retire_decoder.assert_called_once_with('key')
        transport.retire_decoder.reset_mock();sink._kinetic_gpu_texture=False
        TimelineTransport.ensure_video_backend(transport,'key',SimpleNamespace(id='source'))
        transport.retire_decoder.assert_not_called()
        gpu.cpu_media=lambda identifier:False
        TimelineTransport.ensure_video_backend(transport,'key',SimpleNamespace(id='source'))
        transport.retire_decoder.assert_called_once_with('key')

    def test_native_player_failure_and_close_remain_asynchronous_and_owned(self):
        from kinetic_cut.qt_native import LIB,Engine,active,reap
        from PySide6.QtMultimedia import QVideoSink
        if LIB is None:self.skipTest('Native Qt engine unavailable')
        sink=QVideoSink();before=active();engine=Engine(sink,Path('missing-native-test-source-unique.mp4').resolve())
        engine.command(0,500);engine.command(1,1);engine.command(0,900)
        engine.close();deadline=time.monotonic()+5
        while not engine.finished and time.monotonic()<deadline:
            loop=QEventLoop();QTimer.singleShot(10,loop.quit);loop.exec()
        self.assertTrue(engine.finished);reap();self.assertEqual(active(),before)
        self.assertIsNone(engine.handle)
