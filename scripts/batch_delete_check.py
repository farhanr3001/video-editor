"""Real-decoder batch-edit watchdog regression, with isolated application data."""
import os,sys,time,copy,faulthandler,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ["QT_LOGGING_RULES"]="qt.multimedia.*=false"
os.environ["KINETIC_CUT_HOME"]=str(ROOT/"build/batch-delete-check/home")
faulthandler.enable(); faulthandler.dump_traceback_later(35,exit=True)
from PySide6.QtCore import Qt,QThreadPool,QEvent,QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem,Caption,uid
from PySide6.QtMultimedia import QMediaPlayer
from kinetic_cut.media import probe

def wait(milliseconds=250):
    # A real Qt event loop releases Python's GIL, as QApplication.exec does.
    # QTest.qWait/processEvents hold it across native deferred destruction and
    # would themselves deadlock independent multimedia callbacks in this test.
    loop=QEventLoop(); QTimer.singleShot(milliseconds,loop.quit); loop.exec()

def main():
    app=QApplication([]); app.setQuitOnLastWindowClosed(False); w=MainWindow(); w.resize(1680,1000); w.show(); wait()
    media=probe(ROOT/"xqc_royalty.mp4"); p=Project(media=[media])
    for n in range(3):p.add_track("video"); p.add_track("audio")
    for n in range(4):
        group=uid()
        p.timeline.extend([TimelineItem("v"+str(n),media.id,p.video_tracks[n],0,8,n*.2,group_id=group),TimelineItem("a"+str(n),media.id,p.audio_tracks[n],0,8,n*.2,group_id=group)])
    p.captions=[Caption("caption",1,4,"Batch deletion check")]
    w.set_project(p); w.seek(2); wait(800)
    if "--legacy-teardown" in sys.argv:
        def legacy_retire(key):
            player,output,sink=w.transport.decoders[key]
            player.stop(); player.deleteLater(); w.transport.decoders.pop(key)
            w.preview.frames.pop(key,None)
        w.transport.retire_decoder=legacy_retire
    timings={}
    for playing in (False,True):
        for key in (Qt.Key_Delete,Qt.Key_Backspace):
            w.seek(2)
            if playing:w.transport.play()
            w.timeline.select_ids({i.id for i in w.project.timeline},"v0"); w.timeline.setFocus(); wait(100)
            print("Delete",playing,key,"decoders",len(w.transport.decoders),flush=True)
            faulthandler.dump_traceback_later(15,exit=True)
            start=time.monotonic(); QTest.keyClick(w.timeline,key)
            assert not w.project.timeline,"Keyboard shortcut did not remove every media clip"
            timings[f"{playing}-{key}"]=round(time.monotonic()-start,3)
            print("Deleted in",time.monotonic()-start,flush=True)
            faulthandler.dump_traceback_later(15,exit=True)
            wait(); w.undo(); wait(); assert len(w.project.timeline)==8
            print("Undo completed",flush=True)
            faulthandler.dump_traceback_later(15,exit=True)
            w.redo(); wait(); assert not w.project.timeline
            faulthandler.dump_traceback_later(15,exit=True)
            w.undo(); wait(); w.transport.pause()
            assert len(w.transport.findChildren(QMediaPlayer))==len(w.transport.decoders),"Retired players were leaked"
    # Exercise the same decoder retirement through cut/paste, overwrite, seek,
    # track removal and visibility changes, with a live playback clock.
    for action in ("cut","overwrite","track","hide","seek"):
        faulthandler.dump_traceback_later(15,exit=True)
        w.seek(2); w.transport.play(); wait(100)
        w.timeline.select_ids({i.id for i in w.project.timeline},"v0")
        print("Batch action",action,flush=True)
        if action=="cut":
            w.timeline_clipboard("cut",True); assert not w.project.timeline; wait()
            w.seek(0); w.timeline_clipboard("paste",True); assert len(w.project.timeline)==8
        elif action=="overwrite":
            w.timeline_clipboard("copy",True); w.seek(0); w.timeline_clipboard("paste",True); assert len(w.project.timeline)==8
        elif action=="track":
            w.project.delete_track(w.project.video_tracks[-1]); w.model_changed(); wait(); w.undo()
        elif action=="hide":
            for state in w.project.track_states.values():state["visible"]=False
            w.model_changed(); wait(); assert not w.transport.decoders; w.undo()
        else:
            for moment in (10,2,12,3):w.seek(moment); wait(100)
        wait(); w.transport.pause()
        assert len(w.transport.findChildren(QMediaPlayer))==len(w.transport.decoders)
    # One mixed selection removes titles/captions/media atomically and undoable.
    w.timeline.select_ids({i.id for i in w.project.timeline})
    w.timeline.selected_caption_ids={c.id for c in w.project.captions}; w.timeline.selected_caption="caption"
    w.delete_selected(); wait(); assert not w.project.timeline and not w.project.captions
    w.undo(); wait(); assert len(w.project.timeline)==8 and w.project.captions
    # Offscreen Qt has an in-process clipboard, unlike Windows' system clipboard.
    # Release its test QMimeData while QApplication is still alive.
    app.clipboard().clear()
    w.close(); QThreadPool.globalInstance().waitForDone(10000); wait()
    for widget in app.topLevelWidgets():widget.close(); widget.deleteLater()
    app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()
    output=ROOT/"build/batch-delete-check"; output.mkdir(parents=True,exist_ok=True)
    (output/"report.json").write_text(json.dumps(dict(passed=True,delete_seconds=timings,batch_actions=["cut","paste","overwrite","track removal","hide","seek","mixed caption deletion","undo","redo"],retired_players_leaked=0),indent=2))
    faulthandler.cancel_dump_traceback_later()
    from kinetic_cut.icons import lucide_icon
    lucide_icon.cache_clear()
    import gc
    del w; gc.collect()
    print("PASS batch deletion",timings,flush=True)
    return 0

if __name__=="__main__":sys.exit(main())
