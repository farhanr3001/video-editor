"""Opt-in download/integration check; installs only into this test directory."""
import os,sys,threading,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/"build/vocal-component-check"; OUT.mkdir(parents=True,exist_ok=True)
os.environ["KINETIC_CUT_HOME"]=str(OUT/"home")
from kinetic_cut.vocal_component import install,process_audio,ready
from kinetic_cut.process import run
root=OUT/"runtime"; cancel=threading.Event()
last=[None]
def progress(value):
    percent,text=value
    if int(percent)!=last[0] or "Downloading" not in text:print(int(percent),text,flush=True); last[0]=int(percent)
install(progress,cancel,root)
source=ROOT/"build/word-cuts-check/speech.wav"
if not source.exists():source=ROOT/"xqc_royalty.mp4"
offset=0
if '--video' in sys.argv:
    from kinetic_cut.model import Project
    project=Project.load(ROOT/'TestEdit.kcut'); item=next(i for i in project.timeline if i.track in project.audio_tracks)
    source=Path(project.media_by_id(item.media_id).path); offset=item.in_point
output=OUT/("video-vocals.mp3" if '--video' in sys.argv else "vocals.mp3"); process_audio(root,str(source),offset,3,str(output),"ffmpeg",progress,cancel)
from kinetic_cut.media import probe
media=probe(output); assert 2.9<media.duration<3.2
report={"passed":True,"installed_bytes":sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),"output_duration":media.duration,"root":str(root),"input":str(source),"source_offset":offset}
(OUT/("video-report.json" if '--video' in sys.argv else "report.json")).write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
