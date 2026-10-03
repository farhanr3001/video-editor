"""Read-only source investigation: compare Whisper word timing around reported silence."""
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/"build/caption-alignment-probe"; OUT.mkdir(parents=True,exist_ok=True)
os.environ["HF_HUB_OFFLINE"]="1"
from kinetic_cut.process import run
from faster_whisper import WhisperModel
source=r"C:\Users\F\Videos\NoPixel5\2026-09-08 18-18-24.mp4"
wav=OUT/"first-22s.wav"
run(["ffmpeg","-v","error","-y","-i",source,"-t","22","-vn","-ac","1","-ar","16000",str(wav)],check=True)
model=WhisperModel("base.en",device="cpu",compute_type="int8",local_files_only=True)
report={}
for vad in (True,False):
    segments,_=model.transcribe(str(wav),language="en",vad_filter=vad,word_timestamps=True)
    report[str(vad)]=[{"text":s.text,"start":s.start,"end":s.end,"words":[{"text":w.word,"start":w.start,"end":w.end,"probability":w.probability} for w in s.words]} for s in segments]
    print(vad,json.dumps(report[str(vad)]),flush=True)
(OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
from faster_whisper.audio import decode_audio
from faster_whisper.vad import get_speech_timestamps,VadOptions
audio=decode_audio(str(wav)); spans=get_speech_timestamps(audio,VadOptions(min_silence_duration_ms=700,speech_pad_ms=200))
report['regions']=[]
for span in spans:
    origin=span['start']/16000
    segments,_=model.transcribe(audio[span['start']:span['end']],language='en',vad_filter=False,word_timestamps=True,condition_on_previous_text=False)
    report['regions'] += [{"text":w.word,"start":origin+w.start,"end":origin+w.end} for s in segments for w in s.words]
print('regions',json.dumps(report['regions']),flush=True)
(OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
