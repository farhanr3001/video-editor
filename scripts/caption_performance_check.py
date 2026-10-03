"""Isolated typing benchmark; never opens/saves a user project."""
import os,sys,time,json,cProfile,pstats,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(ROOT/'build/caption-performance-home')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,Caption
app=QApplication([]); w=MainWindow(); w.show(); w.autosave_timer.stop()
p=Project(captions=[Caption(str(i),i*.5,i*.5+.4,'Caption '+str(i)) for i in range(1000)])
w.set_project(p); w.select_caption('0'); app.processEvents(); editor=w.inspector.caption_text
profile=cProfile.Profile(); times=[]; profile.enable()
for character in 'quick typing check':
    started=time.perf_counter(); editor.insertPlainText(character); app.processEvents(); times.append((time.perf_counter()-started)*1000)
profile.disable(); stream=io.StringIO(); pstats.Stats(profile,stream=stream).sort_stats('cumulative').print_stats(15)
out=ROOT/'build'/(sys.argv[1] if len(sys.argv)>1 else 'caption-performance.json')
out.write_text(json.dumps(dict(mean_ms=sum(times)/len(times),max_ms=max(times),characters=len(times),profile=stream.getvalue()),indent=2))
print(out.read_text()); w.close(); QThreadPool.globalInstance().waitForDone(10000); app.processEvents()
