"""Lightweight pixel effects shared by preview, GPU export and compatibility output.

Only numeric uniforms and validated opaque colours cross the rendering boundary.
The effect clock follows source edits, so a split does not restart a flash.
"""
import math
from . import finishing_effects as finishing
from PySide6.QtGui import QColor, QImage

# key, label, minimum, maximum, default, step
CONTROLS = {
    'Color Flash': [('strength','Strength (%)',0,100,85,1),('speed','Flashes / second',.1,12,2,.1),('width','Pulse width (%)',1,100,35,1),('softness','Softness (%)',0,100,80,1),('phase','Phase (%)',0,100,0,1)],
    'Exposure Pulse': [('depth','Exposure depth (stops)',0,4,1,.05),('base','Base exposure (stops)',-4,4,0,.05),('speed','Pulses / second',.1,12,1,.1),('phase','Phase (%)',0,100,0,1)],
    'Color Tint': [('strength','Tint strength (%)',0,100,50,1)],
    'Duotone': [('contrast','Contrast',.1,3,1,.05),('balance','Balance',-.5,.5,0,.01)],
    'Posterize': [('levels','Levels per channel',2,32,6,1)],
    'Invert Colors': [],
}
CONTROLS.update(finishing.CONTROLS)
NAMES = tuple(CONTROLS)
ANIMATED = {"Color Flash","Exposure Pulse"} | finishing.ANIMATED
COLORS = {'Color Flash': [('color','Flash colour','#ffffff')],
          'Color Tint': [('color','Tint colour','#70bfff')],
          'Duotone': [('shadow','Shadows','#19204f'),('highlight','Highlights','#ffcf88')]}
DESCRIPTIONS = {
    'Color Flash':'Repeated colour flashes. White by default; adjust the speed, pulse width and softness.',
    'Exposure Pulse':'Smooth rhythmic exposure changes, with independent depth and base exposure.',
    'Color Tint':'Blend a custom colour into the footage without changing its transparency.',
    'Duotone':'Map shadows and highlights to two custom colours, with contrast and balance controls.',
    'Posterize':'Reduce the number of colour levels for a graphic, poster-like look.',
    'Invert Colors':'Invert the footage colours; use Mix for a subtler negative look.',
}

COLORS.update(finishing.COLORS)
DESCRIPTIONS.update(finishing.DESCRIPTIONS)

def number(value, default, low, high):
    try:value=float(value)
    except (TypeError,ValueError,OverflowError):value=default
    return min(high,max(low,value)) if math.isfinite(value) else default

def values(effect):
    name=effect.get('name');result={}
    for key,_,low,high,default,_ in CONTROLS.get(name,[]):
        result[key]=number(effect.get(key,default),default,low,high)
    if name=='Posterize':result['levels']=round(result['levels'])
    for key in finishing.INTEGER_KEYS:
        if key in result:result[key]=round(result[key])
    if name=='Levels':result['white']=max(result['black']+.01,result['white'])
    result['mix']=number(effect.get('mix',100),100,0,100)
    for key,_,default in COLORS.get(name,[]):
        color=QColor(str(effect.get(key,default)))
        result[key]=color.name() if color.isValid() else default
    return result

def default_effect(name, item=None):
    if name not in NAMES:raise ValueError(name)
    result=dict(name=name,enabled=True,mix=100)
    result.update({key:default for key,_,_,_,default,_ in CONTROLS[name]})
    result.update({key:default for key,_,default in COLORS.get(name,[])})
    result['clock_origin']=float(item.in_point) if item else 0.
    return result

def clock_offset(effect,item):
    origin=number(effect.get('clock_origin',0),0,-1e9,1e9)
    return (item.in_point-origin)/max(.01,item.speed)

def clock(effect,item,project_time):
    return project_time-item.start+clock_offset(effect,item)

def descriptor(effect,item=None):
    """Stable uniform layout: mode, p1, p2, colourA, colourB and clip clock offset."""
    v=values(effect);name=effect['name'];p=[0.,0.,0.,v['mix']/100];q=[0.]*4
    a=[1.]*4;b=[1.]*4
    if name=='Color Flash':p[:3]=[v['strength']/100,v['speed'],v['width']/100];q[:2]=[v['softness']/100,v['phase']/100]
    elif name=='Exposure Pulse':p[:3]=[v['depth'],v['speed'],v['base']];q[1]=v['phase']/100
    elif name=='Color Tint':p[0]=v['strength']/100
    elif name=='Duotone':p[:2]=[v['contrast'],v['balance']]
    elif name=='Posterize':p[0]=v['levels']
    elif name in finishing.CONTROLS:
        packed=[v[field[0]] for field in finishing.CONTROLS[name]]+[0.]*6
        p[:3]=packed[:3];q[:3]=packed[3:6]
    for key,target in [('color',a),('shadow',a),('highlight',b)]:
        if key in v:
            c=QColor(v[key]);target[:3]=[c.redF(),c.greenF(),c.blueF()]
    return dict(mode=NAMES.index(name)+1,shader=f'../shaders/finishing_{NAMES.index(name)+1}.frag.qsb' if name in finishing.CONTROLS else '../shaders/creative.frag.qsb',p1=p,p2=q,colorA=a,colorB=b,offset=clock_offset(effect,item) if item else 0.,flip_x=bool(item and item.transform.flip_horizontal),flip_y=bool(item and item.transform.flip_vertical))

