"""Publish reviewed release files; credentials stay in the developer's credential helper."""
import argparse,hashlib,json,os,subprocess,sys,urllib.request
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
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    token=credentials()
    def request(url,data=None,method=None,content_type='application/json'):
        headers={'Authorization':'Bearer '+token,'User-Agent':'KineticCut-ReleasePublisher',
                 'Accept':'application/vnd.github+json','Content-Type':content_type}
        if isinstance(data,dict):data=json.dumps(data).encode()
        return json.load(urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers,method=method),timeout=120))
    releases=request(f'https://api.github.com/repos/{REPOSITORY}/releases')
    release=next((r for r in releases if r['tag_name']=='v'+VERSION),None)
    notes=(ROOT/'RELEASE_NOTES.md').read_text(encoding='utf-8')
    if release is None:
        release=request(f'https://api.github.com/repos/{REPOSITORY}/releases',dict(tag_name='v'+VERSION,target_commitish='main',name='Kinetic Cut '+VERSION,body=notes,draft=True))
    files=[ROOT/f'release/KineticCut-Setup-{VERSION}.exe',*(ROOT/'release').glob(f'KineticCut-*-{VERSION}.zip'),ROOT/'release/components.json',ROOT/'release/build-report.json']
    existing={asset['name']:asset for asset in request(release['assets_url'])}
    for file in files:
        with file.open('rb') as stream:
            hasher=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024*1024),b''):hasher.update(chunk)
            digest='sha256:'+hasher.hexdigest()
        if file.name in existing:
            if existing[file.name]['size']!=file.stat().st_size or existing[file.name].get('digest')!=digest:
                raise RuntimeError('An asset with this name already exists with different or unverified content: '+file.name)
            print('Already uploaded '+file.name,flush=True);continue
        print('Uploading '+file.name,flush=True)
        upload=release['upload_url'].split('{')[0]+'?name='+file.name
        # urllib streams file objects with an explicit Content-Length.
        with file.open('rb') as stream:
            headers={'Authorization':'Bearer '+token,'User-Agent':'KineticCut-ReleasePublisher','Content-Type':'application/octet-stream','Content-Length':str(file.stat().st_size)}
            asset=json.load(urllib.request.urlopen(urllib.request.Request(upload,data=stream,headers=headers,method='POST'),timeout=180))
        if asset.get('digest')!=digest:raise RuntimeError('GitHub upload digest did not match: '+file.name)
        print(json.dumps({k:asset.get(k) for k in ('name','size','digest')}),flush=True)
    if args.publish:release=request(release['url'],dict(draft=False,body=notes),method='PATCH')
    print(json.dumps(dict(url=release['html_url'],draft=release['draft'])),flush=True)

if __name__=='__main__':main()
