import sys
import threading
import types
import subprocess
import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication
from kinetic_cut.captions import transcribe,_from_segments,CaptionBackendError,CaptionCancelled
from kinetic_cut.caption_alignment import ctc_spans,preserve_fillers,usable_words
from kinetic_cut.caption_progress import CaptionProgressDialog
from kinetic_cut import caption_runtime

app=QApplication.instance() or QApplication([])


class WordBoundaryTests(unittest.TestCase):
    def test_ctc_repeated_letters_require_blank_and_all_tokens_survive(self):
        # A, blank, A, blank, B. Two repeated As cannot share a frame.
        logits=np.full((5,3),-20.,np.float32)
        for frame,token in enumerate([1,0,1,0,2]):logits[frame,token]=20
        spans=ctc_spans(logits,[1,1,2],0)
        self.assertEqual(spans,[[0,1],[2,3],[4,5]])
        self.assertIsNone(ctc_spans(logits[:1],[1,1,2],0))

    def test_alignment_is_bounded_and_cancellable(self):
        self.assertIsNone(ctc_spans(np.zeros((2501,3)),[1],0))
        with self.assertRaises(CaptionCancelled):ctc_spans(np.zeros((100,3)),[1],0,lambda:True)

    def test_collapsed_recognized_word_is_retained_but_not_called_exact(self):
        words=[dict(text='oh',start=0,end=.2),dict(text='it',start=.2,end=.2),dict(text='works',start=.4,end=1)]
        usable_words(words,0,1)
        self.assertEqual([w['text'] for w in words],['oh','it','works'])
        self.assertGreater(words[1]['end'],words[1]['start']);self.assertEqual(words[1]['confidence'],0)
        with self.assertRaises(CaptionBackendError):usable_words([dict(text='shit',start=0,end=0)],0,1,True)
        ending=[dict(text='say',start=0,end=1),dict(text='it',start=1,end=1)]
        usable_words(ending,0,1)
        self.assertEqual(ending[-1]['end'],1);self.assertEqual(ending[0]['end'],ending[1]['start'])

    def test_sustained_um_keeps_entire_voiced_island_without_stealing_next_word(self):
        words=[dict(text='Ummm...',start=4.3,end=4.55,_recognizer_start=3.48),dict(text='best',start=5.8,end=6)]
        preserve_fillers(words,[(3.68,4.8),(5.8,6.2)])
        self.assertAlmostEqual(words[0]['start'],3.68);self.assertAlmostEqual(words[0]['end'],4.8)
        words=[dict(text='um',start=.2,end=.3,_recognizer_start=0),dict(text='yes',start=.7,end=1)]
        preserve_fillers(words,[(.05,1)])
        self.assertAlmostEqual(words[0]['end'],.7)

    def test_card_size_changes_neither_onsets_nor_spoken_tails(self):
        words=[dict(text='Best',start=1.15,end=1.46),dict(text='music',start=1.70,end=1.96),dict(text='um',start=2.1,end=3.2),dict(text='yes',start=3.6,end=4)]
        for size in (1,2,3,4,8,12):
            cards=_from_segments([dict(text='Best music um yes',start=1,end=4,words=words)],offset=10,words_per_caption=size,hold_seconds=.08)
            restored=[(w['text'],round(c.start+w['start'],5),round(c.start+w['end'],5)) for c in cards for w in c.word_timings]
            self.assertEqual(restored,[(w['text'],w['start']+10,w['end']+10) for w in words])
            self.assertTrue(all(c.end>=c.start+max(w['end'] for w in c.word_timings) for c in cards))
            self.assertTrue(all(a.end<=b.start for a,b in zip(cards,cards[1:])))


