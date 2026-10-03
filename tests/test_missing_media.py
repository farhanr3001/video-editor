import copy
import tempfile
import unittest
from pathlib import Path
from dataclasses import asdict
from unittest.mock import patch
from kinetic_cut.model import Project,MediaItem,TimelineItem
from kinetic_cut import missing_media as mm

class MissingMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); mm._missing.clear()
    def tearDown(self):self.tmp.cleanup(); mm._missing.clear()
    def project(self):
        m=MediaItem('m',str(self.root/'old.mp4'),'video','old.mp4',20,640,360,30,True)
        p=Project(media=[m],timeline=[TimelineItem('v','m','video_1',2,3,4),TimelineItem('a','m','audio_1',2,3,4),TimelineItem('late','m','video_1',9,3,14)])
        p.timeline[0].transform.zoom=1.7; p.timeline[0].effects=[{'name':'Gaussian Blur','enabled':True}]
        p.timeline[0].keyframes={'zoom':[{'time':0,'value':1},{'time':2,'value':2}]}
        return p
    def replacement(self,duration=20):return MediaItem('new',str(self.root/'new.mp4'),'video','new.mp4',duration,1280,720,60,True)
    def test_initial_available_scan_does_not_invalidate_ready_preview(self):
        key=mm.path_key(str(self.root/'ready.mp4'))
        self.assertEqual(mm.publish({key:False}),set())
        self.assertEqual(mm.publish({key:True}),{key})
        self.assertEqual(mm.publish({key:False}),{key})
    def test_missing_cached_no_stat_during_paint_and_reappearance(self):
        p=self.project(); mm.publish(mm.scan(mm.source_paths(p))); self.assertTrue(mm.is_missing(p.media[0]))
        with patch.object(Path,'is_file',side_effect=AssertionError('paint must not stat')):
            for _ in range(100):self.assertTrue(mm.unavailable(p.media[0],p.timeline[0]))
        Path(p.media[0].path).touch(); mm.publish(mm.scan(mm.source_paths(p))); self.assertFalse(mm.is_missing(p.media[0]))
    def test_replacement_preserves_every_edit_field(self):
        p=self.project(); before=[asdict(i) for i in p.timeline]; result=mm.replace(p,p.media[0].path,self.replacement())
        self.assertEqual(result,(3,0)); self.assertEqual(p.media[0].id,'m')
        for old,item in zip(before,p.timeline):
            now=asdict(item); now.pop('source_requirement'); old.pop('source_requirement'); self.assertEqual(old,now)
    def test_short_file_partial_mismatch_then_retry_and_roundtrip(self):
        p=self.project(); mm.replace(p,p.media[0].path,self.replacement(10))
        self.assertEqual([i.source_mismatch for i in p.timeline],[False,False,True])
        self.assertEqual(mm.label(p.media[0],p.timeline[2]),'old.mp4 mismatch')
        p=Project.from_dict(p.to_dict()); self.assertTrue(p.timeline[2].source_mismatch)
        self.assertEqual(mm.replace(p,p.media[0].path,self.replacement()),(3,0))
        self.assertFalse(any(i.source_mismatch for i in p.timeline))
    def test_audio_stream_and_visual_type_checked_independently(self):
        p=self.project(); replacement=self.replacement(); replacement.has_audio=False
        self.assertEqual(mm.replace(p,p.media[0].path,replacement),(2,1))
        replacement.kind='audio'; replacement.has_audio=True; replacement.width=replacement.height=0
        self.assertEqual(mm.replace(p,p.media[0].path,replacement),(1,2))
    def test_speed_source_range_and_image_duration(self):
        p=self.project(); p.timeline[0].speed=3
        mm.replace(p,p.media[0].path,self.replacement(12)); self.assertTrue(p.timeline[0].source_mismatch)
        image=MediaItem('i',str(self.root/'x.png'),'image','x.png',5,50,50)
        p=Project(media=[image],timeline=[TimelineItem('i','i','video_1',0,120)])
        self.assertEqual(mm.replace(p,image.path,copy.deepcopy(image)),(1,0))
    def test_shorter_video_stream_not_hidden_by_longer_container_duration(self):
        p=self.project(); replacement=self.replacement(); replacement.stream_durations={'video':10,'audio':20}
        self.assertEqual(mm.replace(p,p.media[0].path,replacement),(2,1))
    def test_compound_cache_absence_not_offline_but_child_absence_is(self):
        child=self.project(); compound=MediaItem('c','not-built.mkv','video','Compound',compound=child.to_dict())
        mm.publish(mm.scan(mm.source_paths(child))); self.assertTrue(mm.is_missing(compound))
        Path(child.media[0].path).touch(); mm.publish(mm.scan(mm.source_paths(child))); self.assertFalse(mm.is_missing(compound))
    def test_nested_relink_and_export_preflight(self):
        child=self.project(); old=child.media[0].path
        p=Project(media=[MediaItem('c','','video','Compound',compound=child.to_dict())],timeline=[TimelineItem('c','c','video_1',0,20)])
        self.assertTrue(mm.export_issues(p)); new=self.replacement(); Path(new.path).touch()
        self.assertEqual(mm.replace(p,old,new),(3,0)); self.assertEqual(mm.export_issues(p),[])
    def test_generated_items_never_missing(self):
        for role in ('title','graphic'):
            self.assertFalse(mm.unavailable(None,TimelineItem('g','','video_1',0,2,role=role)))
    def test_audio_offline_icon_is_a_flat_center_line_not_picture_art(self):
        audio=mm.offline_icon(True).pixmap(110,65).toImage()
        video=mm.offline_icon(False).pixmap(110,65).toImage()
        self.assertNotEqual(audio,video)
        self.assertEqual(audio.pixelColor(50,20).name(),'#410b0d')
        self.assertNotEqual(audio.pixelColor(50,32).name(),'#410b0d')
    def test_missing_removal_can_hide_pool_without_losing_timeline(self):
        p=self.project(); p.media[0].pool_hidden=True
        restored=Project.from_dict(p.to_dict()); self.assertTrue(restored.media[0].pool_hidden); self.assertEqual(len(restored.timeline),3)
    def test_power_bin_saved_edits_keep_attributes_and_partial_mismatch(self):
        from kinetic_cut import binclips
        p=self.project(); saved=binclips.asset(binclips.snapshot(p,{i.id for i in p.timeline},set(),'v'))
        mm.publish(mm.scan(mm.source_paths(p))); self.assertTrue(mm.is_missing(saved))
        before=copy.deepcopy(saved.timeline_preset['items']); old=p.media[0].path
        new=self.replacement(10); mm.publish({mm.path_key(new.path):False})
        mm.replace_bin_asset(saved,old,new)
        self.assertTrue(mm.is_missing(saved)) # late cut is still mismatched
        self.assertEqual([i['duration'] for i in before],[i['duration'] for i in saved.timeline_preset['items']])
        mm.replace_bin_asset(saved,new.path,self.replacement(20)); self.assertFalse(mm.is_missing(saved))

if __name__=='__main__':unittest.main()
