"""Story/graphic templates built from motion composition primitives. Each template returns ordinary editable scene
nodes (plus scene extras such as post, floor or camera); parameters patch only the layers the template owns."""
import math

def F(type,label,default,**kw):return dict(type=type,label=label,default=default,**kw)
TEXT=lambda label,default:F('string',label,default,max_len=600)
COLOR=lambda label,default:F('color',label,default)
NUM=lambda label,default,lo,hi:F('number',label,default,min=lo,max=hi)
CHOICE=lambda label,default,choices:F('choice',label,default,choices=choices)

def k(*pairs,ease='Ease Out'):
    """Keyframes from (time, value[, ease]) pairs."""
    out=[]
    for p in pairs:
        out.append(dict(time=p[0],value=p[1],interpolation=p[2] if len(p)>2 else ease))
    return out

def label(id,text,x,y,size,fill,**kw):
    d=dict(id=id,kind='text',text=text,x=x,y=y,font=kw.pop('font','Arial'),font_size=size,fill=fill,bold=kw.pop('bold',True)); d.update(kw); return d

def M(*ds):
    out={}
    for d in ds:out.update(d)
    return out
def pop(t0,dur=.35):return dict(scale=k((t0,.6,'Back Out'),(t0+dur,1)),opacity=k((t0,0),(t0+dur*.6,100,'Hold')))
def fade(t0,t1):return dict(opacity=k((t0,0),(t1,100)))

def split(text):return [s.strip() for s in text.replace('\\n','|').split('|') if s.strip()]
def numbers(text,default):
    out=[]
    for s in text.replace(';',',').split(','):
        try:out.append(float(s))
        except ValueError:pass
    return out or default

# ------------------------------------------------------------------ shapes
def star(r=210,inner=.45):
    pts=[]
    for n in range(10):
        a=-math.pi/2+n*math.pi/5; q=r*(1 if n%2==0 else inner); pts.append('%g %g'%(math.cos(a)*q,math.sin(a)*q))
    return 'M'+' L'.join(pts)+' Z'
SHAPES={'Figure':'M-34 -200 A34 34 0 1 1 34 -200 A34 34 0 1 1 -34 -200 M0 -166 L0 -40 L-50 130 M0 -40 L50 130 M0 -140 L-80 -60 M0 -140 L80 -60',
        'Circle':'M-200 0 A200 200 0 1 1 200 0 A200 200 0 1 1 -200 0','Star':star(),'Heart':'M0 130 C-240 -40 -120 -210 0 -80 C120 -210 240 -40 0 130 Z',
        'Lightning':'M40 -220 L-90 20 L-10 20 L-40 220 L110 -40 L20 -40 Z'}

def build_light_trail(p,w,h,d):
    cx,cy=w/2,h*.56; size=p['size']; draw=min(p['draw'],d*.8); path=p['svg'] if p['shape']=='Custom' and p['svg'] else SHAPES.get(p['shape'],SHAPES['Figure'])
    nodes=[dict(id='haze',kind='ellipse',x=cx,y=cy-h*.1,width=w*1.3,height=h*.5,fill='none',gradient=[p['accent'],'#00000000'],gradient_type='radial',opacity=22,reflect=False,depth=.3)]
    for n,(bx,by,r) in enumerate(((.82,.34,13),(.16,.4,9),(.7,.28,7),(.3,.3,11))):
        nodes.append(dict(id='bokeh%d'%n,kind='ellipse',x=w*bx,y=h*by,width=r*2,height=r*2,fill=p['accent'],opacity=55,depth=.35,glow=dict(radius=r*1.3,intensity=1.2,layers=1),
                          keyframes=dict(opacity=k((0,0),(.8,55)))))
    nodes.append(dict(id='shape',kind='path',path_svg=path,x=cx,y=cy,scale=size,fill='none',stroke=p['color'],stroke_width=5/size,glow=dict(radius=14,intensity=1.7,color=p['accent']),
                      keyframes=dict(trim=k((0,0,'Ease In Out'),(draw,1)))))
    nodes.append(dict(id='head',kind='ellipse',x=cx,y=cy,width=26,height=26,fill='#ffffff',follow=dict(path='shape'),glow=dict(radius=26,intensity=2.2),
                      trail=dict(length=.45,width=11,color=p['color'],samples=28),keyframes=dict(follow_at=k((0,0,'Ease In Out'),(draw,1)),opacity=k((draw,100,'Hold'),(draw+.25,0)))))
    # the path scales with the shape, so the follower must share its scale
    nodes[-1]['scale']=1; nodes[-2]['parent']=''
    if p['burst']=='On':nodes.append(dict(id='sparks',kind='emitter',x=cx,y=cy,start=0,emitter=dict(bursts=[dict(time=draw,count=90)],speed=[260,860],angle=-90,spread=300,gravity=1000,drag=1.6,colors=['#ffffff',p['color'],p['accent']],life=[.7,1.5],size=[6,1.2],seed=11)))
    if p['label']:nodes.append(label('label',p['label'],cx,h*.84,h*.03,p['color'],keyframes=dict(opacity=k((draw*.7,0),(draw+.5,100))),tracking=4,reflect=False))
    extra=dict(floor=dict(y=h*.8,opacity=.4,fade=h*.2,blur=6),post=dict(bloom=.85,bloom_threshold=.5,bloom_radius=28,vignette=.55,grain=.4,tint='#ffc890',tint_amount=.15),
               camera=dict(keyframes=dict(zoom=k((0,1.07,'Ease Out'),(d,1)),x=k((0,-24),(d,24,'Linear')))),motion_blur=dict(samples=1))
    if p['background']=='Dark haze':extra['background']=dict(gradient=['#080504','#1b110b'],angle=90)
    return nodes,extra

