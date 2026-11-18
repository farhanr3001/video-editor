"""One isolated source checkpoint, with logs and an exact source fingerprint."""
import argparse,concurrent.futures,hashlib,json,os,re,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def fingerprint():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    paths=sorted({n for n in names if n and (n.startswith(('kinetic_cut/','tests/','scripts/','assets/','native/','installer/','.github/')) or n.endswith('.py') and '/' not in n or n in ('requirements.txt','KineticCut.spec','build.ps1'))})
    return hashlib.sha256(json.dumps([(n,hashlib.sha256((ROOT/n).read_bytes()).hexdigest()) for n in paths if (ROOT/n).is_file()]).encode()).hexdigest()

def checkpoint(output,modules=None,jobs=3,timeout=300):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True);before=fingerprint()
    paths=[ROOT/'tests'/m for m in modules] if modules else sorted((ROOT/'tests').glob('test*.py'))
    if not paths or any(p.parent!=ROOT/'tests' or not p.is_file() or not p.name.startswith('test') for p in paths):raise ValueError('Unknown test module')
    def run(path):
        started=time.monotonic()
        with tempfile.TemporaryDirectory(prefix=path.stem+'-',dir=output) as home:
            tools=ROOT/'build/distribution-stage/KineticCut/_internal/assets/tools'
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',KINETIC_CUT_HOME=home,KINETIC_TEST_WATCHDOG='1',PATH=str(tools)+os.pathsep+os.environ.get('PATH',''))
            log=output/(path.stem+'.log')
            with log.open('wb') as stream:
                try:code=subprocess.run([sys.executable,str(ROOT/'scripts/unit_tests.py'),path.name],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).returncode
                except subprocess.TimeoutExpired:code=124
            text=log.read_text(encoding='utf-8',errors='replace');match=re.search(r'Ran (\d+) tests?',text)
            result=dict(module=path.name,code=code,tests=int(match[1]) if match else 0,seconds=round(time.monotonic()-started,2))
            print(json.dumps(result),flush=True);return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:rows=list(pool.map(run,paths))
    report=dict(passed=all(row['code']==0 and row['tests']>0 for row in rows) and before==fingerprint(),
                kind='source',full=not modules,source_fingerprint=before,tests=sum(r['tests'] for r in rows),modules=rows)
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report

def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('modules',nargs='*');p.add_argument('--jobs',type=int,default=3);p.add_argument('--timeout',type=int,default=300)
    a=p.parse_args();return 0 if checkpoint(a.output,a.modules or None,a.jobs,a.timeout)['passed'] else 1
if __name__=='__main__':sys.exit(main())
