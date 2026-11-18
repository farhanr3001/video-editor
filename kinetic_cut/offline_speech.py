"""Optional, pinned Piper runtime and public-domain-dataset English narration."""
import hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path

VOICE='offline:en-US-ljspeech-medium'
BASE='https://huggingface.co/rhasspy/piper-voices/resolve/375a0fe641dea077c2a47b4e9a056d6da521eed3/en/en_US/ljspeech/medium/'
ARTIFACTS=(
    ('runtime.zip','https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip',22477236,'f3c58906402b24f3a96d92145f58acba6d86c9b5db896d207f78dc80811efcea'),
    ('voice.onnx',BASE+'en_US-ljspeech-medium.onnx',63531379,'6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22'),
    ('voice.onnx.json',BASE+'en_US-ljspeech-medium.onnx.json',4972,'141d612cc0a95ed7efc1ca936b845c2364967f2e9217c5dbfcf69fc4d6c65860'),
    ('MODEL_CARD',BASE+'MODEL_CARD',517,'fbee1529c89d36b3fe76d7e9f3f832dce17f44900a52d76a9bda735654766b4d'))
DOWNLOAD_BYTES=sum(x[2] for x in ARTIFACTS)
INSTALLED_BYTES=38846222+63531379+4972+517
NOTICES='''Offline English narration uses Piper 2023.11.14-2 (MIT):
https://github.com/rhasspy/piper/tree/2023.11.14-2
Copyright (c) 2022 Michael Hansen
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
Piper includes eSpeak NG (GPL v3), whose licence and corresponding source are available at:
https://github.com/espeak-ng/espeak-ng
ONNX Runtime (MIT): https://github.com/microsoft/onnxruntime
Voice model: en_US-ljspeech-medium, Piper voices revision 375a0fe641dea077c2a47b4e9a056d6da521eed3.
Model card: MODEL_CARD. Training dataset: LJ Speech (public domain), https://keithito.com/LJ-Speech-Dataset/
Original, unmodified runtime is downloaded directly from its upstream release; no paid account is required.
'''

def component_root():
    from .config import DATA_DIR
    return DATA_DIR/'components/offline-speech-v1'

def ready(root=None):
    root=Path(root) if root is not None else component_root()
    try:
        marker=json.loads((root/'ready.json').read_text())
        return marker.get('voice')==VOICE and (root/'piper/piper.exe').is_file() and (root/'voice.onnx').stat().st_size==63531379 and (root/'voice.onnx.json').is_file() and not root.is_symlink()
    except (OSError,ValueError):return False

def install(progress,cancel,root=None):
    from .verified_download import file_lock
    target=Path(root) if root is not None else component_root()
    with file_lock(target.with_suffix('.install.lock'),cancel):return _install(progress,cancel,target)

def _install(progress,cancel,root):
    from .verified_download import fetch
    from .feature_packs import extract
    from .config import CACHE_DIR
    root=Path(root) if root is not None else component_root();root.parent.mkdir(parents=True,exist_ok=True)
    if ready(root):progress((100,'Offline voice ready'));return root
    if root.is_symlink() or root.resolve().parent!=root.parent.resolve():raise ValueError('Unsafe offline voice location')
    if shutil.disk_usage(root.parent).free<DOWNLOAD_BYTES+INSTALLED_BYTES+128*1024**2:raise RuntimeError('Not enough free space for the offline voice')
    downloads=CACHE_DIR/'offline-speech-download';downloads.mkdir(parents=True,exist_ok=True);done=0
    for name,url,size,sha in ARTIFACTS:
        fetch(url,sha,size,downloads/name,cancel,lambda count,total:progress((round((done+count)/DOWNLOAD_BYTES*85),'Downloading offline English voice…')))
        done+=size
    with tempfile.TemporaryDirectory(prefix='offline-speech-',dir=root.parent) as directory:
        stage=Path(directory)/'runtime';stage.mkdir();extract(downloads/'runtime.zip',stage,cancel)
        for name,*_ in ARTIFACTS[1:]:shutil.copy2(downloads/name,stage/name)
        (stage/'NOTICES.txt').write_text(NOTICES,encoding='utf-8')
        inventory={p.relative_to(stage).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
        (stage/'ready.json').write_text(json.dumps(dict(voice=VOICE,files=inventory)),encoding='utf-8')
        if not ready(stage):raise RuntimeError('The offline voice download is incomplete')
        if cancel.is_set():raise InterruptedError('Offline voice download paused')
        previous=root.with_name(root.name+'.previous')
        if previous.exists():raise RuntimeError('An earlier offline voice installation needs attention')
        if root.exists():root.rename(previous)
        try:stage.rename(root)
        except OSError:
            if previous.exists():previous.rename(root)
            raise
        if previous.exists():shutil.rmtree(previous)
    for name,*_ in ARTIFACTS:(downloads/name).unlink(missing_ok=True)
    progress((100,'Offline English voice ready'));return root

def synthesize(text,target,rate,pitch,ffmpeg,cancel_check=None):
    from .process import run_cancellable
    from .tts import _run_audio_process
    root=component_root()
    if not ready(root):raise RuntimeError('Download the optional offline English voice before using it.')
    inventory=json.loads((root/'ready.json').read_text())['files']
    # Validate executable/DLL and model bytes off the GUI before running external code.
    for name,sha in inventory.items():
        if cancel_check and cancel_check():raise InterruptedError('Speech generation cancelled')
        path=root/name
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise RuntimeError('Offline voice files need repair. Remove and download the offline voice again.')
    target=Path(target)
    with tempfile.TemporaryDirectory(prefix='offline-voice-',dir=target.parent) as directory:
        raw=Path(directory)/'speech.wav';script=Path(directory)/'text.txt';script.write_text(text+'\n',encoding='utf-8')
        args=[str(root/'piper/piper.exe'),'--model',str(root/'voice.onnx'),'--output_file',str(raw),'--length_scale',str(1/max(.25,1+rate/100.))]
        with script.open('rb') as stdin,tempfile.TemporaryFile() as output:
            run_cancellable(args,stdin=stdin,stdout=output,stderr=output,cwd=root/'piper',cancel_check=cancel_check,timeout=max(60,len(text)/5),check=True,
                            env=dict(os.environ,OMP_NUM_THREADS='2'),creationflags=getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
        filters=[]
        if pitch:
            ratio=max(.5,min(2.,1+pitch/220.));filters=[f'asetrate=22050*{ratio}',f'aresample=22050',f'atempo={1/ratio}']
        cmd=[ffmpeg,'-y','-i',str(raw)]
        if filters:cmd+=['-af',','.join(filters)]
        _run_audio_process(cmd+['-c:a','libmp3lame','-q:a','2',str(target)],cancel_check)
    return str(target)
