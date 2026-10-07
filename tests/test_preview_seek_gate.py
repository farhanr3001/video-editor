import unittest
from unittest.mock import Mock,patch
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt
from PySide6.QtMultimedia import QMediaPlayer
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project, MediaItem, TimelineItem


class PreviewSeekGateTests(unittest.TestCase):
    def setUp(self):
        self.w=MainWindow(); self.w.autosave_timer.stop(); self.t=self.w.transport
        self.key=('source',30.,1.,'video'); self.player=Mock(); self.sink=Mock(); self.sink._frame_stamp=None
        self.frame=Mock(); self.frame.isValid.return_value=True
        image=QImage(8,8,QImage.Format_RGB32); image.fill(Qt.blue); self.frame.toImage.return_value=image
        self.sink.videoFrame.return_value=self.frame; self.t.decoders[self.key]=(self.player,Mock(),self.sink)
    def tearDown(self):
        with patch('kinetic_cut.transport.QMetaObject.invokeMethod'):self.w.close()
        self.w.deleteLater()
    def stamp(self,start,end):self.frame.startTime.return_value=start; self.frame.endTime.return_value=end
    def test_loading_source_zero_never_published_or_paused(self):
        self.t.position_decoder(self.key,31102); self.stamp(83000,100000)
        self.t.poll_frames(); self.frame.toImage.assert_not_called(); self.player.pause.assert_not_called()
        self.assertNotIn(self.key,self.w.preview.frames)
        self.t.decoder_loaded(self.key,self.player,QMediaPlayer.LoadedMedia)
        self.player.setPosition.assert_called_with(31102); self.player.play.assert_called_once()
        self.stamp(31100000,31116667); self.t.poll_frames()
        self.assertIn(self.key,self.w.preview.frames); self.assertNotIn(self.key,self.t._pending_video_seeks)
        self.player.pause.assert_called_once()
    def test_latest_seek_rejects_previous_position_and_accepts_containing_frame(self):
        self.t.position_decoder(self.key,20000); self.t.position_decoder(self.key,12002)
        self.stamp(20000000,20016667); self.t.poll_frames(); self.frame.toImage.assert_not_called()
        self.stamp(12000000,12016667); self.t.poll_frames(); self.frame.toImage.assert_called_once()
    def test_retired_decoder_cannot_restart_from_late_load_notification(self):
        self.t.position_decoder(self.key,30000)
        with patch('kinetic_cut.transport.QMetaObject.invokeMethod'):self.t.retire_decoder(self.key)
        self.t.decoder_loaded(self.key,self.player,QMediaPlayer.LoadedMedia)
        self.player.play.assert_not_called(); self.assertFalse(self.t._pending_video_seeks)

    def resume_project(self, player_position=2020):
        p=Project(media=[MediaItem('source','fixture.mp4','video','fixture',20,640,360,30)],
                  timeline=[TimelineItem('v','source','video_1',0,20)])
        self.w.project=p; self.w.preview.set_project(p)
        self.key=('source',0.,1.,'video'); self.t.decoders={self.key:(self.player,Mock(),self.sink)}
        self.t._project=p; self.t.position=2.
        self.player.position.return_value=player_position
        self.player.playbackState.return_value=QMediaPlayer.PausedState

    def test_resume_does_not_reseek_positioned_decoder_or_reset_frame_gate(self):
        self.resume_project()
        self.t._frame_epochs[self.key]=7; self.t._video_seek_floor[self.key]=1_500_000
        with patch.object(self.t,'position_decoder',wraps=self.t.position_decoder) as seek:
            self.t.play(); seek.assert_not_called()
        self.player.play.assert_called_once()
        self.assertEqual(self.t._frame_epochs[self.key],7)
        self.assertEqual(self.t._video_seek_floor[self.key],1_500_000)

    def test_resume_still_corrects_drift_and_explicit_seek_positions(self):
        self.resume_project(1000)
        self.t.play(); self.player.setPosition.assert_called_with(2000)
        self.t.pause(); self.player.reset_mock(); self.player.position.return_value=2000
        self.t.seek(2.1); self.player.setPosition.assert_called_with(2100)

    def test_restart_at_project_end_still_positions_to_start(self):
        self.resume_project(20000); self.t.position=20.
        self.t.play(); self.player.setPosition.assert_called_with(0)
        self.assertEqual(self.t.position,0.)
