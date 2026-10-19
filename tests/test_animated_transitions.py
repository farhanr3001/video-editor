import copy,math,json,unittest
import tempfile,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QImage,QPainter
from kinetic_cut.animated_transitions import NAMES,CONTROLS,BASE,values,defaults,maps,composite,shader_map
from kinetic_cut.transitions import Transition,composite_transition
from kinetic_cut.model import Project,ProjectSettings,MediaItem,TimelineItem,Transform
from kinetic_cut.gpu_export import recipe,Unsupported
from kinetic_cut.exporter import ExportPreset

def image(offset=0):
 y,x=np.mgrid[:48,:64];a=np.empty((48,64,4),np.uint8);a[:,:,0]=(x*4+offset)%256;a[:,:,1]=(y*5+offset)%256;a[:,:,2]=160;a[:,:,3]=np.where(x<32,160,255)
 return QImage(a.data,64,48,256,QImage.Format_RGBA8888).copy()

class AnimatedTransitions(unittest.TestCase):
 def test_catalogue_has_24_distinct_pair_transitions_and_specific_controls(self):
  self.assertEqual(len(set(NAMES)),24);self.assertIn('Explosion',NAMES);self.assertIn('Puzzle Assemble',NAMES)
  for name in NAMES:
   self.assertTrue(CONTROLS[name]);self.assertLessEqual(len(CONTROLS[name]),6)
   self.assertEqual(Transition('t',name).properties,defaults(name))
 def test_exact_endpoints_for_every_effect_include_alpha(self):
  a,b=image(),image(85)
  for name in NAMES:
   t=Transition('t',name,properties={'easing':'Linear'})
   self.assertEqual(composite(a,b,t,0,(64,48)),a.convertToFormat(QImage.Format_RGBA8888_Premultiplied),name)
   self.assertEqual(composite(a,b,t,1,(64,48)),b.convertToFormat(QImage.Format_RGBA8888_Premultiplied),name)
 def test_missing_side_and_all_midpoints_are_safe_and_preserve_lower_layer(self):
  a,b=image(),image(85)
  for name in NAMES:
   t=Transition('t',name)
   result=composite(a,b,t,.47,(64,48));self.assertFalse(result.isNull(),name)
   self.assertNotEqual(result,a);self.assertNotEqual(result,b)
   self.assertFalse(composite(None,b,t,.47,(64,48)).isNull())
   self.assertFalse(composite(a,None,t,.47,(64,48)).isNull())
   blank=composite(None,None,t,.47,(64,48));self.assertEqual(blank.pixelColor(30,30).alpha(),0)
 def test_puzzle_assembles_the_actual_incoming_picture_as_moving_pieces(self):
  ua,va,ub,vb,weight=maps('Puzzle Assemble',160,90,values({}),.55)
  u=(np.arange(160)[None,:]+.5)/160;v=(np.arange(90)[:,None]+.5)/90
  self.assertTrue(((weight>.5)&((abs(ub-u)+abs(vb-v))>.01)).any(),'Visible incoming pieces must move, not just reveal a stationary puzzle mask')
  self.assertTrue((weight<.1).any());self.assertTrue((weight>.9).any())
 def test_deterministic_seek_reverse_and_bounded_malformed_controls(self):
  for name in NAMES:
   for properties in ({},{k:float('nan') for k,*_ in BASE},{k:1e20 for k,*_ in BASE},{k:-1e20 for k,*_ in BASE}):
    params=values(properties);self.assertTrue(all(math.isfinite(v) for v in params))
    for at in (0,.12,.5,.92,1):
     out=maps(name,32,24,params,at);self.assertTrue(all(np.isfinite(v).all() for v in out),(name,at));self.assertTrue(((out[-1]>=0)&(out[-1]<=1)).all())
   t=Transition('t',name);first=composite(image(),image(85),t,.31,(64,48));composite(image(),image(85),t,.8,(64,48));self.assertEqual(first,composite(image(),image(85),t,.31,(64,48)),name)
 def test_compositor_clips_and_does_not_overwrite_outside_target(self):
  target=QImage(100,80,QImage.Format_RGBA8888);target.fill(Qt.green)
  painter=QPainter(target);composite_transition(painter,QRectF(10,10,64,48),image(),image(85),Transition('t','Explosion'),.5);painter.end()
  self.assertEqual(target.pixelColor(2,2),Qt.green)
 def project(self):
  media=[MediaItem('m','test.mp4','video','Test',10,64,48,30)]
  p=Project(settings=ProjectSettings(64,48,30),media=media,timeline=[TimelineItem('a','m','video_1',0,2,in_point=1,transform=Transform(.5,.5,1)),TimelineItem('b','m','video_1',2,2,in_point=4,transform=Transform(.5,.5,1))])
  return p
 def test_native_recipe_pairs_keep_track_order_clocks_and_original_document(self):
  p=self.project();p.transitions=[Transition('t','Explosion',track='video_1',start=1.5,duration=1,left_item_id='a',right_item_id='b')]
  before=copy.deepcopy(p.to_dict());job=recipe(p,ExportPreset('t','h264',8,192,''),Path('.'),False)
  self.assertEqual(p.to_dict(),before);self.assertEqual(len(job['layers']),4)
  base,pair=job['layers'][:2],job['layers'][2:];self.assertTrue(all(l['skip_ranges']==[[1.5,2.5]] for l in base))
  self.assertEqual([l['pair']['side'] for l in pair],[0,1]);self.assertEqual([l['source_origin'] for l in pair],[0,2]);self.assertEqual([l['source_in'] for l in pair],[1,4])
  self.assertTrue(all(l['start']==1.5 and l['end']==2.5 and not l['transitions'] for l in pair))
  self.assertEqual(Project.from_dict(json.loads(json.dumps(p.to_dict()))).transitions[0].name,'Explosion')
 def test_edge_transition_gets_transparent_endpoint_and_overlaps_request_exact_fallback(self):
  p=self.project();t=Transition('t','Wave Sweep',track='video_1',start=0,duration=.8,right_item_id='a');p.transitions=[t]
  job=recipe(p,ExportPreset('t','h264',8,192,''),Path('.'),False)
  self.assertTrue(next(l for l in job['layers'] if l.get('pair',{}).get('side')==0)['empty'])
  p.transitions.append(Transition('other','Cross Dissolve',track='video_1',start=.2,duration=.5,right_item_id='a'))
  with self.assertRaises(Unsupported):recipe(p,ExportPreset('t','h264',8,192,''),Path('.'),False)
 def test_cpu_graph_refuses_silent_fade_substitution(self):
  from kinetic_cut.rendergraph import command
  p=self.project();p.transitions=[Transition('t','Puzzle Assemble',right_item_id='a')]
  with self.assertRaisesRegex(ValueError,'exact export preparation'):command(p,'out.mp4',ExportPreset('t','h264',8,192,''))
  p.track_states['video_1']['visible']=False
  self.assertIsInstance(command(p,'out.mp4',ExportPreset('t','h264',8,192,'')),list)
 def test_gpu_shader_sources_match_the_shared_maps(self):
  root=Path(__file__).resolve().parents[1];native=(root/'native/gpu_export.cpp').read_text()
  for n,name in enumerate(NAMES,1):
   self.assertIn(shader_map(name,'glsl'),(root/f'assets/shaders/transition_{n}.frag').read_text())
   self.assertIn(shader_map(name,'hlsl'),native)

