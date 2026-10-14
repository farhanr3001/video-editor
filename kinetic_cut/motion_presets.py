"""Editable graphic recipes based on product, wealth and chapter workflows.

Recipes produce ordinary scene nodes. Parameter changes patch only recipe-owned
fields which actually changed, preserving custom layers and unrelated edits.
"""
import copy,math
from PySide6.QtGui import QColor
from .motion import validate

PRESETS={
    'Product Price Card':dict(description='Product image, title and rolling green price.',value=200000),
    'Price Range Card':dict(description='Product image with a single-line animated price range.',title='RICHARD MILLE RM 055',value=375000,value_max=430000),
    'Animated Total':dict(description='Animated spending, earnings or statistics.',title='TOTAL SPENT',value=151000),
    'Product Showcase':dict(description='Product image and model name with a smooth entrance.',title='RICHARD MILLE',subtitle='RM 88 SMILEY'),
    'Chapter Title':dict(description='A clear animated chapter heading for longform videos.',title='THE WATCH COLLECTION'),
}
FIELDS={
    'title':dict(type='string',label='Title',default='RICHARD MILLE RM 07-04'),
    'subtitle':dict(type='string',label='Model / subtitle',default='WATCH COLLECTION'),
    'image':dict(type='image',label='Product image',default=''),
    'value':dict(type='number',label='Value',default=200000,min=0,max=1e12),
    'value_max':dict(type='number',label='Upper value',default=430000,min=0,max=1e12),
    'prefix':dict(type='string',label='Value prefix',default='$'),
    'suffix':dict(type='string',label='Value suffix',default=''),
    'format':dict(type='choice',label='Number format',default='Compact',choices=['Compact','Full']),
    'animation':dict(type='choice',label='Value animation',default='Rolling',choices=['Rolling','Count','None']),
    'heading_color':dict(type='color',label='Title colour',default='#ffe600'),
    'value_color':dict(type='color',label='Value colour',default='#56f29a'),
    'background':dict(type='color',label='Background',default='#16272c'),
    'gradient_end':dict(type='color',label='Gradient end',default='#294a50'),
    'entry':dict(type='number',label='Entrance (s)',default=.35,min=.01,max=10),
    'roll_duration':dict(type='number',label='Value animation (s)',default=.9,min=.01,max=30),
    'exit':dict(type='number',label='Exit (s)',default=.25,min=.01,max=10),
}

def fields(name):
    chosen=['title','image','heading_color','background','gradient_end','entry','exit']
    if name=='Chapter Title':chosen.remove('image')
    elif name=='Product Showcase':chosen.insert(1,'subtitle')
    else:
        chosen[2:2]=['value',*(['value_max'] if name=='Price Range Card' else []),'prefix','suffix','format','animation','value_color','roll_duration']
        if name=='Animated Total':chosen.remove('image')
    result={key:copy.deepcopy(FIELDS[key]) for key in chosen}
    if name=='Price Range Card':result['animation']['choices']=['Rolling','None']
    return result

def parameters(name,values=None):
    if name not in PRESETS:raise ValueError('Unknown motion preset')
    spec=fields(name); values=values or {}
    if not isinstance(values,dict) or set(values)-set(spec):raise ValueError('Unknown preset parameter')
    result={k:PRESETS[name].get(k,v['default']) for k,v in spec.items()}; result.update(copy.deepcopy(values))
    for key,value in result.items():
        field=spec[key]
        if field['type']=='number':
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not field['min']<=value<=field['max']:raise ValueError('Invalid '+key)
        elif not isinstance(value,str) or len(value)>(32768 if key=='image' else 256):raise ValueError('Invalid '+key)
        elif field['type']=='choice' and value not in field['choices']:raise ValueError('Invalid '+key)
        elif field['type']=='color' and not QColor(value).isValid():raise ValueError('Invalid colour')
    if name=='Price Range Card' and result['value_max']<result['value']:raise ValueError('Upper value must be at least the lower value')
    return result

def amount(number,style):
    if style=='Full':return f'{number:,.0f}'
    for limit,suffix in ((1e9,'B'),(1e6,'M'),(1e3,'K')):
        if number>=limit:return f'{number/limit:.2f}'.rstrip('0').rstrip('.')+suffix
    return f'{number:,.0f}'

