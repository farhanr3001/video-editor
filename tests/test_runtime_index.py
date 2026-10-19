import copy
import gc
import random
import unittest
import weakref
from kinetic_cut.model import Project,TimelineItem,MediaItem,Caption
from kinetic_cut.transitions import Transition
from kinetic_cut.runtime_index import IntervalTree,IndexedList


class RuntimeIndexTests(unittest.TestCase):
    def test_track_normalization_uses_membership_and_updates_after_moves_and_removal(self):
        class Counted(IndexedList):
            scans=0
            def __iter__(self):self.scans+=1;return super().__iter__()
        p=Project(timeline=[TimelineItem(str(n),'m','video_1',n,1) for n in range(3000)])
        values=Counted(p.timeline,p,'timeline');object.__setattr__(p,'timeline',values);index=p.runtime_index;values.scans=0
        for _ in range(20):p.ensure_track_model()
        self.assertEqual(values.scans,0)
        item=values[1000];item.track='main';p.ensure_track_model()
        self.assertEqual((item.track,item.role),('video_2','content'));self.assertEqual(values.scans,0)
        self.assertNotIn('main',index.track_items);self.assertIn(id(item),index.track_items['video_2'])
        values.remove(item);self.assertNotIn('video_2',index.track_items)
        item.track='video_99';self.assertNotIn('video_99',index.track_items)
        p.timeline=[TimelineItem('new','m','audio_9',0,1)];p.ensure_track_model()
        self.assertEqual(set(index.track_items),{'audio_9'});self.assertIn('audio_9',p.audio_tracks)
        p.track_states['audio_9']['visible']=False;p.ensure_track_model()
        self.assertTrue(p.track_states['audio_9']['visible']);self.assertTrue(p.track_states['audio_9']['muted'])

    def test_sparse_overwrite_does_not_inspect_tracks_on_unrelated_clips(self):
        class CountedItem(TimelineItem):
            checks=0;counting=False
            def __getattribute__(self,name):
                if name=='track' and CountedItem.counting:CountedItem.checks+=1
                return super().__getattribute__(name)
        items=[CountedItem(str(n),'m','video_1',n*3,1) for n in range(3000)]
        placed=CountedItem('placed','m','video_1',3000.5,.5);p=Project(timeline=[*items,placed]);p.runtime_index
        CountedItem.counting=True
        try:p.overwrite({'placed'})
        finally:CountedItem.counting=False
        self.assertLess(CountedItem.checks,50)
        self.assertIs(p.item_by_id('999'),items[999]);self.assertEqual(p.item_by_id('1000').duration,.5)
        self.assertEqual(p.item_by_id('placed').start,3000.5)
        self.assertEqual(sum(map(len,p.runtime_index.track_items.values())),len(p.timeline))

    def test_structural_edits_update_only_changed_intervals_and_keep_document_order(self):
        from unittest.mock import patch
        p=Project(timeline=[TimelineItem(str(n),'m','video_1',0,3,link_id='pair' if n<2 else '') for n in range(3000)])
        index=p.runtime_index;tree=index.trees['timeline'];original=p.timeline[20]
        with patch.object(tree,'put',wraps=tree.put) as put:
            replacement=copy.deepcopy(original);replacement.duration=4;p.timeline[20]=replacement
            self.assertIs(p.runtime_index,index);self.assertEqual(put.call_count,1)
            p.timeline.reverse();self.assertEqual(put.call_count,1)
            self.assertEqual(index.active('timeline',1),list(p.timeline))
            p.timeline.append(TimelineItem('new','m','video_1',0,2));self.assertEqual(put.call_count,2)
            p.timeline.remove(replacement);self.assertEqual(put.call_count,2)
        self.assertEqual(len(tree.records),len(p.timeline));self.assertEqual(len(index.edges.records),4*len(p.timeline))
        self.assertEqual(index.link_counts['pair'],2)
        p.timeline=[i for i in p.timeline if i.link_id!='pair'];self.assertNotIn('pair',index.link_counts)
        original.start=1000;original.link_id='detached';self.assertNotIn('detached',index.link_counts)
        self.assertEqual(p.duration,3)

    def test_seeded_membership_mutations_match_reference_and_remove_stale_boundaries(self):
        rng=random.Random(409);p=Project(timeline=[TimelineItem(str(n),'m','video_1',n*2,1) for n in range(50)]);index=p.runtime_index
        for step in range(100):
            if step%4==0:p.timeline.append(TimelineItem('added'+str(step),'m','video_1',rng.randrange(120),2))
            elif step%4==1:p.timeline.pop(rng.randrange(len(p.timeline)))
            elif step%4==2:p.timeline.reverse()
            else:
                at=rng.randrange(len(p.timeline));item=copy.deepcopy(p.timeline[at]);item.start=rng.randrange(120);p.timeline[at]=item
            at=rng.randrange(120)
            self.assertIs(p.runtime_index,index)
            self.assertEqual(index.active('timeline',at),[i for i in p.timeline if i.start<=at<i.start+i.duration])
            self.assertEqual(p.duration,max(i.start+i.duration for i in p.timeline))
        p.transitions=[Transition('t','Cross Dissolve',start=500,duration=2)];self.assertEqual(p.duration,502)
        p.transitions.clear();self.assertLess(p.duration,500)
        p.media=[MediaItem('new','missing.png','image','New')];self.assertIsNotNone(p.media_by_id('new'))

    def test_mutating_a_detached_list_or_record_does_not_change_live_indexes(self):
        item=TimelineItem('old','m','video_1',0,2,link_id='old-link');p=Project(timeline=[item]);index=p.runtime_index;old=p.timeline
        p.timeline=[TimelineItem('new','m','video_1',4,2)]
        revision=index.revision;old.append(TimelineItem('phantom','m','video_1',100,1));item.start=200;item.link_id='phantom-link'
        self.assertEqual(index.revision,revision);self.assertEqual(p.duration,6);self.assertIsNone(p.item_by_id('phantom'))
        self.assertNotIn('phantom-link',index.link_counts)

    def test_random_overlaps_and_live_updates_match_reference(self):
        rng=random.Random(813);tree=IntervalTree();records={}
        for n in range(3000):
            start=rng.uniform(0,1000);end=start+rng.uniform(.01,70)
            tree.put(n,start,end,n);records[n]=(start,end)
        for _ in range(100):
            left=rng.uniform(0,1000);right=left+rng.uniform(0,10)
            self.assertEqual(tree.query(left,right),[n for n,(a,b) in records.items() if a<=right and b>=left])
        for n in range(100):tree.put(n,2000+n,2001+n,n);records[n]=(2000+n,2001+n)
        self.assertEqual(tree.query(2000,2010),[n for n,(a,b) in records.items() if a<=2010 and b>=2000])
        self.assertLess(tree.visited,100)
    def test_large_sparse_query_and_updates_do_not_scan_timeline(self):
        p=Project(timeline=[TimelineItem(str(n),'m','video_1',n*3,1) for n in range(10000)])
        index=p.runtime_index;self.assertEqual(p.duration,29998)
        self.assertEqual([i.id for i in index.active('timeline',15000.5)],['5000'])
        self.assertLess(index.trees['timeline'].visited,80)
        revision=index.revision;p.timeline[5000].start=15001
        self.assertIs(p.runtime_index,index);self.assertGreater(index.revision,revision)
        self.assertEqual(index.active('timeline',15000.5),[])
        self.assertEqual([i.id for i in index.active('timeline',15001.5)],['5000'])
    def test_same_boundary_cell_reuses_active_state_and_seek_is_exact(self):
        p=Project(timeline=[TimelineItem('a','m','video_1',0,5),TimelineItem('b','m','video_1',5,3)])
        index=p.runtime_index;first=index.playback(1);queries=index.queries
        for n in range(100):self.assertIs(index.playback(1+n*.01),first)
        self.assertEqual(index.queries,queries)
        self.assertEqual([i.id for i in index.active('timeline',5)],['b'])
        p.timeline[1].start=6;self.assertEqual(index.active('timeline',5),[])
        self.assertIsNot(index.playback(1),first)
    def test_mutable_lists_records_ids_and_roundtrip_remain_editable(self):
        p=Project(media=[MediaItem('m','source.mp4','video','Source')])
        self.assertEqual(p.duration,0)
        p.timeline.append(TimelineItem('a','m','video_1',3,2));self.assertEqual(p.duration,5)
        p.timeline[0].id='b';self.assertIsNone(p.item_by_id('a'));self.assertEqual(p.item_by_id('b').id,'b')
        p.captions.append(Caption('c',4,9,'Text'));self.assertEqual(p.duration,9)
        p.transitions.append(Transition('t','Cross Dissolve',start=8,duration=2));self.assertEqual(p.duration,10)
        p.transitions[0].start=12;self.assertEqual(p.duration,14)
        p.media[0].id='new';self.assertIsNone(p.media_by_id('m'));self.assertIsNotNone(p.media_by_id('new'))
        restored=Project.from_dict(p.to_dict());self.assertEqual(restored.to_dict(),p.to_dict())
        del restored.timeline[:];self.assertIsNone(restored.item_by_id('b'))
        restored.transitions.clear();restored.captions.clear();self.assertEqual(restored.duration,0)
    def test_history_snapshots_do_not_share_runtime_observers(self):
        p=Project(timeline=[TimelineItem('a','m','video_1',0,2)])
        old=p.runtime_index;q=copy.deepcopy(p);q.runtime_index;q.timeline[0].duration=7
        self.assertEqual(p.duration,2);self.assertEqual(q.duration,7);self.assertIs(p.runtime_index,old)
        self.assertNotIn('_runtime_index',q.to_dict());self.assertNotIn('_index_owners',q.to_dict()['timeline'][0])
        ref=weakref.ref(q);item=q.timeline[0];del q;gc.collect();self.assertIsNone(ref())
        item.start=100;self.assertEqual(p.duration,2)
    def test_document_wire_format_contains_plain_lists_and_survives_process_transfer(self):
        import pickle
        p=Project(timeline=[TimelineItem('a','m','video_1',0,2)],captions=[Caption('c',0,1,'Text')])
        p.runtime_index
        payload=p.to_dict()
        for key in ('media','timeline','captions','transitions'):
            self.assertIs(type(payload[key]),list)
        restored=Project.from_dict(pickle.loads(pickle.dumps(payload)))
        self.assertEqual(restored.to_dict(),payload)
        restored.timeline[0].duration=3
        self.assertEqual(restored.duration,3);self.assertEqual(p.duration,2)
    def test_cancelled_and_reversed_drag_restore_the_temporal_index(self):
        item=TimelineItem('a','m','video_1',0,2);p=Project(timeline=[item]);original=copy.deepcopy(item)
        index=p.runtime_index
        item.start=10;item.duration=4
        self.assertEqual(index.active('timeline',11),[item])
        item.restore_edit_state(original)
        self.assertEqual(index.active('timeline',11),[])
        self.assertEqual(index.active('timeline',1),[item]);self.assertEqual(p.duration,2)
    def test_transition_endpoints_and_warm_neighbors_survive_gaps(self):
        a=TimelineItem('a','m','video_1',0,1);b=TimelineItem('b','m','video_1',10,1)
        p=Project(timeline=[a,b],transitions=[Transition('t','Cross Dissolve',start=5,duration=1,left_item_id='a',right_item_id='b')])
        clips,transitions,_=p.runtime_index.playback(5.5)
        self.assertEqual([i.id for i in clips],['a','b']);self.assertEqual(len(transitions),1)
        self.assertEqual(p.runtime_index.playback(3)[0],[])
        self.assertIn(b,p.runtime_index.playback(9.3)[0])


if __name__=='__main__':unittest.main()
