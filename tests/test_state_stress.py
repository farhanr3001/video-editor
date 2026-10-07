"""Deterministic editor-state stress and failure-path regressions.

Fixtures are synthetic and stay inside the runner's isolated application home.
The seeded exercises check independent timing/source/lock/persistence invariants,
rather than treating completion without an exception as successful editing.
"""
import copy
import json
import math
import os
import random
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QEventLoop, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication

from kinetic_cut.assistant_api import edited, validate
from kinetic_cut.compounds import create
from kinetic_cut.keyframes import evaluated
from kinetic_cut.model import Caption, Crop, MediaItem, Project, TimelineItem, Transform
from kinetic_cut.transitions import Transition
from kinetic_cut.timeline_actions import delete_gaps, keep_audio_ranges


def session_fixture(pairs=80):
    project = Project(name='Disposable state stress')
    project.media = [MediaItem('source', 'synthetic.mp4', 'video', 'Synthetic',
                               7200, 640, 360, 60, True)]
    for _ in range(3):
        project.add_track('video')
    project.add_track('audio')
    for n in range(pairs):
        start = n * 2.5
        link = f'link-{n}'
        for track in ('video_1', 'video_2', 'video_3', 'audio_1'):
            item = TimelineItem(f'{track}-{n}', 'source', track, start, 2.5,
                                in_point=n * 4, link_id=link)
            item.effects = [{'name': 'Gaussian Blur', 'enabled': True,
                             'horizontal': 12, 'vertical': 8}]
            item.keyframes = {'scale': [{'time': 0., 'value': .8, 'interpolation': 'Linear'},
                                       {'time': 2.5, 'value': 1.6, 'interpolation': 'Linear'}]}
            project.timeline.append(item)
        project.timeline.append(TimelineItem(f'graphic-{n}', '', 'video_4', start, 1.,
                                             role='graphic', graphic_type='Circle',
                                             graphic_data={'radius': 50, 'stroke_width': 4}))
        project.captions.append(Caption(f'caption-{n}', start + .1, start + 1.9,
                                        f'Actual words {n}', word_timings=[
                                            {'word': 'Actual', 'start': 0., 'end': .5},
                                            {'word': 'words', 'start': .5, 'end': 1.}]))
    return project


def assert_integrity(test, project):
    validate(project)
    test.assertTrue(math.isfinite(project.duration))
    for rows in (project.timeline, project.captions, project.media, project.transitions):
        test.assertEqual(len({row.id for row in rows}), len(rows))
    tracks = project.video_tracks + project.audio_tracks
    for item in project.timeline:
        test.assertIn(item.track, tracks)
        if item.role not in {'title', 'graphic'}:
            media = project.media_by_id(item.media_id)
            test.assertIsNotNone(media)
            test.assertLessEqual(item.in_point + item.source_duration, media.duration + 1e-5)
    for transition in project.transitions:
        for identifier in (transition.left_item_id, transition.right_item_id):
            if identifier:
                item = project.item_by_id(identifier)
                test.assertIsNotNone(item, f'Orphan transition {transition.id}: {identifier}')
                test.assertEqual(item.track, transition.track)