def build_kinetic(p,w,h,d):
    lines=split(p['text']); size=p['size']*w/1080; accent=int(p['accent_line']); runs=[]
    for n,line in enumerate(lines):runs.append(dict(text=line+('\n' if n<len(lines)-1 else ''),fill=p['accent_color'] if n+1==accent else p['color']))
    node=dict(id='text',kind='text',text='\n'.join(lines),runs=runs,x=w/2,y=h*.4,font=p['font'],font_size=size,bold=p['weight']=='Bold',italic=p['style']=='Italic',fill=p['color'],text_mode='character',
              stagger=p['stagger'],entry_duration=.45,entry_y=size*.35,entry_blur=p['blur']*w/1080,entry_easing='Ease Out',keyframes=dict(opacity=k((d-.35,100,'Hold'),(d,0))))
    extra={}
    if p['background']!='Transparent':extra['background']=dict(gradient=[p['background_color'],p['background_color2']],radial=True,center=[.5,.4],radius=.9)
    return [node],extra

def build_lower_third(p,w,h,d):
    y=h*.8; bw=w*.74; x0=w*.08; e=.5
    return [dict(id='bar',kind='rectangle',x=x0+bw/2,y=y,width=bw,height=h*.1,radius=h*.012,fill=p['color'],shadow=dict(enabled=True,opacity=25,blur=18,y=8),
                 keyframes=dict(x=k((0,x0-bw/2,'Ease Out'),(e,x0+bw/2),(d-e,x0+bw/2,'Ease In'),(d,x0-bw/2)))),
            dict(id='accent',kind='rectangle',x=x0+h*.006,y=y,width=h*.012,height=h*.1,fill=p['accent'],keyframes=dict(scale_y=k((.2,0,'Ease Out'),(.6,1)),opacity=k((d-e,100,'Hold'),(d-e+.01,0)))),
            label('name',p['name'],x0+h*.03,y-h*.016,h*.032,p['text_color'],text_align='left',text_mode='word',stagger=.06,entry_duration=.4,entry_y=h*.015,start=.25,end=d-e+.2),
            label('role',p['role'],x0+h*.03,y+h*.024,h*.02,p['text_color'],text_align='left',opacity=75,bold=False,text_mode='word',stagger=.05,entry_duration=.4,start=.4,end=d-e+.2)],{}

def build_stat(p,w,h,d):
    v=p['value']; e=min(p['count'],d*.7)
    nodes=[label('value',str(int(v)),w/2,h*.44,w*.13,p['color'],text_mode='counter',number_prefix=p['prefix'],number_suffix=p['suffix'],number_decimals=int(p['decimals']),number_grouping=True,
                 glow=dict(radius=20,intensity=.9),keyframes=M(pop(0,.5),dict(number=k((0,0,'Ease Out'),(e,v)),opacity=k((0,0),(.3,100,'Hold'),(d-.3,100),(d,0))))),
           label('caption',p['label'],w/2,h*.44+w*.11,w*.045,p['label_color'],keyframes=dict(opacity=k((.2,0),(.7,100,'Hold'),(d-.3,100),(d,0))),tracking=6)]
    return nodes,{}