def build(name,canvas=(1080,1920),duration=4,values=None):
    p=parameters(name,values); duration=float(duration)
    if not math.isfinite(duration) or not .05<=duration<=3600:raise ValueError('Preset duration must be .05–3600 seconds')
    w,h=map(float,canvas); portrait=h>w; width=w*(.80 if portrait else .64)
    height=min(width*.32,h*.27); y=h*(.54 if portrait else .57)
    if name=='Chapter Title':height=min(width*.25,h*.24); y=h*.48
    entry=min(p['entry'],duration*.4); exit=min(p['exit'],duration*.25)
    root=dict(id='card',name=name,kind='group',x=w*(.46 if portrait else .5),y=y,start=0,end=duration,
              keyframes={'scale':[dict(time=0,value=.92,interpolation='Back Out'),dict(time=entry,value=1)],
                         'opacity':[dict(time=0,value=0,interpolation='Ease Out'),dict(time=entry,value=100,interpolation='Hold'),dict(time=duration-exit,value=100),dict(time=duration,value=0)]})
    nodes=[root,dict(id='panel',name='Background',kind='rectangle',parent='card',width=width,height=height,radius=height*.1,
                    fill=p['background'],gradient=[p['background'],p['gradient_end']],shadow=dict(enabled=True,opacity=18,blur=12,y=6))]
    has_image='image' in p; image_width=height*.74
    text_left=-width/2+(image_width+height*.23 if has_image else width*.08)
    text_width=width/2-width*.08-text_left; text_x=text_left+text_width/2
    if has_image:
        nodes.extend([dict(id='product',name='Product image',kind='image' if p['image'] else 'group',parent='card',source=p['image'],image_fit='contain',x=-width/2+height*.5,y=0,width=image_width,height=height*.82),
                      dict(id='placeholder',name='Image placeholder',kind='text',parent='card',text='ADD\nIMAGE',x=-width/2+height*.5,y=0,font_size=height*.07,fill=p['heading_color'],visible=not bool(p['image']))])
    def text(node_id,label,text,y,size,color,**extra):
        # Fit the longest line without forcing a second price line.
        from PySide6.QtGui import QFont,QFontMetricsF
        font=QFont('Arial'); font.setPixelSize(max(1,round(size))); font.setBold(True)
        measured=max((QFontMetricsF(font).horizontalAdvance(line) for line in text.split('\n')),default=1)
        size=min(size,size*text_width/max(1,measured))
        return dict(id=node_id,name=label,kind='text',parent='card',text=text,x=text_x,y=y,font='Arial',font_size=size,fill=color,bold=True,**extra)
    if name=='Chapter Title':nodes.append(text('heading','Chapter title',p['title'],0,height*.27,p['heading_color'],text_mode='word',stagger=.05,entry_duration=entry,entry_y=height*.12))
    else:
        nodes.append(text('heading','Title',p['title'],-height*.22,height*.12,p['heading_color']))
        if name=='Product Showcase':nodes.append(text('value','Model',p['subtitle'],height*.15,height*.19,'#ffffff'))
        else:
            final=p['prefix']+amount(p['value'],p['format'])+p['suffix']
            if name=='Price Range Card':final+=' - '+p['prefix']+amount(p['value_max'],p['format'])+p['suffix']
            node=text('value','Value',final,height*.16,height*.26,p['value_color'])
            if p['animation']=='Rolling':node.update(text_mode='rolling',entry_duration=min(p['roll_duration'],max(.01,duration-exit)),entry_easing='Ease Out')
            elif p['animation']=='Count' and name!='Price Range Card':
                divisor=next((v for v in (1e9,1e6,1e3) if p['value']>=v),1) if p['format']=='Compact' else 1
                node.update(text_mode='counter',number_prefix=p['prefix'],number_suffix=({1e9:'B',1e6:'M',1e3:'K'}.get(divisor,'')+p['suffix']),number_decimals=2 if divisor!=1 else 0,number_trim_zeros=True,number_grouping=divisor==1,
                            keyframes={'number':[dict(time=0,value=0,interpolation='Ease Out'),dict(time=min(p['roll_duration'],duration-exit),value=p['value']/divisor)]})
            elif p['animation']=='Count':node.update(text_mode='rolling',entry_duration=min(p['roll_duration'],duration-exit))
            nodes.append(node)
    return dict(preset=name,parameters=p,preset_duration=duration,scene=validate(dict(canvas=list(canvas),nodes=nodes)))

def update(data,changes,duration=None):
    name=data.get('preset'); old=build(name,data['scene']['canvas'],data.get('preset_duration',4),data.get('parameters',{}))
    merged=dict(old['parameters']); merged.update(changes)
    new=build(name,old['scene']['canvas'],duration if duration is not None else old['preset_duration'],merged)
    result=copy.deepcopy(data); by_id={n['id']:n for n in result['scene']['nodes']}
    def patch(target,before,after):
        for key in set(before)|set(after):
            if before.get(key)==after.get(key):continue
            if key not in after:target.pop(key,None)
            elif isinstance(before.get(key),dict) and isinstance(after[key],dict):patch(target.setdefault(key,{}),before[key],after[key])
            else:target[key]=copy.deepcopy(after[key])
    previous={n['id']:n for n in old['scene']['nodes']}
    for node in new['scene']['nodes']:
        if node['id'] in by_id:patch(by_id[node['id']],previous.get(node['id'],{}),node)
    result.update(preset=name,parameters=new['parameters'],preset_duration=new['preset_duration']); result['scene']=validate(result['scene'])
    return result

def catalog():return {name:dict(**info,fields=fields(name)) for name,info in PRESETS.items()}

def is_motion(name):return name.lower() in ('motion','motion composition') or name in PRESETS
