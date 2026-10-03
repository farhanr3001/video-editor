"""Force collection after each UI test to expose delayed Qt wrapper lifetime bugs."""
import os,sys,gc,unittest,faulthandler
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"tests"))
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["KINETIC_CUT_HOME"]=str(ROOT/"build/qt-cleanup-home")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent
faulthandler.enable(); app=QApplication([]); app.setQuitOnLastWindowClosed(False)
class Result(unittest.TextTestResult):
    def stopTest(self,test):
        super().stopTest(test); print("COLLECT",test.id(),flush=True); gc.collect(); print("COLLECTED",flush=True)
suite=unittest.TestSuite()
for pattern in ["test_batch_edit_safety.py","test_bins_timeline_caption.py"]:suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/"tests"),pattern))
result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
app.clipboard().clear(); app.sendPostedEvents(None,QEvent.DeferredDelete); gc.collect()
sys.exit(0 if result.wasSuccessful() else 1)