def build_bars(p,w,h,d):
    vals=numbers(p['values'],[30,55,40,80]); labels=split(p['labels'].replace(',','|')); n=len(vals); top=max(vals) or 1
    area_w=w*.78; gap=area_w/n; bw=gap*.6; base=h*.62; maxh=h*.34; nodes=[label('title',p['title'],w/2,h*.2,w*.06,p['text_color'])]
    nodes.append(dict(id='axis',kind='polyline',points=[[w*.11,base],[w*.89,base]],stroke=p['text_color'],stroke_width=3,fill='none',opacity=40,keyframes=dict(trim=k((0,0),(.5,1)))))
    for i,v in enumerate(vals):
        bh=maxh*v/top; x=w*.11+gap*(i+.5); t0=.3+i*.12; col=p['highlight'] if v==top and p['highlight_top']=='On' else p['color']
        nodes.append(dict(id='bar%d'%i,kind='rectangle',x=x,y=base,width=bw,height=bh,anchor_y=bh/2,radius=bw*.12,fill=col,keyframes=dict(scale_y=k((t0,0,'Ease Out'),(t0+.7,1,'Back Out')))))
        nodes.append(label('val%d'%i,str(int(v)),x,base-bh-w*.04,w*.04,p['text_color'],text_mode='counter',number_decimals=0,keyframes=dict(number=k((t0,0),(t0+.7,v)),opacity=k((t0,0),(t0+.3,100)))))
        if i<len(labels):nodes.append(label('lab%d'%i,labels[i],x,base+w*.04,w*.032,p['text_color'],opacity=80,keyframes=dict(opacity=k((t0,0),(t0+.4,80)))))
    return nodes,{}

def build_line(p,w,h,d):
    vals=numbers(p['values'],[20,45,30,70,55,90]); lo,hi=min(vals),max(vals); span=(hi-lo) or 1; n=len(vals); x0=w*.12; x1=w*.88; y1=h*.36; y0=h*.64
    pts=[[x0+(x1-x0)*i/(n-1 if n>1 else 1),y0-(y0-y1)*(v-lo)/span] for i,v in enumerate(vals)]; e=min(p['draw'],d*.8)
    nodes=[dict(id='grid',kind='grid',x=w/2,y=h/2,width=w,height=h,cell=w/14,stroke=p['text_color'],stroke_width=1.5,fill='none',opacity=10),label('title',p['title'],w/2,h*.24,w*.06,p['text_color']),
           dict(id='line',kind='polyline',points=pts,smooth=True,stroke=p['color'],stroke_width=w*.007,fill='none',glow=dict(radius=10,intensity=.6),keyframes=dict(trim=k((0,0,'Ease In Out'),(e,1))))]
    nodes.append(dict(id='ball',kind='ellipse',width=w*.05,height=w*.05,fill=p['color'],gradient=['#ffffff',p['color']],gradient_type='radial',follow=dict(path='line'),stretch=dict(amount=.0006,max=.7),
                      glow=dict(radius=14,intensity=1),shadow=dict(enabled=True,blur=14,y=10,opacity=25),keyframes=dict(follow_at=k((0,0,'Ease In Out'),(e,1)))))
    return nodes,{'motion_blur':dict(samples=4,shutter=180)}

def arrow_nodes(prefix,sx,sy,tx,ty,color,width,t0,t1):
    ang=math.degrees(math.atan2(ty-sy,tx-sx)); nx=tx-math.cos(math.radians(ang))*width*1.2; ny=ty-math.sin(math.radians(ang))*width*1.2
    return [dict(id=prefix+'shaft',kind='polyline',points=[[sx,sy],[(sx+nx)/2+(ny-sy)*.12,(sy+ny)/2-(nx-sx)*.12],[nx,ny]],smooth=True,stroke=color,stroke_width=width,fill='none',keyframes=dict(trim=k((t0,0),(t1,1,'Ease Out')))),
            dict(id=prefix+'head',kind='polygon',sides=3,x=tx,y=ty,width=width*4,height=width*4,rotation=ang+90,anchor_y=width*1.4,fill=color,keyframes=dict(scale=k((t1-.05,0),(t1+.2,1,'Back Out'))))]

def build_callout(p,w,h,d):
    tx,ty=p['target_x']*w,p['target_y']*h; sx,sy=w*(.22 if tx>w/2 else .78),ty+h*(.16 if ty<h*.6 else -.16); size=w*.055
    nodes=arrow_nodes('a',sx,sy,tx,ty,p['color'],w*.012,.15,.7)
    nodes.append(label('text',p['text'],sx,sy+(size*1.3 if sy>ty else -size*1.3),size,p['text_color'],keyframes=dict(opacity=k((.4,0),(.8,100))),stroke='#000000',stroke_width=size*.12))
    return nodes,{}

def ring_path(cx,cy,rx,ry,wobble):
    pts=[]
    for n in range(0,13):
        a=2*math.pi*n/12+math.radians(-70); r=1+wobble*math.sin(n*2.3+1); pts.append([cx+rx*r*math.cos(a),cy+ry*r*math.sin(a)])
    return pts

