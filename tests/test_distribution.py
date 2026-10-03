import hashlib
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from kinetic_cut import updates, feature_packs
from kinetic_cut.uninstall_data import cleanup
from kinetic_cut.version import VERSION, REPOSITORY


class Response(io.BytesIO):
    def __enter__(self):return self
    def __exit__(self, *args):self.close()


class DistributionTests(unittest.TestCase):
    def data(self, version='9.0.0'):
        return dict(tag_name='v'+version, assets=[dict(name=f'KineticCut-Setup-{version}.exe',
                    browser_download_url=f'https://github.com/{REPOSITORY}/releases/download/v{version}/setup.exe',
                    digest='sha256:'+hashlib.sha256(b'installer').hexdigest(), size=9)])

    def test_release_comparison_and_rejected_channels(self):
        self.assertEqual(updates.parse_release(self.data()).version, '9.0.0')
        self.assertIsNone(updates.parse_release(self.data(VERSION)))
        self.assertIsNone(updates.parse_release(dict(self.data(), prerelease=True)))
        for version in ('v1.2.3-beta', '../bad', 'one'):
            with self.assertRaises(ValueError):updates.version_tuple(version)
        data = self.data(); data['assets'][0]['browser_download_url'] = 'https://evil.example/setup.exe'
        with self.assertRaises(ValueError):updates.parse_release(data)
        data = self.data(); data['assets'][0].pop('digest')
        with self.assertRaises(ValueError):updates.parse_release(data)

    def test_offline_does_not_report_up_to_date(self):
        with self.assertRaises(urllib.error.URLError):
            updates.check(opener=lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError('offline')))
        with self.assertRaises(RuntimeError):
            updates.check(opener=lambda *a, **k: (_ for _ in ()).throw(urllib.error.HTTPError('url',403,'limited',{},None)))
        self.assertIsNone(updates.check(opener=lambda *a, **k: (_ for _ in ()).throw(urllib.error.HTTPError('url',404,'none',{},None))))

    def test_verified_download_and_cancel_leave_no_partial(self):
        release = updates.parse_release(self.data())
        with tempfile.TemporaryDirectory() as temp:
            path = updates.download(release, temp, threading.Event(), opener=lambda *a, **k: Response(b'installer'))
            self.assertEqual(path.read_bytes(), b'installer')
            with self.assertRaises(ValueError):
                updates.download(release, temp, threading.Event(), opener=lambda *a, **k: Response(b'corrupted'))
            self.assertEqual(path.read_bytes(), b'installer')
            cancel = threading.Event(); cancel.set()
            with self.assertRaises(InterruptedError):
                updates.download(release, temp, cancel, opener=lambda *a, **k: Response(b'installer'))
            self.assertFalse(list(Path(temp).glob('*.partial')))

    def test_archive_traversal_and_cancellation(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp); archive = temp/'pack.zip'; stage = temp/'stage'; stage.mkdir()
            for name in ('../escape.exe', 'C:/escape.exe', '..\\escape.exe'):
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,b'x')
                with self.assertRaises(ValueError):feature_packs.extract(archive,stage,threading.Event())
                self.assertFalse((temp/'escape.exe').exists())
            with zipfile.ZipFile(archive,'w') as z:z.writestr('valid/tool.exe',b'x')
            cancel = threading.Event(); cancel.set()
            with self.assertRaises(InterruptedError):feature_packs.extract(archive,stage,cancel)
            self.assertFalse((stage/'valid/tool.exe').exists())

    def test_uninstall_preserves_power_bin_sources_and_external_media(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); data = base/'data'; cache = data/'Cache'; cache.mkdir(parents=True)
            source = cache/'tts/source.wav'; source.parent.mkdir(); source.write_bytes(b'user speech')
            unrelated = base/'external.mp4'; unrelated.write_bytes(b'original')
            power = data/'powerbins.json'; original = json.dumps({'media':[{'media':{'path':str(source)}}]})
            power.write_text(original)
            for path in (data/'components/vision/python.exe',cache/'proxies/test.mp4',data/'models/model.bin',data/'settings.json'):
                path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'app owned')
            result = cleanup((data,cache),power)
            self.assertTrue(result['power_bin_preserved']); self.assertEqual(power.read_text(),original)
            self.assertEqual(source.read_bytes(),b'user speech'); self.assertTrue(unrelated.exists())
            self.assertFalse((data/'components').exists()); self.assertFalse((cache/'proxies').exists())
            self.assertFalse((data/'models').exists())

    def test_unreadable_power_bin_stops_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp); power = data/'powerbins.json'; power.write_text('{bad')
            media = data/'source.wav'; media.write_bytes(b'user')
            with self.assertRaises(ValueError):cleanup((data,),power)
            self.assertTrue(media.exists())

    def test_bundled_caption_model_is_used_without_download(self):
        from kinetic_cut.caption_runtime import model_arguments
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'model.bin').write_bytes(b'model')
            with patch('kinetic_cut.icons.resource_path',return_value=root):
                self.assertEqual(model_arguments('base.en'),(str(root),{}))

    def test_frozen_ffmpeg_prefers_shipped_tool_and_preserves_custom_path(self):
        from kinetic_cut.process import resolve_tool
        with tempfile.TemporaryDirectory() as temp:
            tool=Path(temp)/'ffmpeg.exe';tool.write_bytes(b'tool')
            resolve_tool.cache_clear()
            with patch('kinetic_cut.process.sys.frozen',True,create=True),patch('kinetic_cut.icons.resource_path',return_value=tool),patch('kinetic_cut.process.shutil.which',return_value=None):
                self.assertEqual(resolve_tool('ffmpeg'),str(tool))
                custom=str(Path(temp)/'custom/ffmpeg.exe')
                self.assertEqual(resolve_tool(custom),custom)
            resolve_tool.cache_clear()

    def test_theme_dialog_controls_and_menu_order(self):
        from kinetic_cut.theme import get_theme_stylesheet, PALETTES
        from kinetic_cut.update_ui import UpdateDialog
        from kinetic_cut.ui import MainWindow
        app = QApplication.instance() or QApplication([])
        for theme in PALETTES:
            app.setStyleSheet(get_theme_stylesheet(theme))
            dialog = UpdateDialog(None,updates.parse_release(self.data()),startup=True)
            dialog.show(); app.processEvents()
            labels = [b.text() for b in dialog.findChildren(QPushButton)]
            self.assertIn("Don't show again", labels); self.assertIn('OK',labels)
            self.assertTrue(all(b.isVisible() for b in dialog.findChildren(QPushButton)))
            dialog.close(); dialog.deleteLater(); app.processEvents()
        window = MainWindow(); names = [a.text() for a in window.menuBar().actions()[0].menu().actions()]
        self.assertEqual(names.index('Check for updates…')+1,names.index('UI Themes…'))
        window.close(); window.deleteLater(); app.processEvents()

    def test_missing_phone_is_blurred_and_removal_refreshes_effect_buttons(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.cache_manager import CacheManagerDialog
        from kinetic_cut.component_ui import InstallComponentDialog, events
        app = QApplication.instance() or QApplication([])
        window = MainWindow(); self.addCleanup(window.close)
        with patch('kinetic_cut.feature_packs.available',return_value=False):
            window.phone_connect.refresh_download_gate()
            self.assertTrue(window.phone_connect.download_blur.isEnabled())
            self.assertFalse(window.phone_connect.download_content.isEnabled())
            window.effects_panel.categories.setCurrentRow(0); window.effects_panel.refresh()
            self.assertTrue(any(b.text()=='Download' for b in window.effects_panel.list.findChildren(QPushButton)))
            from PySide6.QtCore import QSize
            window.effects_panel.list.resize(QSize(155,400)); window.effects_panel.list.show(); app.processEvents()
            for index in range(window.effects_panel.list.count()):
                row=window.effects_panel.list.itemWidget(window.effects_panel.list.item(index))
                if row:
                    row.resize(145,row.sizeHint().height()); row.layout().activate()
                    button=row.findChild(QPushButton)
                    self.assertGreaterEqual(button.width(),button.minimumSizeHint().width())
                    self.assertLessEqual(button.geometry().right(),row.width())
        with patch('kinetic_cut.feature_packs.available',return_value=True):
            events().changed.emit(); app.processEvents()
            self.assertFalse(window.phone_connect.download_blur.isEnabled())
            self.assertTrue(window.phone_connect.download_content.isEnabled())
            self.assertFalse(any(window.effects_panel.list.itemWidget(window.effects_panel.list.item(i))
                                 for i in range(window.effects_panel.list.count())))
        dialog = InstallComponentDialog(window,'vision')
        self.assertEqual(dialog.progress.value(),0); self.assertTrue(dialog.confirm.isEnabled())
        with patch('kinetic_cut.feature_packs.install',side_effect=lambda k,p,c:(p((50,'Halfway')), feature_packs.component_root(k))[1]):
            dialog.begin()
            from PySide6.QtCore import QThreadPool
            QThreadPool.globalInstance().waitForDone(5000); app.processEvents()
            self.assertEqual(dialog.progress.value(),50)
        dialog.close(); window.close(); window.deleteLater(); app.processEvents()

    def test_dismissed_startup_version_still_appears_in_manual_check(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.update_ui import UpdateController
        app=QApplication.instance() or QApplication([]);window=MainWindow();self.addCleanup(window.close)
        controller=UpdateController(window);release=updates.parse_release(self.data())
        window.settings['updates_ignored_version']=release.version
        from types import SimpleNamespace
        fake=SimpleNamespace(choice='cancel',exec=lambda:None)
        with patch('kinetic_cut.update_ui.UpdateDialog',return_value=fake) as dialog:
            controller.checked(release,True);dialog.assert_not_called()
            controller.checked(release,False);self.assertEqual(dialog.call_count,1)
            newer=updates.parse_release(self.data('10.0.0'))
            controller.checked(newer,True);self.assertEqual(dialog.call_count,2)
        window.close();window.deleteLater();app.processEvents()

    def test_cache_manager_lists_downloaded_components_and_removes_only_selection(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.cache_manager import CacheManagerDialog
        from kinetic_cut.component_ui import events
        app = QApplication.instance() or QApplication([])
        window = MainWindow(); self.addCleanup(window.close)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'phone-android-v1';root.mkdir();(root/'scrcpy.exe').write_bytes(b'tool');(root/'pack-ready.json').write_text('{}')
            with patch('kinetic_cut.feature_packs.component_root',side_effect=lambda key:root if key=='android' else Path(temp)/key):
                dialog=CacheManagerDialog(window)
                self.assertIn('android',dialog.component_rows)
                dialog.component_rows['android'][0].setChecked(True)
                from PySide6.QtWidgets import QMessageBox
                with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(QMessageBox,'information'):
                    dialog.clear_selected()
                self.assertFalse(root.exists());self.assertFalse(dialog.component_rows['android'][0].isEnabled())
                dialog.close()
        window.close();window.deleteLater();app.processEvents()


if __name__ == '__main__':unittest.main()
