import os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
APP=QApplication.instance() or QApplication([])
from kinetic_cut import motion,motion_templates as T,motion_fx as fx

class TemplateTests(unittest.TestCase):
    def test_every_template_validates_lints_clean_and_renders(self):
        for name,t in T.TEMPLATES.items():
            scene,params,d=T.build(name,{},(540,960))
            scene=motion.validate(scene)
            self.assertEqual(fx.lint(scene),[],name)
            image=motion.draw(scene,d*.5,(54,96),30)
            self.assertEqual((image.width(),image.height()),(54,96))
    def test_rejects_bad_input(self):
        for args in (('Nope',{}),('Stat Counter',{'bogus':1}),('Stat Counter',{'value':'x'}),('Light Trail Draw',{'shape':'Cube'}),('Lower Third',{'color':'notacolour'})):
            with self.assertRaises(ValueError):T.build(*args)
    def test_duration_rescales_timing(self):
        scene,_,d=T.build('Lower Third',{},(540,960),8)
        self.assertEqual(d,8)
        keys=[k['time'] for n in scene['nodes'] for c in n.get('keyframes',{}).values() for k in c]
        self.assertGreater(max(keys),7)
    def test_catalog_lists_all(self):
        self.assertEqual(set(T.catalog()),set(T.TEMPLATES)); self.assertGreaterEqual(len(T.TEMPLATES),19)


class EditOpsTests(unittest.TestCase):
    def scene(self):
        s,_,_=T.build('Lower Third',{},(540,960)); return motion.validate(s)
    def test_animate_and_pulse(self):
        from kinetic_cut.motion_editing import apply,ANIMATIONS
        s=self.scene()
        for preset in ANIMATIONS:
            out=apply(s,[dict(op='animate',id='bar',preset=preset,start=1,duration=.5)]); self.assertTrue(out['nodes'][0]['keyframes'])
        out=apply(s,[dict(op='pulse',id='accent',channel='scale',times=[1,2,3],base=1,peak=1.3,attack=.05,decay=.2)])
        keys=[k['time'] for k in next(n for n in out['nodes'] if n['id']=='accent')['keyframes']['scale']]
        self.assertEqual(keys,sorted(keys)); self.assertGreaterEqual(len(keys),9)
        with self.assertRaises(ValueError):apply(s,[dict(op='animate',id='bar',preset='nope')])
        with self.assertRaises(ValueError):apply(s,[dict(op='pulse',id='bar',channel='bogus',times=[1])])
    def test_scene_settings_accepts_camera_and_post(self):
        from kinetic_cut.motion_editing import apply
        out=apply(self.scene(),[dict(op='scene_settings',values=dict(camera=dict(zoom=1.2),post=dict(bloom=.5),floor=dict(y=1500),background=dict(color='#000000')))])
        self.assertEqual(out['camera']['zoom'],1.2)
    def test_timeline_clock_conversion(self):
        from kinetic_cut.assistant_api import EditorAPI as Assistant
        class I:in_point=10.;start=4.;speed=2.
        ops=Assistant._composition_clock(I,[dict(op='pulse',id='x',clock='timeline',times=[5,6],attack=.1)])
        self.assertEqual(ops[0]['times'],[12.,14.]); self.assertAlmostEqual(ops[0]['attack'],.2); self.assertNotIn('clock',ops[0])
if __name__=='__main__':unittest.main()
