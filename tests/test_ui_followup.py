import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from kinetic_cut.controls import InspectorSection
from kinetic_cut.model import Caption, MediaItem, Project, TimelineItem
from kinetic_cut.exporter import _target_size
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.ui import MainWindow
from kinetic_cut.widgets import PreviewCanvas


class FollowupUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_video_dropped_on_audio_lane_keeps_linked_picture_and_sound(self):
        window = MainWindow()
        try:
            media = MediaItem("media", "missing.mp4", "video", "missing.mp4", 12, 1920, 1080, 30, True)
            window.project.media = [media]
            window.add_media_to_track(media.id, "audio_1", 2)
            group = window.project.timeline
            self.assertEqual(len(group), 2)
            self.assertEqual({item.track for item in group}, {"video_1", "audio_1"})
            self.assertEqual(len({item.group_id for item in group}), 1)
            self.assertIn(window.timeline.selected_id, {item.id for item in group if item.track == "video_1"})
        finally:
            window.close()

    def test_mp3_remains_audio_only(self):
        window = MainWindow()
        try:
            media = MediaItem("music", "missing.mp3", "audio", "missing.mp3", 12)
            window.project.media = [media]
            window.add_media_to_track(media.id, "audio_1", 0)
            self.assertEqual([item.track for item in window.project.timeline], ["audio_1"])
        finally:
            window.close()

    def test_timeline_has_two_independent_vertical_section_dividers(self):
        timeline = TimelineWidget(); timeline.resize(900, 520); timeline.show()
        project = Project(captions=[Caption("caption", 0, 1, "Text")])
        project.add_track("video"); project.add_track("audio"); timeline.set_project(project)
        self.assertFalse(timeline._subtitle_divider_rect().isEmpty())
        self.assertFalse(timeline._av_divider_rect().isEmpty())
        old_video, old_audio = timeline.video_track_height, timeline.audio_track_height
        center = timeline._av_divider_rect().center()
        press = QMouseEvent(QMouseEvent.MouseButtonPress, center, center, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        timeline.mousePressEvent(press)
        moved = center + QPoint(0, 24)
        move = QMouseEvent(QMouseEvent.MouseMove, moved, moved, Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        timeline.mouseMoveEvent(move)
        self.assertGreater(timeline.video_track_height, old_video)
        self.assertLess(timeline.audio_track_height, old_audio)
        self.app.processEvents(); self.assertFalse(timeline.grab().isNull()); timeline.close()

    def test_blade_snaps_to_a_cut_on_another_lane(self):
        timeline = TimelineWidget(); timeline.resize(900, 420)
        media = MediaItem("m", "source.mp4", "video", "source.mp4", 20, has_audio=True)
        project = Project(media=[media], timeline=[TimelineItem("v1", "m", "video_1", 0, 5), TimelineItem("v2", "m", "video_1", 5, 5), TimelineItem("a", "m", "audio_1", 0, 10)])
        timeline.set_project(project); timeline.set_zoom(45); timeline.set_tool("blade")
        audio = project.item_by_id("a"); at = timeline._blade_time(audio, timeline.x_for_time(5.08))
        self.assertEqual(at, 5)

    def test_ctrl_shift_and_marquee_select_media_and_subtitles(self):
        timeline = TimelineWidget(); timeline.resize(1000, 500); timeline.show(); timeline.linked_selection=False
        media = MediaItem("m", "source.mp4", "video", "source.mp4", 20)
        clips=[TimelineItem(f"v{index}","m","video_1",index*2,2) for index in range(3)]
        captions=[Caption(f"c{index}",1+index*2,2+index*2,f"Caption {index}") for index in range(3)]
        project=Project(media=[media],timeline=clips,captions=captions); project.playhead=9; timeline.set_project(project); self.app.processEvents()
        QTest.mouseClick(timeline.viewport(),Qt.LeftButton,Qt.NoModifier,timeline.item_rect(clips[0]).center().toPoint())
        QTest.mouseClick(timeline.viewport(),Qt.LeftButton,Qt.ShiftModifier,timeline.item_rect(clips[2]).center().toPoint())
        self.assertEqual(timeline.selected_ids,{"v0","v1","v2"})
        QTest.mouseClick(timeline.viewport(),Qt.LeftButton,Qt.ControlModifier,timeline.item_rect(clips[1]).center().toPoint())
        self.assertEqual(timeline.selected_ids,{"v0","v2"})
        QTest.mouseClick(timeline.viewport(),Qt.LeftButton,Qt.NoModifier,timeline.caption_rect(captions[0]).center().toPoint())
        QTest.mouseClick(timeline.viewport(),Qt.LeftButton,Qt.ShiftModifier,timeline.caption_rect(captions[2]).center().toPoint())
        self.assertEqual(timeline.selected_caption_ids,{"c0","c1","c2"})
        QTest.mouseClick(timeline.viewport(),Qt.LeftButton,Qt.ControlModifier,timeline.caption_rect(captions[1]).center().toPoint())
        self.assertEqual(timeline.selected_caption_ids,{"c0","c2"})
        start=timeline.caption_rect(captions[0]).topLeft().toPoint()-QPoint(18,0); end=timeline.caption_rect(captions[2]).bottomRight().toPoint()+QPoint(18,0)
        QTest.mousePress(timeline.viewport(),Qt.LeftButton,Qt.NoModifier,start); QTest.mouseMove(timeline.viewport(),end,50); QTest.mouseRelease(timeline.viewport(),Qt.LeftButton,Qt.NoModifier,end)
        self.assertEqual(timeline.selected_caption_ids,{"c0","c1","c2"}); timeline.close()

    def test_inspector_section_reset_all_and_crop_window_are_immediate(self):
        import kinetic_cut.ui as ui_module
        window = MainWindow()
        try:
            media = MediaItem("m", "missing.mp4", "video", "missing.mp4", 10, 1920, 1080, 30, False)
            clip = TimelineItem("v", "m", "video_1", 0, 5)
            window.set_project(Project(media=[media], timeline=[clip])); window.timeline.select_ids({"v"}, "v")
            clip.transform.x = .8
            section = next(section for section in window.inspector.video.findChildren(InspectorSection) if section.toggle.text() == "Transform" and section.reset_button.isEnabled())
            section.reset_button.click(); self.assertEqual(clip.transform.x, .5)
            original = ui_module.extract_frame
            ui_module.extract_frame = lambda *_: (time.sleep(.35) or QImage())
            started = time.perf_counter(); window.frame_source("v"); elapsed = time.perf_counter() - started
            self.assertLess(elapsed, .15)
            for dialog in list(window._crop_dialogs):dialog.reject()
            self.app.processEvents(); window.thread_pool.waitForDone(1000); ui_module.extract_frame = original
        finally:
            window.close()

    def test_zoom_one_uses_resolve_style_fill_scaling_in_preview_and_export(self):
        media=MediaItem("m","missing.mp4","video","missing.mp4",5,1920,1080,30,False)
        clip=TimelineItem("v","m","video_1",0,5)
        project=Project(media=[media],timeline=[clip])
        canvas=PreviewCanvas(); canvas.set_project(project)
        source=QImage(960,540,QImage.Format_RGB32)
        target=canvas._layer_rect(clip,source,QRectF(0,0,108,192))
        self.assertAlmostEqual(target.width(),192*16/9)
        self.assertAlmostEqual(target.height(),192)
        self.assertEqual(_target_size(clip,media,project.settings.width),(3414,1920))
        clip.crop.width=.267; clip.crop.height=.841
        exported=_target_size(clip,media,project.settings.width)
        self.assertEqual(exported,(912,1614))
        self.assertEqual((exported[0]%2,exported[1]%2),(0,0))

    def test_fit_command_calculates_a_real_fit_after_native_zoom(self):
        window=MainWindow()
        try:
            media=MediaItem("m","missing.mp4","video","missing.mp4",5,1920,1080,30,False)
            clip=TimelineItem("v","m","video_1",0,5)
            window.set_project(Project(media=[media],timeline=[clip]))
            window.viewer_command("fit","v")
            self.assertAlmostEqual(clip.transform.scale,(1080/1920)/(1920/1080))
            self.assertAlmostEqual(clip.transform.effective_scale_y,(1080/1920)/(1920/1080))
        finally:
            window.close()

    def test_plain_empty_timeline_click_clears_selection(self):
        timeline=TimelineWidget(); timeline.resize(900,420); timeline.show()
        media=MediaItem("m","missing.mp4","video","missing.mp4",5,1920,1080,30,False)
        clip=TimelineItem("v","m","video_1",0,2)
        timeline.set_project(Project(media=[media],timeline=[clip])); timeline.select_ids({"v"},"v"); self.app.processEvents()
        empty=QPoint(round(timeline.x_for_time(8)),round(timeline.track_rect("video_1").center().y()))
        QTest.mouseClick(timeline.viewport(),Qt.LeftButton,Qt.NoModifier,empty)
        self.assertEqual(timeline.selected_ids,set()); self.assertEqual(timeline.selected_id,""); timeline.close()

    def test_selected_timeline_clip_paints_visible_red_perimeter(self):
        timeline=TimelineWidget(); timeline.resize(900,420); timeline.show()
        media=MediaItem("m","missing.mp4","video","missing.mp4",5,1920,1080,30,False)
        clip=TimelineItem("v","m","video_1",0,4)
        timeline.set_project(Project(media=[media],timeline=[clip])); timeline.select_ids({"v"},"v"); self.app.processEvents()
        image=timeline.viewport().grab().toImage(); rect=timeline.item_rect(clip).adjusted(0,0,-1,-1).toAlignedRect()
        red_pixels=0
        for x in range(max(0,rect.left()),min(image.width(),rect.right()+1)):
            for y in (rect.top()+1,rect.bottom()-1):
                colour=image.pixelColor(x,y); red_pixels+=colour.red()>220 and colour.green()<125 and colour.blue()<115
        for y in range(max(0,rect.top()),min(image.height(),rect.bottom()+1)):
            for x in (rect.left()+1,rect.right()-1):
                colour=image.pixelColor(x,y); red_pixels+=colour.red()>220 and colour.green()<125 and colour.blue()<115
        self.assertGreater(red_pixels,30); timeline.close()

    def test_transform_overlay_toggle_does_not_clear_timeline_selection(self):
        window=MainWindow()
        try:
            self.assertTrue(window.transform_box_tool.isChecked())
            window.transform_box_tool.click(); self.assertFalse(window.preview.transform_controls_visible)
            window.transform_box_tool.click(); self.assertTrue(window.preview.transform_controls_visible)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
