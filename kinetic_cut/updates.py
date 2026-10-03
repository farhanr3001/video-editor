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


def parse_release(data, current=VERSION):
    if data.get("draft") or data.get("prerelease"):
        return None
    remote = str(data.get("tag_name", ""))
    if version_tuple(remote) <= version_tuple(current):
        return None
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
                   str(data.get("body", ""))[:12000])


def check(current=VERSION, opener=urllib.request.urlopen):
    request = urllib.request.Request(API, headers={"User-Agent": f"KineticCut/{VERSION}",
                                                    "Accept": "application/vnd.github+json"})
    try:
        with opener(request, timeout=12) as response:
            raw = response.read(MAX_METADATA + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(f"Update server returned HTTP {error.code}. Please try again later.") from error
    if len(raw) > MAX_METADATA:
        raise ValueError("Update information is too large")
    return parse_release(json.loads(raw), current)


def download(release, directory, cancel, progress=lambda *_: None,
             opener=urllib.request.urlopen):
    version_tuple(release.version)
    if not trusted_download(release.url) or not re.fullmatch(r"[a-f0-9]{64}", release.sha256):
        raise ValueError("Invalid release download")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"KineticCut-Setup-{release.version}.exe"
    pending = target.with_suffix(".partial")
    digest = hashlib.sha256(); done = 0
    try:
        request = urllib.request.Request(release.url, headers={"User-Agent": f"KineticCut/{VERSION}"})
        with opener(request, timeout=30) as response, pending.open("wb") as stream:
            while True:
                if cancel.is_set():
                    raise InterruptedError("Update download cancelled.")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                done += len(chunk)
                if done > release.size:
                    raise ValueError("Installer exceeds its published size")
                stream.write(chunk); digest.update(chunk)
                progress(done, release.size)
        if cancel.is_set():
            raise InterruptedError("Update download cancelled.")
        if done != release.size or digest.hexdigest() != release.sha256:
            raise ValueError("Installer verification failed; no update was launched.")
        pending.replace(target)
        return target
    finally:
        pending.unlink(missing_ok=True)
