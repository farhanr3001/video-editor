import copy,tempfile,unittest,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QEventLoop,QTimer,QMimeData,QUrl,QThreadPool
from PySide6.QtGui import QImage,QMouseEvent,QWheelEvent,QDragEnterEvent,QDropEvent,QDragLeaveEvent,QFontDatabase
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,CaptionStyle
from kinetic_cut.timeline_actions import delete_gaps,aligned_linked_av,keep_audio_ranges,complement
from kinetic_cut.profanity import censor_text,contains_curse
# Initialize native Qt SVG bindings before the speech-service sys.modules mock.
# Restoring that mock must not unload/reimport a native PySide extension.
from kinetic_cut.icons import resource_path


class NewActionModelTests(unittest.TestCase):
    def story(self):
        p=Project(); p.add_track("video"); p.add_track("video"); p.add_track("video"); p.add_track("audio")
        p.media=[MediaItem("movie","movie.mp4","video","Movie",30,400,200,60,True),MediaItem("logo","logo.png","image","Logo",5,400,200)]
        for n,start in enumerate([0,8,18]):
            for lane in p.video_tracks[:3]+["audio_1"]:
                p.timeline.append(TimelineItem(f"{n}-{lane}","movie",lane,start,5,group_id=str(n),role="source_audio" if lane=="audio_1" else "normal"))
        p.timeline += [TimelineItem("logo","logo","video_4",0,23),TimelineItem("sfx","movie","audio_2",10,1,role="sfx")]
        p.captions=[Caption("caption",9,11,"Some words")]; return p
    def test_delete_gaps_ignores_long_logo_and_preserves_later_offsets(self):
        p=self.story(); removed,gaps=delete_gaps(p)
        self.assertEqual(gaps,[(5,8),(13,18)]); self.assertEqual(removed,8)
        for lane in p.video_tracks[:3]+["audio_1"]:self.assertEqual([i.start for i in p.timeline if i.track==lane],[0,5,10])
        self.assertEqual(p.item_by_id("sfx").start,7); self.assertEqual(p.item_by_id("logo").duration,15)
        self.assertEqual((p.captions[0].start,p.captions[0].end),(6,8)); self.assertEqual(delete_gaps(p),(0.,[]))
    def test_delete_gaps_locked_track_is_atomic(self):
        p=self.story(); p.track_states["video_4"]["locked"]=True; before=p.to_dict()
        with self.assertRaises(ValueError):delete_gaps(p)
        self.assertEqual(p.to_dict(),before)
    def test_gap_anchor_includes_later_normal_clips_after_first_content_clip(self):
        p=self.story(); p.item_by_id("0-video_1").role="content"
        self.assertEqual(delete_gaps(p)[0],8)
    def test_gap_does_not_erase_sound_effect_in_gap(self):
        p=self.story(); p.item_by_id("sfx").start=6
        removed,gaps=delete_gaps(p); self.assertEqual(gaps,[(5,6),(7,8),(13,18)])
        self.assertEqual(p.item_by_id("sfx").duration,1)
    def test_audio_cut_keeps_video_and_other_clips_fixed(self):
        p=self.story(); audio=p.item_by_id("1-audio_1"); audio.speed=2; audio.in_point=4; before=copy.deepcopy(p.timeline)
        ids=keep_audio_ranges(p,audio,[(0,1),(2,4),(4.5,5)])
        clips=[p.item_by_id(id) for id in ids]; self.assertEqual([(i.start,i.duration,i.in_point) for i in clips],[(8,1,4),(10,2,8),(12.5,.5,13)])
        self.assertTrue(all(i.link_id=="" for i in clips))
        self.assertEqual([i for i in p.timeline if i.id not in ids],[i for i in before if i.id!=audio.id])
    def test_silence_local_pack_keeps_links_trims_speed_and_outside_timing(self):
        p=self.story(); audio=p.item_by_id("1-audio_1")
        for item in p.linked_items(audio):item.speed=2; item.in_point=3; item.transform.x=.3
        keep_audio_ranges(p,audio,[(1,2),(3,5)],True)
        for lane in p.video_tracks[:3]+["audio_1"]:
            clips=sorted((i for i in p.timeline if i.track==lane),key=lambda i:i.start)
            self.assertEqual([i.start for i in clips],[0,8,9,18]); self.assertEqual([i.in_point for i in clips[1:3]],[5,9])
            self.assertEqual([i.transform.x for i in clips[1:3]],[.3,.3])
        self.assertEqual(len(p.linked_items(next(i for i in p.timeline if i.start==8))),4)
        self.assertEqual(p.item_by_id("sfx").start,10)
    def test_silence_requires_aligned_unlocked_av(self):
        p=self.story(); audio=p.item_by_id("1-audio_1"); audio.link_id=""
        with self.assertRaisesRegex(ValueError,"linked"):aligned_linked_av(p,audio)
        audio.link_id=None; p.item_by_id("1-video_1").duration=4
        with self.assertRaisesRegex(ValueError,"same timeline"):aligned_linked_av(p,audio)
        p.item_by_id("1-video_1").duration=5; p.track_states["video_1"]["locked"]=True
        with self.assertRaisesRegex(ValueError,"Unlock"):aligned_linked_av(p,audio)
    def test_censor_preserves_punctuation_case_and_innocent_substrings(self):
        self.assertEqual(censor_text("Fuck, SHIT! class Scunthorpe assess."),"F***, SH**! class Scunthorpe assess.")
        self.assertTrue(contains_curse("(fucking)")); self.assertFalse(contains_curse("classic assignment"))
    def test_cut_recognition_requires_real_word_timestamps(self):
        from kinetic_cut.captions import transcribe,CaptionBackendError
        class Model:
            def __init__(self,*a,**kw):pass
            def transcribe(self,*a,**kw):return [SimpleNamespace(start=0,end=2,text="Oh shit",words=None)],SimpleNamespace(duration=2)
        with patch.dict(sys.modules,{"faster_whisper":SimpleNamespace(WhisperModel=Model)}):
            with self.assertRaises(CaptionBackendError):transcribe("none",{},require_word_timestamps=True)
    def test_cut_ranges_merge_and_clip_to_duration(self):
        self.assertEqual(complement(10,[(-2,1),(2,3),(2.5,4),(9,20)]),[(1,2),(4,9)])


class NewActionUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        for font in ("arial.ttf","arialbd.ttf","segoeui.ttf"):QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+font)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.mime=None
    def tearDown(self):
        if hasattr(self,"w"):self.app.sendEvent(self.w.timeline.viewport(),QDragLeaveEvent())
        QThreadPool.globalInstance().waitForDone(10000); self.wait(80); self.app.clipboard().clear()
        for widget in self.app.topLevelWidgets():widget.close(); widget.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.wait(20); self.temp.cleanup()
    def wait(self,ms=100):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def window(self):
        from kinetic_cut.ui import MainWindow
        self.w=MainWindow(); self.w.resize(1680,1000); self.w.show(); self.wait(50); return self.w
    def image(self,name="alpha.png"):
        path=self.root/name; source=Image.new("RGBA",(200,100),(255,255,255,0)); source.paste((0,255,0,255),(80,35,120,65)); source.save(path)
        return MediaItem(name,str(path),"image",name,5,200,100)
    def test_old_timeline_png_thumbnail_uses_original_alpha(self):
        from kinetic_cut.timeline import TimelineWidget
        media=self.image(); old=self.root/"old.jpg"; Image.new("RGB",(200,100),"white").save(old); media.thumbnail=str(old)
        p=Project(media=[media],timeline=[TimelineItem("clip",media.id,"video_1",0,8)])
        timeline=TimelineWidget(); timeline.set_project(p); timeline.resize(1100,500); timeline.show(); self.wait()
        pix=timeline.thumbnails["rgba:"+media.path].toImage(); self.assertEqual(pix.pixelColor(0,0).alpha(),0)
        self.assertAlmostEqual(pix.width()/pix.height(),2)
    def test_caption_preview_changes_and_conditional_rows(self):
        from kinetic_cut.caption_style_dialog import CaptionStyleDialog
        d=CaptionStyleDialog(CaptionStyle(),{}); d.show(); self.wait(40)
        self.assertFalse(d.form.isRowVisible(d.color_buttons["background_color"]))
        self.assertFalse(d.form.isRowVisible(d.color_buttons["highlight"]))
        first=d.preview.grab().toImage(); d.colors["color"]="#ff00ff"; d.size.setValue(120); d.upper.setChecked(True); self.wait(40)
        self.assertNotEqual(first,d.preview.grab().toImage())
        d.background.setChecked(True); d.animation.setCurrentText("word highlight")
        self.assertTrue(d.form.isRowVisible(d.color_buttons["background_color"])); self.assertTrue(d.form.isRowVisible(d.color_buttons["highlight"]))
        d.preview.play(True); self.assertTrue(d.preview.timer.isActive()); d.reject(); self.assertFalse(d.preview.timer.isActive())
    def test_middle_pan_does_not_zoom_but_normal_wheel_does(self):
        from kinetic_cut.widgets import PreviewCanvas
        view=PreviewCanvas(); view.pan_origin=QPointF(10,10)
        def wheel(buttons):return QWheelEvent(QPointF(40,40),QPointF(40,40),QPoint(),QPoint(0,120),buttons,Qt.NoModifier,Qt.ScrollUpdate,False)
        view.wheelEvent(wheel(Qt.MiddleButton)); self.assertEqual(view.view_zoom,1)
        view.pan_origin=None; view.wheelEvent(wheel(Qt.MiddleButton)); self.assertEqual(view.view_zoom,1)
        view.wheelEvent(wheel(Qt.NoButton)); self.assertGreater(view.view_zoom,1)
    def test_group_drag_lower_boundary_never_collapses_lanes(self):
        from kinetic_cut.timeline import TimelineWidget
        p=Project(); p.add_track("video"); p.add_track("video")
        p.timeline=[TimelineItem(t,"",t,1,10,link_id="") for t in p.video_tracks+["audio_1"]]
        t=TimelineWidget(); t.set_project(p); t.resize(1300,650); t.show(); self.wait(30); t.setProperty("snapping",False)
        t.select_ids({i.id for i in p.timeline},"video_3")
        point=t.item_rect(p.item_by_id("video_3")).center().toPoint(); QTest.mousePress(t.viewport(),Qt.LeftButton,Qt.NoModifier,point)
        dest=QPointF(point.x()+50,t.track_rect("video_1").center().y())
        QApplication.sendEvent(t.viewport(),QMouseEvent(QEvent.MouseMove,dest,dest,Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        self.assertEqual(len(t.move_preview),4); self.assertEqual({i.track for i in t.move_preview},set(p.video_tracks+["audio_1"]))
        QTest.mouseRelease(t.viewport(),Qt.LeftButton,Qt.NoModifier,dest.toPoint())
        self.assertEqual(len(p.timeline),4); self.assertEqual(len({i.start for i in p.timeline}),1)
    def test_external_drop_ghosts_commit_consecutively_and_dedupe_master(self):
        w=self.window(); a=self.image(); b=self.image("second.png"); w.project.media=[a]
        w.timeline.file_drop_controller.cache[str(Path(b.path).resolve()).lower()]=b
        w.timeline.file_drop_controller.resolved=lambda path: a if path==a.path else b
        t=w.timeline; point=QPoint(int(t.x_for_time(1)),int(t.track_rect("video_1").center().y()))
        self.mime=QMimeData(); self.mime.setUrls([QUrl.fromLocalFile(a.path),QUrl.fromLocalFile(b.path)])
        enter=QDragEnterEvent(point,Qt.CopyAction,self.mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(t.viewport(),enter)
        self.assertTrue(enter.isAccepted()); self.assertEqual(len(t.incoming_preview),2); self.assertEqual(len(w.project.media),1)
        starts=[i.start for i in t.incoming_preview]
        drop=QDropEvent(QPointF(point),Qt.CopyAction,self.mime,Qt.LeftButton,Qt.NoModifier); QApplication.sendEvent(t.viewport(),drop)
        self.assertTrue(drop.isAccepted()); self.assertEqual([i.start for i in w.project.timeline],starts); self.assertEqual(len(w.project.media),2)
        self.assertFalse(t.incoming_preview)
    def test_delete_gaps_menu_and_undo_redo(self):
        w=self.window(); p=NewActionModelTests().story()
        # Missing video fixture paths must not start native decoders in this model/UI test.
        with patch.object(w.transport,"sync"),patch.object(w,"seek"):
            w.set_project(p); before=copy.deepcopy(p.to_dict()); w.delete_gaps(); self.assertEqual(w.project.duration,15)
            w.undo(); self.assertEqual(w.project.to_dict()["timeline"],before["timeline"])
            w.redo(); self.assertEqual(w.project.duration,15)
    def test_uncached_explorer_drop_probes_off_thread_then_imports_once(self):
        w=self.window(); media=self.image(); controller=w.timeline.file_drop_controller
        controller.drop([media.path],"video_1",2)
        self.assertFalse(w.project.timeline)
        for _ in range(30):
            if w.project.timeline:break
            self.wait(50)
        self.assertEqual(len(w.project.timeline),1); self.assertEqual(w.project.timeline[0].start,2)
        self.assertEqual(len(w.project.media),1); self.assertEqual(w.project.media[0].width,200)
        controller.drop([media.path],"video_1",8); self.assertEqual(len(w.project.media),1); self.assertEqual(len(w.project.timeline),2)
    def test_file_drop_pending_result_does_not_import_into_changed_project(self):
        w=self.window(); media=self.image(); controller=w.timeline.file_drop_controller
        with patch.object(w,"start_worker"):
            controller.drop([media.path],"video_1",2); w.set_project(Project()); controller.ready(__import__('kinetic_cut.media_insert',fromlist=['source_key']).source_key(media.path),media)
        self.assertFalse(w.project.timeline); self.assertFalse(w.project.media)
    def test_chroma_alpha_preserved_and_source_not_mutated(self):
        from kinetic_cut.chroma import apply
        image=QImage(3,1,QImage.Format_RGBA8888); image.setPixelColor(0,0,Qt.green); image.setPixelColor(1,0,Qt.red); image.setPixelColor(2,0,Qt.transparent)
        result=apply(image,{"color":"#00ff00","similarity":15,"softness":8})
        self.assertEqual(result.pixelColor(0,0).alpha(),0); self.assertEqual(result.pixelColor(1,0).alpha(),255); self.assertEqual(result.pixelColor(2,0).alpha(),0)
        self.assertEqual(image.pixelColor(0,0).alpha(),255)
    def test_audio_drop_actions_commit_once_and_undo(self):
        from PySide6.QtWidgets import QMessageBox
        w=self.window(); jobs=[]
        with patch.object(w.transport,"sync"),patch.object(w,"seek"),patch.object(w,"start_worker",side_effect=jobs.append),patch("kinetic_cut.ui.QDialog.exec",return_value=1),patch.object(QMessageBox,"question",return_value=QMessageBox.Yes):
            w.set_project(NewActionModelTests().story()); original=copy.deepcopy(w.project.to_dict()["timeline"])
            jobs.clear()  # Ignore project-load indexing jobs.
            w.apply_effect_to("Cut curse words","1-audio_1"); self.assertEqual(len(jobs),1)
            jobs.pop().signals.result.emit(([(0,1),(2,5)],1))
            self.assertEqual(len(w.project.timeline),len(original)+1); self.assertEqual(w.project.item_by_id("1-video_1").duration,5)
            w.undo(); self.assertEqual(w.project.to_dict()["timeline"],original)
            w.apply_effect_to("Remove Silence","1-audio_1"); jobs.pop().signals.result.emit(([(1,2),(3,5)],0))
            self.assertEqual(len(w.project.timeline),len(original)+4); self.assertEqual(w.project.item_by_id("2-video_1").start,18)
            w.undo(); self.assertEqual(w.project.to_dict()["timeline"],original)
    def test_audio_result_rejects_changed_clip_without_partial_edit(self):
        w=self.window(); jobs=[]
        with patch.object(w.transport,"sync"),patch.object(w,"seek"),patch.object(w,"start_worker",side_effect=jobs.append):
            w.set_project(NewActionModelTests().story()); w.apply_effect_to("Cut curse words","1-audio_1")
            w.project.item_by_id("1-audio_1").start+=1; before=copy.deepcopy(w.project.to_dict()["timeline"])
            jobs.pop().signals.result.emit(([(0,1),(2,5)],1)); self.assertEqual(w.project.to_dict()["timeline"],before)
    def test_colour_sampler_maps_letterboxed_pixels(self):
        from kinetic_cut.chroma_dialog import SampleImage
        v=SampleImage(); v.resize(400,400); v.image=QImage(200,100,QImage.Format_RGB32); v.image.fill(Qt.green); chosen=[]; v.picked.connect(chosen.append)
        QTest.mouseClick(v,Qt.LeftButton,Qt.NoModifier,QPoint(10,10)); self.assertEqual(chosen,[])
        QTest.mouseClick(v,Qt.LeftButton,Qt.NoModifier,QPoint(200,200)); self.assertEqual(chosen,["#00ff00"])
