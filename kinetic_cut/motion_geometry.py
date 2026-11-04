"""Editor hit geometry in the same parent/local coordinates as scene rendering."""
from PySide6.QtCore import QRectF,QPointF
from PySide6.QtGui import QTransform,QPainterPath
from .motion import curve,geometry,text_parts,_images,node_origin,run_styles

_SIZES={}

def image_size(path):
    """Pixel size of an image file from its header only (no decode), cached by path and modification time."""
    import os
    from PySide6.QtGui import QImageReader
    try:stat=os.stat(path)
    except OSError:return None
    key=(path,stat.st_mtime_ns,stat.st_size); size=_SIZES.get(key)
    if size is None:
        q=QImageReader(path).size(); size=(q.width(),q.height()) if q.isValid() and q.width()>0 and q.height()>0 else ()
        if len(_SIZES)>512:_SIZES.clear()
        _SIZES[key]=size
    return size or None

def local_path(node,t):
    kind=node['kind']
    if kind=='text':
        from .motion_text import counter_text
        text=counter_text(node,t) if node.get('text_mode')=='counter' else node.get('text','')
        path=QPainterPath()
        for part in text_parts(text,node.get('font','Arial'),curve(node,'font_size',t),bool(node.get('bold',True)),'none',curve(node,'tracking',t),node.get('text_align','center'),bool(node.get('italic',False)),run_styles(node)):path.addPath(part)
        # Text handles use its full stable layout, including whitespace gaps.
        bounds=path.boundingRect(); box=QPainterPath(); box.addRect(bounds); return box
    if kind=='group':return QPainterPath()
    if kind=='video':
        w=max(.01,curve(node,'width',t)); h=max(.01,curve(node,'height',t)); path=QPainterPath(); path.addRect(QRectF(-w/2,-h/2,w,h)); return path
    if kind=='image':
        w=max(.01,curve(node,'width',t)); h=max(.01,curve(node,'height',t))
        if node.get('image_fit')=='contain':
            size=image_size(node.get('source',''))
            if size:factor=min(w/size[0],h/size[1]); w=size[0]*factor; h=size[1]*factor
        path=QPainterPath(); path.addRect(QRectF(-w/2,-h/2,w,h)); return path
    return geometry(node,t)

def layout(scene,t,wanted=None):
    """World transforms and hit shapes. wanted (ids) limits the expensive outline work to those layers and their
    descendants (transforms are still computed for all), e.g. for drawing selection handles every playback frame."""
    children={}; result={}; ordered=[]; by_id={n['id']:n for n in scene['nodes']}
    from . import motion_fx as fx
    canvas=scene.get('canvas',[1080,1920])
    for node in scene['nodes']:children.setdefault(node.get('parent',''),[]).append(node)
    needed=None
    if wanted is not None:
        needed=set(i for i in wanted if i in by_id)
        while True:
            more={n['id'] for n in scene['nodes'] if n.get('parent') in needed}-needed
            if not more:break
            needed|=more
    def walk(node,parent,clip,shown):
        visible=shown and node.get('visible',True) and node.get('start',0)<=t<node.get('end',1e5)
        x,y,extra=node_origin(node,t,by_id); world=QTransform(parent); world.translate(x,y); world.rotate(curve(node,'rotation',t)+extra); world.scale(curve(node,'scale',t),curve(node,'scale_y',t)); world.translate(-node.get('anchor_x',0),-node.get('anchor_y',0))
        mask=node.get('mask')
        if mask:
            m=QTransform(world); m.translate(curve(mask,'x',t),curve(mask,'y',t)); m.rotate(curve(mask,'rotation',t)); m.scale(curve(mask,'scale',t),curve(mask,'scale_y',t))
            path=m.map(geometry(mask,t)); clip=path if clip is None else clip.intersected(path)
        use=needed is None or node['id'] in needed
        local=local_path(node,t) if use else QPainterPath(); hit=world.map(local) if use else QPainterPath()
        if clip is not None and use:hit=hit.intersected(clip)
        entry=dict(node=node,world=world,parent=parent,local=local,hit=hit,visible=visible,clip=clip)
        result[node['id']]=entry; ordered.append(node['id'])
        for child in children.get(node['id'],[]):walk(child,world,clip,visible)
        if node['kind']=='group' and use:
            group=QPainterPath()
            for child in children.get(node['id'],[]):
                value=result[child['id']]
                if value['visible']:group=group.united(value['hit'])
            entry['hit']=group; inverse,ok=world.inverted()
            if ok:entry['local']=inverse.map(group)
    for node in children.get('',[]):walk(node,fx.camera_transform(scene,t,node.get('depth',1.),canvas) or QTransform(),None,True)
    return result,ordered
