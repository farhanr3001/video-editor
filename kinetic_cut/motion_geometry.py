"""Editor hit geometry in the same parent/local coordinates as scene rendering."""
from PySide6.QtCore import QRectF,QPointF
from PySide6.QtGui import QTransform,QPainterPath
from .motion import curve,geometry,text_parts,_images

def local_path(node,t):
    kind=node['kind']
    if kind=='text':
        from .motion_text import counter_text
        text=counter_text(node,t) if node.get('text_mode')=='counter' else node.get('text','')
        path=QPainterPath()
        for part in text_parts(text,node.get('font','Arial'),curve(node,'font_size',t),bool(node.get('bold',True)),'none',curve(node,'tracking',t),node.get('text_align','center')):path.addPath(part)
        # Text handles use its full stable layout, including whitespace gaps.
        bounds=path.boundingRect(); box=QPainterPath(); box.addRect(bounds); return box
    if kind=='group':return QPainterPath()
    if kind=='image':
        w=max(.01,curve(node,'width',t)); h=max(.01,curve(node,'height',t)); pic=_images.load(node.get('source',''))
        if node.get('image_fit')=='contain' and not pic.isNull():
            factor=min(w/pic.width(),h/pic.height()); w=pic.width()*factor; h=pic.height()*factor
        path=QPainterPath(); path.addRect(QRectF(-w/2,-h/2,w,h)); return path
    return geometry(node,t)

def layout(scene,t):
    children={}; result={}; ordered=[]
    for node in scene['nodes']:children.setdefault(node.get('parent',''),[]).append(node)
    def walk(node,parent,clip,shown):
        visible=shown and node.get('visible',True) and node.get('start',0)<=t<node.get('end',1e5)
        world=QTransform(parent); world.translate(curve(node,'x',t),curve(node,'y',t)); world.rotate(curve(node,'rotation',t)); world.scale(curve(node,'scale',t),curve(node,'scale_y',t)); world.translate(-node.get('anchor_x',0),-node.get('anchor_y',0))
        mask=node.get('mask')
        if mask:
            m=QTransform(world); m.translate(curve(mask,'x',t),curve(mask,'y',t)); m.rotate(curve(mask,'rotation',t)); m.scale(curve(mask,'scale',t),curve(mask,'scale_y',t))
            path=m.map(geometry(mask,t)); clip=path if clip is None else clip.intersected(path)
        local=local_path(node,t); hit=world.map(local)
        if clip is not None:hit=hit.intersected(clip)
        entry=dict(node=node,world=world,parent=parent,local=local,hit=hit,visible=visible,clip=clip)
        result[node['id']]=entry; ordered.append(node['id'])
        for child in children.get(node['id'],[]):walk(child,world,clip,visible)
        if node['kind']=='group':
            group=QPainterPath()
            for child in children.get(node['id'],[]):
                value=result[child['id']]
                if value['visible']:group=group.united(value['hit'])
            entry['hit']=group; inverse,ok=world.inverted()
            if ok:entry['local']=inverse.map(group)
    for node in children.get('',[]):walk(node,QTransform(),None,True)
    return result,ordered
