import unittest
from unittest.mock import Mock,patch
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt
from PySide6.QtMultimedia import QMediaPlayer
from kinetic_cut.ui import MainWindow


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