class TransitionInspector(unittest.TestCase):
 def test_specific_parameters_and_reset_are_undoable_and_categories_persist(self):
  from kinetic_cut.ui import MainWindow
  from PySide6.QtWidgets import QApplication
  from PySide6.QtCore import QThreadPool,QEvent
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'image.png';image().save(str(path));w=MainWindow();w.autosave_timer.stop()
   try:
    p=Project(media=[MediaItem('m',str(path),'image','Photo',4,64,48)],timeline=[TimelineItem('a','m','video_1',0,2),TimelineItem('b','m','video_1',2,2)])
    w.set_project(p)
    for name in NAMES:
     p.transitions=[];w.set_project(p);trans=w.apply_transition(name,'video_1','a','b',duration=1)
     self.assertIsNotNone(trans);self.assertEqual(w.inspector.animated_trans_name,name)
     self.assertEqual(set(w.inspector.animated_trans_rows),{r[0] for r in CONTROLS[name]})
     row=next(iter(w.inspector.animated_trans_rows.values()));key=next(iter(w.inspector.animated_trans_rows));old=trans.properties[key]
     row.edited.emit(old+.1,.1);self.assertAlmostEqual(w.project.transition_by_id(trans.id).properties[key],old+.1)
     w.undo();self.assertAlmostEqual(w.project.transition_by_id(trans.id).properties[key],old)
     w.redo();self.assertAlmostEqual(w.project.transition_by_id(trans.id).properties[key],old+.1)
     w.inspector.reset_trans_properties();self.assertEqual(w.project.transition_by_id(trans.id).properties,defaults(name))
     p=w.project
   finally:
    w.close();deadline=time.monotonic()+10
    while w.isVisible() and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.02)
    QThreadPool.globalInstance().waitForDone(10000);QApplication.processEvents();w.deleteLater();QApplication.sendPostedEvents(None,QEvent.DeferredDelete);QApplication.processEvents()

if __name__=='__main__':unittest.main()
