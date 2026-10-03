"""Shared app/installer downloads into dedicated, uninstallable component roots."""
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from .updates import trusted_download

ROOTS = {"android": "phone-android-v1", "iphone": "phone-iphone-v1",
         "vision": "vision-v1", "vocals": "vocal-only-v1"}

def effect_component(name):
    from .vision_effects import NAMES
    return 'vision' if name in NAMES else 'vocals' if name == 'Vocal Only' else None


def available(key, settings=None):
    if key in ('android', 'iphone'):
        from .phone_process import tool_path
        return bool(tool_path(settings or {}, 'scrcpy' if key == 'android' else 'uxplay-windows'))
    return installed(key)


def remove(key):
    root = component_root(key)
    if root.is_symlink() or root.resolve().parent != root.parent.resolve():
        raise ValueError('Unsafe component storage path')
    from .config import DATA_DIR
    from .uninstall_data import referenced_paths
    power = DATA_DIR / 'powerbins.json'
    if power.is_file():
        references = referenced_paths(json.loads(power.read_text(encoding='utf-8')))
        if any(path.is_relative_to(root.resolve()) for path in references):
            raise RuntimeError('This component contains a Power Bin source. Collect that media before removing it.')
    if root.exists():shutil.rmtree(root)


def manifest():
    from .icons import resource_path
    path = resource_path("assets", "components.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def component_root(key):
    from .config import DATA_DIR
    return DATA_DIR / "components" / ROOTS[key]


def installed(key):
    root = component_root(key)
    if key == "vision":
        from .vision_component import ready
        return ready(root)
    if key == "vocals":
        from .vocal_component import ready
        return ready(root)
    marker = root / "pack-ready.json"
    exe = root / ("scrcpy.exe" if key == "android" else "uxplay-windows.exe")
    return marker.is_file() and exe.is_file()


def extract(archive, destination, cancel):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as source:
        total = 0
        for item in source.infolist():
            path = destination / item.filename
            if (not path.resolve().is_relative_to(destination) or "\\" in item.filename
                    or ":" in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe component archive path")
            total += item.file_size
            if total > 8 * 1024**3:
                raise ValueError("Component archive exceeds its extraction limit")
        for item in source.infolist():
            if cancel.is_set():
                raise InterruptedError("Component download cancelled")
            source.extract(item, destination)


def install(key, progress, cancel, local_source=None):
    if installed(key):
        progress((100, "Already installed")); return component_root(key)
    metadata = manifest().get(key)
    if metadata:
        from .updates import Release, download
        from .version import VERSION
        if not trusted_download(metadata["url"]):
            raise ValueError("Component download is outside the release channel")
        root = component_root(key); root.parent.mkdir(parents=True, exist_ok=True)
        required = metadata["installed_bytes"] + metadata["download_bytes"] + 128 * 1024**2
        if shutil.disk_usage(root.parent).free < required:
            raise RuntimeError("Not enough free space for this optional component")
        with tempfile.TemporaryDirectory(prefix=f"{key}-install-", dir=root.parent) as temp:
            temp = Path(temp)
            release = Release(VERSION, metadata["url"], metadata["sha256"], metadata["download_bytes"])
            local = None
            if local_source:
                from urllib.parse import urlsplit
                candidate = Path(local_source) / Path(urlsplit(metadata['url']).path).name
                if candidate.is_file():local = candidate
            if local:
                import hashlib
                digest = hashlib.sha256(); count = 0
                with local.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):
                        if cancel.is_set():raise InterruptedError('Component installation cancelled')
                        count += len(chunk); digest.update(chunk)
                        progress((min(85,round(count/metadata['download_bytes']*85)), 'Verifying '+metadata['name']))
                if digest.hexdigest()!=metadata['sha256'] or count!=metadata['download_bytes']:
                    raise ValueError('Local component archive verification failed')
                archive = local
            else:
                archive = download(release, temp, cancel,
                                   lambda done, total: progress((round(done/total*85), "Downloading " + metadata["name"])))
            stage = temp / "runtime"; stage.mkdir(); extract(archive, stage, cancel)
            expected = "scrcpy.exe" if key == "android" else "uxplay-windows.exe" if key == "iphone" else "python.exe"
            if not (stage / expected).is_file():
                raise ValueError("Component archive is incomplete")
            if key in ("vision", "vocals"):
                from .vision_component import ready as vision_ready
                from .vocal_component import ready as vocal_ready
                if not (vision_ready(stage) if key == "vision" else vocal_ready(stage)):
                    raise ValueError("Component runtime validation failed")
            if cancel.is_set():
                raise InterruptedError("Component download cancelled")
            (stage / "pack-ready.json").write_text(json.dumps({"version": VERSION}), encoding="utf-8")
            old = root.with_name(root.name + ".previous")
            if old.exists(): shutil.rmtree(old)
            if root.exists(): root.rename(old)
            try:
                stage.rename(root)
            except OSError:
                if old.exists(): old.rename(root)
                raise
            if old.exists(): shutil.rmtree(old)
        progress((100, metadata["name"] + " ready")); return root
    # Development/legacy builds retain their already working first-use installers.
    if key in ("vision", "vocals"):
        from . import vision_component, vocal_component
        return (vision_component if key == "vision" else vocal_component).install(progress, cancel, component_root(key))
    raise RuntimeError("This build has no phone download manifest. Install the latest release or select your existing phone tools.")


def install_selected(keys, local_source=None):
    import threading
    from .config import DATA_DIR
    log = DATA_DIR / "component-install.log"
    try:
        with log.open("w", encoding="utf-8") as stream:
            for key in keys:
                if key not in ROOTS: raise ValueError("Unknown component: " + key)
                install(key, lambda event: (stream.write(str(event) + "\n"), stream.flush()), threading.Event(), local_source)
        return 0
    except Exception as error:
        with log.open("a", encoding="utf-8") as stream: stream.write("FAILED: " + str(error))
        return 1