class StateFailurePathTests(unittest.TestCase):
    def test_delete_gaps_retimes_transitions_and_remaps_fragment_edges(self):
        project = session_fixture(0)
        project.timeline = [TimelineItem('first', 'source', 'video_1', 0, 2),
                            TimelineItem('middle', 'source', 'video_1', 4, 2),
                            TimelineItem('last', 'source', 'video_1', 6, 2),
                            TimelineItem('overlay', 'source', 'video_2', 0, 8)]
        project.transitions = [Transition(id='join', name='Cross Dissolve', track='video_1',
            start=5.8, duration=.4, left_item_id='middle', right_item_id='last'),
            Transition(id='overlay-edge', name='Cross Dissolve', track='video_2',
                       start=7.6, duration=.4, left_item_id='overlay')]
        removed, gaps = delete_gaps(project)
        self.assertEqual((removed, gaps), (2., [(2., 4.)]))
        self.assertAlmostEqual(project.transition_by_id('join').start, 3.8)
        self.assertAlmostEqual(project.transition_by_id('join').duration, .4)
        self.assertAlmostEqual(project.duration, 6.)
        overlay_transition = project.transition_by_id('overlay-edge')
        surviving_edge = project.item_by_id(overlay_transition.left_item_id)
        self.assertIsNotNone(surviving_edge)
        self.assertEqual((surviving_edge.start, surviving_edge.duration), (2., 4.))
        self.assertAlmostEqual(overlay_transition.start, 5.6)
        assert_integrity(self, project)

    def test_silence_pack_discards_transition_from_separated_neighbour(self):
        project = session_fixture(0)
        project.timeline = [TimelineItem('left', 'source', 'video_1', 0, 4, link_id='av'),
                            TimelineItem('audio', 'source', 'audio_1', 0, 4, link_id='av'),
                            TimelineItem('right', 'source', 'video_1', 4, 2)]
        project.transitions = [Transition(id='join', name='Cross Dissolve', track='video_1',
            start=3.8, duration=.4, left_item_id='left', right_item_id='right')]
        # Packing without removing time exercises real replacement IDs while
        # preserving the cut. A discarded zero-length range should be harmless.
        keep_audio_ranges(project, project.item_by_id('audio'), [(0, 4), (5, 5)], True)
        assert_integrity(self, project)
        # Local packing shortens the group without moving its neighbour, so
        # the previous cross-clip join no longer has a common cut.
        keep_audio_ranges(project, project.item_by_id('audio'), [(1, 4)], True)
        self.assertFalse(project.transitions)  # Local packing separates its neighbour.
        assert_integrity(self, project)

    def test_silence_local_pack_retargets_single_edge_and_drops_cut_edge(self):
        project = session_fixture(0)
        project.timeline = [TimelineItem('left', 'source', 'video_1', 0, 4, link_id='av'),
                            TimelineItem('audio', 'source', 'audio_1', 0, 4, link_id='av')]
        project.transitions = [Transition(id='fade-in', name='Cross Dissolve', track='video_1',
            start=0., duration=.4, right_item_id='left'),
            Transition(id='fade-out', name='Cross Dissolve', track='video_1',
                       start=3.6, duration=.4, left_item_id='left')]
        keep_audio_ranges(project, project.item_by_id('audio'), [(1, 2), (3, 4)], True)
        self.assertIsNone(project.transition_by_id('fade-in'))
        outgoing = project.transition_by_id('fade-out')
        self.assertAlmostEqual(outgoing.start, 1.6)
        self.assertAlmostEqual(outgoing.duration, .4)
        owner = project.item_by_id(outgoing.left_item_id)
        self.assertEqual((owner.start, owner.duration, owner.in_point), (1., 1., 3.))
        assert_integrity(self, project)

    def test_mcp_insert_clip_preserves_explicit_crop_and_transform(self):
        project = session_fixture(0)
        result, identifiers = edited(project, [dict(op='insert_clip', media_id='source',
            track='video_1', start=0., duration=3.,
            crop=dict(x=.2, y=.1, width=.5, height=.6),
            transform=dict(x=.3, y=.4, scale=1.4, scale_y=.7, rotation=24.))])
        item = result.item_by_id(identifiers[0])
        self.assertEqual(item.crop, Crop(.2, .1, .5, .6))
        self.assertEqual((item.transform.x, item.transform.y, item.transform.scale,
                          item.transform.scale_y, item.transform.rotation), (.3, .4, 1.4, .7, 24.))
        self.assertFalse(project.timeline)

    def test_locked_caption_and_transition_additions_are_atomic(self):
        for collection, track, values in (
            ('captions', 'subtitle_1', dict(text='Locked caption')),
            ('transitions', 'video_1', dict(start=0., duration=.5, track='video_1')),
        ):
            project = session_fixture(0)
            project.track_states[track] = {'locked': True}
            before = project.to_dict()
            with self.assertRaisesRegex(ValueError, '[Ll]ocked'):
                edited(project, [dict(op='rename_project', name='Must rollback'),
                                 dict(op='add', collection=collection, values=values)])
            self.assertEqual(project.to_dict(), before)

    def test_deleted_clip_and_lane_remove_only_dependent_transitions(self):
        project = session_fixture(2)
        project.transitions = [Transition('dependent', 'Cross Dissolve', 'Dissolve', 'video_1',
                                          2.25, .5, 'video_1-0', 'video_1-1'),
                               Transition('unrelated', 'Cross Dissolve', 'Dissolve', 'video_2',
                                          2.25, .5, 'video_2-0', 'video_2-1')]
        project.delete(['video_1-0'])
        self.assertEqual([t.id for t in project.transitions], ['unrelated'])
        self.assertTrue(project.delete_track('video_2'))
        self.assertFalse(project.transitions)
        assert_integrity(self, project)

    def test_compounds_rebase_only_selected_transitions(self):
        project = session_fixture(4)
        project.transitions = [Transition('selected', 'Cross Dissolve', 'Dissolve', 'video_1',
                                           7.25, .5, 'video_1-2', 'video_1-3'),
                               Transition('outside', 'Cross Dissolve', 'Dissolve', 'video_2',
                                           2.25, .5, 'video_2-0', 'video_2-1')]
        asset, clips = create(project, {'video_1-2', 'video_1-3'}, set(), 'Selected span')
        child = Project.from_dict(asset.compound)
        self.assertEqual([t.id for t in child.transitions], ['selected'])
        self.assertAlmostEqual(child.transitions[0].start, 2.25)
        self.assertEqual([t.id for t in project.transitions], ['outside'])
        self.assertEqual((asset.duration, clips[0].duration), (5., 5.))
        assert_integrity(self, child)
        assert_integrity(self, project)

    def test_split_and_overwrite_preserve_transition_edge_ownership(self):
        project = session_fixture(2)
        project.transitions = [Transition('join', 'Cross Dissolve', 'Dissolve', 'video_1',
                                          2.25, .5, 'video_1-0', 'video_1-1')]
        right_id = project.split_selection(['video_1-0'], 1.25, linked=False)[0]
        self.assertEqual(project.transitions[0].left_item_id, right_id)
        self.assertEqual(project.transitions[0].right_item_id, 'video_1-1')
        project.timeline.append(TimelineItem('overwrite', 'source', 'video_1', 1.5, .4))
        project.overwrite(['overwrite'])
        outgoing = project.item_by_id(project.transitions[0].left_item_id)
        self.assertAlmostEqual(outgoing.start + outgoing.duration, 2.5)
        self.assertGreater(outgoing.start, 1.5)
        assert_integrity(self, project)
        project.timeline.append(TimelineItem('remove-edge', 'source', 'video_1', 2., .5))
        project.overwrite(['remove-edge'])
        self.assertFalse(project.transitions)

    def test_compound_generator_selection_and_cross_boundary_transition_safe(self):
        project = session_fixture(3)
        project.transitions = [Transition('boundary', 'Cross Dissolve', 'Dissolve', 'video_1',
                                          4.75, .5, 'video_1-1', 'video_1-2')]
        asset, clips = create(project, (identifier for identifier in ('video_1-0', 'video_1-1')),
                          (identifier for identifier in ('caption-0', 'caption-1')), 'Generators')
        child = Project.from_dict(asset.compound)
        self.assertEqual(len(child.timeline), 2)
        self.assertEqual(len(child.captions), 2)
        self.assertFalse(child.transitions)
        self.assertEqual(project.transitions[0].left_item_id, clips[0].id)
        self.assertEqual(project.transitions[0].right_item_id, 'video_1-2')
        assert_integrity(self, project)

    def test_compound_cross_lane_transition_refuses_atomically(self):
        project = session_fixture(3)
        project.transitions = [Transition('boundary', 'Cross Dissolve', 'Dissolve', 'video_1',
                                          4.75, .5, 'video_1-1', 'video_1-2')]
        before = project.to_dict()
        with self.assertRaisesRegex(ValueError, 'both sides'):
            create(project, {'video_1-0', 'video_1-1', 'video_2-1'}, set(), 'Cross lane')
        self.assertEqual(project.to_dict(), before)

    def test_invalid_orphan_transition_and_nonfinite_parameters_are_atomic(self):
        project = session_fixture(2)
        for values in (dict(left_item_id='missing'), dict(duration=float('inf')),
                       dict(properties={'intensity': float('nan')})):
            before = project.to_dict()
            with self.assertRaises(ValueError):
                edited(project, [dict(op='add', collection='transitions', values=values)])
            self.assertEqual(project.to_dict(), before)

    def test_missing_generated_asset_repeated_save_and_reload_preserves_edit(self):
        from PySide6.QtGui import QImage
        from kinetic_cut import missing_media as mm
        fixture_root = Path(os.environ['KINETIC_CUT_HOME']) / 'state-fixtures'
        fixture_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=fixture_root) as directory:
            root = Path(directory)
            source = root / 'generated.png'
            image = QImage(100, 100, QImage.Format_RGB32)
            image.fill(0xffaaccee)
            self.assertTrue(image.save(str(source)))
            media = MediaItem('still', str(source), 'image', 'Own generated fixture', 5., 100, 100)
            project = Project(media=[media], timeline=[TimelineItem('still-clip', media.id,
                'video_1', 2., 12., transform=Transform(.3, .4, 1.2))], portable_media=True)
            document = root / 'own.kcut'
            project.save(document)
            source.unlink()
            for _ in range(20):
                restored = Project.load(document)
                mm.publish(mm.scan(mm.source_paths(restored)))
                self.assertTrue(mm.is_missing(restored.media[0]))
                self.assertTrue(mm.export_issues(restored))
                self.assertEqual(restored.timeline, project.timeline)
                restored.save(document)
            self.assertTrue(image.save(str(source)))
            mm.publish(mm.scan(mm.source_paths(restored)))
            self.assertFalse(mm.is_missing(restored.media[0]))
            self.assertFalse(mm.export_issues(restored))
        mm._missing.clear()

    def test_failed_save_as_preserves_current_path_and_saved_document(self):
        fixture_root = Path(os.environ['KINETIC_CUT_HOME']) / 'state-fixtures'
        fixture_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=fixture_root) as directory:
            root = Path(directory)
            project = session_fixture(2)
            original = root / 'original.kcut'
            project.save(original)
            saved_bytes = original.read_bytes()
            before = project.to_dict()
            with patch.object(Path, 'replace', side_effect=OSError('Simulated full disk / locked destination')):
                with self.assertRaises(OSError):
                    project.save(root / 'failed-save-as.kcut')
            self.assertEqual(project.to_dict(), before)
            self.assertEqual(original.read_bytes(), saved_bytes)
            self.assertFalse((root / 'failed-save-as.kcut').exists())
        with self.assertRaisesRegex(ValueError, 'path'):
            Project().save()

    def test_invalid_batches_do_not_mutate_after_partial_valid_actions(self):
        project = session_fixture(3)
        invalids = [dict(op='bogus'), dict(op='trim', ids=['video_1-0'], delta=float('nan'), edge='left'),
                    dict(op='add', collection='captions', values=dict(start=-1., end=3., text='Bad')),
                    dict(op='update', collection='timeline', id='video_1-0', values=dict(duration=-1.)),
                    dict(op='add', collection='timeline', values=dict(role='normal', media_id='unknown'))]
        for invalid in invalids:
            before = project.to_dict()
            with self.assertRaises((ValueError, TypeError)):
                edited(project, [dict(op='rename_project', name='Partial'), invalid])
            self.assertEqual(project.to_dict(), before)


