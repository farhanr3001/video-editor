"""Separate full-quality render measurement of the user-approved test project."""
import os,sys,time,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
out=root/'build'/sys.argv[1]; out.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(out/'home')
from kinetic_cut.model import Project
from kinetic_cut.exporter import export,PRESETS,automatic_encoder
from kinetic_cut.render_batches import ranges
p=Project.load(root/'xqc kai fashion show.kcut')
report={'duration':p.duration,'items':len(p.timeline),'batches':len(ranges(p)),'hardware':automatic_encoder('ffmpeg','h264')}
start=time.perf_counter()
export(p,str(out/'fashion.mp4'),PRESETS['YouTube Shorts · Quality'],hardware='Auto',progress=lambda value,text:print(round(value*100,1),text,flush=True))
report['elapsed_seconds']=time.perf_counter()-start
(out/'report.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report))
