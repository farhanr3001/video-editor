"""Render-queue integration test with independent timeline cuts, blur, audio FX."""
import os,sys,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"sept-render-home")); os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.media import probe
from kinetic_cut.model import Project,Caption,uid,make_vertical_group,Crop
from kinetic_cut.exporter import build_command,PRESETS

def main():
    app=QApplication([]); w=MainWindow(); media=probe(ROOT/"xqc_royalty.mp4")
    p=Project(name="September render test",media=[media],timeline=make_vertical_group(media,1,4,2))
    main=next(i for i in p.timeline if i.role=="content"); face=next(i for i in p.timeline if i.role=="facecam")
    main.crop=Crop(.401,.098,.267,.841); face.crop=Crop(0,.704,.231,.259)
    main.effects=[dict(name="Gaussian Blur",horizontal=2.,vertical=3.,enabled=True,blend=65)]
    source=next(i for i in p.timeline if i.role=="source_audio"); source.pan=.3; source.pitch_semitones=2; source.fade_in=.2; source.fade_out=.3; source.gain_db=-5
    p.captions=[Caption(uid(),1,2.8,"Caption track styling")]; p.subtitle_style.size=50; p.subtitle_style.color="#56f7ee"; p.subtitle_style.font_face="Bold"; p.subtitle_style.position_y=.6
    w.set_project(p); d=w.delivery; d.location.setText(str(ROOT/"build")); d.name.setText("sept-render-"+uid()); d.resolution.setCurrentIndex(1); d.fps.setCurrentText("30"); d.add_job(); d.render_all()
    deadline=time.monotonic()+45
    while d.running and time.monotonic()<deadline:QTest.qWait(50)
    assert not d.running and d.jobs[0]["state"]=="Complete",d.status.text()
    output=d.jobs[0]["output"]
    data=json.loads(subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",output],capture_output=True,text=True,check=True).stdout)
    video=next(s for s in data["streams"] if s["codec_type"]=="video"); assert (video["width"],video["height"])==(720,1280)
    assert 2.9<float(data["format"]["duration"])<3.1,data["format"]
    assert any(s["codec_type"]=="audio" for s in data["streams"])
    w.close(); w.thread_pool.waitForDone(10000); print("PASS queue render: gap+layers+blur+caption track style+pan/pitch/fades;",output)

if __name__=="__main__":main()
