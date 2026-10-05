import copy,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import av,numpy as np
from PySide6.QtCore import Qt,QEvent,QThreadPool
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,TimelineItem,MediaItem,Transform
from kinetic_cut.motion import validate,draw,geometry,curve
from kinetic_cut.easing import MODES,ease,controls
from kinetic_cut.keyframes import put,evaluated,shift,stretch
from kinetic_cut.native_animation import frame,prepare

def pixels(image):
    image=image.convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()

def scene():
    return validate(dict(canvas=[160,284],nodes=[dict(id='shape',kind='rectangle',x=40,y=142,width=30,height=30,fill='#ff0000',keyframes={'x':[dict(time=0,value=40,interpolation='Bezier',bezier=[.2,0,.3,1]),dict(time=1,value=120)]})]))

def composition(duration=1.2):
    return TimelineItem('scene','','video_1',0,duration,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':scene()},transform=Transform(.5,.5))

class MotionCurveTests(unittest.TestCase):
    def test_easing_endpoints_and_overshoot(self):
        for mode in MODES:
            self.assertEqual(ease(0,mode),0); self.assertEqual(ease(1,mode),1)
        self.assertGreater(ease(.65,'Back Out'),1); self.assertGreater(ease(.2,'Elastic Out'),1)
        self.assertLess(ease(.5,'Ease In'),.5); self.assertGreater(ease(.5,'Ease Out'),.5)
    def test_bezier_inverse_time_and_controls(self):
        self.assertAlmostEqual(ease(.5,'Bezier',[.25,.25,.75,.75]),.5,places=6)
        self.assertGreater(ease(.5,'Bezier',[.2,0,.3,1]),.7)
        for values in ([.8,0,.2,1],[0,float('nan'),1,1],[0,8,1,1],[1,2]):
            with self.assertRaises(ValueError):controls(values)
    def test_curve_roundtrip_update_cut_and_retime(self):
        item=composition(); put(item,'x',0,.2,'Bezier'); item.keyframes['x'][0]['bezier']=[.15,-.1,.45,1.2]; put(item,'x',1,.8)
        put(item,'x',0,.25,'Bezier'); self.assertEqual(item.keyframes['x'][0]['bezier'],[.15,-.1,.45,1.2])
        before=evaluated(item,.6).transform.x; original=copy.deepcopy(item)
        shift(item,.3); self.assertAlmostEqual(evaluated(item,.3).transform.x,before)
        stretch(item,.5); self.assertAlmostEqual(evaluated(item,.15).transform.x,before)
        p=Project(timeline=[original]); self.assertEqual(Project.from_dict(p.to_dict()).timeline[0].keyframes,original.keyframes)

class MotionRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_parent_transform_opacity_and_animated_mask(self):
        s=validate(dict(canvas=[160,284],nodes=[dict(id='parent',kind='group',x=80,y=142,opacity=50,mask=dict(kind='rectangle',width=60,height=60,keyframes={'width':[dict(time=0,value=10),dict(time=1,value=60)]})),dict(id='child',parent='parent',kind='rectangle',width=60,height=60,fill='#ff0000')]))
        first=pixels(draw(s,0,(160,284))); last=pixels(draw(s,1,(160,284)))
        self.assertAlmostEqual(int(first[142,80,3]),128,delta=1); self.assertEqual(first[142,100,3],0); self.assertGreater(last[142,100,3],120)
        self.assertGreater(np.count_nonzero(last[:,:,3]),np.count_nonzero(first[:,:,3])*4)
    def test_trim_and_compatible_path_morph(self):
        s=validate(dict(nodes=[dict(id='p',kind='path',path=[['M',0,0],['L',100,0]],path_to=[['M',0,0],['L',200,100]],morph=.5,trim=.5)]))
        path=geometry(s['nodes'][0],0); self.assertAlmostEqual(path.length(),(150**2+50**2)**.5/2,delta=.2)
        s['nodes'][0]['path_to']=[['M',0,0],['Q',1,2,3,4]]
        with self.assertRaises(ValueError):validate(s)
    def test_character_word_reveals_and_preview_scale(self):
        for mode in ('character','word'):
            s=validate(dict(canvas=[160,284],nodes=[dict(id='text',kind='text',text='MAKE TIME',x=80,y=142,font_size=25,text_mode=mode,stagger=.2,entry_duration=.15)]))
            zero=pixels(draw(s,0,(160,284))); early=pixels(draw(s,.25,(160,284))); late=pixels(draw(s,3,(160,284)))
            self.assertFalse(zero[:,:,3].any()); self.assertGreater(np.count_nonzero(late[:,:,3]),np.count_nonzero(early[:,:,3]))
            large=pixels(draw(s,3,(320,568))); yy,xx=np.where(late[:,:,3]>128); ly,lx=np.where(large[:,:,3]>128)
            self.assertAlmostEqual(lx.mean()/2,xx.mean(),delta=1); self.assertAlmostEqual(ly.mean()/2,yy.mean(),delta=1)
    def test_motion_blur_averages_premultiplied_alpha(self):
        s=scene(); s['nodes'][0]['keyframes']['x']=[dict(time=0,value=20),dict(time=1,value=140)]
        s['motion_blur']={'samples':4,'shutter':360}; result=pixels(draw(s,.5,(160,284),10))
        self.assertTrue(np.any((result[:,:,3]>0)&(result[:,:,3]<255)))
        visible=result[:,:,3]>20; self.assertTrue(np.all(result[:,:,0][visible]>245)); self.assertTrue(np.all(result[:,:,1][visible]==0))
    def test_validation_rejects_cycles_unknown_parent_bad_mask_and_nan(self):
        invalid=[dict(nodes=[dict(id='a',kind='group',parent='a')]),dict(nodes=[dict(id='a',kind='group',parent='b')]),dict(nodes=[dict(id='a',kind='rectangle',x=float('nan'))]),dict(nodes=[dict(id='a',kind='rectangle',mask=dict(keyframes={'width':[{}]}))]),dict(canvas=[0,284]),dict(nodes=[dict(id='a',kind='path',path=[['C',2,3]])])]
        for s in invalid:
            with self.assertRaises(ValueError):validate(s)
    def test_split_trim_retime_keep_composition_time(self):
        item=composition(2); p=Project(timeline=[item]); p.settings.width=160; p.settings.height=284; p.settings.fps=10
        original=copy.deepcopy(item); left,right=p.split(item.id,.4)
        np.testing.assert_array_equal(pixels(frame(p,right,.2)),pixels(frame(p,original,.6)))
        p.trim_items([right.id],.2,'left'); np.testing.assert_array_equal(pixels(frame(p,right,.1)),pixels(frame(p,original,.7)))
        p.retime_items([right.id],2); np.testing.assert_array_equal(pixels(frame(p,right,.1)),pixels(frame(p,original,.8)))
    def test_lossless_overlay_cache_alpha_asset_invalidation_and_cancel(self):
        from kinetic_cut.cache_manager import clear,scan
        with tempfile.TemporaryDirectory() as directory,patch('kinetic_cut.config.CACHE_DIR',Path(directory)):
            p=Project(timeline=[composition()]); p.settings.width=160; p.settings.height=284; p.settings.fps=10; original=p.to_dict()
            stage=prepare(p,None,None); path=Path(stage.media[-1].path); stamp=path.stat().st_mtime_ns
            self.assertTrue(stage.media[-1].has_alpha); self.assertEqual(p.to_dict(),original)
            self.assertEqual(Path(prepare(p,None,None).media[-1].path).stat().st_mtime_ns,stamp)
            with av.open(str(path)) as container:
                decoded=list(container.decode(video=0)); np.testing.assert_array_equal(decoded[5].to_ndarray(format='rgba'),pixels(frame(p,p.timeline[0],.5)))
            cancel=threading.Event(); cancel.set(); p.timeline[0].duration=2
            with self.assertRaisesRegex(RuntimeError,'cancelled'):prepare(p,None,cancel)
            self.assertFalse(list(Path(directory).rglob('pending-*'))); self.assertEqual(scan(Path(directory))['motion-renders'][0],1)
            self.assertEqual(clear(['motion-renders'],Path(directory))[0],1)
    def test_image_change_invalidates_frame_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'image.png'; image=QImage(8,8,QImage.Format_RGBA8888); image.fill(Qt.red); image.save(str(path))
            s=validate(dict(canvas=[160,284],nodes=[dict(id='pic',kind='image',source=str(path),x=80,y=142,width=30,height=30)]))
            self.assertGreater(pixels(draw(s,0,(160,284)))[142,80,0],250)
            image.fill(Qt.blue); image.save(str(path)); self.assertGreater(pixels(draw(s,0,(160,284)))[142,80,2],250)
    def test_portable_scene_assets_and_missing_export_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory); source=directory/'asset.png'; image=QImage(10,10,QImage.Format_RGBA8888); image.fill(Qt.blue); image.save(str(source))
            item=composition(); item.graphic_data['scene']['nodes'].append(dict(id='image',kind='image',source=str(source)))
            p=Project(timeline=[item],portable_media=True); path=directory/'portable.kcut'; p.save(path)
            raw=json.loads(path.read_text()); self.assertEqual(raw['timeline'][0]['graphic_data']['scene']['nodes'][-1]['source'],'asset.png')
            moved=directory/'moved'; moved.mkdir(); source.rename(moved/source.name); path.rename(moved/path.name); loaded=Project.load(moved/path.name)
            self.assertEqual(loaded.timeline[0].graphic_data['scene']['nodes'][-1]['source'],str(moved/source.name))
            (moved/source.name).unlink()
            with patch('kinetic_cut.config.CACHE_DIR',directory/'cache'),self.assertRaisesRegex(ValueError,'image is missing'):prepare(loaded,None,None)
    def test_export_native_alpha_pixels_and_title_keys(self):
        from kinetic_cut.exporter import export,ExportPreset
        from kinetic_cut.model import CaptionStyle
        with tempfile.TemporaryDirectory() as directory,patch('kinetic_cut.config.CACHE_DIR',Path(directory)/'cache'):
            p=Project(timeline=[composition()]); p.settings.width=160; p.settings.height=284; p.settings.fps=10
            out=Path(directory)/'motion.mp4'; export(p,str(out),ExportPreset('test','h264',4,128,'test'),False,'CPU',export_audio=False)
            with av.open(str(out)) as container:
                frames=list(container.decode(video=0)); result=frames[5].to_ndarray(format='rgb24')
            expected=pixels(frame(p,p.timeline[0],.5)); yy,xx=np.where(result[:,:,0]>150); ey,ex=np.where(expected[:,:,0]>150)
            self.assertAlmostEqual(xx.mean(),ex.mean(),delta=1); self.assertAlmostEqual(yy.mean(),ey.mean(),delta=1)
            title=TimelineItem('t','','video_1',0,1.2,role='title',title_text='MOVE',title_style=CaptionStyle(size=24,animation='none',position_y=.5))
            put(title,'x',0,.25); put(title,'x',1,.75); p.timeline=[title]
            first=pixels(frame(p,title,0)); last=pixels(frame(p,title,1)); self.assertGreater(np.where(last[:,:,3]>100)[1].mean(),np.where(first[:,:,3]>100)[1].mean()+60)
            export(p,str(Path(directory)/'title.mp4'),ExportPreset('test','h264',4,128,'test'),False,'CPU',export_audio=False)
            with av.open(str(Path(directory)/'title.mp4')) as container:
                frames=list(container.decode(video=0)); red=frames[8].to_ndarray(format='rgb24')
            expected=pixels(frame(p,title,.8)); yy,xx=np.where(red[:,:,:3].max(axis=2)>150); ey,ex=np.where(expected[:,:,:3].max(axis=2)>150)
            self.assertAlmostEqual(xx.mean(),ex.mean(),delta=2)
    def test_real_media_bezier_export_and_window(self):
        from kinetic_cut.rendergraph import command
        from kinetic_cut.exporter import PRESETS
        from kinetic_cut.process import run
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'box.png'; image=QImage(30,30,QImage.Format_RGB32); image.fill(Qt.white); image.save(str(source))
            item=TimelineItem('v','m','video_1',0,2,transform=Transform(.2,.5,.1)); put(item,'x',0,.2,'Bezier'); put(item,'x',2,.8)
            p=Project(media=[MediaItem('m',str(source),'image','box',2,30,30)],timeline=[item]); p.settings.width=160; p.settings.height=284; p.settings.fps=30
            for window in (None,(.5,1.5)):
                target=Path(directory)/('full.mp4' if window is None else 'window.mp4')
                result=run(command(p,str(target),next(iter(PRESETS.values())),False,'CPU',export_audio=False,window=window),capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace')[-3000:])
                with av.open(str(target)) as container:frames=list(container.decode(video=0))
                for n in (0,15):
                    rgb=frames[n].to_ndarray(format='rgb24'); yy,xx=np.where(rgb.mean(axis=2)>150)
                    local=n/30+(window[0] if window else 0); self.assertAlmostEqual(xx.mean(),160*evaluated(item,local).transform.x-.5,delta=1.5)
    def test_mcp_transaction_scene_schema_and_rejection(self):
        from kinetic_cut.assistant_api import edited,TOOLS
        p=Project(); values=dict(role='graphic',graphic_type='Motion Composition',graphic_data={'scene':scene()})
        stage,ids=edited(p,[dict(op='add',collection='timeline',values=values)])
        self.assertEqual(stage.timeline[0].transform.y,.5); self.assertFalse(p.timeline)
        values['graphic_data']['scene']['nodes'][0]['parent']='missing'
        with self.assertRaises(ValueError):edited(stage,[dict(op='update',collection='timeline',id=ids[0],values=values)])
        self.assertEqual(stage.timeline[0].graphic_data['scene']['nodes'][0].get('parent',''),'')
        self.assertIn('Motion Composition',next(t for t in TOOLS if t['name']=='add_graphic')['inputSchema']['properties']['graphic_type']['enum'])
    def test_simultaneous_advanced_media_curves_use_safe_graph_file(self):
        from kinetic_cut.rendergraph import command
        from kinetic_cut.exporter import export,PRESETS
        from kinetic_cut.keyframes import maximum
        from kinetic_cut.config import CACHE_DIR
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.png'; image=QImage(160,90,QImage.Format_RGB32); image.fill(Qt.white); image.save(str(source))
            item=TimelineItem('v','m','video_1',0,1,transform=Transform(.35,.5,.2))
            for name,a,b in [('x',.35,.65),('y',.4,.6),('scale',.2,.4),('scale_y',.2,.4),('rotation',0,40),('opacity',100,70)]:put(item,name,0,a,'Bezier'); put(item,name,1,b)
            p=Project(media=[MediaItem('m',str(source),'image','source',1,160,90)],timeline=[item]); p.settings.width=320; p.settings.height=180; p.settings.fps=30
            target=Path(directory)/'curves.mp4'; args=command(p,str(target),PRESETS['TikTok · Fast'],False,'CPU',export_audio=False)
            self.assertGreater(len(subprocess.list2cmdline(args)),32767)
            export(p,str(target),PRESETS['TikTok · Fast'],False,'CPU',export_audio=False)
            with av.open(str(target)) as video:self.assertEqual(len(list(video.decode(video=0))),30)
            self.assertFalse(list((CACHE_DIR/'render-logs').glob('filter-*')))
            item.keyframes['scale'][0]['interpolation']='Back Out'; self.assertGreater(maximum(item,'scale'),.4)

class MotionEditorTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.app=QApplication.instance() or QApplication([]); self.w=MainWindow(); self.w.show(); self.w.autosave_timer.stop()
        p=Project(timeline=[composition()]); p.settings.width=160; p.settings.height=284; self.w.set_project(p)
    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); self.w.deleteLater(); self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
    def test_editor_cancel_save_one_undo_and_stale_lock(self):
        from kinetic_cut.motion_editor import MotionEditor
        d=MotionEditor(self.w,self.w.project.timeline[0]); d.change('fill','#00ff00'); d.reject(); self.assertEqual(self.w.project.timeline[0].graphic_data['scene']['nodes'][0]['fill'],'#ff0000')
        before=len(self.w._history); d=MotionEditor(self.w,self.w.project.timeline[0]); d.change('fill','#00ff00'); d.accept(); self.assertEqual(len(self.w._history),before+1)
        self.w.undo(); self.assertEqual(self.w.project.timeline[0].graphic_data['scene']['nodes'][0]['fill'],'#ff0000')
        d=MotionEditor(self.w,self.w.project.timeline[0]); self.w.project.track_states['video_1']={'locked':True}
        with patch('kinetic_cut.motion_editor.QMessageBox.warning') as warning:d.accept(); warning.assert_called_once()
        d.reject()
    def test_duplicate_parent_branch_and_edit_bezier(self):
        from kinetic_cut.motion_editor import MotionEditor
        item=self.w.project.timeline[0]; item.graphic_data['scene']['nodes'].insert(0,dict(id='group',kind='group')); item.graphic_data['scene']['nodes'][1]['parent']='group'
        d=MotionEditor(self.w,item); d.node_id='group'; d.duplicate(); self.assertEqual(len(d.scene['nodes']),4); validate(d.scene)
        d.node_id='shape'; d.channel.setCurrentText('x'); d.seek(0); d.bezier[0].setValue(.15); d.add_key(); self.assertEqual(d.selected_key()['bezier'][0],.15); d.reject()
    def test_native_keyframe_editor_and_default_title_position(self):
        from kinetic_cut.keyframe_editor import KeyframeEditor
        d=KeyframeEditor(self.w,self.w.project.timeline[0]); d.add_key('scale'); d.change_mode('Bezier'); d.item.keyframes['scale'][0]['bezier']=[.1,0,.5,1.1]; d.graph_changed()
        self.assertEqual(d.item.keyframes['scale_y'][0]['bezier'],[.1,0,.5,1.1]); d.reject()
        from kinetic_cut.visuals import draw_caption
        from kinetic_cut.model import Caption,CaptionStyle
        from PySide6.QtCore import QRectF
        title=TimelineItem('t','','video_1',0,2,role='title',title_text='TITLE',title_style=CaptionStyle(size=30,animation='none'))
        self.w.project.playhead=.5
        expected=QImage(160,284,QImage.Format_RGBA8888); expected.fill(Qt.transparent); painter=QPainter(expected); painter.setRenderHints(QPainter.Antialiasing|QPainter.TextAntialiasing|QPainter.SmoothPixmapTransform)
        draw_caption(painter,self.w.project,Caption('t',0,2,'TITLE',title.title_style,False,True),QRectF(0,0,160,284)); painter.end()
        np.testing.assert_array_equal(pixels(frame(self.w.project,title,.5)),pixels(expected))

if __name__=='__main__':unittest.main()
