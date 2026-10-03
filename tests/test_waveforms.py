import tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage,QPainter,QColor
from kinetic_cut.waveforms import Waveform,waveform,paint_waveform,RATE
from kinetic_cut.model import MediaItem,TimelineItem


class WaveformTests(unittest.TestCase):
    def wav(self,path,frames):
        with wave.open(str(path),'wb') as out:
            out.setnchannels(2); out.setsampwidth(2); out.setframerate(RATE); out.writeframes(np.asarray(frames,dtype='<i2').tobytes())
    def test_preserves_stereo_transients_and_last_partial_bin(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'audio.wav'; samples=np.zeros((RATE*3+7,2),dtype=np.int16)
            samples[1000]=[23000,-23000]; samples[-1]=[15000,-16000]; self.wav(path,samples)
            with patch('kinetic_cut.config.CACHE_DIR',Path(directory)):
                result=waveform(str(path),points=1000)
            self.assertEqual(len(result),3001); self.assertEqual(tuple(result.peaks[1000//24]),(-23000,23000)); self.assertEqual(tuple(result.peaks[-1]),(-16000,15000))
    def test_cache_reuse_and_source_change_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); path=root/'audio.wav'; self.wav(path,np.zeros((RATE,2),dtype=np.int16))
            with patch('kinetic_cut.config.CACHE_DIR',root):
                first=waveform(str(path))
                with patch('kinetic_cut.waveforms.popen',side_effect=AssertionError('Unexpected decode')):
                    self.assertTrue(np.array_equal(first.peaks,waveform(str(path)).peaks))
                self.wav(path,np.full((RATE*2,2),7000,dtype=np.int16)); second=waveform(str(path))
                self.assertEqual(len(second),2000); self.assertGreater(second.peaks[:,1].max(),6000)
    def test_zoom_levels_preserve_impulses_and_do_not_repeat_beyond_source(self):
        peaks=np.zeros((60000,2),dtype=np.int16); peaks[12345]=[-12000,24000]; data=Waveform(peaks)
        for width in (.001,.01,.1,1):
            start=np.floor(12.345/width)*width; result=data.columns([start],width)[0]
            self.assertLessEqual(result[0],-12000/32768); self.assertGreaterEqual(result[1],24000/32768)
        self.assertTrue(np.all(data.columns([61,99],.1)==0))
    def test_signed_peak_display_has_split_centre_and_no_artificial_boost(self):
        data=Waveform(np.tile([-8000,16000],(3000,1)))
        media=MediaItem('m','','audio','test',3); item=TimelineItem('a','m','audio_1',0,3)
        image=QImage(310,70,QImage.Format_RGB32); image.fill(QColor('#326951')); painter=QPainter(image)
        paint_waveform(painter,QRectF(0,0,300,62),data,media,item,100,0,300); painter.end()
        self.assertGreater(image.pixelColor(150,17).lightness(),170)
        self.assertLess(image.pixelColor(150,7).lightness(),100)
        self.assertLess(image.pixelColor(150,25).lightness(),150)
        self.assertGreater(image.pixelColor(150,28).lightness(),170)
    def test_crop_speed_and_fades_map_source_time(self):
        peaks=np.zeros((4000,2),dtype=np.int16); peaks[2000:2500]=[-32000,32000]; data=Waveform(peaks)
        self.assertTrue(np.all(data.columns(np.array([0,.5])+2,.01)[0]!=0))
        media=MediaItem('m','','audio','test',4); item=TimelineItem('a','m','audio_1',0,1,2,speed=2,fade_in=.2)
        image=QImage(205,70,QImage.Format_RGB32); image.fill(QColor('#326951')); painter=QPainter(image)
        paint_waveform(painter,QRectF(0,0,200,62),data,media,item,200,0,200); painter.end()
        self.assertGreater(image.pixelColor(43,10).lightness(),170)
        self.assertLess(image.pixelColor(150,10).lightness(),100)
