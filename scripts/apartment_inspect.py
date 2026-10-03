"""Read-only source analysis; outputs are confined to this task's build folder."""
import json
import subprocess
from pathlib import Path
import numpy as np
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'build/apartment-edit'
OUT.mkdir(parents=True, exist_ok=True)
SRC = Path('C:/Users/F/Videos/NoPixel5')
def run(args):
    return subprocess.run(args, check=True, capture_output=True, creationflags=0x08000000)

model = WhisperModel('base.en', device='cpu', compute_type='int8', local_files_only=True)
audio = []
for n in range(1,4):
    path = SRC/f'new house pt{n}.mp4'
    probe = json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]).stdout)
    (OUT/f'probe{n}.json').write_text(json.dumps(probe,indent=2))
    run(['ffmpeg','-y','-v','error','-i',str(path),'-vf','fps=1/6,scale=480:-1,tile=3x4','-frames:v','1',str(OUT/f'contact{n}.jpg')])
    wav = OUT/f'audio{n}.wav'
    run(['ffmpeg','-y','-v','error','-i',str(path),'-vn','-ar','16000','-ac','1',str(wav)])
    raw = run(['ffmpeg','-v','error','-i',str(wav),'-f','f32le','-ar','4000','-ac','1','-']).stdout
    audio.append(np.frombuffer(raw,dtype=np.float32))
    dest = OUT/f'transcript{n}.json'
    if not dest.exists():
        segments,info = model.transcribe(str(wav),language='en',word_timestamps=True,vad_filter=True)
        data = [dict(start=s.start,end=s.end,text=s.text,words=[dict(text=w.word,start=w.start,end=w.end) for w in s.words]) for s in segments]
        dest.write_text(json.dumps(data,indent=2))
    print(f'Clip {n}: {probe["format"]["duration"]} seconds',flush=True)
    for s in json.loads(dest.read_text()):print(f'{s["start"]:.2f}-{s["end"]:.2f} {s["text"]}',flush=True)
overlaps=[]
for i,j in ((0,1),(1,2),(0,2)):
    a,b=audio[i],audio[j]
    # Match the first five seconds of the later clip against the earlier source.
    sample=b[:20000]
    size=1 << (len(a)+len(sample)-2).bit_length()
    conv=np.fft.irfft(np.fft.rfft(a,size)*np.fft.rfft(sample[::-1],size),size)
    corr=conv[len(sample)-1:len(a)]
    cs=np.concatenate(([0.],np.cumsum(a.astype(np.float64)**2)))
    norm=np.sqrt(np.maximum(1e-12,(cs[20000:]-cs[:-20000])*np.sum(sample*sample)))
    scores=corr/norm; at=int(np.argmax(scores)); score=float(scores[at])
    overlaps.append(dict(earlier=i+1,later=j+1,later_start_in_earlier=at/4000,correlation=score,overlap_seconds=(len(a)-at)/4000))
(OUT/'overlaps.json').write_text(json.dumps(overlaps,indent=2)); print(overlaps,flush=True)
