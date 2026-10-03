"""Runs only inside the optional isolated runtime; never imported by the editor."""
import sys,os
from pathlib import Path
import numpy as np
import soundfile as sf
import torch
from demucs.pretrained import get_model
from demucs.apply import apply_model

torch.set_num_threads(2); torch.set_num_interop_threads(1)
repo,source,output=map(Path,sys.argv[1:4])
print("KINETIC_PROGRESS 9 Loading vocal separation model",flush=True)
model=get_model("955717e8",repo=repo); model.eval()
with sf.SoundFile(source) as stream, sf.SoundFile(output,"w",samplerate=44100,channels=2,subtype="FLOAT") as target:
    assert stream.samplerate==44100 and stream.channels==2
    total=len(stream); block=44100*20; context=44100*2
    for begin in range(0,total,block):
        end=min(total,begin+block); left=max(0,begin-context); right=min(total,end+context)
        stream.seek(left); audio=stream.read(right-left,dtype="float32",always_2d=True).T
        wav=torch.from_numpy(audio); ref=wav.mean(0); mean=ref.mean(); std=ref.std().clamp(min=1e-8)
        with torch.inference_mode():
            stems=apply_model(model,((wav-mean)/std)[None],device="cpu",shifts=0,split=True,overlap=.25,progress=False,num_workers=0,segment=5)[0]
            vocal=(stems[model.sources.index("vocals")]*std+mean).numpy()
        target.write(vocal[:,begin-left:end-left].T)
        print(f"KINETIC_PROGRESS {10+85*end/max(1,total):.1f} Separating vocals · {end/44100:.1f} / {total/44100:.1f} seconds",flush=True)
print("KINETIC_PROGRESS 96 Vocal separation complete",flush=True)
