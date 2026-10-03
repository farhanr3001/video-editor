import copy,io,json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QMessageBox
from kinetic_cut.model import Project,MediaItem,TimelineItem,Crop
from kinetic_cut import vision_effects as vision


def fixture(root,points=None):
    source=Path(root)/'source.png'; image=QImage(64,64,QImage.Format_RGBA8888); image.fill(QColor('orange')); image.save(str(source))
    media=MediaItem('m',str(source),'image','Source',2,64,64)
    item=TimelineItem('i','m','video_1',0,2)
    directory=Path(root)/'analysis'; (directory/'masks').mkdir(parents=True)
    (directory/'faces.json').write_text(json.dumps([points,None]))
    mask=QImage(64,64,QImage.Format_RGBA8888); mask.fill(QColor('black'))
    for x in range(24,40):
        for y in range(24,64):mask.setPixelColor(x,y,QColor('white'))
    for n in range(2):mask.save(str(directory/'masks'/f'{n:08d}.png'))
    analysis=dict(root=str(directory),source=vision.fingerprint(media),crop=vars(item.crop.clamped()),source_start=0,source_end=2,fps=1,frames=2,face_frames=int(points is not None),person_frames=2)
    return media,item,analysis,image


class VisionTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self):vision._face_data.cache_clear(); vision.mask_image.cache_clear(); self.temp.cleanup()
    def test_crop_source_and_coverage_guards(self):
        media,item,a,image=fixture(self.root)
        self.assertTrue(vision.valid(a,media,item))
        item.start=19; item.in_point=.5; item.duration=1; self.assertTrue(vision.valid(a,media,item))
        item.duration=3; self.assertFalse(vision.valid(a,media,item))
        item.duration=1; item.crop=Crop(.1,0,.9,1); self.assertFalse(vision.valid(a,media,item))
        item.crop=Crop(); media.path=str(self.root/'missing.png'); self.assertFalse(vision.valid(a,media,item))
    def test_corrupt_landmarks_are_safe_and_report_reanalyse(self):
        media,item,a,image=fixture(self.root); item.effects=[dict(name='Party Hat',analysis=a)]
        path=Path(a['root'])/'faces.json'
        for data in ('[', '{}', '[[[0.1, 0.2]],null]'):
            path.write_text(data)
            self.assertFalse(vision.valid(a,media,item)); self.assertIn('Re-analyse',vision.status(item,media,0)); self.assertEqual(vision.apply(image,item,media,0),image)
    def test_face_loss_hides_filter_and_bypass_restores_source(self):
        media,item,a,image=fixture(self.root); item.effects=[dict(name='Party Hat',analysis=a)]
        self.assertIn('Face not detected',vision.status(item,media,.5)); self.assertEqual(vision.apply(image,item,media,.5),image)
        item.effects[0]['enabled']=False; self.assertEqual(vision.status(item,media,0),'')
    def test_segmentation_alpha_and_hat_stack_order(self):
        points=[[.4,.5],[.6,.5],[.5,.4],[.5,.8],[.3,.6],[.7,.6],[.5,.6],[.5,.7],[.4,.5],[.6,.5]]
        media,item,a,image=fixture(self.root,points); item.effects=[dict(name='Remove Person Background',analysis=a)]
        result=vision.apply(image,item,media,0); self.assertEqual(result.pixelColor(0,0).alpha(),0); self.assertEqual(result.pixelColor(32,50).alpha(),255)
        item.effects.append(dict(name='Party Hat',analysis=a)); result=vision.apply(image,item,media,0)
        self.assertGreater(result.pixelColor(32,16).alpha(),0) # hat survives outside the person mask
        item.effects.reverse(); self.assertEqual(vision.apply(image,item,media,0),result)
    def test_missing_mask_blocks_export_with_actionable_message(self):
        media,item,a,image=fixture(self.root); item.effects=[dict(name='Remove Person Background',analysis=a)]
        (Path(a['root'])/'masks'/'00000001.png').unlink()
        p=Project(media=[media],timeline=[item])
        with self.assertRaisesRegex(ValueError,'Re-analyse'):vision.prepare_export(p,'ffmpeg',None,threading.Event())
    def test_no_vision_export_never_loads_optional_runtime(self):
        self.assertEqual(vision.prepare_export(Project(),'ffmpeg',None,None),{})
        self.assertNotIn('mediapipe',sys.modules)
    def test_analysis_roundtrip_and_invalid_render_graph_guard(self):
        from kinetic_cut.exporter import build_command,PRESETS
        media,item,a,image=fixture(self.root); item.effects=[dict(name='Face Mask',analysis=a)]
        p=Project(media=[media],timeline=[item]); path=self.root/'test.kcut'; p.save(path); restored=Project.load(path)
        self.assertEqual(restored.timeline[0].effects,item.effects)
        with self.assertRaisesRegex(ValueError,'analysis|prepared|prepare'):build_command(p,'out.mp4',next(iter(PRESETS.values())),False,'CPU')
    def test_bounded_decode_cancel_and_partial_frames(self):
        event=threading.Event(); self.assertEqual(list(vision.decoded_frames(io.BytesIO(b'12345678'),4,event)),[b'1234',b'5678'])
        with self.assertRaisesRegex(RuntimeError,'Incomplete'):list(vision.decoded_frames(io.BytesIO(b'123'),4,event))
        event.set()
        from kinetic_cut.vocal_component import Cancelled
        with self.assertRaises(Cancelled):list(vision.decoded_frames(io.BytesIO(b'1234'),4,event))

    def test_new_distortions_change_face_not_edges_and_hide_on_tracking_loss(self):
        from kinetic_cut.effects import CATALOG
        self.assertFalse({'Party Hat','Face Mask'} & set(CATALOG['Face Filters']))
        points=[[.35,.4],[.65,.4],[.5,.2],[.5,.85],[.2,.5],[.8,.5],[.5,.5],[.5,.7],[.35,.4],[.65,.4]]
        media,item,a,image=fixture(self.root,points)
        for y in range(64):
            for x in range(64):image.setPixelColor(x,y,QColor(x*4,y*4,100,255))
        for name in ('Big Nose','Big Lips','Face Twist'):
            item.effects=[dict(name=name,analysis=a)]; result=vision.apply(image,item,media,0)
            self.assertNotEqual(result,image,name); self.assertEqual(result.pixelColor(0,0),image.pixelColor(0,0)); self.assertEqual(vision.apply(image,item,media,1.),image)
            item.effects[0]['enabled']=False; self.assertEqual(vision.apply(image,item,media,0),image)

    def test_textured_accessories_require_pose_and_render_in_preview(self):
        points=[[.35,.4],[.65,.4],[.5,.2],[.5,.85],[.2,.5],[.8,.5],[.5,.5],[.5,.7],[.35,.4],[.65,.4]]
        media,item,a,image=fixture(self.root,points)
        image=image.scaled(320,320)
        item.effects=[dict(name='Puppy Ears & Nose',analysis=a)]
        self.assertFalse(vision.valid_effect(item.effects[0],media,item))
        self.assertIn('Re-analyse',vision.status(item,media,0))
        matrix=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        (Path(a['root'])/'geometry.json').write_text(json.dumps([
            dict(points=[p+[0.] for p in points],matrix=matrix),None]))
        self.assertTrue(vision.valid_effect(item.effects[0],media,item))
        self.assertNotEqual(vision.apply(image,item,media,0),image)
        self.assertEqual(vision.apply(image,item,media,1),image)
        item.effects[0]['name']='Cat Ears & Whiskers'
        self.assertNotEqual(vision.apply(image,item,media,0),image)

    def test_3d_ar_views_follow_pose_and_preserve_legacy_effects(self):
        from kinetic_cut.ar_face_filters import AR_FILTERS,head_angles,view_angles,_view
        from kinetic_cut.icons import resource_path
        from kinetic_cut.effects import CATALOG
        self.assertTrue(set(AR_FILTERS).issubset(CATALOG['Face Filters']))
        self.assertTrue({'Puppy Ears & Nose','Cat Ears & Whiskers'}.issubset(CATALOG['Face Filters']))
        identity=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
        self.assertEqual(view_angles(identity),(0,0))
        matrix=[[.5,0.,.866,0.],[0.,1.,0.,0.],[-.866,0.,.5,0.],[0.,0.,0.,1.]]
        self.assertAlmostEqual(head_angles(matrix)[0],60,delta=.1)
        self.assertEqual(view_angles(matrix),(60,0))
        for folder,*_ in AR_FILTERS.values():
            for yaw in range(-60,61,6):
                for pitch in range(-20,21,10):
                    self.assertTrue(resource_path('assets','face_filters',folder,f'y{yaw:+03d}_p{pitch:+03d}.png').is_file())
            self.assertFalse(_view(folder,0,0).isNull())
        points=[[.35,.4],[.65,.4],[.5,.2],[.5,.85],[.2,.5],[.8,.5],[.5,.5],[.5,.7],[.35,.4],[.65,.4]]
        media,item,a,image=fixture(self.root,points)
        image=image.scaled(320,320)
        item.effects=[dict(name='AR Plague Mask',analysis=a)]
        self.assertFalse(vision.valid_effect(item.effects[0],media,item))
        self.assertIn('Re-analyse',vision.status(item,media,0))
        (Path(a['root'])/'geometry.json').write_text(json.dumps([
            dict(points=[p+[0.] for p in points],matrix=identity),None]))
        self.assertTrue(vision.valid_effect(item.effects[0],media,item))
        self.assertNotEqual(vision.apply(image,item,media,0),image)
        self.assertEqual(vision.apply(image,item,media,1),image)
        item.effects[0]['name']='AR Pixel Glasses'
        self.assertNotEqual(vision.apply(image,item,media,0),image)


