"""Real separate-process tests; never replace this runner's fault handler."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class CrashLoggingTests(unittest.TestCase):
    def child(self,code):
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,'-c',code,directory],cwd=ROOT,capture_output=True,text=True,timeout=12,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            self.assertEqual(result.returncode,0,result.stderr)
            return {p.name:p.read_text(encoding='utf-8',errors='replace') for p in Path(directory).glob('*.log*')}

    def test_healthy_heartbeat_has_no_timeout_and_stops_cleanly(self):
        files=self.child('''
import sys,time
from pathlib import Path
from kinetic_cut.crash_logging import HangWatchdog
w=HangWatchdog(Path(sys.argv[1])/'trace.log',timeout=.3,interval=.025)
for _ in range(25):w.beat();time.sleep(.025)
w.close();assert not w.thread.is_alive() and w.file.closed
''')
        self.assertIn('SESSION ENDED',files['trace.log'])
        self.assertNotIn('Timeout',files['trace.log']);self.assertNotIn('STALLED',files['trace.log'])

    def test_stalled_gui_leaves_all_thread_stacks_and_recovery_marker(self):
        files=self.child('''
import sys,time
from pathlib import Path
from kinetic_cut.crash_logging import HangWatchdog
w=HangWatchdog(Path(sys.argv[1])/'trace.log',timeout=.25,interval=.025)
def blocked_gui_callback():time.sleep(.55)
blocked_gui_callback();w.beat();time.sleep(.08);w.close()
''')
        self.assertIn('EVENT LOOP STALLED',files['trace.log'])
        self.assertIn('blocked_gui_callback',files['trace.log'])
        self.assertIn('EVENT LOOP RECOVERED',files['trace.log'])

    @unittest.skipUnless(os.name=='nt','Native Windows GIL-held call')
    def test_native_call_holding_gil_still_produces_c_watchdog_stack(self):
        files=self.child('''
import sys,time,ctypes
from pathlib import Path
from kinetic_cut.crash_logging import HangWatchdog
w=HangWatchdog(Path(sys.argv[1])/'trace.log',timeout=.25,interval=.025)
time.sleep(.08)
def native_block_holding_gil():ctypes.PyDLL('kernel32').Sleep(700)
native_block_holding_gil();w.beat();time.sleep(.08);w.close()
''')
        self.assertIn('Timeout',files['trace.log'])
        self.assertIn('native_block_holding_gil',files['trace.log'])

    def test_log_rotates_only_at_session_start_and_retains_one_backup(self):
        files=self.child('''
import sys
from pathlib import Path
from kinetic_cut.crash_logging import HangWatchdog
p=Path(sys.argv[1])/'trace.log';p.write_text('previous crash evidence'*30)
w=HangWatchdog(p,max_bytes=200);w.close()
assert p.with_suffix('.log.1').read_text()=='previous crash evidence'*30
''')
        self.assertIn('SESSION',files['trace.log']);self.assertIn('previous crash evidence',files['trace.log.1'])

    def test_report_quota_prevents_repeated_stall_spam(self):
        files=self.child('''
import sys,time
from pathlib import Path
from kinetic_cut.crash_logging import HangWatchdog
w=HangWatchdog(Path(sys.argv[1])/'trace.log',timeout=.15,interval=.01,max_reports=1)
time.sleep(.35);w.beat();time.sleep(.1);w.close();assert w.reports==1
''')
        self.assertEqual(files['trace.log'].count('EVENT LOOP STALLED'),1)

    def test_stop_is_nonblocking_even_when_guard_is_busy(self):
        files=self.child('''
import sys,time,threading
from pathlib import Path
from kinetic_cut.crash_logging import HangWatchdog
w=HangWatchdog(Path(sys.argv[1])/'trace.log',timeout=2,interval=.025)
t=time.monotonic();w.stop();assert time.monotonic()-t<.05
w.close()
''')
        self.assertIn('SESSION ENDED',files['trace.log'])

    def test_real_qt_heartbeat_installs_once_and_quit_stops_guard(self):
        files=self.child('''
import sys,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from kinetic_cut.crash_logging import install
app=QApplication([]);w=install(app,Path(sys.argv[1]));assert install(app,Path(sys.argv[1])) is w
start=w.last_beat;QTimer.singleShot(650,app.quit);app.exec()
assert w.last_beat>start and w.stop_event.is_set();w.close()
''')
        self.assertIn('SESSION ENDED',files['crash-trace.log'])
        self.assertNotIn('STALLED',files['crash-trace.log'])

    def test_guard_start_failure_cannot_leave_fault_handler_on_a_closed_file(self):
        self.child('''
import sys,faulthandler
from pathlib import Path
from unittest.mock import patch
from kinetic_cut.crash_logging import HangWatchdog
with patch('threading.Thread.start',side_effect=RuntimeError('No thread resources')):
 try:HangWatchdog(Path(sys.argv[1])/'trace.log')
 except RuntimeError:pass
 else:raise AssertionError('Expected start failure')
assert not faulthandler.is_enabled()
''')
