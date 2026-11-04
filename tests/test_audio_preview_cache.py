"""Processed audio previews: lossless FLAC, sample-identical to PCM, and superseded files cleaned up."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kinetic_cut.model import MediaItem, TimelineItem
from kinetic_cut.transport import TimelineTransport

FFMPEG = shutil.which('ffmpeg')


def decode(path):
    import numpy as np
    out = subprocess.run([FFMPEG, '-loglevel', 'error', '-i', str(path), '-f', 's16le', '-'], capture_output=True, check=True)
    return np.frombuffer(out.stdout, dtype='<i2')


class AudioPreviewCacheTests(unittest.TestCase):
    def transport(self):
        t = SimpleNamespace(audio_pending=set(), audio_failed=set(), _audio_source_signatures={}, closed=True)
        t.remember_audio_preview = lambda item_id, target: TimelineTransport.remember_audio_preview(t, item_id, target)
        t.audio_ready = lambda key: TimelineTransport.audio_ready(t, key)
        t.sync = Mock()
        return t

    @unittest.skipUnless(FFMPEG, 'ffmpeg is required')
    def test_preview_is_lossless_flac_and_much_smaller(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'voice.wav'
            subprocess.run([FFMPEG, '-loglevel', 'error', '-f', 'lavfi', '-i',
                            'aevalsrc=exprs=0.3*sin(2*PI*220*t)*sin(2*PI*3*t)|0.3*sin(2*PI*330*t):s=48000:d=4',
                            '-c:a', 'pcm_s16le', str(source)], check=True)
            media = MediaItem('m', str(source), 'audio', 'Voice', 4, has_audio=True)
            item = TimelineItem('a', 'm', 'audio_1', 0, 3, in_point=.5, gain_db=4)
            t = self.transport()
            t.window = SimpleNamespace(settings={'ffmpeg': FFMPEG}, start_worker=lambda worker: worker.run())
            with patch('kinetic_cut.config.CACHE_DIR', root):
                self.assertEqual(TimelineTransport.processed_audio(t, item, media), '')   # rendered in the worker
                path = Path(TimelineTransport.processed_audio(t, item, media))
            self.assertEqual(path.suffix, '.flac')
            self.assertTrue(path.name.startswith('audio-preview-'))
            self.assertFalse(list(root.glob('*.pending.*')))
            from kinetic_cut.rendergraph import audio_filters
            snapshot = TimelineItem('a', 'm', 'audio_1', 0, 3, in_point=.5, gain_db=4)
            pcm = root / 'reference.wav'
            subprocess.run([FFMPEG, '-loglevel', 'error', '-y', '-ss', '0.5', '-t', str(snapshot.source_duration), '-i', str(source),
                            '-vn', '-af', audio_filters(snapshot), '-c:a', 'pcm_s16le', str(pcm)], check=True)
            a, b = decode(pcm), decode(path)
            self.assertEqual(len(a), len(b))
            self.assertTrue((a == b).all())                          # bit-identical to the old WAV preview
            self.assertLess(path.stat().st_size, pcm.stat().st_size * .8)

    def test_superseded_preview_is_removed_unless_shared(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second, shared = (root / f'audio-preview-{n}.flac' for n in 'abc')
            for path in (first, second, shared):
                path.write_bytes(b'x')
                os.utime(path, (time.time() - 5000, time.time() - 5000))
            t = self.transport()
            t.remember_audio_preview('clip1', first)
            self.assertGreater(first.stat().st_mtime, time.time() - 60)    # marked as used
            t.remember_audio_preview('clip1', second)                      # a trim made a new preview
            self.assertFalse(first.exists())
            t.remember_audio_preview('clip2', shared)
            t.remember_audio_preview('clip3', shared)
            t.remember_audio_preview('clip2', second)                      # clip3 still plays `shared`
            self.assertTrue(shared.exists())
            t.remember_audio_preview('clip1', second)
            self.assertTrue(second.exists())

    def test_file_in_use_is_left_for_cache_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / 'audio-preview-a.flac', root / 'audio-preview-b.flac'
            first.write_bytes(b'x'); second.write_bytes(b'x')
            t = self.transport()
            t.remember_audio_preview('clip', first)
            with patch.object(Path, 'unlink', side_effect=PermissionError('in use')):
                t.remember_audio_preview('clip', second)
            self.assertTrue(first.exists())


if __name__ == '__main__':
    unittest.main()
