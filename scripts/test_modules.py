"""Run every unittest module in a fresh Qt process (no cross-module windows)."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
output = Path(sys.argv[sys.argv.index('--output')+1]).resolve() if '--output' in sys.argv else root / 'build' / 'theme-module-tests'
output.mkdir(parents=True, exist_ok=True)

def run(path):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
               KINETIC_CUT_HOME=str(output / path.stem / 'unit-test-home'))
    env.pop('KINETIC_TEST_WATCHDOG', None)
    started = time.monotonic()
    log = output / (path.stem + '.log')
    with log.open('w', encoding='utf-8') as stream:
        process = subprocess.Popen([sys.executable, str(root/'scripts/unit_tests.py'), path.name],
                                   cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            code = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                process.kill()
            process.wait(); code = -1
    text = log.read_text(encoding='utf-8', errors='replace')
    count = re.search(r'Ran (\d+) tests?', text)
    return dict(module=path.name, code=code, tests=int(count[1]) if count else 0,
                seconds=round(time.monotonic()-started,2))

if __name__=='__main__':
    paths = sorted((root/'tests').glob('test*.py'))
    previous = None
    if '--retry-failed' in sys.argv:
        previous = json.loads((output/'report.json').read_text(encoding='utf-8'))
        failed = {r['module'] for r in previous['modules'] if r['code'] != 0}
        paths = [p for p in paths if p.name in failed]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for result in executor.map(run, paths):
            results.append(result)
            print(json.dumps(result), flush=True)
    if previous:
        latest = {r['module']: r for r in results}
        results = [latest.get(r['module'],r) for r in previous['modules']]
    report=dict(passed=all(r['code']==0 for r in results),
                tests=sum(r['tests'] for r in results), modules=results)
    if previous:
        report['previous_attempt'] = previous
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    sys.exit(0 if report['passed'] else 1)
