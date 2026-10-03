import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,Transform
from kinetic_cut.compounds import create,content,update_asset,render_asset,validate

class CompoundTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.image=self.root/'source.png'; image=QImage(160,90,QImage.Format_RGB32); image.fill(QColor('#dd7733')); image.save(str(self.image))
        self.p=Project(media=[MediaItem('m',str(self.image),'image','Source',5,160,90)],timeline=[TimelineItem('v','m','video_1',2,1,transform=Transform(.5,.5,1))],captions=[Caption('c',2.1,2.8,'HELLO')])
        self.p.settings.width=160; self.p.settings.height=90; self.p.settings.fps=30
    def tearDown(self):self.temp.cleanup()
    def test_mixed_selection_local_timing_properties_and_persistence(self):
        self.p.timeline.append(TimelineItem('a','m','audio_1',2,1,gain_db=-6))
        self.p.timeline[0].keyframes={'scale':[{'time':.2,'value':1.5,'interpolation':'Smooth'}]}
        before=copy.deepcopy(self.p.to_dict()); asset,clips=create(self.p,{'v','a'},{'c'},'My compound')
        self.assertEqual(len(clips),2); self.assertEqual(clips[0].link_id,clips[1].link_id)
        self.assertEqual(clips[0].start,2); self.assertEqual(clips[0].duration,1)
        child=Project.from_dict(asset.compound); self.assertEqual(child.timeline[0].start,0)
        self.assertEqual(child.timeline[0].keyframes,before['timeline'][0]['keyframes'])
        self.assertAlmostEqual(child.captions[0].start,.1); self.assertFalse(self.p.captions)
        loaded=Project.from_dict(json.loads(json.dumps(self.p.to_dict())))
        self.assertEqual(loaded.media_by_id(asset.id).compound,asset.compound)
        child.timeline[0].duration=3; update_asset(asset,child)
        self.assertEqual(asset.duration,3); self.assertEqual(clips[0].duration,1)
    def test_locked_and_intervening_unselected_clip_safe(self):
        self.p.track_states['video_1']={'locked':True}; before=self.p.to_dict()
        with self.assertRaises(ValueError):create(self.p,{'v'},{'c'},'locked')
        self.assertEqual(self.p.to_dict(),before)
        self.p.track_states['video_1']={}; self.p.timeline.extend([TimelineItem('v2','m','video_1',5,1),TimelineItem('keep','m','video_1',3,1)])
        asset,clips=create(self.p,{'v','v2'},set(),'Span')
        self.assertNotEqual(clips[0].track,'video_1'); self.assertIsNotNone(self.p.item_by_id('keep'))
    def test_nested_navigation_root_save_and_parent_undo(self):
        from kinetic_cut.ui import MainWindow
        w=MainWindow(); w.autosave_timer.stop()
        with patch.object(w.compounds,'request_caches'):
            try:
                w.set_project(self.p); w.timeline.select_ids({'v'},'v'); w.compounds.new('Outer')
                outer=next(i for i in w.project.timeline if w.project.media_by_id(i.media_id).compound)
                w.compounds.open(outer.id); w.project.timeline[0].duration=2; w.model_changed()
                document=w.compounds.root(); self.assertEqual(document.item_by_id(outer.id).duration,1)
                self.assertEqual(document.media_by_id(outer.media_id).duration,2)
                target=self.root/'nested.kcut'; document.save(target); self.assertEqual(Project.load(target).media_by_id(outer.media_id).duration,2)
                w.timeline.select_ids({'v'},'v'); w.compounds.new('Inner')
                inner=next(i for i in w.project.timeline if w.project.media_by_id(i.media_id).compound)
                w.compounds.open(inner.id); self.assertEqual(len(w.compounds.stack),2)
                w.compounds.back(0); self.assertFalse(w.compounds.stack); self.assertEqual(w.project.item_by_id(outer.id).duration,1)
                w.undo(); self.assertEqual(w.project.media_by_id(outer.media_id).duration,1)
                w.redo(); self.assertEqual(w.project.media_by_id(outer.media_id).duration,2)
            finally:w.close(); w.deleteLater(); QApplication.processEvents()
    def test_lossless_nested_cache_real_export(self):
        from kinetic_cut.process import run
        asset,clips=create(self.p,{'v'},{'c'},'Inner')
        # Cache represents child-local time; its duration is independent of parent placement.
        path=render_asset(asset); self.assertTrue(Path(path).is_file())
        result=run(['ffmpeg','-v','error','-i',path,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True)
        self.assertEqual(len(result.stdout),160*90*3)
        outer,_=create(self.p,{i.id for i in clips},set(),'Outer'); second=render_asset(outer)
        result2=run(['ffmpeg','-v','error','-i',second,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True)
        self.assertEqual(result.stdout,result2.stdout)
    def test_cycle_depth_rejected(self):
        data={'media':[{'id':'same','compound':{'media':[]}}]}
        with self.assertRaises(ValueError):validate(data,('same',))
    def test_cache_keeps_transparent_uncovered_pixels(self):
        from kinetic_cut.process import run
        self.p.captions=[]; self.p.timeline[0].transform.scale=.5
        asset,_=create(self.p,{'v'},set(),'Transparent inset')
        result=run(['ffmpeg','-v','error','-i',render_asset(asset),'-frames:v','1','-f','rawvideo','-pix_fmt','rgba','-'],capture_output=True,check=True)
        self.assertEqual(result.stdout[3],0); self.assertEqual(result.stdout[(45*160+80)*4+3],255)
    def test_compound_thumbnail_immediate_and_rendered(self):
        asset,clips=create(self.p,{'v'},{'c'},'Thumb test')
        # Immediate inheritance at creation time:
        self.assertTrue(asset.thumbnail)
        self.assertTrue(Path(asset.thumbnail).exists())
        self.assertEqual(asset.thumbnail,str(self.image))
        # After rendering the cache file:
        target=render_asset(asset)
        self.assertTrue(Path(target).is_file())
        update_asset(asset,Project.from_dict(asset.compound))
        self.assertTrue(asset.thumbnail.endswith('.jpg'))
        self.assertTrue(Path(asset.thumbnail).exists())

class PlaybackUiTests(unittest.TestCase):
    def test_bottom_aligned_subtitle_and_toggle_feedback(self):
        from kinetic_cut.ui import MainWindow
        w=MainWindow(); w.autosave_timer.stop()
        try:
            w.set_project(Project(captions=[Caption('c',0,1,'Caption')]))
            t=w.timeline; t.resize(900,450); t.subtitle_extent=130
            self.assertAlmostEqual(t.track_rect('subtitle_1').bottom(),t.section_rect('subtitle_1').bottom())
            t.subtitle_extent=100
            self.assertAlmostEqual(t.track_rect('subtitle_1').bottom(),t.section_rect('subtitle_1').bottom())
            w.caption_focus.button.setChecked(True); self.assertEqual(w.caption_focus.button.text(),'Return to Video')
            w.caption_focus.button.setChecked(False); self.assertEqual(w.caption_focus.button.text(),'Caption Focus')
        finally:w.close(); w.deleteLater(); QApplication.processEvents()
