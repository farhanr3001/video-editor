import copy
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal, Qt, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtWidgets import QApplication

from kinetic_cut.phone_common import PhoneError, TransferCancelled, remote_path, device_name, local_name
from kinetic_cut.phone_worker import transfer_paths, ProgressReader, publish_local, android
from kinetic_cut.phone_connect import PhoneConnectPage

_app = QApplication.instance() or QApplication([])


class FakeRequest(QObject):
    finished = Signal(bool, object)
    bytesChanged = Signal(object, object)
    def __init__(self, payload, parent=None):
        super().__init__(parent); self.request = copy.deepcopy(payload); self.done = False; self.cancelled = False
    def start(self): pass
    def cancel(self): self.cancelled = True
    def shutdown(self): self.cancelled = True; self.done = True
    def complete(self, success, result):
        self.done = True; self.finished.emit(success, result)


class PhoneTests(unittest.TestCase):
    def setUp(self):
        self.page = PhoneConnectPage(SimpleNamespace(settings={}), FakeRequest)
    def tearDown(self):
        self.page.shutdown(); self.page.deleteLater(); QApplication.processEvents()
    def connect_fixture(self, platform='iphone', writable=True):
        p = self.page; p.platform = platform
        p.device = dict(id='device-A', name='Test phone', state='ready')
        p.location = dict(name='Documents', root='/Documents', app='test.app', writable=writable) if platform=='iphone' else dict(name='Movies', root='/sdcard', writable=True)
        p.path = p.location['root']; p.folder_ready = True; p.update_controls()

    def test_paths_cannot_escape_scope(self):
        self.assertEqual(remote_path('/sdcard/Movies/../Download', '/sdcard'), '/sdcard/Download')
        for path in ['/sdcard/../../data', '/sdcard-other/file', 'relative', '/sdcard/x\nfoo', '/sdcard\\foo']:
            with self.assertRaises(PhoneError): remote_path(path, '/sdcard')
        for name in ['../escape', 'x/y', 'x\\y', '.', '..', '']:
            with self.assertRaises(PhoneError): device_name(name)

    def test_windows_unsafe_phone_names(self):
        for name in ['CON.mp4', 'nul', 'COM1.jpg', 'clip:stream', 'name.', 'name ', 'x?x']:
            with self.assertRaises(PhoneError): local_name(name)
        self.assertEqual(local_name('Café 🎬.mp4'), 'Café 🎬.mp4')

    def test_camera_media_is_readonly_in_ui_and_backend(self):
        self.connect_fixture(writable=False); self.page.location.pop('app')
        self.page.path = '/DCIM'
        self.assertFalse(self.page.send.isEnabled()); self.assertFalse(self.page.drop.isEnabled())
        self.page.send_files(['anything.mp4']); self.assertFalse(self.page.jobs)
        with self.assertRaises(PhoneError): transfer_paths(self.page.payload('push') | dict(local='anything.mp4'))
        self.assertTrue(self.page.mirror_button.isEnabled())

    def test_disconnect_and_reconnect_toggle(self):
        self.connect_fixture()
        self.assertEqual(self.page.mirror.btn_disconnect.text(), '  Disconnect')
        self.page.mirror._on_disconnect_click()
        self.assertFalse(self.page.mirror.connected)
        self.assertEqual(self.page.mirror.btn_disconnect.text(), '  Reconnect')
        reconnected = []
        self.page.mirror.reconnectRequested.connect(lambda: reconnected.append(True))
        self.page.mirror._on_disconnect_click()
        self.assertEqual(reconnected, [True])

    def test_iphone_mirroring_toggle(self):
        self.connect_fixture('iphone')
        def fake_start(*_): self.page.mirror.airplay_active = True
        with patch.object(self.page.mirror, 'start_airplay', side_effect=fake_start):
            self.page.toggle_mirror()
            self.assertEqual(self.page.mirror_button.text(), '  Stop Mirroring')
            self.page.toggle_mirror()
            self.assertEqual(self.page.mirror_button.text(), '  Start Mirroring')

    def test_no_device_no_transfer_controls(self):
        self.assertFalse(self.page.send.isEnabled()); self.assertFalse(self.page.receive.isEnabled())
        self.assertFalse(self.page.connect_button.isEnabled()); self.assertFalse(self.page.mirror_button.isEnabled())

    def test_obsolete_discovery_cannot_replace_new_platform(self):
        self.page.discover(); old = self.page.pending
        self.page.switch_platform('android'); current = self.page.pending
        self.assertTrue(old.cancelled)
        old.complete(True, [dict(id='old', name='Old phone', state='ready', detail='')])
        self.assertEqual(self.page.devices.count(), 0); self.assertIs(self.page.pending, current)
        current.complete(True, [])
        self.assertIn('No USB device', self.page.device_status.text())

    def test_queue_snapshots_device_folder_and_serializes_jobs(self):
        self.connect_fixture()
        p = self.page
        p.enqueue(p.payload('push') | dict(local='first.mp4'), 'first.mp4', '/Documents')
        first = p.active_job; worker = first['worker']
        p.enqueue(p.payload('push') | dict(local='second.mp4'), 'second.mp4', '/Documents')
        p.device['id'] = 'device-B'; p.location['app'] = 'other.app'; p.path = '/Documents/Other'
        self.assertEqual(first['request']['device'], 'device-A'); self.assertEqual(first['request']['location']['app'], 'test.app')
        worker.bytesChanged.emit(5 * 1024**3, 10 * 1024**3)
        self.assertEqual(first['item'].text(1), '50%')
        worker.complete(True, dict(destination='/Documents/first.mp4'))
        self.assertEqual(first['state'], 'Complete'); self.assertEqual(first['item'].text(1), '100%')
        self.assertIs(p.active_job, p.jobs[1])

    def test_cancel_retry_and_complete_after_late_cancel(self):
        self.connect_fixture(); p = self.page
        p.enqueue(p.payload('push') | dict(local='test.mp4'), 'test.mp4', '/Documents')
        job = p.active_job; worker = job['worker']; p.cancel_selected()
        self.assertTrue(worker.cancelled)
        worker.complete(False, 'Cancelled'); self.assertEqual(job['state'], 'Cancelled')
        p.retry_selected(); self.assertEqual(job['state'], 'Transferring'); self.assertIsNot(worker, job['worker'])
        p.cancel_selected(); job['worker'].complete(True, dict(destination='/Documents/test.mp4'))
        self.assertEqual(job['state'], 'Complete')

    def test_external_file_drop_and_folder_rejection(self):
        self.connect_fixture('android'); p = self.page
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'clip.mp4'; path.write_bytes(b'video')
            mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(path))])
            enter = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
            p.drop.dragEnterEvent(enter); self.assertTrue(enter.isAccepted())
            drop = QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
            p.drop.dropEvent(drop); self.assertTrue(drop.isAccepted()); self.assertEqual(len(p.jobs), 1)
            p.send_files([directory]); self.assertEqual(len(p.jobs), 1)

    def test_progress_reader_cancels_before_next_chunk(self):
        cancel = threading.Event(); events = []
        source = ProgressReader(io.BytesIO(b'abcdef'), 6, lambda done,total: events.append((done,total)), cancel)
        self.assertEqual(source.read(2), b'ab'); self.assertEqual(events, [(2,6)])
        cancel.set()
        with self.assertRaises(TransferCancelled): source.read(2)

    def test_download_cannot_overwrite_existing_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'existing.mp4'; target.write_bytes(b'keep')
            temp = Path(directory) / 'partial'; temp.write_bytes(b'new')
            with self.assertRaises(PhoneError): publish_local(temp, target)
            self.assertEqual(target.read_bytes(), b'keep')
            req = dict(platform='android', op='pull', location={}, path='/sdcard/a.mp4', local=str(target))
            with self.assertRaises(PhoneError): transfer_paths(req)

    def test_android_windows_serial_without_usb_tag_detected(self):
        devices = [SimpleNamespace(serial='REAL123', tags={'model':'Pixel'}, state='device'),
                   SimpleNamespace(serial='192.168.1.10:5555', tags={}, state='device'),
                   SimpleNamespace(serial='emulator-5554', tags={}, state='device')]
        with tempfile.NamedTemporaryFile() as executable:
            with patch('adbutils.AdbClient') as client, patch('kinetic_cut.phone_worker.subprocess.run'):
                client.return_value.list.return_value = devices
                result = android(dict(op='discover', adb=executable.name), lambda *_:None, threading.Event())
        self.assertEqual([d['id'] for d in result], ['REAL123'])

    def test_edit_deliver_phone_navigation_and_render_guard(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.workspace import set_page
        w = MainWindow(); w.phone_connect.loaded = True
        try:
            set_page(w, 2)
            self.assertEqual(w.current_page, 2); self.assertEqual(w.page_content.currentIndex(), 1)
            self.assertFalse(w.shortcut_actions['play_pause'].isEnabled())
            set_page(w, 0)
            self.assertEqual(w.page_content.currentIndex(), 0); self.assertTrue(w.shortcut_actions['play_pause'].isEnabled())
            set_page(w, 1); w.delivery.running = True; w.delivery.update_controls(); set_page(w, 2)
            self.assertEqual(w.current_page, 1); self.assertFalse(w.page_group.button(2).isEnabled())
        finally:
            w.delivery.running = False; w.close(); w.deleteLater()

    def test_dynamic_step_instructions_and_category_updates_on_platform_switch(self):
        p = self.page
        # Initially iPhone
        self.assertIn('iPhone', p.step1_title.text())
        self.assertIn('Trust', p.step2_title.text())
        self.assertIn('iPhone', p.step3_sub.text())
        self.assertEqual(p.category_buttons[2].text().strip(), 'Downloads')
        self.assertIn('On My iPhone', p.category_buttons[2].toolTip())

        # Switch to Android
        p.switch_platform('android')
        self.assertEqual(p.platform, 'android')
        self.assertIn('Android', p.step1_title.text())
        self.assertIn('debugging', p.step2_title.text())
        self.assertIn('keyboard', p.step3_sub.text())
        self.assertIn('/sdcard/Download', p.category_buttons[2].toolTip())

        # Switch back to iPhone
        p.switch_platform('iphone')
        self.assertEqual(p.platform, 'iphone')
        self.assertIn('iPhone', p.step1_title.text())
        self.assertIn('Trust', p.step2_title.text())

    def test_android_usb_debugging_guidance_state(self):
        p = self.page
        p.platform = 'android'
        device = {
            'id': 'wpd:Google Pixel',
            'name': 'Google Pixel',
            'model': 'Google Pixel',
            'state': 'need_usb_debugging',
            'detail': 'USB connected · Turn ON "USB debugging" in Developer options'
        }
        p.devices.addItem('Google Pixel', device)
        p.device_changed()
        self.assertFalse(p.connected_card.isHidden())
        self.assertIn('USB Detected', p.connected_header.text())
        self.assertIn('debugging', p.connected_os.text())
        self.assertTrue(p.mirror_button.isEnabled())

    def test_mirror_instant_teardown_on_deactivate(self):
        p = self.page
        p.mirror.canvas.set_mirroring(True)
        self.assertTrue(p.mirror.canvas.mirroring)
        self.assertFalse(p.mirror.is_popped_out)
        p.deactivate()
        self.assertFalse(p.mirror.canvas.mirroring)
        self.assertTrue(p.mirror.stopping)
        self.assertIsNone(p.mirror.container)

    def test_mirror_popout_lifecycle_and_page_switch_persistence(self):
        p = self.page
        m = p.mirror
        m.canvas.set_mirroring(True)

        # Pop out into floating window
        m.pop_out()
        self.assertTrue(m.is_popped_out)
        self.assertIsNotNone(m.popout_window)
        self.assertTrue(m.popout_window.isVisible())
        self.assertFalse(m.popout_placeholder.isHidden())
        self.assertIs(m.canvas.parent(), m.popout_window)

        # Deactivate while popped out: MUST NOT stop mirror!
        m.stopping = False
        p.deactivate()
        self.assertFalse(m.stopping)
        self.assertTrue(m.canvas.mirroring)

        # Dock back into page
        m.dock_back()
        self.assertFalse(m.is_popped_out)
        self.assertFalse(m.popout_window.isVisible())
        self.assertTrue(m.popout_placeholder.isHidden())
        self.assertIs(m.canvas.parent(), m)

        # Deactivate while NOT popped out: MUST stop immediately
        p.deactivate()
        self.assertTrue(m.stopping)
        self.assertFalse(m.canvas.mirroring)

    def test_device_drive_explorer_breadcrumbs_and_android_paths(self):
        p = self.page
        p.switch_platform('android')
        self.assertEqual(p.path, '/sdcard')
        self.assertEqual(p.folder_label.text(), '/sdcard')

        # Navigate into DCIM/Camera
        p.navigate_to_path('/sdcard/DCIM/Camera')
        self.assertEqual(p.path, '/sdcard/DCIM/Camera')
        self.assertGreater(p.breadcrumb_layout.count(), 2)

        # Up to DCIM
        p.parent_folder()
        self.assertEqual(p.path, '/sdcard/DCIM')

        # Up to root /sdcard
        p.parent_folder()
        self.assertEqual(p.path, '/sdcard')

        # Up again stays at root /sdcard
        p.parent_folder()
        self.assertEqual(p.path, '/sdcard')

        # Navigate deep and jump to root
        p.navigate_to_path('/sdcard/Download/Sub')
        p.go_to_root()
        self.assertEqual(p.path, '/sdcard')

    def test_import_to_project_flow(self):
        from PySide6.QtWidgets import QTreeWidgetItem
        p = self.page
        self.connect_fixture('android')
        item = QTreeWidgetItem(['test_video.mp4', '15.0 MB', '2026-09-20'])
        item.setData(0, Qt.UserRole, dict(name='test_video.mp4', folder=False, size=15000000))
        p.files.addTopLevelItem(item)
        item.setSelected(True)

        # Trigger import to project
        p.import_to_project()
        self.assertEqual(len(p.jobs), 1)
        job = p.jobs[0]
        self.assertEqual(job['name'], 'test_video.mp4')
        self.assertTrue(job.get('import_on_complete'))

