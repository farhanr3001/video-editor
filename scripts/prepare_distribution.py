"""Prepare the core and exact downloadable pack metadata; no personal data."""
import argparse, hashlib, json, shutil, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from kinetic_cut.version import VERSION, REPOSITORY

def pack(key,name,source,release):
    target=release/f'KineticCut-{key}-{VERSION}.zip'; installed=0
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(source.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path,path.relative_to(source).as_posix()); installed+=path.stat().st_size
    digest=hashlib.sha256()
    with target.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return dict(name=name,installed_bytes=installed,download_bytes=target.stat().st_size,sha256=digest.hexdigest(),
                url=f'https://github.com/{REPOSITORY}/releases/download/v{VERSION}/{target.name}')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',type=Path,required=True);parser.add_argument('--ffmpeg-bin',type=Path,required=True);args=parser.parse_args()
    inputs=ROOT/'build/distribution-inputs';assets=inputs/'assets';assets.mkdir(parents=True,exist_ok=True)
    for path in (ROOT/'assets').iterdir():
        if path.name in ('phone-tools','downloads','__pycache__'):continue
        if path.is_dir():shutil.copytree(path,assets/path.name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        else:shutil.copy2(path,assets/path.name)
    shutil.copytree(args.model,assets/'caption-models/base.en',dirs_exist_ok=True)
    tools=assets/'tools';tools.mkdir(exist_ok=True)
    for name in ('ffmpeg.exe','ffprobe.exe'):shutil.copy2(args.ffmpeg_bin/name,tools/name)
    for name in ('LICENSE','README.txt'):
        source=args.ffmpeg_bin.parent/name
        if source.is_file():shutil.copy2(source,tools/name)
    release=ROOT/'release';release.mkdir(exist_ok=True)
    specs=[('android','Android mirroring',ROOT/'assets/phone-tools/scrcpy-win64-v4.1'),('iphone','iPhone mirroring',ROOT/'assets/phone-tools/uxplay'),('vision','Face / background tools',inputs/'components/vision-v1'),('vocals','Vocal separation',inputs/'components/vocal-only-v1')]
    metadata={}
    for key,name,source in specs:
        if not source.is_dir():raise RuntimeError(f'Missing prepared component: {source}')
        print('Packing '+name,flush=True);metadata[key]=pack(key,name,source,release)
    (assets/'components.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    (release/'components.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata,indent=2),flush=True)

if __name__=='__main__':main()
