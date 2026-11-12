"""Warmed native GPU decoders must not run ahead of their incoming cut."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QMediaPlayer
from kinetic_cut.qt_native import NativeVideoPlayer


class Engine:
    def __init__(self,*args):self.closed=False;self.commands=[]
    def command(self,kind,value):
        if not self.closed:self.commands.append((kind,value))
    def close(self):self.closed=True


class NativePrimingTests(unittest.TestCase):
    def setUp(self):
        self.transport=QObject();self.transport.playing=False
        self.transport.window=SimpleNamespace(preview=SimpleNamespace(active_frames={}))
        with patch('kinetic_cut.qt_native.Engine',Engine):self.player=NativeVideoPlayer(self.transport,None,'fixture')
        self.key=('video',812.4,1.,'video');self.player._transport_key=self.key
    def tearDown(self):self.player.stop()
    def test_paused_seek_uses_small_clock_without_losing_requested_rate(self):
        self.player.setPlaybackRate(3.451612903)
        self.player.setPosition(833247);self.player.play()
        self.assertEqual(self.player.engine.commands,[(2,.01),(0,833247),(1,QMediaPlayer.PlayingState.value)])
        self.assertEqual(self.player._requested_rate,3.451612903)
    def test_loading_warm_player_is_primed_slowly_during_timeline_playback(self):
        self.transport.playing=True
        self.player.play()  # A future clip may not have had setPlaybackRate yet.
        self.assertEqual(self.player.engine.commands,[(2,.01),(1,QMediaPlayer.PlayingState.value)])
        self.player.pause();self.player.play()
        self.assertEqual(sum(k==2 for k,_ in self.player.engine.commands),1)
    def test_linked_activation_restores_exact_rate_once_before_play(self):
        self.transport.playing=True;self.player.setPlaybackRate(3.451612903);self.player.play();self.player.pause()
        self.transport.window.preview.active_frames={'background':self.key,'foreground':self.key}
        self.player.setPlaybackRate(3.451612903);self.player.setPlaybackRate(3.451612903);self.player.play()
        self.assertEqual(self.player.engine.commands[-2:],[(2,3.451612903),(1,QMediaPlayer.PlayingState.value)])
        self.assertEqual(sum(k==2 and v==3.451612903 for k,v in self.player.engine.commands),1)
    def test_active_normal_slow_fast_and_reverse_rates_are_unchanged(self):
        self.transport.playing=True;self.transport.window.preview.active_frames={'clip':self.key}
        self.player.play()
        self.assertEqual(self.player.engine.commands,[(1,QMediaPlayer.PlayingState.value)])
        for rate in (.25,1.,1.5,3.451612903,8.,-2.):
            self.player.setPlaybackRate(rate);self.player.play()
            self.assertEqual(self.player._rate,rate)
            self.assertEqual(self.player._requested_rate,rate)
    def test_retired_engine_does_not_query_a_destroyed_qt_parent(self):
        self.player.stop()
        with patch.object(self.player,'parent',side_effect=AssertionError('retired QObject')):
            self.player.setPlaybackRate(2.);self.player.play()
        self.assertEqual(self.player.engine.commands,[])


if __name__=='__main__':unittest.main()
