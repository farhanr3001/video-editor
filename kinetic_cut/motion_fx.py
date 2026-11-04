"""Motion composition effects: layer blur/glow/feather, blend modes, camera, floor reflection, post processing,
particles, trails and the extra shape kinds. Everything is optional; a scene without these fields renders as before."""
import math
from functools import lru_cache
import numpy as np
from PIL import Image,ImageFilter
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QImage,QPainter,QPainterPath,QColor,QPen,QTransform,QLinearGradient,QRadialGradient,QBrush,QPolygonF
from .keyframes import value as key_value

BLENDS={'normal':QPainter.CompositionMode_SourceOver,'add':QPainter.CompositionMode_Plus,'multiply':QPainter.CompositionMode_Multiply,
        'screen':QPainter.CompositionMode_Screen,'overlay':QPainter.CompositionMode_Overlay,'soft_light':QPainter.CompositionMode_SoftLight}
CAMERA_CHANNELS={'x':0.,'y':0.,'zoom':1.,'rotation':0.,'shake':0.}
POST_CHANNELS={'bloom':0.,'bloom_threshold':.55,'bloom_radius':24.,'vignette':0.,'vignette_softness':.6,'grain':0.,'aberration':0.,
               'saturation':1.,'contrast':1.,'brightness':0.,'tint_amount':0.,'tint_mix':0.}
FLOOR_DEFAULT=dict(y=1500.,opacity=.35,fade=420.,blur=6.)
NODE_KEYS={'id','name','kind','parent','visible','start','end','keyframes','text','font','bold','fill','stroke','gradient','path','path_to','mask','shadow',
    'source','image_fit','text_align','text_mode','caret','caret_period','number_grouping','number_trim_zeros','number_decimals','number_prefix','number_suffix',
    'stagger','entry_duration','entry_y','entry_rotation','entry_scale','entry_easing','entry_bezier','anchor_x','anchor_y','path_svg','blend','glow','depth',
    'follow','stretch','trail','emitter','runs','entry_blur','entry_color','dash','cap','join','sides','inner','points','smooth','closed','cell','gradient_type','gradient_angle',
    'gradient_stops','gradient_center','gradient_radius','reflect','italic','line_height','visible_in_camera','layout','in_point','speed','loop','volume'}
SCENE_KEYS={'version','template','canvas','nodes','motion_blur','sound_cues','camera','post','floor','background'}

def clamp(v,lo,hi):return max(lo,min(hi,v))

def number(raw,name,low,high):
    if isinstance(raw,bool) or not isinstance(raw,(int,float)) or not math.isfinite(raw):raise ValueError(name+' must be a finite number')
    if not low<=raw<=high:raise ValueError(name+' must be between %g and %g'%(low,high))
    return float(raw)

def colour(raw,name):
    if not isinstance(raw,str) or not QColor(raw).isValid():raise ValueError(name+' must be a valid colour')
    return raw

def pair(raw,name,low,high):
    if isinstance(raw,(int,float)) and not isinstance(raw,bool):raw=[raw,raw]
    if not isinstance(raw,list) or len(raw)!=2:raise ValueError(name+' must be [min, max]')
    return [number(raw[0],name,low,high),number(raw[1],name,low,high)]

