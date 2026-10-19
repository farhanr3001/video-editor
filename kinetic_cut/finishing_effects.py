"""One expression graph per effect, evaluated identically on GPU and CPU.

Sampling coordinates are normalized to the cropped layer, before its transform.
Spatial effects retain the layer's alpha silhouette and use clamped borders.
"""
from dataclasses import dataclass,field
import math

@dataclass(frozen=True)
class E:
    op: str
    args: tuple
    _hash: int = field(init=False,compare=False,repr=False)
    def __post_init__(s):object.__setattr__(s,'_hash',hash((s.op,s.args)))
    def __hash__(s):return s._hash
    def __add__(s,v):return node('+',s,v)
    def __radd__(s,v):return node('+',v,s)
    def __sub__(s,v):return node('-',s,v)
    def __rsub__(s,v):return node('-',v,s)
    def __mul__(s,v):return node('*',s,v)
    def __rmul__(s,v):return node('*',v,s)
    def __truediv__(s,v):return node('/',s,v)
    def __rtruediv__(s,v):return node('/',v,s)
    def __neg__(s):return node('*',s,-1)

def expr(v):return v if isinstance(v,E) else E('const',(float(v),))
def node(op,*args):return E(op,tuple(expr(a) for a in args))
def ref(name):return E('ref',(name,))
def sin(x):return node('sin',x)
def cos(x):return node('cos',x)
def floor(x):return node('floor',x)
def abs_(x):return node('abs',x)
def sqrt(x):return node('sqrt',x)
def power(x,y):return node('pow',x,y)
def minimum(x,y):return node('min',x,y)
def maximum(x,y):return node('max',x,y)
def clamp(x,lo=0,hi=1):return minimum(maximum(x,lo),hi)
def mix(a,b,t):return a+(b-a)*t
def fract(x):return x-floor(x)
def choose(x,a,b):return node('if',x,a,b)
def gt(a,b):return node('gt',a,b)
def smooth(a,b,x):
    t=clamp((x-a)/maximum(.0001,b-a));return t*t*(3-2*t)
U,V,T=ref('u'),ref('v'),ref('t')
ASPECT=ref('aspect')
P=[ref('p'+str(n)) for n in range(6)]
A=[ref('a'+str(n)) for n in range(3)]
B=[ref('b'+str(n)) for n in range(3)]
C=[ref('c'+str(n)) for n in range(3)]
PI=math.pi
def sample(n,u=U,v=V):return E('sample',(n,expr(u),expr(v)))
def luminance(c):return .299*c[0]+.587*c[1]+.114*c[2]
def hash_noise(x,y,frame):
    # 16-bit integer mixing is exact in NumPy, shader integers and FFmpeg's
    # double expression engine, avoiding backend-dependent sin/fract noise.
    def xor(a,b):return node('xor16',a,b)
    def mul(a,b):return node('mul16',a,b)
    seed=xor(xor(mul(x,1973),mul(y,9277)),mul(frame,26699))
    seed=mul(xor(seed,floor(seed/128)),40503)
    seed=mul(xor(seed,floor(seed/512)),57005)
    return seed/65535-.5

