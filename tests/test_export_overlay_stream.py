"""Lossless caption overlay streaming clocks, framing and owned producer failures."""
import copy
import ctypes
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from kinetic_cut import gpu_export_decode as decoding
from kinetic_cut.exporter import ExportPreset, write_ass
from kinetic_cut.gpu_export import prepare_recipe
from kinetic_cut.model import Caption, CaptionStyle, Project, ProjectSettings, TimelineItem


class ExportOverlayStreamTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sources = []

    def tearDown(self):
        for source in reversed(self.sources):
            source.close()
        self.temporary.cleanup()

    def source(self, pixels, *, fps=60., code=0, advertised=None, tail='', sample_frames=None):
        """Tiny real producers exercise actual pipes without rendering media."""
        payload = b''.join(np.asarray(frame, dtype=np.uint8).tobytes() for frame in pixels)
        frames = len(pixels) if advertised is None else advertised
        height, width = np.asarray(pixels[0]).shape[:2]
        program = (
            'import os,sys,time; '
            f'payload=bytes.fromhex({payload.hex()!r}); '
            'os.write(1,payload); '
            f'{tail or "pass"}; sys.exit({code})'
        )
        spec = dict(command=[sys.executable, '-c', program], width=width,
                    height=height, fps=fps, frames=frames,
                    log=str(self.root / f'producer-{len(self.sources)}.log'))
        if sample_frames is not None:
            spec['sample_frames'] = sample_frames
        source = decoding.RawSource(spec)
        self.sources.append(source)
        return source

    def test_exact_rgba_transparency_and_duplicate_first_frame(self):
        frames = [np.array([[[12, 34, 56, 0], [78, 90, 12, 128]]], dtype=np.uint8),
                  np.array([[[1, 2, 3, 255], [255, 128, 0, 42]]], dtype=np.uint8)]
        source = self.source(frames)
        first = source.frame(0.)
        self.assertEqual(first.dtype, np.uint8)
        self.assertEqual(first.shape, (1, 2, 4))
        np.testing.assert_array_equal(first, frames[0])
        np.testing.assert_array_equal(source.frame(0.), frames[0])
        np.testing.assert_array_equal(source.frame(1 / 60), frames[1])
        np.testing.assert_array_equal(source.frame(1 / 60), frames[1])

    def test_fractional_rate_and_numerical_roundoff_do_not_shift_frames(self):
        fps = 60000 / 1001
        frames = [np.full((1, 1, 4), n, dtype=np.uint8) for n in range(4)]
        source = self.source(frames, fps=fps)
        for n, frame in enumerate(frames):
            seconds = max(0., n / fps - 1e-12)
            np.testing.assert_array_equal(source.frame(seconds), frame)

    def test_skipped_requests_consume_exact_intervening_frames(self):
        frames = [np.full((1, 2, 4), n, dtype=np.uint8) for n in range(5)]
        source = self.source(frames)
        np.testing.assert_array_equal(source.frame(0.), frames[0])
        np.testing.assert_array_equal(source.frame(3 / 60), frames[3])
        np.testing.assert_array_equal(source.frame(3 / 60), frames[3])
        np.testing.assert_array_equal(source.frame(4 / 60), frames[4])

    def test_sparse_samples_hold_exact_buffer_without_advancing_generation(self):
        frames = [np.array([[[12, 34, 56, 0], [78, 90, 12, 128]]], dtype=np.uint8),
                  np.array([[[9, 8, 7, 255], [6, 5, 4, 42]]], dtype=np.uint8),
                  np.array([[[0, 0, 0, 0], [0, 0, 0, 0]]], dtype=np.uint8)]
        source = self.source(frames, advertised=10, sample_frames=[0, 4, 9])
        initial = source.generation
        first = source.frame(0.)
        self.assertEqual(source.generation, initial + 1)
        np.testing.assert_array_equal(first, frames[0])
        for index in (1, 2, 3):
            self.assertIs(source.frame(index / 60), first)
            np.testing.assert_array_equal(first, frames[0])
            self.assertEqual(source.generation, initial + 1)
        np.testing.assert_array_equal(source.frame(4 / 60), frames[1])
        self.assertEqual(source.generation, initial + 2)
        np.testing.assert_array_equal(source.frame(8 / 60), frames[1])
        self.assertEqual(source.generation, initial + 2)
        np.testing.assert_array_equal(source.frame(9 / 60), frames[2])
        self.assertEqual(source.generation, initial + 3)

    def test_sparse_target_skip_reads_intermediate_samples_but_not_future_samples(self):
        frames = [np.full((1, 1, 4), n, dtype=np.uint8) for n in (11, 22, 33, 44)]
        source = self.source(frames, advertised=10, sample_frames=[0, 3, 7, 9])
        initial = source.generation
        np.testing.assert_array_equal(source.frame(8 / 60), frames[2])
        self.assertEqual(source.generation, initial + 3)
        np.testing.assert_array_equal(source.frame(9 / 60), frames[3])
        self.assertEqual(source.generation, initial + 4)

    def test_sparse_held_region_still_rejects_backwards_native_requests(self):
        frames = [np.full((1, 1, 4), n, dtype=np.uint8) for n in (11, 22)]
        source = self.source(frames, advertised=10, sample_frames=[0, 9])
        source.frame(7 / 60)
        with self.assertRaises((RuntimeError, ValueError)):
            source.frame(6 / 60)

    def test_sparse_schedule_requires_strict_integer_endpoints_order_and_bounds(self):
        valid = dict(command=['not-launched'], width=1, height=1, fps=60., frames=10,
                     log=str(self.root / 'invalid-samples.log'))
        invalid = ([], [1, 9], [0, 8], [-1, 9], [0, 10], [0, 3, 3, 9],
                   [0, 5, 4, 9], [0, 3.0, 9], [0, True, 9], [False, 9],
                   [0, '3', 9], '0,9')
        for schedule in invalid:
            with self.subTest(schedule=schedule), patch('kinetic_cut.process.popen') as launch:
                with self.assertRaises((ValueError, TypeError)):
                    decoding.RawSource({**valid, 'sample_frames': schedule})
                launch.assert_not_called()

    def test_sparse_final_eof_and_nonzero_exit_never_publish_invalid_tail(self):
        first = np.array([[[1, 2, 3, 255]]], dtype=np.uint8)
        missing = self.source([first], advertised=10, sample_frames=[0, 9])
        np.testing.assert_array_equal(missing.frame(0.), first)
        np.testing.assert_array_equal(missing.frame(8 / 60), first)
        with self.assertRaises((RuntimeError, EOFError, IOError)):
            missing.frame(9 / 60)
        failed = self.source([first, np.zeros_like(first)], advertised=10,
                             sample_frames=[0, 9], code=7)
        np.testing.assert_array_equal(failed.frame(0.), first)
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                failed.frame(9 / 60)

    def test_backwards_and_outside_clock_requests_are_rejected(self):
        frames = [np.full((1, 1, 4), n, dtype=np.uint8) for n in range(3)]
        source = self.source(frames)
        source.frame(1 / 60)
        for seconds in (-1., 0., 3 / 60, float('nan'), float('inf')):
            with self.subTest(seconds=seconds):
                with self.assertRaises((RuntimeError, ValueError)):
                    source.frame(seconds)

    def test_partial_frame_is_never_returned_as_valid_pixels(self):
        # Advertise two pixels, but the producer emits only one complete pixel.
        program = 'import os; os.write(1,bytes([1,2,3,4]))'
        spec = dict(command=[sys.executable, '-c', program], width=2, height=1,
                    fps=60., frames=1, log=str(self.root / 'truncated.log'))
        source = decoding.RawSource(spec)
        self.sources.append(source)
        with self.assertRaises((RuntimeError, EOFError, IOError)):
            source.frame(0.)

    def test_early_complete_frame_eof_is_not_a_frozen_caption_tail(self):
        source = self.source([np.zeros((1, 1, 4), dtype=np.uint8)], advertised=2)
        source.frame(0.)
        with self.assertRaises((RuntimeError, EOFError, IOError)):
            source.frame(1 / 60)

    def test_nonzero_exit_after_last_frame_fails_before_final_pixels_publish(self):
        source = self.source([np.ones((1, 1, 4), dtype=np.uint8)], code=7,
                             tail="os.write(2,b'producer terminal failure')")
        with self.assertRaises(RuntimeError):
            source.frame(0.)
        # A repeated request must not publish a frame whose producer failed.
        with self.assertRaises(RuntimeError):
            source.frame(0.)

    def test_short_pipe_reads_are_assembled_into_complete_rgba_frames(self):
        frames = [np.arange(16, dtype=np.uint8).reshape((2, 2, 4)),
                  np.arange(16, 32, dtype=np.uint8).reshape((2, 2, 4))]
        source = self.source(frames)
        stream = source.process.stdout
        class ShortReader:
            calls = 0
            def readinto(self, view):
                self.calls += 1
                return stream.readinto(view[:3])
            def close(self):
                stream.close()
        short = ShortReader()
        source.process.stdout = short
        for index, frame in enumerate(frames):
            np.testing.assert_array_equal(source.frame(index / 60), frame)
        self.assertGreater(short.calls, 2)

    def test_invalid_source_dimensions_clocks_and_commands_fail_before_launch(self):
        valid = dict(command=['unused'], width=1, height=1, fps=60., frames=1,
                     log=str(self.root / 'invalid.log'))
        for name, value in [('width', 0), ('height', 8193), ('fps', 0),
                            ('fps', float('nan')), ('frames', 0),
                            ('command', 'not-an-argument-list'), ('command', [None])]:
            with self.subTest(name=name, value=value), \
                    patch('kinetic_cut.process.popen') as launch:
                with self.assertRaises((ValueError, TypeError)):
                    decoding.RawSource({**valid, name: value})
                launch.assert_not_called()

    def test_failed_child_ownership_setup_reaps_already_started_producer(self):
        import kinetic_cut.process as process
        original = process.popen
        children = []
        def observed(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        spec = dict(command=[sys.executable, '-c', 'import time; time.sleep(60)'],
                    width=1, height=1, fps=60., frames=1,
                    log=str(self.root / 'ownership-failed.log'))
        with patch.object(process, 'popen', side_effect=observed), \
                patch('kinetic_cut.export_process.ChildJob', side_effect=RuntimeError('ownership setup failed')):
            with self.assertRaises(RuntimeError):
                decoding.RawSource(spec)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())

    @unittest.skipUnless(os.name == 'nt', 'Windows kill-on-close ownership')
    def test_silent_job_assignment_failure_reaps_producer_instead_of_running_unowned(self):
        import kinetic_cut.process as process
        from unittest.mock import Mock
        original = process.popen
        children = []
        def observed(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        spec = dict(command=[sys.executable, '-c', 'import time; time.sleep(60)'],
                    width=1, height=1, fps=60., frames=1,
                    log=str(self.root / 'ownership-missing.log'))
        job = Mock(handle=None)
        with patch.object(process, 'popen', side_effect=observed), \
                patch('kinetic_cut.export_process.ChildJob', return_value=job):
            with self.assertRaises(RuntimeError):
                decoding.RawSource(spec)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        job.close.assert_called()

    def test_close_reaps_a_live_producer_and_is_idempotent(self):
        import kinetic_cut.process as process
        original = process.popen
        children = []
        def observed(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        with patch.object(process, 'popen', side_effect=observed):
            source = self.source([np.zeros((1, 1, 4), dtype=np.uint8)], advertised=2,
                                 tail='time.sleep(60)')
            source.frame(0.)
        self.assertEqual(len(children), 1)
        self.assertIsNone(children[0].poll())
        source.close()
        self.assertIsNotNone(children[0].poll())
        source.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows binary kernel pipe')
    def test_large_pipe_parent_writer_closes_after_spawn_and_reader_remains_owned(self):
        original = decoding._windows_pipe
        pipes = []
        def observed(*args, **kwargs):
            pair = original(*args, **kwargs)
            pipes.append(pair)
            return pair
        with patch.object(decoding, '_windows_pipe', side_effect=observed):
            source = self.source([np.arange(8, dtype=np.uint8).reshape((1, 2, 4))])
        self.assertEqual(len(pipes), 1)
        reader, writer = pipes[0]
        self.assertTrue(writer.closed)
        self.assertFalse(reader.closed)
        np.testing.assert_array_equal(source.frame(0.), np.arange(8, dtype=np.uint8).reshape((1, 2, 4)))
        source.close()
        self.assertTrue(reader.closed)

    def test_decoder_routes_only_explicit_raw_sources_and_releases_them(self):
        marker = str(self.root / 'overlay.raw')
        spec = dict(command=['not-executed'], width=2, height=1, fps=60., frames=1,
                    log=str(self.root / 'unused.log'))
        pixels = np.array([[[1, 2, 3, 4], [5, 6, 7, 8]]], dtype=np.uint8)
        with patch.object(decoding, 'RawSource') as raw, patch.object(decoding, 'Source') as file:
            raw.return_value.frame.return_value = pixels
            file.return_value.frame.return_value = pixels
            decoder = decoding.Decoder({marker: spec})
            width, height = ctypes.c_uint(), ctypes.c_uint()
            pointer = ctypes.c_void_p()
            args = (ctypes.pointer(width), ctypes.pointer(height), ctypes.pointer(pointer))
            self.assertEqual(decoder.read(marker, 'live', 0., *args), 0)
            raw.assert_called_once_with(spec)
            self.assertEqual((width.value, height.value, pointer.value), (2, 1, pixels.ctypes.data))
            self.assertEqual(decoder.read('ordinary.mkv', 'file', 0., *args), 0)
            file.assert_called_once_with('ordinary.mkv', 0.)
            self.assertEqual(decoder.read(marker, 'live', -1., *args), 0)
            raw.return_value.close.assert_called_once_with()
            decoder.close()
            file.return_value.close.assert_called_once_with()

    def test_decoder_reuse_opt_in_reports_changed_held_changed_and_restarts_after_release(self):
        marker = str(self.root / 'sparse-overlay.raw')
        frames = [np.array([[[12, 34, 56, 128]]], dtype=np.uint8),
                  np.array([[[9, 8, 7, 255]]], dtype=np.uint8),
                  np.zeros((1, 1, 4), dtype=np.uint8)]
        payload = b''.join(frame.tobytes() for frame in frames)
        spec = dict(command=[sys.executable, '-c', f'import os; os.write(1,bytes.fromhex({payload.hex()!r}))'],
                    width=1, height=1, fps=60., frames=10, sample_frames=[0, 4, 9],
                    log=str(self.root / 'decoder-sparse.log'))
        decoder = decoding.Decoder({marker: spec}, reuse_frames=True)
        self.sources.append(decoder)
        width, height, pointer = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_void_p()
        args = (ctypes.pointer(width), ctypes.pointer(height), ctypes.pointer(pointer))
        for index, code, expected in ((0, 0, frames[0]), (0, 2, frames[0]),
                                      (3, 2, frames[0]), (4, 0, frames[1]),
                                      (8, 2, frames[1]), (9, 0, frames[2])):
            self.assertEqual(decoder.read(marker, 'same-key', index / 60, *args), code)
            self.assertEqual((width.value, height.value), (1, 1))
            self.assertEqual(ctypes.string_at(pointer.value, 4), expected.tobytes())
        self.assertEqual(decoder.read(marker, 'same-key', -1., *args), 0)
        self.assertEqual(decoder.read(marker, 'same-key', 0., *args), 0)
        self.assertEqual(ctypes.string_at(pointer.value, 4), frames[0].tobytes())

    def test_decoder_default_abi_keeps_success_zero_for_reused_raw_frames(self):
        marker = str(self.root / 'old-abi-overlay.raw')
        payload = bytes([1, 2, 3, 4])
        spec = dict(command=[sys.executable, '-c', f'import os; os.write(1,{payload!r})'],
                    width=1, height=1, fps=60., frames=1,
                    log=str(self.root / 'decoder-old-abi.log'))
        decoder = decoding.Decoder({marker: spec})
        self.sources.append(decoder)
        width, height, pointer = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_void_p()
        args = (ctypes.pointer(width), ctypes.pointer(height), ctypes.pointer(pointer))
        for _ in range(3):
            self.assertEqual(decoder.read(marker, 'old-key', 0., *args), 0)

    def test_decoder_never_reports_texture_reuse_for_generic_pyav_sources(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        pixels = np.array([[[5, 6, 7, 8]]], dtype=np.uint8)
        generic = SimpleNamespace(frame=Mock(return_value=pixels), close=Mock(), generation=1)
        with patch.object(decoding, 'Source', return_value=generic):
            decoder = decoding.Decoder(reuse_frames=True)
            self.sources.append(decoder)
            width, height, pointer = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_void_p()
            args = (ctypes.pointer(width), ctypes.pointer(height), ctypes.pointer(pointer))
            self.assertEqual(decoder.read('video.mkv', 'file-key', 0., *args), 0)
            self.assertEqual(decoder.read('video.mkv', 'file-key', 0., *args), 0)

    def test_caption_and_title_recipe_defers_exact_graph_without_ffv1_prepass(self):
        project = Project(settings=ProjectSettings(width=320, height=180, fps=60),
                          timeline=[TimelineItem('title', '', 'video_1', .2, .3,
                                                 role='title', title_text='Overlay')],
                          captions=[Caption('caption', .7, .9, 'Keep timing',
                                            CaptionStyle(size=30, glow_enabled=True),
                                            customize=True)])
        before = copy.deepcopy(project.to_dict())
        preset = ExportPreset('Test', 'h264', 10, 192, 'Auto', 'auto')
        with patch('kinetic_cut.export_process.render') as render:
            job = prepare_recipe(project, preset, self.root, True, {}, 'ffmpeg', None, None)
        render.assert_not_called()
        self.assertEqual(project.to_dict(), before)
        self.assertEqual(len(job['raw_sources']), 1)
        overlay = job['layers'][-1]
        spec = job['raw_sources'][overlay['path']]
        self.assertEqual((overlay['start'], overlay['end'], overlay['in_point']),
                         (0., project.duration, 0.))
        self.assertTrue(overlay['cpu'])
        self.assertFalse(overlay['still'])
        self.assertEqual((spec['width'], spec['height'], spec['fps'], spec['frames']),
                         (320, 180, 60, math.ceil(project.duration * 60 - 1e-7)))
        args = spec['command']
        self.assertNotIn('ffv1', args)
        self.assertNotIn('-progress', args)
        self.assertEqual(args[-1], 'pipe:1')
        self.assertEqual(args[args.index('-c:v') + 1], 'rawvideo')
        self.assertEqual(args[args.index('-pix_fmt') + 1], 'rgba')
        if '-filter_complex_script' in args:
            graph = Path(args[args.index('-filter_complex_script') + 1]).read_text(encoding='utf-8')
            self.assertIn("select='", graph)
            self.assertNotIn('[captions]fps=', graph)
            self.assertEqual(args[args.index('-fps_mode') + 1], 'passthrough')
            samples = spec['sample_frames']
            self.assertEqual((samples[0], samples[-1]), (0, spec['frames'] - 1))
            self.assertEqual(int(args[args.index('-frames:v') + 1]), len(samples))
        else:
            graph = args[args.index('-filter_complex') + 1]
            self.assertIn('fps=60', graph)
        self.assertIn('alpha=1', graph)
        self.assertIn(':r=60:', graph)
        ass = next(self.root.glob('*.ass')).read_text(encoding='utf-8-sig')
        expected = self.root / 'expected.ass'
        write_ass(project, str(expected), True)
        self.assertEqual(ass, expected.read_text(encoding='utf-8-sig'))
        self.assertIn('Overlay', ass)
        self.assertIn('0:00:00.70', ass)
        self.assertIn('0:00:00.90', ass)
        self.assertIn('\\blur12.0', ass)

    def test_disabling_caption_burn_keeps_titles_but_omits_caption_text(self):
        project = Project(settings=ProjectSettings(width=320, height=180, fps=120),
                          timeline=[TimelineItem('title', '', 'video_1', 0., .2,
                                                 role='title', title_text='Keep title')],
                          captions=[Caption('caption', 0., .2, 'Omit caption')])
        preset = ExportPreset('Test', 'h264', 10, 192, 'Auto', 'auto')
        job = prepare_recipe(project, preset, self.root, False, {}, 'ffmpeg', None, None)
        self.assertEqual(len(job['raw_sources']), 1)
        spec = next(iter(job['raw_sources'].values()))
        self.assertEqual(spec['fps'], 120)
        self.assertEqual(spec['frames'], 24)
        ass = next(self.root.glob('*.ass')).read_text(encoding='utf-8-sig')
        self.assertIn('Keep title', ass)
        self.assertNotIn('Omit caption', ass)


@unittest.skipUnless(os.name == 'nt', 'Windows binary kernel pipe')
class WindowsOverlayPipeTests(unittest.TestCase):
    @staticmethod
    def kernel():
        from ctypes import wintypes as W
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetNamedPipeInfo.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD),
                                            ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD),
                                            ctypes.POINTER(W.DWORD)]
        kernel.GetNamedPipeInfo.restype = W.BOOL
        return kernel

    def test_actual_kernel_capacity_is_one_mebibyte_and_handles_are_non_inheritable(self):
        import msvcrt
        from ctypes import wintypes as W
        kernel = self.kernel()
        reader, writer = decoding._windows_pipe()
        try:
            flags, outbound, inbound, instances = (W.DWORD() for _ in range(4))
            handle = msvcrt.get_osfhandle(reader.fileno())
            self.assertTrue(kernel.GetNamedPipeInfo(handle, ctypes.byref(flags),
                                                   ctypes.byref(outbound), ctypes.byref(inbound),
                                                   ctypes.byref(instances)))
            self.assertGreaterEqual(max(outbound.value, inbound.value), 1024 * 1024)
            self.assertFalse(os.get_inheritable(reader.fileno()))
            self.assertFalse(os.get_inheritable(writer.fileno()))
        finally:
            writer.close()
            reader.close()

    def test_binary_pipe_preserves_every_byte_and_signals_eof_after_writer_close(self):
        payload = bytes(range(256)) * 64
        reader, writer = decoding._windows_pipe()
        try:
            self.assertEqual(writer.write(payload), len(payload))
            writer.close()
            self.assertEqual(reader.read(len(payload) + 1), payload)
            self.assertEqual(reader.read(1), b'')
        finally:
            writer.close()
            reader.close()

    def test_failed_spawn_closes_both_pipe_ends_and_render_log(self):
        import builtins
        pipes = []
        logs = []
        original = decoding._windows_pipe
        open_file = builtins.open
        def observed(*args, **kwargs):
            pair = original(*args, **kwargs)
            pipes.append(pair)
            return pair
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / 'spawn.log'
            def observed_open(name, *args, **kwargs):
                stream = open_file(name, *args, **kwargs)
                if name == str(log):
                    logs.append(stream)
                return stream
            spec = dict(command=['not-launched'], width=2, height=1, fps=60.,
                        frames=1, log=str(log))
            with patch.object(decoding, '_windows_pipe', side_effect=observed), \
                    patch('kinetic_cut.process.popen', side_effect=OSError('spawn failed')), \
                    patch.object(builtins, 'open', side_effect=observed_open):
                with self.assertRaisesRegex(OSError, 'spawn failed'):
                    decoding.RawSource(spec)
            self.assertEqual(len(pipes), 1)
            self.assertTrue(all(stream.closed for stream in pipes[0]))
            self.assertEqual(len(logs), 1)
            self.assertTrue(logs[0].closed)

    def test_partial_pipe_construction_closes_raw_handles_and_transferred_descriptors(self):
        import _winapi
        import msvcrt
        create_pipe = _winapi.CreatePipe
        to_descriptor = msvcrt.open_osfhandle
        to_file = os.fdopen
        set_inheritable = os.set_inheritable
        close_handle = _winapi.CloseHandle
        close_descriptor = os.close
        for failing_stage in ('descriptor-2', 'file-1', 'file-2', 'inherit-2'):
            with self.subTest(stage=failing_stage):
                handles = []
                descriptors = {}
                streams = {}
                closed_handles = []
                closed_descriptors = []
                calls = dict(descriptor=0, file=0, inherit=0)
                def create(*args):
                    pair = create_pipe(*args)
                    handles.extend(pair)
                    return pair
                def descriptor(*args):
                    calls['descriptor'] += 1
                    if failing_stage == f'descriptor-{calls["descriptor"]}':
                        raise OSError('injected half-pipe construction failure')
                    descriptor = to_descriptor(*args)
                    descriptors[descriptor] = args[0]
                    return descriptor
                def file(*args, **kwargs):
                    calls['file'] += 1
                    if failing_stage == f'file-{calls["file"]}':
                        raise OSError('injected half-pipe construction failure')
                    stream = to_file(*args, **kwargs)
                    streams[args[0]] = stream
                    return stream
                def inherit(*args):
                    calls['inherit'] += 1
                    if failing_stage == f'inherit-{calls["inherit"]}':
                        raise OSError('injected half-pipe construction failure')
                    return set_inheritable(*args)
                def close_raw(handle):
                    closed_handles.append(handle)
                    return close_handle(handle)
                def close_fd(descriptor):
                    closed_descriptors.append(descriptor)
                    return close_descriptor(descriptor)
                with patch.object(_winapi, 'CreatePipe', side_effect=create), \
                        patch.object(msvcrt, 'open_osfhandle', side_effect=descriptor), \
                        patch.object(os, 'fdopen', side_effect=file), \
                        patch.object(os, 'set_inheritable', side_effect=inherit), \
                        patch.object(_winapi, 'CloseHandle', side_effect=close_raw), \
                        patch.object(os, 'close', side_effect=close_fd):
                    with self.assertRaisesRegex(OSError, 'half-pipe'):
                        decoding._windows_pipe()
                self.assertEqual(len(handles), 2)
                for handle in handles:
                    if handle in closed_handles:
                        self.assertEqual(closed_handles.count(handle), 1)
                        continue
                    owners = [fd for fd, original in descriptors.items() if original == handle]
                    self.assertEqual(len(owners), 1)
                    descriptor = owners[0]
                    if descriptor in streams:
                        self.assertTrue(streams[descriptor].closed)
                    else:
                        self.assertEqual(closed_descriptors.count(descriptor), 1)
                    # Validate the transferred CRT owner without probing a closed
                    # kernel handle (which can raise STATUS_INVALID_HANDLE under
                    # native handle-verification tooling).
                    with self.assertRaises(OSError):
                        msvcrt.get_osfhandle(descriptor)
