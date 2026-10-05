"""Editable 2D compositions. The same renderer feeds the viewer and alpha export."""
import copy, json, math
from functools import lru_cache
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage,QPainter,QPainterPath,QTransform,QColor,QPen,QFont,QFontMetricsF,QLinearGradient
from .easing import MODES,controls
from .keyframes import value
from .image_cache import FileImageCache

_images=FileImageCache(64*1024**2,max_entries=16)

KINDS=('group','text','rectangle','ellipse','path','image')
CHANNELS={'x':0.,'y':0.,'scale':1.,'scale_y':1.,'rotation':0.,'opacity':100.,'width':300.,'height':180.,'trim':1.,'morph':0.,'tracking':0.,'font_size':100.}
ARITY={'M':2,'L':2,'C':6,'Q':4,'Z':0}

def path_data(raw):
    if not isinstance(raw,list) or len(raw)>2048:raise ValueError('Path must contain at most 2048 commands')
    result=[]
    for command in raw:
        if not isinstance(command,list) or not command or command[0] not in ARITY or len(command)!=ARITY[command[0]]+1:raise ValueError('Use M, L, C, Q and Z path commands')
        result.append([command[0],*[finite(x) for x in command[1:]]])
    return result

def finite(v):
    n=float(v)
    if not math.isfinite(n) or abs(n)>100000:raise ValueError('Motion values must be finite and within -100000–100000')
    return n

def clean_curves(curves):
    if not isinstance(curves,dict) or any(c not in CHANNELS for c in curves):raise ValueError('Unknown motion animation channel')
    result={}
    for channel,keys in curves.items():
        if not isinstance(keys,list) or len(keys)>512:raise ValueError('At most 512 keys per channel')
        cleaned={}
        for key in keys:
            if not isinstance(key,dict) or 'time' not in key or 'value' not in key:raise ValueError('Keys require time and value')
            t=finite(key['time']); mode=key.get('interpolation','Linear')
            if mode not in MODES:raise ValueError('Unknown easing mode')
            cleaned[t]=dict(time=t,value=finite(key['value']),interpolation=mode)
            if mode=='Bezier':cleaned[t]['bezier']=controls(key.get('bezier'))
        result[channel]=[cleaned[t] for t in sorted(cleaned)]
    return result

def validate(raw):
    if not isinstance(raw,dict):raise ValueError('Composition must be an object')
    scene=copy.deepcopy(raw)
    if scene.get('version',1)!=1:raise ValueError('Unsupported motion composition version')
    scene['version']=1
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
            if key in node:node[key]=finite(node[key])
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
        if node.get('text_mode','none') not in ('none','character','word'):raise ValueError('Text mode must be none, character or word')
        if node.get('entry_easing','Ease Out') not in MODES:raise ValueError('Unknown text easing mode')
        if node.get('entry_easing')=='Bezier':node['entry_bezier']=controls(node.get('entry_bezier'))
        for key in ('fill','stroke','font','source'):
            if key in node and not isinstance(node[key],str):raise ValueError(key+' must be text')
        if 'gradient' in node and (not isinstance(node['gradient'],list) or not 2<=len(node['gradient'])<=16 or any(not isinstance(v,str) for v in node['gradient'])):raise ValueError('Gradient requires 2–16 colour strings')
        node['keyframes']=clean_curves(node.get('keyframes',{}))
    by_id={n['id']:n for n in nodes}
    for node in nodes:
        seen={node['id']}; parent=node.get('parent',''); depth=0
        while parent:
            if parent not in by_id or parent in seen:raise ValueError('Parent must exist without a cycle')
            seen.add(parent); depth+=1
            if depth>16:raise ValueError('Composition nesting is limited to 16 levels')
            parent=by_id[parent].get('parent','')
    blur=scene.setdefault('motion_blur',{})
    if not isinstance(blur,dict):raise ValueError('Motion blur must be an object')
    blur['samples']=max(1,min(12,int(finite(blur.get('samples',1)))))
    blur['shutter']=max(0,min(360,finite(blur.get('shutter',180))))
    return scene

