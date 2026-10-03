"""Subtitle placement/trim previews use the same overwrite semantics as media."""
import copy
from .model import uid

def begin(view,primary,alt):
    view._move_snap=None
    view.caption_snapshots={c.id:copy.deepcopy(c) for c in view.project.captions if c.id in view.selected_caption_ids}
    view.caption_copy_ids={key:uid() if alt and view.drag_mode=='caption_move' else key for key in view.caption_snapshots}
    view.caption_preview=[]; view.caption_painted=None

def move(view,delta):
    old=view.caption_snapshots.get(view.selected_caption)
    if not old:return
    originals=view.caption_snapshots; mode=view.drag_mode
    if mode=='caption_move' and not view.caption_preview and abs(delta*view.pixels_per_second)<5:return
    if mode=='caption_move':
        from .mixed_move import snap_move
        delta=snap_move(view,delta,[edge for c in originals.values() for edge in (c.start,c.end)],caption_ids=originals)
        delta=max(-min(c.start for c in originals.values()),delta)
    elif mode=='caption_left':
        delta=view.snap_edge(old.start+delta,exclude_captions=originals)-old.start
        delta=max(-min(c.start for c in originals.values()),min(delta,min(c.end-c.start-.05 for c in originals.values())))
    else:
        delta=view.snap_edge(old.end+delta,exclude_captions=originals)-old.end
        delta=max(max(.05-c.end+c.start for c in originals.values()),delta)
    view.caption_preview=[]
    for key,original in originals.items():
        c=copy.deepcopy(original); c.id=view.caption_copy_ids[key]
        if mode=='caption_move':c.start+=delta; c.end+=delta
        elif mode=='caption_left':
            from .caption_words import shift_origin
            c.start+=delta; shift_origin(c,delta)
        else:c.end+=delta
        view.caption_preview.append(c)
        if c.id==key:
            live=next((current for current in view.project.captions if current.id==key),None)
            if live:live.start=c.start; live.end=c.end
    stage=copy.copy(view.project); replaced={c.id for c in view.caption_preview}
    stage.captions=[c for c in view.project.captions if c.id not in replaced]+view.caption_preview
    stage.overwrite_captions(replaced,notify=False); view.caption_painted=stage.captions

def finish(view):
    if view.caption_painted is not None and not view.project.track_states.get('subtitle_1',{}).get('locked'):
        view.project.captions=view.caption_painted; primary=view.caption_copy_ids.get(view.selected_caption,'')
        view.select_captions({c.id for c in view.caption_preview},primary)
    clear(view)

def clear(view):
    view.caption_snapshots={}; view.caption_copy_ids={}; view.caption_preview=[]; view.caption_painted=None; view.caption_original=None