# key,label,min,max,default,step; every effect also has the existing Mix control.
CONTROLS={
 'Exposure & Gamma':[('exposure','Exposure (stops)',-4,4,.4,.05),('gamma','Gamma',.2,3,1.1,.01),('black','Black offset',-.2,.2,0,.01)],
 'White Balance':[('temperature','Temperature',-100,100,18,1),('tint','Tint',-100,100,0,1)],
 'Shadows & Highlights':[('shadows','Shadows',-100,100,25,1),('highlights','Highlights',-100,100,-20,1),('width','Tonal range',.1,.9,.5,.01)],
 'Vibrance':[('vibrance','Vibrance',-100,100,40,1),('saturation','Saturation (%)',0,200,100,1)],
 'Levels':[('black','Input black',0,.95,.04,.01),('white','Input white',.05,1,.96,.01),('gamma','Midtone gamma',.2,3,1,.01)],
 'Split Toning':[('strength','Strength (%)',0,100,30,1),('balance','Balance',-.5,.5,0,.01),('softness','Tonal softness',.05,.5,.25,.01)],
 'Bleach Bypass':[('strength','Silver contrast (%)',0,100,65,1),('saturation','Saturation (%)',0,100,45,1)],
 'Color Isolation':[('width','Colour tolerance',.02,1,.35,.01),('softness','Edge softness',.01,.5,.15,.01),('background','Background saturation (%)',0,100,0,1)],
 'Hue Shift':[('angle','Hue rotation (degrees)',-180,180,35,1)],
 'Vignette':[('strength','Darkening (%)',0,100,45,1),('radius','Clear radius',.05,1,.4,.01),('softness','Feather',.01,1,.55,.01),('center_x','Centre X',0,1,.5,.01),('center_y','Centre Y',0,1,.5,.01)],
 'Soft Glow':[('radius','Spread (% of layer)',.1,5,1.5,.1),('strength','Strength (%)',0,100,45,1),('threshold','Highlight threshold',0,1,.25,.01)],
 'Highlight Bloom':[('radius','Spread (% of layer)',.1,5,2,.1),('strength','Bloom intensity',0,2,.6,.05),('threshold','Highlight threshold',0,.99,.6,.01)],
 'Chromatic Aberration':[('amount','Channel offset (%)',0,3,.35,.05),('angle','Direction (degrees)',-180,180,0,1)],
 'Lens Distortion':[('amount','Barrel / pincushion',-.8,.8,.22,.01),('zoom','Lens zoom',.5,2,1.1,.01)],
 'Directional Blur':[('radius','Length (% of layer)',0,10,1.5,.1),('angle','Direction (degrees)',-180,180,25,1)],
 'Radial Zoom Blur':[('radius','Zoom blur (%)',0,30,8,.5),('center_x','Centre X',0,1,.5,.01),('center_y','Centre Y',0,1,.5,.01)],
 'Tilt Shift':[('radius','Blur spread (%)',0,5,1.3,.1),('position','Focus position',0,1,.5,.01),('width','Focus band width',.01,.8,.18,.01),('softness','Focus feather',.01,.5,.2,.01)],
 'Film Grain':[('amount','Grain amount (%)',0,40,8,1),('size','Grain size (% of layer)',.1,3,.35,.05),('speed','Grain refresh (Hz)',0,60,24,1)],
 'Film Fade':[('lift','Shadow lift (%)',0,50,12,1),('rolloff','Highlight roll-off (%)',0,50,8,1),('saturation','Saturation (%)',0,150,80,1)],
 'Scanlines':[('density','Lines per layer',20,500,120,1),('strength','Strength (%)',0,100,30,1),('speed','Scroll (cycles / second)',-5,5,0,.1)],
 'Halftone':[('density','Dots across layer',8,200,55,1),('softness','Dot softness',.01,.3,.06,.01),('paper','Paper brightness',0,1,.95,.01)],
 'Mosaic Pixelate':[('columns','Columns',4,320,64,1),('rows','Rows',4,320,36,1)],
 'CRT Monitor':[('density','Scanline density',20,500,140,1),('strength','Scanline strength (%)',0,100,25,1),('curvature','Screen curvature',0,.6,.12,.01),('fringe','RGB fringe (%)',0,2,.2,.05)],
 'Wave Distortion':[('amount','Displacement (%)',0,10,1,.1),('frequency','Waves',.1,30,4,.1),('speed','Speed (cycles / second)',-5,5,.7,.1)],
 'Mirror':[('axis','Mirror axis',0,1,0,1),('center','Mirror centre',.1,.9,.5,.01)],
 'Kaleidoscope':[('segments','Segments',2,16,6,1),('rotation','Rotation (degrees)',-180,180,0,1),('zoom','Zoom',.25,4,1,.05)],
 'RGB Glitch':[('amount','Channel offset (%)',0,5,.7,.1),('speed','Changes per second',.1,30,8,.1),('density','Horizontal bands',2,100,24,1),('activity','Activity (%)',0,100,45,1)],
 'Hue Cycle':[('speed','Cycles per second',.01,5,.25,.01),('phase','Starting hue (degrees)',-180,180,0,1)],
}
COLORS={'Split Toning':[('shadow','Shadow tint','#2877b0'),('highlight','Highlight tint','#ffc47a')],
        'Color Isolation':[('color','Colour to retain','#ff3030')]}
