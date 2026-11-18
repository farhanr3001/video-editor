"""Install only the immutable, hash-verified FFmpeg tools used by public 1.1.32."""
import hashlib
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOOLS={
    'ffmpeg.exe':dict(sha256='b90225987bdd042cca09a1efb5e34e9848f2d1dbf5fbcd388753a44145522997',size=87429632,
        bundle='de56298cbfcc765c16040ed186cefd7382f33d85d51b2538205b644e6717a3b5',bundle_size=31275332),
    'ffprobe.exe':dict(sha256='05e8fa639450f8191635192871ae37a3ec3e4638fa12f3b7d49c6522ba16a8ed',size=87291904,
        bundle='b657cd20d809ef78206ab4428f79fc9948cdefa369b47dc211029302d5463661',bundle_size=31205032),
}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def bounded_copy(source,target,size):
    written=0
    while chunk:=source.read(min(1024*1024,size-written+1)):
        written+=len(chunk)
        if written>size:raise ValueError('CI tool exceeds its pinned size')
        target.write(chunk)
    if written!=size:raise ValueError('CI tool download was incomplete')


def install(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for name,expected in TOOLS.items():
        target=destination/name
        if target.is_file() and target.stat().st_size==expected['size'] and digest(target)==expected['sha256']:continue
        with tempfile.TemporaryDirectory(prefix='ci-tool-',dir=destination) as directory:
            base=Path(directory);archive=base/'payload.zip'
            url='https://github.com/farhanr3001/video-editor/releases/download/v1.1.1/KineticCut-Part-'+expected['bundle']+'.zip'
            request=urllib.request.Request(url,headers={'User-Agent':'KineticCut-CI'})
            with urllib.request.urlopen(request,timeout=120) as response,archive.open('wb') as output:
                bounded_copy(response,output,expected['bundle_size'])
            if digest(archive)!=expected['bundle']:raise ValueError('CI tool payload hash mismatch')
            pending=base/name
            with zipfile.ZipFile(archive) as bundle:
                entry=bundle.getinfo('_internal/assets/tools/'+name)
                if entry.file_size!=expected['size']:raise ValueError('Unexpected CI tool size')
                with bundle.open(entry) as source,pending.open('wb') as output:bounded_copy(source,output,expected['size'])
            if digest(pending)!=expected['sha256']:raise ValueError('CI tool hash mismatch')
            os.replace(pending,target)
        print('Verified public FFmpeg 7.1.1 tool: '+name,flush=True)


if __name__=='__main__':install(ROOT/'build/distribution-stage/KineticCut/_internal/assets/tools')
