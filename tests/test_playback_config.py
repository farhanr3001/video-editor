import os
import unittest
from unittest.mock import patch
from kinetic_cut.playback_config import configure, MODES

class PlaybackConfigTests(unittest.TestCase):
    def test_hardware_default_and_legacy_preference_preserve_established_backend(self):
        for mode in (MODES[1],):
            with patch('kinetic_cut.playback_config.sys.platform', 'win32'), patch.dict(os.environ, {}, clear=True):
                configure({'playback_decoder': mode})
                self.assertEqual(os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES'], 'd3d11va')
                self.assertEqual(os.environ['QT_DISABLE_HW_TEXTURES_CONVERSION'], '1')
        with patch('kinetic_cut.playback_config.sys.platform', 'win32'), patch.dict(os.environ, {}, clear=True):
            configure({})
            self.assertNotIn('QT_FFMPEG_DECODING_HW_DEVICE_TYPES', os.environ)
    def test_cpu_compatibility_and_explicit_environment_override_are_preserved(self):
        with patch('kinetic_cut.playback_config.sys.platform', 'win32'), patch.dict(os.environ, {}, clear=True):
            configure({'playback_decoder': MODES[2]})
            self.assertEqual(os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES'], ',')
        with patch('kinetic_cut.playback_config.sys.platform', 'win32'), patch.dict(os.environ, {'QT_FFMPEG_DECODING_HW_DEVICE_TYPES': 'cuda'}, clear=True):
            configure({})
            self.assertEqual(os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES'], 'cuda')
    def test_non_windows_environment_is_unchanged(self):
        with patch('kinetic_cut.playback_config.sys.platform', 'linux'), patch.dict(os.environ, {}, clear=True):
            configure({})
            self.assertNotIn('QT_FFMPEG_DECODING_HW_DEVICE_TYPES', os.environ)