def build_circle(p,w,h,d):
    tx,ty=p['target_x']*w,p['target_y']*h; rx=w*p['size']; ry=rx*p['aspect']
    nodes=[]
    if p['dim']=='On':nodes.append(dict(id='dim',kind='rectangle',x=w/2,y=h/2,width=w*2,height=h*2,fill='#000000',opacity=0,mask=dict(kind='ellipse',x=tx-w/2,y=ty-h/2,width=rx*2.4,height=ry*2.4,invert=True,feather=rx*.35),
                                  keyframes=dict(opacity=k((.1,0),(.6,55)))))
    nodes.append(dict(id='ring',kind='polyline',points=ring_path(tx,ty,rx,ry,.04),smooth=True,stroke=p['color'],stroke_width=w*.011,fill='none',keyframes=dict(trim=k((0,0,'Ease In Out'),(.7,1))),glow=dict(radius=8,intensity=.5)))
    return nodes,{}

def build_spotlight(p,w,h,d):
    tx,ty=p['target_x']*w,p['target_y']*h; r=w*p['size']
    return [dict(id='dim',kind='rectangle',x=w/2,y=h/2,width=w*2,height=h*2,fill='#000000',mask=dict(kind='ellipse',x=tx-w/2,y=ty-h/2,width=r*2,height=r*2,invert=True,feather=r*.4,keyframes=dict(scale=k((0,3,'Ease Out'),(.6,1)))),
                 keyframes=dict(opacity=k((0,0),(.4,p['dim']),(d-.4,p['dim']),(d,0))))],{}

def build_chat(p,w,h,d):
    msgs=split(p['messages']); size=w*.045; y=h*.28; nodes=[]; gap=min(p['gap'],d/(len(msgs)+1))
    for i,m in enumerate(msgs):
        mine=m.lower().startswith('me:'); text=m[3:].strip() if mine else (m[6:].strip() if m.lower().startswith('other:') else m)
        bw=min(w*.7,max(w*.22,len(text)*size*.55+size*1.6)); bh=size*2.2; x=w*.9-bw/2 if mine else w*.1+bw/2; t0=.2+i*gap; col=p['me_color'] if mine else p['other_color']
        nodes.append(dict(id='bubble%d'%i,kind='group',x=x,y=y,keyframes=pop(t0,.35)))
        nodes.append(dict(id='bg%d'%i,kind='rectangle',parent='bubble%d'%i,width=bw,height=bh,radius=bh*.45,fill=col,shadow=dict(enabled=True,opacity=18,blur=14,y=6)))
        nodes.append(label('tx%d'%i,text,0,0,size,'#ffffff' if mine else p['text_color'],parent='bubble%d'%i))
        y+=bh+size*.7
    return nodes,{}

def build_post(p,w,h,d):
    cw=w*.86; ch=h*.3; cy=h*.45
    nodes=[dict(id='card',kind='group',x=w/2,y=cy,keyframes=M(pop(0,.45),dict(opacity=k((0,0),(.25,100,'Hold'),(d-.3,100),(d,0))))),
           dict(id='panel',kind='rectangle',parent='card',width=cw,height=ch,radius=w*.04,fill=p['card_color'],shadow=dict(enabled=True,opacity=25,blur=30,y=16)),
           dict(id='avatar',kind='ellipse',parent='card',x=-cw/2+w*.1,y=-ch/2+w*.1,width=w*.11,height=w*.11,fill=p['accent']),
           label('initial',p['name'][:1].upper(),-cw/2+w*.1,-ch/2+w*.1,w*.055,'#ffffff',parent='card'),
           label('author',p['name'],-cw/2+w*.19,-ch/2+w*.085,w*.042,p['text_color'],parent='card',text_align='left'),
           label('handle',p['handle'],-cw/2+w*.19,-ch/2+w*.13,w*.032,p['text_color'],parent='card',text_align='left',opacity=55,bold=False),
           label('body',p['text'],-cw/2+w*.06,-ch/2+w*.27,w*.045,p['text_color'],parent='card',text_align='left',text_mode='word',stagger=.06,entry_duration=.3,start=.3,bold=False),
           label('likes',p['likes'],-cw/2+w*.14,ch/2-w*.07,w*.036,p['accent'],parent='card',text_align='left')]
    return nodes,{}

