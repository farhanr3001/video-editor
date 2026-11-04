"""Editable 2D compositions. The same renderer feeds the viewer and alpha export."""
import copy, json, math
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage,QPainter,QPainterPath,QTransform,QColor,QPen,QFont,QFontMetricsF,QLinearGradient
from .easing import MODES,controls
from .keyframes import value
from .image_cache import FileImageCache

_images=FileImageCache(256*1024**2,max_entries=160)  # compositions often hold dozens of thumbnails; never thrash per frame

KINDS=('group','text','rectangle','ellipse','path','image','video','polygon','polyline','grid','emitter')
CHANNELS={'x':0.,'y':0.,'scale':1.,'scale_y':1.,'rotation':0.,'opacity':100.,'width':300.,'height':180.,'trim':1.,'morph':0.,'tracking':0.,'font_size':100.,'radius':0.,'stroke_width':3.,'reveal':1.,'number':0.,'blur':0.,'blur_x':0.,'blur_y':0.,'glow_amount':1.,'rotate_x':0.,'rotate_y':0.,'follow_at':0.,'dash_offset':0.,'trim_start':0.,'entry_blur_amount':1.}
ARITY={'M':2,'L':2,'C':6,'Q':4,'Z':0}

def path_data(raw):
    if not isinstance(raw,list) or len(raw)>2048:raise ValueError('Path must contain at most 2048 commands')
    result=[]
    for command in raw:
        if not isinstance(command,list) or not command or command[0] not in ARITY or len(command)!=ARITY[command[0]]+1:raise ValueError('Use M, L, C, Q and Z path commands')
        result.append([command[0],*[finite(x) for x in command[1:]]])
    return result

def finite(v,limit=100000):
    n=float(v)
    if not math.isfinite(n) or abs(n)>limit:raise ValueError('Motion values must be finite and within ±'+str(limit))
    return n

def clean_curves(curves,channels=None):
    channels=CHANNELS if channels is None else channels
    if not isinstance(curves,dict) or any(c not in channels for c in curves):raise ValueError('Unknown motion animation channel')
    result={}
    for channel,keys in curves.items():
        if not isinstance(keys,list) or len(keys)>512:raise ValueError('At most 512 keys per channel')
        cleaned={}
        for key in keys:
            if not isinstance(key,dict) or 'time' not in key or 'value' not in key:raise ValueError('Keys require time and value')
            t=finite(key['time']); mode=key.get('interpolation','Linear')
            if mode not in MODES:raise ValueError('Unknown easing mode')
            cleaned[t]=dict(time=t,value=finite(key['value'],1e12 if channel=='number' else 100000),interpolation=mode)
            if mode=='Bezier':cleaned[t]['bezier']=controls(key.get('bezier'))
        result[channel]=[cleaned[t] for t in sorted(cleaned)]
    return result

