"""Failed/cancelled thumbnail writes cannot publish a partial cache image."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from kinetic_cut import media


class ThumbnailFileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'thumbs').mkdir();self.source=self.root/'source.mp4';self.source.write_bytes(b'fixture')
        self.cache=patch.object(media,'CACHE_DIR',self.root);self.cache.start()
    def tearDown(self):self.cache.stop();self.temp.cleanup()

    def test_failed_encoder_does_not_publish_or_retain_partial_image(self):
        def failed(args,**kwargs):Path(args[-1]).write_bytes(b'partial');return subprocess.CompletedProcess(args,1)
        with patch.object(media,'run_process',side_effect=failed):self.assertEqual(media.make_thumbnail(self.source,'video'),'')
        self.assertEqual(list((self.root/'thumbs').iterdir()),[])

    def test_cancelled_encoder_cleans_up_and_keeps_source_unchanged(self):
        def cancelled(args,**kwargs):Path(args[-1]).write_bytes(b'partial');raise InterruptedError('Cancelled')
        with patch('kinetic_cut.process.run_cancellable',side_effect=cancelled):
            with self.assertRaises(InterruptedError):media.make_thumbnail(self.source,'video',cancel_check=lambda:False)
        self.assertEqual(list((self.root/'thumbs').iterdir()),[]);self.assertEqual(self.source.read_bytes(),b'fixture')

    def test_success_is_published_only_after_writer_finishes(self):
        def successful(args,**kwargs):
            self.assertEqual(media.cached_thumbnail(self.source,'video'),'')
            Image.new('RGB',(32,18),'green').save(args[-1])
            self.assertEqual(media.cached_thumbnail(self.source,'video'),'')
            return subprocess.CompletedProcess(args,0)
        with patch.object(media,'run_process',side_effect=successful):result=media.make_thumbnail(self.source,'video')
        self.assertEqual(media.cached_thumbnail(self.source,'video'),result)
        self.assertEqual(len(list((self.root/'thumbs').iterdir())),1)
        with Image.open(result) as image:self.assertEqual(image.size,(32,18))

    def test_cached_image_hint_never_decodes_original(self):
        source=self.root/'image.png';Image.new('RGBA',(400,200),'red').save(source)
        thumb=media.make_thumbnail(source,'image')
        with patch('PIL.Image.open',side_effect=AssertionError('Unexpected image decode')):
            self.assertEqual(media.cached_thumbnail(source,'image'),thumb)
