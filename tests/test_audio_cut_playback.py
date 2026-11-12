"""Short deleted intervals must not reuse a stale audible source clock."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import QApplication, QWidget

from kinetic_cut.model import MediaItem, Project, TimelineItem
from kinetic_cut.transport import TimelineTransport


class AudioPlayer(QObject):
    mediaStatusChanged = Signal(object)

    def __init__(self, parent, loading=False):
        super().__init__(parent)
        self.status = QMediaPlayer.LoadingMedia if loading else QMediaPlayer.LoadedMedia
        self.state = QMediaPlayer.StoppedState
        self.ms = 0
        self.seeks = []
        self.plays = 0

    def mediaStatus(self):
        return self.status

    def playbackState(self):
        return self.state

    def position(self):
        return self.ms

    def setPosition(self, value):
        self.seeks.append(value)
        if self.status != QMediaPlayer.LoadingMedia:
            self.ms = value

    def setPlaybackRate(self, value):
        self.rate = value

    def setActiveVideoTrack(self, value):
        self.video_track = value

    def play(self):
        self.plays += 1
        self.state = QMediaPlayer.PlayingState

    def pause(self):
        self.state = QMediaPlayer.PausedState

    @Slot()
    def stop(self):
        self.state = QMediaPlayer.StoppedState

    def loaded(self):
        self.status = QMediaPlayer.LoadedMedia
        self.mediaStatusChanged.emit(self.status)


class AudioCutPlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name)/"audio.wav"
        self.source.write_bytes(b"fixture")
        self.window = QWidget()
        self.preview = QWidget(self.window)
        self.preview.frames = {}
        self.window.preview = self.preview
        self.window.proxies = {}
        self.window.settings = {}
        self.media = MediaItem("m", str(self.source), "audio", "Audio", 4, has_audio=True)
        self.left = TimelineItem("left", "m", "audio_1", 0, .9)
        self.right = TimelineItem("right", "m", "audio_1", 1.04, 2.96, in_point=1.04)
        self.project = Project(media=[self.media], timeline=[self.left, self.right])
        self.window.project = self.project
        self.transport = TimelineTransport(self.window)
        self.players = []
        self.loading = False
        self.create = patch.object(self.transport, "create_decoder", side_effect=self.create_audio)
        self.create.start()

    def create_audio(self, key, media, video, audio_path):
        player = AudioPlayer(self.transport, self.loading)
        output = QAudioOutput(player)
        sink = QVideoSink(player) if video else None
        if sink is not None:sink._frame_stamp = None
        self.transport.decoders[key] = (player, output, sink)
        player.mediaStatusChanged.connect(lambda status: self.transport.decoder_loaded(key, player, status))
        self.players.append((key, player, output))

    def tearDown(self):
        self.create.stop()
        self.transport.shutdown()
        self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def at(self, position, playing=True, force=False):
        self.transport.playing = playing
        self.transport.position = position
        self.transport.sync(force)

    def test_skipped_short_gap_cannot_continue_previous_audio_player(self):
        self.at(.85)
        first = self.players[0]
        first[1].ms = 900  # Decoder lags less than the existing 350 ms tolerance.
        self.at(1.05)     # A busy UI tick skipped the 140 ms deleted interval.
        active = [d for k, d in self.transport.decoders.items() if k not in self.transport.warm_keys]
        self.assertEqual(len(active), 1)
        self.assertIsNot(active[0][0], first[1])
        self.assertGreaterEqual(active[0][0].position(), 1040)
        self.assertTrue(first[2].isMuted() or first[2].volume() == 0)

    def test_loading_seek_is_reapplied_before_audio_is_audible(self):
        self.loading = True
        self.at(1.05)
        key, player, output = self.players[0]
        self.assertEqual(player.position(), 0)
        self.assertEqual(player.plays, 0)
        self.assertTrue(output.isMuted() or output.volume() == 0)
        player.loaded()
        self.app.processEvents()
        self.assertGreaterEqual(player.position(), 1050)
        self.assertEqual(player.playbackState(), QMediaPlayer.PlayingState)
        self.assertFalse(output.isMuted())
        self.assertGreater(output.volume(), 0)

    def test_delayed_load_uses_current_timeline_position(self):
        self.loading = True
        self.at(1.05)
        key, player, output = self.players[0]
        self.at(1.23)
        player.loaded()
        self.app.processEvents()
        self.assertEqual(player.position(), 1230)

    def test_load_after_seek_into_gap_cannot_restart_retired_audio(self):
        self.loading = True
        self.at(1.05)
        key, player, output = self.players[0]
        self.at(.97, playing=False, force=True)
        player.loaded()
        self.app.processEvents()
        self.assertEqual(player.plays, 0)
        self.assertTrue(output.isMuted() or output.volume() == 0)

    def test_continuous_audio_does_not_reseek_each_tick(self):
        self.at(1.05)
        key, player, output = self.players[0]
        seeks = list(player.seeks)
        for position in (1.07, 1.09, 1.11):
            player.ms = round(position*1000)
            self.at(position)
        self.assertEqual(player.seeks, seeks)
        self.assertEqual(player.playbackState(), QMediaPlayer.PlayingState)

    def test_trim_of_same_item_replaces_its_audio_interval(self):
        self.at(1.05, playing=False)
        first = self.players[0]
        self.right.in_point += .08
        self.right.duration -= .08
        self.project.touch()
        self.at(1.05, playing=False)
        active = [d for k, d in self.transport.decoders.items() if k not in self.transport.warm_keys]
        self.assertIsNot(active[0][0], first[1])
        self.assertEqual(active[0][0].position(), 1130)
        self.assertTrue(first[2].isMuted())

    def test_paused_loading_audio_stays_paused_after_load(self):
        self.loading = True
        self.at(1.05, playing=False)
        _, player, _ = self.players[0]
        player.loaded()
        self.app.processEvents()
        self.assertEqual(player.position(), 1050)
        self.assertEqual(player.plays, 0)

    def test_loading_warm_neighbour_remains_silent_until_activated(self):
        self.loading = True
        self.at(.85)
        key, player, output = next(entry for entry in self.players if entry[0] in self.transport.warm_keys)
        player.loaded()
        self.app.processEvents()
        self.assertEqual(player.plays, 0)
        self.assertEqual(output.volume(), 0)
        self.at(1.09)
        self.assertEqual(player.position(), 1090)
        self.assertEqual(player.playbackState(), QMediaPlayer.PlayingState)
        self.assertGreater(output.volume(), 0)

    def video_clips(self):
        self.media.kind = 'video'
        self.left.track = self.right.track = 'video_1'
        self.project.touch()

    def test_video_shared_clock_reseeks_when_a_tick_skips_a_gap(self):
        self.video_clips()
        self.at(.85)
        key, player, _ = self.players[0]
        player.ms = 900
        player.seeks.clear()
        self.at(1.05)
        self.assertEqual(len(self.players), 1)  # Sharing remains intentional.
        self.assertEqual(player.seeks, [1050])
        self.assertEqual(self.transport._video_seek_floor[key], 1_050_000)

    def test_video_continuous_split_and_aligned_layers_keep_decoder(self):
        self.video_clips()
        self.right.start = self.right.in_point = .9
        self.project.video_tracks.append('video_2')
        self.project.timeline.append(TimelineItem('copy', 'm', 'video_2', 0, 3))
        self.project.touch()
        self.at(.85)
        _, player, _ = self.players[0]
        player.ms = 950
        player.seeks.clear()
        self.at(.95)
        self.assertEqual(len(self.players), 1)
        self.assertEqual(player.seeks, [])


if __name__ == "__main__":
    unittest.main()