class SeededStateStressTests(unittest.TestCase):
    def test_seeded_layered_edits_preserve_source_animation_and_locks(self):
        for seed in (731, 991, 20261006):
            rng = random.Random(seed)
            project = session_fixture(50)
            project.track_states['video_3']['locked'] = True
            locked = [asdict(i) for i in project.timeline if i.track == 'video_3']
            for step in range(150):
                candidates = [i for i in project.timeline if i.role == 'normal' and i.track != 'video_3']
                item = rng.choice(candidates)
                operation = rng.choice(('split', 'trim', 'retime', 'move', 'delete', 'caption'))
                if operation == 'split' and item.duration > .15:
                    at = item.start + item.duration * .5
                    original = copy.deepcopy(item)
                    result = project.split_selection([item.id], at, linked=False)
                    if result:
                        right = project.item_by_id(result[0])
                        for fraction in (.0, .3, .8):
                            time = right.start + fraction * right.duration
                            self.assertAlmostEqual(original.source_time(time), right.source_time(time))
                            self.assertAlmostEqual(evaluated(original, time - original.start).transform.scale,
                                                   evaluated(right, time - right.start).transform.scale)
                elif operation == 'trim':
                    project.trim_items([item.id], rng.uniform(-.25, .25), rng.choice(('left', 'right')))
                elif operation == 'retime':
                    original = copy.deepcopy(item)
                    project.retime_items([item.id], rng.uniform(.4, 3.))
                    self.assertAlmostEqual(original.source_duration, item.source_duration)
                    self.assertAlmostEqual(evaluated(original, original.duration * .7).transform.scale,
                                           evaluated(item, item.duration * .7).transform.scale)
                elif operation == 'move':
                    item.start = max(0., item.start + rng.uniform(-.5, .5))
                    project.overwrite([item.id])
                elif operation == 'delete' and len(candidates) > 15:
                    project.delete([item.id], ripple=rng.choice((True, False)))
                elif operation == 'caption':
                    cap = rng.choice(project.captions)
                    cap.start = max(0., cap.start + rng.uniform(-.2, .2))
                    cap.end = cap.start + 1.
                    project.overwrite_captions([cap.id])
                assert_integrity(self, project)
                self.assertEqual([asdict(i) for i in project.timeline if i.track == 'video_3'], locked)
                if step % 25 == 0:
                    project = Project.from_dict(json.loads(json.dumps(project.to_dict())))
            fixture_root = Path(os.environ['KINETIC_CUT_HOME']) / 'state-fixtures'
            fixture_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=fixture_root) as directory:
                path = Path(directory) / 'stress.kcut'
                project.save(path)
                self.assertEqual(Project.load(path).to_dict(), project.to_dict())

    def test_large_nested_document_repeated_roundtrip_without_aliasing(self):
        project = session_fixture(300)
        child = session_fixture(20)
        project.media.append(MediaItem('nested', '', 'video', 'Nested', child.duration,
                                       compound=child.to_dict()))
        for _ in range(12):
            document = project.to_dict()
            restored = Project.from_dict(json.loads(json.dumps(document)))
            self.assertEqual(restored.to_dict(), document)
            restored.media[-1].compound['captions'][0]['text'] = 'Mutation isolation'
            self.assertNotEqual(restored.media[-1].compound, project.media[-1].compound)
            assert_integrity(self, project)


