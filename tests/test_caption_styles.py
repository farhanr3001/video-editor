import copy,tempfile,unittest
from pathlib import Path
from PySide6.QtCore import Qt,QRectF,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter,QFontDatabase
from PySide6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication([])
from kinetic_cut.model import Caption,CaptionStyle,Project
from kinetic_cut.captions import _from_segments,split_caption,merge_captions
from kinetic_cut.caption_words import timings,active_word,prepare_generated,remove_periods,set_text

class CaptionStyleTests(unittest.TestCase):
    def test_word_onsets_preserved_without_padding_distribution(self):
        caps=_from_segments([dict(start=0,end=3,text='This is great.',words=[dict(text='This',start=0,end=.2),dict(text='is',start=.3,end=.5),dict(text='great.',start=1,end=1.4)])],offset=10,words_per_caption=3)
        self.assertEqual(timings(caps[0]),[(10,10.2),(10.3,10.5),(11,11.4)])
        self.assertIsNone(active_word(caps[0],10.8)); self.assertEqual(active_word(caps[0],11.1),2)
        caps[0].start+=5; caps[0].end+=5; self.assertEqual(timings(caps[0])[2],(16,16.4))
    def test_remove_periods_preserves_internal_punctuation(self):
        self.assertEqual(remove_periods('Hello there. 3.14 is pi. "Really." wow... www.test.com'), 'Hello there 3.14 is pi "Really" wow www.test.com')
    def test_split_merge_and_overwrite_preserve_word_metadata(self):
        caption=Caption('a',0,4,'Hello world',word_timings=[dict(text='Hello',start=0,end=1),dict(text='world',start=2,end=3)],highlighted_words=[1])
        left,right=split_caption(caption,2); self.assertEqual(left.text,'Hello world'); self.assertEqual(right.text,'Hello world'); self.assertEqual(right.highlighted_words,[1])
        part1=Caption('p1',0,2,'Hello',word_timings=[dict(text='Hello',start=0,end=1)])
        part2=Caption('p2',2,4,'world',word_timings=[dict(text='world',start=0,end=1)],highlighted_words=[0])
        merged=merge_captions([part1,part2]); self.assertEqual(timings(merged),[(0,1),(2,3)]); self.assertEqual(merged.highlighted_words,[1])
        project=Project(captions=[caption,Caption('b',1,2,'New')]); project.overwrite_captions({'b'})
        tail=next(c for c in project.captions if c.start==2); self.assertEqual(timings(tail)[1],(2,3))
    def test_sparse_keyword_emphasis_and_serialization(self):
        style=CaptionStyle(animation='word highlight 2',glow_enabled=True)
        caps=[Caption('a',0,1,'This is incredible.'),Caption('b',1,2,'another amazing result'),Caption('c',2,3,'the and is'),Caption('d',3,4,'win 500 today')]
        prepare_generated(caps,style,True)
        self.assertEqual(caps[0].highlighted_words,[2]); self.assertFalse(caps[1].highlighted_words); self.assertFalse(caps[2].highlighted_words); self.assertEqual(caps[3].highlighted_words,[1])
        p=Project(captions=caps,subtitle_style=style); restored=Project.from_dict(p.to_dict()); self.assertEqual(restored.to_dict(),p.to_dict())
    def test_case_edits_preserve_metadata_but_replacements_clear_it(self):
        c=Caption('a',0,2,'Hello world',word_timings=[dict(text='Hello',start=0,end=.3),dict(text='world',start=1,end=1.5)],highlighted_words=[1])
        set_text(c,'HELLO WORLD'); self.assertEqual(c.highlighted_words,[1]); self.assertEqual(timings(c)[1],(1,1.5))
        set_text(c,'Different sentence'); self.assertEqual(c.highlighted_words,[]); self.assertEqual(c.word_timings,[])
    def test_font_menu_short_and_legacy_font_preserved(self):
        from kinetic_cut.caption_fonts import CaptionFontCombo
        picker=CaptionFontCombo(); self.assertLess(picker.count(),25); self.assertGreaterEqual(picker.findText('Nirmala UI'),0)
        self.assertIn('Anton',QFontDatabase.families()); picker.setCurrentText('Legacy project font'); self.assertEqual(picker.currentText(),'Legacy project font')
    def test_user_geometos_font_registered_and_exported_as_matching_shapes(self):
        from kinetic_cut.caption_fonts import CaptionFontCombo
        from kinetic_cut.subtitle_render import write
        from PySide6.QtGui import QFont,QFontInfo
        picker=CaptionFontCombo(); self.assertGreaterEqual(picker.findText('Geometos'),0)
        self.assertIn('Geometos',QFontDatabase.families()); self.assertEqual(QFontInfo(QFont('Geometos')).family(),'Geometos')
        project=Project(captions=[Caption('a',0,2,'GEOMETOS CHECK')]); project.subtitle_style.font='Geometos'; project.subtitle_style.animation='none'
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'geometos.ass'; write(project,target)
            self.assertIn('\\p1',target.read_text(encoding='utf-8-sig'))
    def test_dialog_dependencies_hover_and_glow(self):
        from kinetic_cut.caption_style_dialog import CaptionStyleDialog
        dialog=CaptionStyleDialog(CaptionStyle(),{})
        dialog.words.setValue(1); dialog.animation.setCurrentText('fade every word'); self.assertEqual(dialog.words.minimum(),3)
        dialog.animation.setCurrentText('word highlight 2'); self.assertEqual(dialog.words.minimum(),2); self.assertTrue(dialog.form.isRowVisible(dialog.color_buttons['highlight']))
        dialog.animation.setCurrentText('none'); self.assertFalse(dialog.form.isRowVisible(dialog.color_buttons['highlight']))
        selected=dialog.font.currentText(); dialog.hover_preview('Anton'); self.assertEqual(dialog.selected_style().font,'Anton'); self.assertEqual(dialog.font.currentText(),selected)
        dialog.hover_preview(''); self.assertEqual(dialog.selected_style().font,selected)
        dialog.glow.setChecked(True); self.assertTrue(dialog.selected_style().glow_follow_color); self.assertTrue(dialog.form.isRowVisible(dialog.glow_radius))
        dialog.glow_follow.setChecked(False); self.assertTrue(dialog.form.isRowVisible(dialog.color_buttons['glow_color'])); dialog.close()
    def test_new_styles_preview_and_export(self):
        from kinetic_cut.visuals import draw_caption
        from kinetic_cut.subtitle_render import write
        c=Caption('a',0,3,'This looks incredible',word_timings=[dict(text='This',start=0,end=.2),dict(text='looks',start=.6,end=1),dict(text='incredible',start=2,end=2.7)],highlighted_words=[2])
        p=Project(captions=[c]); p.settings.width=640; p.settings.height=360; p.subtitle_style.size=40; p.subtitle_style.glow_enabled=True
        with tempfile.TemporaryDirectory() as folder:
            for animation in ('fade every word','word highlight 2','word highlight','punch','fade','none','bounce','karaoke'):
                p.subtitle_style.animation=animation; p.playhead=2.3
                image=QImage(640,360,QImage.Format_ARGB32); image.fill(Qt.black); painter=QPainter(image)
                try:draw_caption(painter,p,c,QRectF(0,0,640,360))
                finally:painter.end()
                target=Path(folder)/'style.ass'; write(p,target); ass=target.read_text(encoding='utf-8-sig')
                self.assertIn('\\blur12',ass)
                if animation=='fade every word':self.assertIn('0:00:02.00',ass); self.assertIn('\\fad(120,100)',ass)
                if animation=='bounce':self.assertIn('\\fscx125',ass)

    def test_caption_style_dialog_preset_dropdown(self):
        from kinetic_cut.caption_style_dialog import CaptionStyleDialog
        dialog = CaptionStyleDialog(CaptionStyle(), {})
        self.assertTrue(hasattr(dialog, "preset"))
        self.assertGreaterEqual(dialog.preset.count(), 6)
        self.assertEqual(dialog.preset.itemText(0), "Custom / Current")

        # Select Crime Red Alert
        idx = dialog.preset.findText("Crime Red Alert")
        self.assertGreater(idx, 0)
        dialog.preset.setCurrentIndex(idx)
        self.assertEqual(dialog.font.currentText(), "Anton")
        self.assertTrue(dialog.upper.isChecked())
        self.assertTrue(dialog.glow.isChecked())
        self.assertEqual(dialog.colors["highlight"], "#FF2233")
        self.assertEqual(dialog.colors["glow_color"], "#FF2233")
        style = dialog.selected_style()
        self.assertEqual(style.font, "Anton")
        self.assertTrue(style.uppercase)

        # Select Viral TikTok Yellow
        idx_yellow = dialog.preset.findText("Viral TikTok Yellow")
        dialog.preset.setCurrentIndex(idx_yellow)
        self.assertEqual(dialog.colors["highlight"], "#FFE600")
        self.assertEqual(dialog.colors["glow_color"], "#FFE600")

        # Tweak a control manually -> preset reverts to "Custom / Current"
        dialog.size.setValue(99)
        self.assertEqual(dialog.preset.currentIndex(), 0)
        dialog.close()

    def test_dialog_two_tabs_and_no_preset_row_in_ui(self):
        from kinetic_cut.caption_style_dialog import CaptionStyleDialog
        dialog = CaptionStyleDialog(CaptionStyle(), {})
        self.assertTrue(hasattr(dialog, "tabs"))
        self.assertEqual(dialog.tabs.count(), 2)
        self.assertEqual(dialog.tabs.tabText(0), "Caption Setup")
        self.assertEqual(dialog.tabs.tabText(1), "Choose Template")
        # Ensure preset combo box is NOT added to the visible form layout
        self.assertEqual(dialog.form.indexOf(dialog.preset), -1)
        dialog.close()

    def test_template_cards_hover_and_selection(self):
        from PySide6.QtCore import QEvent
        from kinetic_cut.caption_style_dialog import CaptionStyleDialog
        from kinetic_cut.caption_templates import CAPTION_TEMPLATES
        dialog = CaptionStyleDialog(CaptionStyle(), {})
        self.assertEqual(len(dialog.template_cards), len(CAPTION_TEMPLATES))
        self.assertTrue(dialog.template_cards[0].template.get("is_none"))

        # Find CapCut Emoji Pop card
        emoji_card = next(c for c in dialog.template_cards if c.template.get("id") == "capcut_emoji_pop")
        self.assertFalse(emoji_card.timer.isActive())

        # Test hover event starts timer
        dialog.app = _app
        from PySide6.QtGui import QEnterEvent
        enter_ev = QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
        emoji_card.enterEvent(enter_ev)
        self.assertTrue(emoji_card.is_hovered)
        self.assertTrue(emoji_card.timer.isActive())

        # Test leave event stops timer
        leave_ev = QEvent(QEvent.Leave)
        emoji_card.leaveEvent(leave_ev)
        self.assertFalse(emoji_card.is_hovered)
        self.assertFalse(emoji_card.timer.isActive())

        # Test card click selects template and updates controls
        emoji_card.clicked.emit(emoji_card.template)
        self.assertEqual(dialog.selected_template_id, "capcut_emoji_pop")
        self.assertTrue(emoji_card.is_selected)
        self.assertEqual(dialog.font.currentText(), "Komika Axis")
        self.assertEqual(dialog.animation.currentText(), "emoji pop")
        self.assertEqual(dialog.colors["highlight"], "#FFE600")
        self.assertTrue(dialog.form.isRowVisible(dialog.color_buttons["highlight"]))

        style = dialog.selected_style()
        self.assertEqual(style.font, "Komika Axis")
        self.assertEqual(style.animation, "emoji pop")
        self.assertEqual(style.highlight, "#FFE600")

        # Test selecting Neon Glow template
        neon_card = next(c for c in dialog.template_cards if c.template.get("id") == "neon_glow")
        neon_card.clicked.emit(neon_card.template)
        self.assertEqual(dialog.selected_template_id, "neon_glow")
        self.assertTrue(neon_card.is_selected)
        self.assertFalse(emoji_card.is_selected)
        self.assertTrue(dialog.glow.isChecked())
        self.assertEqual(dialog.colors["glow_color"], "#FF2A85")

        # Test selecting No Template card
        none_card = dialog.template_cards[0]
        none_card.clicked.emit(none_card.template)
        self.assertEqual(dialog.selected_template_id, "none")
        self.assertTrue(none_card.is_selected)
        self.assertFalse(neon_card.is_selected)
        self.assertIsNone(dialog.selected_style().id)
        dialog.close()

    def test_capcut_emoji_mapping_and_karaoke(self):
        from kinetic_cut.caption_emojis import get_caption_emojis, find_emoji_for_word
        # Contextual mappings
        self.assertEqual(find_emoji_for_word("curious"), "🤔")
        self.assertEqual(find_emoji_for_word("danger"), "⚠️")
        self.assertEqual(find_emoji_for_word("sinking"), "🌊")
        self.assertEqual(find_emoji_for_word("fire"), "🔥")

        emojis = get_caption_emojis("CURIOUS ABOUT THIS", max_emojis=1)
        self.assertEqual(len(emojis), 1)
        self.assertEqual(emojis[0][1], "🤔")
        self.assertEqual(get_caption_emojis("Okay?"), [])
        self.assertIsNone(find_emoji_for_word("a"))

        # Double emoji
        emojis2 = get_caption_emojis("DANGER WATER ESCAPE", max_emojis=2)
        self.assertEqual(len(emojis2), 2)
        self.assertEqual(emojis2[0][1], "⚠️")
        self.assertEqual(emojis2[1][1], "🌊")

    def test_inspector_templates_tab_and_customize_isolation(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.caption_templates import CAPTION_TEMPLATES
        w = MainWindow()
        try:
            p = w.project
            c1 = Caption('c1', 0, 1.0, 'Word One')
            c1.customize = False
            c2 = Caption('c2', 1.0, 2.0, 'Customized Word')
            c2.customize = True
            c2.style = CaptionStyle()
            c2.style.font = 'Impact'
            c2.style.size = 115
            p.captions = [c1, c2]

            panel = w.inspector
            self.assertEqual(panel.subtitle.count(), 4)
            self.assertEqual(panel.subtitle.tabText(2), 'Timings')
            self.assertEqual(panel.subtitle.tabText(3), 'Templates')

            # Apply CapCut Emoji template
            tmpl_emoji = next(t for t in CAPTION_TEMPLATES if t.get('id') == 'capcut_emoji_pop')
            panel.apply_inspector_template(tmpl_emoji)

            # c1 must be updated to template
            self.assertEqual(p.subtitle_style.font, 'Komika Axis')
            self.assertEqual(p.subtitle_style.animation, 'emoji pop')
            self.assertEqual(c1.style.font, 'Komika Axis')
            self.assertEqual(c1.style.animation, 'emoji pop')

            # c2 MUST NOT be touched because customize is True!
            self.assertEqual(c2.style.font, 'Impact')
            self.assertEqual(c2.style.size, 115)

            # Apply No Template disable card
            tmpl_none = CAPTION_TEMPLATES[0]
            panel.apply_inspector_template(tmpl_none)
            self.assertIsNone(p.subtitle_style.id)
            self.assertIsNone(c1.style.id)
            self.assertEqual(c1.style.animation, 'pop')
            # c2 still preserved!
            self.assertEqual(c2.style.font, 'Impact')
            self.assertEqual(c2.style.size, 115)
        finally:
            w.close()

