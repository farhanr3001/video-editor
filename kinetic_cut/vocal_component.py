"""Opt-in CPU separation runtime. Never imports torch into the editor process."""
import hashlib,json,os,shutil,subprocess,tempfile,time,urllib.request,zipfile
from pathlib import Path
from .process import popen,run

VERSION=1
PYTHON_URL="https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
PYTHON_SHA="009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b"
PIP_URL="https://files.pythonhosted.org/packages/ef/7d/500c9ad20238fcfcb4cb9243eede163594d7020ce87bd9610c9e02771876/pip-24.3.1-py3-none-any.whl"
PIP_SHA="3790624780082365f47549d032f3770eeb2b1e8bd1f7b2e02dace1afa361b4ed"
MODEL_NAME="955717e8-8726e21a.th"
MODEL_URL="https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/"+MODEL_NAME
MODEL_SHA="8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"


class Cancelled(Exception):pass


def component_root():
    from .config import DATA_DIR
    return DATA_DIR/"components"/"vocal-only-v1"


def ready(root=None):
    root=Path(root or component_root())
    try:return json.loads((root/"ready.json").read_text())["version"]==VERSION and (root/"python.exe").is_file() and (root/"models"/MODEL_NAME).is_file()
    except (OSError,ValueError,KeyError):return False


def check_cancel(cancel):
    if cancel.is_set():raise Cancelled("Cancelled — timeline and source files were not changed.")


def download(url,target,digest,progress,cancel,label,low,high):
    check_cancel(cancel); h=hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"KineticCut-OptionalVocals/1"}),timeout=30) as response, open(target,"wb") as stream:
        total=int(response.headers.get("Content-Length",0)); done=0
        while True:
            check_cancel(cancel); chunk=response.read(256*1024)
            if not chunk:break
            stream.write(chunk); h.update(chunk); done+=len(chunk)
            progress((low+(high-low)*min(1,done/total) if total else low,f"{label} · {done/1048576:.1f}"+(f" / {total/1048576:.1f} MB" if total else " MB")))
    if h.hexdigest()!=digest:raise RuntimeError(label+" failed its SHA-256 integrity check. Please retry.")


def unzip(archive,destination):
    destination=Path(destination).resolve()
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if not (destination/member.filename).resolve().is_relative_to(destination):raise RuntimeError("Unsafe archive path")
        source.extractall(destination)


def monitored(args,log,progress,cancel,label,percent,env=None,timeout=1800):
    """File-backed output avoids pipe deadlocks; terminate only our process tree."""
    from .export_process import ChildJob,stop
    progress((percent,label)); started=time.monotonic(); last=""
    with open(log,"wb") as output:
        child=popen(args,stdout=output,stderr=subprocess.STDOUT,env=env); job=ChildJob(child)
        try:
            while child.poll() is None:
                if cancel.is_set() or time.monotonic()-started>timeout:
                    stop(child,job); check_cancel(cancel); raise TimeoutError(label+" timed out. Please retry.")
                with open(log,"rb") as reader:
                    reader.seek(max(0,os.path.getsize(log)-3000)); tail=reader.read().decode("utf-8",errors="replace").strip()
                if tail and tail!=last:
                    last=tail; line=tail.replace("\r","\n").splitlines()[-1]
                    if line.startswith("KINETIC_PROGRESS "):
                        _,value,text=line.split(" ",2); progress((float(value),text))
                    else:progress((percent,label+"\n"+line[:180]))
                time.sleep(.15)
            if child.returncode:
                detail=Path(log).read_text(encoding="utf-8",errors="replace")[-2200:]
                raise RuntimeError(label+" failed.\n"+detail)
        finally:
            if child.poll() is None:stop(child,job)
            job.close()
    check_cancel(cancel)


