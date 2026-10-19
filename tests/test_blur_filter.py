import unittest
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image,ImageFilter
from PySide6.QtGui import QImage
from kinetic_cut.blur_filter import gaussian
from kinetic_cut.visuals import blur_image


def reference(image,rx,ry,blend,border):
    converted=image.convertToFormat(QImage.Format_RGBA8888)
    pil=Image.frombytes('RGBA',(converted.width(),converted.height()),bytes(converted.constBits()))
    padding=max(2,min(128,round(max(rx,ry)*2)))
    padded=Image.fromarray(np.pad(np.asarray(pil),((padding,padding),(padding,padding),(0,0)),mode='reflect' if border=='Reflect' else 'edge'))
    r=max(.1,min(rx,ry));size=(max(4,round(padded.width*r/max(.1,rx))),max(4,round(padded.height*r/max(.1,ry))))
    blurred=padded.resize(size,Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(r)).resize(padded.size,Image.Resampling.BILINEAR).crop((padding,padding,padding+pil.width,padding+pil.height))
    if blend<1:blurred=Image.blend(pil,blurred,max(0,blend))
    data=blurred.tobytes();return QImage(data,blurred.width,blurred.height,QImage.Format_RGBA8888).copy()


class BlurFilterTests(unittest.TestCase):
    def test_strip_seams_and_transparency_are_pixel_identical(self):
        pixels=np.random.default_rng(73).integers(0,256,(1081,1921,4),dtype=np.uint8)
        image=Image.fromarray(pixels)
        for radius in (.1,1.,2.7,5.27,12.,30.,100.):
            with self.subTest(radius=radius):
                expected=image.filter(ImageFilter.GaussianBlur(radius))
                self.assertEqual(gaussian(image,radius).tobytes(),expected.tobytes())
        self.assertTrue(np.array_equal(np.asarray(image),pixels))
    def test_full_filter_keeps_border_blend_and_anisotropy_exact(self):
        pixels=np.random.default_rng(12).integers(0,256,(1081,1921,4),dtype=np.uint8)
        image=QImage(pixels.data,1921,1081,1921*4,QImage.Format_RGBA8888).copy();before=bytes(image.constBits())
        for border in ('Reflect','Replicate'):
            for rx,ry,blend in ((5.27,5.27,1.),(5.27,5.27,.45),(12.,5.27,1.),(0.,8.,.45)):
                with self.subTest(border=border,rx=rx,ry=ry,blend=blend):
                    expected=reference(image,rx,ry,blend,border);actual=blur_image(image,rx,ry,blend,border)
                    self.assertEqual(actual.size(),image.size());self.assertEqual(bytes(actual.constBits()),bytes(expected.constBits()))
        self.assertEqual(bytes(image.constBits()),before)
    def test_concurrent_frames_do_not_mix_pixels_or_deadlock(self):
        images=[Image.fromarray(np.random.default_rng(n).integers(0,256,(720,1280,4),dtype=np.uint8)) for n in range(4)]
        with ThreadPoolExecutor(max_workers=2) as callers:
            outputs=list(callers.map(lambda im:gaussian(im,5.27),images))
        for im,result in zip(images,outputs):self.assertEqual(result.tobytes(),im.filter(ImageFilter.GaussianBlur(5.27)).tobytes())

    def test_visible_region_matches_complete_filter_including_edges(self):
        pixels=np.random.default_rng(4).integers(0,256,(1081,1921,4),dtype=np.uint8)
        image=QImage(pixels.data,1921,1081,1921*4,QImage.Format_RGBA8888).copy()
        for region in ((0,0,250,400),(700,300,1000,800),(1700,900,1921,1081)):
            for border in ('Reflect','Replicate'):
                for blend in (.45,1.):
                    expected=reference(image,5.27,5.27,blend,border)
                    actual=blur_image(image,5.27,5.27,blend,border,preview_fast=True,region=region)
                    x,y,right,bottom=region
                    # constBits borrows QImage storage. Keep both crop owners
                    # alive while comparing, rather than reading freed temporaries.
                    actual_region=actual.copy(x,y,right-x,bottom-y)
                    expected_region=expected.copy(x,y,right-x,bottom-y)
                    self.assertEqual(bytes(actual_region.constBits()),bytes(expected_region.constBits()))
                    self.assertEqual(actual.size(),image.size())
