import unittest
import numpy as np
from PySide6.QtGui import QImage,QGuiApplication
from kinetic_cut.motion import validate,draw,geometry,node_origin
from kinetic_cut.motion_svg import parse
from kinetic_cut import motion_fx as fx

def px(image):
    image=image.convertToFormat(QImage.Format_RGBA8888)
    return np.frombuffer(image.constBits(),np.uint8).reshape(image.height(),image.bytesPerLine()//4,4)[:,:image.width()].copy()

def scene(nodes,**extra):
    return validate(dict(canvas=[200,200],nodes=nodes,**extra))

def rect(**kw):
    base=dict(id='r',kind='rectangle',x=100,y=100,width=40,height=40,fill='#ff0000');base.update(kw);return base

class FxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QGuiApplication.instance() or QGuiApplication([])

    def test_svg_path_absolute_relative_arc_and_errors(self):
        p=parse('M10 10 L 30 10 l 0 20 H 5 v -5 C 1 2 3 4 5 6 S 7 8 9 10 Q 1 1 2 2 T 3 3 Z')
        self.assertEqual(p[0],['M',10,10]); self.assertEqual(p[2],['L',30,30]); self.assertEqual(p[-1],['Z'])
        arc=parse('M0 0 A 10 10 0 0 1 20 0')
        self.assertTrue(all(c[0] in 'MC' for c in arc)); self.assertAlmostEqual(arc[-1][5],20); self.assertAlmostEqual(arc[-1][6],0)
        for bad in ('L 1 2','M 1','M 1 2 x 3','M 1 2 Z 5'):
            with self.assertRaises(ValueError):parse(bad)
        s=scene([dict(id='p',kind='path',path_svg='M0 0 L 50 50',stroke='#fff')]); self.assertEqual(s['nodes'][0]['path'][1],['L',50,50])

    def test_validation_rejects_bad_effect_fields(self):
        for node in (rect(blend='lighten'),rect(glow=5),rect(dash=[0]),rect(cap='x'),rect(emitter=5),rect(kind='emitter',emitter=dict(rate=-1)),
                     rect(follow=dict(path='missing')),rect(runs=[{}]),rect(kind='polyline',points=[[0,0]])):
            with self.assertRaises(ValueError,msg=str(node)):scene([node])
        with self.assertRaises(ValueError):scene([rect()],camera=5)
        with self.assertRaises(ValueError):scene([rect()],post=dict(tint='nope'))

    def test_lint_names_unknown_fields_with_hint(self):
        s=scene([rect(dsh=[4,4])]); warnings=fx.lint(s); self.assertTrue(any("'dsh'" in w and 'dash' in w for w in warnings))
        self.assertEqual(fx.lint(scene([rect(dash=[4,4])])),[])

    def test_blur_softens_edges_and_glow_adds_halo(self):
        sharp=px(draw(scene([rect()]),0,(200,200)))
        soft=px(draw(scene([rect(keyframes=dict(blur=[dict(time=0,value=8)]))]),0,(200,200)))
        self.assertEqual(sharp[100,70,3],0); self.assertGreater(soft[100,70,3],0); self.assertLess(soft[100,100,3],256)
        glow=px(draw(scene([rect(glow=dict(radius=10,intensity=1.5))]),0,(200,200)))
        self.assertGreater(glow[100,72,3],0); self.assertEqual(glow[100,100,3],255)
        none=px(draw(scene([rect(glow=dict(enabled=False))]),0,(200,200))); self.assertEqual(none[100,72,3],0)

    def test_blend_modes_change_result(self):
        base=rect(id='b',fill='#808080',width=100,height=100)
        add=px(draw(scene([base,rect(fill='#808080',blend='add')]),0,(200,200)))
        normal=px(draw(scene([base,rect(fill='#808080')]),0,(200,200)))
        self.assertGreater(int(add[100,100,0]),int(normal[100,100,0])+50)

    def test_mask_invert_and_feather(self):
        m=dict(kind='rectangle',width=40,height=40)
        inv=px(draw(scene([rect(width=120,height=120,mask=dict(m,invert=True))]),0,(200,200)))
        self.assertEqual(inv[100,100,3],0); self.assertEqual(inv[100,60,3],255)
        soft=px(draw(scene([rect(width=120,height=120,mask=dict(kind='rectangle',width=80,height=80,feather=8))]),0,(200,200)))
        self.assertGreater(soft[100,100,3],240); self.assertTrue(0<soft[100,60,3]<255)

    def test_trim_window_follow_and_stretch(self):
        path=dict(id='p',kind='path',path=[['M',0,0],['L',100,0]],stroke='#fff',stroke_width=4,fill='none',x=50,y=100)
        s=scene([path]); full=geometry(s['nodes'][0],0); self.assertAlmostEqual(full.boundingRect().width(),100,delta=1)
        s=scene([dict(path,keyframes=dict(trim_start=[dict(time=0,value=.5)]))]); self.assertAlmostEqual(geometry(s['nodes'][0],0).boundingRect().left(),50,delta=2)
        s=scene([path,dict(id='b',kind='ellipse',width=10,height=10,follow=dict(path='p'),keyframes=dict(follow_at=[dict(time=0,value=0),dict(time=1,value=1)]))])
        by={n['id']:n for n in s['nodes']}; self.assertAlmostEqual(node_origin(by['b'],0,by)[0],50,delta=1); self.assertAlmostEqual(node_origin(by['b'],1,by)[0],150,delta=1)
        self.assertAlmostEqual(node_origin(by['b'],.5,by)[0],100,delta=1)
        s=scene([rect(stretch=dict(amount=.01,max=1),keyframes=dict(x=[dict(time=0,value=20),dict(time=1,value=180)]))])
        moving=px(draw(s,.5,(200,200))); self.assertGreater((moving[...,3]>128).sum(),40*40)

    def test_extra_shapes_and_dash(self):
        for node in (rect(kind='polygon',sides=5,inner=.4),rect(kind='polyline',points=[[0,0],[40,0],[40,40]],smooth=True,fill='none',stroke='#fff'),rect(kind='grid',cell=10,stroke='#fff',fill='none')):
            self.assertFalse(geometry(scene([node])['nodes'][0],0).isEmpty())
        dashed=px(draw(scene([dict(id='l',kind='path',path=[['M',20,100],['L',180,100]],stroke='#fff',stroke_width=6,fill='none',dash=[2,2],cap='flat')]),0,(200,200)))
        row=dashed[100,20:180,3]; self.assertTrue((row==0).any() and (row>200).any())

    def test_emitter_is_deterministic_and_bounded(self):
        e=dict(id='e',kind='emitter',x=100,y=100,emitter=dict(bursts=[dict(time=.1,count=60)],seed=3,life=[.5,.5],speed=[50,100],gravity=0))
        s=scene([e]); a=px(draw(s,.3,(200,200))); b=px(draw(s,.3,(200,200)))
        self.assertTrue((a==b).all()); self.assertGreater((a[...,3]>0).sum(),20)
        self.assertEqual((px(draw(s,.9,(200,200)))[...,3]>0).sum(),0)
        self.assertEqual((px(draw(s,0,(200,200)))[...,3]>0).sum(),0)

    def test_trail_draws_behind_a_moving_dot(self):
        n=dict(id='d',kind='ellipse',width=10,height=10,fill='#fff',y=100,keyframes=dict(x=[dict(time=0,value=20),dict(time=1,value=180)]),trail=dict(length=.4,width=6))
        img=px(draw(scene([n]),.8,(200,200))); self.assertGreater(img[100,120,3],0)
        off=px(draw(scene([{k:v for k,v in n.items() if k!='trail'}]),.8,(200,200))); self.assertEqual(off[100,120,3],0)

    def test_camera_parallax_by_depth(self):
        far=rect(id='f',x=100,y=60,width=20,height=20,depth=0); near=rect(id='n',x=100,y=140,width=20,height=20,depth=1)
        s=scene([far,near],camera=dict(x=40))
        img=px(draw(s,0,(200,200)))
        self.assertEqual(img[60,100,3],255); self.assertEqual(img[140,100,3],0); self.assertEqual(img[140,60,3],255)

    def test_floor_reflection_and_background(self):
        s=scene([rect(y=60,width=30,height=30)],floor=dict(y=120,opacity=.8,fade=100,blur=0),background=dict(color='#101010'))
        img=px(draw(s,0,(200,200)))
        self.assertEqual(tuple(img[5,5,:3]),(16,16,16)); self.assertGreater(img[180,100,0],40); self.assertLess(img[180,100,0],255)

    def test_post_bloom_vignette_grain_tint_and_determinism(self):
        base=scene([rect(width=30,height=30,fill='#ffffff')],background=dict(color='#202020'))
        plain=px(draw(base,0,(200,200)))
        bloom=px(draw(dict(base,post=fx.validate_scene_extras and dict(bloom=1,bloom_threshold=.3,bloom_radius=12)),0,(200,200)))
        self.assertGreater(int(bloom[100,70,0]),int(plain[100,70,0]))
        s=scene([rect(width=30,height=30)],background=dict(color='#808080'),post=dict(vignette=.8,grain=1,tint='#ff0000',tint_amount=1))
        a=px(draw(s,.2,(200,200))); b=px(draw(s,.2,(200,200)))
        self.assertTrue((a==b).all()); self.assertLess(int(a[2,2,0]),int(a[100,70,0]))
        c=px(draw(s,.4,(200,200))); self.assertFalse((a==c).all())
        self.assertLess(int(a[100,70,2]),40)

    def test_rich_text_runs_colours_and_blur_in(self):
        t=dict(id='t',kind='text',x=100,y=100,font_size=40,text_mode='character',stagger=.05,entry_duration=.3,entry_blur=10,fill='#0000ff',
               runs=[dict(text='AB',fill='#ff0000'),dict(text='CD')])
        s=scene([t]); self.assertEqual(s['nodes'][0]['text'],'ABCD')
        img=px(draw(s,1,(200,200))); red=(img[...,0]>200)&(img[...,2]<80)&(img[...,3]>200); blue=(img[...,2]>200)&(img[...,0]<80)&(img[...,3]>200)
        self.assertTrue(red.any() and blue.any()); xs=np.nonzero(red)[1].mean(),np.nonzero(blue)[1].mean(); self.assertLess(xs[0],xs[1])
        self.assertTrue(draw(s,.05,(200,200)).width()==200)

    def test_tilt_and_radial_gradient_render(self):
        s=scene([rect(width=60,height=60,rotate_y=40,gradient=['#fff','#000'],gradient_type='radial')])
        img=px(draw(s,0,(200,200))); self.assertGreater(img[100,100,3],200)

if __name__=='__main__':unittest.main()
