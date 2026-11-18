"""Release evidence is bound to source, version and the actual artifacts."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.check_project import fingerprint
from kinetic_cut.version import VERSION

REQUIRED=('source','staged','installed','installer')
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def validate(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not data.get('passed') or data.get('version')!=VERSION or data.get('source_fingerprint')!=fingerprint():raise ValueError('Release evidence does not match current source/version')
    if set(data.get('milestones',{}))!=set(REQUIRED):raise ValueError('Missing release milestone')
    for kind,item in data['milestones'].items():
        report=Path(item['report'])
        if sha(report)!=item['sha256'] or not json.loads(report.read_text()).get('passed'):raise ValueError('Release evidence changed: '+kind)
    for name,item in data.get('artifacts',{}).items():
        if sha(ROOT/name)!=item['sha256']:raise ValueError('Release artifact changed: '+name)
    build=json.loads((ROOT/'release/build-report.json').read_text(encoding='utf-8'))
    stage=json.loads(Path(data['milestones']['staged']['report']).read_text(encoding='utf-8'))
    if build.get('source_fingerprint')!=data['source_fingerprint'] or build.get('stage_exe_sha256')!=stage.get('exe_sha256'):raise ValueError('Public installer was not built from the verified staged app')
    for field,name in [('full_setup_sha256',f'release/KineticCut-FullSetup-{VERSION}.exe'),('setup_sha256',f'release/KineticCut-Setup-{VERSION}.exe')]:
        if build.get(field)!=sha(ROOT/name):raise ValueError('Installer build receipt does not match '+name)
    expected={f'release/KineticCut-Setup-{VERSION}.exe',f'release/KineticCut-FullSetup-{VERSION}.exe',f'release/KineticCut-Update-{VERSION}.json','release/build-report.json','release/KineticCut-Baseline-1.1.0.json'}
    expected|={name for name in ('release/components.json',f'release/KineticCut-Inventory-{VERSION}.json') if (ROOT/name).is_file()}
    expected|={str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'release/update-payloads').glob('*.zip')}
    if not expected.issubset(data.get('artifacts',{})):raise ValueError('Release artifact inventory is incomplete')
    return data

def seal(output,milestones):
    source=fingerprint();evidence={}
    for kind,path in milestones.items():
        path=Path(path).resolve();report=json.loads(path.read_text(encoding='utf-8'))
        if not report.get('passed') or report.get('source_fingerprint')!=source or report.get('kind')!=kind:raise ValueError('Unverified or stale milestone: '+kind)
        if kind=='source' and not report.get('full'):raise ValueError('Publication requires a complete source checkpoint')
        evidence[kind]=dict(report=str(path),sha256=sha(path))
    if set(evidence)!=set(REQUIRED):raise ValueError('Missing release milestone')
    artifacts=[*sorted((ROOT/'release').glob(f'*{VERSION}.*')),ROOT/'release/build-report.json',ROOT/'release/KineticCut-Baseline-1.1.0.json',ROOT/'release/components.json',*sorted((ROOT/'release/update-payloads').glob('*.zip'))]
    result=dict(passed=True,version=VERSION,source_fingerprint=source,milestones=evidence,
                artifacts={p.relative_to(ROOT).as_posix():dict(sha256=sha(p)) for p in artifacts if p.is_file()})
    Path(output).write_text(json.dumps(result,indent=2),encoding='utf-8');return validate(output)

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('seal');p.add_argument('output');[p.add_argument('--'+k,required=True) for k in REQUIRED]
    p=sub.add_parser('verify');p.add_argument('path')
    p=sub.add_parser('prepare-installer-channel');a=parser.parse_args()
    if a.command=='prepare-installer-channel':
        import shutil
        full=ROOT/f'release/KineticCut-FullSetup-{VERSION}.exe';setup=ROOT/f'release/KineticCut-Setup-{VERSION}.exe'
        if setup.exists() and setup.samefile(full):setup.unlink()
        shutil.copy2(full,setup)
        shutil.copy2(ROOT/f'release/KineticCut-Update-{VERSION}.json',ROOT/f'release/KineticCut-Inventory-{VERSION}.json')
        path=ROOT/'release/build-report.json';report=json.loads(path.read_text());report.update(update_channel='full-installer',migration_bytes=setup.stat().st_size,setup_sha256=sha(setup));path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Installer channel prepared; verify and seal before uploading');return
    if a.command=='seal':seal(a.output,{k:getattr(a,k) for k in REQUIRED})
    else:validate(a.path)
    print('Release evidence verified: source, staged app, installed app, installer and artifacts',flush=True)
if __name__=='__main__':main()
