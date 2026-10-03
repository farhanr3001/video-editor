"""Asynchronous, non-destructive audio editing actions (original files untouched)."""
import copy
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QDialogButtonBox,QDoubleSpinBox,QFormLayout,
    QMessageBox,QProgressDialog)
from .timeline_actions import aligned_linked_av,complement,keep_audio_ranges,merge_ranges


def run_action(window,cut_words=False,on_complete=None):
    from .ui import Worker
    project=window.project; audio=project.item_by_id(window.timeline.selected_id)
    title="Cut curse words" if cut_words else "Remove Silence"
    try:
        if not audio or audio.track not in project.audio_tracks:raise ValueError("Drop this action onto an audio clip in the timeline.")
        targets=[audio] if cut_words else aligned_linked_av(project,audio)
        if any(project.track_states.get(i.track,{}).get("locked") for i in targets):raise ValueError("Unlock the affected layers first.")
        media=project.media_by_id(audio.media_id)
        if not media or not media.has_audio:raise ValueError("That clip has no audio stream.")
    except ValueError as error:QMessageBox.information(window,title,str(error)); return
    threshold=-34.; minimum=.42; padding=.12
    if not cut_words:
        dialog=QDialog(window); dialog.setWindowTitle("Remove dead air — linked video and audio")
        form=QFormLayout(dialog); threshold_box=QDoubleSpinBox(); threshold_box.setRange(-60,-10); threshold_box.setValue(threshold); threshold_box.setSuffix(" dB")
        minimum_box=QDoubleSpinBox(); minimum_box.setRange(.1,3); minimum_box.setValue(minimum); minimum_box.setSuffix(" s")
        padding_box=QDoubleSpinBox(); padding_box.setRange(0,.6); padding_box.setValue(padding); padding_box.setSuffix(" s")
        form.addRow("Silence threshold",threshold_box); form.addRow("Minimum silence",minimum_box); form.addRow("Keep around speech",padding_box)
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Apply); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if not dialog.exec():return
        threshold=threshold_box.value(); minimum=minimum_box.value(); padding=padding_box.value()
    snapshots=copy.deepcopy(targets); original=copy.deepcopy(audio); settings=copy.deepcopy(window.settings)
    progress=QProgressDialog("Recognizing word timestamps…" if cut_words else "Listening for dead air…","Cancel",0,0,window)
    progress.setWindowTitle(title); progress.setWindowModality(Qt.WindowModal); progress.show()
    cancelled=[False]; progress.canceled.connect(lambda:cancelled.__setitem__(0,True))
    def work():
        ffmpeg=settings.get("ffmpeg","ffmpeg")
        if not cut_words:
            from .silence import detect
            ranges=detect(media.path,original.source_duration,threshold,minimum,padding,ffmpeg,original.in_point)
            return [(a/original.speed,b/original.speed) for a,b in ranges],0
        from .captions import transcribe
        from .profanity import contains_curse
        from .process import run
        with tempfile.TemporaryDirectory(prefix="kinetic-word-cuts-") as directory:
            wav=str(Path(directory)/"speech.wav")
            run([ffmpeg,"-hide_banner","-loglevel","error","-y","-ss",str(original.in_point),"-t",str(original.source_duration),"-i",media.path,"-vn","-ac","1","-ar","16000",wav],check=True,capture_output=True)
            words,_=transcribe(wav,settings,words_per_caption=1,hold_seconds=0,require_word_timestamps=True)
        curses=[word for word in words if contains_curse(word.text)]
        # Small guard padding catches consonants at approximate word boundaries.
        cuts=merge_ranges([(max(0,word.start-.035)/original.speed,min(original.source_duration,word.end+.045)/original.speed) for word in curses])
        return complement(original.duration,cuts),len(curses)
    worker=Worker(work)
    def ready(result):
        was_cancelled=cancelled[0]; progress.close()
        if was_cancelled:return
        if window.current_page!=0 or window.project is not project or any(project.item_by_id(i.id)!=i for i in snapshots):
            window.statusBar().showMessage("Audio result discarded because the clip changed.",5000); return
        keep,count=result
        if cut_words and not count:QMessageBox.information(window,title,"No matching curse words were detected. Review the audio: speech recognition can miss words."); return
        if not cut_words and not keep:QMessageBox.information(window,title,"The entire clip was detected as silent; nothing was changed."); return
        if cut_words and QMessageBox.question(window,title,f"Cut {count} detected curse word(s)? Gaps will remain on this audio layer; video and other clips stay in place. Review the result for recognition errors. You can Undo the whole action.")!=QMessageBox.Yes:return
        # A modal confirmation can process events: revalidate immediately before committing.
        if window.current_page!=0 or window.project is not project or any(project.item_by_id(i.id)!=i for i in snapshots):return
        try:ids=keep_audio_ranges(project,project.item_by_id(original.id),keep,pack=not cut_words)
        except ValueError as error:QMessageBox.information(window,title,str(error)); return
        if ids:window.timeline.select_ids(set(ids),ids[0])
        else:window.timeline.select_ids(set())
        window.model_changed(); window.seek(min(project.playhead,project.duration))
        window.statusBar().showMessage(title+" complete · original files unchanged · Undo available",6000)
        if on_complete:on_complete()
    def failed(detail):
        was_cancelled=cancelled[0]; progress.close()
        if not was_cancelled:QMessageBox.warning(window,title,detail[-1800:])
    worker.signals.result.connect(ready); worker.signals.error.connect(failed); window.start_worker(worker)
