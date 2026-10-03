import unittest,copy,tempfile
from pathlib import Path
from kinetic_cut.model import Project,MediaItem,TimelineItem
from kinetic_cut.rendergraph import audio_filters
from kinetic_cut.exporter import build_command,PRESETS

class TimelineEditingTests(unittest.TestCase):
    def fixture(self):
        media=MediaItem("m","source.mp4","video","source",20,1920,1080,30,True)
        return Project(media=[media],timeline=[TimelineItem("v","m","video_1",5,5,3,group_id="g"),TimelineItem("a","m","audio_1",5,5,3,group_id="g")])
    def test_left_trim_recovers_previous_source_frames(self):
        p=self.fixture(); p.trim_items(["v","a"],-10,"left")
        self.assertEqual([(i.start,i.in_point,i.duration) for i in p.timeline],[(2,0,8),(2,0,8)])
    def test_full_source_cannot_extend(self):
        p=self.fixture(); v=p.item_by_id("v"); v.in_point=0; v.duration=20
        p.trim_items(["v"],10,"right"); self.assertEqual(v.duration,20)
        p.trim_items(["v"],-3,"left"); self.assertEqual(v.start,5)
    def test_image_extends_left_without_source_limit(self):
        p=self.fixture(); p.media[0].kind="image"; p.trim_items(["v"],-3,"left")
        v=p.item_by_id("v"); self.assertEqual((v.start,v.duration),(2,8))
        p.trim_items(["v"],15,"right"); self.assertEqual(v.duration,23)
    def test_linked_trim_uses_shared_source_bound(self):
        p=self.fixture(); p.item_by_id("a").in_point=1; p.trim_items(["v","a"],-3,"left")
        self.assertEqual(p.item_by_id("v").start,p.item_by_id("a").start); self.assertEqual(p.item_by_id("a").in_point,0)
    def test_retime_preserves_source_range_and_resets(self):
        p=self.fixture(); p.retime_items(["v","a"],.5)
        for i in p.timeline:self.assertEqual((i.duration,i.source_duration,i.in_point),(10,5,3))
        p.retime_items(["v","a"],2); self.assertEqual(p.item_by_id("v").duration,2.5)
        p.retime_items(["v","a"],1); self.assertEqual(p.item_by_id("v").duration,5)
    def test_independent_retime_does_not_change_audio(self):
        p=self.fixture(); p.retime_items(["v"],2); self.assertEqual(p.item_by_id("a").speed,1)
    def test_silence_ranges_preserve_retimed_source_mapping(self):
        p=self.fixture(); p.retime_items(["v","a"],2)
        p.ripple_ranges("g",[(0,.5),(1,2)],"v")
        self.assertEqual(sorted({(i.start,i.duration,i.in_point,i.speed) for i in p.timeline}),[(5,.5,3,2),(5.5,1,5,2)])
        self.assertTrue(all(len(p.linked_items(i))==2 for i in p.timeline))
    def test_split_retained_source_at_speed(self):
        p=self.fixture(); p.retime_items(["v","a"],2); right=p.split_selection(["v"],6,True)
        self.assertEqual([p.item_by_id(i).in_point for i in right],[5,5])
    def test_retimed_trim_source_bounds(self):
        p=self.fixture(); p.retime_items(["v"],2); p.trim_items(["v"],-10,"left")
        v=p.item_by_id("v"); self.assertEqual((v.start,v.in_point,v.duration),(3.5,0,4))
    def test_middle_overwrite_splits_victim(self):
        p=self.fixture(); p.timeline=[TimelineItem("victim","m","video_1",0,10,2,speed=1.5),TimelineItem("placed","m","video_1",3,2,0)]
        p.overwrite(["placed"]); rest=sorted((i for i in p.timeline if i.id!="placed"),key=lambda i:i.start)
        self.assertEqual([(i.start,i.duration,i.in_point) for i in rest],[(0,3,2),(5,5,9.5)])
    def test_complete_and_edge_overwrite(self):
        for start,duration,expected in [(0,10,[]),(0,2,[(2,8)]),(8,4,[(0,8)])]:
            p=self.fixture(); p.timeline=[TimelineItem("v","m","video_1",0,10),TimelineItem("new","m","video_1",start,duration)]
            p.overwrite(["new"]); self.assertEqual([(i.start,i.duration) for i in p.timeline if i.id!="new"],expected)
    def test_symmetric_audio_video_fragments_keep_links(self):
        p=self.fixture(); p.timeline += [TimelineItem("vnew","m","video_1",6,2),TimelineItem("anew","m","audio_1",6,2)]
        p.overwrite(["vnew","anew"]); v=p.item_by_id("v"); self.assertEqual(len(p.linked_items(v)),2)
    def test_slowdown_overwrites_not_ripples(self):
        p=self.fixture(); p.timeline.append(TimelineItem("next","m","video_1",10,10,0)); p.retime_items(["v"],.5); p.overwrite(["v"])
        n=p.item_by_id("next"); self.assertEqual((n.start,n.duration,n.in_point),(15,5,5))
    def test_locked_track_is_preserved(self):
        p=self.fixture(); p.track_states["video_1"]["locked"]=True; before=copy.deepcopy(p.item_by_id("v")); p.retime_items(["v"],.5); p.trim_items(["v"],-1,"left"); self.assertEqual(p.item_by_id("v"),before)
    def test_speed_persists_and_export_has_tempo_and_alpha_fades(self):
        p=self.fixture(); p.retime_items(["v","a"],2); p.item_by_id("v").fade_in=.3
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"p.kcut"; p.save(path); restored=Project.load(path); self.assertEqual(restored.item_by_id("v").speed,2)
        self.assertIn("atempo=2.000000",audio_filters(p.item_by_id("a")))
        graph=build_command(p,"out.mp4",PRESETS["TikTok · Fast"]); chain=graph[graph.index("-filter_complex")+1]
        self.assertIn("(PTS-STARTPTS)/2.00000000",chain); self.assertIn("alpha=1",chain)
    def test_colour_pipeline_persists_and_non_blur_effect_is_not_rendered_as_blur(self):
        p=self.fixture(); v=p.item_by_id("v"); v.grayscale=True; v.brightness=.04; v.contrast=1.16; v.saturation=.8; v.sharpen=.35
        v.effects=[dict(name="Circle Facecam",enabled=True)]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"colour.kcut"; p.save(path); restored=Project.load(path); rv=restored.item_by_id("v")
            self.assertEqual((rv.grayscale,rv.brightness,rv.contrast,rv.saturation,rv.sharpen),(True,.04,1.16,.8,.35))
        graph=build_command(p,"out.mp4",PRESETS["TikTok · Fast"]); chain=graph[graph.index("-filter_complex")+1]
        self.assertIn("hue=s=0",chain); self.assertIn("eq=brightness=0.04000:contrast=1.16000:saturation=0.80000",chain); self.assertIn("unsharp=",chain); self.assertNotIn("gblur=sigma=12",chain)
if __name__=="__main__":unittest.main()
