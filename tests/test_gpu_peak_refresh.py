"""A stale peak job must wake the renderer to prepare current waveform data."""
import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock
from kinetic_cut.gpu_timeline import GpuTimeline


class GpuPeakRefreshTests(unittest.TestCase):
    def fixture(self,current,completed_identity):
        future=Future();future.set_result([('immutable-image',20,.001)])
        return SimpleNamespace(closed=False,wave_pending={'audio':(completed_identity,future)},
            timeline=SimpleNamespace(waveforms={'audio':current}),waveforms={},wave_timer=Mock(),
            images=Mock(),native_clips=Mock(),schedule=Mock(),signature='retained previous scene')

    def test_stale_completion_requests_refresh_instead_of_leaving_new_waveform_stranded(self):
        previous=object();current=object();surface=self.fixture(current,id(previous))
        GpuTimeline.publish_waves(surface)
        surface.images.put.assert_not_called();surface.native_clips.image.assert_not_called()
        surface.schedule.assert_called_once_with()
        self.assertFalse(surface.wave_pending)
        self.assertIsNone(surface.signature,'A retained unchanged scene must not suppress the replacement job')

    def test_current_completion_publishes_texture_and_refreshes(self):
        current=object();surface=self.fixture(current,id(current))
        GpuTimeline.publish_waves(surface)
        self.assertEqual(surface.waveforms['audio'][0],id(current))
        surface.images.put.assert_called_once();surface.native_clips.image.assert_called_once()
        surface.schedule.assert_called_once_with()

    def test_closed_renderer_does_not_publish_or_restart(self):
        current=object();surface=self.fixture(current,id(current));surface.closed=True
        GpuTimeline.publish_waves(surface)
        surface.schedule.assert_not_called();surface.native_clips.image.assert_not_called()