def validate(raw):
    if not isinstance(raw,dict):raise ValueError('Composition must be an object')
    scene=copy.deepcopy(raw)
    if scene.get('version',1)!=1:raise ValueError('Unsupported motion composition version')
    scene['version']=1
    if 'sound_cues' in scene:
        from .motion_audio import validate as validate_cues
        scene['sound_cues']=validate_cues(scene['sound_cues'])
    canvas=scene.get('canvas',[1080,1920])
    if not isinstance(canvas,list) or len(canvas)!=2 or any(not 1<=finite(v)<=8192 for v in canvas):raise ValueError('Canvas must contain two dimensions in 1–8192')
    scene['canvas']=list(map(float,canvas))
    if not isinstance(scene.get('nodes',[]),list) or len(scene.get('nodes',[]))>256:raise ValueError('Composition supports at most 256 layers')
    nodes=scene.setdefault('nodes',[]); ids=set()
    for node in nodes:
        if not isinstance(node,dict) or not isinstance(node.get('id'),str) or not node['id'] or node['id'] in ids:raise ValueError('Every layer needs a unique ID')
        ids.add(node['id'])
        if not isinstance(node.get('parent',''),str):raise ValueError('Parent must be a layer ID')
        if node.get('kind') not in KINDS:raise ValueError('Unknown motion layer kind')
        for key in (*CHANNELS,'start','end','stroke_width','radius','anchor_x','anchor_y','stagger','entry_duration','entry_y','entry_rotation','entry_scale'):
            if key in node:node[key]=finite(node[key],1e12 if key=='number' else 100000)
        if node.get('end',1e5)<node.get('start',0):raise ValueError('Layer end precedes its start')
        if 'path' in node:node['path']=path_data(node['path'])
        if 'path_to' in node:
            node['path_to']=path_data(node['path_to'])
            if [c[0] for c in node.get('path',[])]!=[c[0] for c in node['path_to']]:raise ValueError('Morph paths must have matching command structure')
        if 'mask' in node:
            if not isinstance(node['mask'],dict) or node['mask'].get('kind','rectangle') not in ('rectangle','ellipse','path'):raise ValueError('Mask must be rectangle, ellipse or path')
            for key in CHANNELS:
                if key in node['mask']:node['mask'][key]=finite(node['mask'][key])
            if 'path' in node['mask']:node['mask']['path']=path_data(node['mask']['path'])
            if 'path_to' in node['mask']:
                node['mask']['path_to']=path_data(node['mask']['path_to'])
                if [c[0] for c in node['mask'].get('path',[])]!=[c[0] for c in node['mask']['path_to']]:raise ValueError('Mask morph paths must have matching command structure')
            node['mask']['keyframes']=clean_curves(node['mask'].get('keyframes',{}))
        if node.get('kind')=='text' and (not isinstance(node.get('text',''),str) or len(node.get('text',''))>4096):raise ValueError('Text layer exceeds 4096 characters')
        if node.get('text_mode','none') not in ('none','character','word','typewriter','counter','rolling'):raise ValueError('Unknown text animation mode')
        if node.get('image_fit','stretch') not in ('stretch','contain','cover'):raise ValueError('Image fit must be stretch, contain or cover')
        if node.get('text_align','center') not in ('left','center','right'):raise ValueError('Text alignment must be left, center or right')
        for key in ('caret_period',):
            if key in node:node[key]=finite(node[key])
        if not .1<=node.get('caret_period',.8)<=10:raise ValueError('Caret period must be .1–10 seconds')
        for key in ('caret','number_grouping','number_trim_zeros'):
            if key in node and not isinstance(node[key],bool):raise ValueError(key+' must be boolean')
        if 'number_decimals' in node:
            v=finite(node['number_decimals'])
            if v!=int(v) or not 0<=v<=6:raise ValueError('Counter decimals must be 0–6')
            node['number_decimals']=int(v)
        for key in ('number_prefix','number_suffix'):
            if key in node and (not isinstance(node[key],str) or len(node[key])>256):raise ValueError('Counter prefix/suffix must be short text')
        if 'shadow' in node:
            from .motion_shadow import validate_shadow
            node['shadow']=validate_shadow(node['shadow'])
        if node.get('entry_easing','Ease Out') not in MODES:raise ValueError('Unknown text easing mode')
        if node.get('entry_easing')=='Bezier':node['entry_bezier']=controls(node.get('entry_bezier'))
        for key in ('fill','stroke','font','source'):
            if key in node and not isinstance(node[key],str):raise ValueError(key+' must be text')
        if 'gradient' in node and (not isinstance(node['gradient'],list) or not 2<=len(node['gradient'])<=16 or any(not isinstance(v,str) for v in node['gradient'])):raise ValueError('Gradient requires 2–16 colour strings')
        node['keyframes']=clean_curves(node.get('keyframes',{}))
        from .motion_fx import validate_node
        validate_node(node)
    by_id={n['id']:n for n in nodes}
    for node in nodes:
        f=node.get('follow')
        if f:
            target=by_id.get(f['path'])
            if not target or target['id']==node['id'] or target.get('parent','')!=node.get('parent',''):raise ValueError('follow must name another layer with the same parent')
            if target.get('kind') not in ('path','polyline','ellipse','rectangle','polygon'):raise ValueError('follow target must be a shape or path layer')
    for node in nodes:
        seen={node['id']}; parent=node.get('parent',''); depth=0
        while parent:
            if parent not in by_id or parent in seen:raise ValueError('Parent must exist without a cycle')
            seen.add(parent); depth+=1
            if depth>16:raise ValueError('Composition nesting is limited to 16 levels')
            parent=by_id[parent].get('parent','')
    from .motion_fx import validate_scene_extras
    validate_scene_extras(scene,finite,clean_curves)
    blur=scene.setdefault('motion_blur',{})
    if not isinstance(blur,dict):raise ValueError('Motion blur must be an object')
    blur['samples']=max(1,min(12,int(finite(blur.get('samples',1)))))
    blur['shutter']=max(0,min(360,finite(blur.get('shutter',180))))
    if scene.get('sound_cues'):
        from .motion_audio import at
        if any(at(cue,scene) is None for cue in scene['sound_cues']):raise ValueError('A sound cue references a missing layer/keyframe. Remove or rebind the cue.')
    return scene

