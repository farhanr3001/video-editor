"""Atomic, bounded scene edits shared by automation and composition tooling."""
import copy
from .motion import validate,CHANNELS,finite,clean_curves

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
        elif kind=='scene_settings':
            values=op.get('values')
            if not isinstance(values,dict) or set(values)-{'canvas','motion_blur','sound_cues'}:raise ValueError('Use canvas/motion_blur/sound_cues scene settings')
            result.update(copy.deepcopy(values))
        else:raise ValueError('Unknown motion edit operation')
    return validate(result)
