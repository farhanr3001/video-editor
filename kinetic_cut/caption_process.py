"""Owned caption inference process: responsive GUI, bounded progress, prompt cancel."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(path,settings,offset=0.,progress=None,words_per_caption=5,hold_seconds=.5,
        require_word_timestamps=False,cancel_check=None):
    from .captions import _check_cancel,CaptionBackendError
    from .model import Caption,CaptionStyle
    from .process import popen
    from .export_process import ChildJob,stop
    _check_cancel(cancel_check)
    with tempfile.TemporaryDirectory(prefix='kinetic-caption-worker-') as directory:
        folder=Path(directory);request=folder/'request.json';log=folder/'worker.log'
        # Never serialize unrelated credentials/settings into an inference request.
        allowed=('whisper_model','whisper_cli','whisper_model_path','caption_language','caption_device','caption_alignment','caption_vocabulary','ffmpeg')
        request.write_text(json.dumps(dict(path=str(Path(path).resolve()),settings={k:settings[k] for k in allowed if k in settings},offset=offset,
            words_per_caption=words_per_caption,hold_seconds=hold_seconds,require_word_timestamps=require_word_timestamps)),encoding='utf-8')
        command=[sys.executable]
        if not getattr(sys,'frozen',False):command.append(str(Path(__file__).resolve().parents[1]/'main.py'))
        command+=['--caption-worker',str(request)]
        started=advanced=time.monotonic();last=None
        with log.open('wb') as output:
            child=popen(command,stdout=output,stderr=subprocess.STDOUT);job=ChildJob(child)
            try:
                if os.name=='nt' and job.handle is None:raise CaptionBackendError('Could not safely own the caption worker. Transcription was stopped.')
                while True:
                    _check_cancel(cancel_check)
                    status=folder/'progress.json'
                    update=None
                    try:
                        stamp=status.stat().st_mtime_ns
                        if stamp!=last:
                            value=json.loads(status.read_text(encoding='utf-8'));last=stamp;advanced=time.monotonic()
                            update=tuple(value) if isinstance(value,list) else value
                    except (OSError,ValueError):pass  # Atomic replacement can briefly be Windows-locked.
                    if update is not None and progress:progress(update)
                    if child.poll() is not None:break
                    if time.monotonic()-started>3600 or time.monotonic()-advanced>180:
                        raise CaptionBackendError('The caption engine stopped making progress. Its GPU/CPU worker was stopped; please retry.')
                    time.sleep(.05)
                _check_cancel(cancel_check)
                result=folder/'result.json'
                if child.returncode or not result.is_file():
                    error=folder/'error.json'
                    detail=json.loads(error.read_text(encoding='utf-8')) if error.is_file() else log.read_text(encoding='utf-8',errors='replace')[-1500:]
                    raise CaptionBackendError('The caption engine could not finish. '+str(detail))
                data=json.loads(result.read_text(encoding='utf-8'))
                return [Caption(**dict(row,style=CaptionStyle(**row['style']))) for row in data['captions']],data['backend']
            finally:
                if child.poll() is None:stop(child,job)
                child.wait();job.close()


def worker(request):
    from dataclasses import asdict
    from .captions import transcribe
    folder=Path(request).resolve().parent
    try:
        data=json.loads(Path(request).read_text(encoding='utf-8'))
        def progress(value):
            pending=folder/'progress.pending'
            pending.write_text(json.dumps(value),encoding='utf-8')
            try:pending.replace(folder/'progress.json')
            except PermissionError:pass  # Next bounded update replaces this one.
        captions,backend=transcribe(**data,progress=progress)
        (folder/'result.json').write_text(json.dumps(dict(backend=backend,captions=[asdict(c) for c in captions])),encoding='utf-8')
        return 0
    except Exception as error:
        (folder/'error.json').write_text(json.dumps(str(error)),encoding='utf-8')
        return 1