def default_scene(canvas=(1080,1920)):
    width,height=canvas
    return {'version':1,'canvas':list(canvas),'nodes':[{'id':'headline','kind':'text','text':'MAKE IT MOVE','x':width/2,'y':height/2,'font_size':width/11,'fill':'#e8ff69','font':'Arial','bold':True,'text_mode':'character','stagger':.045,'entry_duration':.45,'entry_y':height/20,'entry_easing':'Back Out'}],'motion_blur':{'samples':1,'shutter':180}}

def curve(node,name,t):return value(node.get('keyframes',{}).get(name,[]),t,node.get(name,CHANNELS[name]))

def make_path(commands):
    p=QPainterPath(); p.setFillRule(Qt.WindingFill)  # SVG nonzero, same as the GPU renderer
    for c in commands:
        kind,*v=c
        if kind=='M':p.moveTo(*v)
        elif kind=='L':p.lineTo(*v)
        elif kind=='C':p.cubicTo(*v)
        elif kind=='Q':p.quadTo(*v)
        else:p.closeSubpath()
    return p

def geometry(node,t,full=False):
    from . import motion_fx as fx
    kind=node.get('kind','rectangle'); w=max(.01,curve(node,'width',t)); h=max(.01,curve(node,'height',t)); p=QPainterPath()
    if kind=='path':
        commands=node.get('path',[]); other=node.get('path_to')
        if other:
            mix=max(0,min(1,curve(node,'morph',t)))
            commands=[[a[0],*[x+(y-x)*mix for x,y in zip(a[1:],b[1:])]] for a,b in zip(commands,other)]
        p=make_path(commands)
    elif kind=='ellipse':p.addEllipse(QRectF(-w/2,-h/2,w,h))
    elif kind=='polygon':p=fx.polygon_path(node.get('sides',5),w,h,node.get('inner',0))
    elif kind=='polyline':p=fx.polyline_path(node.get('points',[[0,0],[1,0]]),node.get('smooth',False),node.get('closed',False))
    elif kind=='grid':p=fx.grid_path(w,h,node.get('cell',60))
    else:p.addRoundedRect(QRectF(-w/2,-h/2,w,h),max(0,curve(node,'radius',t)),max(0,curve(node,'radius',t)))
    if full:return p
    trim=max(0,min(1,curve(node,'trim',t))); start=max(0,min(1,curve(node,'trim_start',t)))
    if trim<1 or start>0:p=fx.trimmed(p,start,trim)
    return p

# Vector text uses unhinted outlines: hinting snaps glyphs to a pixel grid (wrong once outlines are scaled/animated), and on
# Windows a failing hinting program in some fonts (e.g. Newsreader "g") makes the system engine return no outline at all.
def run_styles(node):
    """Per-character (font, bold, italic, size factor) from rich-text runs, or None when every character uses the layer style."""
    runs=node.get('runs')
    if not runs or not any(key in run for run in runs for key in ('italic','bold','font','size')):return None
    base=(node.get('font','Arial'),bool(node.get('bold',True)),bool(node.get('italic',False)),1.)
    out=[]
    for run in runs:out.extend([(run.get('font',base[0]),bool(run.get('bold',base[1])),bool(run.get('italic',base[2])),float(run.get('size',1.)))]*len(run.get('text','')))
    return tuple(out) if len(out)==len(node.get('text','')) else None

