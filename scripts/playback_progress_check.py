"""Verify changing preview pixels, not merely a moving timeline clock."""
import os,sys,json,faulthandler,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen"); os.environ["QT_LOGGING_RULES"]="qt.multimedia.*=false"
os.environ["KINETIC_CUT_HOME"]=str(ROOT/"build/playback-progress-check/home")
faulthandler.enable(); faulthandler.dump_traceback_later(30,exit=True)
from PySide6.QtCore import QTimer,QEventLoop,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem,Transform
from kinetic_cut.media import probe

def wait(ms):
    loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()

def main():
    app=QApplication([]); app.setQuitOnLastWindowClosed(False); w=MainWindow(); w.resize(1280,800); w.show()
    media=probe(ROOT/"xqc_royalty.mp4"); p=Project(media=[media]); p.add_track("video"); p.add_track("video")
    p.timeline=[TimelineItem("lower",media.id,"video_1",0,4),TimelineItem("upper",media.id,"video_3",0,4,3,transform=Transform(.5,.25,.4)),TimelineItem("audio",media.id,"audio_1",0,4)]
    w.set_project(p); w.seek(.2); wait(300); w.transport.play()
    samples=[]
    try:
        for _ in range(6):
            wait(150); samples.append({"clock":w.project.playhead,"frames":{i:hashlib.sha1(w.preview.frames[key].constBits()).hexdigest() for i,key in w.preview.active_frames.items() if key in w.preview.frames}})
        assert w.transport.playing and samples[-1]["clock"]>samples[0]["clock"]+.5
        for lane in ("lower","upper"):
            count=len({sample["frames"].get(lane) for sample in samples})
            assert count>=4,f"{lane}: only {count} preview frames while clock advances: {samples}"
        assert not any(i.track=="video_2" for i in w.project.timeline)
        p.track_states["video_3"]["visible"]=False; w.model_changed(); wait(160)
        assert set(w.preview.active_frames)=={"lower"}
        before=hashlib.sha1(w.preview.frames[w.preview.active_frames["lower"]].constBits()).hexdigest(); wait(220)
        assert before!=hashlib.sha1(w.preview.frames[w.preview.active_frames["lower"]].constBits()).hexdigest()
        p.track_states["video_1"]["visible"]=False; w.model_changed(); wait(80); assert not w.preview.active_frames and not w.preview._visible_items()
        p.track_states["video_3"]["visible"]=True; w.model_changed(); wait(160); assert set(w.preview.active_frames)=={"upper"}
        # Crossing an edit boundary must replace/reuse decoders without freezing.
        p.track_states["video_1"]["visible"]=True; p.split("lower",2.5); w.model_changed(); w.seek(2.35); wait(380)
        assert w.transport.playing and w.project.playhead>2.5
        w.transport.loop=True; w.seek(3.8); wait(450); assert w.transport.playing and w.project.playhead<1
        w.transport.pause(); w.seek(6); wait(100); assert not w.preview.active_frames and not w.preview._visible_items()
        report={"passed":True,"empty_middle_layer":True,"hidden_layers":True,"cut_boundary":True,"loop":True,"beyond_end_black":True,"pixel_hash_samples":samples}
    finally:
        w.close(); QThreadPool.globalInstance().waitForDone(5000); wait(150); app.clipboard().clear()
        for widget in app.topLevelWidgets():widget.close(); widget.deleteLater()
        app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()
        from kinetic_cut.icons import lucide_icon
        lucide_icon.cache_clear(); faulthandler.cancel_dump_traceback_later()
    output=ROOT/"build/playback-progress-check"; output.mkdir(parents=True,exist_ok=True); (output/"report.json").write_text(json.dumps(report,indent=2))
    print("PASS: changing frames on both video layers with an empty middle layer",flush=True)

if __name__=="__main__":main()
