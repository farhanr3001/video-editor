"""External deadline/heartbeat watchdog; only terminates its own diagnostic tree."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
from kinetic_cut.process import popen
from kinetic_cut.export_process import ChildJob,stop

parser=argparse.ArgumentParser()
parser.add_argument('--seconds',type=int,default=900)
parser.add_argument('--output',required=True)
parser.add_argument('--exe')
args=parser.parse_args(); out=Path(args.output).resolve(); out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,KINETIC_STABILITY_SECONDS=str(args.seconds))
command=[args.exe] if args.exe else [sys.executable,str(root/'main.py')]
command+=['--stability-selftest',str(out)]
started=time.monotonic(); failure=None
with (out/'process.log').open('w',encoding='utf-8') as log:
    child=popen(command,cwd=root,env=env,stdout=log,stderr=log); job=ChildJob(child)
    try:
        while child.poll() is None:
            heartbeat=out/'gui-heartbeat.txt'
            age=time.time()-heartbeat.stat().st_mtime if heartbeat.exists() else time.monotonic()-started
            if age>60:
                failure='GUI heartbeat stopped for over 60 seconds'; stop(child,job); break
            if time.monotonic()-started>args.seconds+120:
                failure='Diagnostic exceeded duration plus startup/close allowance'; stop(child,job); break
            time.sleep(1)
    finally:job.close()
    code=child.wait()
result={'exit_code':code,'watchdog_failure':failure,'elapsed_seconds':time.monotonic()-started,'command':command}
(out/'watchdog.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
raise SystemExit(0 if code==0 and not failure else 1)
