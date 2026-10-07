import unittest
from unittest.mock import Mock,patch
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt
from PySide6.QtMultimedia import QMediaPlayer
from kinetic_cut.ui import MainWindow


class PreviewSeekGateTests(unittest.TestCase):
    def setUp(self):
        self.invoke=patch('kinetic_cut.transport.QMetaObject.invokeMethod').start()
        self.addCleanup(patch.stopall)
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
        with patch('kinetic_cut.transport.QMetaObject.invokeMethod') as invoke:
            self.t.decoder_loaded(self.key,self.player,QMediaPlayer.LoadedMedia)
        self.player.setPosition.assert_not_called()
        self.assertEqual([call.args[1] for call in invoke.call_args_list],['setPosition','play'])
        self.assertTrue(all(call.args[2]==Qt.QueuedConnection for call in invoke.call_args_list))
        self.stamp(31100000,31116667); self.t.poll_frames()
        self.assertIn(self.key,self.w.preview.frames); self.assertNotIn(self.key,self.t._pending_video_seeks)
        self.player.pause.assert_not_called()
        self.assertEqual(self.invoke.call_args_list[-1].args,(self.player,'pause',Qt.QueuedConnection))
    def test_latest_seek_rejects_previous_position_and_accepts_containing_frame(self):
        self.t.position_decoder(self.key,20000); self.t.position_decoder(self.key,12002)
        self.stamp(20000000,20016667); self.t.poll_frames(); self.frame.toImage.assert_not_called()
        self.stamp(12000000,12016667); self.t.poll_frames(); self.frame.toImage.assert_called_once()
    def test_retired_decoder_cannot_restart_from_late_load_notification(self):
        self.t.position_decoder(self.key,30000)
        with patch('kinetic_cut.transport.QMetaObject.invokeMethod'):self.t.retire_decoder(self.key)
        self.t.decoder_loaded(self.key,self.player,QMediaPlayer.LoadedMedia)
        self.player.play.assert_not_called(); self.assertFalse(self.t._pending_video_seeks)

    def test_loading_decoder_defers_seek_and_play_until_ready(self):
        self.player.mediaStatus.return_value=QMediaPlayer.LoadingMedia
        self.player.position.return_value=0
        self.t.position_decoder(self.key,0); self.t.play_decoder(self.player)
        self.invoke.assert_not_called()
        self.assertEqual(self.t._loading_positions[self.key],0)
        self.player.mediaStatus.return_value=QMediaPlayer.LoadedMedia
        self.t.decoder_loaded(self.key,self.player,QMediaPlayer.LoadedMedia)
        self.invoke.assert_called_once_with(self.player,'play',Qt.QueuedConnection)
        self.assertNotIn(self.key,self.t._loading_positions)
    def test_loading_seeks_coalesce_and_retirement_invalidates_pending_position(self):
        self.player.mediaStatus.return_value=QMediaPlayer.LoadingMedia
        self.t.position_decoder(self.key,4001); self.t.position_decoder(self.key,11030)
        self.invoke.assert_not_called()
        self.assertEqual(self.t._loading_positions[self.key],11030)
        self.assertEqual(self.t._video_seek_floor[self.key],11030000)
        self.player.mediaStatus.return_value=QMediaPlayer.LoadedMedia
        with patch('kinetic_cut.transport.Q_ARG') as argument:
            self.t.decoder_loaded(self.key,self.player,QMediaPlayer.LoadedMedia)
            argument.assert_called_once_with('qint64',11030)
        self.assertEqual([call.args[1] for call in self.invoke.call_args_list],['setPosition','play'])
        self.player.mediaStatus.return_value=QMediaPlayer.LoadingMedia
        self.t.position_decoder(self.key,5000); self.t.retire_decoder(self.key)
        self.assertNotIn(self.key,self.t._loading_positions)
