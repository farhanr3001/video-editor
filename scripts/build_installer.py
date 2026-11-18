"""Compile Inno installer with accurate sizes from the staged application."""
import argparse,json,subprocess,sys,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kinetic_cut.version import VERSION

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);args=parser.parse_args()
    from scripts.check_project import fingerprint
    from scripts.release_gate import sha
    from PyInstaller.archive.readers import CArchiveReader
    source=fingerprint()
    helper=CArchiveReader(str(ROOT/'build/distribution-stage/KineticCut/KineticCutUpdater.exe')).open_embedded_archive('PYZ.pyz')
    version_code=helper.extract('kinetic_cut.version')
    if version_code!=compile((ROOT/'kinetic_cut/version.py').read_bytes(),version_code.co_filename,'exec'):
        raise RuntimeError('Rebuild the independent updater for the current application version before making installers.')
    native_compiler=shutil.which('g++') or 'C:/msys64/ucrt64/bin/g++.exe'
    native_env=dict(os.environ,PATH=str(Path(native_compiler).parent)+os.pathsep+os.environ.get('PATH',''))
    subprocess.run([native_compiler,'-municode','-static','-O2','-Wl,--no-insert-timestamp',str(ROOT/'scripts/cleanup_phone_helpers.cpp'),'-ladvapi32','-o',str(ROOT/'build/cleanup_phone_helpers.exe')],env=native_env,check=True)
    subprocess.run([str(ROOT/'build/cleanup_phone_helpers.exe'),'--selftest'],check=True)
    bundle=ROOT/'build/distribution-stage/KineticCut';metadata=json.loads((bundle/'_internal/assets/components.json').read_text());core=sum(p.stat().st_size for p in bundle.rglob('*') if p.is_file())
    lines=[f'#define AppVersion "{VERSION}"',f'#define CoreBytes {core}']
    for key,prefix in [('vision','Vision'),('vocals','Vocals')]:
        item=metadata[key];lines.extend([f'#define {prefix}Bytes {item["installed_bytes"]}',f'#define {prefix}Download {item["download_bytes"]}',f'#define {prefix}MB "{item["installed_bytes"]/1e6:.1f}"'])
    (ROOT/'installer/sizes.iss').write_text('\n'.join(lines)+'\n')
    for defines in ([], ['/DMigration']):
        result=subprocess.run([str(args.compiler),*defines,str(ROOT/'installer/KineticCut.iss')],cwd=ROOT)
        if result.returncode:return result.returncode
    if fingerprint()!=source:raise RuntimeError('Source changed while building installers; verify the final build again.')
    (ROOT/'release/build-report.json').write_text(json.dumps(dict(version=VERSION,source_fingerprint=source,
        stage_exe_sha256=sha(bundle/'KineticCut.exe'),full_setup_sha256=sha(ROOT/f'release/KineticCut-FullSetup-{VERSION}.exe'),
        setup_sha256=sha(ROOT/f'release/KineticCut-Setup-{VERSION}.exe'),core_installed_bytes=core,
        installer_bytes=(ROOT/f'release/KineticCut-FullSetup-{VERSION}.exe').stat().st_size,
        migration_bytes=(ROOT/f'release/KineticCut-Setup-{VERSION}.exe').stat().st_size,components=metadata),indent=2));return 0

if __name__=='__main__':sys.exit(main())
