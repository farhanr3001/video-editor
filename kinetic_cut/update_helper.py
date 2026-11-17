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


class ApplicationBusy(RuntimeError):
    """The installation is still in use; no application files were changed."""


def _application_executable(path,root):
    name=path.name.lower()
    return path.resolve().parent==Path(root).resolve() and (name=='kineticcut.exe' or name.startswith('kineticcut.old-') and name.endswith('.exe'))


def installation_processes(root):
    """Only executables belonging to this exact installation, never other apps."""
    import psutil
    root=Path(root).resolve()
    found=[]
    for process in psutil.process_iter(['exe','cmdline']):
        executable=process.info['exe']
        if not executable or process.pid==os.getpid():continue
        path=Path(executable)
        if not _application_executable(path,root):continue
        found.append((process,process.info['cmdline'] or []))
    return found


def request_editor_close(pids,already_requested):
    """Request normal Qt close/save handling, never force-discard a document."""
    if os.name!='nt':return set()
    from ctypes import wintypes as W
    user=ctypes.WinDLL('user32',use_last_error=True)
    callback=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    user.EnumWindows.argtypes=[callback,W.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)]
    user.IsWindowVisible.argtypes=[W.HWND]
    user.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,ctypes.c_int]
    user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
    visible=set()
    @callback
    def visit(hwnd,_):
        pid=W.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value not in pids or not user.IsWindowVisible(hwnd):return True
        title=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,len(title))
        if title.value=='Kinetic Cut':
            visible.add(pid.value)
            if pid.value not in already_requested:
                user.PostMessageW(hwnd,0x0010,0,0);already_requested.add(pid.value)
        return True
    user.EnumWindows(visit,0)
    return visible


def wait_installation(root,timeout=120):
    """Let workers exit; retire idle stdio bridges once no editor remains.

    Another editor may own unsaved work. Never terminate it, nor helpers while
    that editor is open. An exact-install MCP bridge is headless and holds no
    project; after all editors/workers exit it can safely release its EXE/DLLs.
    """
    import psutil
    started=time.monotonic();deadline=started+timeout;requested=set()
    worker_flags={'--mcp-bridge','--multiprocessing-fork','--caption-worker','--gpu-export-worker',
                  '--preview-effect-source','--media-download-helper'}
    while True:
        running=installation_processes(root)
        if not running:return
        editors={p.pid for p,args in running if not worker_flags.intersection(args)}
        visible=request_editor_close(editors,requested)
        # Only hidden processes whose editor we observed closing, or recognized
        # headless workers, may be retired. Never terminate another visible editor.
        if not visible and not (editors-requested):
            for process,args in running:
                if '--mcp-bridge' not in args and time.monotonic()-started<3:continue
                try:
                    # Recheck identity/arguments immediately before termination.
                    path=Path(process.exe())
                    if _application_executable(path,root) and (worker_flags.intersection(process.cmdline()) or process.pid in requested):
                        process.terminate()
                except psutil.NoSuchProcess:pass
                except psutil.AccessDenied:break
        if time.monotonic()>=deadline:
            raise ApplicationBusy('Another Kinetic Cut window or background task is still running. '
                    'Finish saving or close the remaining Kinetic Cut window, then retry the normal update. No application files were changed.')
        time.sleep(.2)


def prepare_installation(root,names):
    wait_installation(root)
    if os.name!='nt':return
    # Check every destination before starting the transaction. This catches an
    # unrelated scanner/file lock or permissions issue before a partial update.
    for name in names:
        path=files.target_path(root,name)
        if path.is_file():
            try:
                with path.open('r+b'):pass
            except PermissionError as error:
                raise ApplicationBusy('Windows is blocking an application file: '+path.name+'. '
                    'Close all Kinetic Cut windows and AI connections, then retry the normal update. '
                    'No application files were changed.') from error


def replace_with_retry(source,target,timeout=4):
    deadline=time.monotonic()+timeout
    while True:
        try:return os.replace(source,target)
        except PermissionError:
            if os.name!='nt' or time.monotonic()>=deadline:raise
            time.sleep(.15)


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
    parser.add_argument('command', choices=['apply', 'recover', 'quiesce', 'native-prepare', 'native-commit', 'native-rollback'])
    parser.add_argument('path', type=Path)
    parser.add_argument('--wait-pid', type=int, default=0)
    parser.add_argument('--manifest', type=Path); parser.add_argument('--baseline', type=Path)
    parser.add_argument('--no-restart', action='store_true')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args(argv)
    log_dir = args.path.parent if args.command == 'apply' else args.path / '.kinetic-update'
    if args.command=='quiesce':
        import tempfile
        log_dir=Path(tempfile.gettempdir())/'KineticCut-update-check'
    root = args.path
    if args.command == 'apply':root = Path(json.loads(args.path.read_text(encoding='utf-8'))['root'])
    try:
        wait_process(args.wait_pid)
        if args.command=='quiesce':wait_installation(root)
        elif args.command == 'apply':
            files.apply_job(args.path, lambda: probe(root, args.path.parent / 'verification'),
                            replace=replace_with_retry,before_apply=prepare_installation)
            shutil.rmtree(args.path.parent / 'files', ignore_errors=True)
        elif args.command in ('recover', 'native-rollback'):
            wait_installation(root);files.rollback(root)
        elif args.command == 'native-prepare':
            wait_installation(root);native_prepare(root, args.manifest, args.baseline)
        elif args.command == 'native-commit':
            manifest = files.validate_manifest(json.loads((root / files.MANIFEST).read_text(encoding='utf-8')))
            files.commit(root, lambda: (files.verify_install(root, manifest), probe(root, Path(sys.executable).parent / 'verification')))
        if args.command in ('apply', 'recover') and not args.no_restart:
            subprocess.Popen([str(root / 'KineticCut.exe')], cwd=root)
        return 0
    except Exception as error:
        log_dir.mkdir(parents=True, exist_ok=True)
        message = traceback.format_exc(); (log_dir / 'update-error.log').write_text(message, encoding='utf-8')
        if args.command in ('apply', 'recover'):
            if isinstance(error,ApplicationBusy):detail=str(error)
            elif isinstance(error,PermissionError):detail='Windows is still blocking an application file. Close all Kinetic Cut windows and AI connections, then retry the normal update. The previous application was restored where possible.'
            else:detail='The update could not finish. The previous application was restored where possible.\n\n'+message.splitlines()[-1]
            if os.name == 'nt' and not args.quiet:ctypes.windll.user32.MessageBoxW(None,detail,'Kinetic Cut update',0x10)
            if not isinstance(error,ApplicationBusy) and not args.no_restart and not (root / files.JOURNAL).exists():subprocess.Popen([str(root / 'KineticCut.exe')], cwd=root)
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
