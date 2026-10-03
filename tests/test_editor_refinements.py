import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import Qt,QPoint,QPointF,QRectF,QEvent
from PySide6.QtGui import QFontDatabase,QImage,QColor,QPixmap,QPainter,QMouseEvent
from PySide6.QtWidgets import QApplication,QMenu
from PySide6.QtTest import QTest
from kinetic_cut import clipboard
from kinetic_cut.controls import SafeDoubleSpinBox,SafeSpinBox,scrub_delta,InspectorSection
from kinetic_cut.model import Project,TimelineItem,MediaItem,Caption
from kinetic_cut.headline import headline_style,geometry,paths,wrap_lines
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.ui import MainWindow
from kinetic_cut.widgets import PreviewCanvas
from kinetic_cut.workspace import set_page
from kinetic_cut.exporter import write_ass


class RefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        for filename in ("segoeui.ttf","segoeuib.ttf","seguisb.ttf","arial.ttf","arialbd.ttf"):
            path=Path("C:/Windows/Fonts")/filename
            if path.exists():QFontDatabase.addApplicationFont(str(path))

    def project(self):
        media=MediaItem("m","fixture.png","image","fixture.png",10,1920,1080)
        return Project(media=[media],timeline=[TimelineItem("v","m","video_1",1,3,group_id="original",link_id="pair"),TimelineItem("a","m","audio_1",1,3,group_id="original",link_id="pair")],captions=[Caption("c",2,3,"A caption")])

    def window(self):
        w=MainWindow(); w.set_project(self.project()); w.show(); self.app.processEvents()
        self.addCleanup(w.close); return w

    def test_clipboard_preserves_offsets_and_remaps_links_on_each_paste(self):
        p=self.project(); p.timeline[0].speed=2.; payload=clipboard.capture(p,{"v","a"},{"c"})
        ids,caps=clipboard.paste(p,payload,8)
        pasted=[i for i in p.timeline if i.id in ids]
        self.assertEqual([i.start for i in pasted],[8,8]); self.assertEqual(pasted[0].speed,2)
        self.assertEqual(len({i.link_id for i in pasted}),1); self.assertNotEqual(pasted[0].link_id,"pair")
        c=next(c for c in p.captions if c.id in caps); self.assertEqual(c.start,9); self.assertTrue(c.customize)
        second,_=clipboard.paste(p,payload,14); self.assertFalse(ids&second)
        self.assertNotEqual(p.item_by_id(next(iter(second))).link_id,pasted[0].link_id)

    def test_clipboard_locked_destination_is_atomic(self):
        p=self.project(); payload=clipboard.capture(p,{"v","a"},{"c"}); p.track_states["audio_1"]={"locked":True}; before=p.to_dict()
        with self.assertRaises(ValueError):clipboard.paste(p,payload,10)
        self.assertEqual(before,p.to_dict())

    def test_clipboard_overwrite_preserves_tails_and_media_source_times(self):
        p=self.project(); p.media[0].kind="video"; payload=clipboard.capture(p,{"v"},{"c"}); p.timeline[0].duration=12; p.captions[0].end=14
        ids,caps=clipboard.paste(p,payload,5)
        video=sorted([i for i in p.timeline if i.track=="video_1"],key=lambda i:i.start)
        self.assertEqual([(i.start,i.duration) for i in video],[(1,4),(5,3),(8,5)])
        self.assertEqual(video[-1].in_point,7)
        self.assertEqual(sorted((c.start,c.end) for c in p.captions),[(2,6),(6,7),(7,14)])

    def test_clipboard_new_project_creates_required_tracks_and_media(self):
        source=self.project(); source.add_track("video"); source.timeline[0].track="video_2"
        p=Project(); ids,_=clipboard.paste(p,clipboard.capture(source,{"v"},set()),0)
        clip=p.item_by_id(next(iter(ids))); self.assertEqual(clip.track,"video_2"); self.assertIsNotNone(p.media_by_id(clip.media_id))

    def test_cut_paste_shortcuts_undo_and_deliver_guard(self):
        w=self.window(); w.timeline.select_ids({"v","a"},"v"); w.timeline.viewport().setFocus()
        QTest.keyClick(w.timeline.viewport(),Qt.Key_X,Qt.ControlModifier); self.assertFalse(w.project.timeline)
        w.undo(); self.assertEqual(len(w.project.timeline),2); w.redo(); self.assertFalse(w.project.timeline)
        w.seek(7); w.timeline.viewport().setFocus(); QTest.keyClick(w.timeline.viewport(),Qt.Key_V,Qt.ControlModifier)
        self.assertEqual([i.start for i in w.project.timeline],[7,7]); w.undo(); self.assertFalse(w.project.timeline)
        set_page(w,1); before=w._history_key(w.project); w.timeline_clipboard("paste",True); self.assertEqual(before,w._history_key(w.project))

    def test_subtitle_clipboard_and_menu_and_text_edit_shortcuts(self):
        w=self.window(); w.timeline.select_captions({"c"},"c"); w.timeline_clipboard("copy",True); w.seek(8); w.timeline_clipboard("paste",True)
        self.assertTrue(any(c.start==8 for c in w.project.captions))
        menu=QMenu(); w.timeline.add_clipboard_actions(menu)
        self.assertEqual([a.text().split("\t")[0] for a in menu.actions()[:3]],["Cut","Copy","Paste"])
        w.add_title_object("Headline"); edit=w.inspector.title_text; edit.setPlainText("Keep this title"); edit.setFocus(); edit.selectAll()
        QTest.keyClick(edit,Qt.Key_C,Qt.ControlModifier); self.assertEqual(QApplication.clipboard().text(),"Keep this title")
        count=len(w.project.timeline); QTest.keyClick(edit,Qt.Key_X,Qt.ControlModifier); QTest.keyClick(edit,Qt.Key_V,Qt.ControlModifier)
        self.assertEqual(edit.toPlainText(),"Keep this title"); self.assertEqual(len(w.project.timeline),count)

    def test_scrub_speed_precision_and_integer_fields(self):
        self.assertGreater(scrub_delta(20,.02,1),scrub_delta(20,.2,1)*2)
        self.assertAlmostEqual(scrub_delta(20,.2,1,Qt.ShiftModifier),scrub_delta(20,.2,1)/10)
        for cls in (SafeDoubleSpinBox,SafeSpinBox):
            spin=cls(); spin.setRange(-10000,10000); spin.show(); line=spin.lineEdit(); self.app.processEvents()
            local=QPoint(10,10); origin=line.mapToGlobal(local)
            QTest.mousePress(line,Qt.LeftButton,pos=local)
            self.assertIsNotNone(spin._drag_start); self.assertEqual(line.cursor().shape(),Qt.BlankCursor)
            for _ in range(3):
                event=QMouseEvent(QEvent.MouseMove,QPointF(local+QPoint(30,0)),QPointF(origin+QPoint(30,0)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier)
                QApplication.sendEvent(line,event)
            self.assertGreater(spin.value(),90); QTest.mouseRelease(line,Qt.LeftButton,pos=local); self.assertIsNone(spin._drag_start)
            spin.close()

    def test_scrub_escape_and_double_click_typing(self):
        spin=SafeDoubleSpinBox(); spin.setRange(-1000,1000); spin.show(); self.app.processEvents(); line=spin.lineEdit()
        QTest.mousePress(line,Qt.LeftButton); QTest.keyClick(spin,Qt.Key_Escape); self.assertIsNone(spin._drag_start)
        QTest.mouseDClick(line,Qt.LeftButton); QTest.keyClicks(line,"123.45"); QTest.keyClick(line,Qt.Key_Return); self.app.processEvents()
        self.assertAlmostEqual(spin.value(),123.45); spin.close()

    def test_captured_cursor_is_recentered_on_each_native_drag_event(self):
        spin=SafeDoubleSpinBox(); spin.setRange(-10000,10000); line=spin.lineEdit(); spin.show(); self.app.processEvents()
        local=QPoint(10,10); origin=line.mapToGlobal(local)
        with patch("kinetic_cut.controls.QGuiApplication.platformName",return_value="windows"),patch("kinetic_cut.controls.QCursor.setPos") as warp,patch.object(line,"grabMouse"),patch.object(line,"releaseMouse"):
            QTest.mousePress(line,Qt.LeftButton,pos=local)
            for _ in range(2):QApplication.sendEvent(line,QMouseEvent(QEvent.MouseMove,QPointF(local+QPoint(10,0)),QPointF(origin+QPoint(10,0)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
            QTest.mouseRelease(line,Qt.LeftButton,pos=local)
            self.assertGreaterEqual(warp.call_count,3); self.assertTrue(all(call.args[0]==origin for call in warp.call_args_list))
        spin.close()

    def test_position_scrub_updates_preview_units_and_one_undo(self):
        w=self.window(); w.timeline.select_ids({"v"},"v"); row=dict(w.inspector.bindings)["position_x"]; line=row.spin.lineEdit()
        before=w.project.item_by_id("v").transform.x; history=len(w._history); local=QPoint(15,10); origin=line.mapToGlobal(local)
        QTest.mousePress(line,Qt.LeftButton,pos=local)
        for _ in range(3):QApplication.sendEvent(line,QMouseEvent(QEvent.MouseMove,QPointF(local+QPoint(20,0)),QPointF(origin+QPoint(20,0)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        QTest.mouseRelease(line,Qt.LeftButton,pos=local)
        self.assertGreater(abs(w.project.item_by_id("v").transform.x-before)*1080,50)
        self.assertEqual(len(w._history),history+1); w.undo(); self.assertAlmostEqual(w.project.item_by_id("v").transform.x,before)

    def test_seek_beyond_end_black_preview_and_duration_unchanged(self):
        w=self.window(); duration=w.project.duration; w.timeline.scrub_at(w.timeline.x_for_time(12)); w.timeline.scrub_timer.stop()
        self.assertGreater(w.project.playhead,duration); self.assertEqual(w.project.duration,duration)
        image=w.preview.grab().toImage(); center=w.preview.composition_rect().center().toPoint(); self.assertEqual(image.pixelColor(center).name(),"#000000")
        w.timeline._navigation_end=20; w.timeline._range(); w.timeline.horizontalScrollBar().setValue(w.timeline.horizontalScrollBar().maximum())
        w.timeline.start_scrub(w.timeline.viewport().width()-1)
        for _ in range(5):w.timeline.scroll_scrub()
        w.timeline.scrub_timer.stop(); self.assertGreater(w.project.playhead,20); self.assertEqual(w.project.duration,duration)

    def test_timeline_content_never_escapes_section_at_scroll_extremes(self):
        p=self.project(); p.video_tracks=[f"video_{n}" for n in range(1,8)]; p.ensure_track_model()
        p.timeline=[TimelineItem(f"v{n}","m",track,0,12) for n,track in enumerate(p.video_tracks)]
        t=TimelineWidget(); t.resize(850,330); t.set_project(p); t.show(); self.app.processEvents()
        with tempfile.TemporaryDirectory() as directory:
            thumb=QImage(80,45,QImage.Format_RGB32); thumb.fill(QColor("#ff00ff")); path=str(Path(directory)/"thumb.png"); thumb.save(path); p.media[0].thumbnail=path
            for value in (0,t.video_scroll.maximum()//2,t.video_scroll.maximum()):
                t.video_scroll.setValue(value); image=t.viewport().grab().toImage(); section=t.section_rect("video_1")
                videos=p.timeline; p.timeline=[]; baseline=t.viewport().grab().toImage(); p.timeline=videos
                for y in range(t.RULER_HEIGHT,image.height()):
                    if section.top()<=y<section.bottom():continue
                    for x in range(t.LABEL_WIDTH+5,image.width()-15):self.assertEqual(image.pixelColor(x,y),baseline.pixelColor(x,y),(value,x,y))
            t.viewport().grab().save("build/refinement-timeline.png")
        t.close()

    def test_empty_preview_stays_inside_canvas_when_panned(self):
        preview=PreviewCanvas(); preview.resize(600,340); preview.set_project(Project()); preview.view_pan=QPointF(95,15); preview.show(); self.app.processEvents()
        image=preview.grab().toImage(); frame=preview.composition_rect().adjusted(-2,-2,2,2)
        for y in range(image.height()):
            for x in range(image.width()):
                if not frame.contains(QPointF(x,y)):self.assertEqual(image.pixelColor(x,y).name(),"#191a1d")
        preview.grab().save("build/refinement-empty.png"); preview.close()

    def test_headline_wrap_geometry_uniform_scale_and_saved_profile(self):
        style=headline_style(); text="NoPixel 5 lore trailer (RP\nBegins tomorrow)"
        letters,backing=geometry(text,1080,"Arial",72); self.assertFalse(letters.isEmpty()); self.assertTrue(backing.boundingRect().contains(letters.boundingRect()))
        self.assertGreater(len(wrap_lines("x"*100,len,10)),1)
        p1,b1=paths(text,style,1080,1920); style.zoom_x=2; p2,b2=paths(text,style,1080,1920)
        self.assertAlmostEqual(b2.boundingRect().width(),b1.boundingRect().width()*2)
        p=Project(timeline=[TimelineItem("title","","video_1",0,5,role="title",title_text=text,title_style=style)])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"test.kcut"; p.save(path); loaded=Project.load(path); self.assertEqual(loaded.timeline[0].title_style.box_style,"headline")
            ass=Path(directory)/"test.ass"; write_ass(p,ass); content=ass.read_text(encoding="utf-8-sig"); self.assertEqual(content.count("Dialogue:"),2); self.assertIn("\\p1",content)

    def test_headline_inspector_and_shadow_axis_layout(self):
        w=self.window(); w.add_title_object("Headline"); self.app.processEvents()
        self.assertTrue(w.inspector.headline_controls.isVisible()); self.assertFalse(w.inspector.title_style_host.isVisible())
        w.inspector.headline_size.change(150); title=w.project.item_by_id(w.timeline.selected_id); self.assertEqual(title.title_style.zoom_x,1.5); self.assertEqual(title.title_style.zoom_y,1.5)
        w.add_title_object("Text"); self.app.processEvents(); self.assertTrue(w.inspector.title_style_host.isVisible()); self.assertFalse(w.inspector.headline_controls.isVisible())
        rows=dict(w.inspector.style_bindings); self.assertIs(rows["shadow_x"].parentWidget(),rows["shadow_y"].parentWidget())
        section=next(s for s in w.inspector.findChildren(InspectorSection) if s.toggle.text()=="Drop Shadow")
        self.assertIsNotNone(section.enabled_button); section.enabled_button.click(); self.assertFalse(w.inspector.style_target().shadow_enabled)
        self.assertFalse(w.windowIcon().isNull())

    def test_smaller_export_preserves_headline_proportions_without_editing_project(self):
        w=self.window(); w.add_title_object("Headline"); title=w.project.item_by_id(w.timeline.selected_id); text="A social headline\nTwo lines"
        title.title_text=text; source=paths(text,title.title_style,1080,1920)[1].boundingRect()
        w.delivery.sync_project_settings(); w.delivery.resolution.setCurrentIndex(1); output=w.delivery.output_project(); smaller=output.item_by_id(title.id)
        dest=paths(text,smaller.title_style,output.settings.width,output.settings.height)[1].boundingRect()
        self.assertAlmostEqual(dest.width()/source.width(),2/3,delta=.01); self.assertEqual(title.title_style.size,72)


if __name__=="__main__":unittest.main()
