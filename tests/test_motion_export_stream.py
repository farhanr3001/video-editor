import copy,json,math,tempfile,unittest
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter
from PySide6.QtCore import Qt
from kinetic_cut.model import Project,ProjectSettings,TimelineItem,Transform
from kinetic_cut.motion_export_stream import samples,layers
from kinetic_cut.native_animation import frame
from kinetic_cut.gpu_export_decode import RawSource

class MotionStreamTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def project(self):
  scene=dict(canvas=[160,284],nodes=[dict(id='box',kind='rectangle',x=80,y=142,width=60,height=40,fill='#fe7623',keyframes={'x':[dict(time=0,value=50),dict(time=.2,value=80)]})])
  item=TimelineItem('g','','video_1',.013,1.2,role='graphic',graphic_type='Motion Composition',graphic_data=dict(scene=scene),transform=Transform(.5,.5))
  return Project(settings=ProjectSettings(width=160,height=284,fps=30),timeline=[item])
 def test_static_hold_skips_rasters_and_retains_terminal_sample(self):
  p=self.project();indices=samples(p,p.timeline[0],36)
  self.assertEqual(indices[0],0);self.assertEqual(indices[-1],35);self.assertLess(len(indices),12)
  self.assertTrue(set(range(7))<=set(indices))
 def test_masks_blur_and_text_clocks_are_conservative(self):
  p=self.project();i=p.timeline[0];node=i.graphic_data['scene']['nodes'][0]
  node['mask']=dict(keyframes=dict(width=[dict(time=.5,value=10),dict(time=.7,value=50)]))
  i.graphic_data['scene']['motion_blur']=dict(samples=4,shutter=360)
  indices=samples(p,i,36);self.assertTrue(set(range(14,24))<=set(indices))
  node.update(kind='text',text='hello',text_mode='typewriter',caret=True)
  self.assertEqual(samples(p,i,36),list(range(36)))
 def test_sparse_owned_producer_matches_dense_native_pixels_on_every_tick(self):
  p=self.project();second=copy.deepcopy(p.timeline[0]);second.id='second';second.start=1.35;second.duration=.2;p.timeline.append(second)
  with tempfile.TemporaryDirectory() as directory:
   before=copy.deepcopy(p.to_dict());group,sources=layers(p,p.timeline,directory);self.assertEqual(len(group),1);self.assertEqual(p.to_dict(),before)
   spec=next(iter(sources.values()));source=RawSource(spec);first=math.ceil(p.timeline[0].start*30-1e-7)
   try:
    for n in range(spec['frames']):
     at=(first+n)/30;image=QImage(160,284,QImage.Format_RGBA8888);image.fill(Qt.transparent);painter=QPainter(image)
     for item in p.timeline:
      if item.start<=at<item.start+item.duration:painter.drawImage(0,0,frame(p,item,(first+n-math.ceil(item.start*30-1e-7))/30))
     painter.end();pixels=np.frombuffer(image.constBits(),np.uint8).reshape(284,160,4)
     np.testing.assert_array_equal(source.frame(n/30),pixels)
    self.assertEqual(source.process.poll(),0)
   finally:source.close()

 def test_strict_enhanced_stream_uses_cached_pixels_and_rejects_missing_frames(self):
  from kinetic_cut import enhance
  from kinetic_cut.model import MediaItem
  from kinetic_cut.gpu_export import prepare_recipe
  from kinetic_cut.exporter import ExportPreset
  from PySide6.QtGui import QColor
  import shutil
  with tempfile.TemporaryDirectory() as directory:
   folder=Path(directory);path=folder/'source.png';picture=QImage(160,284,QImage.Format_RGB32);picture.fill(QColor('red'));picture.save(str(path))
   item=TimelineItem('enhanced','m','video_1',0,.2,transform=Transform(.5,.5),effects=[enhance.default_effect()])
   p=Project(settings=ProjectSettings(width=160,height=284,fps=10),media=[MediaItem('m',str(path),'image','image',1,160,284,10)],timeline=[item])
   root=enhance.cache_path(p,p.media[0],item,0);(root/'frames').mkdir(parents=True)
   for n,color in enumerate(('#113355','#7799bb')):
    picture.fill(QColor(color));picture.save(str(root/'frames'/f'{n:08d}.png'))
   (root/'info.json').write_text(json.dumps(dict(key=root.name,family=enhance.signature(p.media[0],item,0,10,False),source_start=0,frames=2,fps=10,backend='test')))
   try:
    job=prepare_recipe(p,ExportPreset('test','h264',10,192,''),folder,False,{},'unused',None,None)
    spec=next(iter(job['raw_sources'].values()));source=RawSource(spec)
    try:
     for n,color in enumerate(((17,51,85),(119,153,187))):
      pixels=source.frame(n/10);np.testing.assert_array_equal(pixels[142,80,:3],color)
    finally:source.close()
    (root/'frames/00000001.png').unlink();source=RawSource(spec)
    try:
     source.frame(0)
     with self.assertRaises(RuntimeError):source.frame(.1)
    finally:source.close()
   finally:shutil.rmtree(root);enhance._range_indexes.clear()

 def test_identical_opacity_keys_do_not_turn_long_holds_into_dense_animation(self):
  p=self.project();p.timeline[0].duration=8
  p.timeline[0].graphic_data['scene']['nodes'][0]['keyframes']['opacity']=[dict(time=0,value=0),dict(time=.12,value=100),dict(time=7.8,value=100),dict(time=8,value=0)]
  indices=samples(p,p.timeline[0],240)
  self.assertLess(len(indices),30);self.assertNotIn(120,indices)

 def test_implicit_rolling_and_typewriter_defaults_preserve_their_full_duration(self):
  p=self.project();i=p.timeline[0];node=i.graphic_data['scene']['nodes'][0]
  node.update(kind='text',text='12345',text_mode='rolling');self.assertIn(24,samples(p,i,36))
  i.duration=4;node.update(text='A'*50,text_mode='typewriter');self.assertIn(85,samples(p,i,120))

 def test_background_mask_stream_is_exact_and_missing_masks_are_fatal(self):
  from tests.test_vision_and_render import fixture
  from kinetic_cut.gpu_export import prepare_recipe
  from kinetic_cut.exporter import ExportPreset
  from kinetic_cut.preview_compositor import SceneContext,render
  from PySide6.QtCore import QRectF
  with tempfile.TemporaryDirectory() as directory:
   folder=Path(directory);media,item,analysis,_=fixture(folder);item.duration=.2;item.effects=[dict(name='Remove Person Background',analysis=analysis)]
   p=Project(settings=ProjectSettings(width=160,height=284,fps=10),media=[media],timeline=[item])
   job=prepare_recipe(p,ExportPreset('test','h264',10,192,''),folder,False,{},'unused',None,None)
   spec=next(iter(job['raw_sources'].values()));source=RawSource(spec);context=SceneContext(p,{},{},{},False,1.,draw_captions=False);context.transparent=True;context.strict_export=True
   try:
    for n in range(2):
     p.playhead=n/10;image,_,_=render(context,QRectF(0,0,160,284),(160,284),1.);image=image.convertToFormat(QImage.Format_RGBA8888)
     np.testing.assert_array_equal(source.frame(n/10),np.frombuffer(image.constBits(),np.uint8).reshape(284,160,4))
   finally:source.close()
   (Path(analysis['root'])/'masks/00000000.png').unlink();source=RawSource(spec)
   try:
    with self.assertRaises(RuntimeError):source.frame(0)
   finally:source.close()

 def test_private_producer_reports_errors_without_uncaught_exceptions(self):
  from kinetic_cut.export_preview_source import worker
  with tempfile.TemporaryDirectory() as directory:
   missing=Path(directory)/'missing.json';self.assertEqual(worker(missing),1)
   self.assertIn('FileNotFoundError',missing.with_suffix('.producer-error.log').read_text(encoding='utf-8'))
   self.assertEqual(worker(Path(directory)/'gone'/'missing.json'),1)