def build_route(p,w,h,d):
    a=(w*.18,h*.64); b=(w*.82,h*.38); mid=[(w*.38,h*.5),(w*.56,h*.66),(w*.7,h*.47)]; e=min(p['draw'],d*.8)
    pts=[list(a),*[list(m) for m in mid],list(b)]
    nodes=[dict(id='route',kind='polyline',points=pts,smooth=True,stroke=p['color'],stroke_width=w*.01,fill='none',dash=[2,1.6],cap='flat',keyframes=dict(trim=k((0,0,'Ease In Out'),(e,1)),dash_offset=k((0,0),(d,-40,'Linear')))),
           dict(id='start',kind='ellipse',x=a[0],y=a[1],width=w*.04,height=w*.04,fill=p['text_color'],keyframes=pop(0)),
           dict(id='pin',kind='group',follow=dict(path='route',orient=False),keyframes=dict(follow_at=k((0,0,'Ease In Out'),(e,1)))),
           dict(id='pinbody',kind='polygon',parent='pin',sides=3,y=-w*.035,width=w*.06,height=w*.08,rotation=180,fill=p['color'],glow=dict(radius=10,intensity=.7)),
           dict(id='pindot',kind='ellipse',parent='pin',y=-w*.05,width=w*.03,height=w*.03,fill='#ffffff'),
           label('from',p['from_label'],a[0],a[1]+w*.06,w*.04,p['text_color']),label('to',p['to_label'],b[0],b[1]+w*.06,w*.04,p['text_color'],keyframes=dict(opacity=k((e-.2,0),(e+.2,100))))]
    return nodes,{}

def build_versus(p,w,h,d):
    return [dict(id='left',kind='rectangle',x=w*.25,y=h/2,width=w*.5,height=h*.5,fill=p['color_a'],keyframes=dict(x=k((0,-w*.25,'Back Out'),(.5,w*.25)),opacity=k((d-.3,100,'Hold'),(d,0)))),
            dict(id='right',kind='rectangle',x=w*.75,y=h/2,width=w*.5,height=h*.5,fill=p['color_b'],keyframes=dict(x=k((0,w*1.25,'Back Out'),(.5,w*.75)),opacity=k((d-.3,100,'Hold'),(d,0)))),
            label('a',p['left'],w*.25,h/2,w*.07,'#ffffff',keyframes=fade(.4,.7)),label('b',p['right'],w*.75,h/2,w*.07,'#ffffff',keyframes=fade(.4,.7)),
            dict(id='vs',kind='ellipse',x=w/2,y=h/2,width=w*.2,height=w*.2,fill='#ffffff',shadow=dict(enabled=True,opacity=30,blur=20,y=8),keyframes=pop(.45,.4)),
            label('vstext','VS',w/2,h/2,w*.08,'#111111',keyframes=pop(.5,.4))],{}

def build_ranking(p,w,h,d):
    items=split(p['items']); nodes=[label('title',p['title'],w/2,h*.2,w*.07,p['text_color'])]; row=h*.095
    for i,t in enumerate(items):
        y=h*.3+i*row; t0=.2+i*.25
        nodes.append(dict(id='row%d'%i,kind='group',x=w/2,y=y,keyframes=dict(x=k((t0,w*1.2,'Ease Out'),(t0+.5,w/2)),opacity=k((t0,0),(t0+.2,100)))))
        nodes.append(dict(id='rb%d'%i,kind='rectangle',parent='row%d'%i,width=w*.84,height=row*.82,radius=row*.2,fill=p['card_color']))
        nodes.append(dict(id='rn%d'%i,kind='ellipse',parent='row%d'%i,x=-w*.36,width=row*.58,height=row*.58,fill=p['color'] if i else p['highlight']))
        nodes.append(label('rnt%d'%i,str(i+1),-w*.36,0,row*.34,'#ffffff',parent='row%d'%i))
        nodes.append(label('rt%d'%i,t,-w*.28,0,row*.3,p['text_color'],parent='row%d'%i,text_align='left'))
    return nodes,{}

def build_quote(p,w,h,d):
    return [label('mark','“',w/2,h*.3,w*.3,p['color'],font='Georgia',keyframes=pop(0,.5)),
            dict(id='quote',kind='text',text=p['text'],x=w/2,y=h*.46,font='Georgia',italic=True,bold=False,font_size=w*.06,fill=p['text_color'],text_mode='word',stagger=.08,entry_duration=.35,entry_y=w*.02,entry_blur=12,start=.25),
            label('author','— '+p['author'],w/2,h*.62,w*.04,p['color'],keyframes=dict(opacity=k((d*.55,0),(d*.55+.4,100))))],{}

def build_banner(p,w,h,d):
    y=h*.82; e=.45
    return [dict(id='bar',kind='rectangle',x=w/2,y=y,width=w,height=h*.075,fill=p['color'],keyframes=dict(x=k((0,-w,'Ease Out'),(e,w/2),(d-e,w/2,'Ease In'),(d,w*1.5)))),
            dict(id='tag',kind='rectangle',x=w*.14,y=y,width=w*.26,height=h*.075,fill='#ffffff',keyframes=dict(x=k((0,-w,'Ease Out'),(e,w*.14),(d-e,w*.14,'Ease In'),(d,w*1.5)))),
            label('tagt',p['tag'],w*.14,y,h*.028,p['color'],keyframes=dict(opacity=k((e,0),(e+.2,100,'Hold'),(d-e,100),(d-e+.01,0)))),
            label('head',p['headline'],w*.29,y,h*.022,'#ffffff',text_align='left',text_mode='typewriter',stagger=.03,caret=False,keyframes=dict(opacity=k((e,100,'Hold'),(d-e,100),(d-e+.01,0))),start=e)],{}

