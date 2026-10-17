import copy,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,Transform,Crop
from kinetic_cut.caption_quality import normalize_words,review
from kinetic_cut.captions import _from_segments,CaptionBackendError
from kinetic_cut import transcripts


class EditAssistanceTests(unittest.TestCase):
    def test_spoken_prices_merge_before_single_word_cards_without_timing_loss(self):
        raw='I spent seventy-five k dollars on it'.split()
        words=[dict(text=t,start=i*.2,end=(i+1)*.2) for i,t in enumerate(raw)]
        captions=_from_segments([dict(text=' '.join(raw),start=0,end=1.6,words=words)],words_per_caption=1,hold_seconds=0)
        self.assertEqual([c.text for c in captions],['I','spent','$75K','on','it'])
        price=captions[2]; self.assertAlmostEqual(price.start,.4); self.assertAlmostEqual(price.end,1)
        self.assertAlmostEqual(price.word_timings[0]['end'],.6)
        for text in ('2026','version 1.22','one two three','seventy-five minutes'):
            rows=[dict(text=t,start=i,end=i+.5) for i,t in enumerate(text.split())]
            self.assertEqual([w['text'] for w in normalize_words(rows)],text.split())
    def test_prices_decimal_range_and_no_cross_silence_merge(self):
        raw=['one','point','two','million']; rows=[dict(text=t,start=i,end=i+.5) for i,t in enumerate(raw)]
        self.assertEqual(normalize_words(rows)[0]['text'],'1.2M')
        rows=[dict(text='$375K',start=0,end=.3),dict(text='to',start=.3,end=.4),dict(text='$430K',start=.4,end=.8)]
        self.assertEqual([w['text'] for w in normalize_words(rows)],['$375K','to','$430K'])
        rows=[dict(text='seventy',start=0,end=.2),dict(text='five',start=2,end=2.2),dict(text='k',start=2.2,end=2.3)]
        self.assertEqual([w['text'] for w in normalize_words(rows)],['seventy','5K'])
    def test_invalid_timestamps_reject_and_review_estimates(self):
        with self.assertRaises(CaptionBackendError):_from_segments([dict(text='Hi',start=float('nan'),end=1)])
        c=Caption('c',1,2,'Hello'); p=Project(captions=[c]); self.assertIn('estimated_word_timing',review(p)['issues'][0]['flags'])
        c.word_timings=[dict(text='Hello',start=0,end=.5)]; self.assertEqual(review(p)['issues'],[])
    def test_source_index_search_retime_repeats_invalidation_and_pagination(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(transcripts.config,'CACHE_DIR',Path(folder)/'cache'):
            path=Path(folder)/'source.wav'; path.write_bytes(b'speech')
            media=MediaItem('m',str(path),'audio','Speech',30,has_audio=True); stamp=transcripts.identity(media,{})
            target=transcripts.cache_path(stamp); target.parent.mkdir(parents=True)
            target.write_text(json.dumps(dict(source=stamp,timing='word',segments=[dict(text='Watch price',start=10,end=12,words=[]),dict(text='Steam price',start=15,end=17,words=[])])))
            p=Project(media=[media],timeline=[TimelineItem('a','m','audio_1',5,10,8,speed=2),TimelineItem('b','m','audio_1',30,3,10)])
            result=transcripts.search(p,{},'WATCH',limit=1)
            self.assertEqual(result['total'],1); occurrences=result['matches'][0]['occurrences']
            self.assertEqual([r['start'] for r in occurrences],[6,30]); self.assertEqual([r['end'] for r in occurrences],[7,32])
            self.assertEqual(transcripts.search(p,{},'price',limit=1,offset=1)['matches'][0]['text'],'Steam price')
            path.write_bytes(b'changed speech'); self.assertIsNone(transcripts.load(media,{}))
    def test_cancelled_generation_publishes_nothing_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(transcripts.config,'CACHE_DIR',Path(folder)/'cache'):
            path=Path(folder)/'a.wav'; path.write_bytes(b'original'); media=MediaItem('m',str(path),'audio','a',3,has_audio=True)
            cancel=threading.Event(); cancel.set()
            with self.assertRaises(InterruptedError),patch('kinetic_cut.process.run_cancellable',side_effect=InterruptedError):transcripts.generate(media,{},cancel)
            self.assertEqual(path.read_bytes(),b'original'); self.assertIsNone(transcripts.load(media,{}))
    def test_sound_cues_follow_trim_move_speed_and_do_not_mutate_project(self):
        from kinetic_cut.motion_audio import expanded,validate,playback_view
        cue=dict(id='cash',source='cash.wav',time=1,in_point=.2,duration=2,source_duration=4,gain_db=-4)
        graphic=TimelineItem('g','','video_1',10,2,2,speed=2,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':{'nodes':[],'sound_cues':validate([cue])}})
        p=Project(timeline=[graphic]); before=p.to_dict(); view=expanded(p); audio=view.timeline[-1]
        self.assertEqual(audio.start,10); self.assertEqual(audio.duration,.5); self.assertAlmostEqual(audio.in_point,1.2); self.assertEqual(audio.speed,2)
        view.ensure_track_model(); self.assertEqual(p.to_dict(),before)
        first,cache=playback_view(p); second,_=playback_view(p,cache); self.assertIs(first,second)
        graphic.start=20; moved,_=playback_view(p,cache); self.assertEqual(moved.timeline[-1].start,20)
        p.track_states['video_1']['muted']=True; self.assertIs(expanded(p),p)
    def test_anchoring_uses_actual_crop_and_is_transactional(self):
        app=QApplication.instance() or QApplication([])
        from kinetic_cut.edit_review import anchor_captions
        media=MediaItem('m','a.mp4','video','a',10,1920,1080)
        item=TimelineItem('face','m','video_1',0,10,crop=Crop(0,0,.5,.35),transform=Transform(.5,.2,1),role='facecam')
        caption=Caption('c',0,1,'Hello'); caption.style.size=30
        p=Project(media=[media],timeline=[item],captions=[caption]); before=p.to_dict()
        stage=copy.deepcopy(p); placements=anchor_captions(None,stage,'video_1',['c'],16)
        self.assertEqual(p.to_dict(),before); self.assertEqual(stage.captions[0].style.anchor,'Bottom'); self.assertTrue(stage.captions[0].customize)
        self.assertLess(placements[0]['position_y'],.5)
    def test_sound_is_collected_portable_and_compound_cache_tracks_its_source(self):
        from kinetic_cut.motion_audio import validate
        from kinetic_cut.project_safety import collect_project
        from kinetic_cut.compounds import cache_path,update_asset,content,create
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/'cash.wav'; path.write_bytes(b'audio')
            graphic=TimelineItem('g','','video_1',0,3,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':{'nodes':[],'sound_cues':validate([dict(id='s',source=str(path),duration=1,source_duration=1,time=1)])}},transform=Transform(.5,.5))
            p=Project(name='Sound graphic',timeline=[graphic]); before=p.to_dict(); first=cache_path(content(p))
            output=collect_project(p,root/'collected'); self.assertEqual(p.to_dict(),before)
            moved=root/'moved'; output.parent.rename(moved); loaded=Project.load(moved/output.name)
            self.assertEqual(Path(loaded.timeline[0].graphic_data['scene']['sound_cues'][0]['source']).read_bytes(),b'audio')
            path.write_bytes(b'changed-audio'); self.assertNotEqual(cache_path(content(p)),first)
            asset=MediaItem('compound','','video','Compound'); update_asset(asset,p); self.assertTrue(asset.has_audio)
            stage=copy.deepcopy(p); create(stage,{'g'},set(),'Nested sound'); self.assertTrue(any(i.track in stage.audio_tracks for i in stage.timeline))
    def test_event_binding_validation_and_mcp_key_removal_are_atomic(self):
        from kinetic_cut.motion import validate
        from kinetic_cut.motion_editing import apply
        scene=validate(dict(nodes=[dict(id='n',kind='rectangle',start=.5,end=2,keyframes={'opacity':[dict(time=1,value=0)]})],sound_cues=[dict(id='s',source='cash.wav',time=0,duration=1,source_duration=1,event='keyframe',node_id='n',channel='opacity',key_time=1)]))
        before=copy.deepcopy(scene); after=apply(scene,[dict(op='remove_key',id='n',channel='opacity',time=1)])
        self.assertEqual(after['sound_cues'],[]); self.assertEqual(scene,before)
        with self.assertRaises(ValueError):apply(scene,[dict(op='scene_settings',values={'sound_cues':[{**scene['sound_cues'][0],'node_id':'missing'}]})])
    def test_direct_render_command_includes_cues_once_with_source_trim_and_speed(self):
        from kinetic_cut.motion_audio import expanded,validate
        from kinetic_cut.exporter import build_command,PRESETS
        graphic=TimelineItem('g','','video_1',3,2,2,speed=2,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':{'nodes':[],'sound_cues':validate([dict(id='s',source='cash.wav',time=1,in_point=.2,duration=2,source_duration=4)])}})
        p=Project(timeline=[graphic]); command=build_command(expanded(p),'out.mp4',PRESETS['TikTok · Fast'],False,'CPU')
        self.assertEqual(command.count('cash.wav'),1); graph=command[command.index('-filter_complex')+1]
        self.assertIn('atempo=2.000000',graph); self.assertIn('adelay=3000',graph); self.assertIn('1.200000',command)

if __name__=='__main__':unittest.main()
