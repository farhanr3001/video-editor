"""Explicitly downloaded, process-isolated temporal restoration runtime."""
import json,os,shutil,tempfile,time
from pathlib import Path
from .vocal_component import download,unzip,monitored,check_cancel,PYTHON_URL,PYTHON_SHA,PIP_URL,PIP_SHA

VERSION=2
MODELS=(('realesr-general-x4v3.pth','8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292'),
        ('realesr-general-wdn-x4v3.pth','1641f8c4464b9f097c9fdda5589273713f67cf59f3d909e0bd688f0cee269dca'))
MODEL_SHA=MODELS[0][1]
MODEL_URL='https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/'+MODELS[0][0]


def remove_legacy_model(root):
    import hashlib
    raw=Path(root)
    if raw.is_symlink() or raw.resolve().parent!=raw.parent.resolve():raise ValueError('Unsafe component storage path')
    root=raw.resolve();path=root/'models/realbasicvsr.pth'
    if not ready(root):raise RuntimeError('Verify the lightweight models before removing the old model.')
    if path.is_file() and not path.is_symlink() and path.resolve().parent==root/'models':
        if hashlib.sha256(path.read_bytes()).hexdigest()=='0e2ff2070a160bf19b26c194f82a0ee2ca8c6c4395a2bf927c768de048f156c1':
            size=path.stat().st_size;path.unlink();return size
    return 0


def model_paths(root):return [(str(Path(root)/'models'/name),digest) for name,digest in MODELS]


def runtime_ready(root):
    root=Path(root)
    try:return (root/'python.exe').is_file() and json.loads((root/'ready.json').read_text()).get('version') in (1,2)
    except (OSError,ValueError,AttributeError):return False

def component_root():
    from .config import DATA_DIR
    return DATA_DIR/'components'/'ai-enhance-v1'

def ready(root=None):
    root=Path(root or component_root())
    try:
        record=json.loads((root/'fast-ready.json').read_text())
        return record.get('version')==VERSION and record.get('model_sha256')==MODEL_SHA and (root/'python.exe').is_file() and all((root/'models'/name).stat().st_size==4885111 for name,_ in MODELS)
    except (OSError,ValueError,TypeError,AttributeError):return False

def default_acceleration():
    if os.name!='nt':return 'DirectML'
    import ctypes
    from ctypes import wintypes
    class Display(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('name',wintypes.WCHAR*32),('description',wintypes.WCHAR*128),('flags',wintypes.DWORD),('identity',wintypes.WCHAR*128),('key',wintypes.WCHAR*128)]
    for n in range(32):
        display=Display();display.cb=ctypes.sizeof(display)
        if not ctypes.windll.user32.EnumDisplayDevicesW(None,n,ctypes.byref(display),0):break
        if 'NVIDIA' in display.description.upper() and display.flags&1:return 'CUDA'
    return 'DirectML'

def install(progress,cancel,root=None,acceleration=None):
    root=Path(root or component_root()).resolve()
    if ready(root):return root
    acceleration=acceleration or default_acceleration()
    if acceleration not in ('CUDA','DirectML'):raise ValueError('Unknown enhancement acceleration')
    if os.name!='nt':raise RuntimeError('This optional runtime currently supports Windows.')
    root.parent.mkdir(parents=True,exist_ok=True)
    if runtime_ready(root):
        # Explicit upgrade reuses the owner's installed runtime and leaves the
        # old marker/model intact for rollback. Never download during inference.
        with tempfile.TemporaryDirectory(prefix='enhance-models-',dir=root.parent) as temporary:
            temporary=Path(temporary);(root/'models').mkdir(exist_ok=True)
            for n,(name,digest) in enumerate(MODELS):
                download('https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/'+name,temporary/name,digest,progress,cancel,'Downloading lightweight restoration model',n*45,(n+1)*45)
            check_cancel(cancel)
            for name,_ in MODELS:(temporary/name).replace(root/'models'/name)
            marker=temporary/'fast-ready.json';marker.write_text(json.dumps(dict(version=VERSION,model_sha256=MODEL_SHA)))
            check_cancel(cancel);marker.replace(root/'fast-ready.json')
            remove_legacy_model(root)
        progress((100,'Lightweight AI Enhance ready'));return root
    required=12 if acceleration=='CUDA' else 4
    if shutil.disk_usage(root.parent).free<required*1024**3:raise RuntimeError(f'Free at least {required} GB for optional AI Enhance setup.')
    with tempfile.TemporaryDirectory(prefix='enhance-install-',dir=root.parent) as directory:
        directory=Path(directory);stage=directory/'runtime';stage.mkdir()
        archive=directory/'python.zip';download(PYTHON_URL,archive,PYTHON_SHA,progress,cancel,'Downloading optional Python runtime',0,10);unzip(archive,stage)
        (stage/'python311._pth').write_text('python311.zip\n.\nLib/site-packages\nimport site\n')
        wheel=directory/'pip.whl';download(PIP_URL,wheel,PIP_SHA,progress,cancel,'Preparing installer',10,12)
        packages=stage/'Lib/site-packages';packages.mkdir(parents=True);unzip(wheel,packages)
        python=str(stage/'python.exe')
        pip=[python,'-m','pip','--isolated','--disable-pip-version-check','install','--no-input','--no-cache-dir','--no-warn-script-location','--only-binary=:all:']
        monitored(pip+['setuptools==75.6.0','sympy==1.13.1','mpmath==1.3.0','numpy==1.26.4','opencv-python-headless==4.11.0.86'],directory/'base-install.log',progress,cancel,'Installing optional image runtime',15,timeout=3600)
        packages=['torch==2.4.1','--index-url','https://download.pytorch.org/whl/cu121'] if acceleration=='CUDA' else ['torch==2.4.1','torch-directml==0.2.5.dev240914']
        monitored(pip+packages,directory/'install.log',progress,cancel,'Installing optional '+acceleration+' restoration runtime',25,timeout=3600)
        models=stage/'models';models.mkdir()
        for n,(name,digest) in enumerate(MODELS):
            download('https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/'+name,models/name,digest,progress,cancel,'Downloading lightweight restoration model',85+n*6,91+n*6)
        probe='import torch,cv2; assert torch.cuda.is_available(), "CUDA unavailable: update the NVIDIA driver or choose DirectML"; print(torch.cuda.get_device_name(0))' if acceleration=='CUDA' else 'import torch,cv2,torch_directml; print("AI Enhance runtime ready")'
        monitored([python,'-c',probe],directory/'check.log',progress,cancel,'Checking optional runtime',98)
        check_cancel(cancel);(stage/'ready.json').write_text(json.dumps({'version':VERSION,'model_sha256':MODEL_SHA,'acceleration':acceleration}))
        (stage/'fast-ready.json').write_text(json.dumps({'version':VERSION,'model_sha256':MODEL_SHA}))
        if root.exists():root.rename(root.with_name(root.name+'-incomplete-'+str(time.time_ns())))
        stage.rename(root)
    progress((100,'AI Enhance ready'));return root
