"""Reusable staged/installed native gate. Does not install, publish or open owner data."""
import argparse,json,marshal,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.check_project import fingerprint
from scripts.private_desktop import run
from scripts.release_gate import sha

def verify(exe,output,kind):
    from PyInstaller.archive.readers import CArchiveReader
    from kinetic_cut import update_files as f
    exe=Path(exe).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True);before=fingerprint()
    archive=CArchiveReader(str(exe));pyz=archive.open_embedded_archive('PYZ.pyz');modules=0
    for p in (ROOT/'kinetic_cut').glob('*.py'):
        name='kinetic_cut' if p.stem=='__init__' else 'kinetic_cut.'+p.stem
        if name not in pyz.toc:
            if p.stem=='delivery':continue
            raise ValueError('Package is missing '+name)
        if pyz.extract(name)!=compile(p.read_bytes(),'kinetic_cut/'+p.name,'exec'):raise ValueError('Package source differs: '+name)
        modules+=1
    if marshal.loads(archive.extract('main'))!=compile((ROOT/'main.py').read_bytes(),'main.py','exec'):raise ValueError('Package entry point differs')
    manifest=json.loads((exe.parent/f.MANIFEST).read_text());f.verify_install(exe.parent,manifest)
    cases={}
    for case,flag in [('reliability','--reliability-selftest'),('startup','--startup-windows-selftest')]:
        path=output/case
        code=run([exe,flag,path],output/(case+'.log'),ROOT,timeout=300)
        report=json.loads((path/'report.json').read_text()) if (path/'report.json').exists() else {}
        cases[case]=dict(passed=code==0 and report.get('passed') is True,code=code,report=str(path/'report.json'))
    result=dict(passed=all(row['passed'] for row in cases.values()) and before==fingerprint(),kind=kind,source_fingerprint=before,exe=str(exe),exe_sha256=sha(exe),modules=modules,managed_files=len(manifest['files']),cases=cases)
    (output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('exe',type=Path);p.add_argument('output',type=Path);p.add_argument('--kind',choices=['staged','installed'],required=True);a=p.parse_args()
    sys.exit(0 if verify(a.exe,a.output,a.kind)['passed'] else 1)
