"""Real Qt GPU pair pixels and inspector/history checks on disposable media."""
def preview_checks(window,out,check,wait):
 import copy,time
 import numpy as np
 from PySide6.QtCore import Qt,QRectF
 from PySide6.QtGui import QImage,QPainter,QColor
 from .model import Project,ProjectSettings,MediaItem,TimelineItem,Transform,Crop
 from .transitions import Transition
 from .animated_transitions import NAMES,CONTROLS
 from .preview_compositor import SceneContext,render
 original_size=window.size();images=[];media=[]
 for n in range(2):
  image=QImage(320,180,QImage.Format_RGBA8888);image.fill(QColor('#3975a2' if n==0 else '#b67b43'))
  paint=QPainter(image);paint.fillRect(20+n*60,30,100,100,QColor('#ed3945' if n==0 else '#4ac775'));paint.end()
  path=out/f'transition-{n}.png';image.save(str(path));images.append(image);media.append(MediaItem(str(n),str(path),'image','Transition source',4,320,180))
 a=TimelineItem('ta','0','video_1',0,2,transform=Transform(.5,.5,1));b=TimelineItem('tb','1','video_1',2,2,transform=Transform(.5,.5,1))
 trans=Transition('transition','Wave Sweep',track='video_1',start=1.5,duration=1,left_item_id=a.id,right_item_id=b.id)
 project=Project(settings=ProjectSettings(320,180,60),media=media,timeline=[a,b],transitions=[trans])
 window.set_project(project);window.preview.set_transform_controls_visible(False)
 def parity(label,at=2):
  window.project.touch();window.transport.sync(True);window.seek(at)
  gpu=window.preview.gpu;previous=gpu.frames;gpu.signature=None;gpu.schedule();deadline=time.monotonic()+8
  while gpu.frames<=previous and time.monotonic()<deadline:wait(40)
  wait(200);frame=window.preview.composition_rect()
  actual=gpu.view.grabWindow().copy(frame.toRect()).convertToFormat(QImage.Format_RGBA8888)
  check(label+' presents a GPU frame',not actual.isNull())
  context=SceneContext(copy.deepcopy(window.project),{},{},{},True,1.)
  expected,_,_=render(context,frame,(window.preview.width(),window.preview.height()),1.)
  expected=expected.copy(frame.toRect()).convertToFormat(QImage.Format_RGBA8888)
  pixels=np.frombuffer(actual.constBits(),np.uint8).reshape(actual.height(),actual.width(),4).astype(float)
  reference=np.frombuffer(expected.constBits(),np.uint8).reshape(expected.height(),expected.width(),4).astype(float)
  error=float(np.abs(pixels[:,:,:3]-reference[:,:,:3]).mean())
  actual.save(str(out/(label+'-gpu.png')));expected.save(str(out/(label+'-reference.png')))
  check(label+f' paired GPU parity ({error:.2f})',error<5)
  # Transitions must not turn supported video sources into CPU decode islands.
  check(label+' keeps supported sources GPU eligible',not gpu.cpu_media('0') and not gpu.cpu_media('1'))
 for name in NAMES:
  trans.name=name;trans.properties={};parity('transition-'+name.replace(' ','-'))
 trans.name='Explosion';trans.properties={}
 a.transform=Transform(.35,.6,.65,rotation=17,flip_horizontal=True);a.crop=Crop(.1,.1,.8,.8);a.opacity=65
 b.transform=Transform(.6,.45,.8,rotation=-10);b.opacity=80
 for at in (1.5,1.7,2.2,1.8,2.48):parity('transition-transformed-'+str(at),at)
 project.video_tracks=['under','video_1'];project.track_states['under']={'visible':True,'muted':False,'locked':False}
 under=TimelineItem('under','1','under',0,4,transform=Transform(.5,.5,1));project.timeline.append(under)
 parity('transition-transparent-over-colour',2)
 project.timeline.remove(under);project.video_tracks=['video_1']
 a.transform=b.transform=Transform(.5,.5,1);a.crop=Crop();a.opacity=b.opacity=100
 window.timeline.selected_transition_id=trans.id;window.inspector.select_transition(trans.id)
 for name in NAMES:
  trans.name=name;window.inspector.refresh_transition(trans)
  check(name+' exposes its specific controls',set(window.inspector.animated_trans_rows)=={r[0] for r in CONTROLS[name]})
 for theme in ('default','final_cut_obsidian','ableton_gray'):
  window.apply_theme(theme,save=False);window.resize(1280,800);wait(100)
  window.inspector.grab().save(str(out/f'transition-inspector-{theme}.png'))
  check('transition controls visible '+theme,window.inspector.sec_animated_trans.isVisible())
 window.apply_theme('default',save=False);window.resize(original_size);wait(150)

