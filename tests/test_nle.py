import copy,tempfile,unittest
from pathlib import Path
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,uid
from kinetic_cut.rendergraph import audio_filters
from kinetic_cut.exporter import build_command,write_ass,PRESETS
from kinetic_cut.workspace import PowerBins


class NLETests(unittest.TestCase):
    def fixture(self):
        media=MediaItem("m","source.mp4","video","source.mp4",10,1920,1080,60,True)
        p=Project(media=[media]); p.timeline=[TimelineItem("v","m","video_1",0,10,group_id="g"),TimelineItem("a","m","audio_1",0,10,group_id="g",role="source_audio")]
        return p
    def test_fresh_project_one_track_each(self):
        p=Project(); self.assertEqual(p.video_tracks,["video_1"]); self.assertEqual(p.audio_tracks,["audio_1"])
    def test_reorder_survives_refresh_and_save(self):
        p=Project(); p.add_track("video"); p.move_track("video_1",1); p.ensure_track_model(); self.assertEqual(p.video_tracks,["video_2","video_1"])
        with tempfile.TemporaryDirectory() as d:
            p.save(Path(d)/"p.kcut"); self.assertEqual(Project.load(Path(d)/"p.kcut").video_tracks,p.video_tracks)
    def test_linked_split_right_pairs_are_distinct(self):
        p=self.fixture(); right=p.split_selection(["v"],4,True); self.assertEqual(len(p.timeline),4)
        self.assertEqual({i.id for i in p.linked_items(p.item_by_id(right[0]))},set(right))
        self.assertEqual({i.id for i in p.linked_items(p.item_by_id("v"))},{"v","a"})
    def test_unlinked_split_does_not_cut_audio(self):
        p=self.fixture(); right=p.split_selection(["v"],4,False); self.assertEqual(p.item_by_id("a").duration,10)
        self.assertEqual(len(p.linked_items(p.item_by_id(right[0]))),1)
    def test_explicit_unlink_stays_unlinked_after_refresh(self):
        p=self.fixture(); p.link_selection(["v","a"],True); p.ensure_track_model(); self.assertEqual(len(p.linked_items(p.item_by_id("v"))),1)
    def test_deleted_source_audio_does_not_reappear(self):
        p=self.fixture(); p.item_by_id("v").role="content"; p.delete(["a"]); p.ensure_track_model(); self.assertEqual(len(p.timeline),1)
    def test_subtitle_track_inheritance(self):
        p=Project(); c=Caption("c",0,1,"hello"); p.captions=[c]; p.subtitle_style.size=54; self.assertEqual(p.caption_style(c).size,54)
        c.customize=True; c.style.size=20; self.assertEqual(p.caption_style(c).size,20); self.assertEqual(p.subtitle_style.size,54)
    def test_audio_pan_pitch_and_fades_are_exported(self):
        p=self.fixture(); a=p.item_by_id("a"); a.pan=.4; a.pitch_semitones=2; a.fade_in=.2; a.fade_out=.3
        chain=audio_filters(a); self.assertIn("asetrate=",chain); self.assertIn("pan=stereo",chain); self.assertIn("afade=t=in",chain); self.assertIn("afade=t=out",chain)
    def test_export_without_audio(self):
        p=self.fixture(); command=build_command(p,"out.mp4",PRESETS["TikTok · Fast"],export_audio=False)
        self.assertNotIn("-c:a",command); self.assertIn("-t",command)
    def test_style_controls_written_to_ass(self):
        p=Project(captions=[Caption("c",0,2,"hello\nworld")]); s=p.subtitle_style; s.background_enabled=True; s.background_radius=.02; s.shadow_blur=9; s.line_spacing=20
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"c.ass"; write_ass(p,target); text=target.read_text(encoding="utf-8-sig"); self.assertIn(r"\p1",text); self.assertIn(r"\blur9",text)
    def test_power_bins_survive_new_instance(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bins.json"; bins=PowerBins(path); bins.add_folder("Master/SFX"); media=self.fixture().media[0]; bins.add(media,"Master/SFX"); loaded=PowerBins(path)
            self.assertIn("Master/SFX",loaded.data["folders"]); self.assertEqual(loaded.data["media"][0]["media"]["path"],media.path)
    def test_power_bin_children_and_recursive_rename(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bins.json"; bins=PowerBins(path); bins.add_folder("Master/Memes"); bins.add_folder("Master/Memes/Reactions"); bins.add_folder("Master/Music")
            media=self.fixture().media[0]; bins.add(media,"Master/Memes/Reactions")
            self.assertEqual(bins.child_folders("Master"),["Master/Memes","Master/Music"])
            renamed=bins.rename_folder("Master/Memes","Comedy")
            self.assertEqual(renamed,"Master/Comedy"); self.assertIn("Master/Comedy/Reactions",bins.data["folders"]); self.assertEqual(bins.data["media"][0]["folder"],"Master/Comedy/Reactions")

if __name__=="__main__":unittest.main()