def default_scene(canvas=(1080,1920)):
    width,height=canvas
    return {'version':1,'canvas':list(canvas),'nodes':[{'id':'headline','kind':'text','text':'MAKE IT MOVE','x':width/2,'y':height/2,'font_size':width/11,'fill':'#e8ff69','font':'Arial','bold':True,'text_mode':'character','stagger':.045,'entry_duration':.45,'entry_y':height/20,'entry_easing':'Back Out'}],'motion_blur':{'samples':1,'shutter':180}}

def curve(node,name,t):return value(node.get('keyframes',{}).get(name,[]),t,node.get(name,CHANNELS[name]))

def make_path(commands):
    p=QPainterPath()
    for c in commands:
        kind,*v=c
        if kind=='M':p.moveTo(*v)
        elif kind=='L':p.lineTo(*v)
        elif kind=='C':p.cubicTo(*v)
        elif kind=='Q':p.quadTo(*v)
        else:p.closeSubpath()
    return p

def geometry(node,t):
    kind=node.get('kind','rectangle'); w=max(.01,curve(node,'width',t)); h=max(.01,curve(node,'height',t)); p=QPainterPath()
    if kind=='path':
        commands=node.get('path',[]); other=node.get('path_to')
        if other:
            mix=max(0,min(1,curve(node,'morph',t)))
            commands=[[a[0],*[x+(y-x)*mix for x,y in zip(a[1:],b[1:])]] for a,b in zip(commands,other)]
        p=make_path(commands)
    elif kind=='ellipse':p.addEllipse(QRectF(-w/2,-h/2,w,h))
    else:p.addRoundedRect(QRectF(-w/2,-h/2,w,h),max(0,node.get('radius',0)),max(0,node.get('radius',0)))
    trim=max(0,min(1,curve(node,'trim',t)))
    if trim<1:
        partial=QPainterPath(); length=p.length(); samples=max(2,min(512,math.ceil(length*trim/3)))
        for n in range(samples+1):
            point=p.pointAtPercent(p.percentAtLength(length*trim*n/samples))
            if n:partial.lineTo(point)
            else:partial.moveTo(point)
        p=partial
    return p

@lru_cache(maxsize=128)
def text_parts(text,font_name,size,bold,mode,tracking):
    font=QFont(font_name); font.setPixelSize(max(1,round(size))); font.setBold(bold); font.setLetterSpacing(QFont.AbsoluteSpacing,tracking)
    metrics=QFontMetricsF(font); parts=[]; y=0.; widest=0.
    for line in text.split('\n'):
        tokens=(line.split(' ') if mode=='word' else list(line)) if mode!='none' else [line]
        strings=[token+(' ' if mode=='word' and n<len(tokens)-1 else '') for n,token in enumerate(tokens)]
        # Measure prefixes in one font/coordinate space; preserve kerning at token boundaries.
        widths=[metrics.horizontalAdvance(''.join(strings[:n])) for n in range(len(strings)+1)]
        total=widths[-1]; widest=max(widest,total)
        for n,token in enumerate(strings):
            path=QPainterPath(); path.addText(QPointF(widths[n]-total/2,y),font,token); parts.append(path)
        y+=metrics.height()
    offset=metrics.ascent()-(max(1,len(text.split('\n')))*metrics.height())/2
    for path in parts:path.translate(0,offset)
    return tuple(parts)

def draw_text(painter,node,t):
    from .easing import ease
    mode=node.get('text_mode','none'); paths=text_parts(node.get('text',''),node.get('font','Arial'),curve(node,'font_size',t),bool(node.get('bold',True)),mode,curve(node,'tracking',t))
    duration=max(.001,node.get('entry_duration',.4)); stagger=max(0,node.get('stagger',.04)); local=t-node.get('start',0)
    for n,path in enumerate(paths):
        q=max(0,min(1,(local-n*stagger)/duration)) if mode!='none' else 1.
        if q<=0:continue
        amount=ease(q,node.get('entry_easing','Ease Out'),node.get('entry_bezier'))
        painter.save(); painter.setOpacity(painter.opacity()*q)
        centre=path.boundingRect().center(); painter.translate(centre)
        painter.translate(0,node.get('entry_y',60)*(1-amount)); painter.rotate(node.get('entry_rotation',0)*(1-amount))
        scale=node.get('entry_scale',.85)+(1-node.get('entry_scale',.85))*amount; painter.scale(scale,scale); painter.translate(-centre)
        painter.drawPath(path); painter.restore()