def build_orbit(p,w,h,d):
    cx,cy=w/2,h*.45; r=w*.28; pct=p['value']; nodes=[dict(id='track',kind='ellipse',x=cx,y=cy,width=r*2,height=r*2,fill='none',stroke=p['track_color'],stroke_width=w*.018,keyframes=dict(opacity=k((0,0),(.3,100))))]
    nodes.append(dict(id='arc',kind='ellipse',x=cx,y=cy,width=r*2,height=r*2,fill='none',stroke=p['color'],stroke_width=w*.018,rotation=-90,cap='round',glow=dict(radius=10,intensity=.8),keyframes=dict(trim=k((0,0,'Ease In Out'),(min(1.6,d*.7),pct/100)))))
    for i in range(6):
        a=2*math.pi*i/6-math.pi/2; nodes.append(dict(id='dia%d'%i,kind='polygon',sides=4,x=cx+r*math.cos(a),y=cy+r*math.sin(a),width=w*.032,height=w*.032,fill=p['color'],keyframes=pop(.2+i*.08,.3)))
    nodes.append(dict(id='core',kind='ellipse',x=cx,y=cy,width=r*1.1,height=r*1.1,fill=p['color'],gradient=['#ffffff',p['color']],gradient_type='radial',shadow=dict(enabled=True,opacity=25,blur=24,y=14),keyframes=pop(0,.5)))
    nodes.append(label('pct',str(int(pct)),cx,cy,r*.42,'#ffffff',text_mode='counter',number_suffix='%',number_decimals=0,keyframes=dict(number=k((0,0),(min(1.6,d*.7),pct)))))
    return nodes,{}

def build_iris(p,w,h,d):
    cx,cy=p['center_x']*w,p['center_y']*h; mode=p['mode']; big=math.hypot(w,h)/ (math.hypot(w,h)/2) * 1.0
    r=math.hypot(w,h)*1.1; half=d/2
    if mode=='Open':scale=k((0,0,'Ease In'),(d,1))
    elif mode=='Close':scale=k((0,1,'Ease In'),(d,0))
    else:scale=k((0,1,'Ease In'),(half,0,'Ease Out'),(d,1))
    return [dict(id='panel',kind='rectangle',x=w/2,y=h/2,width=w*2.2,height=h*2.2,fill=p['color'],mask=dict(kind='ellipse',x=cx-w/2,y=cy-h/2,width=r,height=r,invert=True,feather=p['feather'],keyframes=dict(scale=scale)))],{}

def build_flash(p,w,h,d):
    band=w*.5
    return [dict(id='band',kind='rectangle',x=w/2,y=h/2,width=band,height=h*1.8,rotation=20,fill=p['color'],blend='add',glow=dict(radius=60,intensity=1),opacity=90,keyframes=dict(x=k((0,-band,'Ease In Out'),(d,w+band),),opacity=k((0,0),(d*.2,90),(d*.8,90),(d,0)))),
            dict(id='flash',kind='rectangle',x=w/2,y=h/2,width=w*2,height=h*2,fill=p['color'],blend='add',opacity=0,keyframes=dict(opacity=k((d*.35,0),(d*.5,45,'Ease Out'),(d*.75,0))))],{}

