"""Read-only UI interaction profile, separate home and no project writes."""
import os,sys,time,json,cProfile,pstats
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
out=root/'build'/sys.argv[1]; out.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(out/'home')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QTimer,QEventLoop,QThreadPool
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project
app=QApplication([]); w=MainWindow(); w.resize(1480,900); w.show(); w.autosave_timer.stop()
p=Project.load(root/'xqc kai fashion show.kcut'); w.set_project(p)
def wait(ms):
    loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
wait(2500); t=w.timeline; t.pixels_per_second=5; t._range(); app.processEvents()
item=next(i for i in p.timeline if i.track=='video_1' and i.duration>4)
x=round(t.x_for_time(item.start+item.duration/2)); y=round(t.track_rect(item.track).center().y())
report={}
def pointer(n,buttons=Qt.NoButton):
    pos=QPointF(x+10+n%80,y)
    app.sendEvent(t.viewport(),QMouseEvent(QEvent.MouseMove,pos,QPointF(t.viewport().mapToGlobal(pos.toPoint())),Qt.NoButton,buttons,Qt.NoModifier))
def measure(name,action,count=150):
    prof=cProfile.Profile(); values=[]; prof.enable()
    for n in range(count):
        started=time.perf_counter(); action(n); app.processEvents(); values.append((time.perf_counter()-started)*1000)
    prof.disable(); values.sort()
    report[name]={'mean_ms':sum(values)/len(values),'p95_ms':values[int(len(values)*.95)],'max_ms':max(values)}
    with (out/(name+'.txt')).open('w') as f:pstats.Stats(prof,stream=f).sort_stats('cumtime').print_stats(35)
measure('hover',pointer)
QTest.mousePress(t.viewport(),Qt.LeftButton,pos=QPoint(x,y))
report['drag_mode']=t.drag_mode
assert t.drag_mode=='move', (t.drag_mode,x,y,t.item_rect(item),t.section_rect(item.track))
measure('drag',lambda n:pointer(n,Qt.LeftButton))
QTest.keyClick(t.viewport(),Qt.Key_Escape); QTest.mouseRelease(t.viewport(),Qt.LeftButton,pos=QPoint(x,y))
measure('scrub',lambda n:w.transport.scrub(10+n%50*.12))
w.transport.finish_scrub(); wait(200)
measure('cut',lambda n:w.split_at(item.id,item.start+item.duration*.5),count=5)
(out/'report.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report))
w.close(); QThreadPool.globalInstance().waitForDone(15000); app.processEvents()
