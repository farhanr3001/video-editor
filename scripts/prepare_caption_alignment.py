"""Reproducible build input; no alignment downloads occur during captioning."""
import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as source:
        for data in iter(lambda:source.read(1024*1024),b''):result.update(data)
    return result.hexdigest()


def prepare(assets):
    root=Path(__file__).resolve().parents[1]
    source=root/'assets/caption-alignment';metadata=json.loads((source/'source.json').read_text())
    target=Path(assets)/'caption-alignment';target.mkdir(parents=True,exist_ok=True)
    for name in ('source.json','vocab.json'):
        if (source/name).resolve()!=(target/name).resolve():shutil.copy2(source/name,target/name)
    model=target/'model.onnx'
    def valid(path):return path.is_file() and path.stat().st_size==metadata['size'] and digest(path)==metadata['sha256']
    if valid(model):return
    for candidate in (source/'model.onnx',root/'dist/KineticCut/_internal/assets/caption-alignment/model.onnx'):
        if candidate.resolve()!=model.resolve() and valid(candidate):shutil.copy2(candidate,model);return
    url=f"https://huggingface.co/{metadata['repository']}/resolve/{metadata['revision']}/{metadata['file']}"
    with tempfile.TemporaryDirectory(prefix='caption-build-',dir=target) as temporary:
        pending=Path(temporary)/'model.onnx'
        with urllib.request.urlopen(url,timeout=60) as response,pending.open('wb') as output:
            total=0
            while data:=response.read(1024*1024):
                total+=len(data)
                if total>metadata['size']:raise ValueError('Caption alignment download exceeded its pinned size')
                output.write(data)
        if not valid(pending):raise ValueError('Caption alignment download failed SHA-256 validation')
        pending.replace(model)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--assets',default='assets')
    prepare(parser.parse_args().assets)
