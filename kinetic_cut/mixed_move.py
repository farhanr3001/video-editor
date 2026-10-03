"""One horizontal placement transaction for a mixed media/subtitle selection."""
import copy
from PySide6.QtCore import Qt
from .model import uid


def snap_move(view,delta,edges,item_ids=(),caption_ids=(),destination_tracks=None):
    view.snap_guide=None
    if not view.property('snapping'):
        view._move_snap=None; return delta
    # Same-lane boundaries take precedence over slightly offset cuts in other
    # layers or the playhead. Those remain useful fallback alignment targets.
    tracks=set(destination_tracks) if destination_tracks is not None else {i.track for i in view.project.timeline if i.id in item_ids}
    preferred=[e for i in view.project.timeline if i.id not in item_ids and i.track in tracks for e in (i.start,i.start+i.duration)]
    if caption_ids:preferred += [e for c in view.project.captions if c.id not in caption_ids for e in (c.start,c.end)]
    points=[0.,view.project.playhead]
    points += [e for i in view.project.timeline if i.id not in item_ids for e in (i.start,i.start+i.duration)]
    points += [e for c in view.project.captions if c.id not in caption_ids for e in (c.start,c.end)]
    near=min(((abs(edge+delta-point),edge,point) for edge in edges for point in preferred),default=None)
    held=getattr(view,'_move_snap',None)
    if held and held[1] in points and abs(held[0]+delta-held[1])*view.pixels_per_second<=18:
        if held[1] in preferred or not near or near[0]*view.pixels_per_second>10:
            view.snap_guide=held[1]; return held[1]-held[0]
    view._move_snap=None
    distance,edge,point=near if near and near[0]*view.pixels_per_second<=10 else min((abs(edge+delta-point),edge,point) for edge in edges for point in points)
    if distance*view.pixels_per_second<=10:
        view._move_snap=(edge,point); view.snap_guide=point; return point-edge
    return delta


def begin(view,pos,section,modifiers):
    items=view.selected_items()
    if view._state('subtitle_1').get('locked') or any(view._state(i.track).get('locked') for i in items):
        view.drag_mode=''; return
    view.snapshots={i.id:copy.deepcopy(i) for i in items}
    view.caption_snapshots={c.id:copy.deepcopy(c) for c in view.project.captions if c.id in view.selected_caption_ids}
    view.alt_drag=bool(modifiers&Qt.AltModifier); view._move_snap=None
    view.caption_copy_ids={key:uid() if view.alt_drag else key for key in view.caption_snapshots}
    view.caption_preview=[]; view.caption_painted=None; view.drag_mode='mixed_move'
    view.clip_scroll.begin(pos,section,modifiers)


def move(view,delta):
    if not view.move_preview and abs(delta*view.pixels_per_second)<5:return
    starts=[i.start for i in view.snapshots.values()]+[c.start for c in view.caption_snapshots.values()]
    ends=[i.start+i.duration for i in view.snapshots.values()]+[c.end for c in view.caption_snapshots.values()]
    delta=round(delta*view.project.settings.fps)/view.project.settings.fps
    delta=snap_move(view,delta,starts+ends,view.snapshots,view.caption_snapshots)
    delta=max(-min(starts),delta)
    view.move_preview=[]
    for old in view.snapshots.values():
        item=copy.deepcopy(old); item.start+=delta; item._drag_ghost=True; view.move_preview.append(item)
    view.caption_preview=[]
    for key,old in view.caption_snapshots.items():
        c=copy.deepcopy(old); c.start+=delta; c.end+=delta; c.id=view.caption_copy_ids[key]; view.caption_preview.append(c)
    stage=copy.copy(view.project)
    replaced={c.id for c in view.caption_preview}
    stage.captions=copy.deepcopy([c for c in view.project.captions if c.id not in replaced])+view.caption_preview
    stage.overwrite_captions(replaced,notify=False); view.caption_painted=stage.captions


def finish(view):
    if not view.move_preview:return
    if view._state('subtitle_1').get('locked') or any(view._state(i.track).get('locked') for i in view.move_preview):
        view.cancel_drag(); return
    placed=set(); links={}; groups={}; primary=''
    for ghost in view.move_preview:
        if view.alt_drag:
            item=copy.deepcopy(ghost); del item._drag_ghost; item.id=uid()
            key=item.group_id if item.link_id is None else item.link_id
            item.link_id=links.setdefault(key,uid()) if key else ''
            item.group_id=groups.setdefault(item.group_id,uid()); view.project.timeline.append(item)
        else:
            item=view.project.item_by_id(ghost.id)
            if item is None:continue
            item.start=ghost.start
        placed.add(item.id)
        if ghost.id==view.selected_id:primary=item.id
    view.project.overwrite(placed)
    view.project.captions=view.caption_painted
    captions={c.id for c in view.caption_preview}; cap=view.caption_copy_ids.get(view.selected_caption,'')
    view.move_preview=[]
    view.select_ids(placed,primary,True); view.select_captions(captions,cap,True)
    from .caption_gestures import clear
    clear(view); view.itemChanged.emit(primary)