def install(progress,cancel,root=None):
    if root is None:
        from .feature_packs import manifest, install as install_pack
        if 'vocals' in manifest():return install_pack('vocals',progress,cancel)
    root=Path(root or component_root()).resolve()
    if ready(root):return root
    if os.name!="nt":raise RuntimeError("The optional installer currently supports 64-bit Windows.")
    root.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root.parent).free<2*1024**3:raise RuntimeError("Please free at least 2 GB for the optional component installation.")
    with tempfile.TemporaryDirectory(prefix="vocal-install-",dir=root.parent) as directory:
        stage=Path(directory)/"runtime"; stage.mkdir(); python_zip=Path(directory)/"python.zip"
        download(PYTHON_URL,python_zip,PYTHON_SHA,progress,cancel,"Downloading isolated Python runtime",0,12); unzip(python_zip,stage)
        (stage/"python311._pth").write_text("python311.zip\n.\nLib/site-packages\nimport site\n",encoding="utf-8")
        wheel=Path(directory)/"pip.whl"; download(PIP_URL,wheel,PIP_SHA,progress,cancel,"Preparing installer",12,16)
        packages=stage/"Lib"/"site-packages"; packages.mkdir(parents=True,exist_ok=True); unzip(wheel,packages)
        python=str(stage/"python.exe"); pip=[python,"-m","pip","--isolated","--disable-pip-version-check","install","--no-input","--no-cache-dir","--no-warn-script-location"]
        monitored(pip+["setuptools==75.8.0","wheel==0.45.1","numpy==1.26.4"],Path(directory)/"setup.log",progress,cancel,"Preparing CPU dependencies",20)
        monitored(pip+["torch==2.0.1+cpu","torchaudio==2.0.2+cpu","--index-url","https://download.pytorch.org/whl/cpu"],Path(directory)/"torch.log",progress,cancel,"Downloading and installing CPU processing engine",30)
        monitored(pip+["--no-build-isolation","demucs==4.0.1","soundfile==0.13.1"],Path(directory)/"demucs.log",progress,cancel,"Installing vocal separation tools",70)
        models=stage/"models"; models.mkdir()
        download(MODEL_URL,models/MODEL_NAME,MODEL_SHA,progress,cancel,"Downloading vocal separation model",82,97)
        monitored([python,"-c","import torch, torchaudio, demucs, soundfile; print('Optional engine ready')"],Path(directory)/"verify.log",progress,cancel,"Checking installation",98)
        check_cancel(cancel)
        (stage/"ready.json").write_text(json.dumps({"version":VERSION,"model_sha256":MODEL_SHA}),encoding="utf-8")
        if root.exists():root.rename(root.with_name(root.name+"-incomplete-"+str(time.time_ns())))
        stage.rename(root)
    progress((100,"Vocal Only is ready")); return root


def process_audio(root,source,in_point,source_duration,output,ffmpeg,progress,cancel):
    from .icons import resource_path
    with tempfile.TemporaryDirectory(prefix="kinetic-vocals-") as directory:
        directory=Path(directory); wave=directory/"source.wav"; vocals=directory/"vocals.wav"
        monitored([ffmpeg,"-hide_banner","-loglevel","error","-y","-ss",str(in_point),"-t",str(source_duration),"-i",source,"-vn","-ac","2","-ar","44100",str(wave)],directory/"extract.log",progress,cancel,"Extracting selected clip audio",1)
        env=os.environ.copy(); env.update(OMP_NUM_THREADS="2",MKL_NUM_THREADS="2",PYTHONNOUSERSITE="1")
        helper=resource_path("assets","vocal_worker.py")
        monitored([str(Path(root)/"python.exe"),str(helper),str(Path(root)/"models"),str(wave),str(vocals)],directory/"separate.log",progress,cancel,"Loading vocal model and separating audio",8,env=env,timeout=7200)
        # Write beside the chosen output and atomically publish only on success.
        with tempfile.NamedTemporaryFile(prefix=".kinetic-vocals-",suffix=".mp3",dir=Path(output).parent,delete=False) as file:partial=Path(file.name)
        try:
            monitored([ffmpeg,"-hide_banner","-loglevel","error","-y","-i",str(vocals),"-codec:a","libmp3lame","-b:a","320k",str(partial)],directory/"encode.log",progress,cancel,"Saving vocal-only MP3",97)
            check_cancel(cancel); os.replace(partial,output)
        finally:
            if partial.exists():partial.unlink()
    return output
