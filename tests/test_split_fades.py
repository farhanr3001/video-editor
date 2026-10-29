import copy,json,unittest
from kinetic_cut.model import Project,TimelineItem
class SplitFadeTests(unittest.TestCase):
 def test_manual_cut_keeps_fades_on_original_and_new_piece_has_no_fades(self):
  for track,role in [('video_1','normal'),('audio_1','source_audio'),('video_1','title'),('video_1','graphic')]:
   with self.subTest(track=track,role=role):
    p=Project(timeline=[TimelineItem('i','m',track,2,8,in_point=1,speed=1.5,role=role,fade_in=.4,fade_out=.7)])
    left,right=p.split('i',5)
    self.assertEqual((left.fade_in,left.fade_out),(.4,.7));self.assertEqual((right.fade_in,right.fade_out),(0,0))
    self.assertEqual((left.start,left.duration,right.start,right.duration,right.in_point),(2,3,5,5,5.5))
    loaded=Project.from_dict(json.loads(json.dumps(p.to_dict())))
    self.assertEqual((loaded.item_by_id(right.id).fade_in,loaded.item_by_id(right.id).fade_out),(0,0))
 def test_retained_fades_fit_shortened_original_and_repeated_cuts_do_not_copy(self):
  p=Project(timeline=[TimelineItem('i','m','audio_1',0,8,fade_in=3,fade_out=4)])
  left,right=p.split('i',1);self.assertEqual((left.fade_in,left.fade_out),(1,1))
  a,b=p.split(right.id,3);self.assertEqual((a.fade_in,a.fade_out,b.fade_in,b.fade_out),(0,0,0,0))
 def test_linked_cut_clears_each_new_fragment_and_preserves_locked_lane(self):
  p=Project(timeline=[TimelineItem('v','m','video_1',0,8,link_id='av',fade_in=.2,fade_out=.3),TimelineItem('a','m','audio_1',0,8,link_id='av',fade_in=.4,fade_out=.5)])
  p.split_selection(['v'],3)
  self.assertEqual(len(p.timeline),4)
  self.assertTrue(all(i.fade_in==i.fade_out==0 for i in p.timeline if i.id not in ('v','a')))
  p.track_states.setdefault('audio_1',{})['locked']=True;before=copy.deepcopy(p.item_by_id('a'))
  p.split_selection(['v'],1);self.assertEqual(p.item_by_id('a'),before)
 def test_invalid_boundary_cut_preserves_original_fades_and_document(self):
  p=Project(timeline=[TimelineItem('i','m','video_1',0,8,fade_in=.4,fade_out=.7)])
  before=copy.deepcopy(p.to_dict())
  for at in (0,.01,7.99,8):self.assertEqual(p.split('i',at),[])
  self.assertEqual(p.to_dict(),before)

 def test_linked_ui_split_is_one_history_step_and_undo_redo_restores_fades(self):
  from PySide6.QtWidgets import QApplication
  from PySide6.QtCore import QThreadPool,QEvent
  from kinetic_cut.ui import MainWindow
  app=QApplication.instance() or QApplication([]);w=MainWindow();w.autosave_timer.stop()
  try:
   p=Project(timeline=[TimelineItem('v','missing','video_1',0,8,link_id='av',fade_in=.2,fade_out=.3),TimelineItem('a','missing','audio_1',0,8,link_id='av',fade_in=.4,fade_out=.5)])
   w.set_project(p);w.timeline.select_ids({'v'},'v');w.seek(3);index=w._history_index;w.split_selected()
   self.assertEqual(w._history_index,index+1)
   self.assertTrue(all(i.fade_in==i.fade_out==0 for i in w.project.timeline if i.id not in ('v','a')))
   w.undo();self.assertEqual(len(w.project.timeline),2);self.assertEqual((w.project.item_by_id('a').fade_in,w.project.item_by_id('a').fade_out),(.4,.5))
   w.redo();self.assertEqual(len(w.project.timeline),4);self.assertTrue(all(i.fade_in==i.fade_out==0 for i in w.project.timeline if i.id not in ('v','a')))
  finally:
   w.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents();w.deleteLater();app.sendPostedEvents(None,QEvent.DeferredDelete)