CATEGORIES={
 'Color Finishing':['Exposure & Gamma','White Balance','Shadows & Highlights','Vibrance','Levels','Split Toning','Bleach Bypass','Color Isolation','Hue Shift'],
 'Light & Lens':['Vignette','Soft Glow','Highlight Bloom','Chromatic Aberration','Lens Distortion'],
 'Blur & Focus':['Directional Blur','Radial Zoom Blur','Tilt Shift'],
 'Texture & Retro':['Film Grain','Film Fade','Scanlines','Halftone','Mosaic Pixelate','CRT Monitor'],
 'Distortion & Mirror':['Wave Distortion','Mirror','Kaleidoscope'],
 'Glitch & Rhythm':['RGB Glitch','Hue Cycle'],
}
DESCRIPTIONS={
 'Exposure & Gamma':'Adjust exposure in stops, midtone gamma and black offset.',
 'White Balance':'Correct warm/cool temperature and green/magenta tint.',
 'Shadows & Highlights':'Shape dark and bright regions independently with adjustable tonal coverage.',
 'Vibrance':'Boost muted colours more strongly than already saturated colours, with a separate saturation control.',
 'Levels':'Set the input black/white range and midtone gamma.',
 'Split Toning':'Tint shadows and highlights independently with a soft, adjustable tonal crossover.',
 'Bleach Bypass':'Combine desaturated colour with silver-like luminance contrast.',
 'Color Isolation':'Keep a selected colour while desaturating the rest of the image; tolerance and feather are adjustable.',
 'Hue Shift':'Rotate colour hue while retaining luminance structure.',
 'Vignette':'Darken the edges with adjustable strength, clear radius, feather and centre.',
 'Soft Glow':'A soft Gaussian diffusion treatment with highlight gating and a screen blend.',
 'Highlight Bloom':'Spread bright details into their surroundings using a thresholded Gaussian glow.',
 'Chromatic Aberration':'Offset red and blue in opposite directions for controlled lens colour fringing.',
 'Lens Distortion':'Adjust barrel or pincushion distortion and compensate with lens zoom.',
 'Directional Blur':'A 17-tap blur along an adjustable direction; length follows the layer dimensions.',
 'Radial Zoom Blur':'Blur along rays from a movable centre for speed or impact accents.',
 'Tilt Shift':'Keep a horizontal band in focus and progressively diffuse the foreground and background.',
 'Film Grain':'Deterministic monochrome grain with size, amount and refresh controls; pause to freeze it.',
 'Film Fade':'Lift blacks, roll off whites and soften saturation for a faded photographic look.',
 'Scanlines':'Adjustable horizontal scanlines with optional continuous scrolling.',
 'Halftone':'Convert luminance into a regular field of ink dots on adjustable paper.',
 'Mosaic Pixelate':'A grid-locked mosaic with independent column and row counts.',
 'CRT Monitor':'Combine curved-screen sampling, RGB fringe and scanlines.',
 'Wave Distortion':'Animate horizontal wave displacement with adjustable amplitude, frequency and speed.',
 'Mirror':'Reflect the image across an adjustable horizontal or vertical centre.',
 'Kaleidoscope':'Fold the image into adjustable radial segments, with rotation and zoom.',
 'RGB Glitch':'Deterministic animated horizontal-band RGB separation with speed and activity controls.',
 'Hue Cycle':'Cycle smoothly through hue rotations with speed and starting hue controls.',
}
ANIMATED={'Film Grain','Scanlines','Wave Distortion','RGB Glitch','Hue Cycle'}
INTEGER_KEYS={'segments','columns','rows','density','axis'}
CHOICES={('Mirror','axis'):[('Left / right',0),('Top / bottom',1)]}

