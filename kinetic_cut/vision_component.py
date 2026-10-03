"""Optional, isolated MediaPipe CPU runtime; no AI imports during editor startup."""
import json,os,shutil,tempfile,time
from pathlib import Path
from .vocal_component import download,unzip,monitored,check_cancel,PYTHON_URL,PYTHON_SHA,PIP_URL,PIP_SHA

MODELS={
 'face_landmarker.task':('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task','64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'),
 'selfie_segmenter.tflite':('https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/1/selfie_segmenter.tflite','191ac9529ae506ee0beefa6b2c945a172dab9d07d1e802a290a4e4038226658b')}

def component_root():
    from .config import DATA_DIR
    return DATA_DIR/'components'/'vision-v1'

def ready(root=None):
    root=Path(root or component_root())
    try:return json.loads((root/'ready.json').read_text())['version']==1 and (root/'python.exe').is_file() and all((root/'models'/name).is_file() for name in MODELS)
    except (OSError,ValueError,KeyError):return False

def install(progress,cancel,root=None):
    if root is None:
        from .feature_packs import manifest, install as install_pack
        if 'vision' in manifest():return install_pack('vision',progress,cancel)
    root=Path(root or component_root()).resolve()
    if ready(root):return root
    if os.name!='nt':raise RuntimeError('The optional vision installer currently supports Windows only.')
    root.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root.parent).free<1024**3:raise RuntimeError('Please free at least 1 GB for optional vision setup.')
    with tempfile.TemporaryDirectory(prefix='vision-install-',dir=root.parent) as directory:
        stage=Path(directory)/'runtime'; stage.mkdir()
        archive=Path(directory)/'python.zip'; download(PYTHON_URL,archive,PYTHON_SHA,progress,cancel,'Downloading optional Python runtime',0,15); unzip(archive,stage)
        (stage/'python311._pth').write_text('python311.zip\n.\nLib/site-packages\nimport site\n')
        wheel=Path(directory)/'pip.whl'; download(PIP_URL,wheel,PIP_SHA,progress,cancel,'Preparing installer',15,20)
        packages=stage/'Lib'/'site-packages'; packages.mkdir(parents=True); unzip(wheel,packages)
        python=str(stage/'python.exe')
        monitored([python,'-m','pip','--isolated','--disable-pip-version-check','install','--no-input','--no-cache-dir','--no-warn-script-location','mediapipe==0.10.32','numpy==1.26.4','opencv-contrib-python==4.11.0.86','pillow==11.3.0'],Path(directory)/'install.log',progress,cancel,'Installing optional face/background tools',25)
        models=stage/'models'; models.mkdir()
        for n,(name,(url,digest)) in enumerate(MODELS.items()):download(url,models/name,digest,progress,cancel,'Downloading '+name,85+n*5,90+n*5)
        monitored([python,'-c','import mediapipe, cv2, PIL; print("Vision component ready")'],Path(directory)/'check.log',progress,cancel,'Checking optional component',98)
        check_cancel(cancel); (stage/'ready.json').write_text(json.dumps({'version':1,'mediapipe':'0.10.32'}))
        if root.exists():root.rename(root.with_name(root.name+'-incomplete-'+str(time.time_ns())))
        stage.rename(root)
    progress((100,'Face and background component ready')); return root

def analyse(root,media,item,fps,destination,ffmpeg,progress,cancel):
    from .icons import resource_path
    from .vision_effects import fingerprint
    from .exporter import _crop_filter
    destination=Path(destination); destination.parent.mkdir(parents=True,exist_ok=True)
    sample_fps=max(1,min(60,fps/max(.05,item.speed)))
    with tempfile.TemporaryDirectory(prefix='vision-analysis-',dir=destination.parent) as directory:
        stage=Path(directory); movie=stage/'input.mp4'
        filters=_crop_filter(item)+f',scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2,fps={sample_fps:.6f}'
        inputs=['-loop','1'] if media.kind=='image' else ['-ss',str(item.in_point)]
        monitored([ffmpeg,'-hide_banner','-loglevel','error','-y']+inputs+['-i',media.path,'-t',str(item.source_duration),'-vf',filters,'-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(movie)],stage/'prepare.log',progress,cancel,'Preparing cropped clip for analysis',2)
        result=stage/'result'; result.mkdir()
        monitored([str(Path(root)/'python.exe'),str(resource_path('assets','vision_worker.py')),str(movie),str(Path(root)/'models'),str(result),str(sample_fps)],stage/'analyse.log',progress,cancel,'Analysing person and face throughout the clip',5,timeout=7200)
        info=json.loads((result/'info.json').read_text()); info.update(source=fingerprint(media),crop=vars(item.crop.clamped()),source_start=item.in_point,source_end=item.in_point+item.source_duration,fps=sample_fps)
        (result/'info.json').write_text(json.dumps(info)); check_cancel(cancel)
        if not destination.exists():result.rename(destination)
    progress((100,'Analysis complete')); return dict(info,root=str(destination))