class RenderSafetyTests(unittest.TestCase):
    def test_nvidia_final_frame_buffering_is_disabled(self):
        from kinetic_cut.exporter import _encoder
        for codec in ('h264','h265'):
            args,_=_encoder(codec,'NVIDIA'); self.assertEqual(args[args.index('-delay')+1],'0'); self.assertEqual(args[args.index('-rc-lookahead')+1],'0')
    def test_repeated_progress_cannot_defeat_stall_watchdog(self):
        from kinetic_cut.export_process import render
        from kinetic_cut.process import popen
        children=[]
        def start(*args,**kwargs):child=popen(*args,**kwargs); children.append(child); return child
        with patch('kinetic_cut.export_process.popen',side_effect=start):
            with self.assertRaisesRegex(RuntimeError,'stopped advancing'):
                render([sys.executable,'-u','-c','import time\nwhile True:\n print("frame=710\\nout_time_ms=11783333",flush=True); time.sleep(.05)'],12,stall_timeout=.4)
        self.assertIsNotNone(children[0].poll())
    def test_cancel_works_without_any_encoder_output(self):
        from kinetic_cut.export_process import render
        event=threading.Event(); timer=threading.Timer(.2,event.set); timer.start(); started=time.monotonic()
        try:
            with self.assertRaisesRegex(RuntimeError,'cancelled'):render([sys.executable,'-c','import time; time.sleep(30)'],12,cancel=event)
            self.assertLess(time.monotonic()-started,5)
        finally:timer.cancel()
    def test_windows_job_owns_encoder_lifetime(self):
        if os.name!='nt':self.skipTest('Windows ownership')
        from kinetic_cut.export_process import ChildJob,stop
        from kinetic_cut.process import popen
        child=popen([sys.executable,'-c','import time; time.sleep(30)']); job=ChildJob(child)
        try:
            self.assertIsNotNone(job.handle); job.close(); child.wait(timeout=5); self.assertIsNotNone(child.poll())
        finally:stop(child,job)
    def test_cancel_at_publication_keeps_previous_file(self):
        from kinetic_cut.exporter import export,PRESETS
        event=threading.Event()
        with tempfile.TemporaryDirectory() as root:
            output=Path(root)/'existing.mp4'; output.write_bytes(b'previous output')
            def command(project,path,*args,**kwargs):Path(path).write_bytes(b'new partial'); return ['fake']
            def render(*args):event.set(); return 0,[]
            with patch('kinetic_cut.exporter.build_command',side_effect=command),patch('kinetic_cut.export_process.render',side_effect=render):
                with self.assertRaisesRegex(RuntimeError,'cancelled'):export(Project(),str(output),next(iter(PRESETS.values())),False,'CPU',cancel=event)
            self.assertEqual(output.read_bytes(),b'previous output'); self.assertFalse(list(Path(root).glob('.kinetic-export-*')))