class NativeHistoryStressTests(unittest.TestCase):
    def test_large_project_rapid_history_branches_selection_and_page_switches(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.workspace import set_page
        w = MainWindow()
        w.autosave_timer.stop()
        try:
            with patch.object(w.compounds, 'request_caches'), patch.object(w.preview_quality, 'request'):
                from kinetic_cut import missing_media as mm
                mm.publish({mm.path_key('synthetic.mp4'): True})
                w.set_project(session_fixture(100))
                first = copy.deepcopy(w.project.to_dict())
                for n in range(135):
                    w.project.timeline[0].transform.rotation = float(n)
                    w.project.timeline[0].effects[0]['horizontal'] = n % 50
                    w.commit_history()
                self.assertEqual(len(w._history), 100)
                immutable = [copy.deepcopy(p.to_dict()) for p in w._history]
                for _ in range(3):
                    for _ in range(99):
                        w.undo()
                    self.assertEqual(w.project.timeline[0].transform.rotation, 35.)
                    for _ in range(99):
                        w.redo()
                    self.assertEqual(w.project.timeline[0].transform.rotation, 134.)
                    self.assertEqual([p.to_dict() for p in w._history], immutable)
                w.undo()
                w.project.captions[0].text = 'Actual new branch'
                w.commit_history()
                w.redo()
                self.assertEqual(w.project.captions[0].text, 'Actual new branch')
                w.timeline.select_ids({'video_1-0'}, 'video_1-0')
                w.delete_selected()
                self.assertFalse(w.timeline.selected_ids)
                w.undo()
                self.assertIsNotNone(w.project.item_by_id('video_1-0'))
                for _ in range(20):
                    for page in (1, 2, 0):
                        set_page(w, page)
                self.assertEqual(w.project.captions[0].text, 'Actual new branch')
                self.assertEqual(first['media'], w.project.to_dict()['media'])
                assert_integrity(self, w.project)
        finally:
            w._saved_project_key = w._history_key(w.project)
            w.close()
            QThreadPool.globalInstance().waitForDone(10000)
            loop = QEventLoop()
            QTimer.singleShot(50, loop.quit)
            loop.exec()
            w.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            QApplication.processEvents()
            mm._missing.clear()
