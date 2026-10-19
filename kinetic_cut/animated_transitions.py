"""Paired-image transition maps shared by Qt, D3D11 and CPU compatibility.

Maps are evaluated in canvas space after each clip's ordinary effect/transform
stack. They return two sampling coordinates and an incoming-image weight.
No wall-clock randomness: the same timestamp always gives the same picture.
"""
import math
from .finishing_effects import (E,ref,node,sin,cos,floor,abs_,sqrt,minimum,maximum,
    clamp,mix,power,fract,choose,gt,smooth,hash_noise,emit)

CATEGORIES={
 'Distortion & Flow':['Wave Sweep','Liquid Ripple','Swirl Blend','Vortex Zoom','Fluid Melt','Prism Zoom','Lens Ripple','Heat Haze'],
 'Pieces & Particles':['Puzzle Assemble','Puzzle Scatter','Explosion','Shard Burst','Tile Flip','Domino Reveal','Pixel Dissolve','Mosaic Reveal'],
 'Geometric Reveals':['Circle Iris','Diamond Iris','Star Iris','Venetian Blinds','Chevron Sweep','Diagonal Sweep','Hexagon Reveal','Pinwheel'],
}
NAMES=tuple(n for group in CATEGORIES.values() for n in group)
DESCRIPTIONS=dict(zip(NAMES,[
 'A flowing wave sweeps the next shot into view.',
 'Concentric water ripples bend both shots through the cut.',
 'A rotating optical swirl blends the outgoing and incoming scenes.',
 'Pull both shots into a spinning central vortex.',
 'The outgoing image melts into uneven, flowing columns.',
 'A prismatic zoom bends the scene towards the next shot.',
 'A travelling circular lens distorts the image around its reveal edge.',
 'Animated heat shimmer carries one shot into the next.',
 'The incoming video forms interlocking jigsaw pieces that fly together, rotate and connect.',
 'Interlocking pieces of the outgoing video fly apart to uncover the next scene.',
 'Image tiles fly outwards, rotate and shrink to reveal the next shot.',
 'Triangular image fragments burst apart around the chosen centre.',
 'Staggered tiles flip through their narrow edge into the next image.',
 'Rows of tiles turn over in a cascading domino wave.',
 'Deterministic scattered blocks reveal the incoming scene.',
 'Large mosaic cells resolve into the incoming image.',
 'A soft circular aperture opens onto the next shot.',
 'An adjustable diamond aperture opens from the chosen centre.',
 'A rotating star-shaped aperture reveals the incoming shot.',
 'Parallel slats open in a coordinated reveal.',
 'A chevron-shaped edge sweeps across the image.',
 'An angled soft edge sweeps into the next shot.',
 'Staggered hexagonal cells reveal the next image.',
 'Rotating radial blades sweep the next scene into view.',
]))
# key,label,min,max,default,step. The six uniform slots are stable on every backend.
BASE=[('amount','Amount',0,2,1,.05),('detail','Detail',2,32,8,1),('seed','Pattern seed',0,100,0,1),
      ('center_x','Centre X',0,1,.5,.01),('center_y','Centre Y',0,1,.5,.01),('angle','Angle (degrees)',-180,180,0,1)]
CONTROL_SLOTS=[(0,1),(0,1,3,4),(0,3,4),(0,3,4),(0,1,2),(0,3,4),(0,1,3,4),(0,1),
 (0,1,2),(0,1,2),(0,1,2,3,4,5),(0,1,2,3,4,5),(1,2),(1,),(1,2),(0,1),
 (0,3,4),(0,3,4,5),(0,1,3,4,5),(0,1,5),(0,4),(0,5),(1,2),(0,1,3,4,5)]
