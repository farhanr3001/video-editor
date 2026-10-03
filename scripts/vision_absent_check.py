"""Real optional-model negative test; no source media is changed."""
import os,sys,json,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/'build/vision-component-check'
os.environ['KINETIC_CUT_HOME']=str(OUT/'home')
from PIL import Image
from kinetic_cut.model import MediaItem,TimelineItem
from kinetic_cut.vision_component import analyse
source=OUT/'no-face.png'; Image.new('RGB',(320,180),'black').save(source)
media=MediaItem('none',str(source),'image','No face',1,320,180); item=TimelineItem('none','none','video_1',0,1)
result=analyse(OUT/'runtime',media,item,5,OUT/('absent-'+str(time.time_ns())),'ffmpeg',lambda v:print(v,flush=True),threading.Event())
assert result['face_frames']==0 and result['person_frames']==0,result
(OUT/'absent-report.json').write_text(json.dumps(result,indent=2)); print('PASS: no face/person reported on empty clip',flush=True)