def text_parts(text,font_name,size,bold,mode,tracking,alignment='center',italic=False,styles=None):
    """Outline paths of each text token (line, word or character), centred on the layer origin. `styles` (see run_styles)
    lets single words use their own font/bold/italic/size in one layer. Cached: identical text costs nothing per frame."""
    return tuple(QPainterPath(path) for path in _text_parts(text,font_name,round(float(size),3),bool(bold),mode,round(float(tracking),3),alignment,bool(italic),styles))

@lru_cache(maxsize=1024)
def _text_parts(text,font_name,size,bold,mode,tracking,alignment,italic,styles):
    fonts={}
    def font(style):
        if style not in fonts:
            name,b,it,factor=style; f=QFont(name); f.setPixelSize(max(1,round(size*factor))); f.setHintingPreference(QFont.PreferNoHinting)
            f.setBold(b); f.setItalic(it); f.setLetterSpacing(QFont.AbsoluteSpacing,tracking); fonts[style]=(f,QFontMetricsF(f))
        return fonts[style]
    base=(font_name,bold,italic,1.); per=styles if styles and len(styles)==len(text) else (base,)*len(text)
    rows=[]; pos=0
    for line in text.split('\n'):
        style=per[pos:pos+len(line)]; pos+=len(line)+1
        xs=[0.]*(len(line)+1); i=0
        # Measure inside each same-style segment so kerning is preserved within a style.
        while i<len(line):
            j=i
            while j<len(line) and style[j]==style[i]:j+=1
            metrics=font(style[i])[1]
            for q in range(i+1,j+1):xs[q]=xs[i]+metrics.horizontalAdvance(line[i:q])
            i=j
        used=set(style) or {base}
        rows.append((line,style,xs,max(font(s)[1].ascent() for s in used),max(font(s)[1].height() for s in used)))
    parts=[]; y=-sum(row[4] for row in rows)/2
    for line,style,xs,ascent,height in rows:
        tokens=(line.split(' ') if mode=='word' else list(line)) if mode!='none' else [line]
        strings=[token+(' ' if mode=='word' and n<len(tokens)-1 else '') for n,token in enumerate(tokens)]
        total=xs[-1]; offset=0 if alignment=='left' else total if alignment=='right' else total/2; baseline=y+ascent; c=0
        for token in strings:
            path=QPainterPath(); i=c
            while i<c+len(token):
                j=i
                while j<c+len(token) and style[j]==style[i]:j+=1
                path.addText(QPointF(xs[i]-offset,baseline),font(style[i])[0],line[i:j]); i=j
            parts.append(path); c+=len(token)
        y+=height
    return tuple(parts)

def token_fills(node,text,mode,count):
    """Fill colour of each text token, from the layer's rich-text runs."""
    runs=node.get('runs')
    if not runs:return None
    per_char=[]
    for run in runs:per_char.extend([run.get('fill') or node.get('fill','#ffffff')]*len(run['text']))
    fills=[]; pos=0
    for line in text.split('\n'):
        tokens=line.split(' ') if mode=='word' else list(line)
        for token in tokens:
            fills.append(per_char[pos] if pos<len(per_char) else node.get('fill','#ffffff')); pos+=len(token)+(1 if mode=='word' else 0)
        pos+=1
    return fills if len(fills)==count else None

