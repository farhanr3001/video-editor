import copy,json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QEvent,QThreadPool
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from kinetic_cut.finishing_effects import CONTROLS,CATEGORIES,ANIMATED,GRAPHS,shader_cases
from kinetic_cut.creative_effects import default_effect,values,descriptor,apply,filter_string,NAMES
from kinetic_cut.model import Project,ProjectSettings,MediaItem,TimelineItem,Transform,Crop
from kinetic_cut.effects import compatible,CATALOG
from kinetic_cut.exporter import ExportPreset

class FinishingTests(unittest.TestCase):
    @staticmethod
    def image():
        y,x=np.mgrid[:48,:64];a=np.zeros((48,64,4),np.uint8);a[:,:,0]=30+x*3;a[:,:,1]=25+y*4;a[:,:,2]=35+((x//8+y//6)%2)*150;a[:,:,3]=60+x*3
        return QImage(a.data,64,48,256,QImage.Format_RGBA8888).copy()
    def test_categories_names_mode_ids_and_whitelist_are_stable(self):
        self.assertEqual(NAMES[:6],('Color Flash','Exposure Pulse','Color Tint','Duotone','Posterize','Invert Colors'))
        self.assertEqual(len(CONTROLS),28);self.assertEqual(set(sum(CATEGORIES.values(),[])),set(CONTROLS))
        p=Project(media=[MediaItem('m','source.png','image','Image',4,64,48)],timeline=[TimelineItem('a','m','video_1',0,4)])
        from kinetic_cut.gpu_preview import shader_supported
        for name in CONTROLS:
            i=p.timeline[0];i.effects=[default_effect(name,i)];self.assertTrue(compatible(name,i,p));self.assertTrue(shader_supported(i))
            self.assertTrue(any(name in v for v in CATALOG.values()));self.assertGreaterEqual(descriptor(i.effects[0],i)['mode'],7)
    def test_every_default_is_a_real_pixel_effect_and_preserves_alpha(self):
        original=self.image();a=np.frombuffer(original.constBits(),np.uint8).reshape(48,64,4).copy()
        for name in CONTROLS:
            e=default_effect(name);result=apply(original,e,.17);b=np.frombuffer(result.constBits(),np.uint8).reshape(48,64,4)
            self.assertTrue(np.any(a[:,:,:3]!=b[:,:,:3]),name);self.assertTrue(np.array_equal(a[:,:,3],b[:,:,3]),name)
            self.assertEqual(original,self.image(),name)
            e['mix']=0;self.assertEqual(apply(original,e),original,name)
            e['mix']=100;e['enabled']=False;self.assertEqual(apply(original,e),original,name)
    def test_all_parameter_extremes_are_finite_and_renderable(self):
        original=self.image()
        for name,controls in CONTROLS.items():
            for mode in ('min','max','invalid'):
                e=default_effect(name)
                for key,_,low,high,default,_ in controls:e[key]=low if mode=='min' else high if mode=='max' else float('nan')
                d=descriptor(e);self.assertTrue(all(math.isfinite(v) for v in d['p1']+d['p2']),name)
                self.assertFalse(apply(original,e,-.19).isNull(),(name,mode))
    def test_deterministic_animation_pause_seek_and_sampling(self):
        original=self.image()
        for name in ANIMATED:
            e=default_effect(name)
            if name=='Scanlines':e['speed']=1
            self.assertEqual(apply(original,e,.17),apply(original,e,.17),name)
            self.assertNotEqual(apply(original,e,.17),apply(original,e,.43),name)
        e=default_effect('Mosaic Pixelate');e.update(columns=8,rows=6)
        result=apply(original,e);self.assertEqual(result.pixelColor(1,1).red(),result.pixelColor(6,5).red())
    def test_ffmpeg_matches_shared_expression_pixels(self):
        from kinetic_cut.process import run
        original=self.image();raw=bytes(original.constBits());errors=[]
        for name in CONTROLS:
            e=default_effect(name);reference=apply(original,e,.17)
            with tempfile.TemporaryDirectory() as directory:
                script=Path(directory)/'filter.txt';script.write_text('[0:v]'+filter_string(e,'.17')+'[out]',encoding='utf-8')
                r=run(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','rgba','-s','64x48','-i','pipe:0','-filter_complex_script',str(script),'-map','[out]','-frames:v','1','-f','rawvideo','-pix_fmt','rgba','pipe:1'],input=raw,capture_output=True)
            self.assertEqual(r.returncode,0,(name,r.stderr.decode(errors='replace')))
            actual=np.frombuffer(r.stdout,np.uint8).reshape(48,64,4).astype(float);expected=np.frombuffer(reference.constBits(),np.uint8).reshape(48,64,4).astype(float)
            color=float(np.abs(actual[:,:,:3]-expected[:,:,:3]).mean());alpha=float(np.abs(actual[:,:,3]-expected[:,:,3]).max())
            if color>=1.1 or alpha>1:errors.append((name,color,alpha))
        self.assertFalse(errors,errors)
    def test_native_and_qt_shader_sources_match_expression_graph(self):
        root=Path(__file__).resolve().parents[1]
        for index,name in enumerate(CONTROLS,7):self.assertIn(shader_cases('glsl',{name}),(root/f'assets/shaders/finishing_{index}.frag').read_text())
        self.assertIn(shader_cases('hlsl').replace('extra.x','KINETIC_CREATIVE_MODE'),(root/'native/gpu_export.cpp').read_text())
    def test_mixed_stack_export_runs_before_geometry_and_preserves_source(self):
        from kinetic_cut.rendergraph import command
        from kinetic_cut.gpu_export import recipe
        p=Project(settings=ProjectSettings(width=64,height=48,fps=30),media=[MediaItem('m','source.png','image','Image',4,64,48)],timeline=[TimelineItem('a','m','video_1',0,1,transform=Transform(.5,.5,.8,rotation=20,flip_horizontal=True))])
        item=p.timeline[0];item.effects=[default_effect('Vignette'),dict(name='Gaussian Blur',horizontal=3,vertical=3),default_effect('Mosaic Pixelate')]
        before=copy.deepcopy(p.to_dict());preset=ExportPreset('test','h264',10,192,'test');args=command(p,'output.mp4',preset,False,'CPU',export_audio=False)
        graph=args[args.index('-filter_complex')+1];self.assertLess(graph.index('geq='),graph.index('hflip'));self.assertLess(graph.index('geq='),graph.index('rotate='));self.assertEqual(p.to_dict(),before)
        # New effects carry unflipped coordinates through a native flipped source.
        item.transform.rotation=0;ops=recipe(p,preset,Path('.'),False)['layers'][0]['operations'];self.assertTrue(ops[0]['flip_x']);self.assertEqual([o['kind'] for o in ops],['creative','blur','creative'])

class SpeedAndInspectorTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.temp=tempfile.TemporaryDirectory();self.source=Path(self.temp.name)/'video.mp4'
        from kinetic_cut.process import run
        result=run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=64x48:r=30:d=4','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(self.source)],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.w=MainWindow();self.w.autosave_timer.stop()
    def tearDown(self):
        import time
        self.w.close();deadline=time.monotonic()+10
        while getattr(self.w,'_closing',False) and self.w.isVisible() and time.monotonic()<deadline:
            QApplication.processEvents();time.sleep(.02)
        QThreadPool.globalInstance().waitForDone(10000);QApplication.processEvents()
        self.w.deleteLater();QApplication.sendPostedEvents(None,QEvent.DeferredDelete);QApplication.processEvents();self.temp.cleanup()
    def project(self,neighbor=False):
        p=Project(media=[MediaItem('m',str(self.source),'video','Video',4,64,48,30,True)],timeline=[TimelineItem('v','m','video_1',0,1,link_id='link'),TimelineItem('a','m','audio_1',0,1,link_id='link')])
        if neighbor:p.timeline.append(TimelineItem('next','m','video_1',1,2))
        self.w.set_project(p);self.w.timeline.select_ids({'v'},'v');return p
    def test_speed_presets_reuse_real_linked_retime_undo_and_saving(self):
        p=self.project();self.w.apply_effect('Slow Motion · 50%')
        self.assertTrue(all(i.speed==.5 and i.duration==2 for i in self.w.project.timeline));self.assertTrue({'v','a'}<=self.w.timeline.retime_ids)
        self.assertTrue(all(not i.effects for i in self.w.project.timeline),'Speed is timeline retiming, not a pixel effect')
        self.assertEqual(Project.from_dict(json.loads(json.dumps(self.w.project.to_dict()))).timeline[0].speed,.5)
        self.w.undo();self.assertEqual(self.w.project.item_by_id('v').speed,1);self.w.redo();self.assertEqual(self.w.project.item_by_id('v').duration,2)
    def test_slow_motion_never_overwrites_neighbors_or_locked_linked_audio(self):
        p=self.project(True);before=copy.deepcopy(p.to_dict())
        with patch('PySide6.QtWidgets.QMessageBox.information') as message:self.w.apply_effect('Slow Motion · 50%');self.assertTrue(message.called)
        self.assertEqual(p.to_dict(),before)
        p=self.project();p.track_states['audio_1']['locked']=True;before=copy.deepcopy(p.to_dict())
        with patch('PySide6.QtWidgets.QMessageBox.information'):self.w.apply_effect('Slow Motion · 50%')
        self.assertEqual(p.to_dict(),before)
    def test_fast_preset_preserves_an_existing_overlapping_neighbor(self):
        p=self.project(True);p.item_by_id('next').start=.4;before=copy.deepcopy(p.to_dict())
        with patch('PySide6.QtWidgets.QMessageBox.information') as message:self.w.apply_effect('Fast Motion · 200%');self.assertTrue(message.called)
        self.assertEqual(p.to_dict(),before)
    def test_inspector_builds_only_current_controls_and_switches_every_effect(self):
        p=self.project();i=p.timeline[0];panel=self.w.inspector.creative_panel
        for name,controls in CONTROLS.items():
            i.effects=[default_effect(name)];self.w.inspector.select('v');self.w.inspector.effect_picker.setCurrentIndex(0);self.w.inspector.refresh_effect()
            self.assertEqual(panel.current_name,name);self.assertLessEqual(len(panel.rows),8)
            self.assertFalse(panel.isHidden());self.assertEqual(set(n for n,k in panel.rows),{name})
        i.effects=[];self.w.inspector.select('v');self.assertTrue(panel.isHidden())