def hue(c,angle):
    y=luminance(c);i=.596*c[0]-.274*c[1]-.322*c[2];q=.211*c[0]-.523*c[1]+.312*c[2]
    a=i*cos(angle)-q*sin(angle);b=i*sin(angle)+q*cos(angle)
    return [y+.956*a+.621*b,y-.272*a-.647*b,y-1.106*a+1.703*b]

def graph(name):
    y=luminance(C);p=P
    if name=='Exposure & Gamma':return [power(maximum(c*power(2,p[0])+p[2],0),1/p[1]) for c in C]
    if name=='White Balance':return [C[0]*power(2,p[0]*.004+p[1]*.001),C[1]*power(2,-p[1]*.002),C[2]*power(2,-p[0]*.004+p[1]*.001)]
    if name=='Shadows & Highlights':
        delta=p[0]/100*power(1-y,1/p[2])*.5+p[1]/100*power(y,1/p[2])*.5
        return [c+delta for c in C]
    if name=='Vibrance':
        sat=maximum(C[0],maximum(C[1],C[2]))-minimum(C[0],minimum(C[1],C[2]));amount=p[1]/100*(1+p[0]/100*(1-sat))
        return [y+(c-y)*amount for c in C]
    if name=='Levels':return [power(clamp((c-p[0])/maximum(.001,p[1]-p[0])),1/p[2]) for c in C]
    if name=='Split Toning':
        w=smooth(.5+p[1]-p[2],.5+p[1]+p[2],y)
        return [c+(mix(A[n],B[n],w)-.5)*p[0]/100*4*c*(1-c) for n,c in enumerate(C)]
    if name=='Bleach Bypass':return [mix(y+(c-y)*p[1]/100,choose(gt(y,.5),1-2*(1-c)*(1-y),2*c*y),p[0]/100) for c in C]
    if name=='Color Isolation':
        distance=sqrt(sum((C[n]-A[n])*(C[n]-A[n]) for n in range(3))/3);w=1-smooth(p[0],p[0]+p[1],distance)
        return [y+(c-y)*mix(p[2]/100,1,w) for c in C]
    if name in ('Hue Shift','Hue Cycle'):return hue(C,p[0]*PI/180 if name=='Hue Shift' else (T*p[0]*2*PI+p[1]*PI/180))
    if name=='Vignette':
        radius=sqrt((U-p[3])*(U-p[3])+(V-p[4])*(V-p[4]))*1.41421356237
        return [c*(1-p[0]/100*smooth(p[1],p[1]+p[2],radius)) for c in C]
    if name=='Film Fade':return [p[0]/100+(y+(c-y)*p[2]/100)*(1-(p[0]+p[1])/100) for c in C]
    if name=='Film Grain':
        x=floor(U*100/p[1]);z=floor(V*100/(p[1]*ASPECT));frame=floor(T*p[2]);noise=hash_noise(x,z,frame)
        return [c+noise*p[0]/100 for c in C]
    if name=='Scanlines':
        w=(1+cos((V*p[0]+T*p[2])*2*PI))/2
        return [c*(1-w*p[1]/100) for c in C]
    if name=='Halftone':
        x=fract(U*p[0])-.5;z=fract(V*p[0]/ASPECT)-.5;d=sqrt(x*x+z*z);w=smooth(.55*sqrt(maximum(1-y,0))-.5*p[1],.55*sqrt(maximum(1-y,0))+.5*p[1],d)
        return [w*p[2]]*3
    if name=='Mosaic Pixelate':return [sample(n,(floor(U*p[0])+.5)/p[0],(floor(V*p[1])+.5)/p[1]) for n in range(3)]
    if name=='Lens Distortion':
        x=(U-.5)/p[1];z=(V-.5)/(p[1]*ASPECT);factor=1+p[0]*(x*x+z*z)*4
        return [sample(n,.5+x*factor,.5+z*factor*ASPECT) for n in range(3)]
    if name=='Mirror':
        return [sample(n,choose(gt(p[0],.5),U,p[1]-abs_(U-p[1])),choose(gt(p[0],.5),p[1]-abs_(V-p[1]),V)) for n in range(3)]
    if name=='Kaleidoscope':
        x=U-.5;z=(V-.5)/ASPECT;r=sqrt(x*x+z*z)/p[2];angle=node('atan2',z,x)+p[1]*PI/180;sector=2*PI/p[0];angle=abs_(fract(angle/sector)*sector-sector/2)
        return [sample(n,.5+r*cos(angle),.5+r*sin(angle)*ASPECT) for n in range(3)]
    if name=='Wave Distortion':return [sample(n,U+p[0]/100*sin((V*p[1]+T*p[2])*2*PI),V) for n in range(3)]
    if name=='Chromatic Aberration':
        dx=p[0]/100*cos(p[1]*PI/180);dy=p[0]/100*sin(p[1]*PI/180)*ASPECT
        return [sample(0,U+dx,V+dy),C[1],sample(2,U-dx,V-dy)]
    if name=='RGB Glitch':
        band=floor(V*p[2]);frame=floor(T*p[1]);random=hash_noise(band,0,frame)+.5;offset=choose(gt(p[3]/100,random),sin(band*7+frame*3)*p[0]/100,0)
        return [sample(0,U+offset,V),sample(1,U-offset*.2,V),sample(2,U-offset,V)]
    if name=='CRT Monitor':
        x=U-.5;z=V-.5;factor=1+p[2]*(x*x+z*z)*4;u=.5+x*factor;v=.5+z*factor;w=1-p[1]/100*(1+cos(v*p[0]*2*PI))/2
        return [sample(0,u+p[3]/100,v)*w,sample(1,u,v)*w,sample(2,u-p[3]/100,v)*w]
    if name in ('Directional Blur','Radial Zoom Blur','Tilt Shift','Soft Glow','Highlight Bloom'):
        result=[]
        for n in range(3):
            terms=[]
            if name in ('Directional Blur','Radial Zoom Blur'):
                taps=[(k/8,0,1/17) for k in range(-8,9)]
            else:
                kernel=(1,4,6,4,1)
                taps=[(x/2,y/2,kernel[x+2]*kernel[y+2]/256) for y in range(-2,3) for x in range(-2,3)]
            for step,row,weight in taps:
                if name=='Directional Blur':du=cos(p[1]*PI/180)*p[0]/100*step;dv=sin(p[1]*PI/180)*p[0]/100*step*ASPECT
                elif name=='Radial Zoom Blur':du=(U-p[1])*p[0]/100*step;dv=(V-p[2])*p[0]/100*step
                else:du=step*p[0]/100;dv=row*p[0]/100*ASPECT
                value=sample(n,U+du,V+dv)
                if name=='Highlight Bloom':value=maximum(0,value-p[2])/maximum(.01,1-p[2])
                terms.append(value*weight)
            blurred=sum(terms)
            if name=='Tilt Shift':blurred=mix(C[n],blurred,smooth(p[2],p[2]+p[3],abs_(V-p[1])))
            elif name=='Soft Glow':blurred=1-(1-C[n])*(1-blurred*p[1]/100*smooth(p[2],p[2]+.2,y))
            elif name=='Highlight Bloom':blurred=C[n]+blurred*p[1]
            result.append(blurred)
        return result
    raise ValueError(name)