CONTROLS={name:[BASE[n] for n in slots] for name,slots in zip(NAMES,CONTROL_SLOTS)}
CONTROL_LABELS={
 'Wave Sweep':('Wave depth','Wave frequency'),'Liquid Ripple':('Ripple depth','Ripple frequency'),
 'Swirl Blend':('Twist',''),'Vortex Zoom':('Vortex strength',''),'Fluid Melt':('Melt depth','Flow columns'),
 'Prism Zoom':('Zoom strength',''),'Lens Ripple':('Lens strength','Ripple frequency'),'Heat Haze':('Shimmer depth','Shimmer frequency'),
 'Puzzle Assemble':('Piece travel','Piece density'),'Puzzle Scatter':('Piece travel','Piece density'),
 'Explosion':('Burst distance','Tile density'),'Shard Burst':('Burst distance','Shard density'),
 'Tile Flip':('','Tile density'),'Domino Reveal':('','Row density'),'Pixel Dissolve':('','Block density'),
 'Mosaic Reveal':('Pixelation','Cell density'),'Circle Iris':('Feather',''),'Diamond Iris':('Feather',''),
 'Star Iris':('Feather','Star points'),'Venetian Blinds':('Feather','Slats'),'Chevron Sweep':('Feather',''),
 'Diagonal Sweep':('Feather',''),'Hexagon Reveal':('','Cell density'),'Pinwheel':('Feather','Blade density'),
}
CONTROLS={name:[(key,CONTROL_LABELS[name][0 if key=='amount' else 1] if key in ('amount','detail') else label,lo,hi,default,step)
                for key,label,lo,hi,default,step in rows] for name,rows in CONTROLS.items()}

def values(properties):
 result=[]
 for key,_,lo,hi,default,_ in BASE:
  try:value=float((properties or {}).get(key,default))
  except (ValueError,TypeError,OverflowError):value=default
  result.append(min(hi,max(lo,value)) if math.isfinite(value) else default)
 result[1]=round(result[1]);result[2]=round(result[2])
 return result

def defaults(name):
 return dict(easing='Ease In-Out',**{r[0]:r[4] for r in BASE})

def descriptor(transition):
 from .transitions import apply_easing
 return dict(mode=NAMES.index(transition.name)+1,params=values(transition.properties),
             easing=(transition.properties or {}).get('easing','Ease In-Out'))

U,V,T=ref('u'),ref('v'),ref('t')
P=[ref('p'+str(n)) for n in range(6)]
ASPECT=ref('aspect');PI=math.pi
def atan(y,x):return node('atan2',y,x)
def step(a,b):return choose(gt(b,a),1,0)
def rotate(x,y,a):return x*cos(a)-y*sin(a),x*sin(a)+y*cos(a)
def noise(x,y):return hash_noise(x,y,P[2])+.5
def reveal(threshold,feather=.025):return smooth(threshold-feather,threshold+feather,T*1.1-.05)

