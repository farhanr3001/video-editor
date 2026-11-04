"""Atomic, bounded scene edits shared by automation and composition tooling."""
import copy
from .motion import validate,CHANNELS,finite,clean_curves

def K(t,v,mode='Ease Out'):return dict(time=t,value=v,interpolation=mode)
def _slide(dx,dy):
    def build(n,t0,d,a):
        out={}
        if dx:out['x']=[K(t0,n.get('x',0)+dx*a,'Ease Out'),K(t0+d,n.get('x',0))]
        if dy:out['y']=[K(t0,n.get('y',0)+dy*a,'Ease Out'),K(t0+d,n.get('y',0))]
        out['opacity']=[K(t0,0),K(t0+d*.6,n.get('opacity',100),'Linear')]
        return out
    return build
ANIMATIONS={
 'fade_in':lambda n,t0,d,a:{'opacity':[K(t0,0),K(t0+d,n.get('opacity',100))]},
 'fade_out':lambda n,t0,d,a:{'opacity':[K(t0,n.get('opacity',100),'Ease In'),K(t0+d,0)]},
 'pop_in':lambda n,t0,d,a:{'scale':[K(t0,.6/max(a,.01) if a>1 else .6,'Back Out'),K(t0+d,n.get('scale',1))],'opacity':[K(t0,0),K(t0+d*.6,n.get('opacity',100),'Linear')]},
 'pop_out':lambda n,t0,d,a:{'scale':[K(t0,n.get('scale',1),'Ease In'),K(t0+d,0)],'opacity':[K(t0,n.get('opacity',100)),K(t0+d,0,'Ease In')]},
 'slide_in_left':_slide(-300,0),'slide_in_right':_slide(300,0),'slide_in_up':_slide(0,300),'slide_in_down':_slide(0,-300),
 'draw_on':lambda n,t0,d,a:{'trim':[K(t0,0,'Ease In Out'),K(t0+d,1)]},
 'wipe_out':lambda n,t0,d,a:{'trim':[K(t0,1,'Ease In Out'),K(t0+d,0)]},
 'pulse':lambda n,t0,d,a:{'scale':[K(t0,n.get('scale',1),'Linear'),K(t0+d*.3,n.get('scale',1)*(1+.2*a),'Ease Out'),K(t0+d,n.get('scale',1),'Ease In Out')]},
 'shake':lambda n,t0,d,a:{'x':[K(t0+d*i/8,n.get('x',0)+(18*a*(-1)**i if 0<i<8 else 0),'Linear') for i in range(9)]},
 'spin_in':lambda n,t0,d,a:{'rotation':[K(t0,n.get('rotation',0)-180*a,'Ease Out'),K(t0+d,n.get('rotation',0))],'scale':[K(t0,0,'Ease Out'),K(t0+d,n.get('scale',1))]},
}

