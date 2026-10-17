import threading
import time
import unittest
from types import SimpleNamespace
from PySide6.QtCore import QRectF
from kinetic_cut.preview_process import RendererProcess


class RendererShutdownTests(unittest.TestCase):
    def test_close_releases_poll_before_closing_pipe_and_is_idempotent(self):
        polling=threading.Event(); released=threading.Event(); closed=threading.Event()
        in_poll=[False]; violations=[]; terminated=[]; errors=[]
        class Connection:
            def send(self,payload):pass
            def poll(self,timeout):
                in_poll[0]=True; polling.set(); released.wait(2); in_poll[0]=False
                raise EOFError()
            def close(self):
                if in_poll[0]:violations.append('closed during poll')
                closed.set()
        class Process:
            def is_alive(self):return not released.is_set()
            def terminate(self):terminated.append(True); released.set()
            def join(self,timeout):released.wait(timeout)
        service=RendererProcess(); service.shared=None
        service.connection=Connection(); service.process=Process()
        context=SimpleNamespace(project=SimpleNamespace(to_dict=lambda:{}),frames={},active_frames={},fallback_frames={},interactive=True,raster_scale=1.,draw_captions=False)
        def render():
            try:service.render(context,QRectF(0,0,16,16),(16,16),1.)
            except (EOFError,InterruptedError):errors.append(True)
        bridge=threading.Thread(target=render); bridge.start(); self.assertTrue(polling.wait(2))
        before=time.monotonic(); service.close(); service.close()
        self.assertLess(time.monotonic()-before,.2)
        bridge.join(2); self.assertFalse(bridge.is_alive()); self.assertTrue(closed.wait(2))
        self.assertEqual(violations,[]); self.assertEqual(len(terminated),1); self.assertTrue(errors)