class VisionUITests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.w=MainWindow(); self.w.autosave_timer.stop()
        media,item,self.a,image=fixture(self.root)
        self.w.set_project(Project(media=[media],timeline=[item])); self.w.select_item(item.id); self.item=item
    def tearDown(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QEvent,QThreadPool
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); self.w.deleteLater(); QApplication.sendPostedEvents(None,QEvent.DeferredDelete); QApplication.processEvents(); self.temp.cleanup()
    def test_first_use_decline_does_not_install_or_change_timeline(self):
        from kinetic_cut.vision_ui import begin
        with patch('kinetic_cut.vision_component.ready',return_value=False),patch('kinetic_cut.component_ui.InstallComponentDialog.exec',return_value=0) as prompt,patch('kinetic_cut.vision_component.install') as install:
            begin(self.w,'Party Hat'); prompt.assert_called_once(); install.assert_not_called(); self.assertFalse(self.item.effects)
    def test_no_face_detected_message_leaves_timeline_unchanged(self):
        from kinetic_cut.vision_ui import begin
        self.item.effects=[dict(name='Remove Person Background',analysis=self.a)]
        with patch.object(QMessageBox,'information') as message,patch('kinetic_cut.vision_component.install') as install:
            begin(self.w,'Party Hat'); self.assertIn('Face not detected',message.call_args.args); install.assert_not_called(); self.assertEqual(len(self.item.effects),1)
    def test_cached_background_applies_without_download_and_is_undoable(self):
        from kinetic_cut.vision_ui import begin
        self.item.effects=[dict(name='Face Mask',analysis=self.a)]; self.w.model_changed(); self.w.select_item(self.item.id)
        with patch('kinetic_cut.vision_component.install') as install:
            begin(self.w,'Remove Person Background'); install.assert_not_called()
        self.assertEqual(len(self.item.effects),2); self.assertFalse(self.w.inspector.vision_reanalyse.isHidden())
        self.w.undo(); self.assertEqual(len(self.w.project.item_by_id('i').effects),1)
