"""Protocol-adapter tests, distinct from real-phone acceptance tests."""
import asyncio
import io
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from kinetic_cut.phone_common import PhoneError, TransferCancelled
from kinetic_cut.phone_worker import iphone, android


class FakeAfc:
    def __init__(self):
        self.files = {}; self.handles = {}; self.next_handle = 1; self.cancel = None
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass
    async def exists(self, path): return path in self.files
    async def stat(self, path):
        return dict(st_ifmt='S_IFREG' if path in self.files else 'S_IFDIR', st_size=len(self.files.get(path, b'')))
    async def listdir(self, path): return [key.rsplit('/', 1)[-1] for key in self.files]
    async def fopen(self, path, mode):
        handle = self.next_handle; self.next_handle += 1
        if mode == 'w': self.files[path] = b''
        self.handles[handle] = [path, 0]; return handle
    async def fwrite(self, handle, data):
        self.files[self.handles[handle][0]] += data
        if self.cancel: self.cancel.set()
    async def fread(self, handle, size):
        path, offset = self.handles[handle]; data = self.files[path][offset:offset + size]
        self.handles[handle][1] += len(data); return data
    async def fclose(self, handle): self.handles.pop(handle)
    async def rename(self, source, target): self.files[target] = self.files.pop(source)
    async def rm_single(self, path, force=False): self.files.pop(path, None)


class FakeLock:
    paired = True
    all_values = dict(DeviceName='Test iPhone', ProductVersion='18.0')
    async def __aenter__(self): return self
    async def __aexit__(self, *_): pass


class IphoneBackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.afc = FakeAfc(); self.cancel = threading.Event(); self.progress = []
        self.directory = tempfile.TemporaryDirectory(); self.folder = Path(self.directory.name)
        self.patches = [patch('pymobiledevice3.usbmux.list_devices', AsyncMock(return_value=[SimpleNamespace(serial='USB-A', is_usb=True)])),
                        patch('pymobiledevice3.lockdown.create_using_usbmux', AsyncMock(return_value=FakeLock())),
                        patch('pymobiledevice3.services.house_arrest.HouseArrestService.create', AsyncMock(return_value=self.afc)),
                        patch('pymobiledevice3.services.afc.AfcService', return_value=self.afc)]
        for p in self.patches: p.start()
    async def asyncTearDown(self):
        for p in reversed(self.patches): p.stop()
        self.directory.cleanup()
    async def call(self, op, path='/Documents', local=None, location=None):
        return await iphone(dict(platform='iphone', op=op, device='USB-A', path=path,
                                 location=location or dict(app='test.app', root='/Documents', writable=True), local=str(local)),
                            lambda d,t:self.progress.append((d,t)), self.cancel)

    async def test_upload_unicode_and_roundtrip_exact_bytes(self):
        source = self.folder / 'Café 🎬.mp4'; source.write_bytes(b'video-frame' * 70000)
        result = await self.call('push', local=source)
        self.assertEqual(result['bytes'], source.stat().st_size)
        self.assertEqual(self.afc.files['/Documents/' + source.name], source.read_bytes())
        target = self.folder / 'download.mp4'
        await self.call('pull', '/Documents/' + source.name, target)
        self.assertEqual(target.read_bytes(), source.read_bytes()); self.assertFalse(self.afc.handles)
        self.assertFalse(list(self.folder.glob('*.partial')))

    async def test_existing_phone_file_is_not_replaced(self):
        source = self.folder / 'clip.mp4'; source.write_bytes(b'new')
        self.afc.files['/Documents/clip.mp4'] = b'keep'
        with self.assertRaises(PhoneError): await self.call('push', local=source)
        self.assertEqual(self.afc.files['/Documents/clip.mp4'], b'keep')

    async def test_cancel_upload_closes_handle_and_removes_owned_partial(self):
        source = self.folder / 'clip.mp4'; source.write_bytes(b'v' * 600000)
        self.afc.files['/Documents/keep.mp4'] = b'keep'; self.afc.cancel = self.cancel
        with self.assertRaises(TransferCancelled): await self.call('push', local=source)
        self.assertEqual(self.afc.files, {'/Documents/keep.mp4': b'keep'}); self.assertFalse(self.afc.handles)

    async def test_dcim_write_rejected_but_download_allowed(self):
        location = dict(root='/DCIM', writable=False)
        source = self.folder / 'clip.mp4'; source.write_bytes(b'video')
        with self.assertRaises(PhoneError): await self.call('push', '/DCIM', source, location)
        self.afc.files['/DCIM/image.jpg'] = b'image'
        target = self.folder / 'image.jpg'
        await self.call('pull', '/DCIM/image.jpg', target, location)
        self.assertEqual(target.read_bytes(), b'image')

    async def test_disconnected_or_other_device_not_used(self):
        with patch('pymobiledevice3.usbmux.list_devices', AsyncMock(return_value=[SimpleNamespace(serial='USB-B', is_usb=True)])):
            with self.assertRaises(PhoneError): await self.call('list')

    async def test_symlink_scope_escape_rejected(self):
        original = self.afc.stat
        async def stat_path(path):
            return dict(st_ifmt='S_IFLNK', st_size=0) if path == '/Documents/link' else await original(path)
        self.afc.stat = stat_path
        with self.assertRaises(PhoneError): await self.call('list', '/Documents/link/elsewhere')


class AndroidBackendTests(unittest.TestCase):
    def test_upload_and_download_keep_content_and_target(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); source = folder / "a 'quoted' clip.mp4"; source.write_bytes(b'abc' * 4000)
            files = {}; commands = []
            def info(path):
                mode = stat.S_IFREG if path in files else stat.S_IFDIR if path == '/sdcard' else 0
                return SimpleNamespace(mode=mode, size=len(files.get(path, b'')))
            def push(reader, path, **_):
                files[path] = reader.read(); return len(files[path])
            def shell(command, **_):
                commands.append(command)
                if command[0] == 'rm': files.pop(command[-1], None)
                return ''
            def shell2(command, **_):
                files[command[3]] = files.pop(command[2]); return SimpleNamespace(returncode=0)
            sync = SimpleNamespace(stat=info, push=push, iter_content=lambda path: iter([files[path]]))
            device = SimpleNamespace(sync=sync, shell=shell, shell2=shell2)
            client = SimpleNamespace(list=lambda **_: [SimpleNamespace(serial='USB-A', state='device', tags={})], device=lambda **_:device)
            req = dict(platform='android', device='USB-A', adb=str(source), op='push', path='/sdcard', location=dict(root='/sdcard', writable=True), local=str(source))
            with patch('adbutils.AdbClient', return_value=client), patch('kinetic_cut.phone_worker.subprocess.run'):
                result = android(req, lambda *_:None, threading.Event())
                self.assertEqual(files[result['destination']], source.read_bytes())
                target = folder / 'download.mp4'; req.update(op='pull', path=result['destination'], local=str(target))
                android(req, lambda *_:None, threading.Event())
                self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertTrue(any(command[0] == 'am' for command in commands))
            self.assertEqual(list(files), ['/sdcard/' + source.name])