def draw_text(painter,node,t):
    from .easing import ease
    from . import motion_fx as fx
    mode=node.get('text_mode','none')
    if mode=='rolling':
        from .motion_text import draw_rolling
        draw_rolling(painter,node,t); return
    if mode=='typewriter':
        from .motion_text import draw_typewriter
        draw_typewriter(painter,node,t); return
    text=node.get('text','')
    if mode=='counter':
        from .motion_text import counter_text
        text=counter_text(node,t); mode='none'
    static=mode=='none'; build_mode='character' if (static and node.get('runs')) else mode
    paths=text_parts(text,node.get('font','Arial'),curve(node,'font_size',t),bool(node.get('bold',True)),build_mode,curve(node,'tracking',t),node.get('text_align','center'),bool(node.get('italic',False)),run_styles(node))
    fills=token_fills(node,text,build_mode,len(paths))
    duration=max(.001,node.get('entry_duration',.4)); stagger=max(0,node.get('stagger',.04)); local=t-node.get('start',0)
    blur_in=node.get('entry_blur',0)*curve(node,'entry_blur_amount',t)
    for n,path in enumerate(paths):
        q=1. if static else max(0,min(1,(local-n*stagger)/duration))
        if q<=0:continue
        amount=ease(q,node.get('entry_easing','Ease Out'),node.get('entry_bezier'))
        painter.save(); painter.setOpacity(painter.opacity()*q)
        centre=path.boundingRect().center(); painter.translate(centre)
        painter.translate(0,node.get('entry_y',60)*(1-amount)); painter.rotate(node.get('entry_rotation',0)*(1-amount))
        scale=node.get('entry_scale',.85)+(1-node.get('entry_scale',.85))*amount; painter.scale(scale,scale); painter.translate(-centre)
        if fills:painter.setBrush(QColor(fills[n]))
        blur=blur_in*(1-amount)
        if blur>.4 and not static:fx.draw_blurred_path(painter,path,blur,painter.brush(),painter.pen())
        else:painter.drawPath(path)
        painter.restore()

def _extent(node,t):
    """Approximate laid-out size of a layer for stack layout (width, height) in its parent's units."""
    kind=node.get('kind')
    if kind=='text':
        f=QFont(node.get('font','Arial')); f.setPixelSize(max(1,round(curve(node,'font_size',t)))); f.setBold(bool(node.get('bold',True))); f.setItalic(bool(node.get('italic',False)))
        m=QFontMetricsF(f); lines=node.get('text','').split('\n')
        return max(m.horizontalAdvance(line) for line in lines)*abs(curve(node,'scale',t)),m.height()*len(lines)*node.get('line_height',1.)*abs(curve(node,'scale_y',t))
    if kind=='group' and 'height' not in node and 'height' not in node.get('keyframes',{}):return 0.,0.
    return curve(node,'width',t)*abs(curve(node,'scale',t)),curve(node,'height',t)*abs(curve(node,'scale_y',t))

def _presence(node,t,reflow):
    """0..1 share of a stack slot: grows in when the layer starts and shrinks when it ends, so the stack reflows smoothly."""
    start=node.get('start',0); end=node.get('end',1e9)
    if t<start or t>=end:return 0.
    if reflow<=0:return 1.
    q=max(0.,min(1.,min(t-start,end-t)/reflow)); return q*q*(3-2*q)

def stack_offset(node,t,by_id):
    """Offset of a child of a group with layout={'type':'stack',...}: children are arranged along the axis, centred on the
    group origin, with the gap between them; layers that have not started yet take no space and slide the others smoothly."""
    parent=by_id.get(node.get('parent',''))
    layout=parent.get('layout') if parent else None
    if not isinstance(layout,dict) or layout.get('type')!='stack':return 0.,0.
    vertical=layout.get('direction','vertical')!='horizontal'; gap=float(layout.get('gap',24)); reflow=float(layout.get('reflow',.35))
    siblings=[n for n in by_id.values() if n.get('parent','')==parent['id'] and n.get('visible',True)]
    cursor=0.; centres={}; first=True
    for n in siblings:
        size=_extent(n,t)[1 if vertical else 0]; p=_presence(n,t,reflow)
        lead=0. if first else gap
        if p>0:cursor+=lead*p
        # An appearing layer sits in its full final slot (just past the previous one); the others glide to make room.
        centres[n['id']]=cursor+lead*(1-p)+size/2; cursor+=size*p; first=first and p<=0
    c=centres.get(node['id'],cursor/2)-cursor/2
    return (0.,c) if vertical else (c,0.)

def node_origin(node,t,by_id):
    """Local x,y,extra rotation of a layer, including a follow-path binding and its parent's stack layout."""
    dx,dy=stack_offset(node,t,by_id)
    x=curve(node,'x',t)+dx; y=curve(node,'y',t)+dy; extra=0.
    f=node.get('follow')
    if f and f['path'] in by_id:
        target=by_id[f['path']]; path=geometry(target,t,full=True)
        if not path.isEmpty():
            p=max(0,min(1,curve(node,'follow_at',t))); percent=path.percentAtLength(path.length()*p)
            m=QTransform(); m.translate(curve(target,'x',t),curve(target,'y',t)); m.rotate(curve(target,'rotation',t)); m.scale(curve(target,'scale',t),curve(target,'scale_y',t)); m.translate(-target.get('anchor_x',0),-target.get('anchor_y',0))
            point=m.map(path.pointAtPercent(percent)); x+=point.x(); y+=point.y()
            if f.get('orient'):extra=-path.angleAtPercent(percent)+curve(target,'rotation',t)+f.get('offset',0)
            else:extra=f.get('offset',0)
    return x,y,extra

