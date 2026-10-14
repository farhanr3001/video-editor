import copy
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project, MediaItem, TimelineItem, Caption, Transform, Crop
from kinetic_cut.video_worker import VideoEngine, shared_file
from kinetic_cut.preview_compositor import SceneContext, render
from kinetic_cut.widgets import PreviewCanvas


class WorkerDecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import av
        cls.temp=tempfile.TemporaryDirectory(); cls.path=Path(cls.temp.name)/'frames.mp4'
        with av.open(str(cls.path),'w') as output:
            stream=output.add_stream('libx264',rate=30); stream.width=160; stream.height=90
            stream.pix_fmt='yuv420p'; stream.options={'g':'15','bf':'0','crf':'10'}
            for n in range(90):
                data=np.zeros((90,160,3),dtype=np.uint8)
                data[:,:,0]=n*2; data[:,n%140:n%140+20,1]=240
                frame=av.VideoFrame.from_ndarray(data,format='rgb24')
                for packet in stream.encode(frame):output.mux(packet)
            for packet in stream.encode():output.mux(packet)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def start(self,path=None):
        engine=VideoEngine(str(path or self.path)); thread=threading.Thread(target=engine.run)
        thread.start()
        def finish():
            engine.stop(); thread.join(5); self.assertFalse(thread.is_alive()); self.assertFalse(engine.error)
        self.addCleanup(finish); return engine
    def sought(self,engine,at):
        engine.command(position=at,playing=False); generation=engine.generation
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            f=engine.frame()
            if f.isValid() and f.generation==generation:return f
            if engine.error:self.fail(engine.error)
            time.sleep(.002)
        self.fail(f'No frame for {at}; generation {generation}')
    def test_seek_pixels_frame_intervals_and_stale_generations(self):
        import av
        engine=self.start()
        for at in (0,.123,2.72,.8,1.51,.8,2.99):
            result=self.sought(engine,at)
            self.assertLessEqual(result.startTime(),at*1e6+1)
            self.assertGreater(result.endTime(),at*1e6-1)
            with av.open(str(self.path)) as source:
                expected=next(f for f in source.decode(video=0) if f.time+1/30>at+1e-6).to_ndarray(format='rgba')
            actual=np.frombuffer(result.image.constBits(),np.uint8).reshape(90,160,4)
            np.testing.assert_array_equal(actual,expected)
        engine.command(position=1.); old=engine.frame()
        engine.command(position=2.)
        self.assertNotEqual(old.generation,engine.generation)
    def test_play_pause_rate_and_bounded_source_cache(self):
        engine=self.start(); self.sought(engine,.3)
        engine.command(playing=True,rate=2.)
        time.sleep(.3); self.assertGreater(engine.position(),.8)
        engine.command(playing=False); before=engine.position(); time.sleep(.06)
        self.assertAlmostEqual(before,engine.position(),places=6)
        self.assertLessEqual(engine.cache_bytes,64*1024**2); self.assertLessEqual(len(engine.cache),32)
        engine.command(playing=True,rate=-1); time.sleep(.08)
        self.assertLess(engine.position(),before)
    def test_nonzero_stream_origin_and_variable_frame_intervals(self):
        import av
        from fractions import Fraction
        path=Path(self.temp.name)/'variable-offset.mp4'
        times=(0,33,100,133,220,253,320)
        with av.open(str(path),'w') as output:
            stream=output.add_stream('libx264',rate=30); stream.width=160; stream.height=90
            stream.pix_fmt='yuv420p'; stream.time_base=Fraction(1,1000)
            stream.codec_context.time_base=Fraction(1,1000); stream.options={'g':'15','bf':'0','crf':'10'}
            for n,pts in enumerate(times):
                frame=av.VideoFrame.from_ndarray(np.full((90,160,3),n*30,dtype=np.uint8),format='rgb24')
                frame.pts=5000+pts; frame.time_base=Fraction(1,1000)
                for packet in stream.encode(frame):output.mux(packet)
            for packet in stream.encode():output.mux(packet)
        with av.open(str(path)) as source:
            offset=float(source.streams.video[0].start_time*source.streams.video[0].time_base)
            reference=list(source.decode(video=0))
        self.assertGreater(offset,1.)
        engine=self.start(path)
        for at in (.01,.05,.12,.18,.24,.29,.05):
            result=self.sought(engine,at)
            expected=next(f for n,f in enumerate(reference[:-1]) if f.time-offset<=at<reference[n+1].time-offset)
            self.assertAlmostEqual(result.start/1e6,expected.time-offset,places=5)
            actual=np.frombuffer(result.image.constBits(),np.uint8).reshape(90,160,4)
            np.testing.assert_array_equal(actual,expected.to_ndarray(format='rgba'))
    @unittest.skipUnless(os.name=='nt','Windows share-delete handle')
    def test_open_source_can_be_renamed_and_original_survives(self):
        path=Path(self.temp.name)/'shared.mp4'; path.write_bytes(self.path.read_bytes())
        target=path.with_name('renamed.mp4')
        with shared_file(path) as source:
            path.rename(target); self.assertGreater(len(source.read(128)),0)
        target.unlink(); self.assertTrue(self.path.is_file())
    def test_decode_error_closes_without_hanging(self):
        engine=VideoEngine(str(Path(self.temp.name)/'missing.mp4'))
        thread=threading.Thread(target=engine.run); thread.start(); thread.join(2)
        self.assertFalse(thread.is_alive()); self.assertTrue(engine.error)
    def test_full_seek_proxy_keeps_dimensions_frame_rate_and_short_gop(self):
        from kinetic_cut.media import generate_proxy
        media=MediaItem('full',str(self.path),'video','fixture',3,160,90,30)
        captured={}; cache=Path(self.temp.name)/'cache'; (cache/'proxies').mkdir(parents=True,exist_ok=True)
        def encode(args,duration,callback,cancel):
            captured['args']=args; Path(args[-1]).write_bytes(self.path.read_bytes()); return 0,[]
        with patch('kinetic_cut.media.CACHE_DIR',cache),patch('kinetic_cut.exporter.automatic_encoder',return_value='CPU'),patch('kinetic_cut.export_process.render',side_effect=encode):
            result=generate_proxy(media,seek_cache=True)
        args=captured['args']; self.assertNotIn('-vf',args)
        self.assertEqual(args[args.index('-g')+1],'15'); self.assertEqual(args[args.index('-bf')+1],'0')
        self.assertEqual(args[args.index('-fps_mode')+1],'passthrough')
        self.assertTrue(Path(result).name.startswith('full-seek-')); self.assertEqual(self.path.read_bytes(),Path(result).read_bytes())
    @unittest.skipUnless(os.name=='nt','Windows path aliases')
    def test_seek_cache_eviction_preserves_protected_case_and_slash_aliases(self):
        from kinetic_cut.media import generate_proxy
        from types import SimpleNamespace
        cache=Path(self.temp.name)/'protected-cache'; (cache/'proxies').mkdir(parents=True,exist_ok=True)
        victim=cache/'proxies'/'full-seek-0123456789abcdef.mp4'; victim.write_bytes(b'protected-source')
        media=MediaItem('full',str(self.path),'video','fixture',3,160,90,30)
        original_stat=Path.stat
        def observed(path,*args,**kwargs):
            value=original_stat(path,*args,**kwargs)
            return SimpleNamespace(st_size=1600*1024**2,st_mtime=value.st_mtime,st_mode=value.st_mode) if path==victim else value
        alias=str(victim).upper().replace('\\','/')
        with patch('kinetic_cut.media.CACHE_DIR',cache),patch.object(Path,'stat',observed):
            with self.assertRaisesRegex(ValueError,'storage budget'):
                generate_proxy(media,seek_cache=True,protected=[alias])
        self.assertEqual(victim.read_bytes(),b'protected-source')


class WorkerCompositionTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([])
        self.canvas=PreviewCanvas(); self.canvas.resize(320,480)
        self.p=Project(); self.p.settings.width=360; self.p.settings.height=640
        self.p.video_tracks=['video_1','video_2','video_3']
        self.p.media=[MediaItem('m','','video','fixture',4,160,90,30)]
        self.image=QImage(160,90,QImage.Format_RGBA8888); self.image.fill(QColor('#366995'))
        paint=QPainter(self.image); paint.fillRect(30,10,70,50,Qt.yellow); paint.end()
        self.p.timeline=[TimelineItem('bg','m','video_1',0,4,role='background'),
                         TimelineItem('v','m','video_2',0,4,crop=Crop(.1,.05,.8,.9),transform=Transform(x=.4,y=.4,scale=.65))]
        self.p.captions=[Caption('c',0,4,'Exact $375K',customize=True)]
        self.p.captions[0].style.glow_enabled=True
        self.canvas.set_project(self.p); self.canvas.frames={'k':self.image}; self.canvas.active_frames={'bg':'k','v':'k'}
    def tearDown(self):
        self.canvas.composition_cache.close(); self.canvas.close(); self.canvas.deleteLater(); self.app.processEvents()
    def test_worker_scene_equals_shared_renderer_with_effects_text_and_motion(self):
        from kinetic_cut.motion import default_scene
        self.p.timeline.append(TimelineItem('g','','video_3',0,4,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':default_scene((360,640))}))
        self.p.timeline[1].effects=[dict(name='Gaussian Blur',horizontal=5,vertical=5)]
        for at in (.12,.5,2.3):
            self.p.playhead=at
            for scale in (1.,2.):
                rect=QRectF(10,9,270,480); size=(round(320*scale),round(500*scale))
                first=SceneContext(copy.deepcopy(self.p),{'k':self.image},dict(self.canvas.active_frames),{},True,scale)
                second=SceneContext(copy.deepcopy(self.p),{'k':self.image},dict(self.canvas.active_frames),{},True,scale)
                expected,bounds,_=render(first,rect,size,scale)
                with ThreadPoolExecutor(max_workers=1) as pool:actual,other,_=pool.submit(render,second,rect,size,scale).result(10)
                self.assertEqual(actual,expected); self.assertEqual(bounds,other)
                self.assertEqual(actual.pixelColor(0,0).alpha(),0)
    def test_worker_scene_matches_actual_canvas_content_paint(self):
        from types import SimpleNamespace
        self.canvas.transport=SimpleNamespace(playing=True,scrubbing=False)
        self.p.playhead=.6; rect=QRectF(11,9,270,480); size=(320,500)
        context=SceneContext(copy.deepcopy(self.p),{'k':self.image},dict(self.canvas.active_frames),{},True,1.)
        expected=QImage(*size,QImage.Format_ARGB32_Premultiplied); expected.fill(Qt.transparent)
        painter=QPainter(expected); painter.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform); painter.fillRect(rect,Qt.black)
        self.canvas._paint_scene(painter,rect); painter.end()
        with ThreadPoolExecutor(max_workers=1) as pool:actual,_,_=pool.submit(render,context,rect,size,1.).result(5)
        self.assertEqual(actual,expected)
    def test_current_caption_overlay_matches_complete_scene_pixels(self):
        from kinetic_cut.visuals import draw_caption
        rect=QRectF(11,9,270,480); size=(320,500)
        for animation in ('none','karaoke','emoji pop'):
            self.p.captions[0].style.animation=animation
            for at in (.1,1.2):
                self.p.playhead=at
                complete=SceneContext(copy.deepcopy(self.p),{'k':self.image},dict(self.canvas.active_frames),{},True,1.)
                expected,_,_=render(complete,rect,size,1.)
                layers=SceneContext(copy.deepcopy(self.p),{'k':self.image},dict(self.canvas.active_frames),{},True,1.,False)
                actual,_,_=render(layers,rect,size,1.)
                painter=QPainter(actual); painter.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
                draw_caption(painter,self.p,self.p.captions[0],rect); painter.end()
                self.assertEqual(actual,expected,(animation,at))
    def test_process_scene_has_identical_pixels_and_reaps_its_helper(self):
        from kinetic_cut.preview_process import RendererProcess
        from kinetic_cut.motion import default_scene
        self.p.timeline.append(TimelineItem('g','','video_3',0,4,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':default_scene((360,640))}))
        self.p.playhead=.45; rect=QRectF(11,9,270,480); size=(320,500)
        context=SceneContext(copy.deepcopy(self.p),{'k':self.image},dict(self.canvas.active_frames),{},True,1.)
        expected,bounds,notice=render(context,rect,size,1.)
        service=RendererProcess()
        names=[]
        try:
            actual,other,status=service.render(context,rect,size,1.)
            self.assertEqual(actual,expected); self.assertEqual(other,bounds); self.assertEqual(status,notice)
            for at,x in ((.7,.4),(1.2,.75)):
                context.project.playhead=at
                context.project.timeline[1].transform.x=x
                expected,bounds,notice=render(context,rect,size,1.)
                actual,other,status=service.render(context,rect,size,1.)
                self.assertEqual(actual,expected); self.assertEqual(other,bounds); self.assertEqual(status,notice)
            larger=QImage(320,180,QImage.Format_RGBA8888); larger.fill(Qt.cyan)
            context.frames={'k':larger}; context.project.timeline[1].transform.x=.6
            expected,bounds,notice=render(context,rect,size,1.)
            actual,other,status=service.render(context,rect,size,1.)
            self.assertEqual(actual,expected); self.assertEqual(other,bounds); self.assertEqual(status,notice)
            if service.shared:names=[slot.name for slot in service.shared.slots.values()]
        finally:
            service.close()
            if service.process:service.process.join(3)
        self.assertFalse(service.process.is_alive())
        if names:
            from multiprocessing.shared_memory import SharedMemory
            deadline=time.monotonic()+2
            while service.shared.slots and time.monotonic()<deadline:time.sleep(.01)
            self.assertFalse(service.shared.slots)
            for name in names:
                with self.assertRaises(FileNotFoundError):SharedMemory(name=name)
    def test_cache_changes_reject_old_scene_and_preserve_unrelated_timings(self):
        cache=self.canvas.composition_cache; rect=self.canvas.composition_rect()
        self.assertIsNone(cache.request(rect)); cache.future.result(5)
        first=cache.request(rect); self.assertIsNotNone(first)
        self.p.timeline[1].transform.x=.7
        self.assertIsNone(cache.request(rect)); cache.future.result(5)
        changed=cache.request(rect); self.assertIsNotNone(changed); self.assertNotEqual(first[0],changed[0])
        self.p.playhead=4.1
        self.assertIsNone(cache.request(rect))
        self.assertEqual(self.p.timeline[1].start,0); self.assertEqual(self.p.timeline[1].duration,4)
        self.assertLessEqual(cache.images.byte_count,128*1024**2)
    def test_slow_composition_cannot_hold_an_old_frame_indefinitely(self):
        from concurrent.futures import Future
        cache=self.canvas.composition_cache; rect=self.canvas.composition_rect()
        cache.request(rect); cache.future.result(5); self.assertIsNotNone(cache.request(rect))
        self.p.playhead=.5
        cache.future=Future(); cache.pending=(('blocked',),cache.last[0],cache.future)
        cache.last_completed=0.
        self.assertIsNone(cache.request(rect),'Slow helper must return to the current-frame renderer')
    def test_redecoded_same_source_time_reuses_complete_composition(self):
        self.image.setText('_kinetic_source_frame','fixture-source-version:frame-0')
        cache=self.canvas.composition_cache; rect=self.canvas.composition_rect()
        cache.request(rect); cache.future.result(5); first=cache.request(rect)
        replacement=self.image.copy()
        self.assertNotEqual(replacement.cacheKey(),self.image.cacheKey())
        self.canvas.frames['k']=replacement
        reused=cache.request(rect)
        self.assertEqual(reused[0],first[0]); self.assertEqual(cache.hits,1)
    def test_missing_active_lane_is_never_cached_as_black(self):
        self.canvas.frames.clear()
        cache=self.canvas.composition_cache
        self.assertIsNone(cache.request(self.canvas.composition_rect()))
        self.assertIsNone(cache.future); self.assertEqual(cache.images.byte_count,0)
    def test_crop_pixels_survive_source_changes_and_crop_writes_preserve_source(self):
        import gc
        from kinetic_cut.preview_raster import RasterContext
        original=self.image.copy(); crop=Crop(.1,.1,.7,.7)
        expected=RasterContext._source_crop(original,crop)
        view=RasterContext._source_crop(original,crop)
        self.assertEqual(view.copy(),expected)
        original.fill(Qt.red); self.assertEqual(view.copy(),expected)
        del original; gc.collect(); self.assertEqual(view.copy(),expected)
        retained=QImage(self.image)
        view.fill(Qt.green)
        self.assertEqual(RasterContext._source_crop(retained,crop),expected)
        edge=RasterContext._source_crop(self.image,Crop(.1,0,.7,1))
        self.assertEqual((edge.width(),edge.height()),(112,90))
        self.assertEqual(edge.pixelColor(0,0),self.image.pixelColor(16,0))
        self.assertEqual(edge.pixelColor(111,89),self.image.pixelColor(127,89))
        self.assertEqual(RasterContext._source_crop(self.image,Crop()),self.image)


if __name__=='__main__':unittest.main()
