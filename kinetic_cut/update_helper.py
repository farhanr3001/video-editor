"""Independent updater: wait for editor exit, replace verified files, recover on failure."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from . import update_files as files


def wait_process(pid, timeout=120):
    if not pid:return
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:return
        try:
            if kernel.WaitForSingleObject(handle, timeout * 1000) != 0:
                raise RuntimeError('The editor is still running; update was not installed.')
        finally:kernel.CloseHandle(handle)
    else:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:os.kill(pid, 0)
            except ProcessLookupError:return
            time.sleep(.2)
        raise RuntimeError('The editor is still running')


def probe(root, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, KINETIC_CUT_HOME=str(output / 'profile'), KINETIC_CUT_UPDATE_PROBE='1')
    report = output / 'startup'
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    result = subprocess.run([str(root / 'KineticCut.exe'), '--startup-selftest', str(report)],
                            env=env, cwd=root, timeout=90, creationflags=flags)
    if result.returncode or not (report / 'report.json').is_file():raise RuntimeError('Updated application did not pass its startup check')
    data = json.loads((report / 'report.json').read_text(encoding='utf-8'))
    if data.get('passed') is False:raise RuntimeError('Updated application startup check failed')


def native_prepare(root, manifest_path, baseline_path):
    manifest = files.validate_manifest(json.loads(Path(manifest_path).read_text(encoding='utf-8')))
    baseline = json.loads(Path(baseline_path).read_text(encoding='utf-8'))
    files.rollback(root)
    for name, item in baseline['files'].items():
        path = files.target_path(root, name)
        if not path.is_file() or files.digest(path) != item['sha256']:
            raise RuntimeError('This small installer requires the original 1.1.0 application. Use the full installer to repair or install the application.')
    changed = {name: item for name, item in manifest['files'].items()
               if baseline['files'].get(name, {}).get('sha256') != item['sha256']}
    for name in (files.MANIFEST, files.INVENTORY):
        path = Path(manifest_path).parent / name
        changed[name] = dict(sha256=files.digest(path))
    expected = {name: files.digest(files.target_path(root, name)) if files.target_path(root, name).is_file() else None for name in changed}
    removed = {name: item['sha256'] for name, item in baseline['files'].items() if name not in manifest['files']}
    files.prepare_transaction(root, changed, expected, removed)
    try:
        for name in removed:files.target_path(root, name).unlink()
    except Exception:
        files.rollback(root); raise


def run(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['apply', 'recover', 'native-prepare', 'native-commit', 'native-rollback'])
    parser.add_argument('path', type=Path)
    parser.add_argument('--wait-pid', type=int, default=0)
    parser.add_argument('--manifest', type=Path); parser.add_argument('--baseline', type=Path)
    parser.add_argument('--no-restart', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    log_dir = args.path.parent if args.command == 'apply' else args.path / '.kinetic-update'
    root = args.path
    if args.command == 'apply':root = Path(json.loads(args.path.read_text(encoding='utf-8'))['root'])
    try:
        wait_process(args.wait_pid)
        if args.command == 'apply':
            files.apply_job(args.path, lambda: probe(root, args.path.parent / 'verification'))
            shutil.rmtree(args.path.parent / 'files', ignore_errors=True)
        elif args.command in ('recover', 'native-rollback'):files.rollback(root)
        elif args.command == 'native-prepare':native_prepare(root, args.manifest, args.baseline)
        elif args.command == 'native-commit':
            manifest = files.validate_manifest(json.loads((root / files.MANIFEST).read_text(encoding='utf-8')))
            files.commit(root, lambda: (files.verify_install(root, manifest), probe(root, Path(sys.executable).parent / 'verification')))
        if args.command in ('apply', 'recover') and not args.no_restart:
            subprocess.Popen([str(root / 'KineticCut.exe')], cwd=root)
        return 0
    except Exception:
        log_dir.mkdir(parents=True, exist_ok=True)
        message = traceback.format_exc(); (log_dir / 'update-error.log').write_text(message, encoding='utf-8')
        if args.command in ('apply', 'recover'):
            if os.name == 'nt' and not args.quiet:ctypes.windll.user32.MessageBoxW(None, 'The update could not finish. The previous application was restored where possible.\n\n' + message.splitlines()[-1], 'Kinetic Cut update', 0x10)
            if not args.no_restart and not (root / files.JOURNAL).exists():subprocess.Popen([str(root / 'KineticCut.exe')], cwd=root)
        return 1


def recover_on_startup():
    """Run recovery outside the application folder, so Windows permits EXE replacement."""
    if not getattr(sys, 'frozen', False) or os.environ.get('KINETIC_CUT_UPDATE_PROBE'):return False
    root = Path(sys.executable).parent
    if not (root / files.JOURNAL).is_file():return False
    import tempfile
    destination = Path(tempfile.mkdtemp(prefix='KineticCut-recovery-')) / 'KineticCutUpdater.exe'
    shutil.copy2(root / 'KineticCutUpdater.exe', destination)
    subprocess.Popen([str(destination), 'recover', str(root), '--wait-pid', str(os.getpid())])
    return True
