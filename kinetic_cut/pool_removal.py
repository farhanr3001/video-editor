"""Confirmed bin removal through existing project deletion operations."""
from PySide6.QtWidgets import QMessageBox
from .media_insert import source_key


def remove(panel,ids,folder):
    window=panel.window
    if window.current_page!=0 or not ids:return False
    project=window.project
    if folder=='project':
        media_ids={m.id for m in project.media if m.id in ids}
    else:
        entries=[e for e in panel.power.data['media'] if e['folder']==folder and e['media']['id'] in ids]
        if not entries:return False
        paths={source_key(e['media']['path']) for e in entries if e['media'].get('path')}
        media_ids={m.id for m in project.media if m.id in ids or m.path and source_key(m.path) in paths}
    clips=[i for i in project.timeline if i.media_id in media_ids]
    if any(project.track_states.get(i.track,{}).get('locked') for i in clips):
        QMessageBox.information(window,'Media on locked tracks','Unlock the affected timeline tracks before removing this media.')
        return False
    if clips:
        answer=QMessageBox.warning(window,'Remove media used in timeline',
            f'{len(ids)} selected media item(s) detected. Removing them from the '+('Media Pool' if folder=='project' else 'Power Bin')+
            f' will also remove {len(clips)} timeline clip(s).\n\nOriginal source files will stay on disk.',
            QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)
        if answer!=QMessageBox.Ok:return False
    if folder!='project':
        panel.power.data['media']=[e for e in panel.power.data['media'] if not(e['folder']==folder and e['media']['id'] in ids)]
        panel.power.save()
    window.timeline.cancel_drag()
    project.delete({i.id for i in clips})
    if folder=='project':project.media=[m for m in project.media if m.id not in media_ids]
    if window.current_media_id in media_ids:window.current_media_id=''
    if clips or folder=='project':window.model_changed()
    panel.refresh(preserve=True)
    return True
