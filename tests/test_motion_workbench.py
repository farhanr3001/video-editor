import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QThreadPool
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.motion import draw,validate,curve
from kinetic_cut.motion_presets import PRESETS,build,update,parameters
from kinetic_cut.motion_editing import apply
from kinetic_cut.motion_geometry import layout
from kinetic_cut.model import Project,TimelineItem,Transform

def pixels(image):
    image=image.convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()

class MotionWorkbenchModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_all_recipes_are_editable_bounded_and_inside_safe_area(self):
        for size in ((1080,1920),(1920,1080),(320,568)):
            for name in PRESETS:
                data=build(name,size); self.assertLessEqual(len(data['scene']['nodes']),8)
                entries,_=layout(data['scene'],1.5)
                rect=entries['card']['hit'].boundingRect()
                self.assertGreaterEqual(rect.left(),size[0]*.05-1)
                self.assertLessEqual(rect.right(),size[0]*.95+1)
                if size[1]>size[0]:self.assertLessEqual(rect.right(),size[0]*.88+1)
                self.assertLessEqual(rect.bottom(),size[1]*.82)
                self.assertTrue(pixels(draw(data['scene'],1.5,(320,568)))[:,:,3].any())
    def test_exact_single_line_range_and_green_prices(self):
        data=build('Price Range Card'); node=next(n for n in data['scene']['nodes'] if n['id']=='value')
        self.assertEqual(node['text'],'$375K - $430K'); self.assertNotIn('\n',node['text']); self.assertEqual(node['fill'],'#56f29a')
        self.assertEqual(build('Product Price Card')['parameters']['value'],200000)
        for raw in ({'value':float('nan')},{'value':True},{'unknown':3},{'background':'not-a-colour'},{'image':4}):
            with self.assertRaises(ValueError):parameters('Product Price Card',raw)
        with self.assertRaises(ValueError):build('Price Range Card',values={'value_max':100})
        from kinetic_cut.motion_text import counter_text
        count=build('Animated Total',values={'animation':'Count'}); node=next(n for n in count['scene']['nodes'] if n['id']=='value')
        self.assertEqual(counter_text(node,1.5),'$151K')
    def test_parameter_patch_preserves_custom_layers_curves_and_masks(self):
        data=build('Product Price Card'); data['scene']['nodes'][0]['rotation']=12
        panel=next(n for n in data['scene']['nodes'] if n['id']=='panel'); panel['mask']={'width':900,'height':250}; panel['keyframes']={'rotation':[dict(time=0,value=2),dict(time=1,value=8)]}
        data['scene']['nodes'].append(dict(id='custom',kind='ellipse',width=12,height=12,x=20,y=20))
        original=copy.deepcopy(data); result=update(data,{'value':75000,'background':'#2d240b'})
        self.assertEqual(data,original); self.assertEqual(result['scene']['nodes'][0]['rotation'],12)
        normalized=next(n for n in validate(original['scene'])['nodes'] if n['id']=='panel')
        changed=next(n for n in result['scene']['nodes'] if n['id']=='panel'); self.assertEqual(changed['mask'],normalized['mask']); self.assertEqual(changed['keyframes'],normalized['keyframes'])
        self.assertEqual(result['scene']['nodes'][-1],validate(original['scene'])['nodes'][-1])
        self.assertEqual(next(n for n in result['scene']['nodes'] if n['id']=='value')['text'],'$75K')
    def test_roll_settles_pixel_exactly_to_text_and_is_seek_deterministic(self):
        node=dict(id='v',kind='text',text='$375K - $430K',x=200,y=70,font_size=34,fill='#56f29a',text_mode='rolling',entry_duration=1)
        scene=validate(dict(canvas=[400,140],nodes=[node])); before=copy.deepcopy(scene)
        early=pixels(draw(scene,.3,(400,140))); self.assertTrue(early[:,:,3].any())
        normal=copy.deepcopy(scene); normal['nodes'][0]['text_mode']='none'
        np.testing.assert_array_equal(pixels(draw(scene,1,(400,140))),pixels(draw(normal,1,(400,140))))
        draw(scene,.8,(400,140)); np.testing.assert_array_equal(early,pixels(draw(scene,.3,(400,140)))); self.assertEqual(scene,before)
    def test_image_contain_cover_and_legacy_stretch_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'tall.png'; image=QImage(20,80,QImage.Format_RGBA8888); image.fill(Qt.red); image.save(str(path))
            scene=validate(dict(canvas=[200,200],nodes=[dict(id='image',kind='image',source=str(path),x=100,y=100,width=100,height=100)]))
            legacy=pixels(draw(scene,0,(200,200))); scene['nodes'][0]['image_fit']='contain'; contained=pixels(draw(scene,0,(200,200)))
            self.assertGreater(np.count_nonzero(legacy[:,:,3]),np.count_nonzero(contained[:,:,3])*3)
            _,x=np.where(contained[:,:,3]>128); self.assertAlmostEqual(x.max()-x.min()+1,25,delta=1)
            scene['nodes'][0]['image_fit']='cover'; np.testing.assert_array_equal(legacy,pixels(draw(scene,0,(200,200))))
    def test_geometry_matches_parent_rotation_and_masks(self):
        scene=validate(dict(canvas=[240,240],nodes=[dict(id='parent',kind='group',x=120,y=120,rotation=30,scale=1.2,scale_y=.8,mask={'width':70,'height':70}),dict(id='shape',parent='parent',kind='rectangle',x=10,y=10,width=80,height=80)]))
        entries,_=layout(scene,0); yy,xx=np.where(pixels(draw(scene,0,(240,240)))[:,:,3]>240)
        rect=entries['shape']['hit'].boundingRect(); self.assertAlmostEqual(rect.center().x(),(xx.min()+xx.max())/2,delta=2); self.assertAlmostEqual(rect.center().y(),(yy.min()+yy.max())/2,delta=2)
    def test_atomic_layer_and_key_operations_reject_cycles_and_preserve_source(self):
        data=build('Chapter Title'); before=copy.deepcopy(data['scene'])
        result=apply(before,[dict(op='add_layer',node={'id':'custom','kind':'rectangle'}),dict(op='set_key',id='custom',channel='x',time=.2,value=100,interpolation='Bezier',bezier=[.2,0,.6,1]),dict(op='set_key',id='custom',channel='x',time=.2,value=120)])
        self.assertEqual(before,data['scene']); self.assertEqual(len(result['nodes'][-1]['keyframes']['x']),1)
        self.assertEqual(result['nodes'][-1]['keyframes']['x'][0]['value'],120)
        with self.assertRaises(ValueError):apply(before,[dict(op='update_layer',id='card',values={'parent':'heading'})])
        with self.assertRaises(ValueError):apply(before,[dict(op='remove_layer',id='missing')])
        self.assertEqual(apply(before,[dict(op='remove_layer',id='card')])['nodes'],[])

class MotionWorkbenchEditorTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        # These unit tests own editor gestures, not subprocess shutdown. Native
        # workflow diagnostics below separately exercise the default process path.
        self.compositor=patch.dict('os.environ',{'KINETIC_COMPOSITION_PROCESS':'0'}); self.compositor.start()
        self.app=QApplication.instance() or QApplication([]); self.w=MainWindow(); self.w.show(); self.w.autosave_timer.stop()
        self.data=build('Product Price Card',(320,568),4)
        self.item=TimelineItem('motion','','video_1',0,4,role='graphic',graphic_type='Motion Composition',graphic_data=self.data,transform=Transform(.5,.5))
        p=Project(timeline=[self.item]); p.settings.width=320; p.settings.height=568; p.settings.fps=30; self.w.set_project(p)
        from kinetic_cut.motion_editor import MotionEditor
        self.d=MotionEditor(self.w,self.item); self.d.show(); self.app.processEvents()
    def tearDown(self):
        cache=self.w.preview.composition_cache; executor=cache.executor
        if cache.future:cache.future.result(10)
        self.d.reject(); self.w.close()
        if executor:executor.shutdown(wait=True,cancel_futures=True)
        QThreadPool.globalInstance().waitForDone(10000); self.d.deleteLater(); self.w.deleteLater(); self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
        self.compositor.stop()
    def test_navigation_uses_source_time_and_playback_pauses_at_end(self):
        self.d.select_node('card'); self.d.channel.setCurrentText('scale'); self.d.navigate('key',1); self.assertAlmostEqual(self.d.position,.35)
        self.d.navigate('frame',-1); self.assertAlmostEqual(self.d.position,.35-1/30,places=3)
        self.d.navigate('start'); self.assertEqual(self.d.position,0); self.d.navigate('end'); self.assertLess(self.d.position,4)
        self.d.toggle(); self.d._play_started-=10; self.d.tick(); self.assertFalse(self.d.timer.isActive())
        self.d.original.in_point=.0176
        self.assertAlmostEqual(self.d.timeline.at(self.d.timeline.x(.0176+2.3/30)),.0176+2/30)
    def test_preview_click_move_resize_inspector_and_local_undo(self):
        self.d.seek(1.5); self.d.select_node('heading'); preview=self.d.preview
        entry=preview.geometry()[0]['heading']; center=preview.from_scene(entry['hit'].boundingRect().center()).toPoint(); before=copy.deepcopy(self.d.scene)
        QTest.mousePress(preview,Qt.LeftButton,Qt.NoModifier,center); QTest.mouseMove(preview,center+QPoint(12,9)); QTest.mouseRelease(preview,Qt.LeftButton,Qt.NoModifier,center+QPoint(12,9))
        self.assertEqual(self.d.node_id,'heading'); self.assertNotEqual(self.d.scene,before); self.assertAlmostEqual(self.d.spins['x'].value(),curve(self.d.node(),'x',1.5),places=2)
        self.d.local_history(-1); self.assertEqual(self.d.scene,before); self.d.local_history(1); self.assertNotEqual(self.d.scene,before)
        point=preview.handles(preview.geometry()[0]['heading'])['2'].toPoint(); size=curve(self.d.node(),'font_size',1.5)
        QTest.mousePress(preview,Qt.LeftButton,Qt.NoModifier,point); QTest.mouseMove(preview,point+QPoint(12,12)); QTest.mouseRelease(preview,Qt.LeftButton,Qt.NoModifier,point+QPoint(12,12)); self.assertGreater(curve(self.d.node(),'font_size',1.5),size)
        self.assertEqual(self.item.graphic_data,self.data) # editor remains transactional
    def test_diamond_retime_is_frame_snapped_and_undoable(self):
        self.d.select_node('card'); self.d.channel.setCurrentText('scale'); timeline=self.d.timeline
        index=timeline.rows.index(('card','scale')); key=self.d.node()['keyframes']['scale'][1]; before=copy.deepcopy(self.d.scene)
        point=QPoint(round(timeline.x(key['time'])),round(timeline.row_rect(index).center().y()))
        QTest.mousePress(timeline.viewport(),Qt.LeftButton,Qt.NoModifier,point); QTest.mouseMove(timeline.viewport(),point+QPoint(40,0)); QTest.mouseRelease(timeline.viewport(),Qt.LeftButton,Qt.NoModifier,point+QPoint(40,0))
        self.assertNotEqual(self.d.scene,before); times=[k['time'] for k in self.d.node()['keyframes']['scale']]; self.assertAlmostEqual(times[-1]*30,round(times[-1]*30))
        self.assertIsNotNone(self.d.selected_key())
        self.d.local_history(-1); self.assertEqual(self.d.scene,before)
    def test_preview_zoom_pan_are_view_only_and_cached(self):
        self.d.seek(1.5); preview=self.d.preview; before=copy.deepcopy(self.d.scene)
        self.d.preview_zoom.setValue(2); self.assertEqual(preview.view_scale,2)
        point=QPoint(preview.width()//2,preview.height()//2)
        with patch('kinetic_cut.motion_preview.draw',wraps=draw) as renderer:
            preview.repaint(); count=renderer.call_count
            QTest.mousePress(preview,Qt.MiddleButton,Qt.NoModifier,point); QTest.mouseMove(preview,point+QPoint(15,12)); QTest.mouseRelease(preview,Qt.MiddleButton,Qt.NoModifier,point+QPoint(15,12)); preview.repaint()
            self.assertEqual(renderer.call_count,count)
        self.assertEqual(self.d.scene,before); self.assertEqual(preview.pan,QPointF(15,12))
        preview.fit(); self.assertEqual(preview.view_scale,1); self.assertEqual(preview.pan,QPointF())
    def test_mcp_preset_edit_revision_lock_undo_and_exact_preview(self):
        self.d.reject(); api=self.w.assistant_connection.api
        state=api.call_get_motion_composition('motion',1.5); self.assertEqual(state['preset'],'Product Price Card')
        image=api.call_get_motion_preview('motion',1.5); self.assertEqual(image['_mcp_content'][1]['mimeType'],'image/png')
        result=api.call_configure_motion_preset(state['revision'],'motion',{'value':75000}); self.assertTrue(result['undoable'])
        self.assertEqual(self.w.project.timeline[0].graphic_data['parameters']['value'],75000)
        with self.assertRaises(ValueError):api.call_configure_motion_preset(state['revision'],'motion',{'value':100})
        self.w.undo(); self.assertEqual(self.w.project.timeline[0].graphic_data['parameters']['value'],200000)
        state=api.call_get_state('summary'); self.w.project.track_states['video_1']={'locked':True}
        from kinetic_cut.assistant_api import revision
        with self.assertRaises(ValueError):api.call_edit_motion_composition(revision(self.w.project),'motion',[dict(op='remove_layer',id='card')])
    def test_inspector_and_catalogue_add_preset_as_normal_editable_composition(self):
        self.d.reject(); self.w.select_item('motion'); control=self.w.inspector.motion_preset
        control.controls['value'].setValue(120000); self.assertEqual(self.w.project.timeline[0].graphic_data['parameters']['value'],120000)
        added=self.w.add_graphic_object('Price Range Card',start=5,properties={'value':75000,'value_max':100000})
        self.assertEqual(added.graphic_type,'Motion Composition'); self.assertEqual(added.graphic_data['preset'],'Price Range Card'); self.assertEqual(added.transform.y,.5)
        self.assertEqual(next(n for n in added.graphic_data['scene']['nodes'] if n['id']=='value')['text'],'$75K - $100K')
        before=self.w.project.to_dict()
        with self.assertRaises(ValueError):self.w.add_graphic_object('Price Range Card',track='__new_video',properties={'value_max':1})
        self.assertEqual(self.w.project.to_dict(),before)
        added.in_point=1; self.w.select_item(added.id); self.w.inspector.edit_graphic_duration(5)
        self.assertEqual(next(n for n in added.graphic_data['scene']['nodes'] if n['id']=='card')['end'],6)

if __name__=='__main__':unittest.main()
