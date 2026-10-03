import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QFontDatabase,QMouseEvent,QColor
from PySide6.QtWidgets import QApplication,QListWidget,QListWidgetItem,QAbstractItemView,QDialogButtonBox
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,Crop
from kinetic_cut.emoji import catalogue,segments,fonts,image,EmojiTextEdit,EmojiPicker
from kinetic_cut.headline import headline_style
from kinetic_cut import attributes,clipboard
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.workspace import BinMediaList,PowerBins,set_page


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        for f in ("arial.ttf","arialbd.ttf","segoeui.ttf","segoeuib.ttf"):QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+f)
    def setUp(self):self.addCleanup(self.cleanup_widgets)
    def cleanup_widgets(self):
        # Closed Qt dialogs can retain signal/Python cycles. Destroy test-only
        # widgets while QApplication is alive, not during interpreter teardown.
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().waitForDone(5000)
        self.app.processEvents()
        from PySide6.QtWidgets import QWidget
        for widget in self.app.topLevelWidgets():
            # Native popup wrappers can already have been demoted to QObject
            # during deferred destruction; only live widgets can be closed.
            if isinstance(widget,QWidget):widget.close(); widget.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
    def window(self):
        w=MainWindow(); w.show(); self.app.processEvents(); self.addCleanup(w.close); return w
    def test_every_catalogue_sequence_has_single_google_colour_glyph(self):
        import uharfbuzz as hb
        font,tt=fonts(); data=tt["CBDT"].strikeData[0]; self.assertEqual(len(catalogue()[0]),3953)
        for seq,name,_ in catalogue()[0]:
            b=hb.Buffer(); b.add_str(seq); b.guess_segment_properties(); hb.shape(font,b)
            self.assertEqual(len([i for i in b.glyph_infos if i.codepoint and tt.getGlyphName(i.codepoint) in data]),1,name)
    def test_colour_emoji_and_joined_sequence_segmentation(self):
        text="Hello 🥹 👩🏽‍💻 🇬🇧 👨‍👩‍👧‍👦!"; parts=segments(text)
        self.assertEqual([t for t,emoji in parts if emoji],["🥹","👩🏽‍💻","🇬🇧","👨‍👩‍👧‍👦"])
        im=image("🥹"); colors={im.pixelColor(x,y).name() for x in range(im.width()) for y in range(im.height()) if im.pixelColor(x,y).alpha()>200}
        self.assertGreater(len(colors),30)
    def test_picker_search_inserts_at_caret_and_is_undoable(self):
        edit=EmojiTextEdit(); edit.setPlainText("Hello !"); cursor=edit.textCursor(); cursor.setPosition(6); edit.setTextCursor(cursor); edit.show()
        edit.pick_emoji(); picker=edit._picker; picker.search.setText("face holding back tears"); self.assertEqual(picker.grid.count(),1)
        picker.choose(picker.grid.item(0)); self.assertEqual(edit.toPlainText(),"Hello 🥹!"); edit.undo(); self.assertEqual(edit.toPlainText(),"Hello !"); edit.close()
    def test_rich_text_paints_google_emoji_and_preserves_unicode_copy_undo(self):
        edit=EmojiTextEdit(); edit.resize(520,160); edit.setStyleSheet("background:#222;color:white;font-size:22px"); original="Hello 🥹 👩🏽‍💻 🇬🇧"; edit.setPlainText(original); edit.show(); self.app.processEvents()
        pixels=edit.viewport().grab().toImage(); coloured=sum(max(c.red(),c.green(),c.blue())-min(c.red(),c.green(),c.blue())>80 for c in (pixels.pixelColor(x,y) for x in range(pixels.width()) for y in range(pixels.height())))
        self.assertGreater(coloured,150); self.assertEqual(edit.toPlainText(),original)
        edit.selectAll(); edit.copy(); self.assertEqual(self.app.clipboard().text(),original)
        edit.cut(); self.assertEqual(edit.toPlainText(),""); edit.undo(); self.assertEqual(edit.toPlainText(),original); edit.close()
    def test_picker_grid_paints_colour_artwork_and_editor_has_icon(self):
        edit=EmojiTextEdit(); self.assertFalse(edit.emoji_button.icon().isNull()); edit.pick_emoji(); picker=edit._picker; self.app.processEvents()
        rect=picker.grid.visualItemRect(picker.grid.item(0)); self.assertGreater(rect.width(),30); self.assertGreater(rect.height(),30)
        pixels=picker.grid.viewport().grab(rect).toImage(); coloured=sum(max(c.red(),c.green(),c.blue())-min(c.red(),c.green(),c.blue())>80 for c in (pixels.pixelColor(x,y) for x in range(pixels.width()) for y in range(pixels.height())))
        self.assertGreater(coloured,100); picker.close(); edit.close()
    def test_headline_controls_default_center_colour_duration_and_undo(self):
        w=self.window(); w.add_title_object("Headline"); item=w.project.item_by_id(w.timeline.selected_id); inspector=w.inspector
        self.assertEqual([inspector.headline_positions[a].spin.value() for a in ("X","Y")],[540,960])
        inspector.headline_duration.change(7.25); self.assertEqual(item.duration,7.25); w.undo(); self.assertEqual(w.project.item_by_id(item.id).duration,5)
        inspector.headline_positions["X"].change(300); self.assertAlmostEqual(w.project.item_by_id(item.id).title_style.position_x,300/1080)
        with patch("kinetic_cut.properties.QColorDialog.getColor",return_value=QColor("#3388cc")):inspector.headline_color.click()
        self.assertEqual(w.project.item_by_id(item.id).title_style.color,"#3388cc")
        self.assertEqual(w.windowTitle(),"Kinetic Cut")
    def test_scrubber_snaps_to_media_and_subtitle_edges_and_can_disable(self):
        t=TimelineWidget(); p=Project(timeline=[TimelineItem("v","","video_1",2,3)],captions=[Caption("c",7,9,"Test")]); t.resize(900,360); t.set_project(p)
        for edge in (2,5,7,9):t.scrub_at(t.x_for_time(edge)+4); self.assertEqual(p.playhead,edge)
        t.setProperty("snapping",False); t.scrub_at(t.x_for_time(5)+4); self.assertNotEqual(p.playhead,5); t.close()
    def test_media_pool_rubber_band_selects_multiple_items(self):
        w=self.window(); grid=BinMediaList(w.media_panel); grid.setViewMode(QListWidget.IconMode); grid.setMovement(QListWidget.Static); grid.setGridSize(__import__("PySide6.QtCore",fromlist=["QSize"]).QSize(100,90)); grid.resize(360,300)
        for i in range(3):item=QListWidgetItem(str(i)); item.setData(Qt.UserRole+1,"media"); grid.addItem(item)
        grid.show(); self.app.processEvents(); start=QPoint(325,255); end=QPoint(5,5)
        QTest.mousePress(grid.viewport(),Qt.LeftButton,pos=start); QTest.mouseMove(grid.viewport(),end,30); QTest.mouseRelease(grid.viewport(),Qt.LeftButton,pos=end)
        self.assertEqual(len(grid.selectedItems()),3); grid.close()
    def test_batch_drag_payload_ignores_folders_and_places_consecutively(self):
        w=self.window(); w.project.media=[MediaItem("one","one.mp4","video","1",2,1920,1080),MediaItem("two","two.mp4","video","2",3,1920,1080)]; w.refresh_media()
        grid=w.media_panel.grid
        for n in range(grid.count()):grid.item(n).setSelected(True)
        folder=QListWidgetItem("folder"); folder.setData(Qt.UserRole+1,"folder"); grid.addItem(folder); folder.setSelected(True)
        with patch("kinetic_cut.workspace.QDrag") as drag:
            grid.startDrag(Qt.CopyAction); mime=drag.return_value.setMimeData.call_args.args[0]; self.assertEqual(json.loads(bytes(mime.data("application/x-kinetic-media-ids"))),["one","two"])
        with patch.object(w.transport,"sync"),patch.object(w,"start_worker"):
            w.add_media_batch(["one","two"],"video_1",4)
        self.assertEqual([(i.start,i.duration) for i in w.project.timeline],[(4,2),(6,3)]); w.undo(); self.assertFalse(w.project.timeline)
        grid.clearSelection(); folder=QListWidgetItem("folder"); folder.setData(Qt.UserRole+1,"folder"); grid.addItem(folder); folder.setSelected(True)
        with patch("kinetic_cut.workspace.QDrag") as drag:grid.startDrag(Qt.CopyAction); drag.assert_not_called()
    def test_batch_remove_pool_preserves_used_media_and_powerbin_files(self):
        w=self.window(); w.project.media=[MediaItem("one","one.png","image","1"),MediaItem("two","two.png","image","2")]; w.project.timeline=[TimelineItem("v","one","video_1",0,5)]; w.refresh_media()
        for n in range(w.media_panel.grid.count()):w.media_panel.grid.item(n).setSelected(True)
        w.media_panel.remove_selected(); self.assertEqual([m.id for m in w.project.media],["one"])
        with tempfile.TemporaryDirectory() as directory:
            panel=w.media_panel; panel.power=PowerBins(Path(directory)/"bins.json"); panel.power.add_folder("Master/Test"); panel.power.add(w.project.media[0],"Master/Test"); panel.folder="Master/Test"; panel.refresh(); panel.grid.item(0).setSelected(True); panel.remove_selected(); self.assertFalse(panel.power.data["media"]); self.assertEqual(len(w.project.timeline),1)
    def test_attribute_dialog_defaults_off_and_master_selects_compatible_fields(self):
        dialog=attributes.PasteAttributesDialog("Source","Target","video"); self.assertFalse(dialog.selected()); self.assertFalse(dialog.buttons.button(QDialogButtonBox.Apply).isEnabled())
        dialog.master.click(); self.assertEqual(dialog.selected(),{key for _,key in attributes.VIDEO}); dialog.master.click(); self.assertFalse(dialog.selected()); dialog.close()
    def test_attribute_group_toggles_follow_individual_properties(self):
        dialog=attributes.PasteAttributesDialog("Source","Target","video"); zoom=dialog.groups[0][0]
        dialog.checks["scale_x"].setChecked(True); self.assertEqual(zoom.checkState(),Qt.PartiallyChecked)
        dialog.checks["scale_y"].setChecked(True); self.assertEqual(zoom.checkState(),Qt.Checked)
        zoom.click(); self.assertFalse(dialog.selected()); dialog.close()
    def test_video_attributes_preserve_unselected_fields_and_copy_exact_crop_pixels(self):
        p=Project(media=[MediaItem("m","m.png","image","m",0,1920,1080),MediaItem("n","n.png","image","n",0,3840,2160)])
        source=TimelineItem("s","m","video_1",0,3,crop=Crop(.1,0,.8,1)); source.transform.x=.7; source.transform.scale=2
        target=TimelineItem("t","n","video_1",5,2); p.timeline=[source,target]
        raw=attributes.source_for(clipboard.capture(p,{"s"},set()),"video"); attributes.apply(p,raw,[target],"video",{"position","crop_left"})
        self.assertEqual(target.transform.x,.7); self.assertEqual(target.transform.scale,1); self.assertEqual(target.start,5); self.assertEqual(target.duration,2); self.assertAlmostEqual(target.crop.x*3840,192)
    def test_audio_and_text_attribute_type_safety_and_track_style_independence(self):
        p=Project(timeline=[TimelineItem("a","","audio_1",0,2,gain_db=-9,pan=.3)],captions=[Caption("s",0,2,"Source"),Caption("t",3,4,"Keep text")]); p.subtitle_style.color="#cc3366"
        payload=clipboard.capture(p,{"a"},{"s"}); self.assertIsNone(attributes.source_for(payload,"video"))
        target=p.captions[1]; raw=attributes.source_for(payload,"text"); raw["style"]["color"]="#123456"; attributes.apply(p,raw,[target],"text",{"color"})
        self.assertEqual(target.text,"Keep text"); self.assertEqual(target.style.color,"#123456"); self.assertEqual(p.subtitle_style.color,"#cc3366"); self.assertTrue(target.customize)
        p.track_states["subtitle_1"]={"locked":True}
        with self.assertRaises(ValueError):attributes.apply(p,raw,[target],"text",{"color"})
    def test_paste_attributes_mismatched_type_does_not_open_dialog(self):
        w=self.window(); w.project.timeline=[TimelineItem("v","","video_1",0,2),TimelineItem("a","","audio_1",0,2)]; w.timeline.set_project(w.project); clipboard.put(clipboard.capture(w.project,{"a"},set())); w.timeline.select_ids({"v"},"v")
        with patch("kinetic_cut.attributes.PasteAttributesDialog") as dialog:w.paste_attributes(); dialog.assert_not_called()
    def drag_setup(self):
        t=TimelineWidget(); t.resize(950,500); p=Project(timeline=[TimelineItem("v","","video_1",0,2)]); t.set_project(p); t.show(); self.app.processEvents(); self.addCleanup(t.close); return t,p
    def move(self,t,pos):
        event=QMouseEvent(QEvent.MouseMove,QPointF(pos),QPointF(t.viewport().mapToGlobal(pos)),Qt.NoButton,Qt.LeftButton,Qt.AltModifier); QApplication.sendEvent(t.viewport(),event)
    def test_alt_drag_is_ghost_until_release_and_escape_is_nonmutating(self):
        t,p=self.drag_setup(); origin=t.item_rect(p.timeline[0]).center().toPoint(); QTest.mousePress(t.viewport(),Qt.LeftButton,Qt.AltModifier,pos=origin); self.move(t,origin+QPoint(200,0))
        self.assertEqual(len(p.timeline),1); self.assertEqual(p.timeline[0].start,0); self.assertEqual(len(t.move_preview),1)
        QTest.keyClick(t.viewport(),Qt.Key_Escape); self.assertFalse(t.move_preview); self.assertEqual(len(p.timeline),1)
        QTest.mousePress(t.viewport(),Qt.LeftButton,Qt.AltModifier,pos=origin); self.move(t,origin+QPoint(200,0)); QTest.mouseRelease(t.viewport(),Qt.LeftButton,Qt.AltModifier,pos=origin+QPoint(200,0)); self.assertEqual(len(p.timeline),2)
    def test_provisional_layer_appears_disappears_then_commits_only_on_drop(self):
        t,p=self.drag_setup(); origin=t.item_rect(p.timeline[0]).center().toPoint(); QTest.mousePress(t.viewport(),Qt.LeftButton,Qt.AltModifier,pos=origin)
        pos=QPoint(origin.x()+180,round(t.track_rect("video_1").top()-20)); self.move(t,pos); self.assertEqual(t.provisional_track,"__new_video"); self.assertEqual(len(p.video_tracks),1); self.assertEqual(len(t.display_tracks("video")),2)
        self.move(t,origin+QPoint(180,0)); self.assertEqual(t.provisional_track,""); self.assertEqual(len(p.video_tracks),1)
        self.move(t,pos); QTest.mouseRelease(t.viewport(),Qt.LeftButton,Qt.AltModifier,pos=pos); self.assertEqual(len(p.video_tracks),2); self.assertTrue(any(i.track=="video_2" for i in p.timeline)); self.assertFalse(any(k.startswith("__new_") for k in p.track_states))


if __name__=="__main__":unittest.main()