TEMPLATES={
 'Light Trail Draw':dict(description='A point of light draws a glowing outline with a comet trail, bloom, haze, wet-floor reflection and a spark burst.',build=build_light_trail,duration=4,
   fields=dict(shape=CHOICE('Shape','Figure',['Figure','Circle','Star','Heart','Lightning','Custom']),svg=TEXT('Custom SVG path (centred on 0,0)',''),size=NUM('Size',1.5,.2,6),draw=NUM('Draw time (s)',2,.3,30),color=COLOR('Line colour','#ffe2b0'),accent=COLOR('Glow colour','#ff9a50'),
               burst=CHOICE('Spark burst','On',['On','Off']),background=CHOICE('Background','Dark haze',['Dark haze','Transparent']),label=TEXT('Caption',''))),
 'Kinetic Statement':dict(description='Large animated statement. Characters blur in one by one; one line can use an accent colour.',build=build_kinetic,duration=3.5,
   fields=dict(text=TEXT('Text (| = new line)','sketch in.|motion out.'),accent_line=NUM('Accent line (0 = none)',2,0,12),color=COLOR('Colour','#3a1f12'),accent_color=COLOR('Accent colour','#e8703a'),font=F('string','Font','Georgia'),
               style=CHOICE('Style','Italic',['Italic','Regular']),weight=CHOICE('Weight','Regular',['Regular','Bold']),size=NUM('Size',110,20,400),blur=NUM('Blur-in',22,0,80),stagger=NUM('Letter delay (s)',.04,0,.5),
               background=CHOICE('Background','Transparent',['Transparent','Gradient']),background_color=COLOR('Background','#f7f4f0'),background_color2=COLOR('Background edge','#d9d4cd'))),
 'Lower Third':dict(description='Name and role bar that slides in and out.',build=build_lower_third,duration=4,
   fields=dict(name=TEXT('Name','ALEX MORGAN'),role=TEXT('Role','Host'),color=COLOR('Bar','#16272c'),accent=COLOR('Accent','#ffe600'),text_color=COLOR('Text','#ffffff'))),
 'Stat Counter':dict(description='Big number that counts up with a caption.',build=build_stat,duration=3,
   fields=dict(value=NUM('Value',1250000,0,1e12),prefix=TEXT('Prefix','$'),suffix=TEXT('Suffix',''),decimals=NUM('Decimals',0,0,4),count=NUM('Count time (s)',1.4,.2,20),label=TEXT('Caption','TOTAL REVENUE'),color=COLOR('Number','#ffffff'),label_color=COLOR('Caption colour','#ffe600'))),
 'Bar Chart':dict(description='Animated bar chart; bars grow from the baseline and values count up.',build=build_bars,duration=4,
   fields=dict(title=TEXT('Title','QUARTERLY GROWTH'),labels=TEXT('Labels (, separated)','Q1,Q2,Q3,Q4'),values=TEXT('Values (, separated)','30,55,40,80'),color=COLOR('Bars','#5aa9ff'),highlight=COLOR('Top bar','#ffe600'),highlight_top=CHOICE('Highlight top','On',['On','Off']),text_color=COLOR('Text','#ffffff'))),
 'Line Chart':dict(description='Line chart that draws on with a ball squashing along the curve.',build=build_line,duration=4,
   fields=dict(title=TEXT('Title','VIEWS PER DAY'),values=TEXT('Values (, separated)','20,45,30,70,55,90'),draw=NUM('Draw time (s)',2.2,.3,30),color=COLOR('Line','#e8703a'),text_color=COLOR('Text','#222222'))),
 'Callout Arrow':dict(description='An arrow draws itself towards a point on the frame with a label.',build=build_callout,duration=3,
   fields=dict(text=TEXT('Label','LOOK HERE'),target_x=NUM('Target X (0-1)',.5,0,1),target_y=NUM('Target Y (0-1)',.45,0,1),color=COLOR('Arrow','#ffe600'),text_color=COLOR('Text','#ffffff'))),
 'Circle Highlight':dict(description='A hand-drawn ring around a point, optionally dimming the rest of the frame.',build=build_circle,duration=2.5,
   fields=dict(target_x=NUM('Target X (0-1)',.5,0,1),target_y=NUM('Target Y (0-1)',.45,0,1),size=NUM('Radius (width fraction)',.16,.03,.8),aspect=NUM('Aspect',1,.3,3),color=COLOR('Ring','#ff3b30'),dim=CHOICE('Dim rest','On',['On','Off']))),
 'Spotlight Focus':dict(description='Dims everything except a softly feathered circle that shrinks onto the subject.',build=build_spotlight,duration=3,
   fields=dict(target_x=NUM('Target X (0-1)',.5,0,1),target_y=NUM('Target Y (0-1)',.45,0,1),size=NUM('Radius (width fraction)',.28,.05,1),dim=NUM('Dim (%)',70,0,100))),
 'Chat Story':dict(description='Message bubbles pop in one after another. Prefix a message with "me:" to put it on the right.',build=build_chat,duration=6,
   fields=dict(messages=TEXT('Messages (| separated)','hey are you awake?|me:yeah what happened|you will not believe this|me:tell me NOW'),gap=NUM('Seconds between messages',1,.2,5),me_color=COLOR('Your bubbles','#2f8cff'),other_color=COLOR('Other bubbles','#ececf1'),text_color=COLOR('Other text','#111111'))),
 'Social Post Card':dict(description='A social media style post card with avatar, text and a like counter.',build=build_post,duration=4,
   fields=dict(name=TEXT('Name','Alex Morgan'),handle=TEXT('Handle','@alexmorgan'),text=TEXT('Post text','this edit took me 3 minutes'),likes=TEXT('Likes','24.8K likes'),card_color=COLOR('Card','#ffffff'),text_color=COLOR('Text','#111111'),accent=COLOR('Accent','#2f8cff'))),
 'Route Line':dict(description='Animated dashed route with a pin travelling along it and two labels.',build=build_route,duration=4,
   fields=dict(from_label=TEXT('From','LONDON'),to_label=TEXT('To','TOKYO'),draw=NUM('Draw time (s)',2.4,.3,30),color=COLOR('Route','#ff5a36'),text_color=COLOR('Text','#ffffff'))),
 'Versus Split':dict(description='Two coloured halves slide in with a VS badge.',build=build_versus,duration=3,
   fields=dict(left=TEXT('Left','TEAM A'),right=TEXT('Right','TEAM B'),color_a=COLOR('Left colour','#1f6feb'),color_b=COLOR('Right colour','#e5484d'))),
 'Ranking List':dict(description='Numbered list rows slide in one by one.',build=build_ranking,duration=5,
   fields=dict(title=TEXT('Title','TOP 5'),items=TEXT('Items (| separated)','First|Second|Third|Fourth|Fifth'),card_color=COLOR('Rows','#ffffff'),color=COLOR('Number','#2f8cff'),highlight=COLOR('Winner','#ffb800'),text_color=COLOR('Text','#111111'))),
 'Quote Card':dict(description='Large quote that blurs in word by word with an author line.',build=build_quote,duration=4.5,
   fields=dict(text=TEXT('Quote','Make it move.'),author=TEXT('Author','Anonymous'),color=COLOR('Accent','#e8703a'),text_color=COLOR('Text','#ffffff'))),
 'Breaking Banner':dict(description='News style banner with a tag and typewriter headline.',build=build_banner,duration=4,
   fields=dict(tag=TEXT('Tag','BREAKING'),headline=TEXT('Headline','Something unbelievable just happened'),color=COLOR('Banner','#d00000'))),
 'Orbit Progress':dict(description='Progress ring with orbiting markers and a counting percentage.',build=build_orbit,duration=3.5,
   fields=dict(value=NUM('Percent',87,0,100),color=COLOR('Ring','#e8703a'),track_color=COLOR('Track','#d8d4cf'))),
 'Iris Wipe':dict(description='Transition overlay: a soft-edged circle opens or closes over the picture. Place it on the cut.',build=build_iris,duration=.8,
   fields=dict(mode=CHOICE('Mode','Close and Open',['Open','Close','Close and Open']),color=COLOR('Colour','#1a0f0a'),center_x=NUM('Centre X (0-1)',.5,0,1),center_y=NUM('Centre Y (0-1)',.5,0,1),feather=NUM('Edge softness',60,0,300))),
 'Light Sweep':dict(description='Transition overlay: a bright additive band sweeps across with a flash on the cut.',build=build_flash,duration=.7,
   fields=dict(color=COLOR('Light','#ffe9c4'))),
}