def node_matrix(node,t,by_id):
    """Full parent-to-canvas transform of a layer (without camera), used by trails and editor hit tests."""
    chain=[]; current=node; seen=set()
    while current is not None and current['id'] not in seen:
        chain.append(current); seen.add(current['id']); current=by_id.get(current.get('parent',''))
    m=QTransform()
    for item in reversed(chain):
        x,y,extra=node_origin(item,t,by_id); m.translate(x,y); m.rotate(curve(item,'rotation',t)+extra); m.scale(curve(item,'scale',t),curve(item,'scale_y',t)); m.translate(-item.get('anchor_x',0),-item.get('anchor_y',0))
    return m

_frames=__import__('collections').OrderedDict(); _frame_bytes=[0]
FRAME_CACHE_BYTES=256*1024**2

def draw(scene,t,size,fps=60):
    """Render an RGBA frame (cached: repeated requests for the same scene/time/size, such as panning or pausing, are free)."""
    def stamp(path):
        try:st=Path(path).stat(); return (st.st_mtime_ns,st.st_size)
        except (OSError,TypeError,ValueError):return None
    try:key=(hash(json.dumps(scene,sort_keys=True,default=str)),tuple(stamp(n['source']) for n in scene.get('nodes',[]) if isinstance(n,dict) and n.get('source')),round(float(t),6),int(size[0]),int(size[1]),round(float(fps),3))
    except (TypeError,ValueError):return draw_uncached(scene,t,size,fps)
    image=_frames.get(key)
    if image is not None:
        _frames.move_to_end(key); return image
    image=draw_uncached(scene,t,size,fps); cost=image.sizeInBytes()
    if cost<FRAME_CACHE_BYTES//2:
        _frames[key]=image; _frame_bytes[0]+=cost
        while _frame_bytes[0]>FRAME_CACHE_BYTES and _frames:
            _,old=_frames.popitem(last=False); _frame_bytes[0]-=old.sizeInBytes()
    return image

