"""Read-only fashion-show profiling; each run uses a separate application home."""
import os,sys,time,json,cProfile,pstats
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
out=root/'build'/sys.argv[1]; out.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(out/'home')
os.environ['QT_LOGGING_RULES']='qt.multimedia.ffmpeg.hwaccel=true'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QEventLoop,QThreadPool
from kinetic_cut.model import Project
from kinetic_cut.ui import MainWindow
app=QApplication([]); w=MainWindow(); w.resize(1480,900); w.show(); w.autosave_timer.stop()
p=Project.load(root/'xqc kai fashion show.kcut'); w.set_project(p)
def wait(ms):
    loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
wait(2000)
if '--optimized' in sys.argv:
    from kinetic_cut.media import generate_proxy
    used={i.media_id for i in p.timeline if i.track in p.video_tracks and i.start<20 and i.start+i.duration>10}
    for m in p.media:
        if m.id in used and m.kind=='video' and m.width>960:w.preview_quality.ready[m.id]=generate_proxy(m)
    from PySide6.QtCore import QSignalBlocker
    with QSignalBlocker(w.preview_quality):w.preview_quality.setCurrentIndex(1)
    w.preview_quality.apply()
w.seek(10); wait(700)
report={'duration':p.duration,'items':len(p.timeline),'captions':len(p.captions),'media':len(p.media)}
prof=cProfile.Profile(); prof.enable(); ticks=[]; previous=[time.perf_counter()]
timer=QTimer(); timer.setInterval(10)
def sample():
    now=time.perf_counter(); ticks.append((now-previous[0])*1000); previous[0]=now
timer.timeout.connect(sample); timer.start(); w.transport.play(); wait(10000); w.transport.pause(); timer.stop()
report['playback_tick_mean_ms']=sum(ticks)/len(ticks); report['playback_tick_max_ms']=max(ticks)
durations=[]
for i in range(150):
    at=10+(i%50)*.12; start=time.perf_counter(); w.transport.scrub(at); app.processEvents(); durations.append((time.perf_counter()-start)*1000)
w.transport.finish_scrub(); wait(500); prof.disable()
report['scrub_mean_ms']=sum(durations)/len(durations); report['scrub_max_ms']=max(durations)
report['decoder_count']=len(w.transport.decoders); report['final_playhead']=w.project.playhead
w.grab().save(str(out/'workspace.png'))
prof.dump_stats(str(out/'profile.pstats'))
with (out/'profile.txt').open('w') as f:pstats.Stats(prof,stream=f).sort_stats('cumtime').print_stats(55)
(out/'report.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report))
w.close(); QThreadPool.globalInstance().waitForDone(15000); app.processEvents()
