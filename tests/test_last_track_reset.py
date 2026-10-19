import copy,unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from kinetic_cut.model import Project,TimelineItem,Caption
from kinetic_cut.transitions import Transition
from kinetic_cut.ui import MainWindow


class LastTrackResetTests(unittest.TestCase):
    def test_delete_empty_tracks_promotes_first_populated_lane_and_is_undoable(self):
        window=MainWindow();window.autosave_timer.stop()
        try:
            for kind in ('video','audio'):
                p=Project();second=p.add_track(kind);third=p.add_track(kind);fourth=p.add_track(kind)
                first=kind+'_1';p.track_names[third]='Custom lane'
                p.track_states[second]['muted']=True
                p.timeline=[TimelineItem('keep','',second,0,2),TimelineItem('custom','',third,0,2)]
                p.transitions=[Transition('keep-transition','Cross Dissolve',track=second,start=.5,duration=.5)]
                window.set_project(p);window.timeline.selected_track=first;before=copy.deepcopy(p.to_dict())
                window.timeline_command('delete_empty_tracks',None)
                self.assertEqual(getattr(p,kind+'_tracks'),[second,third])
                self.assertEqual(p.track_names[second],kind.title()+' 1');self.assertEqual(p.track_names[third],'Custom lane')
                self.assertTrue(p.track_states[second]['muted']);self.assertEqual(p.transitions[0].track,second)
                self.assertEqual([i.track for i in p.timeline],[second,third]);self.assertEqual(window.timeline.selected_track,second)
                self.assertEqual([i.id for i in p.runtime_index.active('timeline',1)],['keep','custom'])
                window.undo();restored=window.project.to_dict()
                for value in (before,restored):value.pop('modified_at',None);value.pop('playhead',None)
                self.assertEqual(restored,before)
                window.redo();self.assertEqual(getattr(window.project,kind+'_tracks'),[second,third])
                self.assertEqual(Project.from_dict(window.project.to_dict()).to_dict(),window.project.to_dict())
            p=Project();p.add_track('video');p.add_track('audio');window.set_project(p)
            window.timeline_command('delete_empty_tracks',None)
            self.assertEqual(p.video_tracks,['video_1']);self.assertEqual(p.audio_tracks,['audio_1'])
        finally:window.close();window.deleteLater();QApplication.processEvents()

    def test_only_last_lane_of_its_type_clears_and_resets(self):
        for kind in ('video','audio'):
            track=kind+'_7';other='audio_1' if kind=='video' else 'video_1'
            p=Project();setattr(p,kind+'_tracks',[track]);p.track_names[track]='Custom';p.track_states[track]={'visible':False,'locked':True,'muted':True}
            p.timeline=[TimelineItem('clear','',track,0,3),TimelineItem('keep','',other,0,3)]
            p.captions=[Caption('keep-caption',0,1,'Keep')]
            p.transitions=[Transition('clear-transition','Cross Dissolve',track=track,start=1,duration=.5)]
            self.assertTrue(p.delete_track(track))
            default=kind+'_1';self.assertEqual(getattr(p,kind+'_tracks'),[default])
            self.assertEqual(p.track_names[default],kind.title()+' 1')
            self.assertEqual(p.track_states[default],{'visible':True,'locked':False,'muted':False})
            self.assertEqual([i.id for i in p.timeline],['keep']);self.assertEqual(len(p.captions),1);self.assertFalse(p.transitions)
            self.assertNotIn(track,p.track_names);self.assertNotIn(track,p.track_states)
            restored=Project.from_dict(p.to_dict());self.assertEqual(restored.to_dict(),p.to_dict())
            self.assertEqual([i.id for i in p.runtime_index.active('timeline',1)],['keep'])

    def test_multiple_lanes_still_delete_normally_and_invalid_lane_is_unchanged(self):
        for kind in ('video','audio'):
            p=Project();second=p.add_track(kind)
            p.timeline=[TimelineItem('remove','',kind+'_1',0,2),TimelineItem('keep','',second,0,2)]
            self.assertTrue(p.delete_track(kind+'_1'));self.assertEqual(getattr(p,kind+'_tracks'),[second])
            self.assertEqual([i.id for i in p.timeline],['keep'])
            before=p.to_dict();self.assertFalse(p.delete_track('not-a-track'));self.assertEqual(p.to_dict(),before)

    def test_user_command_can_cancel_and_undo_the_entire_last_layer_reset(self):
        window=MainWindow();window.autosave_timer.stop()
        try:
            for kind in ('video','audio'):
                p=Project(timeline=[TimelineItem('clear','',kind+'_1',0,3,role='title' if kind=='video' else 'source_audio')])
                p.track_names[kind+'_1']='My Layer';p.track_states[kind+'_1']['muted']=True
                window.set_project(p);before=copy.deepcopy(p.to_dict())
                with patch('kinetic_cut.ui.QMessageBox.question',return_value=QMessageBox.No):window.timeline_command('delete_track',kind+'_1')
                self.assertEqual(window.project.to_dict(),before)
                with patch('kinetic_cut.ui.QMessageBox.question',return_value=QMessageBox.Yes):window.timeline_command('delete_track',kind+'_1')
                self.assertFalse(window.project.timeline);self.assertEqual(window.timeline.selected_track,kind+'_1')
                window.undo();restored=window.project.to_dict()
                for value in (before,restored):value.pop('modified_at',None);value.pop('playhead',None)
                self.assertEqual(restored,before)
                window.redo();self.assertFalse(window.project.timeline)
        finally:window.close();window.deleteLater();QApplication.processEvents()