# ---------------------------------------------------------------- validation
def validate_node(node):
    """Normalise the optional effect fields of one layer in place."""
    from .motion_svg import parse
    if node.get('kind')=='emitter' and 'emitter' not in node:node['emitter']={}
    if 'path_svg' in node:node['path']=parse(node['path_svg']); node['kind']=node.get('kind','path')
    if node.get('blend','normal') not in BLENDS:raise ValueError('blend must be '+', '.join(BLENDS))
    if 'depth' in node:node['depth']=number(node['depth'],'depth',0,10)
    if 'glow' in node:
        g=node['glow']
        if not isinstance(g,dict):raise ValueError('glow must be an object')
        g=dict(g); g['enabled']=bool(g.get('enabled',True)); g['radius']=number(g.get('radius',16),'glow radius',0,400); g['intensity']=number(g.get('intensity',1),'glow intensity',0,8)
        g['layers']=int(number(g.get('layers',2),'glow layers',1,4))
        if g.get('color'):g['color']=colour(g['color'],'glow colour')
        node['glow']=g
    if 'follow' in node:
        f=node['follow']
        if not isinstance(f,dict) or not isinstance(f.get('path'),str):raise ValueError('follow needs {path: layer id}')
        f=dict(f); f['orient']=bool(f.get('orient',False)); f['offset']=number(f.get('offset',0),'follow offset',-3600,3600); node['follow']=f
    if 'stretch' in node:
        s=node['stretch']
        if not isinstance(s,dict):raise ValueError('stretch must be an object')
        node['stretch']=dict(amount=number(s.get('amount',.0006),'stretch amount',0,1),max=number(s.get('max',.6),'stretch max',0,4),squash=bool(s.get('squash',True)))
    if 'trail' in node:
        r=node['trail']
        if not isinstance(r,dict):raise ValueError('trail must be an object')
        r=dict(r); r['length']=number(r.get('length',.6),'trail length',.01,10); r['samples']=int(number(r.get('samples',40),'trail samples',2,200))
        r['width']=number(r.get('width',6),'trail width',.1,500); r['taper']=number(r.get('taper',1),'trail taper',0,6); r['fade']=number(r.get('fade',1.5),'trail fade',0,8)
        r['additive']=bool(r.get('additive',True))
        if r.get('color'):r['color']=colour(r['color'],'trail colour')
        node['trail']=r
    if 'emitter' in node:node['emitter']=validate_emitter(node['emitter'])
    if 'runs' in node:
        runs=node['runs']
        if not isinstance(runs,list) or not 1<=len(runs)<=64:raise ValueError('runs must list 1–64 text runs')
        clean=[]
        for run in runs:
            if not isinstance(run,dict) or not isinstance(run.get('text'),str):raise ValueError('Every run needs text')
            item={'text':run['text']}
            if run.get('fill'):item['fill']=colour(run['fill'],'run fill')
            for key in ('italic','bold'):
                if key in run:item[key]=bool(run[key])
            if run.get('font'):
                if not isinstance(run['font'],str) or len(run['font'])>128:raise ValueError('run font must be a family name')
                item['font']=run['font']
            if 'size' in run:item['size']=number(run['size'],'run size',.1,10)
            clean.append(item)
        node['runs']=clean; node['text']=''.join(r['text'] for r in clean)
        if len(node['text'])>4096:raise ValueError('Text layer exceeds 4096 characters')
    if 'entry_blur' in node:node['entry_blur']=number(node['entry_blur'],'entry_blur',0,200)
    if 'entry_color' in node:node['entry_color']=colour(node['entry_color'],'entry_color')
    if node.get('kind')=='video':
        for key,low,high in (('in_point',0,1e6),('speed',.05,20),('volume',0,1)):
            if key in node:node[key]=number(node[key],key,low,high)
        if 'loop' in node:node['loop']=bool(node['loop'])
        if node.get('image_fit','cover') not in ('contain','cover','stretch'):raise ValueError('image_fit must be contain, cover or stretch')
    if 'layout' in node:
        lay=node['layout']
        if not isinstance(lay,dict) or lay.get('type','stack')!='stack':raise ValueError("layout must be {'type':'stack', ...}")
        if lay.get('direction','vertical') not in ('vertical','horizontal'):raise ValueError('layout direction must be vertical or horizontal')
        node['layout']=dict(type='stack',direction=lay.get('direction','vertical'),gap=number(lay.get('gap',24),'layout gap',-2000,2000),reflow=number(lay.get('reflow',.35),'layout reflow',0,5))
    if 'dash' in node:
        d=node['dash']
        if not isinstance(d,list) or not 1<=len(d)<=8 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not v>0 for v in d):raise ValueError('dash must list 1–8 positive lengths (in stroke widths)')
        node['dash']=[float(v) for v in d]
    if node.get('cap','round') not in ('round','flat','square'):raise ValueError('cap must be round, flat or square')
    if node.get('join','round') not in ('round','miter','bevel'):raise ValueError('join must be round, miter or bevel')
    if node.get('kind')=='polygon':
        node['sides']=int(number(node.get('sides',5),'sides',3,64)); node['inner']=number(node.get('inner',0),'inner',0,.98)
    if node.get('kind')=='polyline':
        pts=node.get('points')
        if not isinstance(pts,list) or not 2<=len(pts)<=2048 or any(not isinstance(p,list) or len(p)!=2 for p in pts):raise ValueError('polyline points must be 2–2048 [x, y] pairs')
        node['points']=[[number(p[0],'point',-100000,100000),number(p[1],'point',-100000,100000)] for p in pts]
    if node.get('kind')=='grid':node['cell']=number(node.get('cell',60),'cell',2,2000)
    if node.get('gradient_type','linear') not in ('linear','radial'):raise ValueError('gradient_type must be linear or radial')
    if 'gradient_stops' in node:
        stops=node['gradient_stops']
        if not isinstance(stops,list) or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not 0<=v<=1 for v in stops):raise ValueError('gradient_stops must be numbers in 0–1')
        if len(stops)!=len(node.get('gradient',[])):raise ValueError('gradient_stops must match the gradient colours')
    if 'gradient_center' in node:node['gradient_center']=pair(node['gradient_center'],'gradient_center',-1,2)
    if 'gradient_radius' in node:node['gradient_radius']=number(node['gradient_radius'],'gradient_radius',.01,20)
    if 'gradient_angle' in node:node['gradient_angle']=number(node['gradient_angle'],'gradient_angle',-3600,3600)
    mask=node.get('mask')
    if isinstance(mask,dict):
        if 'feather' in mask:mask['feather']=number(mask['feather'],'mask feather',0,400)
        if 'invert' in mask and not isinstance(mask['invert'],bool):raise ValueError('mask invert must be boolean')

