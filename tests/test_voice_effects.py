import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,MediaItem,TimelineItem
from kinetic_cut.effects import CATALOG,compatible
from kinetic_cut.voice_effects import NAMES,CONTROLS,default_effect,filter_chain
from kinetic_cut.rendergraph import audio_filters
from kinetic_cut.process import run


class VoiceEffectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def fixture(self):
        return Project(media=[MediaItem('m','missing.wav','audio','Voice',3,has_audio=True)],
                       timeline=[TimelineItem('a','m','audio_1',0,3),TimelineItem('b','m','audio_1',3,3)])

    def test_catalog_and_audio_only_lock_guards(self):
        p=self.fixture(); video=TimelineItem('v','m','video_1',0,3)
        for name in NAMES:
            self.assertIn(name,CATALOG['Audio']); self.assertTrue(compatible(name,p.timeline[0],p))
            self.assertFalse(compatible(name,video,p))
        p.track_states['audio_1']['locked']=True
        self.assertFalse(compatible(NAMES[0],p.timeline[0],p))

    def test_zero_strength_and_disabled_are_exact_bypass(self):
        item=self.fixture().timeline[0]; original=audio_filters(item)
        for name in NAMES:
            effect=default_effect(name); effect['enabled']=False; item.effects=[effect]
            self.assertEqual(audio_filters(item),original)
            effect['enabled']=True; effect['amount']=0
            self.assertEqual(audio_filters(item),original)

    def test_malformed_values_are_finite_and_bounded(self):
        for name in NAMES:
            effect=default_effect(name); effect.update({key:float('nan') for key,*_ in CONTROLS[name]})
            effect['amount']='invalid'; chain=filter_chain(effect)
            self.assertNotIn('nan',chain); self.assertTrue(chain)
            effect['amount']=float('inf'); self.assertNotIn('inf',filter_chain(effect))

    def test_effects_persist_and_stacked_order_is_preserved(self):
        p=self.fixture(); p.timeline[0].effects=[default_effect(name) for name in NAMES]
        restored=Project.from_dict(p.to_dict()); self.assertEqual(restored.timeline[0].effects,p.timeline[0].effects)
        chain=audio_filters(restored.timeline[0]); self.assertLess(chain.index('asetrate='),chain.index('highpass='))
        self.assertIn('afade=t=out',audio_filters(TimelineItem('x','m','audio_1',0,3,fade_out=.2,effects=[default_effect(NAMES[0])])))

    def test_real_dsp_pitch_duration_channels_and_robot_frequency(self):
        item=self.fixture().timeline[0]
        def samples(effect):
            item.effects=[effect]
            result=run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=240:duration=3:sample_rate=48000','-af',audio_filters(item),'-f','f32le','-'],capture_output=True,check=True)
            data=np.frombuffer(result.stdout,dtype=np.float32).reshape(-1,2)
            self.assertEqual(data.shape,(144000,2)); self.assertTrue(np.isfinite(data).all())
            self.assertLessEqual(float(np.max(np.abs(data))),1.)
            return data
        for name in NAMES:
            effect=default_effect(name); data=samples(effect)
            spectrum=np.abs(np.fft.rfft(data[24000:120000,0])); frequencies=np.fft.rfftfreq(96000,1/48000)
            peak=frequencies[np.argmax(spectrum)]
            if name in ('Chipmunk Voice','Deep Voice'):
                self.assertAlmostEqual(peak,240*2**(effect['semitones']/12),delta=2)
            if name=='Robot Voice':self.assertTrue(abs(peak-185)<2 or abs(peak-295)<2)
        item.speed=1.5; item.duration=2
        result=run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','sine=frequency=240:duration=3:sample_rate=48000','-af',audio_filters(item),'-f','f32le','-'],capture_output=True,check=True)
        self.assertEqual(len(result.stdout),96000*2*4)

    def test_inspector_multiselect_reset_bypass_remove_and_undo(self):
        from kinetic_cut.ui import MainWindow
        w=MainWindow(); p=self.fixture()
        try:
            w.transport.processed_audio=Mock(return_value='')
            w.set_project(p); w.timeline.select_ids({'a','b'},'a')
            w.apply_effect('Walkie Talkie'); self.assertTrue(all(i.effects for i in p.timeline))
            inspector=w.inspector; panel=inspector.voice_panel
            self.assertFalse(panel.isHidden()); panel.rows['Walkie Talkie','drive'].spin.setValue(5)
            self.assertEqual([i.effects[0]['drive'] for i in p.timeline],[5,5])
            panel.rows['Walkie Talkie','low_cut'].reset.click()
            self.assertEqual([i.effects[0]['low_cut'] for i in p.timeline],[450,450])
            panel.reset.click(); self.assertEqual([i.effects[0]['drive'] for i in p.timeline],[2.5,2.5])
            inspector.effect_enabled.click(); self.assertTrue(all(not i.effects[0]['enabled'] for i in p.timeline))
            inspector.remove_effect(); self.assertTrue(all(not i.effects for i in p.timeline))
            w.undo(); self.assertTrue(all(i.effects for i in w.project.timeline))
        finally:w.close(); w.deleteLater(); self.app.processEvents()

    def test_processed_preview_eligibility_uses_shared_voice_filters(self):
        from kinetic_cut.transport import TimelineTransport
        from kinetic_cut.voice_effects import PROCESSED_NAMES
        self.assertTrue(set(NAMES)<=PROCESSED_NAMES)
        source=Path(tempfile.gettempdir())/'kinetic-nonexistent-voice-fixture.wav'
        item=TimelineItem('a','m','audio_1',0,2,effects=[default_effect(NAMES[0])])
        media=MediaItem('m',str(source),'audio','Voice',2,has_audio=True)
        owner=Mock(); owner.settings={'ffmpeg':'ffmpeg'}; owner.start_worker=Mock()
        transport=Mock(window=owner,audio_pending=set(),audio_failed=set(),_audio_source_signatures={})
        with tempfile.TemporaryDirectory() as temp,patch('kinetic_cut.config.CACHE_DIR',Path(temp)):
            self.assertEqual(TimelineTransport.processed_audio(transport,item,media),'')
        self.assertEqual(owner.start_worker.call_count,1)
        self.assertEqual(len(transport.audio_pending),1)


if __name__=='__main__':unittest.main()
