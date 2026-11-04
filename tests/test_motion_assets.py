import json
import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication


class MotionAssetsAndEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_every_builtin_asset_validates_and_inserts(self):
        from kinetic_cut import motion_assets as A, motion as M, motion_fx as FX
        scene = M.validate(dict(version=1, canvas=[1080, 1920], nodes=[]))
        for name in A.BUILTIN:
            preview = M.validate(A.preview_scene(A.builtin(name)))
            self.assertEqual(FX.lint(preview), [], name)
            scene, group = A.insert(scene, name, 300, 400, 2.0)
            self.assertIn(group, {n['id'] for n in scene['nodes']})
        scene = M.validate(scene)
        ids = [n['id'] for n in scene['nodes']]
        self.assertEqual(len(ids), len(set(ids)))
        groups = [n for n in scene['nodes'] if n.get('name') == 'Word reveal']
        self.assertEqual((groups[0]['x'], groups[0]['y']), (300, 400))
        text = next(n for n in scene['nodes'] if n.get('parent') == groups[0]['id'])
        self.assertAlmostEqual(text['start'], 2.0)

    def test_capture_save_and_reload_user_asset(self):
        from kinetic_cut import motion_assets as A, motion as M
        from kinetic_cut.motion_geometry import layout
        with tempfile.TemporaryDirectory() as folder, patch('kinetic_cut.config.CONFIG_DIR', folder):
            scene = M.validate(dict(version=1, canvas=[1080, 1920], nodes=[]))
            scene, group = A.insert(scene, 'Label pill', 500, 900, 3.0)
            asset = A.capture(scene, [group], 'My pill', 3.0)
            self.assertEqual(asset['category'], 'Mine'); self.assertTrue(asset['nodes'])
            A.save(asset)
            self.assertIn('My pill', [a['name'] for a in A.catalogue()])
            scene, again = A.insert(scene, 'My pill', 100, 100, 0)
            entries, _ = layout(M.validate(scene), 0)
            bounds = entries[again]['hit'].boundingRect()
            self.assertFalse(bounds.isEmpty())
            self.assertAlmostEqual(bounds.center().x(), 100, places=4)
            self.assertAlmostEqual(bounds.center().y(), 100, places=4)
            self.assertTrue(A.delete('My pill')); self.assertNotIn('My pill', [a['name'] for a in A.catalogue()])

    def test_rich_text_runs_mix_styles_in_one_layer(self):
        from kinetic_cut import motion as M, motion_frame as F
        node = M.validate(dict(version=1, canvas=[1080, 1920], nodes=[dict(id='t', kind='text', text='Cuts the dead air.', font='Arial', font_size=80, bold=False,
              runs=[dict(text='Cuts the '), dict(text='dead air.', italic=True, size=1.2, fill='#ff0000')])]))['nodes'][0]
        styles = M.run_styles(node)
        self.assertEqual(len(styles), len(node['text'])); self.assertTrue(styles[-1][2]); self.assertFalse(styles[0][2])
        plain = M.text_parts(node['text'], 'Arial', 80, False, 'none', 0)
        rich = M.text_parts(node['text'], 'Arial', 80, False, 'none', 0, 'center', False, styles)
        self.assertGreater(rich[0].boundingRect().width(), plain[0].boundingRect().width())
        frame = F.frame(dict(version=1, canvas=[1080, 1920], nodes=[node]), 1., (540, 960))
        self.assertTrue(frame['items'])

    def test_stack_layout_reflows_as_children_start(self):
        from kinetic_cut import motion as M
        scene = M.validate(dict(version=1, canvas=[1080, 1920], nodes=[
            dict(id='g', kind='group', x=540, y=900, layout=dict(type='stack', gap=20, reflow=.4)),
            dict(id='a', parent='g', kind='rectangle', width=100, height=100),
            dict(id='b', parent='g', kind='rectangle', width=100, height=200, start=1.)]))
        by_id = {n['id']: n for n in scene['nodes']}
        before = M.stack_offset(by_id['a'], .5, by_id); after = M.stack_offset(by_id['a'], 2., by_id)
        self.assertAlmostEqual(before[1], 0, places=3)
        self.assertAlmostEqual(after[1], -(20 + 200) / 2, places=3)
        self.assertAlmostEqual(M.stack_offset(by_id['b'], 2., by_id)[1], 100 + 20 + 200 / 2 - 320 / 2, places=3)
        mid = M.stack_offset(by_id['a'], 1.2, by_id)[1]
        self.assertTrue(after[1] < mid < before[1])

    def test_video_layer_validates_and_reaches_the_gpu_description(self):
        from kinetic_cut import motion as M, motion_frame as F
        from kinetic_cut.motion_video import url, parse, source_time
        scene = M.validate(dict(version=1, canvas=[1080, 1920], nodes=[dict(id='v', kind='video', source='C:/clips/a b.mp4', in_point=2, speed=2, start=1,
                                                                            width=800, height=450, shadow=dict(enabled=True, opacity=30))]))
        self.assertAlmostEqual(source_time(scene['nodes'][0], 2.), 4.)
        items = F.frame(scene, 2., (540, 960))['items']
        video = items[0]['items'][0] if items[0]['k'] == 'layer' else items[0]
        self.assertEqual(video['k'], 'video'); self.assertAlmostEqual(video['t'], 4.)
        self.assertEqual(parse(url('C:/clips/a b.mp4', 4.)[len('image://motionvideo/'):]), ('C:/clips/a b.mp4', 4.))
        with self.assertRaises(ValueError): M.validate(dict(version=1, canvas=[10, 10], nodes=[dict(id='v', kind='video', speed=0)]))

    def test_scene_and_sequence_operations(self):
        from kinetic_cut import motion as M
        from kinetic_cut.motion_editing import apply
        scene = M.validate(dict(version=1, canvas=[1080, 1920], nodes=[dict(id='t1', kind='text', text='a'), dict(id='t2', kind='text', text='b')]))
        scene = apply(scene, [dict(op='add_scene', id='s1', start=0, end=2, children=['t1']), dict(op='add_scene', id='s2', start=0, end=3, handoff='slide', children=['t2']),
                              dict(op='sequence', ids=['s1', 's2'], start=1, overlap=.2), dict(op='insert_asset', name='Loop line', x=540, y=1200, time=.5)])
        by_id = {n['id']: n for n in scene['nodes']}
        self.assertEqual(by_id['t1']['parent'], 's1'); self.assertAlmostEqual(by_id['s1']['start'], 1); self.assertAlmostEqual(by_id['s2']['start'], 2.8)
        self.assertIn('blur_x', by_id['s2']['keyframes'])
        self.assertTrue(any(n.get('name') == 'Loop line' for n in scene['nodes']))

    def test_mcp_tools_and_cue_limit(self):
        from kinetic_cut.assistant_api import TOOLS
        from kinetic_cut.motion_audio import MAX_CUES, validate
        names = {t['name'] for t in TOOLS}
        for name in ('get_motion_contact_sheet', 'motion_scene_file', 'list_fonts', 'add_motion_sound_cues', 'motion_assets'): self.assertIn(name, names)
        self.assertEqual(MAX_CUES, 128)
        with self.assertRaises(ValueError): validate([dict(id=str(n), source='a.wav', time=0) for n in range(129)])

    def test_editor_canvas_uses_the_gpu_renderer(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / 'kinetic_cut' / 'motion_preview.py').read_text(encoding='utf-8')
        self.assertIn("Surface(self,'GpuMotionEditor.qml')", source); self.assertIn('def publish', source)
        self.assertTrue((Path(__file__).resolve().parents[1] / 'assets' / 'qml' / 'GpuMotionEditor.qml').exists())


if __name__ == '__main__':
    unittest.main()
