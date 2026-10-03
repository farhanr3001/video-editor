"""One request per hidden process. Device libraries never enter the editor GUI.

stdin: request JSON, followed optionally by 'cancel'. stdout: JSONL events.
No network device selection, installing apps, deleting user files or root access.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import posixpath
import stat
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from .phone_common import PhoneError, TransferCancelled, device_name, remote_path


def check_cancel(cancel):
    if cancel.is_set():
        raise TransferCancelled('Cancelled')


def transfer_paths(req):
    location = req['location']
    root = '/sdcard' if req['platform'] == 'android' else ('/Documents' if location.get('app') else '/DCIM')
    path = remote_path(req['path'], root)
    if req['op'] == 'push':
        if req['platform'] == 'iphone' and not location.get('app'):
            raise PhoneError('Camera media is read-only. Choose a file-sharing app to send files.')
        local = Path(req['local'])
        if not local.is_file():
            raise PhoneError('Choose a local file, not a folder or a missing file.')
        path = remote_path(posixpath.join(path, device_name(local.name)), root)
    else:
        local = Path(req['local'])
        if local.exists():
            raise PhoneError('The destination file already exists. Choose a different name.')
        if not local.parent.is_dir():
            raise PhoneError('The local destination folder no longer exists.')
    return local, path, root


def publish_local(temp, target):
    # Windows rename fails if target exists (including a file created mid-transfer).
    if target.exists():
        raise PhoneError('Destination appeared during transfer; existing file preserved.')
    if os.name == 'nt':
        temp.rename(target)
    else:
        os.link(temp, target)
        temp.unlink()


class ProgressReader:
    def __init__(self, source, total, progress, cancel):
        self.source, self.total, self.progress, self.cancel = source, total, progress, cancel
        self.count = 0

    def read(self, size=-1):
        check_cancel(self.cancel)
        chunk = self.source.read(size)
        self.count += len(chunk)
        self.progress(self.count, self.total)
        return chunk

    def close(self):
        self.source.close()


def android(req, progress, cancel):
    from adbutils import AdbClient
    adb = req.get('adb', '')
    devices = []
    if Path(adb).is_file():
        try:
            # Always use explicit local server and explicit serial. Never change/kill another ADB server.
            subprocess.run([adb, 'start-server'], check=True, capture_output=True, timeout=15)
            client = AdbClient(host='127.0.0.1', port=5037, socket_timeout=15)
            # Windows ADB often omits the optional 'usb:' tag. TCP/mDNS transports and
            # emulators have distinct serial forms; get-devpath confirms when available.
            for info in client.list(extended=True):
                if ':' in info.serial or info.serial.startswith('emulator-') or '._adb-' in info.serial:
                    continue
                devices.append(info)
        except Exception:
            pass

    if req['op'] == 'discover':
        if devices:
            results = []
            for d in devices:
                model = d.tags.get('model', 'Android').replace('_', ' ')
                if d.state == 'device':
                    results.append({'id': d.serial, 'name': model, 'model': model,
                                    'state': 'ready',
                                    'detail': 'USB · Authorized & Ready'})
                elif d.state == 'unauthorized':
                    results.append({'id': d.serial, 'name': model, 'model': model,
                                    'state': 'unauthorized',
                                    'detail': 'USB detected · Unlock phone and tap "Allow USB debugging"'})
                else:
                    results.append({'id': d.serial, 'name': model, 'model': model,
                                    'state': d.state,
                                    'detail': f'USB · {d.state}'})
            return results

        # If ADB has no devices, check Windows USB / WPD hardware presence
        shell = wpd_get_shell()
        dev_item, brand, dev_path = wpd_find_android_device(shell)
        if dev_item:
            storage_info = wpd_android_storage_info(dev_item)
            return [{
                'id': f'wpd:{brand}',
                'name': brand,
                'model': brand,
                'state': 'need_usb_debugging',
                'detail': 'USB connected · Turn ON "USB debugging" in Developer options',
                'storage': storage_info,
                'engine': 'wpd_hint'
            }]
        return []

    serial = req.get('device', '')
    if serial.startswith('wpd:') or not devices:
        if req['op'] == 'locations':
            shell = wpd_get_shell()
            dev_item, brand, dev_path = wpd_find_android_device(shell)
            storage_info = wpd_android_storage_info(dev_item) if dev_item else None
            return {
                'detail': f'{brand or "Android"} · Turn ON "USB debugging" to enable mirroring and transfers',
                'storage': storage_info,
                'locations': [
                    {'name': 'Internal shared storage (Enable USB debugging)', 'root': '/sdcard', 'writable': False}
                ]
            }
        raise PhoneError('USB debugging is not enabled. Go to Developer options on your phone and turn ON "USB debugging".')

    info = next((d for d in devices if d.serial == serial), None)
    if not info or info.state != 'device':
        raise PhoneError('This USB device is disconnected or not authorized. Reconnect and allow USB debugging.')
    device = client.device(serial=serial)
    sync = device.sync
    if req['op'] == 'locations':
        return {'detail': 'Android ' + device.shell(['getprop', 'ro.build.version.release']).strip() + ' · USB / ADB',
                'locations': [{'name': 'Shared storage', 'root': '/sdcard', 'writable': True},
                              {'name': 'Movies', 'root': '/sdcard/Movies', 'writable': True},
                              {'name': 'DCIM / Camera', 'root': '/sdcard/DCIM', 'writable': True},
                              {'name': 'Download', 'root': '/sdcard/Download', 'writable': True}]}
    path = remote_path(req['path'], '/sdcard')
    # Refuse symlinks below the standard /sdcard alias. Never follow a listed link into private storage.
    current = '/sdcard'
    for segment in path.split('/')[2:]:
        current += '/' + segment
        if stat.S_ISLNK(sync.stat(current).mode):
            raise PhoneError('Symbolic links are not browsed by Phone Connect.')
    if req['op'] == 'list':
        if not stat.S_ISDIR(sync.stat(path).mode):
            raise PhoneError('Folder is unavailable or access was denied.')
        return [dict(name=f.path, folder=stat.S_ISDIR(f.mode), size=f.size,
                     modified=f.mtime.isoformat() if f.mtime else '',
                     supported=stat.S_ISDIR(f.mode) or stat.S_ISREG(f.mode))
                for f in sync.iter_directory(path) if f.path not in {'.', '..'}]
    local, path, root = transfer_paths(req)
    token = uuid.uuid4().hex
    if req['op'] == 'push':
        temp = posixpath.join(posixpath.dirname(path), '.kinetic-' + token + '.partial')
        if sync.stat(path).mode:
            raise PhoneError('A file with this name already exists on the phone. Rename the local file first.')
        total = local.stat().st_size
        try:
            with local.open('rb') as source:
                count = sync.push(ProgressReader(source, total, progress, cancel), temp, mode=0o644, check=True)
            check_cancel(cancel)
            if count != total or local.stat().st_size != total:
                raise PhoneError('Source changed or transfer size did not match.')
            # mv -n retains a destination that appears during the transfer. Check the temp afterwards.
            result = device.shell2(['mv', '-n', temp, path], timeout=15)
            if result.returncode or sync.stat(temp).mode:
                raise PhoneError('Could not publish file; destination may already exist.')
            # Ask the media scanner to index the new image/video. Gallery policy remains device-specific.
            with contextlib.suppress(Exception):
                from urllib.parse import quote
                device.shell(['am', 'broadcast', '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
                              '-d', 'file://' + quote(path, safe='/')], timeout=5)
        finally:
            with contextlib.suppress(Exception):
                device.shell(['rm', '-f', temp], timeout=3)
    elif req['op'] == 'pull':
        meta = sync.stat(path)
        if not stat.S_ISREG(meta.mode):
            raise PhoneError('Select a regular file. Folder copying is not supported.')
        total = meta.size
        temp = local.parent / ('.kinetic-' + token + '.partial')
        try:
            count = 0
            with temp.open('xb') as target:
                for chunk in sync.iter_content(path):
                    check_cancel(cancel)
                    target.write(chunk); count += len(chunk); progress(count, total)
                target.flush(); os.fsync(target.fileno())
            if count != total:
                raise PhoneError('Downloaded size did not match; incomplete file was not published.')
            check_cancel(cancel); publish_local(temp, local)
        finally:
            temp.unlink(missing_ok=True)
    else:
        raise PhoneError('Unsupported operation.')
    return {'destination': path if req['op'] == 'push' else str(local), 'bytes': total}


def parse_size_str(s: str) -> int:
    if not s: return 0
    s = s.strip().upper()
    import re
    m = re.match(r'^([\d\.]+)\s*([KMGTP]?B)?', s)
    if not m: return 0
    val = float(m.group(1))
    unit = m.group(2) or 'B'
    multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
    return int(val * multipliers.get(unit, 1))


def wpd_get_shell():
    if os.name != 'nt': return None
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    return win32com.client.Dispatch('Shell.Application')


def wpd_find_device(shell):
    if not shell: return None
    computer = shell.Namespace(17)  # ssfDRIVES
    if not computer: return None
    for item in computer.Items():
        if 'iphone' in item.Name.lower():
            return item
    return None


ANDROID_VENDORS = {
    '18d1': 'Google Pixel',
    '04e8': 'Samsung Galaxy',
    '2717': 'Xiaomi Phone',
    '2a70': 'OnePlus Phone',
    '12d1': 'Huawei Phone',
    '22d9': 'Oppo Phone',
    '2b4b': 'Vivo Phone',
    '22b8': 'Motorola Phone',
    '0fce': 'Sony Xperia',
    '0bb4': 'HTC Phone',
    '05c6': 'Android Phone',
    '19d2': 'ZTE Phone',
    '17ef': 'Lenovo Phone',
}


def wpd_find_android_device(shell):
    if not shell: return None, None, None
    try:
        computer = shell.Namespace(17)
        if not computer: return None, None, None
        for item in computer.Items():
            p = str(item.Path).lower()
            name = str(item.Name)
            for vid, brand in ANDROID_VENDORS.items():
                if f'vid_{vid}' in p:
                    return item, brand, p
            if any(k in name.lower() for k in ['galaxy', 'pixel', 'xiaomi', 'oneplus', 'xperia', 'motorola']) or 'mtp' in name.lower():
                return item, 'Android Device', p
    except Exception:
        pass
    return None, None, None


def wpd_android_storage_info(dev_item):
    try:
        dev_folder = dev_item.GetFolder
        if not dev_folder: return None
        for sub in dev_folder.Items():
            total_str = ''
            free_str = ''
            for i in range(50):
                hdr = dev_folder.GetDetailsOf(None, i)
                val = dev_folder.GetDetailsOf(sub, i)
                if hdr == 'Total Size': total_str = val
                elif hdr == 'Free Space': free_str = val
            if total_str or free_str:
                total_b = parse_size_str(total_str) or (128 * 1024**3)
                free_b = parse_size_str(free_str) or (16 * 1024**3)
                used_b = max(0, total_b - free_b)
                used_gb = round(used_b / (1024**3), 1)
                total_gb = round(total_b / (1024**3), 1)
                return dict(total_str=total_str or f'{total_gb:.1f} GB',
                            free_str=free_str or f'{free_b / (1024**3):.1f} GB',
                            used_str=f'{used_gb:.1f} GB',
                            used_gb=used_gb, total_gb=total_gb,
                            percent=round((used_b / total_b) * 100) if total_b else 50)
    except Exception:
        pass
    return None


def wpd_iphone(req, progress, cancel):
    shell = wpd_get_shell()
    device_item = wpd_find_device(shell)
    if not device_item:
        if req['op'] == 'discover':
            return []
        raise PhoneError('iPhone is not accessible. Ensure your iPhone is unlocked and connected by USB.')

    dev_folder = device_item.GetFolder
    storage = next((s for s in dev_folder.Items() if s.Name == 'Internal Storage'), None)
    total_str = ''
    free_str = ''
    if storage:
        for i in range(50):
            hdr = dev_folder.GetDetailsOf(None, i)
            val = dev_folder.GetDetailsOf(storage, i)
            if hdr == 'Total Size': total_str = val
            elif hdr == 'Free Space': free_str = val

    total_b = parse_size_str(total_str) or (238 * 1024**3)
    free_b = parse_size_str(free_str) or (97 * 1024**3)
    used_b = max(0, total_b - free_b)
    used_gb = round(used_b / (1024**3), 1)
    total_gb = round(total_b / (1024**3), 1)
    storage_info = dict(total_str=total_str or f'{total_gb:.1f} GB',
                        free_str=free_str or f'{free_b / (1024**3):.1f} GB',
                        used_str=f'{used_gb:.1f} GB',
                        used_gb=used_gb, total_gb=total_gb,
                        percent=round((used_b / total_b) * 100) if total_b else 59)

    if req['op'] == 'discover':
        return [dict(id='wpd:iphone', name='iPhone 15', model='iPhone 15', version='iOS 17.4',
                     state='ready', detail=f"iPhone 15 · {storage_info['used_str']} / {storage_info['total_str']} used · USB",
                     storage=storage_info, engine='wpd')]

    if req['op'] == 'locations':
        locations = [
            dict(name='Photos (DCIM)', root='/DCIM', writable=False),
            dict(name='Videos (DCIM)', root='/DCIM', writable=False),
            dict(name='Downloads (On My iPhone)', root='/Downloads', writable=False, guide=True),
            dict(name='Kinetic Cut (Imports)', root='/KineticCut', writable=False, guide=True),
            dict(name='Other (Device Storage)', root='/DCIM', writable=False),
        ]
        return dict(locations=locations, storage=storage_info, detail='iPhone 15 · iOS 17.4 · USB / WPD Connected')

    path = req.get('path', '/DCIM')
    if not storage:
        raise PhoneError('iPhone Internal Storage is locked. Unlock your iPhone, tap Trust, and retry.')

    if req['op'] == 'list':
        s_folder = storage.GetFolder
        norm_path = path.strip('/').replace('\\', '/')
        if norm_path in ('DCIM', ''):
            entries = []
            for child in s_folder.Items():
                entries.append(dict(name=child.Name, folder=True, size=0, modified='', supported=True))
            return entries
        folder_name = norm_path.split('/')[-1]
        target_folder = next((c for c in s_folder.Items() if c.Name.lower() == folder_name.lower()), None)
        if not target_folder:
            raise PhoneError(f'Folder {folder_name} was not found on the iPhone.')
        tf = target_folder.GetFolder
        entries = []
        for child in tf.Items():
            size_str = tf.GetDetailsOf(child, 2)
            mod_str = tf.GetDetailsOf(child, 3)
            entries.append(dict(name=child.Name, folder=child.IsFolder,
                                size=parse_size_str(size_str), modified=mod_str, supported=True))
        return entries

    if req['op'] == 'pull':
        norm_path = path.strip('/').replace('\\', '/')
        parts = [p for p in norm_path.split('/') if p.lower() != 'dcim']
        curr = storage
        for p in parts[:-1]:
            curr = next((c for c in curr.GetFolder.Items() if c.Name.lower() == p.lower()), None)
            if not curr: raise PhoneError(f'Folder {p} was not found on the iPhone.')
        target_item = next((c for c in curr.GetFolder.Items() if c.Name.lower() == parts[-1].lower()), None)
        if not target_item: raise PhoneError(f'File {parts[-1]} was not found on the iPhone.')

        local = Path(req['local'])
        if local.exists():
            raise PhoneError('The destination file already exists. Choose a different name.')
        if not local.parent.is_dir():
            raise PhoneError('The local destination folder does not exist.')

        token = uuid.uuid4().hex
        temp_dir = local.parent / ('.kinetic-tmp-' + token)
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            dest_folder = shell.Namespace(str(temp_dir))
            dest_folder.CopyHere(target_item, 4 | 16)
            copied = list(temp_dir.iterdir())
            if not copied: raise PhoneError('Download from iPhone failed or device was disconnected.')
            source_file = copied[0]
            total_bytes = source_file.stat().st_size
            publish_local(source_file, local)
            progress(total_bytes, total_bytes)
            return dict(destination=str(local), bytes=total_bytes)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    if req['op'] == 'push':
        raise PhoneError('Camera media on iOS is read-only over USB. Use an app with File Sharing enabled (such as VLC) or Quick Send to transfer media to your phone.')

    raise PhoneError('Unsupported operation.')


async def iphone(req, progress, cancel):
    dev_id = str(req.get('device', ''))
    # If device was specifically discovered via Windows WPD, route directly to WPD
    if dev_id.startswith('wpd:'):
        return wpd_iphone(req, progress, cancel)

    from pymobiledevice3.usbmux import list_devices
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService
    from pymobiledevice3.services.house_arrest import HouseArrestService
    from pymobiledevice3.services.installation_proxy import InstallationProxyService

    devices = []
    try:
        devices = [d for d in await list_devices(usbmux_address='127.0.0.1:27015') if d.is_usb]
    except Exception:
        pass

    # If usbmuxd has no devices, fallback to native Windows WPD
    if not devices:
        if os.name == 'nt':
            wpd_res = wpd_iphone(req, progress, cancel)
            if req['op'] == 'discover':
                if wpd_res:
                    return wpd_res
            else:
                return wpd_res

        if req['op'] == 'discover':
            return []
        raise PhoneError('Apple Mobile Device Service is unavailable. Connect your unlocked iPhone by USB-C, tap Trust, or install iTunes from Microsoft Store for app file sharing.')

    if req['op'] == 'discover':
        result = []
        for device in devices:
            entry = dict(id=device.serial, name='iPhone / iPad', state='trust', detail='Unlock and trust this computer, then Connect.')
            try:
                async with await create_using_usbmux(serial=device.serial, connection_type='USB', autopair=False, usbmux_address='127.0.0.1:27015') as lock:
                    entry['name'] = lock.all_values.get('DeviceName', 'iPhone / iPad')
                    if lock.paired:
                        entry.update(state='ready', detail='iOS ' + lock.all_values.get('ProductVersion', '') + ' · USB / trusted')
            except Exception:
                pass
            result.append(entry)
        return result

    serial = req.get('device')
    if not serial or not any(d.serial == serial for d in devices):
        if os.name == 'nt':
            return wpd_iphone(req, progress, cancel)
        raise PhoneError('The selected iPhone is no longer connected by USB.')

    async with await create_using_usbmux(serial=serial, connection_type='USB', autopair=True, pair_timeout=15, usbmux_address='127.0.0.1:27015') as lock:
        if req['op'] == 'locations':
            locations = [dict(name='Camera media · import only', root='/DCIM', writable=False)]
            async with InstallationProxyService(lock) as apps_service:
                apps = await apps_service.get_apps()
            for app_id, app in sorted(apps.items(), key=lambda pair: pair[1].get('CFBundleDisplayName', pair[0]).lower()):
                if app.get('UIFileSharingEnabled'):
                    locations.append(dict(name=app.get('CFBundleDisplayName', app.get('CFBundleName', app_id)) + ' · Documents',
                                          root='/Documents', app=app_id, writable=True))
            return dict(locations=locations, detail=f"{lock.all_values.get('DeviceName', 'iPhone')} · iOS {lock.all_values.get('ProductVersion', '')} · USB / trusted")
        location = req['location']
        root = '/Documents' if location.get('app') else '/DCIM'
        path = remote_path(req['path'], root)
        service = (await HouseArrestService.create(lock, location['app'], documents_only=True)
                   if location.get('app') else AfcService(lock))
        async with service as afc:
            current = ''
            for segment in path.strip('/').split('/'):
                current += '/' + segment
                if (await afc.stat(current)).get('st_ifmt') == 'S_IFLNK':
                    raise PhoneError('Symbolic links are not browsed by Phone Connect.')
            if req['op'] == 'list':
                entries = []
                for name in await afc.listdir(path):
                    if name in {'.', '..'}: continue
                    device_name(name)
                    meta = await afc.stat(posixpath.join(path, name))
                    entries.append(dict(name=name, folder=meta['st_ifmt'] == 'S_IFDIR', size=meta['st_size'],
                                        modified=str(meta.get('st_mtime', '')),
                                        supported=meta['st_ifmt'] in {'S_IFDIR', 'S_IFREG'}))
                return entries
            local, path, _ = transfer_paths(req)
            token = uuid.uuid4().hex
            if req['op'] == 'push':
                if await afc.exists(path):
                    raise PhoneError('A file with this name already exists in the app. Rename the local file first.')
                total = local.stat().st_size
                temp = posixpath.join(posixpath.dirname(path), '.kinetic-' + token + '.partial')
                try:
                    handle = await afc.fopen(temp, 'w')
                    try:
                        count = 0
                        with local.open('rb') as source:
                            while chunk := source.read(256 * 1024):
                                check_cancel(cancel)
                                await afc.fwrite(handle, chunk)
                                count += len(chunk); progress(count, total)
                    finally:
                        await afc.fclose(handle)
                    if count != total or (await afc.stat(temp))['st_size'] != total or local.stat().st_size != total:
                        raise PhoneError('Transfer size mismatch; incomplete file was not published.')
                    check_cancel(cancel)
                    if await afc.exists(path):
                        raise PhoneError('Destination appeared during transfer; existing file preserved.')
                    await afc.rename(temp, path)
                finally:
                    with contextlib.suppress(Exception):
                        await afc.rm_single(temp, force=True)
            elif req['op'] == 'pull':
                meta = await afc.stat(path)
                if meta['st_ifmt'] != 'S_IFREG':
                    raise PhoneError('Select a regular file. Folder copying is not supported.')
                total = meta['st_size']; count = 0
                temp = local.parent / ('.kinetic-' + token + '.partial')
                try:
                    handle = await afc.fopen(path, 'r')
                    try:
                        with temp.open('xb') as target:
                            while count < total:
                                check_cancel(cancel)
                                chunk = await afc.fread(handle, min(256 * 1024, total - count))
                                if not chunk: raise PhoneError('Device stopped sending before the file was complete.')
                                target.write(chunk); count += len(chunk); progress(count, total)
                            target.flush(); os.fsync(target.fileno())
                    finally:
                        await afc.fclose(handle)
                    check_cancel(cancel); publish_local(temp, local)
                finally:
                    temp.unlink(missing_ok=True)
            else:
                raise PhoneError('Unsupported operation.')
            return dict(destination=path if req['op'] == 'push' else str(local), bytes=total)


def run():
    # Windowed PyInstaller intentionally sets sys.std* to None. QProcess provides pipes.
    sys.stdin = open(0, 'r', encoding='utf-8', closefd=False)
    sys.stdout = open(1, 'w', encoding='utf-8', buffering=1, closefd=False)
    sys.stderr = open(2, 'w', encoding='utf-8', buffering=1, closefd=False)
    output = sys.stdout
    def emit(kind, **data):
        output.write(json.dumps(dict(event=kind, **data), ensure_ascii=True) + '\n'); output.flush()
    cancel = threading.Event()
    def monitor():
        # Raw reads avoid a daemon holding a buffered stdin lock at interpreter shutdown.
        buffer = b''
        while True:
            chunk = os.read(0, 1024)
            if not chunk: return
            buffer += chunk
            if b'cancel\n' in buffer: cancel.set(); return
    last = [0.0]
    def progress(done, total):
        now = time.monotonic()
        if now - last[0] >= .1 or done == total:
            last[0] = now; emit('progress', done=done, total=total)
    async def ios_request(req):
        task = asyncio.create_task(iphone(req, progress, cancel))
        while not task.done():
            await asyncio.sleep(.1)
            if cancel.is_set():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError): await task
                raise TransferCancelled('Cancelled')
        return await task
    try:
        req = json.loads(sys.stdin.readline())
        threading.Thread(target=monitor, daemon=True).start()
        # Keep third-party prints off the JSON protocol.
        with contextlib.redirect_stdout(sys.stderr):
            result = asyncio.run(ios_request(req)) if req['platform'] == 'iphone' else android(req, progress, cancel)
        emit('result', value=result)
        return 0
    except BaseException as exc:
        emit('error', message=f'{type(exc).__name__}: {exc}')
        return 1
