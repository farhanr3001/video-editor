import os,sys,time,json,faulthandler
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/'build/export-queue-stall-check'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(OUT/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
from kinetic_cut.process import install_desktop_process_policy
install_desktop_process_policy()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QEventLoop
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project
app=QApplication([]); app.setQuitOnLastWindowClosed(False); faulthandler.enable(); faulthandler.dump_traceback_later(120,repeat=True)
w=MainWindow(); w.resize(1280,850); w.show(); project=Project.load(ROOT/'TestEdit.kcut')
for media in project.media:media.thumbnail=''
w.set_project(project); w.autosave_timer.stop()
from kinetic_cut.workspace import set_page
set_page(w,1); d=w.delivery; d.location.setText(str(OUT)); d.name.setText('caption-'+str(time.time_ns())); d.burn.setChecked(True); d.hardware.setCurrentText('Auto'); d.add_job(); start=time.monotonic(); d.render_all()
loop=QEventLoop(); timer=QTimer(); timer.setInterval(1000)
def check():
    print(round(time.monotonic()-start,1),d.progress.value(),d.jobs[0]['state'],d.status.text(),flush=True)
    if d.jobs[0]['state'] in ('Complete','Failed') or time.monotonic()-start>180:loop.quit()
timer.timeout.connect(check); timer.start(); loop.exec(); timer.stop()
report={'seconds':time.monotonic()-start,'state':d.jobs[0]['state'],'error':d.jobs[0].get('error'),'progress':d.progress.value()}
(OUT/'report.json').write_text(json.dumps(report,indent=2)); print(report,flush=True)
w.close(); cleanup=QEventLoop(); QTimer.singleShot(100,cleanup.quit); cleanup.exec()
sys.exit(0 if report['state']=='Complete' else 1)
