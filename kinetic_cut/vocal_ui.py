"""Simple first-use download -> save -> optional replacement workflow."""
import copy,threading
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog,QMessageBox,QProgressDialog
from . import vocal_component as component


def begin(window):
    from .ui import Worker
    from .media import probe
    from .media_insert import source_key
    item=window.project.item_by_id(window.timeline.selected_id)
    if getattr(window,"_vocal_busy",False):QMessageBox.information(window,"Vocal Only","A Vocal Only job is already running."); return
    if not item or item.track not in window.project.audio_tracks or window.project.track_states.get(item.track,{}).get("locked"):
        QMessageBox.information(window,"Vocal Only","Drop Vocal Only onto an unlocked audio clip."); return
    media=window.project.media_by_id(item.media_id)
    if not media or not media.has_audio:QMessageBox.information(window,"Vocal Only","The selected clip has no audio stream."); return
    root=component.component_root(); needs_download=not component.ready(root)
    if needs_download:
        text=("Vocal Only needs an optional local CPU processing component.\n\n"
              "Estimated download: 250–450 MB. Installed size: approximately 1.2 GB; allow 2 GB free during setup.\n\n"
              "Downloads come from Python.org, PyPI, PyTorch and Meta's model host. Audio stays on your computer. Nothing loads at normal app startup.\n\n"
              "Download and enable Vocal Only now?")
        from .component_ui import offer
        if not offer(window,'vocals'):return
        needs_download=False
    suggested=str(Path(media.path).with_name(Path(media.path).stem+"-vocals.mp3"))
    output,_=QFileDialog.getSaveFileName(window,"Save vocal-only audio",suggested,"MP3 audio (*.mp3)")
    if not output:return
    if Path(output).suffix.lower()!=".mp3":output+=".mp3"
    if source_key(output)==source_key(media.path):QMessageBox.warning(window,"Vocal Only","Choose a different filename; the original media cannot be overwritten."); return
    project=window.project; snapshot=copy.deepcopy(item); settings=copy.deepcopy(window.settings)
    progress=QProgressDialog("Preparing Vocal Only…","Cancel",0,100,window); progress.setWindowTitle("Vocal Only"); progress.setWindowModality(Qt.NonModal); progress.setMinimumDuration(0); progress.setAutoClose(False); progress.setAutoReset(False); progress.resize(480,150); progress.show()
    cancel=threading.Event(); window._vocal_busy=True; window._vocal_cancel=cancel
    def cancelling():
        cancel.set(); window.statusBar().showMessage("Cancelling Vocal Only; cleaning up temporary files…")
    progress.canceled.connect(cancelling)
    def work():
        report=lambda value:worker.signals.progress.emit(value)
        if needs_download:component.install(report,cancel,root)
        component.process_audio(root,media.path,snapshot.in_point,snapshot.source_duration,output,settings.get("ffmpeg","ffmpeg"),report,cancel)
        return probe(output,settings.get("ffprobe","ffprobe"),settings.get("ffmpeg","ffmpeg"))
    worker=Worker(work)
    def updated(value):
        if window.transport.closed:return
        percent,text=value; progress.setValue(max(0,min(100,int(percent)))); progress.setLabelText(text); window.statusBar().showMessage(text.splitlines()[0])
    worker.signals.progress.connect(updated)
    def finish():
        window._vocal_busy=False; window._vocal_cancel=None
        if not window.transport.closed:progress.close()
    def done(asset):
        finish()
        if window.transport.closed:return
        valid=window.project is project and project.item_by_id(snapshot.id)==snapshot and window.current_page==0 and not project.track_states.get(snapshot.track,{}).get("locked")
        if not valid:
            QMessageBox.information(window,"Vocal Only saved",f"Saved to:\n{output}\n\nThe original clip changed or is locked, so it was not replaced. Import the MP3 when you are ready."); return
        answer=QMessageBox.question(window,"Vocal Only ready",f"Saved to:\n{output}\n\nReplace this audio clip in the timeline with the vocal-only MP3?\n\nVideo, clip timing and existing audio settings will stay unchanged. You can Undo the replacement.",QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)
        if answer!=QMessageBox.Yes:return
        if window.project is not project or project.item_by_id(snapshot.id)!=snapshot or project.track_states.get(snapshot.track,{}).get("locked"):return
        current=project.item_by_id(snapshot.id)
        existing=next((m for m in project.media if source_key(m.path)==source_key(asset.path)),None)
        if existing:asset=existing
        else:project.media.append(asset)
        current.media_id=asset.id; current.in_point=0
        window.model_changed(); window.refresh_media(); window.seek(project.playhead)
        window.statusBar().showMessage("Audio replaced with Vocal Only · linked video unchanged · Undo available",6000)
    def failed(detail):
        was_cancelled=cancel.is_set(); finish()
        if window.transport.closed:return
        if was_cancelled:window.statusBar().showMessage("Vocal Only cancelled · timeline unchanged",5000)
        else:QMessageBox.warning(window,"Vocal Only could not finish",detail[-2200:]+"\n\nYour timeline and original media were not changed. You can retry Vocal Only.")
    worker.signals.result.connect(done); worker.signals.error.connect(failed); window.start_worker(worker)
