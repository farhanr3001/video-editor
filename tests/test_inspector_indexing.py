"""Inspector work follows the selected subset, preserving target semantics."""
import unittest
from types import SimpleNamespace
from kinetic_cut.model import Project,TimelineItem
from kinetic_cut.runtime_index import IndexedList
from kinetic_cut.properties import PropertiesPanel


class CountedTimeline(IndexedList):
    def __init__(self,*args):self.scans=0;super().__init__(*args)
    def __iter__(self):self.scans+=1;return super().__iter__()


class InspectorIndexingTests(unittest.TestCase):
    def fixture(self):
        project=Project(timeline=[TimelineItem(str(i),'media','video_1',i,1) for i in range(3000)])
        items=CountedTimeline(project.timeline,project,'timeline');object.__setattr__(project,'timeline',items)
        project.runtime_index;items.scans=0
        panel=SimpleNamespace(window=SimpleNamespace(project=project,timeline=SimpleNamespace(selected_ids={'2000'})),item_id='2000')
        return project,panel,items

    def test_single_selection_does_not_scan_unrelated_clips_per_control(self):
        project,panel,items=self.fixture();expected=project.item_by_id('2000')
        for _ in range(100):self.assertEqual(PropertiesPanel.targets(panel,False),[expected])
        self.assertEqual(items.scans,0)
        project.track_states['video_1']={'locked':True}
        self.assertEqual(PropertiesPanel.targets(panel),[])
        panel.window.timeline.selected_ids={'missing'};self.assertEqual(PropertiesPanel.targets(panel),[])

    def test_multi_selection_keeps_document_order_and_refreshes_after_reorder(self):
        project,panel,items=self.fixture();panel.window.timeline.selected_ids={'2000','10','2990'}
        self.assertEqual([i.id for i in PropertiesPanel.targets(panel)],['10','2000','2990'])
        scans=items.scans
        for _ in range(100):self.assertEqual([i.id for i in PropertiesPanel.targets(panel)],['10','2000','2990'])
        self.assertEqual(items.scans,scans)
        items.reverse();self.assertEqual([i.id for i in PropertiesPanel.targets(panel)],['2990','2000','10'])
        project.timeline=[project.item_by_id('10')]
        self.assertEqual([i.id for i in PropertiesPanel.targets(panel)],['10'])

    def test_primary_kind_locks_audio_filter_and_project_replacement_are_preserved(self):
        video=TimelineItem('video','m','video_1',0,1);audio=TimelineItem('audio','m','audio_1',0,1);title=TimelineItem('title','m','video_1',0,1,role='title')
        project=Project(timeline=[title,audio,video]);panel=SimpleNamespace(window=SimpleNamespace(project=project,timeline=SimpleNamespace(selected_ids={'title','audio','video'})),item_id='video')
        self.assertEqual(PropertiesPanel.targets(panel),[video]);self.assertEqual(PropertiesPanel.targets(panel,True),[])
        panel.item_id='audio';self.assertEqual(PropertiesPanel.targets(panel,True),[audio])
        panel.item_id='title';self.assertEqual(PropertiesPanel.targets(panel),[title])
        replacement=TimelineItem('video','other','video_1',9,4);panel.window.project=Project(timeline=[replacement]);panel.item_id='video'
        self.assertEqual(PropertiesPanel.targets(panel),[replacement]);self.assertIs(PropertiesPanel.targets(panel)[0],replacement)


if __name__=='__main__':unittest.main()
