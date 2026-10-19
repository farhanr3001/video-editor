import copy,json,math,tempfile,unittest
from pathlib import Path
import numpy as np
from PySide6.QtCore import QEvent,QRectF,QThreadPool
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication
from kinetic_cut.creative_effects import NAMES,CONTROLS,default_effect,values,apply,clock,descriptor,filter_string
from kinetic_cut.model import Project,ProjectSettings,MediaItem,TimelineItem
from kinetic_cut.effects import CATALOG,compatible
from kinetic_cut.gpu_preview import shader_supported
from kinetic_cut.gpu_export import recipe
from kinetic_cut.exporter import ExportPreset

class CreativeEffectTests(unittest.TestCase):
    def fixture(self):
        return Project(settings=ProjectSettings(width=64,height=64,fps=30),media=[MediaItem('m','missing.png','image','Image',5,64,64)],timeline=[TimelineItem('a','m','video_1',0,2),TimelineItem('b','m','video_1',2,2)])
    def image(self):
        image=QImage(64,64,QImage.Format_RGBA8888);image.fill(QColor(40,100,170,123));return image
    def test_catalog_and_video_image_lock_guards(self):
        p=self.fixture();item=p.timeline[0]
        for name in NAMES:
            self.assertTrue(any(name in names for names in CATALOG.values()));self.assertTrue(compatible(name,item,p))
            item.track='audio_1';self.assertFalse(compatible(name,item,p));item.track='video_1'
            item.role='title';self.assertFalse(compatible(name,item,p));item.role='video'
        p.track_states['video_1']['locked']=True;self.assertFalse(compatible(NAMES[0],item,p))
    def test_all_effects_change_pixels_preserve_alpha_and_bypass(self):
        source=self.image()
        for name in NAMES[:6]:
            effect=default_effect(name);actual=apply(source,effect)
            self.assertNotEqual(actual.pixelColor(2,2),source.pixelColor(2,2),name)
            self.assertEqual(actual.pixelColor(2,2).alpha(),123,name)
            effect['mix']=0;self.assertEqual(apply(source,effect),source,name)
            effect['mix']=100;effect['enabled']=False;self.assertEqual(apply(source,effect),source,name)
    def test_flash_defaults_white_speed_width_softness_and_custom_colour(self):
        source=self.image();e=default_effect('Color Flash')
        self.assertEqual(e['color'],'#ffffff');self.assertGreater(apply(source,e,0).pixelColor(2,2).red(),200)
        self.assertEqual(apply(source,e,.25),source)
        self.assertEqual(apply(source,e,.5),apply(source,e,0))
        e.update(color='#ff0000',strength=100,softness=0)
        self.assertEqual(apply(source,e,0).pixelColor(2,2),QColor(255,0,0,123))
        e['width']=100;self.assertNotEqual(apply(source,e,.2),source)
    def test_untrusted_project_values_are_finite_bounded_colours(self):
        for name in NAMES:
            e=default_effect(name)
            for key in e:
                if key not in ('name','enabled'):e[key]=float('nan')
            d=descriptor(e);self.assertTrue(all(math.isfinite(v) for key in ('p1','p2','colorA','colorB') for v in d[key]))
            self.assertNotIn('nan',filter_string(e,'T'))
        self.assertEqual(values(dict(name='Color Flash',color='untrusted:bad'))['color'],'#ffffff')
    def test_clock_move_split_trim_and_speed_preserve_phase(self):
        p=self.fixture();item=p.timeline[0];item.in_point=10;item.start=3;item.speed=2;e=default_effect('Color Flash',item)
        self.assertEqual(clock(e,item,3),0);self.assertEqual(clock(e,item,4),1)
        right=copy.deepcopy(item);right.start+=.37;right.in_point+=.74
        self.assertAlmostEqual(clock(e,right,right.start),clock(e,item,right.start))
        item.start+=10;self.assertEqual(clock(e,item,14),1)
    def test_native_recipe_keeps_order_and_stays_gpu(self):
        p=self.fixture();item=p.timeline[0];item.effects=[default_effect('Duotone'),dict(name='Gaussian Blur'),default_effect('Color Flash')]
        self.assertTrue(shader_supported(item))
        ops=recipe(p,ExportPreset('test','h264',10,192,'test'),Path('.'),False)['layers'][0]['operations']
        self.assertEqual([o['kind'] for o in ops],['creative','blur','creative'])
        self.assertEqual([ops[0]['mode'],ops[2]['mode']],[4,1])
        item.effects[0]['enabled']=False;self.assertEqual(len(recipe(p,ExportPreset('test','h264',10,192,'test'),Path('.'),False)['layers'][0]['operations']),2)
    def test_cpu_image_animation_cache_recalculates_while_source_is_unchanged(self):
        from kinetic_cut.preview_raster import RasterContext,prepare_layer_image
        p=self.fixture();item=p.timeline[0];item.effects=[default_effect('Color Flash')];context=RasterContext(p,False,1)
        source=self.image();r=QRectF(0,0,64,64)
        p.playhead=0;a=prepare_layer_image(context,item,source,r,r)
        p.playhead=.25;b=prepare_layer_image(context,item,source,r,r)
        self.assertNotEqual(a,b);self.assertEqual(b,source)
    def test_roundtrip_and_stack_order(self):
        p=self.fixture();p.timeline[0].effects=[default_effect('Color Tint'),default_effect('Invert Colors')]
        restored=Project.from_dict(json.loads(json.dumps(p.to_dict())))
        self.assertEqual(restored.to_dict(),p.to_dict())
        source=self.image();a=apply(apply(source,p.timeline[0].effects[0]),p.timeline[0].effects[1]);b=apply(apply(source,p.timeline[0].effects[1]),p.timeline[0].effects[0])
        self.assertNotEqual(a,b)
    def test_ffmpeg_pixels_match_cpu_reference(self):
        from kinetic_cut.process import run
        source=self.image();raw=bytes(source.constBits())
        for name in NAMES[:6]:
            e=default_effect(name)
            for t in (0,.17):
                result=run(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgba','-s','64x64','-i','pipe:0','-vf',filter_string(e,str(t)),'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','pipe:1'],input=raw,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
                actual=np.frombuffer(result.stdout,np.uint8).astype(float);expected=np.frombuffer(apply(source,e,t).constBits(),np.uint8).astype(float)
                self.assertLessEqual(np.abs(actual-expected).max(),1.1,name)
    def test_windowed_export_keeps_flash_phase_after_clip_offset_and_retime(self):
        from kinetic_cut.rendergraph import command
        from kinetic_cut.process import run
        import av
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);p=self.fixture();source=root/'source.png';self.image().save(str(source));p.media[0].path=str(source)
            item=p.timeline[0];p.timeline=[item];item.start=.3;item.in_point=.4;item.speed=1.5;item.effects=[default_effect('Color Flash')]
            item.effects[0].update(speed=2.7,phase=13)
            preset=ExportPreset('test','h264',10,192,'test')
            for start in (.3,.6):
                output=root/f'{start}.mp4';args=command(p,str(output),preset,False,'CPU','ffmpeg',export_audio=False,window=(start,start+.2))
                result=run(args,capture_output=True);self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
                with av.open(str(output)) as movie:actual=next(movie.decode(video=0)).to_ndarray(format='rgb24')[32,32]
                reference=apply(self.image(),item.effects[0],clock(item.effects[0],item,start)).pixelColor(32,32)
                # The source has transparency; the scene is composed over black.
                expected=np.array([reference.red(),reference.green(),reference.blue()])*123/255
                self.assertLess(np.abs(actual.astype(float)-expected).max(),6)

