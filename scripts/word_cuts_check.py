"""Offline real speech recognition + audio source-trim/non-ripple validation."""
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/"build/word-cuts-check"; OUT.mkdir(parents=True,exist_ok=True)
os.environ["HF_HUB_OFFLINE"]="1"; os.environ.setdefault("KINETIC_CUT_HOME",str(OUT/"home"))
from kinetic_cut.process import run
from kinetic_cut.captions import transcribe
from kinetic_cut.profanity import contains_curse,censor_text
from kinetic_cut.media import probe
from kinetic_cut.model import Project,TimelineItem
from kinetic_cut.timeline_actions import complement,keep_audio_ranges
wav=OUT/"speech.wav"
if not wav.exists() or wav.stat().st_size<100:
    run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ROOT/"scripts/speech_fixture.ps1"),str(wav)],check=True,capture_output=True)
words,backend=transcribe(str(wav),{"whisper_model":"base.en"},words_per_caption=1,hold_seconds=0,require_word_timestamps=True)
curses=[c for c in words if contains_curse(c.text)]; assert len(curses)>=2,[(w.text,w.start,w.end) for w in words]
media=probe(wav); clip=TimelineItem("audio",media.id,"audio_1",3,media.duration,in_point=0)
p=Project(media=[media],timeline=[clip]); keep=complement(clip.duration,[(c.start,c.end) for c in curses]); ids=keep_audio_ranges(p,clip,keep)
assert len(ids)>=2 and p.timeline[0].start==3
assert all(abs(c.in_point-(c.start-3))<.00001 for c in p.timeline)
report={"passed":True,"backend":backend,"detected":[{"word":censor_text(c.text),"start":c.start,"end":c.end} for c in curses],"retained_audio_segments":len(ids),"source_duration":media.duration,"timeline_start":3}
(OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8"); print(json.dumps(report,indent=2))
