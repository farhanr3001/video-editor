"""Bounded fault/GUI-hang evidence without changing transport or native controls.

The GUI only updates a timestamp. A separate Python guard owns the native
faulthandler timeout, so a native call holding the GIL can still leave a stack.
No watchdog kills, restarts or calls into Qt from another thread.
"""
import atexit
import faulthandler
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


class HangWatchdog:
    def __init__(self,path,*,timeout=5.,interval=.5,max_reports=4,max_bytes=2_000_000):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists() and self.path.stat().st_size>=max_bytes:
            self.path.replace(self.path.with_suffix(self.path.suffix+'.1'))
        self.file=self.path.open('ab',buffering=0)
        self.timeout=float(timeout);self.interval=float(interval)
        self.max_reports=max_reports;self.max_bytes=max_bytes
        self.last_beat=time.monotonic();self.stop_event=threading.Event();self.stopped=threading.Event()
        self.reports=0;self.reported=False;self.deadline=0.;self.armed_beat=0.
        self.owns_fault_handler=not faulthandler.is_enabled()
        self._write('SESSION pid='+str(os.getpid())+'; event-loop stalls and fatal Python/native faults. '
                    'A stack snapshot is diagnostic evidence, not proof of a crash or its root cause.')
        if self.owns_fault_handler:faulthandler.enable(file=self.file,all_threads=True)
        self.thread=threading.Thread(target=self._run,name='KineticHangWatchdog',daemon=True)
        try:self.thread.start()
        except BaseException:
            if self.owns_fault_handler:faulthandler.disable()
            self.file.close()
            raise
        atexit.register(self.close)

    def _write(self,message):
        self.file.write(('\n'+datetime.now(timezone.utc).isoformat()+' '+message+'\n').encode('utf-8'))

    def beat(self):
        self.last_beat=time.monotonic()

    def stop(self):
        # Do not join native/Python threads from the GUI shutdown callback.
        self.stop_event.set()

    def _run(self):
        try:
            while not self.stop_event.is_set():
                now=time.monotonic();delay=now-self.last_beat
                exhausted=self.reports>=self.max_reports or os.fstat(self.file.fileno()).st_size>=self.max_bytes
                if exhausted:
                    if self.owns_fault_handler:faulthandler.cancel_dump_traceback_later()
                    break
                if delay>=self.timeout:
                    if not self.reported:
                        # Finish the C watchdog's possible write before adding
                        # a second traceback; concurrent dumps interleave bytes.
                        if self.owns_fault_handler:faulthandler.cancel_dump_traceback_later()
                        self._write(f'EVENT LOOP STALLED for {delay:.2f}s; may be blocked processing or a native modal dialog.')
                        faulthandler.dump_traceback(file=self.file,all_threads=True)
                        self.reports+=1;self.reported=True
                        logging.error('Event loop unresponsive for %.2fs; thread stacks: %s',delay,self.path)
                else:
                    if self.reported:
                        self._write('EVENT LOOP RECOVERED');self.reported=False;self.deadline=0.
                    # Only this guard thread arms/cancels the C watchdog. Qt's
                    # heartbeat never waits for a watchdog thread or writes files.
                    if self.owns_fault_handler and self.last_beat>self.armed_beat and now>=self.deadline-self.timeout*.6:
                        faulthandler.dump_traceback_later(self.timeout,repeat=False,file=self.file)
                        self.armed_beat=self.last_beat;self.deadline=now+self.timeout
                self.stop_event.wait(self.interval)
        except Exception:
            logging.exception('Crash diagnostic guard failed')
        finally:
            if self.owns_fault_handler:faulthandler.cancel_dump_traceback_later()
            self.stopped.set()

    def close(self):
        self.stop()
        # At process exit only, or explicitly in isolated tests. A live guard
        # retains its file rather than closing a descriptor under a native dump.
        if self.thread is not threading.current_thread():self.thread.join(1.)
        if not self.stopped.is_set() or self.file.closed:return
        if self.owns_fault_handler:faulthandler.disable()
        self._write('SESSION ENDED');self.file.close()
        atexit.unregister(self.close)


def install(app,directory):
    """Install once for a real desktop session; helpers/selftests opt in separately."""
    if getattr(app,'_kinetic_hang_watchdog',None):return app._kinetic_hang_watchdog
    from PySide6.QtCore import QTimer
    from .activity_log import install as install_activity,record
    try:install_activity(directory)
    except Exception:logging.exception('Could not initialize recent-action log')
    watchdog=HangWatchdog(Path(directory)/'crash-trace.log')
    timer=QTimer(app);timer.setInterval(500);timer.timeout.connect(watchdog.beat);timer.start()
    app.aboutToQuit.connect(watchdog.stop)
    app.aboutToQuit.connect(lambda:record('application.quit'))
    app._kinetic_hang_watchdog=watchdog;app._kinetic_hang_timer=timer
    return watchdog
