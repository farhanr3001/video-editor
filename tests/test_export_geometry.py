import unittest
from dataclasses import asdict

from kinetic_cut.export_geometry import visible_source
from kinetic_cut.exporter import PRESETS, _target_size, build_command
from kinetic_cut.model import Crop, MediaItem, Project, TimelineItem, Transform


class ExportGeometryTests(unittest.TestCase):
    def scene(self):
        media=MediaItem('m','fixture.mp4','video','fixture',5,1920,1080,60,False)
        item=TimelineItem('v','m','video_1',0,1,
                          transform=Transform(x=-1.6853824074,y=.2019020833,scale=2.997))
        return Project(media=[media],timeline=[item]),media,item

    def graph(self,project):
        args=build_command(project,'fixture-output.mp4',PRESETS['TikTok · Fast'],
                           burn_captions=False,hardware='CPU',export_audio=False)
        return args[args.index('-filter_complex')+1]

    def test_reported_pan_retains_source_mapping_with_small_buffer(self):
        p,m,i=self.scene();lw,lh=_target_size(i,m,1080,1,1920)
        self.assertEqual((lw,lh),(10230,5754))
        rx,ry,rw,rh,sw,sh,cx,cy=visible_source(1920,1080,lw,lh,i.transform.x*1080,i.transform.y*1920,1080,1920)
        self.assertLess(sw,1200);self.assertLess(sh,2000)
        for x,y in ((0,0),(540,960),(1080,1920)):
            old_x=(x-(i.transform.x*1080-lw/2))*1920/lw
            old_y=(y-(i.transform.y*1920-lh/2))*1080/lh
            new_x=rx+(x-(cx-sw/2))*rw/sw
            new_y=ry+(y-(cy-sh/2))*rh/sh
            self.assertAlmostEqual(old_x,new_x,delta=.25)
            self.assertAlmostEqual(old_y,new_y,delta=.25)

    def test_edges_and_anisotropic_zoom_keep_placement(self):
        for cx,cy in ((540,960),(5000,4000),(-2500,-4000),(540,5000)):
            with self.subTest(centre=(cx,cy)):
                result=visible_source(1920,1080,14000,12000,cx,cy,1080,1920)
                self.assertIsNotNone(result)
                x,y,w,h,sw,sh,nx,ny=result
                self.assertTrue(all(v%2==0 for v in (x,y,w,h,sw,sh)))
                self.assertGreater(w,0);self.assertGreater(h,0)
                self.assertLessEqual(x+w,1920);self.assertLessEqual(y+h,1080)
                self.assertAlmostEqual(nx-sw/2,cx-7000+x*14000/1920)
                self.assertAlmostEqual(ny-sh/2,cy-6000+y*12000/1080)

    def test_fully_offscreen_and_tiny_sources_do_not_make_invalid_crop(self):
        for cx,cy in ((20000,960),(-20000,960),(540,20000),(540,-20000)):
            self.assertIsNone(visible_source(1920,1080,10230,5754,cx,cy,1080,1920))
        self.assertIsNone(visible_source(1,1,10230,5754,540,960,1080,1920))

    def test_large_normal_layer_is_sampled_without_mutating_project(self):
        p,m,i=self.scene();before=p.to_dict();graph=self.graph(p)
        self.assertIn('crop=210:366:1298:464,scale=1118:1950',graph)
        self.assertNotIn('scale=8192:',graph)
        self.assertEqual(p.to_dict(),before)

    def test_flips_precede_source_sampling(self):
        p,m,i=self.scene();i.transform.flip_horizontal=True;i.transform.flip_vertical=True
        graph=self.graph(p)
        self.assertIn('hflip,vflip,crop=210:366:1298:464',graph)

    def test_regular_layer_uses_established_full_source_chain(self):
        p,m,i=self.scene();i.transform.scale=1
        graph=self.graph(p);self.assertIn('scale=3414:1920',graph)
        self.assertNotIn('crop=210:366',graph)

    def test_complex_static_layers_keep_requested_dimensions(self):
        for changes in ('rotation','circle','effect','crop','alpha'):
            p,m,i=self.scene()
            if changes=='rotation':i.transform.rotation=13
            elif changes=='circle':i.transform.shape='circle'
            elif changes=='effect':i.effects=[dict(name='Gaussian Blur',enabled=True,horizontal=4,vertical=4)]
            elif changes=='crop':i.crop=Crop(0,0,.9,1)
            else:m.has_alpha=True
            with self.subTest(changes=changes):
                lw,lh=_target_size(i,m,1080,1,1920)
                graph=self.graph(p);self.assertIn(f'scale={lw}:{lh}',graph)
                self.assertNotIn('scale=8192:',graph)

    def test_disabled_effect_does_not_disable_bounded_sampling(self):
        p,m,i=self.scene();i.effects=[dict(name='Gaussian Blur',enabled=False)]
        self.assertIn('crop=210:366:1298:464',self.graph(p))
