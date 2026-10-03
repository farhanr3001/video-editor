import copy,unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint,Qt,QEvent,QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,Caption,TimelineItem,MediaItem
from kinetic_cut.controls import SafeSlider
from kinetic_cut.captions import split_caption


class SubtitleEditingTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.app=QApplication.instance(); self.w=MainWindow(); self.w.resize(1400,850); self.w.show(); self.w.autosave_timer.stop()
        self.p=Project(captions=[Caption('a',0,2,'One'),Caption('b',4,6,'Two'),Caption('c',8,10,'Three')]); self.w.set_project(self.p)
        self.t=self.w.timeline; self.t.set_zoom(35); self.app.processEvents()
    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); self.w.deleteLater(); self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
    def drag(self,start,end,alt=False,release=True):
        mod=Qt.AltModifier if alt else Qt.NoModifier
        QTest.mousePress(self.t.viewport(),Qt.LeftButton,mod,start); QTest.mouseMove(self.t.viewport(),end)
        if release:QTest.mouseRelease(self.t.viewport(),Qt.LeftButton,mod,end)
    def cap(self,id):return next(c for c in self.w.project.captions if c.id==id)
    def test_single_word_blade_cut_at_playhead_succeeds(self):
        self.w.seek(1); self.t.tool='blade'; rect=self.t.visible_caption_rect(self.cap('a')); pos=QPoint(round(self.t.x_for_time(1)),round(rect.center().y()))
        QTest.mouseClick(self.t.viewport(),Qt.LeftButton,pos=pos)
        parts=sorted((c for c in self.w.project.captions if c.text=='One'),key=lambda c:c.start)
        self.assertEqual(len(parts),2); self.assertEqual([(c.start,c.end) for c in parts],[(0,1),(1,2)])
    def test_custom_caption_off_and_on_keep_header_compact(self):
        self.t.select_captions({'a'},'a'); panel=self.w.inspector
        for height in (650,850,1100):
            self.w.resize(1400,height); self.app.processEvents()
            positions=[]
            for custom in (False,True,False):
                panel.customize.setChecked(custom); self.app.processEvents()
                positions.append((panel.caption_text.y(),panel.customize.y()))
                self.assertLess(panel.caption_text.y(),110)
                self.assertLess(panel.customize.y()-panel.caption_text.geometry().bottom(),15)
            self.assertEqual(positions[0],positions[1]); self.assertEqual(positions[0],positions[2])
    def test_case_toggle_batch_and_highlight_undo(self):
        self.t.select_captions({'a','b'},'a'); panel=self.w.inspector
        panel.caption_text.case_button.click(); self.assertEqual((self.cap('a').text,self.cap('b').text),('ONE','ONE'))
        panel.caption_text.case_button.click(); self.assertEqual(self.cap('a').text,'one')
        self.w.flush_text_edit(); panel.toggle_word_highlight('a',0); self.assertEqual(self.cap('a').highlighted_words,[0])
        panel.subtitle.setCurrentIndex(2); panel.refresh_timings(); self.assertTrue(panel.caption_table.item(0,2).data(Qt.UserRole+1))
        self.w.undo(); self.assertEqual(self.cap('a').highlighted_words,[])
    def test_overwrite_retains_both_tails_and_style_and_rejects_overlap(self):
        self.p.captions=[Caption('long',0,10,'Original'),Caption('new',3,5,'New')]; self.p.captions[0].style.color='#112233'
        self.p.overwrite_captions({'new'}); ordered=sorted(self.p.captions,key=lambda c:c.start)
        self.assertEqual([(c.start,c.end) for c in ordered],[(0,3),(3,5),(5,10)]); self.assertEqual(ordered[-1].style.color,'#112233')
        self.assertIsNot(ordered[0].style,ordered[-1].style)
    def test_multi_caption_move_preserves_selection_and_offsets(self):
        self.t.select_captions({'a','b'},'a'); start=self.t.visible_caption_rect(self.cap('a')).center().toPoint()
        self.drag(start,start+QPoint(70,0)); self.assertEqual(self.t.selected_caption_ids,{'a','b'})
        self.assertEqual((self.cap('a').start,self.cap('b').start),(2,6))
        self.w.undo(); self.assertEqual((self.cap('a').start,self.cap('b').start),(0,4))
    def test_alt_drag_duplicates_selected_subtitles_and_escape_discards(self):
        self.t.select_captions({'a','b'},'a'); start=self.t.visible_caption_rect(self.cap('a')).center().toPoint()
        self.drag(start,start+QPoint(385,0),alt=True,release=False); self.assertEqual(len(self.p.captions),3)
        QTest.keyClick(self.t.viewport(),Qt.Key_Escape); self.assertEqual(len(self.p.captions),3)
        self.drag(start,start+QPoint(385,0),alt=True); self.assertEqual(len(self.p.captions),5)
        self.assertEqual(len(self.t.selected_caption_ids),2); self.assertFalse(self.t.selected_caption_ids&{'a','b','c'})
        self.assertEqual((self.cap('a').start,self.cap('b').start),(0,4))
    def test_trim_previews_overwrite_and_undo_restores_neighbour(self):
        r=self.t.visible_caption_rect(self.cap('a')); start=QPoint(round(r.right()-2),round(r.center().y())); end=QPoint(round(self.t.x_for_time(5)-2),start.y())
        self.drag(start,end,release=False); self.assertEqual(self.cap('a').end,5)
        neighbour=next(c for c in self.t.caption_painted if c.id=='b'); self.assertEqual(neighbour.start,5); self.assertEqual(self.cap('b').start,4)
        QTest.mouseRelease(self.t.viewport(),Qt.LeftButton,pos=end); self.assertEqual(self.cap('b').start,5)
        self.w.undo(); self.assertEqual((self.cap('a').end,self.cap('b').start),(2,4))
    def test_custom_properties_and_text_apply_to_all_selected_not_other_captions(self):
        self.t.select_captions({'a','b'},'a'); panel=self.w.inspector; panel.customize.setChecked(True)
        for attr,value in [('position_y',.3),('color','#123456'),('background_enabled',True),('animation','fade'),('font_face','Italic'),('outline_width',11)]:
            panel.edit_style(attr,value); self.assertEqual(getattr(self.cap('a').style,attr),value); self.assertEqual(getattr(self.cap('b').style,attr),value)
        self.assertFalse(self.cap('c').customize); self.assertEqual(self.cap('c').style.position_y,.78)
        panel.caption_text.setPlainText('Both'); self.assertEqual(self.cap('a').text,'Both'); self.assertEqual(self.cap('b').text,'Both'); self.assertEqual(self.cap('c').text,'Three')
    def test_timings_own_tab_and_custom_style_immediately_follows_checkbox(self):
        self.t.select_captions({'a'},'a'); panel=self.w.inspector
        self.assertEqual(panel.subtitle.tabText(2),'Timings'); self.assertFalse(panel.subtitle.widget(0).isAncestorOf(panel.caption_table))
        layout=panel.caption_header.parentWidget().layout(); self.assertEqual(layout.indexOf(panel.custom_style_host),layout.indexOf(panel.caption_header)+1)
        panel.customize.setChecked(True); self.assertEqual(panel.style_content.parentWidget(),panel.custom_style_host)
        self.assertIsNone(panel.style_scroll.widget())
        panel.subtitle.setCurrentIndex(2); self.assertEqual(panel.caption_table.rowCount(),3)
    def test_cursor_at_end_typing_is_one_undo_and_does_not_refresh_tables(self):
        self.t.select_captions({'a'},'a'); panel=self.w.inspector
        self.assertEqual(panel.caption_text.textCursor().position(),3)
        with patch.object(self.w,'commit_history',wraps=self.w.commit_history) as history,patch.object(panel,'refresh_timings') as table:
            for character in ' test':panel.caption_text.insertPlainText(character)
            self.assertEqual(history.call_count,0); self.assertEqual(table.call_count,0); self.w.flush_text_edit(); self.assertEqual(history.call_count,1)
        self.w.undo(); self.assertEqual(self.cap('a').text,'One'); self.w.redo(); self.assertEqual(self.cap('a').text,'One test')
    def test_timings_cells_edit_and_invalid_times_revert(self):
        self.t.select_captions({'a'},'a'); panel=self.w.inspector; panel.subtitle.setCurrentIndex(2)
        panel.caption_table.item(0,1).setText('5'); self.assertEqual(self.cap('a').end,5); self.assertEqual(self.cap('b').start,5)
        panel.caption_table.item(0,0).setText('nan'); self.assertEqual(self.cap('a').start,0); self.assertEqual(panel.caption_table.item(0,0).text(),'0.000')
        panel.caption_table.item(0,2).setText('Updated'); self.assertEqual(self.cap('a').text,'Updated')
    def test_history_shared_records_never_alias_live_project(self):
        self.t.select_captions({'a'},'a'); panel=self.w.inspector; panel.caption_text.insertPlainText('!'); self.w.flush_text_edit()
        before=self.w._history[0]; after=self.w._history[-1]
        self.assertIs(before.captions[1],after.captions[1]); self.assertIsNot(self.p.captions[1],after.captions[1])
        self.p.captions[1].style.color='#abcdef'; self.assertNotEqual(after.captions[1].style.color,'#abcdef')
    def test_locked_captions_display_real_values_without_allowing_edits(self):
        self.cap('a').customize=True; self.cap('a').style.position_y=.25; self.p.track_states['subtitle_1']['locked']=True
        self.t.select_captions({'a'},'a'); panel=self.w.inspector
        row=next(row for attr,row in panel.style_bindings if attr=='position_y')
        self.assertEqual(row.spin.value(),.25*self.p.settings.height); self.assertTrue(panel.caption_text.isReadOnly()); self.assertFalse(panel.customize.isEnabled())
        panel.edit_style('position_y',.5); self.assertEqual(self.cap('a').style.position_y,.25)
    def test_position_y_scrubs_in_track_and_custom_caption(self):
        self.t.select_captions({'a'},'a'); panel=self.w.inspector
        row=next(row for attr,row in panel.style_bindings if attr=='position_y')
        for custom in (False,True):
            panel.subtitle.setCurrentIndex(0); panel.customize.setChecked(custom); panel.subtitle.setCurrentIndex(0 if custom else 1); self.app.processEvents()
            old=panel.style_target().position_y; edit=row.spin.lineEdit(); start=edit.rect().center()
            QTest.mousePress(edit,Qt.LeftButton,pos=start); QTest.mouseMove(edit,start+QPoint(12,0)); QTest.mouseRelease(edit,Qt.LeftButton,pos=start+QPoint(12,0))
            self.assertGreater(panel.style_target().position_y,old); self.assertLess(panel.style_target().position_y-old,.1)
    def test_effect_and_title_properties_apply_to_same_type_selection(self):
        self.p.timeline=[TimelineItem('x','','video_1',0,2,role='title',title_text='X'),TimelineItem('y','','video_2',0,2,role='title',title_text='Y')]; self.p.add_track('video'); self.w.set_project(self.p)
        self.t.select_ids({'x','y'},'x'); panel=self.w.inspector; panel.edit_style('position_y',.25); panel.title_text.setPlainText('Same')
        self.assertTrue(all(i.title_style.position_y==.25 and i.title_text=='Same' for i in self.p.timeline))
        self.w.flush_text_edit()
        for i in self.p.timeline:i.role='normal'; i.effects=[dict(name='Gaussian Blur',horizontal=12,vertical=12,linked=True)]
        panel.select('x'); panel.edit_effect('horizontal',33); self.assertTrue(all(i.effects[0]['vertical']==33 for i in self.p.timeline))
    def test_slider_groove_click_jumps_and_continues_dragging(self):
        slider=SafeSlider(Qt.Horizontal); slider.setRange(0,1000); slider.resize(220,30); slider.show(); self.app.processEvents()
        QTest.mousePress(slider,Qt.LeftButton,pos=QPoint(170,15)); self.assertGreater(slider.value(),750)
        QTest.mouseMove(slider,QPoint(45,15)); self.assertLess(slider.value(),250)
        QTest.mouseRelease(slider,Qt.LeftButton,pos=QPoint(45,15)); self.assertFalse(slider.isSliderDown()); slider.close()
