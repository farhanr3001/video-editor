"""GPU motion graphics: frame description, preview layer wiring and the no-CPU-raster guarantee."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PySide6.QtCore import QRectF
from PySide6.QtGui import QGuiApplication
from kinetic_cut import motion as M, motion_frame as F, motion_templates as T
from kinetic_cut.motion_gpu import MotionLayers, is_motion, placement, opacity_of

app = QGuiApplication.instance() or QGuiApplication([])


def scene(name='Kinetic Statement'):
    s, _, d = T.build(name, {}, [1080, 1920], T.TEMPLATES[name]['duration'])
    return M.validate(s), d


def fake_item(s, **extra):
    t = SimpleNamespace(x=.5, y=.5, anchor_x=0, anchor_y=0, rotation=0, scale=1, effective_scale_y=1)
    return SimpleNamespace(id='g1', role='graphic', graphic_type='Motion Composition', graphic_data={'scene': s}, start=0., duration=5., in_point=0., speed=1.,
                           fade_in=0, fade_out=0, opacity=100., transform=t, **extra)


class GpuMotionTests(unittest.TestCase):
    def test_every_template_has_a_complete_gpu_frame_description(self):
        for name in T.TEMPLATES:
            s, d = scene(name)
            f = F.frame(s, d * .6, (540, 960))
            self.assertEqual(f['unsupported'], [], name)
            self.assertTrue(f['items'], name)

    def test_frame_description_is_far_cheaper_than_cpu_rasterisation(self):
        import time
        s, d = scene('Light Trail Draw'); F.frame(s, 1., (540, 960))
        a = time.perf_counter(); [F.frame(s, 1 + n * .016, (540, 960)) for n in range(10)]; gpu = (time.perf_counter() - a) / 10
        a = time.perf_counter(); M.draw_uncached(s, 1.3, (540, 960)); cpu = time.perf_counter() - a
        self.assertLess(gpu * 4, cpu)

    def test_matrices_include_device_scale_and_camera(self):
        s, d = scene('Lower Third'); f = F.frame(s, d * .6, (540, 960)); big = F.frame(s, d * .6, (1080, 1920))
        first=lambda fr:next(i for i in fr['items'] if 'matrix' in i)
        self.assertAlmostEqual(first(f)['matrix'][0] * 2, first(big)['matrix'][0], places=4)

    def test_preview_motion_layers_do_not_call_the_cpu_renderer(self):
        s, d = scene('Chat Story'); item = fake_item(s,track='video_1',keyframes={})
        project = SimpleNamespace(settings=SimpleNamespace(width=1080, height=1920, fps=30))
        layer = Mock(); surface = SimpleNamespace(create=Mock(return_value=layer), item=Mock(return_value=None))
        motion = MotionLayers(surface)
        with patch.object(M, 'draw', side_effect=AssertionError('CPU renderer used')), patch.object(M, 'draw_uncached', side_effect=AssertionError('CPU renderer used')):
            shown = motion.update([item], project, 1.2, QRectF(0, 0, 540, 960), {item.track:3})
        self.assertEqual(shown, {'motion:g1'}); surface.create.assert_called_once_with('GpuMotion.qml', None)
        values = {c.args[0]: c.args[1] for c in layer.setProperty.call_args_list}
        self.assertTrue(values['frame']['items']); self.assertAlmostEqual(values['k'], .5)
        motion.update([], project, 1.2, QRectF(0, 0, 540, 960), {}); layer.setVisible.assert_called_with(False)

    def test_is_motion_and_fades(self):
        s, _ = scene(); item = fake_item(s); self.assertTrue(is_motion(item))
        item.role = 'title'; self.assertFalse(is_motion(item))
        item.role = 'graphic'; item.fade_in = 1.; self.assertAlmostEqual(opacity_of(item, .5), .5)

    def test_placement_centres_the_scene_on_the_frame(self):
        s, _ = scene(); item = fake_item(s); project = SimpleNamespace(settings=SimpleNamespace(width=1080, height=1920, fps=30))
        m = placement(item, project, QRectF(0, 0, 540, 960)); p = m.map(__import__('PySide6.QtCore', fromlist=['QPointF']).QPointF(270, 480))
        self.assertAlmostEqual(p.x(), 270, places=3); self.assertAlmostEqual(p.y(), 480, places=3)

    def test_shader_sources_are_compiled(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / 'assets' / 'shaders'
        for n in ('motion_post', 'motion_bright', 'motion_bloom', 'motion_add', 'motion_mask'):
            self.assertTrue((root / (n + '.frag.qsb')).exists(), n)

    def test_export_stage_and_qml_files_exist_and_stage_imports(self):
        from pathlib import Path
        import kinetic_cut.motion_gpu_render as R
        root = Path(__file__).resolve().parents[1] / 'assets' / 'qml'
        for n in ('GpuMotion.qml', 'GpuMotionList.qml', 'GpuMotionStage.qml'): self.assertTrue((root / n).exists(), n)
        self.assertTrue(hasattr(R, 'MotionStage'))

    def test_export_producer_sends_motion_graphics_to_the_gpu_stage(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / 'kinetic_cut' / 'export_preview_source.py').read_text(encoding='utf-8')
        self.assertIn('MotionStage', text); self.assertIn('is_motion(graphic)', text)

    def test_fallback_export_preparation_uses_the_gpu_producer_not_the_cpu_painter(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / 'kinetic_cut' / 'native_animation.py').read_text(encoding='utf-8')
        self.assertIn('gpu_frames(project,item,count', text); self.assertIn('--preview-effect-source', text)
        from kinetic_cut.native_animation import is_motion_graphic
        s, _ = scene(); self.assertTrue(is_motion_graphic(fake_item(s)))

    def test_compatibility_transitions_use_the_gpu_stage(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / 'kinetic_cut'
        text = (root / 'transition_export.py').read_text(encoding='utf-8')
        self.assertIn('gpu_transition_stage import Client', text); self.assertIn('gpu.composite(', text)
        self.assertIn('gpu_transition', (root / 'export_preview_source.py').read_text(encoding='utf-8'))
        import kinetic_cut.gpu_transition_stage as G
        self.assertTrue(hasattr(G, 'TransitionStage') and hasattr(G, 'Client') and hasattr(G, 'serve'))

    def test_graphic_transitions_are_baked_into_the_native_stream(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / 'kinetic_cut'
        ge = (root / 'gpu_export.py').read_text(encoding='utf-8'); ms = (root / 'motion_export_stream.py').read_text(encoding='utf-8')
        pv = (root / 'export_preview_source.py').read_text(encoding='utf-8')
        self.assertIn('_graphic_pair', ge); self.assertIn('ALL_NAMES', ge); self.assertIn('graphic_layers(project,native_items,directory,graphic_pairs)', ge)
        self.assertIn('graphic_transitions', ms); self.assertIn('graphic_transitions', pv); self.assertIn('render_transition', pv)
        from kinetic_cut.motion_gpu_render import MotionStage
        self.assertTrue(hasattr(MotionStage, 'render_transition'))

    def test_directional_blur_and_entry_colour(self):
        from pathlib import Path
        from kinetic_cut import motion as M, motion_frame as F
        from kinetic_cut.motion_templates import k
        self.assertIn('blur_x', M.CHANNELS); self.assertIn('blur_y', M.CHANNELS)
        scene = M.validate(dict(version=1, canvas=[400, 400], nodes=[
            dict(id='r', kind='rectangle', x=200, y=200, width=100, height=60, fill='#ffffff', keyframes=dict(blur_x=k((0, 30), (1, 0)))),
            dict(id='t', kind='text', text='ab cd', x=200, y=100, font='Arial', font_size=40, fill='#000000', text_mode='word', stagger=.3, entry_duration=.4, entry_color='#ff0000')]))
        d = F.frame(scene, .1, (400, 400), 30)
        blur = [i for i in d['items'] if i['k'] == 'dblur']
        self.assertTrue(blur and blur[0]['dx'] > 20 and blur[0]['dy'] == 0 and blur[0]['items'][0]['k'] == 'layer')
        self.assertFalse([i for i in F.frame(scene, 1.5, (400, 400), 30)['items'] if i['k'] == 'dblur'])
        words = [i for i in d['items'] if i['k'] == 'path' and i.get('fill')]
        self.assertTrue(any(w['fill']['color'].lower().startswith('#') for w in words))
        root = Path(__file__).resolve().parents[1] / 'assets'
        self.assertTrue((root / 'shaders' / 'motion_dirblur.frag.qsb').exists()); self.assertIn('dblur', (root / 'qml' / 'GpuMotionList.qml').read_text())

    def test_text_outlines_are_cleaned_and_scale_animations_are_uniform(self):
        from PySide6.QtGui import QPainterPath, QFont
        from PySide6.QtCore import QPointF
        from kinetic_cut import motion_frame as F, motion_templates as T
        from kinetic_cut.motion_editing import ANIMATIONS
        p = QPainterPath(); p.addText(QPointF(0, 0), QFont('Arial', 40), 'g')
        self.assertTrue(F.text_svg(p).startswith('M')); self.assertIs(F.text_svg(p), F.text_svg(p))
        scene, _, _ = T.build('Iris Wipe', {}, [1080, 1920], .8)
        mask = scene['nodes'][0]['mask']['keyframes']
        self.assertEqual([k['value'] for k in mask['scale']], [k['value'] for k in mask['scale_y']])
        node = {'id': 'a', 'scale': 1.0, 'scale_y': 1.0}
        self.assertIn('scale', ANIMATIONS['pop_in'](node, 0, .3, 1))


if __name__ == '__main__':
    unittest.main()
