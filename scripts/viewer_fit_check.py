"""Inspect width-fill on a read-only copy of the apartment project."""
import os,sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
out=ROOT/'build/viewer-fit-check'; out.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(out/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop,QTimer
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project
app=QApplication([]); w=MainWindow(); w.resize(1600,1000); w.show(); w.autosave_timer.stop()
path=ROOT/'Apartment Tour - xQc.kcut'; before=hashlib.sha256(path.read_bytes()).hexdigest()
try:
    w.set_project(Project.load(path)); w.seek(.7)
    loop=QEventLoop(); QTimer.singleShot(1500,loop.quit); loop.exec()
    cam=next(i for i in w.project.timeline if i.role=='facecam' and i.start<=.7<i.start+i.duration)
    xy=(cam.transform.x,cam.transform.y)
    w.select_item(cam.id); w.preview.grab().save(str(out/'before.png'))
    w.viewer_command('fit',cam.id)
    assert (cam.transform.x,cam.transform.y)==xy
    w.viewer_command('position_top',cam.id)
    frame=w.preview.composition_rect()
    rect=next(r for i,_,r in w.preview._visible_items() if i.id==cam.id)
    assert abs(rect.left()-frame.left())<.01 and abs(rect.right()-frame.right())<.01
    assert abs(rect.top()-frame.top())<.01
    w.preview.grab().save(str(out/'after.png'))
    result=dict(passed=True,width=rect.width(),output_width=frame.width(),position_preserved_by_fit=True,
                position_top_retained=True,viewer_tooltip=w.preview.toolTip(),project_unchanged=before==hashlib.sha256(path.read_bytes()).hexdigest())
    (out/'report.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result))
finally:w.close(); app.processEvents()
