import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QSize,Qt
from PySide6.QtGui import QImage,QColor
from kinetic_cut import enhance
from kinetic_cut.enhance_preview import PreviewFrames

class EnhancePreviewTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.cache=PreviewFrames()
  for folder in ('frames','original'):(self.root/folder).mkdir()
  self.record=dict(root=str(self.root),frames=2,fps=10,original_frames=True);(self.root/'info.json').write_text('{}')
  for n in range(2):
   raw=QImage(16,12,QImage.Format_RGBA8888);raw.fill(QColor(20,60,90,160));raw.save(str(self.root/'original'/f'{n:08d}.png'))
   im=QImage(64,48,QImage.Format_RGBA8888);im.fill(QColor(80+n*40,140,180));im.save(str(self.root/'frames'/f'{n:08d}.png'))
  self.p=enhance.parameters(enhance.default_effect())
 def tearDown(self):self.cache.close();self.temp.cleanup()
 def test_display_cache_reuses_pixels_and_strength_and_removal_invalidate(self):
  with patch('kinetic_cut.enhance.read_frame',wraps=enhance.read_frame) as read:
   a=self.cache.get(self.record,0,self.p,QSize(32,24),False);b=self.cache.get(self.record,0,self.p,QSize(32,24),False)
   self.assertEqual(a,b);self.assertEqual(read.call_count,1);self.assertEqual(a.size(),QSize(32,24))
   self.p['enhancement_strength']=20;c=self.cache.get(self.record,0,self.p,QSize(32,24),False);self.assertNotEqual(c,a);self.assertEqual(read.call_count,2)
   (self.root/'frames/00000000.png').unlink();self.assertTrue(self.cache.get(self.record,0,self.p,QSize(32,24),False).isNull())
 def test_preview_preserves_alpha_and_full_resolution_reader(self):
  full=enhance.read_frame(self.record,0,self.p);preview=enhance.read_frame(self.record,0,self.p,QSize(32,24))
  self.assertEqual(full.size(),QSize(64,48));self.assertEqual(preview.size(),QSize(32,24));self.assertEqual(preview.pixelColor(0,0).alpha(),160)
  for channel in ('red','green','blue'):self.assertLessEqual(abs(getattr(full.pixelColor(0,0),channel)()-getattr(preview.pixelColor(0,0),channel)()),1)
 def test_clear_discards_inflight_result(self):
  from concurrent.futures import Future
  future=Future();self.cache.pending['fake']=future;self.cache.clear();self.assertTrue(future.cancelled());self.assertEqual(len(self.cache.images),0)
 def test_source_defaults_match_owner_but_legacy_missing_fields_stay_compatible(self):
  expected=dict(enhancement_strength=93,detail_recovery=100,denoise=71,deblur=94,sharpen=100,compression_cleanup=100,face_restore=False,face_restore_strength=25,temporal_stability=80,mix=100,upscale=4,quality_mode='High')
  actual=enhance.default_effect()
  for key,value in expected.items():self.assertEqual(actual[key],value)
  self.assertEqual(enhance.parameters({'name':enhance.NAME})['upscale'],1)
 def test_real_prefetch_processes_are_retired(self):
  import psutil
  self.cache.get(self.record,0,self.p,QSize(32,24));deadline=time.monotonic()+8
  while not self.cache.prepared and time.monotonic()<deadline:time.sleep(.02)
  self.assertTrue(self.cache.prepared);pids=list(self.cache.executor._processes);self.cache.close();deadline=time.monotonic()+5
  while any(psutil.pid_exists(pid) for pid in pids) and time.monotonic()<deadline:time.sleep(.02)
  self.assertTrue(all(not psutil.pid_exists(pid) for pid in pids))
 def test_compact_progress_reports_elapsed_and_estimate(self):
  from kinetic_cut.enhance_ui import EnhanceProgress
  with patch('kinetic_cut.enhance_ui.time.monotonic',return_value=100):dialog=EnhanceProgress()
  with patch('kinetic_cut.enhance_ui.time.monotonic',return_value=110):dialog.setValue(25)
  self.assertIn('10s',dialog.timing.text());self.assertIn('30s',dialog.timing.text());self.assertLess(dialog.width(),600);dialog.close();dialog.deleteLater()

 def test_composition_child_uses_threads_not_nested_processes(self):
  import multiprocessing
  from concurrent.futures import ThreadPoolExecutor
  class Child:daemon=True
  with patch.object(multiprocessing,'current_process',return_value=Child()):
   self.cache.get(self.record,0,self.p,QSize(32,24));self.assertIsInstance(self.cache.executor,ThreadPoolExecutor)

 def test_large_viewer_does_not_inflate_prepared_pixels(self):
  preview=enhance.read_frame(self.record,0,self.p,QSize(4000,3000))
  self.assertEqual(preview.size(),QSize(64,48))

 def test_cache_miss_never_substitutes_recent_enhanced_pixels(self):
  first=self.cache.get(self.record,0,self.p,QSize(32,24),False)
  with patch('kinetic_cut.enhance.read_frame',wraps=enhance.read_frame) as read:
   second=self.cache.get(self.record,1,self.p,QSize(32,24),False)
  self.assertNotEqual(first,second);self.assertEqual(read.call_args.args[1],1)
 def test_paused_seek_still_loads_exact_frame(self):
  first=self.cache.get(self.record,0,self.p,QSize(32,24),False)
  last=self.cache.get(self.record,1,self.p,QSize(32,24),False)
  self.assertNotEqual(first,last)

 def test_playing_replaced_metadata_cannot_reuse_previous_generation(self):
  self.cache.get(self.record,0,self.p,QSize(32,24),False)
  (self.root/'info.json').write_text('{"generation":2}')
  with patch('kinetic_cut.enhance.read_frame',wraps=enhance.read_frame) as read:
   self.cache.get(self.record,1,self.p,QSize(32,24),False);self.assertEqual(read.call_count,1)
