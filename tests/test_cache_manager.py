import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QImage, QColor
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from kinetic_cut.cache_manager import scan, clear, CacheManagerDialog


class CacheManagerTests(unittest.TestCase):
    def test_file_menu_placement_and_three_theme_palette(self):
        from kinetic_cut.ui import MainWindow
        window=MainWindow(); window.autosave_timer.stop()
        try:
            file_menu=window.menuBar().actions()[0].menu()
            self.assertEqual([action.text() for action in file_menu.actions()[-4:]],
                             ['Cache Manager…','Optional downloads…','Check for updates…','UI Themes…'])
            for theme in ('default','final_cut_obsidian','ableton_gray'):
                window.apply_theme(theme,save=False)
                dialog=CacheManagerDialog(window)
                self.assertEqual(dialog.palette().color(QPalette.Window),
                                 QApplication.instance().palette().color(QPalette.Window))
                self.assertEqual(set(dialog.rows),{'motion-renders','thumbs','proxies','waveforms','compounds','vision-renders','projects','audio-preview'})
                dialog.close()
        finally:
            window.close()
    def test_only_regenerable_allowlisted_files_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('thumbs/a.jpg','thumbs/notes.txt','tts/voice.mp3',
                         'recovered/project.kcut','vision-analysis/1/faces.json',
                         'motion-renders/overlay.mkv','motion-renders/scene.json',
                         'audio-preview-123.wav','ordinary.wav'):
                target = root/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(b'abc')
            self.assertEqual(scan(root)['thumbs'],(1,3))
            self.assertEqual(scan(root)['audio-preview'],(1,3))
            self.assertEqual(scan(root)['motion-renders'],(1,3))
            self.assertEqual(clear(['thumbs','audio-preview','motion-renders'],root),(3,9))
            for name in ('thumbs/notes.txt','tts/voice.mp3','recovered/project.kcut',
                         'vision-analysis/1/faces.json','motion-renders/scene.json','ordinary.wav'):
                self.assertTrue((root/name).is_file(), name)
            with self.assertRaises(ValueError):
                clear(['recovered'],root)

    def test_symlinks_are_not_traversed(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root=Path(directory); (root/'thumbs').mkdir()
            target=Path(outside)/'keep.jpg'; target.write_bytes(b'keep')
            try:(root/'thumbs'/'outside.jpg').symlink_to(target)
            except (OSError,NotImplementedError):self.skipTest('symlink privilege unavailable')
            self.assertEqual(clear(['thumbs'],root),(0,0))
            self.assertEqual(target.read_bytes(),b'keep')

    def test_missing_video_thumbnail_rebuilds_without_blocking_pool(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.model import MediaItem, Project
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'clip.mp4'; source.write_bytes(b'source')
            thumb=Path(directory)/'rebuilt.png'
            picture=QImage(32,18,QImage.Format_RGB32); picture.fill(QColor('blue')); picture.save(str(thumb))
            media=MediaItem('cache-video',str(source),'video','clip',1,32,18,thumbnail=str(Path(directory)/'missing.png'))
            window=MainWindow(); window.autosave_timer.stop()
            try:
                with patch('kinetic_cut.media.make_thumbnail',return_value=str(thumb)) as make:
                    window.set_project(Project(media=[media]))
                    QApplication.processEvents()
                    QThreadPool.globalInstance().waitForDone(10000)
                    QApplication.processEvents()
                    self.assertEqual(media.thumbnail,str(thumb))
                    make.assert_called_once_with(str(source),'video')
            finally:
                window.close()
