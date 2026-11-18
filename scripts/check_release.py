"""Run required release milestones. Never replaces the owner's app or publishes."""
import argparse,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.check_project import checkpoint,fingerprint
from scripts.verify_package import verify
from scripts.release_gate import seal

def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    p.add_argument('--stage',type=Path,default=ROOT/'build/distribution-stage/KineticCut/KineticCut.exe')
    p.add_argument('--installed',type=Path,default=ROOT/'dist/KineticCut/KineticCut.exe')
    p.add_argument('--compiler',type=Path,default=ROOT/'build/tools/inno/ISCC.exe');p.add_argument('--offline-fixture',type=Path)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if a.offline_fixture:os.environ['KINETIC_OFFLINE_VOICE_FIXTURE']=str(a.offline_fixture.resolve())
    if not checkpoint(out/'source')['passed']:raise RuntimeError('Source checkpoint failed')
    for kind,exe in [('staged',a.stage),('installed',a.installed)]:
        if not verify(exe,out/kind,kind)['passed']:raise RuntimeError(kind+' application failed verification')
    subprocess.run([sys.executable,str(ROOT/'scripts/verify_installer.py'),str(out/'installer'),'--compiler',str(a.compiler)],cwd=ROOT,check=True)
    milestones={k:out/k/'report.json' for k in ('source','staged','installed','installer')}
    seal(out/'release-gate.json',milestones)
    print('All local release milestones passed. Publication still requires owner authorization.',flush=True)
if __name__=='__main__':main()
