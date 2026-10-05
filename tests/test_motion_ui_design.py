import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import av,numpy as np
from PySide6.QtCore import Qt,QEvent,QThreadPool,QPointF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from kinetic_cut.motion import validate,draw,geometry
from kinetic_cut.motion_text import graphemes,revealed_text,counter_text
from kinetic_cut.model import Project,TimelineItem,Transform

def pixels(image):
    return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()

def fixture():
    return validate(dict(canvas=[240,240],nodes=[dict(id='panel',kind='rectangle',x=120,y=120,width=180,height=80,radius=20,fill='#ffffff',shadow=dict(enabled=True,blur=12,opacity=30,y=8)),dict(id='typing',kind='text',text='find a moment',x=44,y=111,font_size=18,bold=False,fill='#101315',text_align='left',text_mode='typewriter',caret=True,stagger=.08),dict(id='counter',kind='text',x=44,y=142,font_size=15,fill='#16866c',text_align='left',text_mode='counter',number_suffix=' frames',keyframes={'number':[dict(time=0,value=0),dict(time=1,value=2400)]})]))

class MotionUIDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_typewriter_graphemes_pauses_reverse_and_trim_phase(self):
        text='A👩‍💻e\u0301🇬🇧!'; self.assertEqual(graphemes(text),('A','👩‍💻','e\u0301','🇬🇧','!'))
        n=dict(text=text,stagger=.1,start=.3)
        self.assertEqual(revealed_text(n,.3),''); self.assertEqual(revealed_text(n,.6),'A👩‍💻e\u0301')
        n['keyframes']={'reveal':[dict(time=0,value=0),dict(time=1,value=1,interpolation='Hold'),dict(time=2,value=1),dict(time=3,value=0)]}
        self.assertEqual(revealed_text(n,1.6),text); self.assertEqual(revealed_text(n,2.5),'A👩‍💻')
        p=Project(timeline=[TimelineItem('motion','','video_1',0,4,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':fixture()},transform=Transform(.5,.5))]); p.settings.width=p.settings.height=240
        from kinetic_cut.native_animation import frame
        before=pixels(frame(p,p.timeline[0],.7)); _,right=p.split('motion',.4)
        np.testing.assert_array_equal(before,pixels(frame(p,right,.3)))
    def test_typing_anchor_stays_fixed_for_every_alignment_and_scale(self):
        for alignment in ('left','center','right'):
            s=validate(dict(canvas=[240,240],nodes=[dict(id='t',kind='text',text='MMMM',x=120,y=120,font_size=30,text_mode='typewriter',text_align=alignment,stagger=.1)]))
            early=pixels(draw(s,.1,(240,240))); late=pixels(draw(s,.4,(240,240)))
            _,a=np.where(early[:,:,3]>180); _,b=np.where(late[:,:,3]>180)
            self.assertAlmostEqual(a.min(),b.min(),delta=1)
            large=pixels(draw(s,.1,(480,480))); _,x=np.where(large[:,:,3]>180); self.assertAlmostEqual(x.min()/2,a.min(),delta=1)
    def test_caret_blinks_without_text_and_masks_clip_it(self):
        n=dict(id='t',kind='text',text='search',x=60,y=120,font_size=24,text_mode='typewriter',text_align='left',stagger=2,caret=True,caret_period=1)
        s=validate(dict(canvas=[240,240],nodes=[n])); self.assertTrue(pixels(draw(s,0,(240,240)))[:,:,3].any()); self.assertFalse(pixels(draw(s,.6,(240,240)))[:,:,3].any())
        s['nodes'][0]['mask']=dict(kind='rectangle',x=100,width=10,height=10)
        self.assertFalse(pixels(draw(s,0,(240,240)))[:,:,3].any())
    def test_counters_format_roundtrip_and_invalid_controls(self):
        n=dict(number_prefix='$',number_suffix=' saved',number_decimals=2.0,number_grouping=True,keyframes={'number':[dict(time=0,value=0),dict(time=1,value=2500)]})
        self.assertEqual(counter_text(n,.5),'$1,250.00 saved'); n['number']=-.001; n['keyframes']={}; self.assertEqual(counter_text(n,0),'$0.00 saved')
        s=validate(dict(nodes=[dict(id='n',kind='text',text_mode='counter',number=12000000)])); self.assertEqual(s['nodes'][0]['number'],12000000)
        for extra in (dict(text_align='bad'),dict(caret_period=0),dict(number_decimals=2.5),dict(shadow=dict(blur=999)),dict(shadow=dict(color='invalid!')),dict(caret='yes')):
            with self.assertRaises(ValueError):validate(dict(nodes=[dict(id='t',kind='text',**extra)]))
    def test_animated_radius_stroke_and_bounded_soft_shadows(self):
        from kinetic_cut.motion_shadow import _cache
        _cache.clear(); s=fixture(); early=pixels(draw(s,0,(240,240))); self.assertGreater(early[169,120,3],0); self.assertLess(early[169,120,3],80)
        s['nodes'][0]['keyframes']={'radius':[dict(time=0,value=0),dict(time=1,value=40)]}
        self.assertTrue(geometry(s['nodes'][0],0).contains(QPointF(85,35))); self.assertFalse(geometry(s['nodes'][0],1).contains(QPointF(85,35)))
        for n in range(30):s['nodes'][0]['width']=160+n; draw(s,.8,(240,240))
        self.assertLessEqual(len(_cache),24); self.assertLessEqual(_cache.byte_count,32*1024**2)
        s=validate(dict(canvas=[240,240],nodes=[dict(id='p',kind='path',x=120,y=120,path=[['M',-50,0],['L',50,0]],fill='none',stroke='#ffffff',keyframes={'stroke_width':[dict(time=0,value=1),dict(time=1,value=12)]})]))
        self.assertGreater(np.count_nonzero(pixels(draw(s,1,(240,240)))[:,:,3]),np.count_nonzero(pixels(draw(s,0,(240,240)))[:,:,3])*5)
    def test_actual_120fps_export_typing_counter_shadows(self):
        from kinetic_cut.exporter import export,ExportPreset
        from kinetic_cut.native_animation import frame
        item=TimelineItem('ui','','video_1',0,.3,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':fixture()},transform=Transform(.5,.5)); p=Project(timeline=[item]); p.settings.width=p.settings.height=240; p.settings.fps=120
        with tempfile.TemporaryDirectory() as directory,patch('kinetic_cut.config.CACHE_DIR',Path(directory)/'cache'):
            target=Path(directory)/'ui.mp4'; export(p,str(target),ExportPreset('test','h264',4,128,'test'),False,'CPU',export_audio=False)
            with av.open(str(target)) as movie:
                self.assertEqual(str(movie.streams.video[0].average_rate),'120'); frames=list(movie.decode(video=0))
            self.assertEqual(len(frames),36)
            image=frame(p,item,.2).convertToFormat(QImage.Format_RGBA8888); rgba=pixels(image); expected=rgba[:,:,:3].astype(float)*rgba[:,:,3:]/255
            self.assertLess(np.abs(frames[24].to_ndarray(format='rgb24').astype(float)-expected).mean(),4)

class MotionUIDesignEditorTests(unittest.TestCase):
    def test_native_controls_history_persistence_and_120fps_choice(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.motion_editor import MotionEditor
        from kinetic_cut.project_settings import ProjectSettingsDialog
        app=QApplication.instance() or QApplication([]); w=MainWindow(); w.show(); w.autosave_timer.stop()
        try:
            p=Project(timeline=[TimelineItem('ui','','video_1',0,2,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':fixture()})]); w.set_project(p); before=copy.deepcopy(w.project.timeline[0])
            d=MotionEditor(w,w.project.timeline[0]); d.show(); d.node_id='typing'; d.refresh(); self.assertTrue(d.caret.isVisible()); d.text_align.setCurrentText('right'); d.text_mode.setCurrentText('counter'); self.assertTrue(d.spins['number'].isVisible()); self.assertFalse(d.caret.isVisible())
            d.spins['number_decimals'].setValue(2); d.preview.repaint(); d.reject(); self.assertEqual(w.project.timeline[0],before)
            d=MotionEditor(w,w.project.timeline[0]); d.show(); d.shadow.setChecked(False); d.accept(); self.assertFalse(w.project.timeline[0].graphic_data['scene']['nodes'][0]['shadow']['enabled']); w.undo(); self.assertEqual(w.project.timeline[0],before)
            settings=ProjectSettingsDialog(w.project,w); self.assertGreaterEqual(settings.fps.findText('120'),0); settings.fps.setCurrentText('120'); self.assertEqual(settings.values()[1].fps,120); settings.reject()
        finally:w.close(); QThreadPool.globalInstance().waitForDone(10000); w.deleteLater(); app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()

if __name__=='__main__':unittest.main()
