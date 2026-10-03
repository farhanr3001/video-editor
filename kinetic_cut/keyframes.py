"""Clip-local scalar curves shared by preview, editing and export expressions."""
import copy,math

PROPERTIES={'x':('Position X',-5.,5.,.01),'y':('Position Y',-5.,5.,.01),
            'scale':('Zoom X',.05,8.,.01),'scale_y':('Zoom Y',.05,8.,.01),
            'rotation':('Rotation',-3600.,3600.,1.),'opacity':('Opacity',0.,100.,1.)}
MODES=('Linear','Smooth','Hold')

def clean(curves):
    result={}
    for name,keys in (curves or {}).items():
        if name not in PROPERTIES:continue
        values={}; _,low,high,_=PROPERTIES[name]
        for key in keys:
            t=float(key['time']); value=float(key['value'])
            if not math.isfinite(t) or not math.isfinite(value):raise ValueError('Keyframes must contain finite numbers')
            values[t]={'time':t,'value':max(low,min(high,value)),'interpolation':key.get('interpolation','Linear') if key.get('interpolation','Linear') in MODES else 'Linear'}
        if values:result[name]=[values[t] for t in sorted(values)]
    return result

def base(item,name):
    return item.opacity if name=='opacity' else item.transform.effective_scale_y if name=='scale_y' else getattr(item.transform,name)

def value(keys,time,default):
    if not keys:return default
    if time<=keys[0]['time']:return keys[0]['value']
    for a,b in zip(keys,keys[1:]):
        if time<b['time']:
            q=(time-a['time'])/(b['time']-a['time']); mode=a.get('interpolation','Linear')
            if mode=='Hold':q=0
            elif mode=='Smooth':q=q*q*(3-2*q)
            return a['value']+(b['value']-a['value'])*q
    return keys[-1]['value']

def evaluated(item,local_time):
    if not item.keyframes:return item
    result=copy.copy(item); result.transform=copy.copy(item.transform)
    for name,keys in item.keyframes.items():
        number=value(keys,local_time,base(item,name))
        if name=='opacity':result.opacity=number
        else:setattr(result.transform,name,number)
    return result

def shift(item,delta):
    item.keyframes={name:[dict(k,time=k['time']-delta) for k in keys] for name,keys in item.keyframes.items()}

def stretch(item,ratio):
    item.keyframes={name:[dict(k,time=k['time']*ratio) for k in keys] for name,keys in item.keyframes.items()}

def put(item,name,time,number,mode='Linear',epsilon=1e-7):
    keys=[k for k in item.keyframes.get(name,[]) if abs(k['time']-time)>epsilon]
    keys.append(dict(time=time,value=number,interpolation=mode)); item.keyframes=clean({**item.keyframes,name:keys})

def expression(item,name,time='t'):
    keys=item.keyframes.get(name,[])
    if not keys and name=='scale_y' and item.transform.scale_y is None:return expression(item,'scale',time)
    if not keys:return f'{base(item,name):.12g}'
    result=f'{keys[-1]["value"]:.12g}'
    for a,b in reversed(list(zip(keys,keys[1:]))):
        q=f'(({time})-{a["time"]:.12g})/{b["time"]-a["time"]:.12g}'
        mode=a.get('interpolation','Linear')
        if mode=='Hold':segment=f'{a["value"]:.12g}'
        else:
            if mode=='Smooth':q=f'({q})*({q})*(3-2*({q}))'
            segment=f'{a["value"]:.12g}+({b["value"]-a["value"]:.12g})*({q})'
        result=f'if(lt(({time}),{b["time"]:.12g}),{segment},{result})'
    return f'if(lt(({time}),{keys[0]["time"]:.12g}),{keys[0]["value"]:.12g},{result})'