def graph(name):
 amount,detail,seed,cx,cy,angle=P
 x=(U-cx)*ASPECT;y=V-cy;r=sqrt(x*x+y*y+.00000001);a=atan(y,x)
 peak=sin(T*PI);turn=angle*PI/180
 au,av,bu,bv,w=U,V,U,V,T
 if name=='Wave Sweep':
  edge=U+.06*amount*sin(V*detail+T*PI*2)*peak
  w=reveal(edge);au=U+.045*amount*peak*sin(V*detail+T*8);bu=U-.045*amount*peak*sin(V*detail+T*8)
 elif name in ('Liquid Ripple','Lens Ripple'):
  wave=sin(r*detail*5-T*12)*peak*amount*.035
  if name=='Lens Ripple':
   ring=T*1.4-.1;wave=wave*(1-smooth(.02,.2,abs_(r-ring)));w=reveal(r/1.2)
  au=U+x/maximum(.01,r)/ASPECT*wave;av=V+y/maximum(.01,r)*wave
  bu=U-x/maximum(.01,r)/ASPECT*wave;bv=V-y/maximum(.01,r)*wave
 elif name in ('Swirl Blend','Vortex Zoom'):
  twist=peak*amount*(1-clamp(r))*PI*(2 if name=='Vortex Zoom' else .65)
  zoom=1+peak*amount*(2 if name=='Vortex Zoom' else .1)
  ax,ay=rotate(x/zoom,y/zoom,twist);bx,by=rotate(x/zoom,y/zoom,-twist)
  au,av=cx+ax/ASPECT,cy+ay;bu,bv=cx+bx/ASPECT,cy+by
 elif name=='Fluid Melt':
  edge=V+.14*amount*sin(U*detail+seed)*peak+.05*sin(U*detail*2.7)
  w=reveal(edge,.04);av=V-T*.12*amount*peak;bv=V+(1-T)*.12*amount*peak
 elif name=='Prism Zoom':
  zoom=1+peak*amount*2;au,av=cx+x/ASPECT/zoom,cy+y/zoom
  bx,by=rotate(x/zoom,y/zoom,peak*amount*.15);bu,bv=cx+bx/ASPECT,cy+by
 elif name=='Heat Haze':
  dx=amount*peak*.025*(sin(V*detail*2+T*17)+sin(V*detail*3-T*11))
  au=U+dx;bu=U-dx;av=V+.01*amount*peak*sin(U*detail+T*8);bv=V-.01*amount*peak*sin(U*detail+T*8)
 elif name in ('Puzzle Assemble','Puzzle Scatter'):
  cols=maximum(2,floor(detail*.75));rows=maximum(2,floor(cols/ASPECT))
  phase=T if name=='Puzzle Assemble' else 1-T
  spread=1+power(1-phase,2)*amount*2.4
  cell_x=floor(((U-.5)/spread+.5)*cols);cell_y=floor(((V-.5)/spread+.5)*rows)
  coverage=U*0;sample_u=U;sample_v=V
  # Inverse-project the nearby physical pieces. Tabs cross cell boundaries;
  # testing the 3x3 neighbourhood lets them move and rotate as real cut-outs,
  # rather than sliding footage behind a stationary jigsaw mask.
  for dy in (-1,0,1):
   for dx in (-1,0,1):
    ix=cell_x+dx;iy=cell_y+dy;ox=(ix+.5)/cols;oy=(iy+.5)/rows
    local_phase=clamp((phase-noise(ix,iy)*.3)/.7);remaining=1-local_phase
    twist=(noise(ix+17,iy)-.5)*remaining*amount
    scale=maximum(.2,1-remaining*amount*.45)
    lx=(U-(.5+(ox-.5)*spread))*cols;ly=(V-(.5+(oy-.5)*spread))*rows
    lx,ly=rotate(lx,ly,-twist);lx=lx/scale;ly=ly/scale
    body=(1-smooth(.495,.505,abs_(lx)))*(1-smooth(.495,.505,abs_(ly)))
    circles=U*0
    for ex,ey,valid in ((-.5,0,step(0,ix)),(.5,0,step(ix,cols-1)),(0,-.5,step(0,iy)),(0,.5,step(iy,rows-1))):
     circle=(1-smooth(.168,.18,sqrt(power(lx+(-ex),2)+power(ly+(-ey),2))))*valid
     circles=maximum(circles,circle)
    tab=gt(fract((ix+iy)*.5),.25)
    shape=choose(tab,maximum(body,circles),body*(1-circles))
    inside=step(-1,ix)*step(ix,cols)*step(-1,iy)*step(iy,rows)
    cover=shape*inside*smooth(0,.15,local_phase)
    use=gt(cover,coverage);sample_u=choose(use,ox+lx/cols,sample_u);sample_v=choose(use,oy+ly/rows,sample_v);coverage=maximum(coverage,cover)
  if name=='Puzzle Assemble':bu,bv,w=sample_u,sample_v,coverage
  else:au,av,w=sample_u,sample_v,1-coverage
 elif name in ('Explosion','Shard Burst'):
  cols=detail;rows=maximum(2,floor(cols/ASPECT));spread=1+T*T*amount*5
  gx=(U-cx)/spread+cx;gy=(V-cy)/spread+cy;ix=floor(gx*cols);iy=floor(gy*rows)
  ox=(ix+.5)/cols;oy=(iy+.5)/rows
  px=cx+(ox-cx)*spread;py=cy+(oy-cy)*spread
  lx=(U-px)*cols;ly=(V-py)*rows
  twist=(noise(ix,iy)-.5)*T*amount*6+turn*T
  lx,ly=rotate(lx,ly,twist);shrink=maximum(.02,1-T*.9)
  lx,ly=lx/shrink,ly/shrink;au=ox+lx/cols;av=oy+ly/rows
  cover=step(abs_(lx),.5)*step(abs_(ly),.5)
  if name=='Shard Burst':cover=cover*mix(1,step(lx+ly,.48),smooth(0,.18,T))
  cover=cover*(1-smooth(.65,1,T));w=1-cover
 elif name in ('Tile Flip','Domino Reveal'):
  cols=detail;rows=maximum(2,floor(detail/ASPECT));ix=floor(U*cols);iy=floor(V*rows)
  delay=noise(ix,iy)*.45 if name=='Tile Flip' else (iy/rows)*.45
  phase=clamp((T-delay)/.55);squeeze=maximum(.025,abs_(cos(phase*PI)))
  bu=(ix+.5+(fract(U*cols)-.5)/squeeze)/cols;au=bu
  cover=step(abs_(fract(U*cols)-.5),squeeze*.5)
  # The edge briefly exposes the next image rather than an opaque black tile.
  w=choose(gt(phase,.5),1,1-cover)
 elif name=='Pixel Dissolve':w=reveal(noise(floor(U*detail),floor(V*detail/ASPECT)),.015)
 elif name=='Mosaic Reveal':
  cells=maximum(2,detail/(maximum(.02,peak)*2));bu=(floor(U*cells)+.5)/cells;bv=(floor(V*cells/ASPECT)+.5)/(cells/ASPECT)
  bu=mix(U,bu,peak*amount*.5);bv=mix(V,bv,peak*amount*.5);w=smooth(.15,.85,T)
 elif name=='Circle Iris':
  extent=sqrt(power(maximum(cx,1-cx)*ASPECT,2)+power(maximum(cy,1-cy),2))
  w=reveal(r/maximum(.1,extent),.015+.025*amount)
 elif name=='Diamond Iris':
  dx,dy=rotate(x,y,turn);w=reveal((abs_(dx)+abs_(dy))/maximum(.1,ASPECT+1),.015+.025*amount)
 elif name=='Star Iris':
  spokes=maximum(3,floor(detail));edge=r/(.75+.22*cos((a+turn+T*.25)*spokes));w=reveal(edge/maximum(1,ASPECT),.02+.02*amount)
 elif name=='Venetian Blinds':w=reveal(fract((U*cos(turn)+V*sin(turn))*detail),.015+.025*amount)
 elif name=='Chevron Sweep':w=reveal((U+.4*abs_(V-cy))/(1.4),.015+.025*amount)
 elif name=='Diagonal Sweep':
  dx=U*cos(turn+PI/4)+V*sin(turn+PI/4);bound=maximum(.1,abs_(cos(turn+PI/4))+abs_(sin(turn+PI/4)))
  w=reveal((dx-minimum(0,cos(turn+PI/4))-minimum(0,sin(turn+PI/4)))/bound,.015+.025*amount)
 elif name=='Hexagon Reveal':
  gx=U*detail*ASPECT;gy=V*detail;row=floor(gy/.8660254);best=ref('p0')*0+100;owner_x=U*0;owner_y=V*0
  for dy in (0,1):
   ry=row+dy;offset=fract(ry*.5);col=floor(gx-offset)
   for dx in (0,1):
    ix=col+dx;distance=power(gx-ix-offset,2)+power(gy-ry*.8660254,2);near=gt(best,distance)
    owner_x=choose(near,ix,owner_x);owner_y=choose(near,ry,owner_y);best=minimum(best,distance)
  w=reveal(noise(owner_x,owner_y),.025)
 elif name=='Pinwheel':w=reveal(fract((a+turn)/(2*PI)*maximum(2,floor(detail*.5))),.015+.025*amount)
 # Enforce exact endpoints independently of every spatial mask/soft edge.
 w=choose(gt(T,.999999),1,choose(gt(.000001,T),0,w))
 au=choose(gt(.000001,T),U,au);av=choose(gt(.000001,T),V,av)
 bu=choose(gt(T,.999999),U,bu);bv=choose(gt(T,.999999),V,bv)
 return (au,av,bu,bv,clamp(w))

