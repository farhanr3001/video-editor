"""Publish reviewed release files; credentials stay in the developer's credential helper."""
import argparse,hashlib,json,os,subprocess,sys,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from kinetic_cut.version import VERSION,REPOSITORY

def credentials():
    if os.environ.get('GITHUB_TOKEN'):return os.environ['GITHUB_TOKEN']
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    result=subprocess.run(['git','-c','credential.interactive=never','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,env=env)
    values=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
    if not values.get('password'):raise RuntimeError('Sign in to GitHub with Git Credential Manager before publishing.')
    return values['password']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true')
    parser.add_argument('--installer-update', action='store_true', help='Use the full installer update channel when native installer ownership/code must change.')
    parser.add_argument('--gate',type=Path,help='Source-bound release_gate.py evidence (required for publication).')
    parser.add_argument('--preview',action='store_true',help='Publish only to the opt-in Preview channel.')
    args=parser.parse_args()
    if not args.gate:raise RuntimeError('Release uploads require --gate evidence for the current source and all release milestones.')
    from scripts.release_gate import validate
    validate(args.gate)
    token=credentials()
    def request(url,data=None,method=None,content_type='application/json'):
        headers={'Authorization':'Bearer '+token,'User-Agent':'KineticCut-ReleasePublisher',
                 'Accept':'application/vnd.github+json','Content-Type':content_type}
        if isinstance(data,dict):data=json.dumps(data).encode()
        return json.load(urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers,method=method),timeout=120))
    releases=request(f'https://api.github.com/repos/{REPOSITORY}/releases')
    release=next((r for r in releases if r['tag_name']=='v'+VERSION),None)
    notes_path=ROOT/'RELEASE_NOTES.md' # Maintainer's local release notes, excluded from source history.
    notes=notes_path.read_text(encoding='utf-8') if notes_path.is_file() else f'Kinetic Cut {VERSION}. See the repository README for details.'
    if release is None:
        release=request(f'https://api.github.com/repos/{REPOSITORY}/releases',dict(tag_name='v'+VERSION,target_commitish='main',name='Kinetic Cut '+VERSION,body=notes,draft=True,prerelease=args.preview))
    files=[ROOT/f'release/KineticCut-Setup-{VERSION}.exe',ROOT/f'release/KineticCut-FullSetup-{VERSION}.exe',
           ROOT/f'release/KineticCut-Update-{VERSION}.json',ROOT/'release/KineticCut-Baseline-1.1.0.json',
           *(ROOT/'release/update-payloads').glob('KineticCut-Part-*.zip'),ROOT/'release/build-report.json']
    if args.installer_update:
        # Existing updaters prefer an exact-name manifest. Omit it for this
        # checkpoint so they run Setup, replacing the native uninstaller too.
        from scripts.release_gate import sha
        if sha(ROOT/f'release/KineticCut-FullSetup-{VERSION}.exe')!=sha(ROOT/f'release/KineticCut-Setup-{VERSION}.exe'):raise RuntimeError('Prepare the installer update channel before sealing release evidence.')
        files=[p for p in files if p.name!=f'KineticCut-Update-{VERSION}.json']
        inventory=ROOT/f'release/KineticCut-Inventory-{VERSION}.json'
        if not inventory.is_file() or sha(inventory)!=sha(ROOT/f'release/KineticCut-Update-{VERSION}.json'):raise RuntimeError('Prepare the installer inventory before sealing release evidence.')
        files.extend([inventory,ROOT/'release/components.json'])
        report_path=ROOT/'release/build-report.json'
        report=json.loads(report_path.read_text(encoding='utf-8'))
        if report.get('update_channel')!='full-installer' or report.get('migration_bytes')!=(ROOT/f'release/KineticCut-Setup-{VERSION}.exe').stat().st_size:raise RuntimeError('Installer channel report was not prepared before release verification.')
    assets=[];page=1
    while True:
        batch=request(release['assets_url']+f'?per_page=100&page={page}');assets.extend(batch)
        if len(batch)<100:break
        page+=1
    existing={asset['name']:asset for asset in assets}
    if args.installer_update and f'KineticCut-Update-{VERSION}.json' in existing:
        raise RuntimeError('An incremental-channel manifest already exists; do not publish an installer-only checkpoint over it.')
    def upload_file(file):
        with file.open('rb') as stream:
            hasher=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b''):hasher.update(chunk)
            digest='sha256:'+hasher.hexdigest()
        if file.name in existing:
            if existing[file.name]['size']!=file.stat().st_size or existing[file.name].get('digest')!=digest:
                raise RuntimeError('An asset with this name already exists with different or unverified content: '+file.name)
            print('Already uploaded '+file.name,flush=True);return
        print('Uploading '+file.name,flush=True)
        upload=release['upload_url'].split('{')[0]+'?name='+file.name
        # urllib streams file objects with an explicit Content-Length.
        with file.open('rb') as stream:
            headers={'Authorization':'Bearer '+token,'User-Agent':'KineticCut-ReleasePublisher','Content-Type':'application/octet-stream','Content-Length':str(file.stat().st_size)}
            asset=json.load(urllib.request.urlopen(urllib.request.Request(upload,data=stream,headers=headers,method='POST'),timeout=180))
        if asset.get('digest')!=digest:raise RuntimeError('GitHub upload digest did not match: '+file.name)
        print(json.dumps({k:asset.get(k) for k in ('name','size','digest')}),flush=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(upload_file, files))
    if args.publish:release=request(release['url'],dict(draft=False,body=notes,prerelease=args.preview),method='PATCH')
    print(json.dumps(dict(url=release['html_url'],draft=release['draft'])),flush=True)

if __name__=='__main__':main()
