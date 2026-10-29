"""Pair recipe construction and exact, temporary compatibility preparation."""
import copy,math
from .animated_transitions import NAMES,descriptor

def exact_names():
 """Legacy motion/wipe compositors cannot be represented by a generic fade."""
 from .transitions import TRANSITION_SET
 return TRANSITION_SET

def legacy_frame(project,transition,images,size):
 """Use the actual preview's crop-local/pivot compositing, without a widget."""
 from PySide6.QtGui import QImage,QPainter
 from PySide6.QtCore import Qt,QRectF
 from .preview_compositor import SceneContext
 frames={key:image for key,image in zip((transition.left_item_id,transition.right_item_id),images) if key and image is not None}
 context=SceneContext(project,frames,{key:key for key in frames},{},False,1.,draw_captions=False)
 image=QImage(*size,QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
 painter=QPainter(image);painter.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform)
 try:context._draw_layer_transition(painter,transition.track,transition,QRectF(0,0,*size))
 finally:painter.end()
 return image

def configure_layers(project,layers,error):
 """Add bounded pair passes without changing the document or source clocks."""
 new=[t for t in project.transitions if t.name in NAMES and t.track in project.video_tracks and project.track_states.get(t.track,{}).get('visible',True)]
 if not new:
  from .legacy_transition_gpu import configure_layers as legacy
  return legacy(project,layers,error)
 by_id={v['id']:v for v in layers};pairs=[]
 for trans in new:
  if any(t is not trans and t.track==trans.track and t.start<trans.end and t.end>trans.start for t in project.transitions):raise error('overlapping transition windows')
  data=descriptor(trans)
  for side,identifier in enumerate((trans.left_item_id,trans.right_item_id)):
   original=project.item_by_id(identifier) if identifier else None
   if original and (original.muted or original.track!=trans.track):raise error('muted or mismatched transition endpoint')
   source=by_id.get(identifier)
   if identifier and not source:raise error('transition endpoint requires exact preparation')
   layer=copy.deepcopy(source) if source else dict(path='',empty=True,still=True,cpu=False,size=[2,2],crop=[0,0,1,1],box=[0,0,project.settings.width,project.settings.height],opacity=1.,operations=[],clock='',in_point=0,speed=1)
   if source:source.setdefault('skip_ranges',[]).append([trans.start,trans.end])
   layer.update(id='__transition_'+trans.id+'_'+str(side),track=trans.track,start=trans.start,end=trans.end,transitions=[],skip_ranges=[],
       pair=dict(id=trans.id,side=side,start=trans.start,duration=trans.duration,**data),
       source_origin=original.start if original else trans.start,source_in=source['in_point'] if source else 0,
       source_duration=original.duration if original else trans.duration,source_speed=original.speed if original else 1,
       effect_origin=original.start if original else trans.start)
   # Geometry streams are indexed by absolute output frame, not pair-window start.
   pairs.append(layer)
 order={t:n for n,t in enumerate(project.video_tracks)}
 from .legacy_transition_gpu import configure_layers as legacy
 return legacy(project,sorted([*layers,*pairs],key=lambda v:(order.get(v.get('track'),0),bool(v.get('pair')),v.get('pair',{}).get('start',v['start']),v.get('pair',{}).get('side',0))),error)