def apply(scene,operations):
    result=copy.deepcopy(scene)
    if not isinstance(operations,list) or not 1<=len(operations)<=256:raise ValueError('Provide 1–256 motion edits')
    def node(node_id):
        found=next((n for n in result['nodes'] if n['id']==node_id),None)
        if found is None:raise ValueError('Unknown motion layer')
        return found
    for op in operations:
        if not isinstance(op,dict):raise ValueError('Motion edit must be an object')
        kind=op.get('op')
        if kind=='add_layer':
            raw=op.get('node');
            if not isinstance(raw,dict):raise ValueError('Add layer requires a node')
            result['nodes'].append(copy.deepcopy(raw))
        elif kind=='update_layer':
            target=node(op.get('id')); values=op.get('values')
            if not isinstance(values,dict) or 'id' in values:raise ValueError('Layer ID cannot be changed')
            target.update(copy.deepcopy(values))
        elif kind=='remove_layer':
            target=node(op.get('id')); ids={target['id']}
            while True:
                more={n['id'] for n in result['nodes'] if n.get('parent') in ids}
                if more<=ids:break
                ids|=more
            result['nodes']=[n for n in result['nodes'] if n['id'] not in ids]
            if 'sound_cues' in result:result['sound_cues']=[c for c in result['sound_cues'] if c.get('event','time')=='time' or c.get('node_id') not in ids]
        elif kind=='move_layer':
            target=node(op.get('id')); before=node(op['before']) if op.get('before') else None
            if before is target:continue
            result['nodes'].remove(target); result['nodes'].insert(result['nodes'].index(before) if before else len(result['nodes']),target)
        elif kind in ('set_key','remove_key'):
            target=node(op.get('id')); channel=op.get('channel'); t=finite(op.get('time'))
            if channel not in CHANNELS or t<0:raise ValueError('Invalid key channel/time')
            keys=target.setdefault('keyframes',{}).setdefault(channel,[])
            keys[:]=[k for k in keys if abs(k['time']-t)>1e-5]
            if kind=='remove_key' and 'sound_cues' in result:
                result['sound_cues']=[c for c in result['sound_cues'] if not(c.get('event')=='keyframe' and c.get('node_id')==target['id'] and c.get('channel')==channel and abs(c.get('key_time',-1)-t)<1e-5)]
            if kind=='set_key':
                key=dict(time=t,value=op.get('value'),interpolation=op.get('interpolation','Linear'))
                if 'bezier' in op:key['bezier']=op['bezier']
                keys.extend(clean_curves({channel:[key]})[channel]); keys.sort(key=lambda k:k['time'])
        elif kind=='animate':
            target=node(op.get('id')); preset=op.get('preset'); t0=finite(op.get('start',0)); d=finite(op.get('duration',.5))
            if preset not in ANIMATIONS or d<=0 or t0<0:raise ValueError('animate needs preset '+', '.join(ANIMATIONS)+', start >= 0 and duration > 0')
            amount=finite(op.get('amount',1)); curves=target.setdefault('keyframes',{})
            generated=ANIMATIONS[preset](target,t0,d,amount)
            if 'scale' in generated and 'scale_y' not in generated:
                # scale is the horizontal factor; keep pops/pulses uniform by keying scale_y in proportion
                ratio=target.get('scale_y',1)/(target.get('scale',1) or 1)
                generated['scale_y']=[dict(k,value=k['value']*ratio) for k in generated['scale']]
            for channel,keys in generated.items():
                existing=curves.setdefault(channel,[]); times=[k['time'] for k in keys]
                existing[:]=[k for k in existing if not min(times)-1e-5<=k['time']<=max(times)+1e-5]+keys; existing.sort(key=lambda k:k['time'])
        elif kind=='pulse':
            target=node(op.get('id')); channel=op.get('channel','scale'); times=op.get('times')
            if channel not in CHANNELS or not isinstance(times,list) or not 1<=len(times)<=128:raise ValueError('pulse needs a channel and 1-128 times')
            base=finite(op.get('base',CHANNELS[channel])); peak=finite(op.get('peak',base*1.15 if base else 1)); attack=max(.005,finite(op.get('attack',.05))); decay=max(.01,finite(op.get('decay',.25)))
            keys=target.setdefault('keyframes',{}).setdefault(channel,[]); added={}
            for raw in sorted(finite(v) for v in times):
                if raw<0:continue
                added[round(raw,5)]=dict(time=raw,value=base,interpolation='Linear')
                added[round(raw+attack,5)]=dict(time=raw+attack,value=peak,interpolation='Ease Out')
                added[round(raw+attack+decay,5)]=dict(time=raw+attack+decay,value=base,interpolation='Ease In Out')
            new=clean_curves({channel:list(added.values())})[channel]; lo,hi=min(k['time'] for k in new),max(k['time'] for k in new)
            keys[:]=[k for k in keys if not lo-1e-5<=k['time']<=hi+1e-5]+new; keys.sort(key=lambda k:k['time'])
        elif kind=='scene_settings':
            values=op.get('values')
            if not isinstance(values,dict) or set(values)-{'canvas','motion_blur','sound_cues','camera','post','floor','background'}:raise ValueError('Use canvas/motion_blur/sound_cues/camera/post/floor/background scene settings')
            result.update(copy.deepcopy(values))
        elif kind=='insert_asset':
            from .motion_assets import insert
            result,_=insert(result,op.get('name',''),op.get('x'),op.get('y'),finite(op.get('time',0)))
        elif kind=='add_scene':
            # A beat container: fades in, then blurs/fades (or slides) out so the next scene can take over.
            start=finite(op.get('start',0)); end=finite(op.get('end',start+3)); fade_in=finite(op.get('fade_in',.25)); fade_out=finite(op.get('fade_out',.3))
            if end<=start or op.get('id') in {n['id'] for n in result['nodes']} or not isinstance(op.get('id'),str) or not op['id']:raise ValueError('add_scene needs a new id and end > start')
            handoff=op.get('handoff','blur'); keys={'opacity':[dict(time=start,value=0.,interpolation='Ease Out'),dict(time=start+fade_in,value=100.,interpolation='Ease Out'),dict(time=end-fade_out,value=100.,interpolation='Ease In'),dict(time=end,value=0.,interpolation='Ease Out')]}
            if handoff=='blur':keys['blur']=[dict(time=end-fade_out,value=0.,interpolation='Ease In'),dict(time=end,value=finite(op.get('amount',14)),interpolation='Ease Out')]
            elif handoff=='slide':
                d=finite(op.get('amount',90)); keys['x']=[dict(time=start,value=d,interpolation='Ease Out'),dict(time=start+.35,value=0.,interpolation='Ease Out'),dict(time=end-fade_out,value=0.,interpolation='Ease In'),dict(time=end,value=-d,interpolation='Ease Out')]
                keys['blur_x']=[dict(time=start,value=d/2,interpolation='Ease Out'),dict(time=start+.35,value=0.,interpolation='Ease Out'),dict(time=end-fade_out,value=0.,interpolation='Ease In'),dict(time=end,value=d/2,interpolation='Ease Out')]
            elif handoff!='fade':raise ValueError('handoff must be blur, slide or fade')
            result['nodes'].append(dict(id=op['id'],name=op.get('name',op['id']),kind='group',x=0.,y=0.,start=start,end=end,keyframes=keys))
            for child in op.get('children',[]):node(child)['parent']=op['id']
        elif kind=='sequence':
            # Lay existing scene groups end to end (each keeps its length), overlapping by `overlap` for the hand-off.
            at=finite(op.get('start',0)); overlap=finite(op.get('overlap',.2)); ids=op.get('ids')
            if not isinstance(ids,list) or not ids:raise ValueError('sequence needs ids')
            for scene_id in ids:
                group=node(scene_id); length=group.get('end',group.get('start',0)+3)-group.get('start',0); shift=at-group.get('start',0)
                branch={scene_id}
                while True:
                    more={n['id'] for n in result['nodes'] if n.get('parent') in branch}-branch
                    if not more:break
                    branch|=more
                for n in result['nodes']:
                    if n['id'] not in branch:continue
                    for key in ('start','end'):
                        if key in n:n[key]=max(0.,n[key]+shift)
                    for curve_keys in n.get('keyframes',{}).values():
                        for key in curve_keys:key['time']=max(0.,key['time']+shift)
                at+=max(.05,length-overlap)
        else:raise ValueError('Unknown motion edit operation')
    return validate(result)
