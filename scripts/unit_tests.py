"""Run the suite with deterministic Qt cleanup before Python finalization."""
import os,sys,unittest,gc,faulthandler
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build/unit-test-home"))
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import QEvent,QThreadPool
import shiboken6

faulthandler.enable()
if os.environ.get('KINETIC_TEST_WATCHDOG'):faulthandler.dump_traceback_later(20,repeat=True)
app=QApplication([]); app.setQuitOnLastWindowClosed(False)
app.setProperty('kineticTestDiscardUnsaved',True)  # Fixture teardown; close-guard tests explicitly clear it.
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT/"tests"),pattern=sys.argv[1] if len(sys.argv)>1 else "test*.py"))
workers_done=QThreadPool.globalInstance().waitForDone(10000)
app.processEvents()
for widget in app.topLevelWidgets():
    # Earlier closes/deferred deletions may have retired a native popup wrapper
    # while Qt's top-level snapshot was being enumerated.
    if shiboken6.isValid(widget) and isinstance(widget,QWidget):
        widget.close()
        if shiboken6.isValid(widget):widget.deleteLater()
app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()
from kinetic_cut.icons import lucide_icon
lucide_icon.cache_clear(); gc.collect()
shiboken6.delete(app)
if not workers_done:print("ERROR: background workers did not finish",file=sys.stderr)
sys.exit(0 if result.wasSuccessful() and workers_done else 1)