def pulse(p,q,time):
    phase=(time*p[1]+q[1])%1
    x=min(phase,1-phase)/max(.005,p[2]/2)
    return (1-q[0])+q[0]*(1+math.cos(math.pi*x))/2 if x<1 else 0.

def apply(image,effect,time=0.):
    if image.isNull() or not effect.get('enabled',True):return image
    d=descriptor(effect);p,q=d['p1'],d['p2']
    if not p[3]:return image
    import numpy as np
    result=image.convertToFormat(QImage.Format_RGBA8888)
    pixels=np.frombuffer(result.bits(),np.uint8).reshape(result.height(),result.bytesPerLine())[:,:result.width()*4].reshape(result.height(),result.width(),4)
    rgb=pixels[:,:,:3].astype(np.float32)/255;out=rgb
    a=np.array(d['colorA'][:3]);b=np.array(d['colorB'][:3]);mode=d['mode']
    if mode==1:out=rgb+(a-rgb)*p[0]*pulse(p,q,time)
    elif mode==2:out=rgb*2**(p[2]+p[0]*(1+math.cos(2*math.pi*(time*p[1]+q[1])))/2)
    elif mode==3:out=rgb+(a-rgb)*p[0]
    elif mode==4:
        y=np.clip(((rgb*np.array([.299,.587,.114])).sum(axis=2)-.5)*p[0]+.5+p[1],0,1)[:,:,None]
        out=a+(b-a)*y
    elif mode==5:out=np.floor(rgb*(p[0]-1)+.5)/(p[0]-1)
    elif mode==6:out=1-rgb
    else:out=finishing.evaluate(effect["name"],rgb,[*p[:3],*q[:3]],a,b,time)
    out=rgb+(np.clip(out,0,1)-rgb)*p[3]
    pixels[:,:,:3]=np.clip(np.floor(out*255+.5),0,255).astype(np.uint8)
    return result

def filter_string(effect,time_expression):
    """FFmpeg fallback uses the same equations, after the existing PTS mapping."""
    d=descriptor(effect);p,q=d['p1'],d['p2'];a=d['colorA'];b=d['colorB'];mode=d['mode']
    advanced=finishing.ffmpeg_expressions(effect['name'],[*p[:3],*q[:3]],a,b,time_expression) if effect['name'] in finishing.CONTROLS else None
    expressions=[]
    for n,ch in enumerate('rgb'):
        c=f'{ch}(X,Y)/255';out=c
        if mode==1:
            phase=f'mod(mod(({time_expression})*{p[1]}+{q[1]},1)+1,1)'
            x=f'min({phase},1-({phase}))/{max(.005,p[2]/2)}'
            strength=f'{p[0]}*if(lt({x},1),{1-q[0]}+{q[0]}*(1+cos(PI*({x})))/2,0)'
            out=f'({c})+({a[n]}-({c}))*({strength})'
        elif mode==2:out=f'({c})*pow(2,{p[2]}+{p[0]}*(1+cos(2*PI*(({time_expression})*{p[1]}+{q[1]})))/2)'
        elif mode==3:out=f'({c})+({a[n]}-({c}))*{p[0]}'
        elif mode==4:
            y=f'clip(((.299*r(X,Y)+.587*g(X,Y)+.114*b(X,Y))/255-.5)*{p[0]}+.5+{p[1]},0,1)'
            out=f'{a[n]}+{b[n]-a[n]}*({y})'
        elif mode==5:out=f'floor(({c})*{p[0]-1}+.5)/{p[0]-1}'
        elif mode==6:out=f'1-({c})'
        elif advanced:out=advanced[n]
        expressions.append(f"{ch}='255*(({c})+(clip({out},0,1)-({c}))*{p[3]})'")
    return 'format=rgba,geq='+':'.join(expressions)+":a='alpha(X,Y)':interpolation=bilinear"