class EngineTests(unittest.TestCase):
    def modules(self,model):
        parent=types.ModuleType('faster_whisper');parent.WhisperModel=model
        audio=types.ModuleType('faster_whisper.audio');audio.decode_audio=lambda *a,**k:np.zeros(32000,np.float32)
        vad=types.ModuleType('faster_whisper.vad');vad.VadOptions=lambda **k:None
        vad.get_speech_timestamps=lambda *a:[dict(start=0,end=32000)]
        return {'faster_whisper':parent,'faster_whisper.audio':audio,'faster_whisper.vad':vad}

    def test_gpu_failure_retries_whole_transcript_on_cpu_without_partial_cards(self):
        devices=[]
        class Model:
            def __init__(self,*a,device,**k):self.device=device;devices.append(device)
            def transcribe(self,*a,**k):
                def segments():
                    yield types.SimpleNamespace(start=0.,end=1.,text='hello',words=[types.SimpleNamespace(word='hello',start=0.,end=1.)])
                    if self.device=='cuda':raise RuntimeError('GPU became unavailable')
                return segments(),None
        with patch.dict(sys.modules,self.modules(Model)),patch('kinetic_cut.caption_runtime.model_arguments',return_value=('fixture',{})),patch('kinetic_cut.caption_runtime.device_options',return_value=[('cuda','float16',[]),('cpu','int8',[])]):
            cards,backend=transcribe('fixture',{'caption_alignment':False})
        self.assertEqual(devices,['cuda','cpu']);self.assertEqual(len(cards),1);self.assertIn('CPU',backend)

    def test_cancel_after_gpu_start_never_retries_cpu(self):
        event=threading.Event();devices=[]
        class Model:
            def __init__(self,*a,device,**k):devices.append(device);event.set()
        with patch.dict(sys.modules,self.modules(Model)),patch('kinetic_cut.caption_runtime.model_arguments',return_value=('fixture',{})),patch('kinetic_cut.caption_runtime.device_options',return_value=[('cuda','float16',[]),('cpu','int8',[])]):
            with self.assertRaises(CaptionCancelled):transcribe('fixture',{'caption_alignment':False},cancel_check=event.is_set)
        self.assertEqual(devices,['cuda'])


class ProgressTests(unittest.TestCase):
    def test_clock_updates_between_messages_and_eta_excludes_model_loading(self):
        clock=[0.];dialog=CaptionProgressDialog(clock=lambda:clock[0])
        try:
            clock[0]=30;dialog.refresh_time();self.assertIn('Elapsed 0:30',dialog.labelText());self.assertIn('Estimating',dialog.labelText())
            dialog.set_progress(45,'Transcribing… 0s / 100s')
            clock[0]=40;dialog.set_progress(54,'Transcribing… 20s / 100s')
            self.assertIn('About 0:40 remaining',dialog.labelText())
            clock[0]=42;dialog.refresh_time();self.assertIn('Elapsed 0:42',dialog.labelText())
            dialog.set_progress(45,'GPU speech engine unavailable; retrying with CPU…')
            self.assertIn('Estimating',dialog.labelText())
        finally:dialog.close()
        self.assertFalse(dialog._timer.isActive())


class CaptionProcessTests(unittest.TestCase):
    def test_cancel_reaps_owned_silent_child_and_removes_request_storage(self):
        from kinetic_cut.caption_process import run
        from kinetic_cut.process import popen
        children=[];folders=[];event=threading.Event()
        def silent(command,**kwargs):
            folders.append(Path(command[-1]).parent)
            child=popen([sys.executable,'-c','import time;time.sleep(30)'],**kwargs);children.append(child);return child
        timer=threading.Timer(.3,event.set);timer.start();started=time.monotonic()
        try:
            with patch('kinetic_cut.process.popen',side_effect=silent):
                with self.assertRaises(CaptionCancelled):run('fixture.wav',{},cancel_check=event.is_set)
        finally:timer.cancel()
        self.assertLess(time.monotonic()-started,3);self.assertIsNotNone(children[0].poll())
        self.assertTrue(all(not p.exists() for p in folders))

    def test_request_excludes_credentials_and_reconstructs_word_timing_and_style(self):
        import json
        from kinetic_cut.caption_process import run
        from kinetic_cut.process import popen
        children=[];requests=[]
        def result(command,**kwargs):
            request=Path(command[-1]);requests.append(json.loads(request.read_text()))
            result=dict(backend='fixture',captions=[dict(id='c',start=1.,end=2.,text='hello',style={'font':'Arial'},word_timings=[dict(text='hello',start=0.,end=.8)])])
            script='import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2],encoding="utf-8")'
            child=popen([sys.executable,'-c',script,str(request.parent/'result.json'),json.dumps(result)],**kwargs);children.append(child);return child
        with patch('kinetic_cut.process.popen',side_effect=result):cards,backend=run('fixture.wav',{'elevenlabs_api_key':'SECRET','caption_language':'en'})
        self.assertEqual(requests[0]['settings'],{'caption_language':'en'})
        self.assertEqual(cards[0].style.font,'Arial');self.assertEqual(cards[0].word_timings[0]['end'],.8)
        self.assertEqual(backend,'fixture');self.assertEqual(children[0].poll(),0)


if __name__=='__main__':unittest.main()
