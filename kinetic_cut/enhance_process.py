"""Inference-only ownership, cancellation and forward-progress watchdog."""
import json,os,subprocess,time
from pathlib import Path
from .process import popen
from .export_process import ChildJob,stop
from .vocal_component import check_cancel


def run(args,log,progress,cancel,timeout=3600,stall_timeout=30,startup_timeout=90):
    check_cancel(cancel);started=advanced=time.monotonic();last_frame=-1;ready=False
    with open(log,'wb') as output,open(log,'r',encoding='utf-8',errors='replace') as reader:
        child=popen(args,stdout=output,stderr=subprocess.STDOUT);job=ChildJob(child)
        try:
            if os.name=='nt' and job.handle is None:
                raise RuntimeError('Could not safely own the GPU worker lifetime. Inference was stopped.')
            while True:
                check_cancel(cancel)
                for line in reader.readlines():
                    try:update=json.loads(line)
                    except (ValueError,TypeError):continue
                    if not isinstance(update,dict):continue
                    frame=update.get('frames')
                    if isinstance(frame,int) and frame>last_frame:
                        last_frame=frame;advanced=time.monotonic();ready=True
                        progress((25,json.dumps(update)))
                if child.poll() is not None:break
                now=time.monotonic()
                if now-started>timeout:raise TimeoutError('AI Enhance exceeded its time limit; GPU processing was stopped.')
                if now-(advanced if ready else started)>(stall_timeout if ready else startup_timeout):
                    raise TimeoutError('AI Enhance stopped making progress; its GPU worker was stopped. Try a smaller crop or lower Upscale.')
                time.sleep(.1)
            check_cancel(cancel)
            if child.returncode:
                detail=Path(log).read_text(encoding='utf-8',errors='replace')[-2200:]
                raise RuntimeError('AI Enhance worker stopped. Original media is unchanged.\n'+detail)
            return dict(pid=child.pid,seconds=time.monotonic()-started)
        finally:
            if child.poll() is None:stop(child,job)
            job.close()
