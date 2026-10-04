"""Background availability checks and transactional, folder-scoped relinking."""
import copy
from dataclasses import asdict
from pathlib import Path
from PySide6.QtCore import QObject,QTimer,Qt
from PySide6.QtWidgets import QFileDialog,QMessageBox
from . import missing_media as offline
from .model import MediaItem

class MissingMediaController(QObject):
    def __init__(self,panel):
        super().__init__(panel); self.panel=panel; self.busy=False; self.relinking=False
        self.timer=QTimer(self); self.timer.setInterval(2500); self.timer.timeout.connect(self.check); self.timer.start()
        QTimer.singleShot(0,self.check)

    def check(self):
        w=self.panel.window
        if self.busy or getattr(getattr(w,'transport',None),'closed',False):return
        from .ui import Worker
        paths=offline.source_paths(w.project)
        paths.extend(m.path for e in self.panel.power.data['media'] for m in offline.leaf_media(MediaItem(**e['media'])))
        paths.extend(entry.path for folder in self.panel.watch_folders.folders.values() for entry in folder.entries.values())
        self.busy=True; worker=Worker(offline.scan,paths)
        worker.signals.result.connect(self.checked)
        worker.signals.finished.connect(lambda:setattr(self,'busy',False)); w.start_worker(worker)

    def checked(self,values):
        if getattr(getattr(self.panel.window,'transport',None),'closed',False):return
        changed=offline.publish(values)
        if not changed:return
        self.invalidate(changed)
        self.refresh()

    def refresh(self):
        panel=self.panel; ids={i.data(Qt.UserRole) for i in panel.grid.selectedItems()}; current=panel.grid.currentItem()
        primary=current.data(Qt.UserRole) if current else None; scroll=panel.grid.verticalScrollBar().value()
        panel.refresh(); panel.grid.blockSignals(True)
        for n in range(panel.grid.count()):
            item=panel.grid.item(n)
            if item.data(Qt.UserRole)==primary:panel.grid.setCurrentItem(item)
            item.setSelected(item.data(Qt.UserRole) in ids)
        panel.grid.blockSignals(False); panel.grid.verticalScrollBar().setValue(scroll)
        self.panel.window.timeline.viewport().update(); self.panel.window.preview.update()

    def invalidate(self,paths):
        w=self.panel.window
        ids={m.id for m in w.project.media if offline.path_key(m.path) in paths or m.compound}
        if not hasattr(w,'transport'):return
        for key in list(w.transport.decoders):
            if key[0] in ids:w.transport.retire_decoder(key)
        from .media_source import set_media_source
        from .pool_tools import SourcePreview
        from PySide6.QtCore import QUrl
        players=[w.player]+[dialog.player for dialog in w.media_panel.findChildren(SourcePreview) if dialog.player]
        for player in players:
            url=player.source()
            if url.isLocalFile() and offline.path_key(url.toLocalFile()) in paths:
                player.stop(); set_media_source(player,QUrl())
        w.transport.previous_video.clear(); w.transport.boundary_holds.clear()
        w.preview.still_cache.clear(); w.timeline.thumbnails.clear(); w.timeline._scaled_thumbnails.clear(); w.timeline._waveform_pixmaps.clear()
        for id in ids:
            getattr(w.transport,'_audio_source_signatures',{}).pop(id,None)
            w.proxies.pop(id,None); w.preview_quality.ready.pop(id,None)
            w.timeline.waveforms.pop(id,None); w.timeline.waveform_pending.discard(id); w.timeline.waveform_failures.discard(id)
            media=w.project.media_by_id(id)
            if media and not offline.is_missing(media):w.request_waveform(media)
        w.transport.sync(True)

    def choose_file(self,media):
        if self.relinking or self.panel.window.current_page!=0:return
        if media.compound:
            QMessageBox.information(self.panel,'Compound media','Open this compound in the timeline and relink its missing source media. The compound itself does not need a replacement file.'); return
        if media.timeline_preset:
            blocked={i['media_id'] for i in media.timeline_preset.get('items',[]) if i.get('source_mismatch')}
            media=next((m for m in offline.leaf_media(media) if offline.is_missing(m) or m.id in blocked),None)
        if not media:return
        path,_=QFileDialog.getOpenFileName(self.panel,'Replace '+Path(media.path).name,str(Path(media.path).parent),'Media files (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.ts *.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.png *.jpg *.jpeg *.webp *.bmp)')
        if path:self.start([(copy.deepcopy(media),path)])

    def choose_folder(self):
        panel=self.panel
        if self.relinking or panel.window.current_page!=0:return
        folder=QFileDialog.getExistingDirectory(panel,'Change source folder of all missing items')
        if not folder:return
        media=offline.iter_media(panel.window.project) if panel.folder=='project' else [MediaItem(**e['media']) for e in panel.power.data['media'] if e['folder']==panel.folder]
        leaves={(m.id,m.path):m for asset in media for m in offline.leaf_media(asset) if offline.is_missing(m)}
        self.start([(copy.deepcopy(m),str(Path(folder)/Path(m.path).name)) for m in leaves.values()])

    def start(self,requests):
        if not requests:return
        from .ui import Worker
        from .media import probe
        w=self.panel.window; self.relinking=True; project=w.project; folder=self.panel.folder
        ffprobe=w.settings.get('ffprobe','ffprobe'); ffmpeg=w.settings.get('ffmpeg','ffmpeg')
        w.transport.pause(); w.statusBar().showMessage('Checking replacement media…')
        def prepare():
            good=[]; errors=[]
            for old,path in requests:
                try:good.append((old,probe(path,ffprobe,ffmpeg)))
                except Exception as exc:errors.append(Path(path).name+': '+str(exc)[-250:])
            return good,errors
        def apply(result):
            if w.project is not project or getattr(w.transport,'closed',False):return
            if w.current_page!=0:
                w.statusBar().showMessage('Relinking cancelled because the workspace changed. Return to Edit and try again.',8000); return
            good,errors=result; restored=blocked=applied=0; changed=set()
            for old,new in good:
                if folder=='project':
                    current=next((m for m in offline.iter_media(project) if m.id==old.id and m.path==old.path),None)
                    if not current or current.path!=old.path:continue
                    counts=offline.replace(project,old.path,new)
                else:
                    entries=[e for e in self.panel.power.data['media'] if e['folder']==folder and any(m.id==old.id and m.path==old.path for m in offline.leaf_media(MediaItem(**e['media'])))]
                    if not entries:continue
                    for entry in entries:
                        updated=MediaItem(**entry['media']); offline.replace_bin_asset(updated,old.path,new); entry['media']=asdict(updated)
                    counts=offline.replace(project,old.path,new)
                restored+=counts[0]; blocked+=counts[1]; applied+=1
                changed.update((offline.path_key(old.path),offline.path_key(new.path)))
                offline.publish({offline.path_key(new.path):False})
            if applied:
                if folder!='project':self.panel.power.save()
                self.invalidate(changed); w.model_changed(); self.refresh(); w.preview_quality.request()
            message=f'Relinked {applied} media · {restored} cuts restored · {blocked} cuts marked mismatch.'
            if errors:message+=f' {len(errors)} files not found or unreadable; left unchanged.'
            w.statusBar().showMessage(message,15000)
            if errors:QMessageBox.warning(self.panel,'Some media could not be relinked',message+'\n\n'+'\n'.join(errors[:12]))
            if applied:
                from .vision_ui import reanalyse_pasted
                targets=[i for i in project.timeline if not i.source_mismatch and project.media_by_id(i.media_id) and offline.path_key(project.media_by_id(i.media_id).path) in changed]
                reanalyse_pasted(w,targets,context='relinked')
        worker=Worker(prepare); worker.signals.result.connect(apply)
        worker.signals.finished.connect(lambda:setattr(self,'relinking',False)); w.start_worker(worker)
