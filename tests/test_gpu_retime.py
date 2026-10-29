import unittest
from fractions import Fraction
from kinetic_cut.gpu_retime import retime_schedule

class RetimeScheduleTests(unittest.TestCase):
 def clock(self,origin=0):
  return Fraction(1,1000),tuple(origin+round(n*1000/60) for n in range(180)),origin
 def ids(self,speed,fps=60,start=0):
  result=retime_schedule(self.clock(),.123,.307,speed,fps,start)
  return [round(t*60) for t in result['source_times']]
 def test_fast_playback_keeps_primary_clock_first_picture_on_colliding_tick(self):
  self.assertEqual(self.ids(2.150089419612866),[8,10,12,14,16,18,20,23,25,27,29,31,33,35,37,40,42,44,46])
 def test_slow_motion_repeats_exact_pictures(self):
  self.assertEqual(self.ids(.5),[8,8,9,9,10,10,11,11,12,12,13,13,14,14,15,15,16,16,17])
 def test_fractional_fps_and_fractional_start(self):
  self.assertEqual(self.ids(1.3,60000/1001,.013),[8,9,10,12,13,14,16,17,18,20,21,22,23,25,26,27,29,30,31])
 def test_nonzero_origin_keeps_relative_source_times(self):
  a=retime_schedule(self.clock(),.123,.307,2.15,60)
  b=retime_schedule(self.clock(2000),.123,.307,2.15,60)
  self.assertEqual(a,b)
 def test_variable_frame_spacing_uses_pts(self):
  clock=(Fraction(1,1000),(0,10,40,80,90,160,200),0)
  result=retime_schedule(clock,0,.1,1,60)
  self.assertEqual(result['source_times'],[0,.01,.04,.04,.04,.08])
 def test_no_output_tick_is_empty(self):
  self.assertEqual(retime_schedule(self.clock(),0,.002,2,60,.001)['source_times'],[])
 def test_invalid_speed_or_empty_interval_fails(self):
  for speed,duration in ((0,1),(-1,1),(1,0)):
   with self.assertRaises(ValueError):retime_schedule(self.clock(),0,duration,speed,60)
 def test_end_of_source_fails_explicitly(self):
  with self.assertRaises(ValueError):retime_schedule(self.clock(),4,1,1,60)

 def test_mixed_motion_blur_stays_native_with_sampled_dimensions(self):
  import tempfile
  from kinetic_cut.model import Project,ProjectSettings,MediaItem,TimelineItem,Transform
  from kinetic_cut.exporter import ExportPreset
  from kinetic_cut.visual_fx import default_visual_fx
  from kinetic_cut.gpu_export import prepare_recipe
  p=Project(settings=ProjectSettings(width=320,height=180,fps=60),media=[MediaItem('m','source.png','image','image',2,320,180)],timeline=[TimelineItem('i','m','video_1',0,.5,transform=Transform(.5,.5,1),effects=[default_visual_fx('Punch Zoom'),dict(name='Gaussian Blur',horizontal=30,vertical=30)])])
  with tempfile.TemporaryDirectory() as directory:job=prepare_recipe(p,ExportPreset('test','h264',10,192,''),directory,False,{},'unused',None,None)
  self.assertEqual(job['cpu_islands'],[])
  self.assertGreater(len({tuple(s[2:4]) for s in job['layers'][0]['geometry']}),1)
  self.assertEqual(job['layers'][0]['operations'][0]['kind'],'blur')
