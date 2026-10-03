import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt,QThreadPool,QEvent
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,MediaItem,TimelineItem,Transform
from kinetic_cut.keyframes import put,value,evaluated,expression
from kinetic_cut.ui import MainWindow
from kinetic_cut.keyframe_editor import KeyframeEditor


class CurveTests(unittest.TestCase):
    def item(self):
        i=TimelineItem('v','m','video_1',10,4); put(i,'scale',0,1,'Smooth'); put(i,'scale',4,2); return i
    def test_interpolation_hold_easing_and_legacy(self):
        i=self.item(); self.assertEqual(evaluated(i,2).transform.scale,1.5); self.assertAlmostEqual(evaluated(i,1).transform.scale,1.15625)
        i.keyframes['scale'][0]['interpolation']='Hold'; self.assertEqual(evaluated(i,3.9).transform.scale,1); self.assertEqual(evaluated(i,4).transform.scale,2)
        self.assertEqual(evaluated(i,2).transform.effective_scale_y,1); self.assertEqual(expression(i,'scale_y'),expression(i,'scale'))
        self.assertFalse(Project.from_dict(Project().to_dict()).timeline)
    def test_move_serialize_split_trim_and_retime(self):
        i=self.item(); p=Project(media=[MediaItem('m','none','video','test',30)],timeline=[i])
        i.start=20; clone=Project.from_dict(p.to_dict()); self.assertEqual(clone.item_by_id('v').keyframes,i.keyframes)
        left,right=p.split('v',22); self.assertAlmostEqual(evaluated(right,0).transform.scale,1.5)
        self.assertAlmostEqual(evaluated(right,.5).transform.scale,evaluated(self.item(),2.5).transform.scale)
        p.trim_items([right.id],.5,'left'); self.assertAlmostEqual(evaluated(right,0).transform.scale,evaluated(self.item(),2.5).transform.scale)
        before=evaluated(right,.5).transform.scale; p.retime_items([right.id],2); self.assertAlmostEqual(evaluated(right,.25).transform.scale,before)
    def test_overwrite_retains_animation_on_uncovered_tail(self):
        i=self.item(); p=Project(media=[MediaItem('m','none','image','test')],timeline=[i,TimelineItem('cut','m','video_1',11,1)])
        p.overwrite(['cut']); tail=next(x for x in p.timeline if x.start==12); self.assertAlmostEqual(evaluated(tail,0).transform.scale,1.5)


class KeyframeUITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)/'square.png'; image=QImage(160,90,QImage.Format_RGB32); image.fill(Qt.white); image.save(str(self.path))
        self.w=MainWindow(); self.w.resize(1300,850); self.w.show(); self.w.autosave_timer.stop()
        self.p=Project(media=[MediaItem('m',str(self.path),'image','Square',2,160,90)],timeline=[TimelineItem('v','m','video_1',0,2,transform=Transform(.5,.5,.3))]); self.p.settings.width=320; self.p.settings.height=180; self.p.settings.fps=30; self.w.set_project(self.p)
    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); QApplication.processEvents(); self.w.deleteLater(); QApplication.sendPostedEvents(None,QEvent.DeferredDelete); self.temp.cleanup()
    def test_dialog_cancel_save_and_one_step_undo(self):
        d=KeyframeEditor(self.w,self.p.timeline[0]); d.add_key('scale'); d.edit_value('scale',.5); d.reject(); self.assertFalse(self.p.timeline[0].keyframes)
        history=len(self.w._history); d=KeyframeEditor(self.w,self.p.timeline[0]); d.add_key('scale'); d.seek(1); d.add_key('scale'); d.edit_value('scale',.8)
        self.assertEqual(d.item.keyframes['scale_y'][-1]['value'],.8); d.accept(); self.assertEqual(len(self.w._history),history+1)
        self.assertEqual(evaluated(self.p.timeline[0],1).transform.scale,.8); self.w.undo(); self.assertFalse(self.w.project.timeline[0].keyframes)
    def test_changed_or_locked_clip_cannot_save(self):
        d=KeyframeEditor(self.w,self.p.timeline[0]); d.add_key('x'); self.p.timeline[0].duration=1.5
        with patch('kinetic_cut.keyframe_editor.QMessageBox.warning') as warning:d.accept(); warning.assert_called_once()
        self.assertFalse(self.p.timeline[0].keyframes); d.reject()
    def test_export_dynamic_scale_position_rotation_opacity_and_window(self):
        from kinetic_cut.rendergraph import command
        from kinetic_cut.exporter import PRESETS
        from kinetic_cut.process import run
        item=self.p.timeline[0]
        for name,start,end in [('scale',.3,.6),('scale_y',.3,.6),('x',.3,.65),('rotation',0,20),('opacity',100,70)]:put(item,name,0,start); put(item,name,1,end)
        for window in (None,(.5,1.5)):
            out=Path(self.temp.name)/('full.mp4' if window is None else 'window.mp4')
            result=run(command(self.p,str(out),next(iter(PRESETS.values())),False,'CPU',export_audio=False,window=window),capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace')[-3000:])
            raw=run(['ffmpeg','-v','error','-i',str(out),'-vf','select=eq(n\,0)+eq(n\,15)','-vsync','0','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
            frames=np.frombuffer(raw,np.uint8).reshape(-1,180,320,3)
            centers=[]
            for frame in frames:
                yy,xx=np.where(frame.mean(axis=2)>80); self.assertGreater(len(xx),100); centers.append(xx.mean())
            self.assertGreater(centers[1],centers[0]+15)