GRAPHS={name:tuple(graph(name)) for name in CONTROLS}

def evaluate(name,rgb,p,a,b,time):
    import numpy as np
    h,w=rgb.shape[:2]
    context=dict(u=(np.arange(w,dtype=np.float32)[None,:]+.5)/w,v=(np.arange(h,dtype=np.float32)[:,None]+.5)/h,t=np.float32(time),aspect=np.float32(w/h))
    context.update({'p'+str(n):np.float32(x) for n,x in enumerate(p)});context.update({'a'+str(n):np.float32(x) for n,x in enumerate(a)});context.update({'b'+str(n):np.float32(x) for n,x in enumerate(b)});context.update({'c'+str(n):rgb[:,:,n] for n in range(3)})
    cache={};uses={};visited=set()
    def children(e):return e.args[1:] if e.op=='sample' else () if e.op in ('const','ref') else e.args
    def visit(e):
        if e in visited:return
        visited.add(e)
        for child in children(e):uses[child]=uses.get(child,0)+1;visit(child)
    for e in GRAPHS[name]:uses[e]=uses.get(e,0)+1;visit(e)
    def release(e):
        uses[e]-=1
        if uses[e]==0:cache.pop(e,None)
    def run(e):
        if e in cache:return cache[e]
        op=e.op
        if op=='const':r=np.float32(e.args[0])
        elif op=='ref':r=context[e.args[0]]
        elif op=='sample':
            n,x,y=e.args;x=np.clip(run(x)*w-.5,0,w-1);y=np.clip(run(y)*h-.5,0,h-1);x0=np.floor(x).astype(np.int32);y0=np.floor(y).astype(np.int32);x1=np.minimum(x0+1,w-1);y1=np.minimum(y0+1,h-1);fx=x-x0.astype(np.float32);fy=y-y0.astype(np.float32)
            r=(rgb[y0,x0,n]*(1-fx)+rgb[y0,x1,n]*fx)*(1-fy)+(rgb[y1,x0,n]*(1-fx)+rgb[y1,x1,n]*fx)*fy
        else:
            args=[run(v) for v in e.args]
            operations={'+':np.add,'-':np.subtract,'*':np.multiply,'/':np.divide,'pow':np.power,'sin':np.sin,'cos':np.cos,'floor':np.floor,'abs':np.abs,'sqrt':np.sqrt,'min':np.minimum,'max':np.maximum,'gt':np.greater,'if':np.where,'atan2':np.arctan2}
            if op in ('xor16','mul16'):
                x,y=((np.asarray(a).astype(np.int64)&65535).astype(np.uint32) for a in args)
                r=((np.bitwise_xor(x,y) if op=='xor16' else x*y)&65535).astype(np.float32)
            else:r=operations[op](*args)
        cache[e]=r
        for child in children(e):release(child)
        return r
    outputs=[]
    for e in GRAPHS[name]:outputs.append(np.broadcast_to(run(e),(h,w)));release(e)
    return np.stack(outputs,axis=2)