def draw(scene,t,size,fps=60):
    """Render an RGBA frame; shutter samples are averaged in premultiplied space."""
    width,height=map(int,size); blur=scene.get('motion_blur',{}); samples=blur.get('samples',1)
    shutter=blur.get('shutter',180)/360/max(1,fps)
    if samples<=1 or not shutter:return draw_sample(scene,t,(width,height))
    import numpy as np
    total=np.zeros((height,width,4),dtype=np.float32)
    for n in range(samples):
        image=draw_sample(scene,max(0,t-shutter*(n+.5)/samples),(width,height))
        total+=np.frombuffer(image.constBits(),np.uint8).reshape(height,image.bytesPerLine()//4,4)[:,:width]
    pixels=np.rint(total/samples).astype(np.uint8)
    return QImage(pixels.data,width,height,width*4,QImage.Format_ARGB32_Premultiplied).copy()

def draw_sample(scene,t,size):
    width,height=size; image=QImage(width,height,QImage.Format_ARGB32_Premultiplied); image.fill(Qt.transparent)
    painter=QPainter(image); painter.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing|QPainter.SmoothPixmapTransform)
    canvas=scene.get('canvas',[1080,1920]); painter.scale(width/max(1,canvas[0]),height/max(1,canvas[1]))
    nodes=scene.get('nodes',[]); children={}
    for node in nodes:children.setdefault(node.get('parent',''),[]).append(node)
    def render(node):
        if not node.get('visible',True) or not node.get('start',0)<=t<node.get('end',1e5):return
        painter.save()
        try:
            painter.translate(curve(node,'x',t),curve(node,'y',t)); painter.rotate(curve(node,'rotation',t))
            painter.scale(curve(node,'scale',t),curve(node,'scale_y',t)); painter.translate(-node.get('anchor_x',0),-node.get('anchor_y',0))
            painter.setOpacity(painter.opacity()*max(0,min(1,curve(node,'opacity',t)/100)))
            if node.get('mask'):
                mask=node['mask']; transform=QTransform(); transform.translate(curve(mask,'x',t),curve(mask,'y',t)); transform.rotate(curve(mask,'rotation',t)); transform.scale(curve(mask,'scale',t),curve(mask,'scale_y',t))
                painter.setClipPath(transform.map(geometry(mask,t)),Qt.IntersectClip)
            fill=node.get('fill','#ffffff'); gradient=node.get('gradient')
            brush=QColor(fill) if fill!='none' else Qt.NoBrush
            if isinstance(gradient,list) and len(gradient)>=2:
                w=curve(node,'width',t); g=QLinearGradient(-w/2,0,w/2,0)
                for n,color in enumerate(gradient):g.setColorAt(n/(len(gradient)-1),QColor(color))
                brush=g
            painter.setBrush(brush); stroke=node.get('stroke','none')
            painter.setPen(QPen(QColor(stroke),max(0,node.get('stroke_width',3)),Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin) if stroke!='none' else Qt.NoPen)
            kind=node['kind']
            if kind=='text':draw_text(painter,node,t)
            elif kind=='image':
                pic=_images.load(node.get('source',''))
                if not pic.isNull():
                    w=max(.01,curve(node,'width',t)); h=max(.01,curve(node,'height',t)); painter.drawImage(QRectF(-w/2,-h/2,w,h),pic)
            elif kind!='group':painter.drawPath(geometry(node,t))
            for child in children.get(node['id'],[]):render(child)
        finally:painter.restore()
    try:
        for node in children.get('',[]):render(node)
    finally:painter.end()
    return image

def schema():
    return dict(version=1,kinds=KINDS,channels=CHANNELS,easing=MODES,path_commands=ARITY,
                guidance='Nodes use project pixels; parent IDs form groups. Key times are composition seconds. Text: text_mode character/word, stagger, entry_duration/y/rotation/scale/easing. Mask uses local rectangle/ellipse/path geometry. Path trim 0–1 and matching path_to/morph. motion_blur samples 1–12, shutter 0–360. Templates are scene JSON.')
