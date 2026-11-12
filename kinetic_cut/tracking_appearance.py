"""Sparse source-time appearance keys; independent of the tracking trajectory."""
import math

# Keep asset paths on the marker itself: temporal Image states select this same
# asset. This keeps existing project collection/relink rules fully applicable.
FIELDS = frozenset(('mode','loss_policy','follow_scale','width','height','padding',
    'offset_x','offset_y','rotation','opacity','color','stroke_width','fill','blur',
    'pixel_size','arrow_length','arrow_head','label','font','font_size',
    'label_color','label_background','label_padding','radius'))
MAX_KEYS = 10000


def states(marker):
    records=marker.get('appearance_keys',[])
    if not isinstance(records,list) or len(records)>MAX_KEYS:
        raise ValueError('Invalid tracked marker appearance keys')
    previous=-1.
    for record in records:
        if not isinstance(record,dict):raise ValueError('Invalid marker appearance key')
        stamp=record.get('time');values=record.get('values')
        if isinstance(stamp,bool) or not isinstance(stamp,(float,int)) or not math.isfinite(stamp) or stamp<0 or stamp<=previous:
            raise ValueError('Marker appearance times must be finite and increasing')
        if not isinstance(values,dict) or not values or set(values)-FIELDS:
            raise ValueError('Invalid marker appearance properties')
        previous=stamp
    return records


def evaluate(marker,at):
    result=dict(marker)
    # Each sparse key changes only specified fields, held until their next key.
    for record in states(marker):
        if record['time']>at+1e-7:break
        result.update(record['values'])
    result.pop('appearance_keys',None)
    return result


def edit(marker,times,values):
    values={k:v for k,v in values.items() if k in FIELDS}
    if not values:return
    records={r['time']:dict(r['values']) for r in states(marker)}
    for stamp in times:records.setdefault(float(stamp),{}).update(values)
    if len(records)>MAX_KEYS:raise ValueError('Too many tracked marker appearance keys')
    marker['appearance_keys']=[dict(time=t,values=v) for t,v in sorted(records.items())]


def variants(marker):
    current=dict(marker);current.pop('appearance_keys',None)
    yield dict(current)
    for key in states(marker):
        current.update(key['values']);yield dict(current)
