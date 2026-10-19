"""Draggable time actions backed by the editor's established retime commands."""
import copy

PRESETS={'Slow Motion · 50%':.5,'Slow Motion · 25%':.25,'Fast Motion · 200%':2.,'Time-lapse · 400%':4.}
CONTROLS='Speed / Retime Controls'
NAMES=(*PRESETS,CONTROLS)
DESCRIPTIONS={name:f'Play video at {speed*100:g}% speed, keeping its source range. Linked audio follows. Opens retime controls; this preset never overwrites neighboring clips.' for name,speed in PRESETS.items()}
DESCRIPTIONS[CONTROLS]='Show the selected video clips’ existing speed controls (Ctrl+R).'

def conflicts(project,ids,speed):
    trial=copy.deepcopy(project);trial.retime_items(ids,speed)
    for item in trial.timeline:
        if item.id not in ids:continue
        for other in trial.runtime_index.query('timeline',item.start,item.start+item.duration):
            if other.id==item.id or other.track!=item.track:continue
            # The standard retime command subtracts any remaining overlap,
            # even if it existed before the speed change. Presets must refuse
            # that too, rather than silently trimming a neighboring clip.
            new_overlap=max(0,min(item.start+item.duration,other.start+other.duration)-max(item.start,other.start))
            if new_overlap>1e-7:return True
    return False

def apply(window,name):
    from .effects import compatible
    from PySide6.QtWidgets import QMessageBox
    timeline=window.timeline;project=window.project
    selected=timeline.selected_ids or {timeline.selected_id}
    targets={i for i in selected if compatible(name,project.item_by_id(i),project)}
    if not targets:
        window.statusBar().showMessage('Select an unlocked video clip to change its speed.',4000);return
    ids=timeline.expanded(targets)
    if any(project.track_states.get(project.item_by_id(i).track,{}).get('locked') for i in ids if project.item_by_id(i)):
        QMessageBox.information(window,'Linked layer locked','Unlock the linked video/audio layers before changing speed.');return
    if name in PRESETS and conflicts(project,ids,PRESETS[name]):
        QMessageBox.information(window,'Clips overlap','This speed change would leave overlapping clips. Move or trim them apart first, or adjust the clip using the retime controls. No clips were changed.')
        timeline.select_ids(ids,timeline.selected_id);timeline.retime_ids.update(ids);timeline.viewport().update();return
    timeline.select_ids(ids,timeline.selected_id)
    if name==CONTROLS:
        timeline.retime_ids.update(ids);timeline.viewport().update();return
    timeline.set_speed(PRESETS[name])
    window.statusBar().showMessage(f'Applied {name}. Adjust the speed using the clip’s retime controls.',4000)
