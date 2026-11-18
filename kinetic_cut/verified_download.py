"""Bounded, resumable downloads; only a complete SHA-256 match is published."""
import hashlib
import json
import re
import http.client
import os,time
from contextlib import contextmanager
import urllib.error
import urllib.request
from pathlib import Path


@contextmanager
def file_lock(path,cancel,timeout=120):
    """Coordinate editor processes without ever waiting on the GUI thread."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():raise ValueError('Download lock cannot be a link')
    with path.open('a+b') as stream:
        if stream.tell()==0:stream.write(b'0');stream.flush()
        deadline=time.monotonic()+timeout
        while True:
            if cancel.is_set():raise InterruptedError('Download paused')
            try:
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except (OSError,BlockingIOError):
                if time.monotonic()>=deadline:raise TimeoutError('Another Kinetic Cut window is still downloading this file')
                cancel.wait(.1)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def fetch(url,sha256,size,destination,cancel,progress=lambda *_:None,opener=urllib.request.urlopen,attempts=3):
    destination=Path(destination)
    with file_lock(destination.with_suffix(destination.suffix+'.lock'),cancel):
        return _fetch(url,sha256,size,destination,cancel,progress,opener,attempts)

def _fetch(url, sha256, size, destination, cancel, progress=lambda *_:None,
          opener=urllib.request.urlopen, attempts=3):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    if not re.fullmatch('[a-f0-9]{64}',sha256) or not 0<size<=4*1024**3:raise ValueError('Invalid download inventory')
    partial=destination.with_suffix(destination.suffix+'.partial')
    metadata=partial.with_suffix(partial.suffix+'.json')
    identity=dict(url=url,sha256=sha256,size=size)
    if any(p.is_symlink() for p in (destination,partial,metadata)):raise ValueError('Download storage cannot be a link')
    def check():
        if cancel.is_set():raise InterruptedError('Download paused. You can continue it next time.')
    def checksum(path):
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):check();digest.update(chunk)
        return digest
    def discard():
        partial.unlink(missing_ok=True);metadata.unlink(missing_ok=True)
    check()
    if destination.is_file() and destination.stat().st_size==size and checksum(destination).hexdigest()==sha256:
        progress(size,size);return destination
    try:state=json.loads(metadata.read_text(encoding='utf-8'))
    except (ValueError,OSError):state={}
    if any(state.get(k)!=v for k,v in identity.items()) or partial.is_symlink() or (partial.exists() and partial.stat().st_size>size):
        discard();state=identity.copy()
    for attempt in range(attempts):
        check();offset=partial.stat().st_size if partial.exists() else 0
        digest=checksum(partial) if offset else hashlib.sha256()
        if offset==size:
            if digest.hexdigest()!=sha256:discard();raise ValueError('Download verification failed. Please retry.')
            check();partial.replace(destination);metadata.unlink(missing_ok=True);progress(size,size);return destination
        headers={'User-Agent':'KineticCut-VerifiedDownload','Accept-Encoding':'identity'}
        if offset:
            headers['Range']=f'bytes={offset}-'
            if state.get('validator'):headers['If-Range']=state['validator']
        try:
            with opener(urllib.request.Request(url,headers=headers),timeout=30) as response:
                status=getattr(response,'status',None) or getattr(response,'getcode',lambda:200)() or 200
                response_headers=getattr(response,'headers',{})
                if offset and status==200:offset=0;digest=hashlib.sha256()
                elif status==206:
                    match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response_headers.get('Content-Range',''))
                    if not match or int(match[1])!=offset or int(match[3])!=size or not offset<=int(match[2])<size:
                        discard();raise ValueError('The download server returned an invalid range.')
                elif status!=200:raise ValueError('Unexpected download response')
                validator=response_headers.get('ETag','')
                if validator.startswith('W/'):validator=''
                state={**identity,'validator':validator or response_headers.get('Last-Modified','')}
                metadata.write_text(json.dumps(state),encoding='utf-8')
                done=offset;progress(done,size)
                with partial.open('ab' if offset else 'wb') as stream:
                    while True:
                        check();chunk=response.read(256*1024)
                        if not chunk:break
                        done+=len(chunk)
                        if done>size:raise ValueError('Download exceeds its published size')
                        stream.write(chunk);digest.update(chunk);progress(done,size)
            if done!=size:raise ConnectionError('The download was interrupted')
            if digest.hexdigest()!=sha256:
                discard();raise ValueError('Download verification failed. Please retry.')
            check();partial.replace(destination);metadata.unlink(missing_ok=True);return destination
        except urllib.error.HTTPError as error:
            if error.code==416:discard();state=identity.copy()
            elif error.code not in (408,429,500,502,503,504):raise
            if attempt+1==attempts:raise
        except (urllib.error.URLError,ConnectionError,TimeoutError,OSError,http.client.HTTPException):
            if attempt+1==attempts:raise
        except ValueError:
            discard();raise
        check()
        if cancel.wait(.25*(attempt+1)):check()
    raise RuntimeError('Download did not finish')