def catalog():
    return {name:dict(description=t['description'],default_duration=t['duration'],fields={k:{a:b for a,b in f.items()} for k,f in t['fields'].items()}) for name,t in TEMPLATES.items()}

def uniform_scale(node):
    """'scale' is the horizontal factor (scale_y is separate), so a pop/zoom keyed only on scale would squash sideways."""
    if not isinstance(node,dict):return
    keys=node.get('keyframes',{})
    if 'scale' in keys and 'scale_y' not in keys:keys['scale_y']=[dict(x) for x in keys['scale']]
    if 'scale' in node and 'scale_y' not in node:node['scale_y']=node['scale']

def build(name,params=None,canvas=(1080,1920),duration=None):
    """Return (scene, parameters, duration). Unknown template or invalid values raise ValueError."""
    if name not in TEMPLATES:raise ValueError('Unknown story template. Use one of: '+', '.join(TEMPLATES))
    t=TEMPLATES[name]; params=params or {}
    if not isinstance(params,dict):raise ValueError('properties must be an object')
    unknown=[k for k in params if k not in t['fields']]
    if unknown:raise ValueError('Unknown field %s for %s. Fields: %s'%(unknown[0],name,', '.join(t['fields'])))
    out={}
    for key,f in t['fields'].items():
        v=params.get(key,f['default'])
        if f['type']=='number':
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not f['min']<=v<=f['max']:raise ValueError('%s must be a number between %g and %g'%(key,f['min'],f['max']))
        elif f['type']=='choice':
            if v not in f['choices']:raise ValueError('%s must be one of %s'%(key,', '.join(f['choices'])))
        elif f['type']=='color':
            from PySide6.QtGui import QColor
            if not isinstance(v,str) or not QColor(v).isValid():raise ValueError(key+' must be a colour such as #ffcc00')
        elif not isinstance(v,str) or len(v)>f.get('max_len',600):raise ValueError(key+' must be text')
        out[key]=v
    d=float(duration or t['duration']); w,h=canvas
    nodes,extra=t['build'](out,w,h,d)
    for node in nodes:uniform_scale(node);uniform_scale(node.get('mask'))
    scene={'version':1,'canvas':[w,h],'nodes':nodes,'template':name}
    scene.update(extra)
    return scene,out,d
