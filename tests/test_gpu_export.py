import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kinetic_cut.model import Project,ProjectSettings,MediaItem,TimelineItem,Transform,Crop
from kinetic_cut.exporter import ExportPreset,build_command
from kinetic_cut.gpu_export import recipe,prepare_recipe,mux_command,Unsupported


class GpuExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.p=Project(settings=ProjectSettings(width=1080,height=1920,fps=60),
            media=[MediaItem('m','source.mp4','video','Source',10,1920,1080,60,True)],
            timeline=[TimelineItem('i','m','video_1',1,2,in_point=.71,transform=Transform(x=.5,y=.5))])
        self.preset=ExportPreset('Auto','h264',15,192,'Auto','auto')
    def tearDown(self):self.temp.cleanup()
    def test_real_gpu_recipe_preserves_source_clock_crop_and_independent_geometry(self):
        item=self.p.timeline[0];item.crop=Crop(.1,.2,.4,.5);item.transform.scale=1.5;item.transform.scale_y=.7
        item.transform.rotation=30;item.transform.anchor_x=10;item.transform.flip_horizontal=True
        before=copy.deepcopy(self.p.to_dict());job=recipe(self.p,self.preset,self.root,False);layer=job['layers'][0]
        self.assertEqual(layer['in_point'],.71);self.assertEqual(layer['start'],1);self.assertEqual(layer['end'],3)
        self.assertAlmostEqual(layer['crop'][0],.5);self.assertEqual(layer['crop'][2],-.4)
        self.assertEqual(layer['size'],[2048,672]);self.assertEqual(job['quality'],'auto');self.assertEqual((job['fps_num'],job['fps_den']),(60,1))
        self.assertEqual(self.p.to_dict(),before)
    def test_disabled_effects_and_hidden_layers_are_not_processed(self):
        item=self.p.timeline[0];item.effects=[dict(name='unknown',enabled=False)]
        self.assertEqual(len(recipe(self.p,self.preset,self.root,False)['layers']),1)
        self.p.track_states['video_1']['visible']=False
        self.assertEqual(recipe(self.p,self.preset,self.root,False)['layers'],[])
    def test_ordered_blurs_and_colour_matrices_keep_mix_and_border(self):
        self.p.timeline[0].effects=[dict(name='Sepia',amount=50),dict(name='Gaussian Blur',horizontal=20,vertical=5,blend=30,border='Smear'),dict(name='Channel Swap')]
        ops=recipe(self.p,self.preset,self.root,False)['layers'][0]['operations']
        self.assertEqual([o['kind'] for o in ops],['matrix','blur','matrix']);self.assertAlmostEqual(ops[0]['rows'][0][0],.6965)
        self.assertEqual(ops[1],dict(kind='blur',x=20.,y=5.,blend=.3,reflect=False))
    def test_alpha_video_uses_explicit_cpu_source_adapter_not_missing_layer(self):
        self.p.media[0].has_alpha=True
        self.assertTrue(recipe(self.p,self.preset,self.root,False)['layers'][0]['cpu'])
    def test_unsupported_pixel_operation_is_an_exact_layer_not_silently_omitted(self):
        item=self.p.timeline[0];item.transform.pitch=20
        with self.assertRaises(Unsupported):recipe(self.p,self.preset,self.root,False)
        with patch('kinetic_cut.export_process.render',return_value=(0,[])) as render:
            job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
        self.assertEqual(len(job['layers']),1);self.assertEqual(len(job['cpu_islands']),1)
        self.assertTrue(job['layers'][0]['cpu']);self.assertEqual(job['layers'][0]['in_point'],0)
        args=render.call_args.args[0];self.assertIn('ffv1',args);self.assertIn('perspective=',args[args.index('-filter_complex')+1])
        self.assertEqual((job['layers'][0]['start'],job['layers'][0]['end']),(1,3))
    def test_mux_reuses_exact_audio_graph_and_does_not_encode_video_again(self):
        self.p.audio_tracks=['audio_1'];audio=copy.deepcopy(self.p.timeline[0]);audio.id='a';audio.track='audio_1';audio.gain_db=-3;audio.pan=.2;audio.speed=1.25;audio.fade_in=.2;self.p.timeline.append(audio)
        self.p.settings.normalize_audio=True;job=recipe(self.p,self.preset,self.root,False)
        native=mux_command(self.p,job,str(self.root/'out.mp4'),self.preset,'ffmpeg',True)
        legacy=build_command(self.p,str(self.root/'legacy.mp4'),self.preset,False,'CPU')
        graph=native[native.index('-filter_complex')+1]
        legacy_graph=legacy[legacy.index('-filter_complex')+1]
        for operation in ('atempo=1.250000','volume=-3.0000dB','afade=t=in','loudnorm=I=-14'):
            self.assertIn(operation,graph);self.assertIn(operation,legacy_graph)
        self.assertEqual(native[native.index('-c:v')+1],'copy');self.assertEqual(native[native.index('-r')+1],'60/1')
    def test_fractional_and_high_user_frame_rates_are_preserved(self):
        for rate,expected in ((120,(120,1)),(144,(144,1)),(60000/1001,(60000,1001))):
            self.p.settings.fps=rate;job=recipe(self.p,self.preset,self.root,False)
            self.assertEqual((job['fps_num'],job['fps_den']),expected)
    def test_mask_grade_sharpen_and_chroma_have_explicit_gpu_operations(self):
        item=self.p.timeline[0];item.transform.shape='circle';item.crop_softness=10;item.brightness=.1;item.sharpen=.8
        item.effects=[dict(name='Green Screen',color='#00ff00')]
        layer=recipe(self.p,self.preset,self.root,False)['layers'][0]
        self.assertEqual([op['kind'] for op in layer['operations']],['mask','grade','sharpen'])
        self.assertEqual(layer['keys'][0]['color'],[0.,1.,0.]);self.assertFalse(layer['circle'])
    def test_simple_animation_is_geometry_metadata_without_pixel_preparation(self):
        item=self.p.timeline[0];item.keyframes={'scale':[dict(time=0,value=.5),dict(time=2,value=1.5)]}
        layer=recipe(self.p,self.preset,self.root,False)['layers'][0]
        self.assertEqual(layer['first_frame'],60);self.assertEqual(len(layer['geometry']),120)
        self.assertGreater(layer['geometry'][-1][2],layer['geometry'][0][2]);self.assertEqual(layer['operations'],[])
    def test_retimming_and_non_normal_blends_are_not_misreported_as_native_parity(self):
        item=self.p.timeline[0];item.speed=2
        with self.assertRaisesRegex(Unsupported,'retime'):recipe(self.p,self.preset,self.root,False)
        item.speed=1;item.composite_mode='Screen'
        with self.assertRaisesRegex(Unsupported,'blend'):prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
    def test_prepared_effect_source_keeps_original_layout_without_reapplying_crop(self):
        item=self.p.timeline[0];item.crop=Crop(.1,.2,.4,.5)
        layer=recipe(self.p,self.preset,self.root,False,{'i':'prepared.mkv'})['layers'][0]
        self.assertEqual(layer['path'],'prepared.mkv');self.assertTrue(layer['cpu']);self.assertFalse(layer['still'])
        self.assertEqual(layer['crop'],[0.,0.,1.,1.]);self.assertEqual(layer['size'],[1366,960]);self.assertEqual(layer['in_point'],0.)
    def test_enhanced_source_is_required_and_pixel_effects_are_not_applied_twice(self):
        item=self.p.timeline[0];item.brightness=.2;item.sharpen=1
        item.effects=[dict(name='AI Enhance',enabled=True),dict(name='Gaussian Blur',horizontal=20,vertical=20)]
        with self.assertRaisesRegex(Unsupported,'prepared'):recipe(self.p,self.preset,self.root,False)
        layer=recipe(self.p,self.preset,self.root,False,{'i':'enhanced.mkv'})['layers'][0]
        self.assertEqual(layer['operations'],[]);self.assertEqual(layer['keys'],[]);self.assertEqual(layer['path'],'enhanced.mkv')
