import copy
import unittest
from dataclasses import asdict

from kinetic_cut.model import Caption, Project, TimelineItem
from kinetic_cut.ripple_delete import deletion_clock
from kinetic_cut.transitions import Transition


class RippleDeleteTests(unittest.TestCase):
    def cuts(self):
        p = Project()
        p.add_track("video"); p.add_track("video")
        # Exact frame boundaries from the reported lag test project, at 60fps.
        boundaries = [0, 232, 568, 1334, 2290, 2907, 3481, 3782, 4127]
        selected = set()
        for lane in ("video_1", "video_2", "video_3", "audio_1"):
            for n, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
                item = TimelineItem(f"{lane}-{n}", "source", lane, start/60, (end-start)/60,
                                    in_point=start/60, group_id=str(n), speed=1.25,
                                    keyframes={"opacity": [{"time": .1, "value": 70}]})
                p.timeline.append(item)
                if n in (1, 3, 5): selected.add(item.id)
        # Split-created items need not be stored chronologically.
        p.timeline.reverse()
        return p, selected

    def test_reported_separated_cuts_all_lanes_pack_once_and_preserve_source(self):
        p, selected = self.cuts()
        original = {i.id: asdict(i) for i in p.timeline}
        p.delete(iter(selected), True)
        expected = [0, 232/60, 998/60, 1615/60, 1916/60]
        for lane in ("video_1", "video_2", "video_3", "audio_1"):
            items = sorted((i for i in p.timeline if i.track == lane), key=lambda i: i.start)
            self.assertEqual([i.id for i in items], [f"{lane}-{n}" for n in (0, 2, 4, 6, 7)])
            for item, start in zip(items, expected):
                self.assertAlmostEqual(item.start, start)
                actual = asdict(item); actual["start"] = original[item.id]["start"]
                self.assertEqual(actual, original[item.id])
            for left, right in zip(items, items[1:]):
                self.assertAlmostEqual(left.start + left.duration, right.start)

    def test_subtitle_only_separated_delete_preserves_word_offsets(self):
        p = Project(captions=[Caption(str(n), n*2, n*2+2, str(n)) for n in range(6)])
        p.captions[4].word_timings = [{"word": "4", "start": .2, "end": .7}]
        p.delete([], True, {"1", "3"})
        self.assertEqual([(c.id, c.start, c.end) for c in p.captions],
                         [("0", 0, 2), ("2", 2, 4), ("4", 4, 6), ("5", 6, 8)])
        self.assertEqual(p.captions[2].word_timings, [{"word": "4", "start": .2, "end": .7}])

    def test_mixed_caption_media_selection_uses_one_clock_and_merges_overlaps(self):
        p = Project(timeline=[TimelineItem("d", "", "video_1", 2, 3),
                              TimelineItem("keep", "", "audio_1", 9, 2)],
                    captions=[Caption("d1", 3, 6, "remove"), Caption("d2", 7, 8, "remove"),
                              Caption("keep", 9, 11, "keep")])
        p.delete({"d"}, True, {"d1", "d2"})
        self.assertEqual(p.timeline[0].start, 4)
        self.assertEqual((p.captions[0].start, p.captions[0].end), (4, 6))

    def test_surviving_crossing_items_protect_their_footage_and_sync(self):
        p = Project(timeline=[TimelineItem("d", "", "video_1", 2, 6),
                              TimelineItem("cross", "", "audio_1", 4, 2),
                              TimelineItem("tail", "", "audio_1", 8, 2)],
                    captions=[Caption("cross", 5, 7, "keep")])
        p.delete({"d"}, True)
        self.assertEqual([(i.id, i.start, i.duration) for i in p.timeline],
                         [("cross", 2, 2), ("tail", 5, 2)])
        self.assertEqual((p.captions[0].start, p.captions[0].end), (3, 5))

    def test_locked_items_and_captions_unchanged_and_not_removed(self):
        p = Project(timeline=[TimelineItem("d", "", "video_1", 2, 2),
                              TimelineItem("locked", "", "audio_1", 3, 5),
                              TimelineItem("tail", "", "video_1", 6, 2)],
                    captions=[Caption("locked", 4, 7, "keep")])
        p.track_states["audio_1"]["locked"] = True
        p.track_states["subtitle_1"] = {"locked": True}
        p.delete({"d", "locked"}, True, {"locked"})
        self.assertEqual([(i.id, i.start) for i in p.timeline], [("locked", 3), ("tail", 4)])
        self.assertEqual((p.captions[0].start, p.captions[0].end), (4, 7))

    def test_lift_keeps_survivors_in_place_and_empty_repeat_is_noop(self):
        p, selected = self.cuts(); before = {i.id: asdict(i) for i in p.timeline}
        p.delete(selected, False)
        self.assertEqual([asdict(i) for i in p.timeline], [before[i.id] for i in p.timeline])
        snapshot = copy.deepcopy(p.to_dict()); p.delete(selected, True)
        self.assertEqual(p.to_dict(), snapshot)

    def test_surviving_transition_follows_its_edge_deleted_edges_removed(self):
        p = Project(timeline=[TimelineItem("d", "", "video_1", 1, 2),
                              TimelineItem("left", "", "video_1", 4, 2),
                              TimelineItem("right", "", "video_1", 6, 2)])
        p.transitions = [Transition("keep", "Cross Dissolve", start=5.5, duration=1,
                                     left_item_id="left", right_item_id="right"),
                         Transition("delete", "Cross Dissolve", start=1, left_item_id="d")]
        p.delete({"d"}, True)
        self.assertEqual(len(p.transitions), 1)
        self.assertEqual((p.transitions[0].start, p.transitions[0].duration), (3.5, 1))
        self.assertEqual((p.timeline[0].start, p.timeline[1].start), (2, 4))

    def test_clock_many_disjoint_ranges_and_preexisting_gap(self):
        clock = deletion_clock([(n*4+1, n*4+2) for n in range(10000)], [])
        self.assertEqual(clock(40000), 30000)
        self.assertEqual(clock(.5), .5)
        self.assertEqual(clock(1.5), 1)
        self.assertEqual(clock(3), 2)  # unrelated preexisting empty time stays


if __name__ == "__main__": unittest.main()
