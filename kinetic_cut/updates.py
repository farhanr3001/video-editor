"""Bounded GitHub release discovery and verified, cancellable installer download."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .version import VERSION, REPOSITORY

API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_METADATA = 1024 * 1024


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        raise ValueError("Unsupported release version")
    return tuple(int(part) for part in match.groups())


def trusted_download(url):
    parsed = urllib.parse.urlsplit(url)
    prefix = f"/{REPOSITORY}/releases/download/"
    return (parsed.scheme == "https" and parsed.netloc == "github.com"
            and parsed.path.startswith(prefix) and not parsed.query and not parsed.fragment)


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str
    size: int
    notes: str = ""
    manifest: dict | None = None
    selection: dict | None = None
    incremental: bool = False
    preview: bool = False


def parse_release(data, current=VERSION, *, allow_preview=False):
    if data.get("draft") or data.get("prerelease") and not allow_preview:
        return None
    remote = str(data.get("tag_name", ""))
    if version_tuple(remote) <= version_tuple(current):
        return None
    name = f"KineticCut-Update-{remote.lstrip('v')}.json"
    asset = next((a for a in data.get("assets", []) if a.get("name") == name), None)
    incremental = asset is not None
    if not asset:
        name = f"KineticCut-Setup-{remote.lstrip('v')}.exe"
        asset = next((a for a in data.get("assets", []) if a.get("name") == name), None)
    if not asset:
        raise ValueError("The new release does not contain a Windows installer yet.")
    digest = str(asset.get("digest", ""))
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
        raise ValueError("The release installer has no SHA-256 verification information.")
    url = str(asset.get("browser_download_url", ""))
    if not trusted_download(url):
        raise ValueError("The release installer is outside the configured update channel.")
    size = int(asset.get("size", 0))
    if size <= 0 or size > 4 * 1024**3:
        raise ValueError("Invalid installer size")
    return Release(remote.lstrip("v"), url, digest.split(":", 1)[1].lower(), size,
                   str(data.get("body", ""))[:12000], incremental=incremental,preview=bool(data.get('prerelease')))


def check(current=VERSION, opener=urllib.request.urlopen, *, channel='stable'):
    if channel not in ('stable','preview'):raise ValueError('Unknown update channel')
    request = urllib.request.Request(API if channel=='stable' else API.rsplit('/',1)[0]+'?per_page=5', headers={"User-Agent": f"KineticCut/{VERSION}",
                                                    "Accept": "application/vnd.github+json"})
    try:
        with opener(request, timeout=12) as response:
            raw = response.read(MAX_METADATA*(8 if channel=='preview' else 1) + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(f"Update server returned HTTP {error.code}. Please try again later.") from error
    if len(raw) > MAX_METADATA*(8 if channel=='preview' else 1):
        raise ValueError("Update information is too large")
    data=json.loads(raw)
    if channel=='preview':
        if not isinstance(data,list):raise ValueError('Invalid release list')
        releases=[]
        for item in data:
            try:
                candidate=parse_release(item,current,allow_preview=True)
                if candidate:releases.append(candidate)
            except ValueError:continue
        release=max(releases,key=lambda r:version_tuple(r.version),default=None)
    else:release = parse_release(data, current)
    if release and release.incremental:
        from dataclasses import replace
        from .update_files import MAX_MANIFEST, validate_manifest
        if release.size > MAX_MANIFEST:raise ValueError('Update manifest exceeds size limit')
        with opener(urllib.request.Request(release.url, headers={'User-Agent':'KineticCut-Updater'}), timeout=12) as response:
            raw = response.read(release.size + 1)
        if len(raw) != release.size or hashlib.sha256(raw).hexdigest() != release.sha256:
            raise ValueError('Update manifest verification failed')
        release = replace(release, manifest=validate_manifest(json.loads(raw), release.version))
    return release


def repair_release(current=VERSION,opener=urllib.request.urlopen):
    """Read the official inventory for this exact version, independently of local files."""
    version_tuple(current)
    request=urllib.request.Request(API.rsplit('/',1)[0]+'/tags/v'+current,headers={'User-Agent':'KineticCut-Repair'})
    with opener(request,timeout=12) as response:raw=response.read(MAX_METADATA+1)
    if len(raw)>MAX_METADATA:raise ValueError('Repair information exceeds its size limit')
    data=json.loads(raw)
    if data.get('draft') or data.get('tag_name')!='v'+current:raise ValueError('No official repair for this version')
    assets=data.get('assets',[])
    asset=next((a for name in (f'KineticCut-Update-{current}.json',f'KineticCut-Inventory-{current}.json') for a in assets if a.get('name')==name),None)
    if not asset:raise RuntimeError('Repair files are not available for this version. Check for an application update.')
    from .update_files import MAX_MANIFEST,validate_manifest
    sha=str(asset.get('digest','')).removeprefix('sha256:');size=asset.get('size',0);url=asset.get('browser_download_url','')
    if not trusted_download(url) or not re.fullmatch('[a-f0-9]{64}',sha) or not 0<size<=MAX_MANIFEST:raise ValueError('Invalid repair inventory')
    with opener(urllib.request.Request(url,headers={'User-Agent':'KineticCut-Repair'}),timeout=12) as response:body=response.read(size+1)
    if len(body)!=size or hashlib.sha256(body).hexdigest()!=sha:raise ValueError('Repair verification failed')
    return Release(current,url,sha,size,manifest=validate_manifest(json.loads(body),current),incremental=True)

def repair_installer(current=VERSION,opener=urllib.request.urlopen):
    version_tuple(current)
    request=urllib.request.Request(API.rsplit('/',1)[0]+'/tags/v'+current,headers={'User-Agent':'KineticCut-Repair'})
    with opener(request,timeout=12) as response:raw=response.read(MAX_METADATA+1)
    if len(raw)>MAX_METADATA:raise ValueError('Repair information exceeds its size limit')
    data=json.loads(raw)
    if data.get('tag_name')!='v'+current or data.get('draft'):raise ValueError('No official repair for this version')
    asset=next((a for a in data.get('assets',[]) if a.get('name')==f'KineticCut-FullSetup-{current}.exe'),None)
    if not asset:raise RuntimeError('The complete repair package is not available')
    return parse_release(dict(data,assets=[dict(asset,name=f'KineticCut-Setup-{current}.exe')]),current='0.0.0',allow_preview=True)


def download(release, directory, cancel, progress=lambda *_: None,
             opener=urllib.request.urlopen):
    version_tuple(release.version)
    if not trusted_download(release.url) or not re.fullmatch(r"[a-f0-9]{64}", release.sha256):
        raise ValueError("Invalid release download")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"KineticCut-Setup-{release.version}.exe"
    from .verified_download import fetch
    return fetch(release.url,release.sha256,release.size,target,cancel,progress,opener)
