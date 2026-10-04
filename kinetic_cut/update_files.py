"""Verified application-file updates. User data is never an update destination."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import threading
import urllib.request
import zipfile

from .updates import trusted_download, version_tuple

MANIFEST = '_update.json'
INVENTORY = '_update-files.txt'
JOURNAL = '.kinetic-update/transaction.json'
MAX_MANIFEST = 8 * 1024 * 1024
ROOT_FILES = {'KineticCut.exe', 'KineticCutUpdater.exe', MANIFEST, INVENTORY}


def cancelled(cancel):
    if cancel.is_set():raise InterruptedError('Update cancelled; the installed application was not changed.')


def digest(path, cancel=None):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            if cancel is not None:cancelled(cancel)
            result.update(chunk)
    return result.hexdigest()


def valid_name(name):
    if not isinstance(name, str) or not name or '\\' in name or any(c in name for c in ':<>"|?*\x00\r\n'):
        raise ValueError('Unsafe application file name')
    parts = name.split('/')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in parts):
        raise ValueError('Unsafe application file path')
    if any(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', p.split('.')[0], re.I) for p in parts):
        raise ValueError('Reserved Windows file name')
    if name not in ROOT_FILES and not name.startswith('_internal/'):
        raise ValueError('Update attempted to access a non-application file')
    vendor_fixture = name == '_internal/IPython/lib/tests/test.wav'
    if name.lower().startswith('_internal/assets/downloads/') or (not vendor_fixture and PurePosixPath(name).suffix.lower() in ('.kcut', '.mp4', '.mkv', '.mp3', '.wav', '.mov')):
        raise ValueError('Personal media cannot be managed by application updates')
    return name


def target_path(root, name):
    root = Path(root).resolve(); path = root / valid_name(name)
    if not path.resolve().is_relative_to(root):raise ValueError('Application path crosses a junction or symlink')
    for parent in [path, *path.parents]:
        if parent == root:break
        if parent.is_symlink():raise ValueError('Application files cannot be symlinks')
    return path


def validate_manifest(data, version=None):
    if data.get('schema') != 1 or data.get('application') != 'KineticCut':raise ValueError('Unsupported update manifest')
    version_tuple(data.get('version'))
    if version and data['version'] != version:raise ValueError('Update version mismatch')
    files = data.get('files'); bundles = data.get('bundles')
    if not isinstance(files, dict) or not 1 <= len(files) <= 25000 or not isinstance(bundles, dict) or len(bundles) > 2000:raise ValueError('Invalid update file inventory')
    names = set(); total = 0
    for name, item in files.items():
        valid_name(name)
        if name.lower() in names:raise ValueError('Duplicate Windows application path')
        names.add(name.lower())
        if name in (MANIFEST, INVENTORY):raise ValueError('Recursive update metadata')
        if not re.fullmatch('[a-f0-9]{64}', item.get('sha256', '')) or not isinstance(item.get('size'), int) or not 0 <= item['size'] <= 2 * 1024**3:raise ValueError('Invalid update file digest/size')
        total += item['size']
        if item.get('bundle') not in bundles:raise ValueError('Missing file payload')
    if total > 8 * 1024**3:raise ValueError('Update exceeds application size limit')
    for key, item in bundles.items():
        if not re.fullmatch('[a-f0-9]{64}', key) or item.get('sha256') != key or not trusted_download(item.get('url', '')) or not isinstance(item.get('size'), int) or not 0 < item['size'] <= 2 * 1024**3:raise ValueError('Invalid update payload')
    if 'KineticCut.exe' not in files:raise ValueError('Update has no application executable')
    return data


def fetch_file(url, sha256, size, destination, cancel, progress=lambda *_: None, opener=urllib.request.urlopen):
    if not trusted_download(url) or not re.fullmatch('[a-f0-9]{64}', sha256) or not 0 < size <= 2 * 1024**3:raise ValueError('Invalid verified download')
    destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_suffix('.partial'); done = 0; checksum = hashlib.sha256()
    try:
        cancelled(cancel)
        request = urllib.request.Request(url, headers={'User-Agent': 'KineticCut-Updater'})
        with opener(request, timeout=30) as response, pending.open('wb') as stream:
            while True:
                cancelled(cancel); chunk = response.read(256 * 1024)
                if not chunk:break
                done += len(chunk)
                if done > size:raise ValueError('Download exceeds published size')
                stream.write(chunk); checksum.update(chunk); progress(done, size)
        cancelled(cancel)
        if done != size or checksum.hexdigest() != sha256:raise ValueError('Update download verification failed')
        pending.replace(destination); return destination
    finally:pending.unlink(missing_ok=True)


def plan(root, manifest, cancel=None, progress=lambda *_: None):
    cancel = cancel or threading.Event(); validate_manifest(manifest)
    changed = {}; expected = {}; files = manifest['files']
    for index, (name, item) in enumerate(files.items()):
        cancelled(cancel); path = target_path(root, name)
        current = digest(path, cancel) if path.is_file() else None
        if current != item['sha256']:
            changed[name] = item; expected[name] = current
        if index % 100 == 0:progress(round(index / len(files) * 100), 'Checking installed application files…')
    old_path = Path(root) / MANIFEST
    removed = {}
    if old_path.is_file():
        old = validate_manifest(json.loads(old_path.read_text(encoding='utf-8')))
        if version_tuple(old['version']) >= version_tuple(manifest['version']):raise ValueError('Update is not newer than the installed inventory')
        for name, item in old['files'].items():
            if name not in files:
                path = target_path(root, name)
                if path.is_file():
                    if digest(path, cancel) != item['sha256']:raise ValueError('An obsolete application file was modified; use the full installer to repair it')
                    removed[name] = item['sha256']
    keys = {item['bundle'] for item in changed.values()}
    return dict(changed=changed, expected=expected, removed=removed, bundles=sorted(keys),
                download_bytes=sum(manifest['bundles'][key]['size'] for key in keys))


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.tmp')
    with pending.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, separators=(',', ':')); stream.flush(); os.fsync(stream.fileno())
    pending.replace(path)


def stage_update(root, manifest, selection, directory, cancel, progress=lambda *_: None, local_payloads=None):
    """Download selected payloads; verify every member and extract changed files only."""
    validate_manifest(manifest); directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    stage = directory / 'files'; stage.mkdir(exist_ok=True); total = selection['download_bytes']; done = 0
    needed = selection['changed']; selected = set(selection['bundles'])
    if selected != {item['bundle'] for item in needed.values()}:raise ValueError('Update payload selection mismatch')
    required = sum(item['size'] for item in needed.values()) * 2 + total + 64 * 1024**2
    if shutil.disk_usage(directory).free < required:raise RuntimeError('Not enough free space to download and safely apply this update')
    try:
        for key in selection['bundles']:
            cancelled(cancel); metadata = manifest['bundles'][key]; archive = directory / (key + '.zip')
            source = Path(local_payloads) / ('KineticCut-Part-' + key + '.zip') if local_payloads else None
            if source and source.is_file():
                if source.stat().st_size != metadata['size'] or digest(source, cancel) != key:raise ValueError('Local update payload verification failed')
                archive = source
            else:
                fetch_file(metadata['url'], key, metadata['size'], archive, cancel,
                           lambda count, size: progress(round((done + count) / max(total, 1) * 100), 'Downloading changed application files…'))
            expected_members = {name for name, item in manifest['files'].items() if item['bundle'] == key}
            with zipfile.ZipFile(archive) as zipped:
                members = zipped.infolist()
                if len(members) != len(expected_members) or {item.filename for item in members} != expected_members:raise ValueError('Update archive inventory mismatch')
                for entry in members:
                    cancelled(cancel); valid_name(entry.filename); item = manifest['files'][entry.filename]
                    if entry.file_size != item['size'] or (entry.external_attr >> 16) & 0o170000 == 0o120000:raise ValueError('Invalid update archive member')
                    checksum = hashlib.sha256(); dest = target_path(stage, entry.filename)
                    output = None
                    if entry.filename in needed:dest.parent.mkdir(parents=True, exist_ok=True); output = dest.open('wb')
                    try:
                        with zipped.open(entry) as stream:
                            for chunk in iter(lambda: stream.read(256 * 1024), b''):
                                cancelled(cancel); checksum.update(chunk)
                                if output:output.write(chunk)
                    finally:
                        if output:output.close()
                    if checksum.hexdigest() != item['sha256']:raise ValueError('Update file verification failed')
            done += metadata['size']; progress(round(done / max(total, 1) * 100), 'Verified changed application files')
            if archive.parent == directory:archive.unlink(missing_ok=True)
        cancelled(cancel)
        (stage / MANIFEST).write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8')
        (stage / INVENTORY).write_text('\n'.join([*sorted(manifest['files']), MANIFEST, INVENTORY]) + '\n', encoding='utf-8')
        for name in (MANIFEST, INVENTORY):
            path = stage / name; needed[name] = dict(sha256=digest(path), size=path.stat().st_size)
            current = target_path(root, name); selection['expected'][name] = digest(current) if current.is_file() else None
        job = dict(schema=1, root=str(Path(root).resolve()), stage=str(stage.resolve()), manifest=manifest,
                   changed=needed, expected=selection['expected'], removed=selection['removed'])
        write_json(directory / 'job.json', job); return directory / 'job.json'
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        for path in directory.glob('*.partial'):path.unlink(missing_ok=True)
        for path in directory.glob('*.zip'):path.unlink(missing_ok=True)
        raise


def prepare_transaction(root, changed, expected, removed=None):
    """Persist sparse backups before any replacement (also used by migration setup)."""
    root = Path(root).resolve(); journal = root / JOURNAL
    if journal.exists():raise RuntimeError('An interrupted update needs recovery before another update')
    folder = journal.parent; entries = {}
    for name in [*changed, *(removed or {})]:
        path = target_path(root, name); previous = digest(path) if path.is_file() else None
        wanted = expected.get(name) if name in changed else removed[name]
        if previous != wanted:raise RuntimeError('Application files changed during the download; check for updates again')
        entries[name] = dict(old=previous, new=changed[name]['sha256'] if name in changed else None)
    folder.mkdir(exist_ok=False) # Exclusive application-file update ownership.
    transaction = dict(schema=1, root=str(root), state='preparing', entries=entries)
    write_json(journal, transaction)
    try:
        for name, entry in entries.items():
            if entry['old'] is not None:
                backup = target_path(folder / 'backup', name); backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path(root, name), backup)
                if digest(backup) != entry['old']:raise RuntimeError('Update rollback verification failed')
        transaction['state'] = 'prepared'; write_json(journal, transaction)
    except BaseException:
        shutil.rmtree(folder); raise
    return transaction


def rollback(root):
    root = Path(root).resolve(); journal = root / JOURNAL
    if not journal.is_file():return
    transaction = json.loads(journal.read_text(encoding='utf-8'))
    if transaction.get('root') != str(root) or transaction.get('schema') != 1:raise ValueError('Invalid rollback journal')
    if transaction['state'] == 'preparing':
        shutil.rmtree(journal.parent); return # Backups incomplete, application not touched.
    if transaction['state'] == 'committed':
        shutil.rmtree(journal.parent); return
    for name, entry in reversed(list(transaction['entries'].items())):
        dest = target_path(root, name)
        if entry['old'] is None:
            # Never remove a file replaced independently after this update attempt.
            if dest.is_file() and digest(dest) != entry['new']:raise RuntimeError('Cannot remove an independently modified update file')
            dest.unlink(missing_ok=True)
        else:
            backup = target_path(journal.parent / 'backup', name)
            if not backup.is_file() or digest(backup) != entry['old']:raise RuntimeError('Verified update rollback file is missing')
            dest.parent.mkdir(parents=True, exist_ok=True)
            pending = dest.with_name(dest.name + '.restore')
            shutil.copy2(backup, pending); pending.replace(dest)
    shutil.rmtree(journal.parent, ignore_errors=True)


def verify_install(root, manifest):
    validate_manifest(manifest)
    for name, item in manifest['files'].items():
        path = target_path(root, name)
        if not path.is_file() or path.stat().st_size != item['size'] or digest(path) != item['sha256']:
            raise RuntimeError('Application verification failed: ' + name)


def commit(root, verify=lambda: None):
    root = Path(root).resolve(); journal = root / JOURNAL
    transaction = json.loads(journal.read_text(encoding='utf-8'))
    for name, entry in transaction['entries'].items():
        path = target_path(root, name)
        if entry['new'] is None:
            if path.exists():raise RuntimeError('Obsolete application file was not removed')
        elif not path.is_file() or digest(path) != entry['new']:raise RuntimeError('Installed update file verification failed')
    verify(); transaction['state'] = 'committed'; write_json(journal, transaction)
    shutil.rmtree(journal.parent)


def apply_job(job_path, verify=lambda: None, replace=os.replace):
    job = json.loads(Path(job_path).read_text(encoding='utf-8')); validate_manifest(job['manifest'])
    root = Path(job['root']).resolve(); stage = Path(job['stage']).resolve()
    if job.get('schema') != 1 or root == stage or stage.is_relative_to(root):raise ValueError('Invalid update job location')
    if set(job['expected']) != set(job['changed']):raise ValueError('Invalid update preconditions')
    old = validate_manifest(json.loads((root / MANIFEST).read_text(encoding='utf-8'))) if (root / MANIFEST).is_file() else None
    if old and version_tuple(old['version']) >= version_tuple(job['manifest']['version']):raise ValueError('Update would downgrade the application')
    for name, checksum in job['removed'].items():
        if name in job['manifest']['files'] or not old or old['files'].get(name, {}).get('sha256') != checksum:
            raise ValueError('Update cannot remove an unowned application file')
    for name, item in job['changed'].items():
        path = target_path(stage, name)
        if name not in (MANIFEST, INVENTORY) and name not in job['manifest']['files']:raise ValueError('Unpublished update file')
        expected = job['manifest']['files'].get(name, item)
        if item['sha256'] != expected['sha256'] or not path.is_file() or digest(path) != item['sha256']:raise ValueError('Staged update changed before installation')
    if json.loads((stage / MANIFEST).read_text(encoding='utf-8')) != job['manifest']:raise ValueError('Staged manifest mismatch')
    inventory = '\n'.join([*sorted(job['manifest']['files']), MANIFEST, INVENTORY]) + '\n'
    if (stage / INVENTORY).read_text(encoding='utf-8') != inventory:raise ValueError('Staged application inventory mismatch')
    prepare_transaction(root, job['changed'], job['expected'], job['removed'])
    try:
        for name in job['removed']:target_path(root, name).unlink()
        for name in job['changed']:
            dest = target_path(root, name); dest.parent.mkdir(parents=True, exist_ok=True)
            replace(target_path(stage, name), dest)
        commit(root, lambda: (verify_install(root, job['manifest']), verify()))
    except BaseException:
        rollback(root); raise
    write_json(Path(job_path).parent / 'completed.json', {'version': job['manifest']['version']})
    return root
