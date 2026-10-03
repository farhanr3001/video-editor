import os,sys,json,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/'build/vision-component-check'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(OUT/'home')
from kinetic_cut.vision_component import install,analyse
from kinetic_cut.model import Project
cancel=threading.Event(); progress=lambda value:print(round(value[0]),value[1],flush=True)
root=install(progress,cancel,OUT/'runtime'); p=Project.load(ROOT/'TestEdit.kcut'); item=next(i for i in p.timeline if i.track=='video_3'); media=p.media_by_id(item.media_id); item.duration=2
result=analyse(root,media,item,30,OUT/('analysis-'+str(time.time_ns())),'ffmpeg',progress,cancel)
result['installed_bytes']=sum(f.stat().st_size for f in root.rglob('*') if f.is_file()); (OUT/'report.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2),flush=True)
assert result['face_frames']>0 and result['person_frames']>0