def prepare(project,directory,preset,ffmpeg,prepared,progress,cancel):
 """Raster only unsupported pair windows; all files belong to this export job."""
 names=exact_names()
 transitions=[t for t in project.transitions if t.name in names and t.track in project.video_tracks and project.track_states.get(t.track,{}).get('visible',True)]
 if not transitions:return project
 import av,numpy as np,shutil
 from pathlib import Path
 from fractions import Fraction
 from PySide6.QtGui import QImage,QPainter
 from PySide6.QtCore import Qt,QRectF
 from .rendergraph import command
 from .export_process import render
 from .gpu_export_decode import Source
 from .animated_transitions import composite
 from .model import MediaItem,TimelineItem,Transform
 directory=Path(directory)/'paired-transitions';directory.mkdir(exist_ok=True)
 stage=copy.deepcopy(project);stage.transitions=[t for t in stage.transitions if t.name not in names]
 stage._transition_exclusions=copy.deepcopy(getattr(project,'_transition_exclusions',{}))
 fps=project.settings.fps;width=project.settings.width;height=project.settings.height
 def check():
  if cancel and cancel.is_set():raise RuntimeError('Export cancelled. Transition processing stopped safely.')
  if shutil.disk_usage(directory).free<256*1024**2:raise RuntimeError('Not enough free space for exact transition preparation')
 for number,trans in enumerate(transitions):
  check();sides=[];paths=[]
  first=math.ceil(trans.start*fps-1e-7);last=math.ceil(trans.end*fps-1e-7)
  if first>=last:continue
  try:
   for side,identifier in enumerate((trans.left_item_id,trans.right_item_id)):
    item=project.item_by_id(identifier) if identifier else None
    if not item or item.muted:sides.append(None);continue
    low=min(max(first/fps,item.start),max(item.start,item.start+item.duration-1/fps))
    high=max(low+1/fps,min(last/fps,item.start+item.duration))
    if trans.name not in NAMES:
     media=project.media_by_id(item.media_id)
     if media.kind=='image':sides.append((None,low,item));continue
     sides.append((Source(media.path,item.in_point+(low-item.start)*item.speed),low,item));continue
    one=copy.copy(project);one.timeline=[item];one.transitions=[];one.captions=[]
    path=directory/f'{number}-{side}.mkv';paths.append(path)
    args=command(one,str(path),preset,False,'CPU',ffmpeg,None,False,prepared,window=(low,high),transparent=True)
    args=args[:args.index('-c:v')]+['-c:v','ffv1','-level','3','-pix_fmt','bgra','-threads','2','-frames:v',str(max(1,math.ceil((high-low)*fps-1e-7))),'-progress','pipe:1','-nostats',str(path)]
    code,tail=render(args,high-low,None,cancel)
    if code:raise RuntimeError('Transition source preparation failed:\n'+'\n'.join(tail)[-3000:])
    sides.append((Source(str(path),0),low,item))
   target=directory/f'transition-{number}.mkv'
   with av.open(str(target),'w') as movie:
    stream=movie.add_stream('ffv1',rate=Fraction(str(fps)));stream.width=width;stream.height=height;stream.pix_fmt='bgra';stream.options={'level':'3','threads':'2'}
    for n in range(last-first):
     check();at=(first+n)/fps;images=[]
     for side in sides:
      if side is None:images.append(None);continue
      reader,low,item=side;seconds=max(0,min(at,item.start+item.duration-1/fps)-low)
      if trans.name not in NAMES:
       if reader is None:images.append(QImage(project.media_by_id(item.media_id).path));continue
       seconds=item.in_point+(low-item.start+seconds)*item.speed
      data=reader.frame(seconds);h,w=data.shape[:2];images.append(QImage(data.data,w,h,w*4,QImage.Format_RGBA8888).copy())
     if trans.name in NAMES:image=composite(*images,trans,trans.progress(at),(width,height))
     else:
      view=copy.copy(project);view.playhead=at
      image=legacy_frame(view,trans,images,(width,height))
     image=image.convertToFormat(QImage.Format_RGBA8888)
     pixels=np.frombuffer(image.constBits(),np.uint8).reshape(height,image.bytesPerLine()//4,4)[:,:width].copy()
     frame=av.VideoFrame.from_ndarray(pixels,format='rgba');frame.pts=n
     for packet in stream.encode(frame):movie.mux(packet)
     if n%15==0 and progress:progress(0,f'Preparing {trans.name} · {n/fps:.1f}s / {(last-first)/fps:.1f}s')
    for packet in stream.encode():movie.mux(packet)
   identifier='__paired_transition_'+trans.id
   stage.media.append(MediaItem(identifier,str(target),'video',trans.name,(last-first)/fps,width,height,fps,has_alpha=True))
   stage.timeline.append(TimelineItem(identifier,identifier,trans.track,first/fps,(last-first)/fps,transform=Transform(.5,.5,1)))
   for identifier in (trans.left_item_id,trans.right_item_id):
    if identifier:stage._transition_exclusions.setdefault(identifier,[]).append((first/fps,last/fps))
  finally:
   for side in sides:
    if side and side[0]:side[0].close()
   for path in paths:path.unlink(missing_ok=True)
 return stage