def emit(e,backend,channel=0,bindings=None):
    if bindings and e in bindings:return bindings[e]
    op=e.op;args=e.args
    if op=='const':return format(args[0],'.12g')+('.0' if args[0].is_integer() and backend!='ffmpeg' else '')
    if op=='ref':
        key=args[0]
        if key=='aspect':return '(W/H)' if backend=='ffmpeg' else 'p2.w' if backend=='glsl' else 'row1.w'
        if backend=='ffmpeg':
            if key=='u':return '((X+.5)/W)'
            if key=='v':return '((Y+.5)/H)'
            if key=='t':return 'TIME'
            if key[0]=='c':return 'rgb'[int(key[1])]+'(X,Y)/255'
            return key.upper()
        if key in ('u','v'):return 'uv.'+('x' if key=='u' else 'y')
        if key=='t':return 'effectTime' if backend=='glsl' else 'extra.y'
        n=int(key[1]);prefix={'p':('p1' if n<3 else 'p2') if backend=='glsl' else ('row0' if n<3 else 'row1'),'a':'colorA' if backend=='glsl' else 'row2','b':'colorB' if backend=='glsl' else 'grade','c':'rgb'}[key[0]]
        return prefix+'.'+'xyzw'[n if key[0]!='p' or n<3 else n-3]
    if op=='sample':
        n,u,v=args;x=emit(u,backend,bindings=bindings);y=emit(v,backend,bindings=bindings)
        if backend=='ffmpeg':return f"({'rgb'[n]}(clip(({x})*W-.5,0,W-1),clip(({y})*H-.5,0,H-1))/255)"
        vector='vec2' if backend=='glsl' else 'float2';return f"creativeRgb({vector}({x},{y})).{'rgb'[n]}"
    a=[emit(v,backend,channel,bindings) for v in args]
    if op in ('xor16','mul16'):
        if backend=='ffmpeg':
            x,y=(f'mod(mod(({v}),65536)+65536,65536)' for v in a)
            return f'({x}+{y}-2*bitand({x},{y}))' if op=='xor16' else f'mod(({x})*({y}),65536)'
        cast='float'
        return f'{cast}((uint(int({a[0]})){"^" if op=="xor16" else "*"}uint(int({a[1]})))&65535u)'
    if op in ('+','-','*','/'):return '('+a[0]+op+a[1]+')'
    if op=='gt':return f'gt({a[0]},{a[1]})' if backend=='ffmpeg' else '('+a[0]+'>'+a[1]+')'
    if op=='if':return f'if({a[0]},{a[1]},{a[2]})' if backend=='ffmpeg' else '('+a[0]+'?'+a[1]+':'+a[2]+')'
    if op=='atan2' and backend=='glsl':op='atan'
    return op+'('+','.join(a)+')'