def export_checks(out,check):
 """Decoded H264 pair output, all modes; unencoded Qt parity is checked above."""
 import numpy as np,av
 from PySide6.QtGui import QImage
 from .model import Project,ProjectSettings,MediaItem,TimelineItem,Transform
 from .transitions import Transition
 from .animated_transitions import NAMES,composite
 from .creative_effects import default_effect,apply
 from .gpu_export import recipe,render_native,mux_command
 from .exporter import ExportPreset
 from .export_process import render
 directory=out/'paired-transitions';directory.mkdir(exist_ok=True);w,h=240,160;y,x=np.mgrid[:h,:w];images=[];media=[];results=[]
 for n in range(2):
  pixels=np.stack((40+100*x/w+n*50,50+90*y/h+n*45,np.full_like(x,160-n*90),np.full_like(x,255)),axis=-1).astype(np.uint8)
  image=QImage(pixels.data,w,h,w*4,QImage.Format_RGBA8888).copy();path=directory/f'source-{n}.png';image.save(str(path));images.append(image)
  media.append(MediaItem(str(n),str(path),'image','Paired source',2,w,h))
 project=Project(settings=ProjectSettings(w,h,30),media=media,timeline=[TimelineItem('a','0','video_1',0,1,transform=Transform(.5,.5,1)),TimelineItem('b','1','video_1',1,1,transform=Transform(.5,.5,1))])
 preset=ExportPreset('Paired checks','h264',20,192,'','bitrate')
 for index,label in enumerate((*NAMES,'paired-alpha-background','paired-clock-fade')):
  name=label if label in NAMES else 'Wave Sweep'
  folder=directory/f'{index+1:02d}';folder.mkdir(exist_ok=True)
  project.video_tracks=['video_1'];project.timeline=project.timeline[:2]
  for item in project.timeline:item.effects=[];item.opacity=100;item.fade_in=item.fade_out=0
  if label=='paired-alpha-background':
   project.video_tracks=['under','video_1'];project.track_states['under']={'visible':True,'muted':False,'locked':False}
   project.timeline.append(TimelineItem('under','0','under',0,2,transform=Transform(.5,.5,1)))
   project.timeline[0].opacity=60;project.timeline[1].opacity=75
  if label=='paired-clock-fade':
   project.timeline[0].effects=[default_effect('Color Flash',project.timeline[0])];project.timeline[0].fade_out=.4
   project.timeline[1].effects=[default_effect('Color Tint',project.timeline[1])];project.timeline[1].fade_in=.4
  trans=Transition('pair',name,track='video_1',start=.5,duration=1,left_item_id='a',right_item_id='b');project.transitions=[trans]
  job=recipe(project,preset,folder,False);status=render_native(job,folder)
  target=folder/'pair.mp4';code,tail=render(mux_command(project,job,str(target),preset,'ffmpeg',False),2);check(label+' pair export completes',code==0 and status['state']=='Complete')
  errors=[];frames=0
  with av.open(str(target)) as movie:
   for n,frame in enumerate(movie.decode(video=0)):
    frames+=1
    if n not in (15,21,30,39,44,45):continue
    sides=[]
    for image,item in zip(images,project.timeline[:2]):
     t=min(max(0,n/30-item.start),item.duration-1/30)
     for effect in item.effects:image=apply(image,effect,t)
     data=np.frombuffer(image.constBits(),np.uint8).reshape(h,w,4).copy()
     fade=min(1,max(0,t/item.fade_in)) if item.fade_in else 1
     if item.fade_out:fade*=min(1,max(0,(item.duration-t)/item.fade_out))
     data[:,:,3]=np.floor(data[:,:,3].astype(np.float32)*item.opacity/100*fade+.5).astype(np.uint8)
     sides.append(QImage(data.data,w,h,w*4,QImage.Format_RGBA8888).copy())
    reference=composite(*sides,trans,trans.progress(n/30),(w,h)).convertToFormat(QImage.Format_RGBA8888)
    pixels=np.frombuffer(reference.constBits(),np.uint8).reshape(h,w,4).astype(float)
    alpha=pixels[:,:,3:4]/255;expected=pixels[:,:,:3]*alpha
    if label=='paired-alpha-background':expected+=np.frombuffer(images[0].constBits(),np.uint8).reshape(h,w,4)[:,:,:3]*(1-alpha)
    actual=frame.to_ndarray(format='rgb24').astype(float)
    errors.append(float(np.abs(actual-expected).mean()))
    if n==30:frame.to_image().save(folder/'middle.jpg');reference.save(str(folder/'reference.png'))
  check(label+' pair export preserves frame count',frames==60)
  check(label+' decoded pair pixels match shared maps',max(errors)<4)
  results.append(dict(name='transition-'+label,mean_pixel_error=float(np.mean(errors)),max_sample_error=max(errors),diagnostics=status))
 return results