GRAPHS={n:graph(n) for n in NAMES}

def shader_map(name,backend):
 graph=GRAPHS[name];bindings={};lines=[]
 def bind(e):
  if e.op in ('const','ref') or e in bindings:return
  for child in e.args:bind(child)
  code=emit(e,backend,bindings=bindings);key='t'+str(len(bindings));bindings[e]=key
  lines.append(('bool' if e.op=='gt' else 'float')+' '+key+'='+code+';')
 for e in graph:bind(e)
 outputs=[emit(e,backend,bindings=bindings) for e in graph]
 vector='vec2' if backend=='glsl' else 'float2'
 lines+=['uvA='+vector+'('+','.join(outputs[:2])+');','uvB='+vector+'('+','.join(outputs[2:4])+');','weight='+outputs[4]+';']
 return '\n'.join(lines)

def maps(name,width,height,params,progress,row_start=0,row_count=None):
 import numpy as np
 rows=height if row_count is None else row_count
 context=dict(u=(np.arange(width,dtype=np.float32)[None,:]+.5)/width,v=(np.arange(row_start,row_start+rows,dtype=np.float32)[:,None]+.5)/height,t=np.float32(progress),aspect=np.float32(width/height))
 context.update({'p'+str(n):np.float32(v) for n,v in enumerate(params)})
 cache={};uses={};seen=set()
 def visit(e):
  if e in seen:return
  seen.add(e)
  if e.op in ('const','ref'):return
  for child in e.args:uses[child]=uses.get(child,0)+1;visit(child)
 for e in GRAPHS[name]:uses[e]=uses.get(e,0)+1;visit(e)
 def release(e):
  uses[e]-=1
  if uses[e]==0:cache.pop(e,None)
 def run(e):
  if e in cache:return cache[e]
  if e.op=='const':r=np.float32(e.args[0])
  elif e.op=='ref':r=context[e.args[0]]
  else:
   args=[run(v) for v in e.args]
   operations={'+':np.add,'-':np.subtract,'*':np.multiply,'/':np.divide,'pow':np.power,'sin':np.sin,'cos':np.cos,'floor':np.floor,'abs':np.abs,'sqrt':np.sqrt,'min':np.minimum,'max':np.maximum,'gt':np.greater,'if':np.where,'atan2':np.arctan2}
   if e.op in ('xor16','mul16'):
    x,y=((np.asarray(a).astype(np.int64)&65535).astype(np.uint32) for a in args)
    r=((np.bitwise_xor(x,y) if e.op=='xor16' else x*y)&65535).astype(np.float32)
   else:r=operations[e.op](*args)
   for child in e.args:release(child)
  cache[e]=r;return r
 out=[]
 for e in GRAPHS[name]:out.append(np.broadcast_to(run(e),(rows,width)));release(e)
 return out

