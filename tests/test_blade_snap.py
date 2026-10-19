import unittest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,TimelineItem,Caption
from kinetic_cut.timeline import TimelineWidget


class BladeSnapTests(unittest.TestCase):
    def setUp(self):
        self.p=Project(video_tracks=['video_1','video_2'],timeline=[TimelineItem('target','','video_1',0,12),TimelineItem('above','','video_2',0,5),TimelineItem('right','','video_2',5,7)],captions=[Caption('caption',0,12,'words')])
        self.p.playhead=11;self.t=TimelineWidget();self.t.set_project(self.p);self.t.setProperty('snapping',True);self.t.pixels_per_second=100
    def tearDown(self):
        self.t.close();self.t.deleteLater();QApplication.processEvents()
    def at(self,seconds,item=None):return self.t._blade_time(item or self.p.timeline[0],self.t.x_for_time(seconds))

    def test_wider_hold_near_isolated_cut_and_immediate_pointer_tracking(self):
        for direction in (-1,1):
            self.t._blade_snap=None
            self.assertEqual(self.at(5+direction*.11),5)
            self.assertNotEqual(self.at(5+direction*.13),5)
            self.assertEqual(self.at(5+direction*.11),5,'No latch or mouse exit is required to recapture')
            self.assertEqual(self.at(5+direction*.10),5)

    def test_adjacent_targets_handoff_at_midpoint_in_both_directions(self):
        self.p.captions.append(Caption('nearby',5.12,6,'nearby'))
        self.assertEqual(self.at(5.01),5)
        self.assertEqual(self.at(5.05),5)
        self.assertEqual(self.at(5.07),5.12)
        self.assertEqual(self.at(5.05),5)

    def test_continuous_sweep_visits_all_staggered_boundaries_without_exit(self):
        edges=[4.80,4.89,5.,5.07,5.19,5.28,5.41]
        self.p.timeline=[self.p.timeline[0],*[TimelineItem('edge'+str(n),'','video_2' if n%2 else 'audio_1',at,1) for n,at in enumerate(edges)]]
        self.p.captions=[Caption('cap',5.13,6,'words')];edges.append(5.13);edges.sort()
        for steps in (range(475,547),range(546,474,-1)):
            seen=[]
            for step in steps:
                pointer=step/100;nearest=min(edges,key=lambda edge:abs(edge-pointer));actual=self.at(pointer)
                self.assertAlmostEqual(abs(actual-pointer),abs(nearest-pointer),places=6)
                if actual not in seen:seen.append(actual)
            self.assertEqual(seen,edges if steps.step>0 else list(reversed(edges)))

    def test_playhead_hold_does_not_mask_a_closer_edit(self):
        self.p.playhead=5
        self.assertEqual(self.at(5.01),5)
        self.p.captions.append(Caption('nearby',5.12,6,'words'))
        self.assertEqual(self.at(5.08),5.12)

    def test_nearby_caption_defers_to_video_until_zoom_makes_it_distinct(self):
        self.p.captions.append(Caption('nearby',5.03,8,'words'))
        for zoom in (20,100):
            self.t.pixels_per_second=zoom;self.assertEqual(self.at(5.03),5)
        self.t.pixels_per_second=240;self.assertEqual(self.at(5.03),5.03)

    def test_caption_priority_is_local_and_only_for_media_blading(self):
        self.p.captions.append(Caption('nearby',5.04,8,'words'))
        self.assertEqual(self.at(5.04),5)
        self.assertEqual(self.at(5.04,self.p.captions[0]),5.04)
        self.assertEqual(self.at(5.14),5.04,'Video outside capture range must not hide a subtitle target')
        self.t.setProperty('snapping',False);self.assertNotEqual(self.at(5.04),5)

    def test_close_subtitle_priority_never_hides_the_next_video_cut(self):
        video_edges=[5.,5.08,5.16]
        self.p.timeline=[self.p.timeline[0],*[TimelineItem(str(n),'','video_2',at,1) for n,at in enumerate(video_edges)]]
        self.p.captions=[Caption(str(n),at+.03,8,'words') for n,at in enumerate(video_edges)]
        for steps in (range(496,522),range(521,495,-1)):
            for step in steps:
                pointer=step/100;actual=self.at(pointer);nearest=min(video_edges,key=lambda edge:abs(edge-pointer))
                self.assertAlmostEqual(abs(actual-pointer),abs(nearest-pointer),places=6)

    def test_audio_edges_do_not_suppress_subtitle_targets(self):
        self.p.timeline=[self.p.timeline[0],TimelineItem('audio','','audio_1',5,2)]
        self.p.captions.append(Caption('nearby',5.03,8,'words'))
        self.assertEqual(self.at(5.03),5.03)

    def test_media_and_caption_edges_on_any_layer_share_exact_timestamp(self):
        boundary=5.007
        self.p.timeline[1].duration=boundary;self.p.timeline[2].start=boundary
        for item in (self.p.timeline[0],self.p.captions[0]):
            self.t._blade_snap=None
            self.assertEqual(self.at(boundary+.10,item),boundary)
            self.assertEqual(self.at(boundary+.11,item),boundary)
        self.p.timeline=[self.p.timeline[0]];self.p.captions.append(Caption('edge',boundary,8,'edge'))
        self.assertEqual(self.at(boundary+.10),boundary)

    def test_pixel_distances_do_not_depend_on_zoom_or_scroll(self):
        for zoom in (20,100,240):
            self.t.pixels_per_second=zoom;self.t._range();self.t.horizontalScrollBar().setValue(15);self.t._blade_snap=None
            self.assertEqual(self.at(5+11/zoom),5)
            self.assertNotEqual(self.at(5+13/zoom),5)

    def test_snap_off_and_removed_or_moved_edges_release_hold(self):
        self.assertEqual(self.at(5.10),5)
        self.t.setProperty('snapping',False);self.assertNotEqual(self.at(5.20),5)
        self.t.setProperty('snapping',True);self.assertNotEqual(self.at(5.20),5)
        self.assertEqual(self.at(5.10),5)
        self.p.timeline[1].duration=7;self.p.timeline[2].start=7
        self.assertNotEqual(self.at(5.20),5)
        self.assertEqual(self.at(7.10),7)
        self.p.timeline=self.p.timeline[:1];self.assertNotEqual(self.at(7.20),7)

    def test_clip_limits_invalid_nearest_and_tool_or_pointer_exit(self):
        self.assertEqual(self.at(5.10),5)
        self.assertGreater(self.at(5.20,self.p.timeline[2]),5,'Cannot cut at the hovered clip endpoint')
        self.t._blade_snap=None;self.assertEqual(self.at(5.10),5)
        self.t.set_tool('select');self.t.set_tool('blade');self.assertNotEqual(self.at(5.20),5)
        self.assertEqual(self.at(5.10),5);self.t.leaveEvent(QEvent(QEvent.Leave));self.assertNotEqual(self.at(5.20),5)
        # The hovered clip's own nearest endpoint must not mask a valid cut.
        self.p.timeline[0].start=4.95;self.assertEqual(self.at(4.97),5)
