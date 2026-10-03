"""Record only this test editor's startup subprocesses, in an isolated profile."""
import os,sys,json,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/'build/startup-process-check'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(OUT/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
from kinetic_cut.process import install_desktop_process_policy
install_desktop_process_policy(); events=[]; started=time.monotonic()
def audit(event,args):
    if event=='subprocess.Popen':events.append(dict(seconds=time.monotonic()-started,executable=str(args[0]),command=str(args[1]),stack=traceback.format_stack(limit=8)))
sys.addaudithook(audit)
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QEventLoop
app=QApplication([])
from kinetic_cut.ui import MainWindow
w=MainWindow(); w.show(); loop=QEventLoop(); QTimer.singleShot(1200,loop.quit); loop.exec(); w.close()
(OUT/'report.json').write_text(json.dumps(dict(seconds=time.monotonic()-started,events=events),indent=2)); print(json.dumps(events,indent=2),flush=True)
