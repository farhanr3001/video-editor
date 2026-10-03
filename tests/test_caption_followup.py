"""Word-count, hold, centering and zoom invariants for caption templates."""
import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QRectF,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QStyle,QStyleOptionSpinBox
from PySide6.QtTest import QTest
from kinetic_cut.model import Caption,CaptionStyle,Project
from kinetic_cut.visuals import draw_caption,caption_geometry,caption_emoji_rect
from kinetic_cut.caption_emojis import emojis_for_caption
from kinetic_cut.word_highlight import events

class CaptionFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def fixture(self,text,animation='emoji pop'):
        c=Caption('c',2,5,text,word_timings=[dict(text=w,start=n*.2,end=n*.2+.15) for n,w in enumerate(text.split())])
        p=Project(captions=[c],subtitle_style=CaptionStyle(font='Komika Axis',size=101,animation=animation,color='#FFFFFF',highlight='#FFE600'))
        return p,c

    def colors(self,p,c,time):
        colors=[]; p.playhead=time
        with patch('kinetic_cut.visuals.draw_caption_glyphs',side_effect=lambda painter,path,runs,style,scale:colors.append(style.color)):
            im=QImage(540,960,QImage.Format_ARGB32); im.fill(Qt.black); painter=QPainter(im)
            try:draw_caption(painter,p,c,QRectF(0,0,540,960))
            finally:painter.end()
        return colors

    def test_single_word_color_is_static_for_entire_card_including_hold(self):
        for animation in ('karaoke','emoji pop','double emoji'):
            for word,color in [('happened','#FFFFFF'),('Headphones','#FFE600'),('Okay','#FFFFFF')]:
                p,c=self.fixture(word,animation)
                for time in (2,2.04,2.23,3,4.99):
                    self.assertEqual(self.colors(p,c,time),[color],(animation,word,time))
                lines=[line for line in events(p,c,'C0') if line.startswith('Dialogue: 3,')]
                self.assertEqual(len(lines),1); self.assertIn('0:00:02.00,0:00:05.00',lines[0])
                self.assertIn('1c&H00FFFFFF' if color=='#FFFFFF' else '1c&H0000E6FF',lines[0])

    def test_manual_single_word_emphasis_and_meaningful_words_remain_sparse(self):
        p,c=self.fixture('happened'); c.highlighted_words=[0]
        self.assertEqual(self.colors(p,c,4.99),['#FFE600'])
        p=Project(subtitle_style=CaptionStyle(animation='karaoke'),captions=[Caption(str(n),n*.2,(n+1)*.2,w) for n,w in enumerate('Okay incredible wonderful amazing happened ordinary magical'.split())])
        from kinetic_cut.caption_emphasis import single_word_emphasized
        chosen=[c.text for c in p.captions if single_word_emphasized(p,c)]
        self.assertTrue(chosen); self.assertLess(len(chosen),len(p.captions)/2); self.assertNotIn('happened',chosen)

    def test_two_to_twelve_words_keep_speech_timed_karaoke(self):
        for count in range(2,13):
            for animation in ('karaoke','emoji pop','double emoji'):
                p,c=self.fixture(' '.join(['coffee']+['word']*(count-1)),animation)
                for n in range(count):
                    expected=['#FFFFFF']*count; expected[n]='#FFE600'
                    self.assertEqual(self.colors(p,c,2+n*.2+.05),expected,(count,animation,n))
                self.assertEqual(self.colors(p,c,4.99),['#FFFFFF']*count)

    def test_emoji_centered_over_entire_caption_in_preview_and_export(self):
        for count in range(1,13):
            p,c=self.fixture(' '.join(['word']*(count//2)+['headphones']+['word']*(count-count//2-1)))
            chosen=emojis_for_caption(p,c); self.assertTrue(chosen)
            frame=QRectF(13,27,540,960); geometry=caption_geometry(p,c,frame)
            rect=caption_emoji_rect(geometry[2],geometry[3][chosen[0][0]],.5)
            self.assertAlmostEqual(rect.center().x(),geometry[2].center().x())
            self.assertLess(rect.bottom(),geometry[2].top())
            exported=[]
            def collect(runs,*args,**kwargs):
                if kwargs.get('layer')==5:exported.extend(runs)
                return []
            with patch('kinetic_cut.emoji.ass_events',side_effect=collect):events(p,c,'C0')
            full=caption_geometry(p,c,QRectF(0,0,1080,1920))
            self.assertTrue(exported); self.assertAlmostEqual(exported[0][1].center().x(),full[2].center().x())

    def test_canonical_word_shapes_and_wrapping_identical_at_all_preview_scales(self):
        for count in range(1,13):
            p,c=self.fixture(' '.join((['HEADPHONES','IN,','MINDFUL','MOMENTS']*3)[:count]))
            full=caption_geometry(p,c,QRectF(0,0,1080,1920))
            for scale in (.1,.17,.25,.5,1,2):
                small=caption_geometry(p,c,QRectF(0,0,1080*scale,1920*scale))
                self.assertEqual(len(full[4]),len(small[4]))
                for (a,_),(b,_) in zip(full[4],small[4]):
                    self.assertEqual(a.elementCount(),b.elementCount())
                    for n in range(a.elementCount()):
                        self.assertAlmostEqual(a.elementAt(n).x,b.elementAt(n).x/scale,places=5)
                        self.assertAlmostEqual(a.elementAt(n).y,b.elementAt(n).y/scale,places=5)

    def test_fixture_keeps_headphones_and_happened_plain(self):
        root=Path(__file__).resolve().parents[1]
        fixture=root/'caption_testing.kcut'
        p=Project.load(fixture if fixture.is_file() else root/'tests/fixtures/caption_semantics.json')
        headphones=next(c for c in p.captions if c.text.lower()=='headphones')
        self.assertEqual(emojis_for_caption(p,headphones),[(0,'🎧')])
        happened=next(c for c in p.captions if c.text.lower()=='happened')
        for time in (happened.start+.01,happened.start+.4,happened.end-.01):
            self.assertEqual(self.colors(p,happened,time),['#FFFFFF'])

    def test_setup_tabs_and_spin_arrows_work_and_refresh_across_all_themes(self):
        from kinetic_cut.caption_style_dialog import CaptionStyleDialog
        from kinetic_cut.theme_widgets import apply_application_theme,palette
        d=CaptionStyleDialog(CaptionStyle(animation='emoji pop'),{'caption_words_per_card':3})
        d.show()
        try:
            for theme in ('default','final_cut_obsidian','ableton_gray'):
                apply_application_theme(theme); self.app.processEvents()
                self.assertIn(palette()['bg_panel'],d.tabs.styleSheet())
                self.assertIn(palette()['accent'],d.tabs.styleSheet())
                self.assertIn('color: '+palette()['text_selected'],d.tabs.styleSheet())
                self.assertIn('spin-up',d.words.styleSheet()); self.assertIn('spin-down',d.words.styleSheet())
                d.words.setValue(3); option=QStyleOptionSpinBox(); d.words.initStyleOption(option)
                for sub,expected in ((QStyle.SC_SpinBoxUp,4),(QStyle.SC_SpinBoxDown,3)):
                    r=d.words.style().subControlRect(QStyle.CC_SpinBox,option,sub,d.words)
                    self.assertFalse(r.isEmpty()); QTest.mouseClick(d.words,Qt.LeftButton,pos=r.center()); self.assertEqual(d.words.value(),expected)
        finally:d.close()

    def test_setup_and_card_preview_fit_complete_emoji_composition(self):
        from kinetic_cut.caption_style_dialog import fit_preview
        for count in (1,2,3,6,12):
            p,c=self.fixture(' '.join(['headphones']+['word']*(count-1))); p.settings.height=400
            frame=QRectF(8,8,464,144); fit_preview(p,c,frame)
            geometry=caption_geometry(p,c,frame); bounds=geometry[2]
            rect=caption_emoji_rect(bounds,geometry[3][0],frame.width()/1080)
            center=rect.center(); rect.setWidth(rect.width()*1.3); rect.setHeight(rect.height()*1.3); rect.moveCenter(center)
            composite=bounds.united(rect)
            self.assertGreaterEqual(composite.top(),frame.top())
            self.assertLessEqual(composite.bottom(),frame.bottom())
