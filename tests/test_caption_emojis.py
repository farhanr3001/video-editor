"""Sparse meaningful emoji emphasis and matching preview/export word windows."""
import copy,unittest
from unittest.mock import patch
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,Caption,CaptionStyle
from kinetic_cut.caption_emojis import get_caption_emojis,find_emoji_for_word,emojis_for_caption

class CaptionEmojiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def project(self,words,spacing=.3):
        return Project(subtitle_style=CaptionStyle(animation='emoji pop'),captions=[Caption(str(n),n*spacing,(n+1)*spacing,word) for n,word in enumerate(words.split())])

    def test_fillers_unknown_words_and_prefix_collisions_stay_plain(self):
        for text in ('Okay?','a in on to it','You will just have to do that','business firewall windowless mindful','foobar xyzzy','fast quick first best out no never'):
            with self.subTest(text=text):self.assertEqual(get_caption_emojis(text),[])
        self.assertIsNone(find_emoji_for_word('firewall')); self.assertEqual(find_emoji_for_word('COFFEE!'),'☕')
        self.assertEqual(get_caption_emojis('coffee',0),[])

    def test_meaningful_keywords_prioritized_over_word_order_and_duplicates(self):
        self.assertEqual(get_caption_emojis('coffee coffee PANIC!',1),[(2,'😰')])
        self.assertEqual(get_caption_emojis('coffee coffee'),[(0,'☕')])
        self.assertEqual(get_caption_emojis('headphones and coffee'),[(0,'🎧'),(2,'☕')])

    def test_context_disambiguates_idioms_time_and_phone_calls(self):
        self.assertEqual(get_caption_emojis('run the code and fire him'),[])
        self.assertEqual(get_caption_emojis('call it a day'),[])
        self.assertEqual(get_caption_emojis('call of duty'),[(2,'🎮')])
        self.assertEqual(get_caption_emojis('five minutes'),[(1,'⏱️')])
        self.assertEqual(get_caption_emojis('minutes from the meeting'),[])
        self.assertEqual(get_caption_emojis('phone on silent',1),[(2,'🔇')])
        self.assertEqual(get_caption_emojis('I will run home',1),[(2,'🏃')])

    def test_cross_caption_context_and_sparse_repeat_suppression(self):
        p=self.project('You will not believe what just happened',.3)
        self.assertEqual(emojis_for_caption(p,p.captions[3]),[(0,'🤯')])
        p=self.project('coffee headphones panic phone money coffee',.4)
        picks=[(c.start,emoji) for c in p.captions for _,emoji in emojis_for_caption(p,c)]
        self.assertTrue(picks); self.assertLessEqual(len(picks),3)
        for n,(start,emoji) in enumerate(picks):
            for other,other_emoji in picks[n+1:]:
                self.assertGreaterEqual(abs(start-other),.8)
                if emoji==other_emoji:self.assertGreaterEqual(abs(start-other),8)

    def test_context_does_not_cross_sentence_or_long_speech_gap(self):
        p=self.project('not. believe',.3); self.assertEqual(emojis_for_caption(p,p.captions[1]),[])
        p=self.project('not believe',2); p.captions[0].end=.3
        self.assertEqual(emojis_for_caption(p,p.captions[1]),[])
        cap=Caption('c',0,1,'not. believe')
        p=Project(captions=[cap],subtitle_style=CaptionStyle(animation='emoji pop'))
        self.assertEqual(emojis_for_caption(p,cap),[])

    def test_selection_updates_after_text_style_retime_and_project_reload(self):
        p=self.project('coffee'); before=copy.deepcopy(p.to_dict())
        self.assertEqual(emojis_for_caption(p,p.captions[0]),[(0,'☕')]); self.assertEqual(p.to_dict(),before)
        p.captions[0].text='Okay?'; self.assertEqual(emojis_for_caption(p,p.captions[0]),[])
        p.captions[0].text='phone'; p.touch(); self.assertEqual(emojis_for_caption(p,p.captions[0]),[(0,'📱')])
        p.subtitle_style.animation='pop'; self.assertEqual(emojis_for_caption(p,p.captions[0]),[])
        p.subtitle_style.animation='emoji pop'; restored=Project.from_dict(p.to_dict())
        self.assertEqual(emojis_for_caption(restored,restored.captions[0]),[(0,'📱')])

    def test_preview_only_draws_selected_word_not_other_words_or_timing_gaps(self):
        from kinetic_cut.visuals import draw_caption
        cap=Caption('c',0,1,'The coffee is',word_timings=[{'text':'The','start':0,'end':.2},{'text':'coffee','start':.3,'end':.7},{'text':'is','start':.8,'end':1}])
        p=Project(captions=[cap],subtitle_style=CaptionStyle(animation='emoji pop'))
        calls=[]
        with patch('kinetic_cut.emoji.draw',side_effect=lambda painter,runs:calls.extend(runs)):
            for time,expected in [(.1,[]),(.25,[]),(.45,['☕']),(.75,[]),(.9,[])]:
                calls.clear(); p.playhead=time; image=QImage(1080,1920,QImage.Format_ARGB32); image.fill(0); painter=QPainter(image)
                try:draw_caption(painter,p,cap,QRectF(0,0,1080,1920))
                finally:painter.end()
                self.assertEqual([emoji for emoji,_ in calls],expected)

    def test_export_matches_selected_word_window_without_first_word_fallback(self):
        from kinetic_cut.word_highlight import events
        cap=Caption('c',0,1,'The coffee is',word_timings=[{'text':'The','start':0,'end':.2},{'text':'coffee','start':.3,'end':.7},{'text':'is','start':.8,'end':1}])
        p=Project(captions=[cap],subtitle_style=CaptionStyle(animation='emoji pop')); calls=[]
        def record(runs,start,end,*args,**kwargs):
            if runs:calls.append(([e for e,_ in runs],start,end))
            return []
        with patch('kinetic_cut.emoji.ass_events',side_effect=record):events(p,cap,'C0')
        self.assertEqual(calls,[(['☕'],.3,.7)])

    def test_full_export_routes_emoji_templates_with_any_font_to_word_events(self):
        import tempfile
        from pathlib import Path
        from kinetic_cut.subtitle_render import write
        for animation in ('emoji pop','double emoji'):
            p=self.project('coffee'); p.subtitle_style.animation=animation
            p.subtitle_style.font='Komika Axis'; p.subtitle_style.glow_enabled=False
            with tempfile.TemporaryDirectory() as folder:
                with patch('kinetic_cut.word_highlight.events',return_value=['EMOJI_WORD_EVENTS']) as generate:
                    target=Path(folder)/'captions.ass'; write(p,target)
                generate.assert_called_once_with(p,p.captions[0],'C0')
                self.assertIn('EMOJI_WORD_EVENTS',target.read_text(encoding='utf-8-sig'))