def validate_emitter(raw):
    if not isinstance(raw,dict):raise ValueError('emitter must be an object')
    e=dict(raw)
    e['rate']=number(e.get('rate',0),'emitter rate',0,2000)
    bursts=e.get('bursts',[])
    if not isinstance(bursts,list) or len(bursts)>64:raise ValueError('emitter bursts must list up to 64 {time,count}')
    e['bursts']=[dict(time=number(b.get('time',0),'burst time',0,1e5),count=int(number(b.get('count',20),'burst count',1,3000))) for b in bursts]
    e['life']=pair(e.get('life',[.6,1.2]),'emitter life',.01,30); e['speed']=pair(e.get('speed',[120,420]),'emitter speed',0,20000)
    e['angle']=number(e.get('angle',-90),'emitter angle',-3600,3600); e['spread']=number(e.get('spread',360),'emitter spread',0,360)
    e['gravity']=number(e.get('gravity',600),'emitter gravity',-20000,20000); e['drag']=number(e.get('drag',1),'emitter drag',0,50)
    e['size']=pair(e.get('size',[4,1]),'emitter size',.1,400); e['trail']=number(e.get('trail',.05),'emitter trail',0,2)
    e['fade']=number(e.get('fade',1.2),'emitter fade',0,8); e['seed']=int(number(e.get('seed',1),'emitter seed',0,2**31-1))
    cols=e.get('colors',['#ffffff'])
    if not isinstance(cols,list) or not 1<=len(cols)<=8:raise ValueError('emitter colors must list 1–8 colours')
    e['colors']=[colour(c,'emitter colour') for c in cols]
    if e.get('shape','spark') not in ('spark','dot','streak','ring'):raise ValueError('emitter shape must be spark, dot, streak or ring')
    e['shape']=e.get('shape','spark'); e['additive']=bool(e.get('additive',True)); e['radius']=number(e.get('radius',0),'emitter radius',0,5000)
    e['spawn_end']=number(e.get('spawn_end',1e5),'emitter spawn_end',0,1e5)
    return e

def validate_scene_extras(scene,finite,clean_curves_for):
    cam=scene.get('camera')
    if cam is not None:
        if not isinstance(cam,dict):raise ValueError('camera must be an object')
        cam=dict(cam)
        for key,default in CAMERA_CHANNELS.items():cam[key]=finite(cam.get(key,default))
        cam['keyframes']=clean_curves_for(cam.get('keyframes',{}),CAMERA_CHANNELS); scene['camera']=cam
    post=scene.get('post')
    if post is not None:
        if not isinstance(post,dict):raise ValueError('post must be an object')
        post=dict(post)
        for key,default in POST_CHANNELS.items():post[key]=finite(post.get(key,default))
        for key in ('tint','tint_to'):
            if post.get(key):colour(post[key],'post '+key)
        post['keyframes']=clean_curves_for(post.get('keyframes',{}),POST_CHANNELS); scene['post']=post
    floor=scene.get('floor')
    if floor is not None:
        if not isinstance(floor,dict):raise ValueError('floor must be an object')
        floor=dict(floor); floor['enabled']=bool(floor.get('enabled',True))
        for key,default in FLOOR_DEFAULT.items():floor[key]=finite(floor.get(key,default))
        scene['floor']=floor
    bg=scene.get('background')
    if bg is not None:
        if not isinstance(bg,dict):raise ValueError('background must be an object')
        bg=dict(bg)
        if bg.get('color'):colour(bg['color'],'background colour')
        if 'gradient' in bg:
            g=bg['gradient']
            if not isinstance(g,list) or not 2<=len(g)<=16:raise ValueError('background gradient needs 2–16 colours')
            for c in g:colour(c,'background gradient')
        scene['background']=bg

def lint(scene):
    """Human-readable warnings for unknown fields (they are otherwise ignored silently)."""
    import difflib
    out=[]
    for key in scene:
        if key not in SCENE_KEYS:out.append("scene: unknown field '%s'"%key+_hint(key,SCENE_KEYS,difflib))
    from .motion import CHANNELS
    for node in scene.get('nodes',[]):
        for key in node:
            if key not in NODE_KEYS and key not in CHANNELS and key not in ('width','height','radius','stroke_width','font_size','tracking','number'):
                out.append("layer '%s': unknown field '%s'"%(node.get('id','?'),key)+_hint(key,NODE_KEYS|set(CHANNELS),difflib))
    return out

def _hint(key,known,difflib):
    near=difflib.get_close_matches(key,sorted(known),1,.7)
    return " (did you mean '%s'?)"%near[0] if near else ''

# ---------------------------------------------------------------- image helpers
def blank(size):
    image=QImage(int(size[0]),int(size[1]),QImage.Format_ARGB32_Premultiplied); image.fill(Qt.transparent); return image

def np_of(image):
    image=image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()

def image_of(arr):
    arr=np.ascontiguousarray(arr,np.uint8); h,w=arr.shape[:2]
    return QImage(arr.tobytes(),w,h,w*4,QImage.Format_ARGB32_Premultiplied).copy()

