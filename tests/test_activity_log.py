"""Bounded, nonblocking recent actions, including abrupt process termination."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from kinetic_cut.activity_log import ActivityLog,read,SLOT_BYTES


class ActivityLogTests(unittest.TestCase):
    def test_ring_is_bounded_and_retains_latest_actions_in_sequence_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'actions.log';log=ActivityLog(path,capacity=8)
            for n in range(30):log.record('seek',position=n)
            rows=read(path)
            self.assertEqual(path.stat().st_size,8*SLOT_BYTES)
            self.assertEqual([r['details']['position'] for r in rows],list(range(22,30)))
            log.close()

    def test_drag_updates_coalesce_but_release_is_always_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'actions.log';log=ActivityLog(path)
            for n in range(50):log.record('scrub.move',throttle=1.,position=n)
            log.record('scrub.end',position=49)
            rows=read(path);log.close()
            self.assertEqual(sum(r['action']=='scrub.move' for r in rows),1)
            self.assertEqual(rows[-1]['action'],'scrub.end')
            self.assertEqual(rows[-1]['details']['position'],49)

    def test_previous_session_is_retained_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'actions.log';log=ActivityLog(path);log.record('scrub.start',position=5);log.close()
            log=ActivityLog(path)
            self.assertIn('scrub.start',[r['action'] for r in read(path.with_suffix('.log.1'))]);log.close()

    def test_many_threads_cannot_corrupt_records_or_grow_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'actions.log';log=ActivityLog(path,capacity=32)
            with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lambda n:log.record('job.finished',number=n),range(800)))
            rows=read(path);log.close()
            self.assertEqual(len(rows),32);self.assertEqual(len({r['sequence'] for r in rows}),32)
            self.assertEqual(path.stat().st_size,32*SLOT_BYTES)

    def test_unexpected_details_and_damaged_line_do_not_break_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'actions.log';log=ActivityLog(path,capacity=4)
            log.record('problem',value=float('nan'),large='text'*10000,custom=object())
            log.mapping[:SLOT_BYTES]=b'incomplete JSON'.ljust(SLOT_BYTES-1,b' ')+b'\n'
            rows=read(path);self.assertEqual(rows[-1]['action'],'problem');log.close()

    def test_last_action_is_readable_after_abrupt_kill_without_python_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'actions.log';ready=Path(directory)/'ready'
            code='''
import sys,time,os,ctypes
from pathlib import Path
from kinetic_cut.activity_log import ActivityLog
log=ActivityLog(Path(sys.argv[1]));log.record('scrub.start',position=9.15)
Path(sys.argv[2]).write_text('ready')
if os.name=='nt':ctypes.PyDLL('kernel32').Sleep(30000)
else:time.sleep(30)
'''
            child=subprocess.Popen([sys.executable,'-c',code,str(path),str(ready)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            try:
                deadline=time.monotonic()+5
                while not ready.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.01)
                self.assertTrue(ready.exists());self.assertEqual(read(path)[-1]['action'],'scrub.start')
                child.terminate();child.wait(timeout=5)
                self.assertEqual(read(path)[-1]['details']['position'],9.15)
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)

    def test_installed_action_hooks_record_transport_and_edit_intent(self):
        from kinetic_cut import activity_log
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.model import Project
        from PySide6.QtCore import QThreadPool
        from PySide6.QtWidgets import QApplication
        with tempfile.TemporaryDirectory() as directory:
            log=activity_log.install(directory);w=MainWindow();w.autosave_timer.stop()
            try:
                w.set_project(Project(name='Activity fixture'))
                w.transport.seek(.1);w.transport.scrub(.2);w.transport.finish_scrub()
                w.transport.play();w.transport.pause();w.split_selected();w.undo();w.redo()
                actions=[r['action'] for r in read(log.path)]
                for expected in ['project.switch','seek','scrub.start','scrub.end','play','pause','edit.split','undo','redo']:
                    self.assertIn(expected,actions)
            finally:
                w.close();QThreadPool.globalInstance().waitForDone(5000);QApplication.processEvents();log.close()
