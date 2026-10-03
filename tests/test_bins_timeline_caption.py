import copy,json,os,tempfile,time,unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict
from PIL import Image,ImageDraw
from PySide6.QtCore import Qt,QPoint,QPointF,QRectF,QEvent,QMimeData,QThreadPool
from PySide6.QtGui import QImage,QPainter,QMouseEvent,QFontDatabase
from PySide6.QtWidgets import QApplication,QFontComboBox,QComboBox
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,CaptionStyle,Crop
from kinetic_cut.media import make_thumbnail
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.widgets import PreviewCanvas
from kinetic_cut.workspace import PowerBins
from kinetic_cut import binclips
from kinetic_cut.visuals import draw_caption
from kinetic_cut.word_highlight import events
from kinetic_cut.icons import lucide_icon


class BinTimelineCaptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        for font in ("arial.ttf","arialbd.ttf","segoeui.ttf"):QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+font)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.directory=Path(self.temp.name); self.addCleanup(self.temp.cleanup); self.addCleanup(self.cleanup_widgets)
    def cleanup_widgets(self):
        QThreadPool.globalInstance().waitForDone(5000); self.app.processEvents()
        for widget in self.app.topLevelWidgets():widget.close(); widget.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
    def window(self):
        w=MainWindow(); w.resize(1680,1000); w.show(); self.app.processEvents(); return w
    def image_media(self,name="logo"):
        path=self.directory/(name+".png"); image=Image.new("RGBA",(400,200),(255,255,255,0)); ImageDraw.Draw(image).rectangle((100,75,299,124),fill=(0,255,0,255)); image.save(path)
        return MediaItem(name,str(path),"image",name,5,400,200)
    def motion(self,t,point,global_point=None):
        local=QPointF(point); global_point=global_point or t.viewport().mapToGlobal(point)
        QApplication.sendEvent(t.viewport(),QMouseEvent(QEvent.MouseMove,local,QPointF(global_point),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
    def test_transparent_thumbnail_and_icon_preserve_aspect_on_black(self):
        media=self.image_media(); thumb=make_thumbnail(media.path,"image"); image=Image.open(thumb)
        self.assertEqual(image.mode,"RGBA"); self.assertEqual(image.size,(320,160)); self.assertEqual(image.getpixel((0,0))[3],0)
        w=self.window(); pixels=w.media_panel.media_icon(media).pixmap(110,65).toImage(); green=[(x,y) for x in range(110) for y in range(65) if pixels.pixelColor(x,y).green()>200 and pixels.pixelColor(x,y).red()<20]
        width=max(x for x,y in green)-min(x for x,y in green); height=max(y for x,y in green)-min(y for x,y in green)
        self.assertAlmostEqual(width/height,4,delta=.5); self.assertLess(pixels.pixelColor(0,0).red(),20)
    def test_rename_is_display_only_and_open_location_uses_parent(self):
        w=self.window(); media=self.image_media(); w.project.media=[media]; w.refresh_media(); item=w.media_panel.grid.item(0)
        with patch("kinetic_cut.workspace.QInputDialog.getText",return_value=("xQc LOGO",True)):w.media_panel.rename_media(item)
        self.assertEqual(media.name,"xQc LOGO"); self.assertTrue(Path(media.path).exists())
        with patch("kinetic_cut.workspace.QDesktopServices.openUrl",return_value=True) as open_url:w.media_panel.open_file_location(w.media_panel.grid.item(0)); self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()),self.directory)
        panel=w.media_panel; panel.power=PowerBins(self.directory/"bins.json"); panel.power.add(media,"Master"); panel.folder="Master"; panel.refresh()
        with patch("kinetic_cut.workspace.QInputDialog.getText",return_value=("Saved logo",True)):panel.rename_media(panel.grid.item(0))
        self.assertEqual(PowerBins(self.directory/"bins.json").data["media"][0]["media"]["name"],"Saved logo"); self.assertEqual(media.name,"xQc LOGO")
    def test_power_bin_roundtrip_preserves_trim_effects_transform_and_links(self):
        media=MediaItem("m","source.mp4","video","source.mp4",30,1920,1080,60,True)
        p=Project(media=[media]); v=TimelineItem("v","m","video_1",7,4,2,group_id="g",crop=Crop(.1,.2,.7,.6),opacity=74,effects=[{"name":"Gaussian Blur","horizontal":9}]); v.transform.x=.3; v.transform.scale=1.6
        a=TimelineItem("a","m","audio_1",7,4,2,group_id="g",gain_db=-7,pan=.25); p.timeline=[v,a]
        preset=binclips.asset(binclips.snapshot(p,{"v","a"},set(),"v")); bins=PowerBins(self.directory/"bins.json"); bins.add(preset,"Master"); v.transform.x=.9
        saved=MediaItem(**PowerBins(self.directory/"bins.json").data["media"][0]["media"]); target=Project(); track=target.add_track("video"); ids,_=binclips.restore(target,saved,track,12)
        clip=next(i for i in target.timeline if i.track==track); audio=next(i for i in target.timeline if i.track=="audio_1")
        self.assertEqual(clip.start,12); self.assertEqual(clip.in_point,2); self.assertEqual(clip.duration,4); self.assertEqual(clip.transform.x,.3); self.assertEqual(clip.effects[0]["horizontal"],9); self.assertEqual(clip.opacity,74); self.assertEqual(clip.crop.y,.2); self.assertEqual(audio.gain_db,-7); self.assertEqual(len(target.linked_items(clip)),2)
        self.assertEqual(p.timeline[0].start,7); self.assertNotIn("v",ids)
    def test_power_bin_variants_and_caption_styles_survive_move_and_reload(self):
        p=Project(captions=[Caption("c",3,6,"Reusable caption")]); p.subtitle_style.color="#123456"
        one=binclips.asset(binclips.snapshot(p,set(),{"c"})); two=copy.deepcopy(one); two.id="other"; two.name="Second preset"
        bins=PowerBins(self.directory/"bins.json"); bins.add_folder("Master/Other"); bins.add(one,"Master"); bins.add(two,"Master"); bins.move(one,"Master","Master/Other"); self.assertEqual(len(bins.data["media"]),2)
        target=Project(); _,ids=binclips.restore(target,one,"video_1",10); caption=target.captions[0]
        self.assertEqual((caption.start,caption.end,caption.style.color),(10,13,"#123456")); self.assertTrue(caption.customize)
    def test_drag_to_power_bin_restores_original_before_drop(self):
        w=self.window(); m=self.image_media(); w.project.media=[m]; clip=TimelineItem("v",m.id,"video_1",1,3); clip.transform.x=.31; w.project.timeline=[clip]; w.model_changed(); self.app.processEvents()
        panel=w.media_panel; panel.power=PowerBins(self.directory/"bins.json"); panel.rebuild_tree(); t=w.timeline; origin=t.item_rect(clip).center().toPoint(); original=asdict(clip)
        QTest.mousePress(t.viewport(),Qt.LeftButton,pos=origin); self.motion(t,origin+QPoint(50,0)); self.assertTrue(t.move_preview)
        class Drag:
            def __init__(self,*_):pass
            def setMimeData(self,mime):self.mime=mime
            def setPixmap(self,pix):pass
            def setHotSpot(self,point):pass
            def exec(self,action):
                assert asdict(clip)==original and not t.move_preview
                assert panel.store_timeline_drop(self.mime,"Master")
                return Qt.CopyAction
        global_pos=panel.tree.viewport().mapToGlobal(QPoint(10,10))
        with patch("kinetic_cut.workspace.QDrag",Drag):self.motion(t,t.viewport().mapFromGlobal(global_pos),global_pos)
        self.assertEqual(asdict(clip),original); self.assertEqual(len(panel.power.data["media"]),1); self.assertFalse(t.drag_mode)
        w.set_project(Project()); panel.folder="Master"; panel.refresh(); saved_id=panel.grid.item(0).data(Qt.UserRole); w.add_media_to_track(saved_id,"video_1",0)
        self.assertEqual(w.project.timeline[0].transform.x,.31); self.assertEqual(w.project.timeline[0].duration,3)
    def test_locked_tracks_reject_media_titles_and_saved_clips(self):
        w=self.window(); m=self.image_media(); audio=MediaItem("a","audio.wav","audio","audio",5); w.project.media=[m,audio]
        for track in ("video_1","audio_1"):w.project.track_states[track]["locked"]=True
        w.add_media_to_track(m.id,"video_1",0); w.add_media_to_track(audio.id,"video_1",0); w.add_title_object("Headline"); self.assertFalse(w.project.timeline)
        source=Project(media=[m],timeline=[TimelineItem("c",m.id,"video_1",0,3)]); preset=binclips.asset(binclips.snapshot(source,{"c"},set())); w.project.media.append(preset); w.add_media_to_track(preset.id,"video_1",0); self.assertFalse(w.project.timeline)
    def test_edge_trim_snaps_all_media_types_and_toggle_disables(self):
        for kind in ("image","video","audio","title","caption"):
            with self.subTest(kind=kind):
                t=TimelineWidget(); t.resize(900,440); m=MediaItem("m","unused","image" if kind=="title" else kind,"m",20,1920,1080); p=Project(media=[m]); track="audio_1" if kind=="audio" else "video_1"
                clip=TimelineItem("clip","m",track,0,2,role="title" if kind=="title" else "normal"); p.timeline=[clip,TimelineItem("edge","m",p.add_track("video"),0,3)]
                if kind=="caption":p.timeline=p.timeline[1:]; p.captions=[Caption("cap",0,2,"Text")]
                t.set_project(p); t.show(); self.app.processEvents(); rect=t.caption_rect(p.captions[0]) if kind=="caption" else t.item_rect(clip); point=QPoint(round(rect.right()-2),round(rect.center().y()))
                QTest.mousePress(t.viewport(),Qt.LeftButton,pos=point); self.motion(t,QPoint(round(t.x_for_time(3)+2),point.y()))
                end=p.captions[0].end if kind=="caption" else clip.start+clip.duration; self.assertEqual(end,3)
                t.cancel_drag(); t.setProperty("snapping",False); QTest.mousePress(t.viewport(),Qt.LeftButton,pos=point); self.motion(t,QPoint(round(t.x_for_time(3)+2),point.y())); end=p.captions[0].end if kind=="caption" else clip.start+clip.duration; self.assertNotEqual(end,3); t.cancel_drag(); t.close()
    def test_arrow_frame_steps_and_loop_respects_toggle(self):
        w=self.window(); w.project.timeline=[TimelineItem("v","","video_1",0,2)]; w.model_changed(); w.seek(1); t=w.timeline
        QTest.keyClick(t.viewport(),Qt.Key_Right); self.assertAlmostEqual(w.project.playhead,61/60); QTest.keyClick(t.viewport(),Qt.Key_Left); self.assertEqual(w.project.playhead,1)
        transport=w.transport; w.loop_button.click(); self.assertTrue(transport.loop)
        transport.playing=True; transport.origin=1.9; transport.started=time.monotonic()-.3; transport.tick(); self.assertTrue(transport.playing); self.assertLess(transport.position,.5)
        w.loop_button.click(); transport.origin=1.9; transport.started=time.monotonic()-.3; transport.tick(); self.assertFalse(transport.playing); self.assertEqual(transport.position,2)
    def test_lock_icons_cut_split_label_and_toggle_order(self):
        w=self.window(); self.assertIn("Cut/Split",w.blade_tool.toolTip()); self.assertLess(w.snap_tool.mapToGlobal(QPoint()).x(),w.link_toggle.mapToGlobal(QPoint()).x())
        with patch("kinetic_cut.timeline.lucide_icon",wraps=lucide_icon) as icons:w.timeline.viewport().grab(); self.assertIn("lock-open",[call.args[0] for call in icons.call_args_list])
        w.project.track_states["video_1"]["locked"]=True
        with patch("kinetic_cut.timeline.lucide_icon",wraps=lucide_icon) as icons:w.timeline.viewport().grab(); self.assertIn("lock",[call.args[0] for call in icons.call_args_list])
        self.assertFalse(w.timeline._razor_cursor().pixmap().isNull())
    def test_hidden_images_titles_subtitles_and_topmost_transform_overlay(self):
        m=self.image_media(); p=Project(media=[m],timeline=[TimelineItem("v",m.id,"video_1",0,5)]); canvas=PreviewCanvas(); canvas.resize(720,600); canvas.set_project(p); canvas.show(); self.app.processEvents(); self.assertEqual(len(canvas._visible_items()),1)
        p.track_states["video_1"]["visible"]=False; self.assertFalse(canvas._visible_items()); p.timeline[0].role="title"; p.timeline[0].title_text="Hidden title"; p.timeline[0].title_style=CaptionStyle(); p.captions=[Caption("c",0,5,"Hidden caption")]; p.track_states["subtitle_1"]={"visible":False}; canvas.grab(); self.assertFalse(canvas.text_rects)
        p.timeline[0].role="normal"; p.track_states["video_1"]["visible"]=True; p.timeline.append(TimelineItem("upper",m.id,p.add_track("video"),0,5)); canvas.selected_item_id="v"; operations=[]
        original=canvas._draw_transform_box
        # A Mock records its QPainter argument and keeps it alive after the
        # paint event / QWidget teardown, causing a native crash during GC.
        # Record only the draw order, never the native painter wrapper.
        def record_overlay(*args):operations.append("overlay"); original(*args)
        with patch.object(canvas,"_draw_transform_box",new=record_overlay):canvas.grab()
        self.assertEqual(operations,["overlay"])
    def test_caption_font_dropdown_and_new_defaults_and_animation(self):
        w=self.window(); self.assertEqual(w.project.subtitle_style.color,"#55ffff"); self.assertEqual(w.project.subtitle_style.outline,"#000000")
        media=MediaItem("m","unused.mp4","video","m",5,1920,1080); w.project.media=[media]; w.project.timeline=[TimelineItem("v","m","video_1",0,5,role="content")]
        def inspect(dialog):
            from kinetic_cut.caption_fonts import CaptionFontCombo
            dialog.show(); self.app.processEvents(); font=dialog.findChild(CaptionFontCombo,"captionFontPicker"); self.assertFalse(font.isEditable()); self.assertGreater(font.count(),1)
            QTest.mouseClick(font,Qt.LeftButton,pos=font.rect().center()); self.app.processEvents(); self.assertTrue(font.view().isVisible()); font.hidePopup()
            self.assertTrue(any(combo.findText("word highlight")>=0 for combo in dialog.findChildren(QComboBox))); dialog.close(); return 0
        with patch("kinetic_cut.ui.QDialog.exec",inspect):w.generate_captions()
    def test_word_highlight_advances_and_single_word_has_no_card(self):
        p=Project(captions=[Caption("c",0,3,"One two three")]); p.subtitle_style.animation="word highlight"; p.subtitle_style.highlight="#ff00aa"; p.subtitle_style.shadow_enabled=False; p.subtitle_style.outline_width=0
        frames=[]
        for at in (.1,1.1,2.1):
            p.playhead=at; image=QImage(540,960,QImage.Format_RGB32); image.fill(Qt.black); painter=QPainter(image); draw_caption(painter,p,p.captions[0],QRectF(0,0,540,960)); painter.end()
            xs=[x for x in range(540) for y in range(650,870) if image.pixelColor(x,y).red()>200 and image.pixelColor(x,y).green()<20]; self.assertTrue(xs); frames.append(sum(xs)/len(xs))
        self.assertLess(frames[0],frames[1]); self.assertLess(frames[1],frames[2]); exported=events(p,p.captions[0],"C0"); self.assertEqual(sum(line.startswith("Dialogue: 1,") for line in exported),3)
        p.captions[0].text="One"; self.assertFalse(any(line.startswith("Dialogue: 1,") for line in events(p,p.captions[0],"C0")))