def _blur_plane(img,radius):
    f=int(clamp(radius/3.5,1,10))
    if f>1:
        small=img.resize((max(1,img.width//f),max(1,img.height//f)),Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius/f))
        return small.resize(img.size,Image.BILINEAR)
    return img.filter(ImageFilter.GaussianBlur(radius))

def blur_np(arr,radius):
    """Gaussian blur of a premultiplied BGRA array. Colour and alpha are blurred as separate opaque planes so
    Pillow never re-premultiplies already premultiplied data."""
    if radius<=.3:return arr
    rgb=_blur_plane(Image.fromarray(np.ascontiguousarray(arr[...,:3]),'RGB'),radius)
    a=_blur_plane(Image.fromarray(np.ascontiguousarray(arr[...,3]),'L'),radius)
    out=np.empty_like(arr); out[...,:3]=np.asarray(rgb); out[...,3]=np.asarray(a); return out

def blur_image(image,radius):return image_of(blur_np(np_of(image),radius))

def tint_image(image,color):
    """Replace the colour of a premultiplied image but keep its alpha."""
    arr=np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.width(),4).astype(np.float32)
    c=QColor(color); a=arr[...,3:4]/255
    arr[...,0]=c.blue()*a[...,0]; arr[...,1]=c.green()*a[...,0]; arr[...,2]=c.red()*a[...,0]
    return QImage(np.ascontiguousarray(arr.astype(np.uint8)).tobytes(),image.width(),image.height(),image.width()*4,QImage.Format_ARGB32_Premultiplied).copy()

def scale_of(painter):
    return math.sqrt(abs(painter.worldTransform().determinant())) or 1.

def device_size(painter):
    d=painter.device(); return d.width(),d.height()

def needs_layer(node,mask_feather,blur):
    g=node.get('glow')
    return blur>.05 or bool(g and g.get('enabled',True) and g.get('intensity',1)>0) or mask_feather>0

def glow_halo(arr,radius,intensity,layers):
    """Sum of progressively wider blurs of the layer, computed once at reduced resolution."""
    widest=radius*(1+1.8*(layers-1)); f=int(clamp(widest/3.5,1,10)); h,w=arr.shape[:2]
    if f>1:
        small=np.empty((max(1,h//f),max(1,w//f),4),np.uint8)
        small[...,:3]=np.asarray(Image.fromarray(np.ascontiguousarray(arr[...,:3]),'RGB').resize((small.shape[1],small.shape[0]),Image.BILINEAR))
        small[...,3]=np.asarray(Image.fromarray(np.ascontiguousarray(arr[...,3]),'L').resize((small.shape[1],small.shape[0]),Image.BILINEAR))
    else:small=arr
    halo=None
    for n in range(layers):
        piece=blur_np(small,radius*(1+1.8*n)/f).astype(np.float32)*(1/(1+.6*n))
        halo=piece if halo is None else halo+piece
    halo=np.clip(halo*intensity/max(1,layers)**.5,0,255).astype(np.uint8)
    if f>1:
        out=np.empty((h,w,4),np.uint8)
        out[...,:3]=np.asarray(Image.fromarray(np.ascontiguousarray(halo[...,:3]),'RGB').resize((w,h),Image.BILINEAR))
        out[...,3]=np.asarray(Image.fromarray(np.ascontiguousarray(halo[...,3]),'L').resize((w,h),Image.BILINEAR))
        return out
    return halo

def render_layer(painter,node,draw_fn,blur_px,glow_amount,feather=None):
    """Render draw_fn into a device-size layer with the painter's transform, then feather/blur/glow the used area."""
    s=scale_of(painter)
    layer=blank(device_size(painter)); lp=QPainter(layer)
    try:
        lp.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing|QPainter.SmoothPixmapTransform); lp.setTransform(painter.worldTransform())
        draw_fn(lp)
    finally:lp.end()
    arr=np_of(layer)
    if feather:
        mask_path,amount,invert=feather
        mi=blank(device_size(painter)); mp=QPainter(mi); mp.setRenderHint(QPainter.Antialiasing); mp.setTransform(painter.worldTransform())
        try:
            mp.setPen(Qt.NoPen); mp.setBrush(Qt.white)
            if invert:
                full=QPainterPath(); full.addRect(QRectF(-1e5,-1e5,2e5,2e5)); mp.drawPath(full.subtracted(mask_path))
            else:mp.drawPath(mask_path)
        finally:mp.end()
        ma=blur_np(np_of(mi),amount*s)[...,3:4].astype(np.float32)/255
        arr=(arr.astype(np.float32)*ma).astype(np.uint8)
    g=node.get('glow'); glowing=bool(g and g.get('enabled',True) and g.get('intensity',1)>0 and glow_amount>0)
    alpha=arr[...,3]; rows=np.flatnonzero(alpha.max(axis=1)); cols=np.flatnonzero(alpha.max(axis=0))
    if not len(rows):return
    reach=max(blur_px*s,(g['radius']*(1+1.8*(g.get('layers',2)-1))*s if glowing else 0))*3+3
    y0=int(max(0,rows[0]-reach)); y1=int(min(arr.shape[0],rows[-1]+1+reach)); x0=int(max(0,cols[0]-reach)); x1=int(min(arr.shape[1],cols[-1]+1+reach))
    crop=np.ascontiguousarray(arr[y0:y1,x0:x1])
    if blur_px>.05:crop=blur_np(crop,blur_px*s)
    painter.save()
    try:
        painter.resetTransform()
        if glowing:
            halo=glow_halo(crop,g['radius']*s,g['intensity']*glow_amount,g.get('layers',2)); gi=image_of(halo)
            if g.get('color'):gi=tint_image(gi,g['color'])
            painter.setCompositionMode(QPainter.CompositionMode_Plus); painter.drawImage(x0,y0,gi)
        painter.setCompositionMode(BLENDS[node.get('blend','normal')]); painter.drawImage(x0,y0,image_of(crop))
    finally:painter.restore()

def draw_blurred_path(painter,path,blur,brush,pen):
    """Draw one path softened by `blur` canvas units (used for per-character blur-in)."""
    tr=painter.worldTransform(); s=scale_of(painter); r=blur*s; pad=r*3+pen.widthF()*s+2
    dev=tr.mapRect(path.boundingRect()).adjusted(-pad,-pad,pad,pad).toAlignedRect()
    w,h=device_size(painter); dev=dev.intersected(QRectF(0,0,w,h).toAlignedRect())
    if dev.isEmpty():return
    img=blank((dev.width(),dev.height())); p=QPainter(img)
    try:
        p.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing); p.setTransform(tr*QTransform.fromTranslate(-dev.x(),-dev.y()))
        p.setBrush(brush); p.setPen(pen); p.drawPath(path)
    finally:p.end()
    img=blur_image(img,r)
    painter.save()
    try:painter.resetTransform(); painter.drawImage(dev.topLeft(),img)
    finally:painter.restore()

# ---------------------------------------------------------------- brushes, pens, shapes
def make_brush(node,w,h,fill,gradient):
    if isinstance(gradient,list) and len(gradient)>=2:
        stops=node.get('gradient_stops') or [n/(len(gradient)-1) for n in range(len(gradient))]
        if node.get('gradient_type','linear')=='radial':
            cx,cy=node.get('gradient_center',[.5,.5]); radius=max(1,w/2*node.get('gradient_radius',1))
            g=QRadialGradient(QPointF((cx-.5)*w,(cy-.5)*h*(w/max(1,h))),radius)
            brush=QBrush(g); brush.setTransform(QTransform.fromScale(1,h/max(1,w)))
            for stop,color in zip(stops,gradient):g.setColorAt(stop,QColor(color))
            brush=QBrush(g); brush.setTransform(QTransform.fromScale(1,h/max(1,w))); return brush
        else:
            a=math.radians(node.get('gradient_angle',0)); dx,dy=math.cos(a)*w/2,math.sin(a)*h/2
            g=QLinearGradient(-dx,-dy,dx,dy)
        for stop,color in zip(stops,gradient):g.setColorAt(stop,QColor(color))
        return QBrush(g)
    return QBrush(QColor(fill)) if fill!='none' else QBrush(Qt.NoBrush)

def make_pen(node,stroke,width,dash_offset):
    if stroke=='none' or width<=0:return QPen(Qt.NoPen)
    cap={'round':Qt.RoundCap,'flat':Qt.FlatCap,'square':Qt.SquareCap}[node.get('cap','round')]
    join={'round':Qt.RoundJoin,'miter':Qt.MiterJoin,'bevel':Qt.BevelJoin}[node.get('join','round')]
    pen=QPen(QColor(stroke),width,Qt.SolidLine,cap,join)
    if node.get('dash'):pen.setDashPattern(node['dash']); pen.setDashOffset(dash_offset)
    return pen

def polygon_path(sides,w,h,inner):
    p=QPainterPath(); points=[]
    count=sides*2 if inner>0 else sides
    for n in range(count):
        a=-math.pi/2+2*math.pi*n/count; r=(1 if (inner<=0 or n%2==0) else inner)
        points.append(QPointF(math.cos(a)*w/2*r,math.sin(a)*h/2*r))
    p.addPolygon(QPolygonF(points)); p.closeSubpath(); return p

def polyline_path(points,smooth,closed):
    p=QPainterPath(); pts=[QPointF(*q) for q in points]
    p.moveTo(pts[0])
    if smooth and len(pts)>2:
        for n in range(len(pts)-1):
            p0=pts[n-1] if n>0 else pts[n]; p1=pts[n]; p2=pts[n+1]; p3=pts[n+2] if n+2<len(pts) else pts[n+1]
            t=1/6
            p.cubicTo(p1+(p2-p0)*t,p2-(p3-p1)*t,p2)
    else:
        for q in pts[1:]:p.lineTo(q)
    if closed:p.closeSubpath()
    return p

def grid_path(w,h,cell):
    p=QPainterPath(); x=-w/2
    while x<=w/2+.01:p.moveTo(x,-h/2); p.lineTo(x,h/2); x+=cell
    y=-h/2
    while y<=h/2+.01:p.moveTo(-w/2,y); p.lineTo(w/2,y); y+=cell
    return p

def trimmed(path,start,end):
    """The part of a path between two fractions of its length (a comet, a ring segment, a draw-on)."""
    if end<=start:return QPainterPath()
    length=path.length()
    if length<=0:return path
    p=QPainterPath(); samples=max(2,min(256,math.ceil(length*(end-start)/6)))
    for n in range(samples+1):
        point=path.pointAtPercent(path.percentAtLength(length*(start+(end-start)*n/samples)))
        if n:p.lineTo(point)
        else:p.moveTo(point)
    return p

# ---------------------------------------------------------------- particles
@lru_cache(maxsize=16)
def _table(seed,n):
    return np.random.RandomState(seed&0x7fffffff).random_sample((n,6))

def _ramp(colors,u):
    if len(colors)==1:return QColor(colors[0])
    x=clamp(u,0,1)*(len(colors)-1); i=min(len(colors)-2,int(x)); f=x-i; a=QColor(colors[i]); b=QColor(colors[i+1])
    return QColor(round(a.red()+(b.red()-a.red())*f),round(a.green()+(b.green()-a.green())*f),round(a.blue()+(b.blue()-a.blue())*f))

def draw_emitter(painter,node,t,cap=3500):
    e=node['emitter']; start=node.get('start',0); table=_table(e['seed'],20000); births=[]
    lmax=e['life'][1]
    if e['rate']>0:
        last=min(t,start+e['spawn_end']); first=max(0,math.ceil((t-lmax-start)*e['rate']))
        for k in range(first,int((last-start)*e['rate'])+1):births.append((k,start+k/e['rate']))
    for index,burst in enumerate(e['bursts']):
        if burst['time']<=t<=burst['time']+lmax:
            for j in range(burst['count']):births.append((10000*(index+1)+j,burst['time']))
    if len(births)>cap:births=births[-cap:]
    if not births:return
    painter.save()
    try:
        if e['additive']:painter.setCompositionMode(QPainter.CompositionMode_Plus)
        for k,tb in births:
            tau=t-tb
            if tau<0:continue
            r=table[k%20000]; life=e['life'][0]+(e['life'][1]-e['life'][0])*r[2]
            if tau>=life:continue
            u=tau/life; ang=math.radians(e['angle']+(r[0]-.5)*e['spread']); sp=e['speed'][0]+(e['speed'][1]-e['speed'][0])*r[1]
            d=e['drag']; td=(1-math.exp(-d*tau))/d if d>0 else tau; vx=math.cos(ang)*sp; vy=math.sin(ang)*sp
            ox=oy=0.
            if e['radius']:ox=math.cos(r[4]*6.283)*e['radius']*r[5]; oy=math.sin(r[4]*6.283)*e['radius']*r[5]
            x=ox+vx*td; y=oy+vy*td+.5*e['gravity']*tau*tau
            ex=math.exp(-d*tau); cx=vx*ex; cy=vy*ex+e['gravity']*tau
            size=(e['size'][0]+(e['size'][1]-e['size'][0])*u)*(.6+.8*r[3]); alpha=clamp((1-u)**e['fade'],0,1)
            color=_ramp(e['colors'],(u+r[4]*.2) if len(e['colors'])>1 else 0); color.setAlphaF(alpha)
            shape=e['shape']
            if shape in ('spark','streak'):
                pen=QPen(color,max(.5,size),Qt.SolidLine,Qt.RoundCap); painter.setPen(pen)
                painter.drawLine(QPointF(x-cx*e['trail'],y-cy*e['trail']),QPointF(x,y))
            if shape in ('spark','dot'):
                painter.setPen(Qt.NoPen); painter.setBrush(color); painter.drawEllipse(QPointF(x,y),max(.4,size*(.6 if shape=='spark' else .5)),max(.4,size*(.6 if shape=='spark' else .5)))
            if shape=='ring':
                painter.setBrush(Qt.NoBrush); painter.setPen(QPen(color,max(.5,size*.3))); painter.drawEllipse(QPointF(x,y),size*(1+u*3),size*(1+u*3))
    finally:painter.restore()

# ---------------------------------------------------------------- camera
def camera_values(scene,t):
    cam=scene.get('camera')
    if not cam:return None
    k=cam.get('keyframes',{}); v={n:key_value(k.get(n,[]),t,cam.get(n,d)) for n,d in CAMERA_CHANNELS.items()}
    return v

def camera_transform(scene,t,depth,size):
    v=camera_values(scene,t)
    if not v:return None
    w,h=size; tr=QTransform(); d=depth
    shake=v['shake']; sx=sy=0.
    if shake:
        sx=shake*(math.sin(t*47.3)+.7*math.sin(t*31.1+1.7)+.5*math.sin(t*83.9+.4))/2.2; sy=shake*(math.sin(t*53.7+2.1)+.7*math.sin(t*29.3)+.5*math.sin(t*71.3+1.1))/2.2
    zoom=1+(v['zoom']-1)*d
    tr.translate(w/2,h/2); tr.rotate(v['rotation']*d); tr.scale(zoom,zoom); tr.translate(-w/2,-h/2); tr.translate(-v['x']*d+sx*min(1,d),-v['y']*d+sy*min(1,d))
    return tr

# ---------------------------------------------------------------- post processing
def post_values(scene,t):
    post=scene.get('post')
    if not post:return None
    k=post.get('keyframes',{}); v={n:key_value(k.get(n,[]),t,post.get(n,d)) for n,d in POST_CHANNELS.items()}
    v['tint']=post.get('tint','#ffffff'); v['tint_to']=post.get('tint_to') or v['tint']; return v

@lru_cache(maxsize=4)
def _vignette_edge(h,w,softness):
    yy,xx=np.mgrid[0:h,0:w].astype(np.float32); d=np.sqrt(((xx/w-.5)*2)**2+((yy/h-.5)*2)**2)/1.414
    return np.clip((d-(1-softness))/max(.01,softness),0,1)**2

@lru_cache(maxsize=2)
def _noise(h,w):
    return np.random.RandomState(7).standard_normal((h,w)).astype(np.float32)

def apply_post_reference(image,v,scale,frame_seed):
    """Original float32 implementation, kept as the correctness reference for tests."""
    if not v:return image
    h,w=image.height(),image.width()
    arr=np.frombuffer(image.constBits(),np.uint8).reshape(h,image.bytesPerLine()//4,4)[:,:w].astype(np.float32)/255
    if v['aberration']:
        k=int(round(v['aberration']*scale))
        if k:arr[...,0]=np.roll(arr[...,0],k,axis=1); arr[...,2]=np.roll(arr[...,2],-k,axis=1)
    if v['bloom']>0:
        f=4 if min(h,w)>600 else 2 if min(h,w)>300 else 1
        small=arr if f==1 else arr[::f,::f]
        lum=small[...,2]*.3+small[...,1]*.59+small[...,0]*.11
        mask=np.clip((lum-v['bloom_threshold'])/max(.01,1-v['bloom_threshold']),0,1)[...,None]
        bright=Image.fromarray((np.clip(small[...,:3]*mask,0,1)*255).astype(np.uint8),'RGB'); r=max(1,v['bloom_radius']*scale/f); glow=None
        for n,wt in ((0,.5),(1,.3),(2,.2)):
            piece=np.asarray(_blur_plane(bright,r*(1+1.7*n)),np.float32)/255*wt
            glow=piece if glow is None else glow+piece
        glow*=v['bloom']*1.6
        if f>1:glow=np.asarray(Image.fromarray((np.clip(glow,0,1)*255).astype(np.uint8),'RGB').resize((w,h),Image.BILINEAR),np.float32)/255
        arr[...,:3]+=glow
        gl=glow[...,0]*.11+glow[...,1]*.59+glow[...,2]*.3; arr[...,3]=np.maximum(arr[...,3],np.clip(gl,0,1))
    rgb=arr[...,:3]
    if v['brightness']:rgb+=v['brightness']*arr[...,3:4]
    if v['contrast']!=1:rgb[:]=(rgb-.5*arr[...,3:4])*v['contrast']+.5*arr[...,3:4]
    if v['saturation']!=1:
        lum=(rgb[...,2]*.3+rgb[...,1]*.59+rgb[...,0]*.11)[...,None]; rgb[:]=lum+(rgb-lum)*v['saturation']
    if v['tint_amount']:
        a=QColor(v['tint']); b=QColor(v['tint_to']); m=clamp(v['tint_mix'],0,1)
        c=np.array([(a.blue()+(b.blue()-a.blue())*m)/255,(a.green()+(b.green()-a.green())*m)/255,(a.red()+(b.red()-a.red())*m)/255],np.float32)
        rgb[:]=rgb*((1-v['tint_amount'])+v['tint_amount']*c)
    if v['vignette']:
        rgb*= (1-clamp(v['vignette'],0,1)*_vignette_edge(h,w,round(v['vignette_softness'],3)))[...,None]
    if v['grain']:
        rs=np.random.RandomState(frame_seed&0x7fffffff); noise=np.roll(np.roll(_noise(h,w),int(rs.randint(0,h)),axis=0),int(rs.randint(0,w)),axis=1)[...,None]
        rgb+=noise*v['grain']*.08*arr[...,3:4]
    arr[...,:3]=np.clip(rgb,0,1); arr[...,:3]=np.minimum(arr[...,:3],arr[...,3:4])
    return QImage(np.ascontiguousarray((arr*255+.5).astype(np.uint8)).tobytes(),w,h,w*4,QImage.Format_ARGB32_Premultiplied).copy()


@lru_cache(maxsize=4)
def _vignette_mask(h,w,softness,strength):
    edge=_vignette_edge(h,w,softness); return Image.fromarray(np.clip((1-strength*edge)*255+.5,0,255).astype(np.uint8),'L').convert('RGB')

@lru_cache(maxsize=2)
def _noise_tile(h,w):
    return np.random.RandomState(7).standard_normal((h*2,w*2)).astype(np.float32)

@lru_cache(maxsize=4)
def _noise_scaled(h,w,amount):
    return Image.fromarray(np.clip(_noise_tile(h,w)*amount*.08*255+128.5,0,255).astype(np.uint8),'L').convert('RGB')

def _lut(fn,bands=1):return [min(255,max(0,int(fn(i/255)*255+.5))) for i in range(256)]*bands

def apply_post(image,v,scale,frame_seed):
    """Post processing built from Pillow's C image operations (no full-frame float arrays), about 5x faster than the reference."""
    if not v:return image
    from PIL import ImageChops
    h,w=image.height(),image.width()
    img=Image.frombuffer('RGBA',(w,h),bytes(image.constBits()),'raw','BGRA',image.bytesPerLine(),1)
    r,g,b,a=img.split()
    if v['aberration']:
        k=int(round(v['aberration']*scale))
        if k:r=ImageChops.offset(r,k,0); b=ImageChops.offset(b,-k,0)
    rgb=Image.merge('RGB',(r,g,b))
    if v['bloom']>0:
        f=4 if min(h,w)>600 else 2 if min(h,w)>300 else 1
        small=rgb if f==1 else rgb.reduce(f); thr=v['bloom_threshold']
        mask=small.convert('L').point(_lut(lambda x:min(1,max(0,(x-thr)/max(.01,1-thr))))); bright=ImageChops.multiply(small,mask.convert('RGB'))
        radius=max(1,v['bloom_radius']*scale/f); glow=None
        for n,wt in ((0,.5),(1,.3),(2,.2)):
            piece=_blur_plane(bright,radius*(1+1.7*n)).point(_lut(lambda x,wt=wt:x*wt,3))
            glow=piece if glow is None else ImageChops.add(glow,piece)
        gain=v['bloom']*1.6; glow=glow.point(_lut(lambda x:min(1,x*gain),3))
        if f>1:glow=glow.resize((w,h),Image.BILINEAR)
        rgb=ImageChops.add(rgb,glow); a=ImageChops.lighter(a,glow.convert('L'))
    if v['brightness'] or v['contrast']!=1:
        c=v['contrast'];bv=v['brightness'];rgb=rgb.point(_lut(lambda x:(x-.5)*c+.5+bv,3))
    if v['saturation']!=1:rgb=Image.blend(rgb.convert('L').convert('RGB'),rgb,v['saturation']) if v['saturation']<=1 else ImageChops.add(rgb,ImageChops.subtract(rgb,rgb.convert('L').convert('RGB')).point(_lut(lambda x:min(1,x*(v['saturation']-1)),3)))
    if v['tint_amount']:
        ca=QColor(v['tint']); cb=QColor(v['tint_to']); m=clamp(v['tint_mix'],0,1); amt=v['tint_amount']
        mult=[(1-amt)+amt*(ca.red()+(cb.red()-ca.red())*m)/255,(1-amt)+amt*(ca.green()+(cb.green()-ca.green())*m)/255,(1-amt)+amt*(ca.blue()+(cb.blue()-ca.blue())*m)/255]
        pr,pg,pb=rgb.split(); rgb=Image.merge('RGB',(pr.point(_lut(lambda x:x*mult[0])),pg.point(_lut(lambda x:x*mult[1])),pb.point(_lut(lambda x:x*mult[2]))))
    if v['vignette']:rgb=ImageChops.multiply(rgb,_vignette_mask(h,w,round(v['vignette_softness'],3),round(clamp(v['vignette'],0,1),3)))
    if v['grain']:
        rs=np.random.RandomState(frame_seed&0x7fffffff); oy=int(rs.randint(0,h)); ox=int(rs.randint(0,w))
        rgb=ImageChops.add(rgb,_noise_scaled(h,w,round(v['grain'],3)).crop((ox,oy,ox+w,oy+h)),1,-128)
    rgb=ImageChops.darker(rgb,Image.merge('RGB',(a,a,a))); out=Image.merge('RGBA',(*rgb.split(),a))
    return QImage(out.tobytes('raw','BGRA'),w,h,w*4,QImage.Format_ARGB32_Premultiplied).copy()

# ---------------------------------------------------------------- floor reflection and background
def paint_background(image,scene,size):
    bg=scene.get('background')
    if not bg:return
    p=QPainter(image); w,h=size
    try:
        if bg.get('gradient'):
            colors=bg['gradient']
            if bg.get('radial'):
                cx,cy=bg.get('center',[.5,.45]); g=QRadialGradient(QPointF(cx*w,cy*h),max(w,h)*bg.get('radius',.75))
            else:
                a=math.radians(bg.get('angle',90)); g=QLinearGradient(w/2-math.cos(a)*w/2,h/2-math.sin(a)*h/2,w/2+math.cos(a)*w/2,h/2+math.sin(a)*h/2)
            for n,c in enumerate(colors):g.setColorAt(n/(len(colors)-1),QColor(c))
            p.fillRect(QRectF(0,0,w,h),QBrush(g))
        elif bg.get('color'):p.fillRect(QRectF(0,0,w,h),QColor(bg['color']))
    finally:p.end()

def reflection(image,floor,scale,canvas_h,height_px):
    """Mirror everything above the floor line into the area below it, fading with distance. Only the rows that can still be
    visible (within the fade distance) are processed."""
    h,w=image.height(),image.width(); fy=int(floor['y']/canvas_h*h)
    if fy<=1 or fy>=h-1:return None
    arr=np.frombuffer(image.constBits(),np.uint8).reshape(h,image.bytesPerLine()//4,4)[:,:w]
    fade=max(1.,floor['fade']/canvas_h*h); rows=int(min(h-fy,fade+1,fy)); 
    if rows<=0 or floor['opacity']<=0:return None
    band=arr[fy-rows:fy][::-1].astype(np.float32)
    factor=np.clip(1-np.arange(rows)/fade,0,1)*floor['opacity']
    band=(band*factor[:,None,None]).astype(np.uint8)
    pad=int(floor['blur']*scale*2)+1; blurred=blur_np(np.ascontiguousarray(band),floor['blur']*scale) if pad>2 else band
    out=np.zeros((h,w,4),np.uint8); out[fy:fy+rows]=blurred
    return image_of(out)
