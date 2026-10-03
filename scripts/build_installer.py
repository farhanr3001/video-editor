"""Compile Inno installer with accurate sizes from the staged application."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kinetic_cut.version import VERSION

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',type=Path,required=True);args=parser.parse_args()
    bundle=ROOT/'build/distribution-stage/KineticCut';metadata=json.loads((bundle/'_internal/assets/components.json').read_text());core=sum(p.stat().st_size for p in bundle.rglob('*') if p.is_file())
    lines=[f'#define AppVersion "{VERSION}"',f'#define CoreBytes {core}']
    for key,prefix in [('android','Android'),('iphone','IPhone'),('vision','Vision'),('vocals','Vocals')]:
        item=metadata[key];lines.extend([f'#define {prefix}Bytes {item["installed_bytes"]}',f'#define {prefix}Download {item["download_bytes"]}',f'#define {prefix}MB "{item["installed_bytes"]/1e6:.1f}"'])
    (ROOT/'installer/sizes.iss').write_text('\n'.join(lines)+'\n')
    result=subprocess.run([str(args.compiler),str(ROOT/'installer/KineticCut.iss')],cwd=ROOT)
    if result.returncode:return result.returncode
    (ROOT/'release/build-report.json').write_text(json.dumps(dict(version=VERSION,core_installed_bytes=core,installer_bytes=(ROOT/f'release/KineticCut-Setup-{VERSION}.exe').stat().st_size,components=metadata),indent=2));return 0

if __name__=='__main__':sys.exit(main())
