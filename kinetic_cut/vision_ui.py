"""First-use consent and background analysis for face/person effects."""
import copy,threading,time
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QMessageBox,QProgressDialog
from . import vision_component as component
from .vision_effects import NAMES,FACE_NAMES,POSE_NAMES,MESH_NAMES,valid

def _valid_for_names(info,media,item,names):
    return valid(info,media,item,any(name in POSE_NAMES for name in names),any(name in MESH_NAMES for name in names))

def reanalyse_pasted(window,targets,context='pasted'):
    """Retain reusable analysis, otherwise analyse the actual pasted destinations."""
    from .vision_effects import active
    from .ui import Worker
    from .config import CACHE_DIR
    project=window.project
    pending=[copy.deepcopy(item) for item in targets if any(not _valid_for_names(e.get('analysis',{}),project.media_by_id(item.media_id),item,[e['name']]) for e in active(item))]
    if not pending:return
    if getattr(window,'_vision_busy',False):
        window.statusBar().showMessage(f'{context.title()} effects need analysis. Wait for the current analysis, then use Re-analyse in Effects.',8000); return
    root=component.component_root()
    if not component.ready(root) and QMessageBox.question(window,f'Enable {context} face/background effects',f'Download the optional local vision component to analyse the {context} effects? This uses the same local component as adding a face/background effect.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:
        window.statusBar().showMessage(f'Effects {context}; use Re-analyse in Effects to enable them on these clips.',8000); return
    assets={i.media_id:copy.deepcopy(project.media_by_id(i.media_id)) for i in pending}
    fps=project.settings.fps; ffmpeg=window.settings.get('ffmpeg','ffmpeg')
    cancel=threading.Event(); window._vision_busy=True; window._vision_cancel=cancel
    dialog=QProgressDialog(f'Analysing {context} effects…','Cancel',0,100,window); dialog.setWindowTitle('Relink Effects' if context=='relinked' else 'Paste Effects'); dialog.setMinimumDuration(0); dialog.setAutoClose(False); dialog.setAutoReset(False); dialog.show(); dialog.canceled.connect(cancel.set)
    def work():
        component.install(lambda v:worker.signals.progress.emit(v),cancel,root)
        results=[]
        for index,item in enumerate(pending):
            if cancel.is_set():raise RuntimeError('Analysis cancelled')
            media=assets[item.media_id]
            info=next((info for _,info in results if _valid_for_names(info,media,item,[e['name'] for e in active(item)])),None)
            if info is None:
                info=component.analyse(root,media,item,fps,CACHE_DIR/'vision-analysis'/str(time.time_ns()),ffmpeg,lambda v:worker.signals.progress.emit(((index+v[0]/100)*100/len(pending),f'Clip {index+1}/{len(pending)} · '+v[1])),cancel)
            results.append((item,info))
        return results
    def finish():
        window._vision_busy=False; window._vision_cancel=None
        if not window.transport.closed:dialog.close()
    def done(results):
        finish()
        if window.transport.closed or window.project is not project:return
        count=0
        for snapshot,info in results:
            item=project.item_by_id(snapshot.id)
            if not item or item.effects!=snapshot.effects or (context!='relinked' and project.track_states.get(item.track,{}).get('locked')) or not _valid_for_names(info,project.media_by_id(item.media_id),item,[e['name'] for e in active(item)]):continue
            for effect in active(item):effect['analysis']=copy.deepcopy(info)
            count+=1
        if count:window.model_changed()
        window.statusBar().showMessage(f'{context.title()} effect analysis ready for {count}/{len(pending)} clips. Review playback; undetected subjects remain unfiltered.',8000)
    def failed(detail):
        finish()
        if not window.transport.closed:window.statusBar().showMessage(f'{context.title()} effects still need Re-analyse: '+('cancelled' if cancel.is_set() else detail[-350:]),10000)
    def update(value):
        if not window.transport.closed:dialog.setValue(round(value[0])); dialog.setLabelText(value[1])
    worker=Worker(work); worker.signals.progress.connect(update); worker.signals.result.connect(done); worker.signals.error.connect(failed); window.start_worker(worker)

def begin(window,name=None,reanalyse=False):
    from .ui import Worker
    from .config import CACHE_DIR
    item=window.project.item_by_id(window.timeline.selected_id)
    if not name:
        effect=window.inspector.effect(); name=effect.get('name') if effect else None
    if name not in NAMES or not item or item.role in {'title','background'} or item.track not in window.project.video_tracks:return
    if window.project.track_states.get(item.track,{}).get('locked'):return
    if getattr(window,'_vision_busy',False):QMessageBox.information(window,'Analysis in progress','Wait for the current face/background analysis or cancel it first.'); return
    project=window.project; media=project.media_by_id(item.media_id); existing_effect=window.inspector.effect() if reanalyse else None
    if not media or media.kind not in {'image','video'}:return
    require_extra=name in POSE_NAMES|MESH_NAMES or any(e.get('name') in POSE_NAMES|MESH_NAMES for e in item.effects)
    cached=next((e['analysis'] for e in item.effects if e.get('name') in NAMES and _valid_for_names(e.get('analysis',{}),media,item,[name] if require_extra else [])),None)
    def commit(info):
        if window.transport.closed:return
        current=project.item_by_id(item.id)
        if reanalyse and current and not any(e is existing_effect for e in current.effects):return
        if window.project is not project or not current or window.current_page!=0 or project.track_states.get(current.track,{}).get('locked') or not _valid_for_names(info,project.media_by_id(current.media_id),current,[name] if require_extra else []):
            window.statusBar().showMessage('Analysis saved, but the selected source/crop changed. Apply the effect again.',6000); return
        detected=info['person_frames'] if name=='Remove Person Background' else info['face_frames']
        if not detected:
            QMessageBox.information(window,'Person not detected' if name=='Remove Person Background' else 'Face not detected','No reliable '+('person' if name=='Remove Person Background' else 'face')+' was detected in this cropped clip. No effect was applied. Try adjusting the crop so the subject is visible.'); return
        if name=='Custom Face':
            from .custom_face_dialog import CustomFaceDialog
            existing=next((e for e in current.effects if e.get('name')=='Custom Face'),None)
            dialog=CustomFaceDialog(window,media,current,info,existing)
            if dialog.exec()!=QDialog.Accepted:
                window.statusBar().showMessage('Custom Face cancelled · clip unchanged',5000)
                return
            target=project.item_by_id(item.id)
            if window.project is not project or target is not current or project.track_states.get(current.track,{}).get('locked') or not _valid_for_names(info,project.media_by_id(current.media_id),current,[name]):
                QMessageBox.warning(window,'Clip changed','The clip changed while Custom Face was open. No changes were applied.'); return
            for effect in current.effects:
                if effect.get('name') in NAMES:effect['analysis']=copy.deepcopy(info)
            if existing:existing.update(dialog.result_effect())
            else:current.effects.append(dialog.result_effect())
            window.model_changed(); window.select_item(current.id); window.inspector.tabs.setCurrentIndex(2)
            index=next(n for n,e in enumerate(current.effects) if e['name']=='Custom Face')
            window.inspector.effect_picker.setCurrentIndex(index)
            window.statusBar().showMessage(f'Custom Face applied · {detected}/{info["frames"]} frames tracked · Undo available',7000)
            return
        for effect in current.effects:
            if effect.get('name') in NAMES:effect['analysis']=copy.deepcopy(info)
        effect=next((e for e in current.effects if e.get('name')==name),None)
        if effect:effect.update(enabled=True,analysis=copy.deepcopy(info))
        else:current.effects.append(dict(name=name,enabled=True,analysis=copy.deepcopy(info)))
        window.model_changed(); window.select_item(current.id); window.inspector.tabs.setCurrentIndex(2)
        index=next(n for n,e in enumerate(current.effects) if e['name']==name); window.inspector.effect_picker.setCurrentIndex(index)
        window.statusBar().showMessage(f'{name} applied · detection in {detected}/{info["frames"]} frames · Undo available',7000)
        if name in FACE_NAMES and detected<info['frames']*.9:QMessageBox.information(window,'Face tracking completed',f'Face detected in {detected} of {info["frames"]} analysed frames. The face filter disappears when tracking is lost, so no stale distortion remains on the image. Review playback before exporting.')
    if cached and not reanalyse:commit(cached); return
    root=component.component_root()
    if not component.ready(root):
        message=('These effects need an optional local face/background component.\n\nEstimated download: 100–200 MB; installation: about 350 MB (measured 346 MB). Allow 1 GB free for setup. Downloads come from Python.org, PyPI and Google. Video processing runs locally; the component does not load during normal editor startup.\n\nAnalysis follows the current crop through the clip. Changing the crop requires Re-analyse. Lossless export caches can use additional disk space. Hair edges and fast movement may need review.\n\nDownload and enable these effects?')
        from .component_ui import offer
        if not offer(window,'vision'):return
    snapshot=copy.deepcopy(item); asset=copy.deepcopy(media); fps=project.settings.fps; ffmpeg=window.settings.get('ffmpeg','ffmpeg'); destination=CACHE_DIR/'vision-analysis'/str(time.time_ns())
    cancel=threading.Event(); window._vision_busy=True; window._vision_cancel=cancel
    dialog=QProgressDialog('Preparing cropped clip analysis…','Cancel',0,100,window); dialog.setWindowTitle(name); dialog.setWindowModality(Qt.NonModal); dialog.setMinimumDuration(0); dialog.setAutoClose(False); dialog.setAutoReset(False); dialog.resize(510,150); dialog.show(); dialog.canceled.connect(cancel.set)
    def work():
        progress=lambda value:worker.signals.progress.emit(value)
        component.install(progress,cancel,root)
        return component.analyse(root,asset,snapshot,fps,destination,ffmpeg,progress,cancel)
    def update(value):
        if not window.transport.closed:dialog.setValue(round(value[0])); dialog.setLabelText(value[1])
    def finish():
        window._vision_busy=False; window._vision_cancel=None
        if not window.transport.closed:dialog.close()
    def done(info):finish(); commit(info)
    def failed(detail):
        cancelled=cancel.is_set(); finish()
        if window.transport.closed:return
        if cancelled:window.statusBar().showMessage('Analysis cancelled · timeline unchanged',5000)
        else:QMessageBox.warning(window,'Analysis could not finish',detail[-2000:]+'\n\nThe timeline and original media were not changed.')
    worker=Worker(work); worker.signals.progress.connect(update); worker.signals.result.connect(done); worker.signals.error.connect(failed); window.start_worker(worker)


def customize(window):
    """Reopen saved Custom Face values without changing the clip on Cancel."""
    from .custom_face_dialog import CustomFaceDialog
    item=window.project.item_by_id(window.timeline.selected_id)
    effect=window.inspector.effect() if item else None
    if not item or not effect or effect.get('name')!='Custom Face':return
    media=window.project.media_by_id(item.media_id)
    if not media or not _valid_for_names(effect.get('analysis',{}),media,item,['Custom Face']):
        QMessageBox.information(window,'Analysis needed','The face mesh is missing or the source/crop changed. Click Re-analyse current crop first.'); return
    original=copy.deepcopy(effect)
    dialog=CustomFaceDialog(window,media,item,effect['analysis'],effect)
    if dialog.exec()!=QDialog.Accepted:return
    current=window.project.item_by_id(item.id)
    if current is not item or window.project.track_states.get(item.track,{}).get('locked') or effect!=original:
        QMessageBox.warning(window,'Clip changed','The clip changed while Custom Face was open. No changes were applied.'); return
    effect.update(dialog.result_effect())
    window.model_changed(); window.select_item(item.id); window.inspector.tabs.setCurrentIndex(2)
