import copy,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kinetic_cut.model import Project,ProjectSettings,TimelineItem,MediaItem
from kinetic_cut.exporter import ExportPreset
from kinetic_cut.gpu_export import recipe,prepare_recipe,Unsupported
from kinetic_cut.transitions import Transition

class EffectExportStreamTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.preset=ExportPreset('test','h264',10,192,'','auto')
  self.p=Project(settings=ProjectSettings(width=320,height=180,fps=60),media=[MediaItem('m','source.mp4','video','source',10,320,180,60)],timeline=[TimelineItem('i','m','video_1',.013,1.027,in_point=.1,speed=2.15)])
 def tearDown(self):self.temp.cleanup()
 def test_retimed_effect_defers_exact_pixels_without_a_serial_ffv1_pass(self):
  self.p.timeline[0].effects=[dict(name='Gaussian Blur',horizontal=24,vertical=24)]
  before=copy.deepcopy(self.p.to_dict())
  with patch('kinetic_cut.export_process.render') as render:job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  render.assert_not_called();self.assertEqual(self.p.to_dict(),before)
  layer=job['layers'][0];spec=job['raw_sources'][layer['path']]
  self.assertTrue(layer['cpu']);self.assertEqual((spec['width'],spec['height']),(320,180))
  self.assertNotIn('ffv1',spec['command']);self.assertEqual(spec['command'][-1],'pipe:1')
  graph=spec['command'][spec['command'].index('-filter_complex')+1]
  self.assertIn('gblur=',graph);self.assertIn('/2.15000000',graph)
 def test_fractional_interval_has_exact_global_frame_count_and_terminal_clock(self):
  with patch('kinetic_cut.export_process.render'):job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  layer=job['layers'][0];spec=job['raw_sources'][layer['path']];item=self.p.timeline[0]
  first=math.ceil(item.start*60-1e-7);last=math.ceil((item.start+item.duration)*60-1e-7)
  self.assertEqual(spec['frames'],last-first);self.assertEqual((layer['start'],layer['end']),(first/60,last/60))
  self.assertEqual(spec['command'][spec['command'].index('-frames:v')+1],str(last-first))
 def test_subframe_interval_with_no_output_frame_does_not_start_a_producer(self):
  self.p.timeline[0].start=.001;self.p.timeline[0].duration=.002
  with patch('kinetic_cut.export_process.render') as render:job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  render.assert_not_called();self.assertEqual(job['layers'],[]);self.assertFalse(job.get('raw_sources'))
 def test_legacy_motion_and_wipes_cannot_silently_export_as_fades(self):
  self.p.timeline[0].speed=1
  for name in ('Whip Pan Transition','Zoom In (Whoosh)','Clock Wipe','Dip to Color / White Flash'):
   self.p.transitions=[Transition('t',name,track='video_1',start=.013,duration=.2,right_item_id='i')]
   with self.subTest(name=name):
    job=recipe(self.p,self.preset,self.root,False);pairs=[l for l in job['layers'] if 'pair' in l]
    self.assertEqual(len(pairs),2);self.assertTrue(all(l['pair']['legacy'] for l in pairs));self.assertEqual(pairs[0]['skip_ranges'],[])
 def test_legacy_transition_preparation_is_used_by_native_export(self):
  self.p.timeline[0].speed=1;self.p.transitions=[Transition('t','Whip Pan Transition',right_item_id='i')]
  prepared=copy.deepcopy(self.p);prepared.transitions=[]
  original=recipe
  def unavailable(project,*args,**kwargs):
   if project.transitions:raise Unsupported('exact transition preparation')
   return original(project,*args,**kwargs)
  with patch('kinetic_cut.gpu_export.recipe',side_effect=unavailable),patch('kinetic_cut.transition_export.prepare',return_value=prepared) as prepare:job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  prepare.assert_called_once();self.assertTrue(job['layers'])
 def test_native_paired_transitions_and_exact_legacy_dissolve_routes(self):
  self.p.timeline[0].speed=1
  self.p.transitions=[Transition('t','Puzzle Assemble',right_item_id='i')]
  self.assertEqual(sum('pair' in l for l in recipe(self.p,self.preset,self.root,False)['layers']),2)
  self.p.transitions=[Transition('t','Cross Dissolve',right_item_id='i')]
  self.assertEqual(sum(l.get('pair',{}).get('legacy',False) for l in recipe(self.p,self.preset,self.root,False)['layers']),2)

 def test_oversized_stream_filter_uses_exact_utf8_script_before_windows_launch(self):
  import subprocess
  from kinetic_cut.rendergraph import command
  graph='null'+(' '*40000)
  with patch('kinetic_cut.rendergraph.command',return_value=['ffmpeg','-filter_complex',graph,'-c:v','unused','out']),patch('kinetic_cut.export_process.render'):
   job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  spec=next(iter(job['raw_sources'].values()));args=spec['command'];self.assertLess(len(subprocess.list2cmdline(args)),28000)
  self.assertNotIn('-filter_complex',args);self.assertEqual(Path(args[args.index('-filter_complex_script')+1]).read_text(encoding='utf-8'),graph)
 def test_streamed_endpoint_stays_hidden_during_prepared_transition(self):
  self.p._transition_exclusions={'i':[[.02,.2]]}
  with patch('kinetic_cut.export_process.render'):job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  self.assertEqual(job['layers'][0]['skip_ranges'],[[.02,.2]])
 def test_cpu_batches_preserve_prepared_transition_exclusion_without_mutating_source(self):
  from kinetic_cut.render_batches import prepare
  from kinetic_cut.rendergraph import command
  import threading
  self.p._transition_exclusions={'i':[[.02,.2]]};graphs=[]
  def capture(project,*args,**kwargs):
   result=command(project,*args,**kwargs);graphs.append(result[result.index('-filter_complex')+1]);return result
  with patch('kinetic_cut.rendergraph.command',side_effect=capture),patch('kinetic_cut.export_process.render',return_value=(0,[])),patch('pathlib.Path.unlink'):
   prepare(self.p,self.root,self.preset,'ffmpeg',{},None,threading.Event())
  self.assertTrue(graphs);self.assertTrue(all('not(gte(t,' in graph for graph in graphs))
  self.assertEqual(self.p._transition_exclusions,{'i':[[.02,.2]]})

 def test_native_camera_uses_exact_preview_transform_each_output_frame(self):
  from kinetic_cut.visual_fx import default_visual_fx,evaluate_visual_fx,apply_visual_fx_to_transform
  from kinetic_cut.keyframes import evaluated
  from kinetic_cut.exporter import _target_size
  self.p.timeline[0].speed=1;item=self.p.timeline[0];item.effects=[default_visual_fx('Punch Zoom')]
  job=recipe(self.p,self.preset,self.root,False);layer=job['layers'][0]
  for index,sample in enumerate(layer['geometry']):
   at=(layer['first_frame']+index)/60-item.start;expected=copy.deepcopy(evaluated(item,at));apply_visual_fx_to_transform(expected.transform,evaluate_visual_fx(expected,at,320,180))
   width,height=_target_size(expected,self.p.media[0],320,1.,180)
   self.assertEqual(sample[2:4],[width,height])
 def test_perspective_camera_is_gpu_geometry_without_cpu_islands(self):
  from kinetic_cut.visual_fx import default_visual_fx
  self.p.timeline[0].speed=1;self.p.timeline[0].effects=[default_visual_fx('Tilt')]
  job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  self.assertEqual(job['cpu_islands'],[]);self.assertTrue(any(len(s)==15 for s in job['layers'][0]['geometry']))
 def test_projective_placement_maps_rotated_pivot_back_to_original_uv(self):
  from PySide6.QtGui import QTransform
  from PySide6.QtCore import Qt,QPointF
  from kinetic_cut.gpu_export import placement_homography
  from kinetic_cut.model import Transform
  t=Transform(.5,.5,1,rotation=23,anchor_x=12,anchor_y=-7,pitch=30,yaw=-12);w,h=180,90;cx,cy=150,200
  rows=placement_homography(t,w,h,cx,cy);m=QTransform();m.translate(cx+t.anchor_x,cy+t.anchor_y);m.rotate(t.rotation);m.translate(-t.anchor_x,-t.anchor_y);m.rotate(t.pitch,Qt.XAxis);m.rotate(t.yaw,Qt.YAxis)
  for u,v in ((0,0),(1,0),(0,1),(1,1),(.3,.7)):
   q=m.map(QPointF((u-.5)*w,(v-.5)*h));den=rows[6]*q.x()+rows[7]*q.y()+rows[8]
   self.assertAlmostEqual((rows[0]*q.x()+rows[1]*q.y()+rows[2])/den,u,places=10);self.assertAlmostEqual((rows[3]*q.x()+rows[4]*q.y()+rows[5])/den,v,places=10)

 def test_preview_effect_stream_matches_real_compositor_and_finishes_producer(self):
  from PySide6.QtWidgets import QApplication
  from PySide6.QtGui import QImage,QColor
  from PySide6.QtCore import QRectF
  from kinetic_cut.visual_fx import default_visual_fx
  from kinetic_cut.gpu_export_decode import RawSource
  from kinetic_cut.preview_compositor import SceneContext,render
  import numpy as np
  app=QApplication.instance() or QApplication([]);path=self.root/'pattern.png';image=QImage(320,180,QImage.Format_RGBA8888);image.fill(QColor('#457abd'));image.save(str(path))
  self.p.media[0].kind='image';self.p.media[0].path=str(path);item=self.p.timeline[0];item.speed=1;item.duration=.1;item.effects=[default_visual_fx('Punch Zoom'),dict(name='Gaussian Blur',horizontal=4,vertical=4)]
  second=copy.deepcopy(item);second.id='second';second.track='video_2';second.speed=2;second.effects=[];self.p.video_tracks.append('video_2');self.p.timeline.append(second)
  original=recipe
  def unsupported_geometry(project,*args,**kwargs):
   if project.timeline:raise Unsupported('animated effect geometry' if project.timeline[0].id==item.id else 'exact retime frame cadence')
   return original(project,*args,**kwargs)
  with patch('kinetic_cut.gpu_export.recipe',side_effect=unsupported_geometry):job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  self.assertEqual(len(job['raw_sources']),2);spec=next(iter(job['raw_sources'].values()));self.assertIn('--preview-effect-source',spec['command']);self.p.timeline=[item]
  source=RawSource(spec);context=SceneContext(copy.deepcopy(self.p),{},{},{},False,1.,draw_captions=False);context.transparent=True;first=math.ceil(item.start*60-1e-7)
  try:
   for n in range(spec['frames']):
    context.project.playhead=(first+n)/60;expected,_,_=render(context,QRectF(0,0,320,180),(320,180),1.);expected=expected.convertToFormat(QImage.Format_RGBA8888);pixels=np.frombuffer(expected.constBits(),np.uint8).reshape(180,320,4)
    np.testing.assert_array_equal(source.frame(n/60),pixels)
   self.assertEqual(source.process.poll(),0)
  finally:source.close()

 def test_unrelated_compatibility_layer_does_not_bake_native_transitions(self):
  from kinetic_cut.visual_fx import default_visual_fx
  self.p.timeline[0].speed=1
  background=copy.deepcopy(self.p.timeline[0]);background.id='bg';background.track='video_2';background.role='background';background.effects=[default_visual_fx('Tilt')]
  self.p.video_tracks.append('video_2');self.p.timeline.append(background)
  self.p.transitions=[Transition('t','Whip Pan Transition',track='video_1',start=.013,duration=.2,right_item_id='i')]
  with patch('kinetic_cut.transition_export.prepare',side_effect=AssertionError('unrelated serial transition preparation')):
   job=prepare_recipe(self.p,self.preset,self.root,False,{},'ffmpeg',None,None)
  self.assertEqual(sum(bool(layer.get('pair',{}).get('legacy')) for layer in job['layers']),2)
  self.assertFalse(any('exact paired transition' in reason for reason in job['cpu_islands']))
