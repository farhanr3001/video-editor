import copy,json,tempfile,unittest
from pathlib import Path
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,Transform
from kinetic_cut.project_timelines import capture,default_name
from kinetic_cut.close_guard import document_key


class ProjectTimelineTests(unittest.TestCase):
    def fixture(self):
        return Project(name='Shared project',media=[MediaItem('asset','video.mp4','video','Video',5,640,360)],
                       timeline=[TimelineItem('clip','asset','video_1',0,5)],captions=[Caption('c',0,1,'First timeline')])

    def test_legacy_load_becomes_timeline_one_without_changing_content(self):
        p=Project.from_dict(dict(name='Old',timeline=[dict(id='v',media_id='m',track='video_1',start=0,duration=5)]))
        self.assertEqual(p.timeline_name,'Timeline 1');self.assertEqual(len(p.timeline_choices()),1);self.assertEqual(p.duration,5)

    def test_new_empty_timeline_shares_media_and_keeps_original_all_content(self):
        p=self.fixture();first=p.active_timeline_id;before=capture(p);assets=copy.deepcopy(p.media);p.playhead=2
        second=p.create_timeline();self.assertNotEqual(second,first);self.assertEqual(p.timeline_name,'Timeline 2')
        self.assertEqual((p.timeline,p.captions,p.duration),([],[],0));self.assertEqual(p.media,assets)
        p.settings.width=720;p.timeline.append(TimelineItem('new','asset','video_1',1,2));p.mark_in=1
        p.switch_timeline(first);self.assertEqual(p.timeline_name,'Timeline 1');self.assertEqual(p.timeline[0].id,'clip');self.assertEqual(p.captions[0].text,'First timeline');self.assertEqual(p.playhead,2)
        self.assertEqual(p.settings.width,before['data']['settings']['width']);p.switch_timeline(second)
        self.assertEqual(p.settings.width,720);self.assertEqual(p.mark_in,1);self.assertEqual(p.timeline[0].id,'new')

    def test_save_load_active_choice_and_inactive_typed_content(self):
        p=self.fixture();first=p.active_timeline_id;p.create_timeline('Funny chase');p.timeline.append(TimelineItem('other','asset','video_1',2,1,transform=Transform(.4,.6,1.5)))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'multi.kcut';p.save(path);r=Project.load(path)
        self.assertEqual(r.timeline_name,'Funny chase');self.assertEqual(r.timeline[0].transform.scale,1.5);r.switch_timeline(first)
        self.assertEqual(r.captions[0].text,'First timeline');self.assertEqual(r.media,p.media)

    def test_names_increment_order_stays_fixed_and_duplicates_refuse_atomically(self):
        p=self.fixture();first=p.active_timeline_id;second=p.create_timeline('Chase');third=p.create_timeline()
        self.assertEqual(p.timeline_name,'Timeline 3');p.switch_timeline(first);p.switch_timeline(third);p.switch_timeline(second)
        self.assertEqual([r['id'] for r in p.timeline_choices()],[first,second,third]);before=p.to_dict()
        with self.assertRaises(ValueError):p.create_timeline('chase')
        with self.assertRaises(ValueError):p.switch_timeline('gone')
        self.assertEqual(p.to_dict(),before)

    def test_export_snapshot_excludes_inactive_work_but_detaches_current_assets(self):
        p=self.fixture();p.create_timeline();p.timeline.append(TimelineItem('new','asset','video_1',0,2))
        q=p.active_snapshot();self.assertFalse(q.other_timelines);q.media[0].name='Changed';q.timeline[0].duration=1
        self.assertEqual(p.media[0].name,'Video');self.assertEqual(p.timeline[0].duration,2)

    def test_portable_save_rebases_graphic_paths_in_both_timelines(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);image=root/'image.png';image.write_bytes(b'fixture')
            p=self.fixture();p.media[0].path=str(image);p.portable_media=True
            p.timeline[0].effects=[dict(name='Object Tracking',image=str(image))];first=p.active_timeline_id
            p.create_timeline();p.timeline.append(TimelineItem('two','asset','video_1',0,1,effects=[dict(name='Object Tracking',image=str(image))]))
            path=root/'portable.kcut';p.save(path);raw=json.loads(path.read_text());self.assertEqual(raw['other_timelines'][0]['data']['timeline'][0]['effects'][0]['image'],'image.png')
            r=Project.load(path);r.switch_timeline(first);self.assertEqual(Path(r.timeline[0].effects[0]['image']),image.resolve())

    def test_close_key_includes_inactive_edits_but_ignores_their_playhead(self):
        p=self.fixture();p.create_timeline();before=document_key(p);p.other_timelines[0]['data']['playhead']=3
        self.assertEqual(document_key(p),before);p.other_timelines[0]['data']['timeline'][0]['duration']=3
        self.assertNotEqual(document_key(p),before)

    def test_malformed_inactive_content_cannot_silently_disappear(self):
        for rows in (None,{},[dict(id='other',data='bad')],[dict(id='timeline_1',data={})]):
            with self.assertRaises(ValueError):Project.from_dict(dict(other_timelines=rows))

if __name__=='__main__':unittest.main()