def draw_uncached(scene,t,size,fps=60):
    """Render an RGBA frame; shutter samples are averaged in premultiplied space."""
    from . import motion_fx as fx
    width,height=map(int,size); blur=scene.get('motion_blur',{}); samples=blur.get('samples',1)
    shutter=blur.get('shutter',180)/360/max(1,fps)
    if samples<=1 or not shutter:image=draw_sample(scene,t,(width,height))
    else:
        import numpy as np
        total=np.zeros((height,width,4),dtype=np.float32)
        for n in range(samples):
            frame=draw_sample(scene,max(0,t-shutter*(n+.5)/samples),(width,height))
            total+=np.frombuffer(frame.constBits(),np.uint8).reshape(height,frame.bytesPerLine()//4,4)[:,:width]
        pixels=np.rint(total/samples).astype(np.uint8)
        image=QImage(pixels.data,width,height,width*4,QImage.Format_ARGB32_Premultiplied).copy()
    values=fx.post_values(scene,t)
    if values:image=fx.apply_post(image,values,width/max(1,scene.get('canvas',[1080,1920])[0]),int(round(t*max(1,fps))))
    return image

def draw_sample(scene,t,size):
    from . import motion_fx as fx
    width,height=size; canvas=scene.get('canvas',[1080,1920]); k=width/max(1,canvas[0])
    image=QImage(width,height,QImage.Format_ARGB32_Premultiplied); image.fill(Qt.transparent)
    fx.paint_background(image,scene,(width,height))
    floor=scene.get('floor')
    if floor and floor.get('enabled',True):
        layer=QImage(width,height,QImage.Format_ARGB32_Premultiplied); layer.fill(Qt.transparent)
        paint_nodes(scene,t,layer,lambda node:node.get('reflect',True))
        mirrored=fx.reflection(layer,floor,k,canvas[1],height)
        if mirrored is not None:
            p=QPainter(image); p.drawImage(0,0,mirrored); p.end()
    paint_nodes(scene,t,image,lambda node:True)
    return image

def paint_nodes(scene,t,image,include):
    from . import motion_fx as fx
    width,height=image.width(),image.height(); canvas=scene.get('canvas',[1080,1920])
    painter=QPainter(image); painter.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing|QPainter.SmoothPixmapTransform); painter.scale(width/max(1,canvas[0]),height/max(1,canvas[1]))
    nodes=scene.get('nodes',[]); children={}; by_id={n['id']:n for n in nodes}
    for node in nodes:children.setdefault(node.get('parent',''),[]).append(node)
    def content(node,p):
        fill=node.get('fill','#ffffff'); gradient=node.get('gradient'); kind=node['kind']
        w=curve(node,'width',t); h=curve(node,'height',t)
        trail=node.get('trail')
        if trail:draw_trail(node,p)
        p.setBrush(fx.make_brush(node,w,h,fill,gradient)); stroke=node.get('stroke','none'); sw=max(0,curve(node,'stroke_width',t))
        p.setPen(fx.make_pen(node,stroke,sw,curve(node,'dash_offset',t)))
        if kind=='text':draw_text(p,node,t)
        elif kind in ('image','video'):
            if kind=='video':
                from .motion_video import FRAMES,source_time
                try:pic=FRAMES.image(node.get('source',''),source_time(node,t))
                except Exception:pic=QImage()
            else:pic=_images.load(node.get('source',''))
            if not pic.isNull():
                iw=max(.01,w); ih=max(.01,h); rect=QRectF(-iw/2,-ih/2,iw,ih)
                fit=node.get('image_fit','cover' if kind=='video' else 'stretch')
                if fit!='stretch':
                    factor=(min if fit=='contain' else max)(iw/pic.width(),ih/pic.height())
                    rect=QRectF(-pic.width()*factor/2,-pic.height()*factor/2,pic.width()*factor,pic.height()*factor)
                    if fit=='cover':p.setClipRect(QRectF(-iw/2,-ih/2,iw,ih),Qt.IntersectClip)
                p.drawImage(rect,pic)
        elif kind=='emitter':fx.draw_emitter(p,node,t)
        elif kind!='group':
            shape=geometry(node,t)
            if node.get('shadow',{}).get('enabled',False):
                from .motion_shadow import paint_shadow
                paint_shadow(p,shape,node['shadow'],fill!='none' or bool(gradient),sw if stroke!='none' else 0)
            p.drawPath(shape)
        for child in children.get(node['id'],[]):render(child,p)
    def draw_trail(node,p):
        r=node['trail']; now=node_matrix(node,t,by_id); inverse,ok=now.inverted()
        if not ok:return
        n=r['samples']; points=[]
        for i in range(n+1):
            tt=max(0,t-r['length']*i/n); x,y,_=node_origin(node,tt,by_id); parent=by_id.get(node.get('parent',''))
            pm=node_matrix(parent,tt,by_id) if parent else QTransform()
            points.append(inverse.map(pm.map(QPointF(x,y))))
        base=r.get('color') or (node.get('fill') if node.get('fill','none')!='none' else node.get('stroke','#ffffff'))
        p.save()
        try:
            if r['additive']:p.setCompositionMode(QPainter.CompositionMode_Plus)
            for i in range(n):
                u=i/n; c=QColor(base); c.setAlphaF(max(0,min(1,(1-u)**r['fade'])))
                p.setPen(QPen(c,max(.3,r['width']*(1-u)**r['taper']),Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin)); p.drawLine(points[i],points[i+1])
        finally:p.restore()
    def render(node,p,root=False):
        if not node.get('visible',True) or not node.get('start',0)<=t<node.get('end',1e5):return
        if not include(node) and root:return
        p.save()
        try:
            if root:
                cam=fx.camera_transform(scene,t,node.get('depth',1.),canvas)
                if cam:p.setTransform(cam,True)
            x,y,extra=node_origin(node,t,by_id); p.translate(x,y)
            s=node.get('stretch')
            if s:
                h=1/240; x0,y0,_=node_origin(node,t-h,by_id); x1,y1,_=node_origin(node,t+h,by_id); vx=(x1-x0)/(2*h); vy=(y1-y0)/(2*h); speed=math.hypot(vx,vy)
                f=1+min(s['max'],s['amount']*speed)
                if f>1.001:
                    ang=math.degrees(math.atan2(vy,vx)); p.rotate(ang); p.scale(f,1/math.sqrt(f) if s['squash'] else 1); p.rotate(-ang)
            p.rotate(curve(node,'rotation',t)+extra)
            p.scale(curve(node,'scale',t),curve(node,'scale_y',t))
            rx=curve(node,'rotate_x',t); ry=curve(node,'rotate_y',t)
            if rx or ry:
                tilt=QTransform(); tilt.rotate(rx,Qt.XAxis); tilt.rotate(ry,Qt.YAxis); p.setTransform(tilt,True)
            p.translate(-node.get('anchor_x',0),-node.get('anchor_y',0))
            p.setOpacity(p.opacity()*max(0,min(1,curve(node,'opacity',t)/100)))
            mask=node.get('mask'); feather=None
            if mask:
                transform=QTransform(); transform.translate(curve(mask,'x',t),curve(mask,'y',t)); transform.rotate(curve(mask,'rotation',t)); transform.scale(curve(mask,'scale',t),curve(mask,'scale_y',t))
                path=transform.map(geometry(mask,t)); invert=bool(mask.get('invert'))
                if mask.get('feather',0)>0:feather=(path,mask['feather'],invert)
                else:
                    if invert:
                        full=QPainterPath(); full.addRect(QRectF(-1e5,-1e5,2e5,2e5)); path=full.subtracted(path)
                    p.setClipPath(path,Qt.IntersectClip)
            blur=curve(node,'blur',t); glow=curve(node,'glow_amount',t)
            if fx.needs_layer(node,feather[1] if feather else 0,blur):
                fx.render_layer(p,node,lambda lp:content(node,lp),blur,glow,feather)
            else:
                if node.get('blend','normal')!='normal':p.setCompositionMode(fx.BLENDS[node['blend']])
                content(node,p)
        finally:p.restore()
    try:
        for node in children.get('',[]):render(node,painter,True)
    finally:painter.end()

