"""Audit every published frame near Tony's first two cuts; never save the project."""
import os,sys,json,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
label=sys.argv[1] if len(sys.argv)>1 else 'check'
out=ROOT/'build'/('tony-preview-'+label); out.mkdir(parents=True,exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(out/'home')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop,QTimer
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project
app=QApplication([]); w=MainWindow(); w.autosave_timer.stop(); w.show()
path=ROOT/'tony.kcut'; before=hashlib.sha256(path.read_bytes()).hexdigest(); project=Project.load(path)
records=[]; original=w.transport.frame
def frame(key,image):
    decoder=w.transport.decoders.get(key)
    if decoder and decoder[2]:
        stamp=decoder[2]._frame_stamp
        items=[i for i in project.timeline if i.track in project.video_tracks and i.media_id==key[0] and round(i.in_point-i.start*i.speed,4)==key[1]]
        if stamp and items:
            lower=min(i.in_point for i in items)
            records.append(dict(t=w.transport.position,source=stamp[0]/1e6,lower=lower,warm=key in w.transport.warm_keys,bad=stamp[0]/1e6<lower-.08))
    original(key,image)
w.transport.frame=frame
def wait(ms):
    loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
try:
    w.set_project(project); w.transport.seek(6.8); wait(800); w.transport.play()
    deadline=time.monotonic()+15
    while w.transport.position<11.3 and time.monotonic()<deadline:wait(10)
    w.transport.pause(); wait(100)
    result=dict(passed=bool(records) and not any(r['bad'] for r in records),published=len(records),bad=[r for r in records if r['bad']],reached=w.transport.position,project_unchanged=before==hashlib.sha256(path.read_bytes()).hexdigest())
    (out/'report.json').write_text(json.dumps(result,indent=2)); (out/'frames.json').write_text(json.dumps(records,indent=2)); print(json.dumps(result),flush=True)
finally:w.close(); app.processEvents()
