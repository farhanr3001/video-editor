import copy,json,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
from kinetic_cut.model import Project,MediaItem,TimelineItem
from kinetic_cut import enhance
from kinetic_cut.enhance_storage import State,families

class StorageTests(unittest.TestCase):
 def test_absent_effect_detection_caches_only_immutable_history(self):
  from kinetic_cut.enhance_storage import history_has_enhancement
  from kinetic_cut.runtime_index import IndexedList
  class Counted(IndexedList):
   scans=0
   def __iter__(self):self.scans+=1;return super().__iter__()
  snapshot=Project(timeline=[TimelineItem(str(n),'m','video_1',n,1) for n in range(1000)])
  values=Counted(snapshot.timeline,snapshot,'timeline');object.__setattr__(snapshot,'timeline',values)
  object.__setattr__(snapshot,'_history_snapshot',True)
  self.assertFalse(history_has_enhancement([snapshot]));scans=values.scans
  for _ in range(100):self.assertFalse(history_has_enhancement([snapshot]))
  self.assertEqual(values.scans,scans)
  live=copy.deepcopy(snapshot);self.assertNotIn('_enhance_present',live.__dict__)
  self.assertFalse(history_has_enhancement([live]));live.timeline[0].effects.append(enhance.default_effect())
  self.assertTrue(history_has_enhancement([snapshot,live]));self.assertNotIn('_enhance_present',live.__dict__)

 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.cache=self.base/'cache';self.source=self.base/'source.mp4';self.source.write_bytes(b'owner source')
  self.patch=patch('kinetic_cut.config.CACHE_DIR',self.cache);self.patch.start()
  m=MediaItem('m',str(self.source),'video','source',2,16,12);m.fps=10
  i=TimelineItem('i','m','video_1',0,2);i.effects=[enhance.default_effect()];self.p=Project(media=[m],timeline=[i]);self.item=i;self.media=m
  self.root=enhance.cache_path(self.p,m,i,0);(self.root/'frames').mkdir(parents=True);(self.root/'frames/00000000.png').write_bytes(b'cache');(self.root/'frames/00000019.png').write_bytes(b'cache');(self.root/'info.json').write_text(json.dumps(dict(key=self.root.name,family=enhance.signature(m,i,0,10,False),frames=20,fps=10,source_start=0,engine='compact-v1')))
  enhance._range_indexes.clear();self.state=State(self.cache/'ai-enhance')
 def tearDown(self):self.patch.stop();enhance._range_indexes.clear();self.temp.cleanup()
 def empty(self):
  p=copy.deepcopy(self.p);p.timeline=[];return p
 def test_remove_clip_keeps_undo_then_close_reclaims(self):
  self.state.update([self.p],[]);self.state.sweep();self.assertTrue(self.root.exists())
  self.state.update([self.p,self.empty()],[]);self.state.sweep();self.assertTrue(self.root.exists())
  self.state.update([self.empty()],[],identify=[self.p]);report=self.state.sweep(True);self.assertEqual(report['deleted'],1);self.assertFalse(self.root.exists());self.assertEqual(self.source.read_bytes(),b'owner source')
 def test_remove_effect_and_history_expiry_reclaims(self):
  self.state.update([self.p],[]);self.state.sweep();p=copy.deepcopy(self.p);p.timeline[0].effects=[]
  self.state.update([p],[],identify=[self.p]);self.state.sweep();self.assertFalse(self.root.exists())
 def test_other_timeline_clip_shares_frames(self):
  p=copy.deepcopy(self.p);p.timeline[0].id='second';self.state.update([p],[],identify=[self.p]);self.state.sweep(True);self.assertTrue(self.root.exists())
 def test_other_saved_project_retains_then_release_reclaims(self):
  path=self.base/'other.kcut';self.p.save(path);self.state.update([self.empty()],[path],identify=[self.p]);self.state.sweep(True);self.assertTrue(self.root.exists())
  self.empty().save(path);self.state.sweep(True);self.assertFalse(self.root.exists())
 def test_other_live_session_retains(self):
  import psutil
  folder=self.cache/'ai-enhance/.sessions';folder.mkdir();lease=folder/'other.json';lease.write_text(json.dumps(dict(pid=os.getpid(),started=psutil.Process().create_time(),families=list(families([self.p])[0]))))
  self.state.update([self.empty()],[],identify=[self.p]);self.state.sweep(True);self.assertTrue(self.root.exists());lease.unlink();self.state.sweep(True);self.assertFalse(self.root.exists())
 def test_export_movie_reclaimed_together_with_frames(self):
  path=self.cache/'ai-enhance'/(enhance.export_key(self.p,self.item)+'.mkv');path.write_bytes(b'cached export')
  self.state.update([self.p],[]);self.state.sweep();self.assertTrue(path.exists())
  self.state.update([self.empty()],[],identify=[self.p]);self.state.sweep(True);self.assertFalse(path.exists());self.assertFalse(self.root.exists())
 def test_corrupt_other_project_fails_closed(self):
  path=self.base/'bad.kcut';path.write_text('{bad');self.state.update([self.empty()],[path],identify=[self.p]);report=self.state.sweep(True);self.assertTrue(report['unsafe']);self.assertTrue(self.root.exists())
 def test_unknown_directory_and_models_untouched(self):
  other=self.cache/'ai-enhance/foreign';other.mkdir();(other/'keep').write_text('keep');models=self.base/'components/ai-enhance-v1';models.mkdir(parents=True);(models/'model.pth').write_text('model')
  self.state.update([self.empty()],[],identify=[self.p]);self.state.sweep(True);self.assertEqual((other/'keep').read_text(),'keep');self.assertTrue((models/'model.pth').exists())
 def test_cancelled_or_failed_publication_is_not_automatically_deleted(self):
  (self.root/'info.json').unlink();self.state.update([self.p],[]);self.state.sweep(True);self.assertTrue(self.root.exists())
 def test_new_session_adopts_stale_retirement_journal(self):
  self.state.update([self.p],[]);self.state.sweep(True);next_state=State(self.cache/'ai-enhance');next_state.update([self.empty()],[]);next_state.sweep(True);self.assertFalse(self.root.exists())
 def test_nested_used_compound_retains_but_unused_bin_media_does_not(self):
  wrapper=MediaItem('compound','','video','nested',2,16,12);wrapper.compound=self.p.to_dict();outer=Project(media=[wrapper],timeline=[TimelineItem('outer','compound','video_1',0,2)])
  self.state.update([outer],[]);self.state.sweep();self.assertTrue(self.root.exists());outer.timeline=[];self.state.update([outer],[],identify=[self.p]);self.state.sweep(True);self.assertFalse(self.root.exists())
 def test_storage_estimate_deduplicates_and_reuses_ready_frames(self):
  self.assertEqual(enhance.estimate_space(self.p,[self.item])['peak_bytes'],0)
  (self.root/'info.json').unlink();enhance._range_indexes.clear();duplicate=copy.deepcopy(self.item);duplicate.id='duplicate';single=enhance.estimate_space(self.p,[self.item]);both=enhance.estimate_space(self.p,[self.item,duplicate]);self.assertGreater(single['peak_bytes'],0);self.assertEqual(single['peak_bytes'],both['peak_bytes'])

 def test_locked_retirement_is_retried_without_leaking_disk_frames(self):
  self.state.update([self.p],[]);self.state.sweep();self.state.update([self.empty()],[],identify=[self.p])
  with patch('shutil.rmtree',side_effect=PermissionError('scanner holds file')):self.state.sweep(True)
  self.assertTrue(list((self.cache/'ai-enhance').glob('_gc-*')))
  next_state=State(self.cache/'ai-enhance');next_state.update([self.empty()],[]);next_state.sweep(True)
  self.assertFalse(list((self.cache/'ai-enhance').glob('_gc-*')));self.assertTrue(self.source.exists())

 def test_rapid_project_switch_before_first_sweep_still_tracks_old_frames(self):
  self.state.update([self.p],[]);self.state.update([self.empty()],[])
  self.state.sweep(True);self.assertFalse(self.root.exists())