def ffmpeg_expressions(name,p,a,b,time):
    import re
    constants={'P'+str(n):format(v,'.12g') for n,v in enumerate(p)};constants.update({'A'+str(n):format(v,'.12g') for n,v in enumerate(a)});constants.update({'B'+str(n):format(v,'.12g') for n,v in enumerate(b)});constants['TIME']='('+time+')'
    output=[]
    for e in GRAPHS[name]:
        bindings={};setup=[];seen=set()
        def visit(node):
            if node in seen:return
            seen.add(node)
            if node.op not in ('const','ref'):
                for child in (node.args[1:] if node.op=='sample' else node.args):visit(child)
            if node.op in ('mul16','xor16'):
                index=len(bindings)
                if index>=10:raise ValueError('FFmpeg hash register budget exceeded')
                setup.append(f'st({index},{emit(node,"ffmpeg",bindings=bindings)})');bindings[node]=f'ld({index})'
        visit(e)
        text=emit(e,'ffmpeg',bindings=bindings)
        if setup:text='('+(';'.join([*setup,text]))+')'
        output.append(re.sub(r'\b(P[0-5]|A[0-2]|B[0-2]|TIME)\b',lambda m:constants[m[0]],text))
    return output

def shader_cases(backend,names=None):
    vector='vec3' if backend=='glsl' else 'float3';mode='mode' if backend=='glsl' else 'extra.x'
    lines=[]
    for n,(name,graph) in enumerate(GRAPHS.items()):
        if names is not None and name not in names:continue
        bindings={};lines.append(f'    if ({mode} < {n+7.5}) {{')
        def bind(e):
            if e.op in ('const','ref') or e in bindings:return
            children=e.args[1:] if e.op=='sample' else e.args
            for child in children:bind(child)
            code=emit(e,backend,bindings=bindings);name='e'+str(len(bindings));bindings[e]=name
            lines.append('        '+('bool' if e.op=='gt' else 'float')+' '+name+'='+code+';')
        for e in graph:bind(e)
        lines.append('        return '+vector+'('+','.join(emit(e,backend,bindings=bindings) for e in graph)+');\n    }')
    return '\n'.join(lines)+'\n    return rgb;'