class CreativeInspectorTests(unittest.TestCase):
    def test_multiselection_inspector_bypass_reset_remove_undo_redo(self):
        from kinetic_cut.ui import MainWindow
        w=MainWindow();w.autosave_timer.stop();p=CreativeEffectTests().fixture();w.set_project(p)
        try:
            w.timeline.selected_ids={'a','b'};w.timeline.selected_id='a';w.inspector.select('a')
            w.apply_effect('Color Flash')
            self.assertTrue(all(len(i.effects)==1 for i in w.project.timeline))
            panel=w.inspector.creative_panel;self.assertFalse(panel.isHidden())
            w.inspector.edit_effect('speed',3.5);self.assertTrue(all(i.effects[0]['speed']==3.5 for i in w.project.timeline))
            panel.reset_effect();self.assertTrue(all(i.effects[0]['speed']==2 for i in w.project.timeline))
            w.inspector.edit_effect('enabled',False);self.assertTrue(all(not i.effects[0]['enabled'] for i in w.project.timeline))
            w.inspector.remove_effect();self.assertTrue(all(not i.effects for i in w.project.timeline))
            w.undo();self.assertTrue(all(i.effects for i in w.project.timeline));w.redo();self.assertTrue(all(not i.effects for i in w.project.timeline))
        finally:
            w.close();QThreadPool.globalInstance().waitForDone(10000);w.deleteLater();QApplication.sendPostedEvents(None,QEvent.DeferredDelete);QApplication.processEvents()