def composite(a,b,transition,progress,size):
 """Return premultiplied QImage; missing sides are transparent, never black."""
 import numpy as np
 from PySide6.QtCore import Qt
 from PySide6.QtGui import QImage
 from .transitions import apply_easing
 w,h=size
 phase=apply_easing(progress,(transition.properties or {}).get('easing','Ease In-Out'))
 if phase<=0 or phase>=1:
  image=a if phase<=0 else b
  if image is not None and not image.isNull():return image.scaled(w,h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation).convertToFormat(QImage.Format_RGBA8888_Premultiplied)
  image=QImage(w,h,QImage.Format_RGBA8888_Premultiplied);image.fill(Qt.transparent);return image
 def pixels(image):
  if image is None or image.isNull():return np.zeros((h,w,4),np.float32)
  image=image.scaled(w,h,Qt.IgnoreAspectRatio,Qt.SmoothTransformation).convertToFormat(QImage.Format_RGBA8888_Premultiplied)
  return np.frombuffer(image.constBits(),np.uint8).reshape(h,image.bytesPerLine())[:,:w*4].reshape(h,w,4).astype(np.float32)
 def sample(data,u,v):
  x=np.clip(u*w-.5,0,w-1);y=np.clip(v*h-.5,0,h-1);x0=np.floor(x).astype(np.int32);y0=np.floor(y).astype(np.int32);x1=np.minimum(x0+1,w-1);y1=np.minimum(y0+1,h-1);fx=(x-x0.astype(np.float32))[...,None];fy=(y-y0.astype(np.float32))[...,None]
  return (data[y0,x0]*(1-fx)+data[y0,x1]*fx)*(1-fy)+(data[y1,x0]*(1-fx)+data[y1,x1]*fx)*fy
 source_a,source_b=pixels(a),pixels(b);result=np.empty((h,w,4),np.uint8);params=values(transition.properties)
 for start in range(0,h,64):
  count=min(64,h-start);ua,va,ub,vb,m=maps(transition.name,w,h,params,phase,start,count)
  result[start:start+count]=np.clip(np.floor(sample(source_a,ua,va)*(1-m[...,None])+sample(source_b,ub,vb)*m[...,None]+.5),0,255).astype(np.uint8)
 return QImage(result.data,w,h,w*4,QImage.Format_RGBA8888_Premultiplied).copy()
