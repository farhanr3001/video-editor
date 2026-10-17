import json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
import psutil
from kinetic_cut import enhance_component as component
from kinetic_cut.enhance_process import run
from kinetic_cut.vocal_component import Cancelled,check_cancel


class EnhanceProcessTests(unittest.TestCase):
    def exercise(self,body,callback=lambda event:None,**options):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'worker.log'
            return run([sys.executable,'-u','-c',body],log,callback,options.pop('cancel',threading.Event()),**options)

    def test_cancel_reaps_owned_process_tree(self):
        cancel=threading.Event();pids=[]
        def progress(event):pids.append(json.loads(event[1])['pid']);cancel.set()
        with self.assertRaises(Cancelled):
            self.exercise('import os,json,time;print(json.dumps(dict(frames=0,pid=os.getpid())),flush=True);time.sleep(20)',progress,cancel=cancel)
        self.assertTrue(pids);self.assertTrue(all(not psutil.pid_exists(pid) for pid in pids))

    def test_callback_failure_also_stops_worker(self):
        pids=[]
        def progress(event):pids.append(json.loads(event[1])['pid']);raise RuntimeError('closed receiver')
        with self.assertRaisesRegex(RuntimeError,'closed receiver'):
            self.exercise('import os,json,time;print(json.dumps(dict(frames=0,pid=os.getpid())),flush=True);time.sleep(20)',progress)
        self.assertTrue(pids);self.assertTrue(all(not psutil.pid_exists(pid) for pid in pids))

    def test_startup_and_forward_progress_stalls_are_bounded(self):
        for body in ('import time;time.sleep(20)','import json,time;print(json.dumps(dict(frames=0)),flush=True);time.sleep(20)'):
            began=time.monotonic()
            with self.assertRaises(TimeoutError):self.exercise(body,stall_timeout=.3,startup_timeout=.3)
            self.assertLess(time.monotonic()-began,4)

    def test_worker_error_propagates_without_cpu_retry(self):
        with self.assertRaisesRegex(RuntimeError,'GPU memory exhausted'):
            self.exercise('raise RuntimeError("GPU memory exhausted")')

    def test_successful_worker_is_retired(self):
        result=self.exercise('import json;print(json.dumps(dict(frames=2)),flush=True)')
        self.assertFalse(psutil.pid_exists(result['pid']))

    def test_crop_first_decoder_matches_full_rgba_then_qrect_crop(self):
        import shutil
        if not shutil.which('ffmpeg'):self.skipTest('FFmpeg unavailable')
        import av,numpy as np
        from kinetic_cut.model import Project,MediaItem,TimelineItem,Crop
        from kinetic_cut.enhance import _source_frames
        from kinetic_cut.preview_raster import RasterContext
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'odd.mkv'
            with av.open(str(path),'w') as movie:
                stream=movie.add_stream('ffv1',rate=5);stream.width=65;stream.height=49;stream.pix_fmt='bgra'
                for n in range(2):
                    values=np.random.default_rng(n).integers(0,256,(49,65,4),dtype=np.uint8)
                    frame=av.VideoFrame.from_ndarray(values,format='rgba');frame.pts=n
                    for packet in stream.encode(frame):movie.mux(packet)
                for packet in stream.encode():movie.mux(packet)
            media=MediaItem('m',str(path),'video','odd',.4,65,49);media.fps=5
            item=TimelineItem('i','m','video_1',0,.4);item.crop=Crop(.1,.13,.6,.6);project=Project(media=[media],timeline=[item])
            full=list(_source_frames(project,item,'ffmpeg',threading.Event()))
            cropped=list(_source_frames(project,item,'ffmpeg',threading.Event(),source_crop=item.crop))
            self.assertEqual(len(full),2);self.assertEqual(len(full),len(cropped))
            for (_,image,at),(_,crop,other_at) in zip(full,cropped):
                self.assertEqual(crop,RasterContext._source_crop(image,item.crop));self.assertEqual(at,other_at)


class EnhanceUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'component';self.root.mkdir()
        (self.root/'python.exe').touch();(self.root/'ready.json').write_text(json.dumps(dict(version=1,acceleration='CUDA')))
        (self.root/'models').mkdir();(self.root/'models/realbasicvsr.pth').write_bytes(b'owner old model')
    def tearDown(self):self.temp.cleanup()
    def write_model(self,url,path,digest,progress,cancel,*args):
        check_cancel(cancel)
        with open(path,'wb') as stream:stream.truncate(4885111)

    def test_explicit_small_upgrade_reuses_runtime_and_keeps_old_marker_model(self):
        self.assertTrue(component.runtime_ready(self.root));self.assertFalse(component.ready(self.root))
        before=(self.root/'ready.json').read_bytes()
        with patch.object(component,'download',side_effect=self.write_model) as download,patch.object(component,'monitored') as pip:
            component.install(lambda event:None,threading.Event(),self.root,'CUDA')
            self.assertEqual(download.call_count,2);pip.assert_not_called()
        self.assertTrue(component.ready(self.root));self.assertEqual((self.root/'ready.json').read_bytes(),before)
        self.assertEqual((self.root/'models/realbasicvsr.pth').read_bytes(),b'owner old model')

    def test_cancelled_upgrade_does_not_activate_or_replace_old_runtime(self):
        cancel=threading.Event()
        def download(*args):self.write_model(*args);cancel.set()
        with patch.object(component,'download',side_effect=download):
            with self.assertRaises(Cancelled):component.install(lambda event:None,cancel,self.root,'CUDA')
        self.assertFalse(component.ready(self.root));self.assertTrue(component.runtime_ready(self.root))
        self.assertFalse((self.root/'fast-ready.json').exists());self.assertEqual((self.root/'models/realbasicvsr.pth').read_bytes(),b'owner old model')
