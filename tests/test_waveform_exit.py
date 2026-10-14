import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.cache_manager import clear_waveforms_on_exit
from kinetic_cut.ui import MainWindow,Worker
from kinetic_cut.waveforms import waveform,RATE


class WaveformExitTests(unittest.TestCase):
    def setUp(self):
        self.app=QApplication.instance() or QApplication([])
        self.app.setProperty('kineticTestDiscardUnsaved',True)

    def test_only_waveforms_are_cleared_and_missing_cache_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertEqual(clear_waveforms_on_exit(root),(0,0))
            files=('waveforms/one.npz','waveforms/two.npz','waveforms/notes.txt',
                   'tts/speech.mp3','thumbs/image.png','proxies/video.mp4',
                   'vision-analysis/mask.json','project.kcut','source.wav','recovery.kcut')
            for name in files:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'keep')
            self.assertEqual(clear_waveforms_on_exit(root),(2,8))
            for name in files[2:]:self.assertEqual((root/name).read_bytes(),b'keep')
            self.assertEqual(clear_waveforms_on_exit(root),(0,0))

    def test_rejected_close_does_not_clear(self):
        with tempfile.TemporaryDirectory() as directory,patch('kinetic_cut.cache_manager.CACHE_DIR',Path(directory)):
            path=Path(directory)/'waveforms/keep.npz';path.parent.mkdir();path.write_bytes(b'cache')
            window=MainWindow();window.autosave_timer.stop()
            try:
                with patch('kinetic_cut.close_guard.confirm_close',return_value=False):
                    event=QCloseEvent();window.closeEvent(event)
                self.assertFalse(event.isAccepted());self.assertEqual(path.read_bytes(),b'cache')
                self.assertFalse(getattr(window,'_closing',False))
            finally:window.close()
            self.assertFalse(path.exists())

    def test_terminal_close_waits_for_writer_and_clears_its_new_file(self):
        with tempfile.TemporaryDirectory() as directory,patch('kinetic_cut.cache_manager.CACHE_DIR',Path(directory)):
            root=Path(directory);folder=root/'waveforms';folder.mkdir();old=folder/'old.npz';old.write_bytes(b'old')
            started=threading.Event();release=threading.Event();new=folder/'finished.npz'
            def generate():
                started.set();release.wait(5);new.write_bytes(b'new');return 'complete'
            window=MainWindow();window.autosave_timer.stop();finished=[]
            window.shutdownFinished.connect(lambda:finished.append((old.exists(),new.exists())))
            worker=Worker(generate);window.start_worker(worker)
            try:
                self.assertTrue(started.wait(2))
                event=QCloseEvent();window.closeEvent(event)
                self.assertFalse(event.isAccepted());self.assertTrue(old.exists());self.assertEqual(finished,[])
                release.set();loop=QEventLoop();window.shutdownFinished.connect(loop.quit)
                QTimer.singleShot(2000,loop.quit);loop.exec()
                self.assertEqual(finished,[(False,False)])
                self.assertEqual(window._workers,set())
            finally:release.set();window.close()

    def test_cleanup_errors_cannot_prevent_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'waveforms').mkdir()
            with patch('kinetic_cut.cache_manager.clear',side_effect=PermissionError('locked')):
                with self.assertLogs(level='ERROR'):self.assertEqual(clear_waveforms_on_exit(root),(0,0))

    def test_linked_external_waveform_folder_is_protected(self):
        with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as outside:
            root=Path(directory);target=Path(outside);(target/'keep.npz').write_bytes(b'keep')
            # The containment guard also protects Windows junction targets.
            with patch.object(Path,'resolve',lambda p,*args,**kwargs:target if p.name=='waveforms' else p),patch.object(Path,'is_dir',return_value=True):
                self.assertEqual(clear_waveforms_on_exit(root),(0,0))
            self.assertEqual((target/'keep.npz').read_bytes(),b'keep')

    def test_reopening_regenerates_identical_peaks_and_retains_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'original.wav'
            values=np.zeros((RATE+7,2),dtype=np.int16);values[125]=[-24000,19000]
            with wave.open(str(source),'wb') as output:
                output.setnchannels(2);output.setsampwidth(2);output.setframerate(RATE);output.writeframes(values.tobytes())
            original=source.read_bytes()
            with patch('kinetic_cut.config.CACHE_DIR',root):
                first=waveform(source);self.assertEqual(len(list((root/'waveforms').glob('*.npz'))),1)
                self.assertEqual(clear_waveforms_on_exit(root)[0],1)
                from kinetic_cut.process import popen
                with patch('kinetic_cut.waveforms.popen',wraps=popen) as decoder:second=waveform(source)
                decoder.assert_called_once()
                self.assertTrue(np.array_equal(first.peaks,second.peaks))
                self.assertEqual(len(list((root/'waveforms').glob('*.npz'))),1)
            self.assertEqual(source.read_bytes(),original)