def schema():
    return dict(version=1,kinds=KINDS,channels=CHANNELS,easing=MODES,path_commands=ARITY,
                sound_cues=dict(fields=['id','source','time','in_point','duration','source_duration','gain_db','enabled','event','node_id','channel','key_time'],events=['time','layer_start','layer_end','keyframe'],coordinates='Composition source seconds. Up to 128 cues; gain -60–0 dB. Local source files remain external, portable paths are rebased with the project.'),
                guidance='Coordinates: scale is horizontal and scale_y vertical (key both for uniform pops); mask geometry is layer-local; text x,y is the line-box centre; fill none (not null) for stroke-only paths, stroke is a colour with stroke_width; path fill is nonzero. Rich text runs may set italic, bold, font, size (factor), fill. Groups may have layout={type:stack,direction,gap,reflow}. Kind video: source,in_point,speed,loop,image_fit. Channels blur_x/blur_y blur along one axis. Large scenes: motion_scene_file; previews: get_motion_contact_sheet; assets: motion_assets. Nodes use scene canvas pixels; parent IDs form groups. Key times are composition source seconds (clip in_point + local timeline time * speed). Text: text_mode character/word/typewriter/counter/rolling, text_align left/center/right. Rolling animates digits in text over entry_duration and settles to that exact text. Typewriter uses stagger seconds/grapheme or reveal 0–1 keys, optional caret/caret_period. Counters use number keys, number_decimals/grouping/prefix/suffix. Images: source path and image_fit contain/cover/stretch; existing images default stretch for compatibility. radius/stroke_width animate. Shape shadow: enabled, color, opacity, blur, x, y. Mask uses local geometry. Path trim 0–1 and matching path_to/morph. motion_blur samples 1–12, shutter 0–360. Templates are scene JSON. Presets are ordinary editable scenes with exposed parameters.')
