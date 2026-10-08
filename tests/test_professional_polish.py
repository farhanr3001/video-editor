import copy
import inspect
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QPointF, QMimeData, Qt
from PySide6.QtGui import QColor, QDragMoveEvent, QDropEvent, QImage, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from kinetic_cut.effects import ADJUSTABLE, MATRICES, TITLES, apply_color_effect, color_filter, compatible
from kinetic_cut.exporter import PRESETS
from kinetic_cut.model import Caption, MediaItem, Project, TimelineItem
from kinetic_cut.process import run as run_process
from kinetic_cut.rendergraph import audio_filters, command
from kinetic_cut.startup import StartupSplash
from kinetic_cut.ui import MainWindow
from kinetic_cut.workspace import set_page


class PolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.window=MainWindow(); self.window.resize(1480,900); self.window.show()
        media=MediaItem("m","fixture.png","image","fixture.png",20,1920,1080)
        project=Project(media=[media],timeline=[TimelineItem("v","m","video_1",0,10),TimelineItem("a","m","audio_1",0,10)],captions=[Caption("c",0,3,"A test caption")])
        self.window.set_project(project); self.window.timeline.linked_selection=False
        self.window.timeline.select_ids({"v"},"v"); self.app.processEvents()

    def tearDown(self):
        self.window.close(); self.app.processEvents()

    def project_key(self):
        return self.window._history_key(self.window.project)

    def test_inspector_title_and_custom_caption_colour_accept_and_cancel(self):
        w=self.window
        w.add_title_object("Text")
        title=w.project.item_by_id(w.timeline.selected_id)
        swatch=dict(w.inspector.style_colors)["color"]
        with patch("kinetic_cut.properties.QColorDialog.getColor",return_value=QColor("#ed826e")) as picker:
            swatch.click(); self.assertEqual(picker.call_count,1)
        self.assertEqual(title.title_style.color,"#ed826e")
        with patch("kinetic_cut.properties.QColorDialog.getColor",return_value=QColor()):swatch.click()
        self.assertEqual(title.title_style.color,"#ed826e")
        w.timeline.select_captions({"c"},"c"); w.inspector.customize_caption(True)
        caption=w.project.captions[0]; original=w.project.subtitle_style.color
        with patch("kinetic_cut.properties.QColorDialog.getColor",return_value=QColor("#65aadc")):swatch.click()
        self.assertEqual(caption.style.color,"#65aadc"); self.assertEqual(w.project.subtitle_style.color,original)

    def test_style_control_enablement_is_refreshed_when_switching_to_title(self):
        w=self.window; w.timeline.select_captions({"c"},"c"); w.inspector.customize_caption(True)
        w.inspector.edit_style("shadow_enabled",False)
        self.assertFalse(dict(w.inspector.style_colors)["shadow_color"].isEnabled())
        w.add_title_object("Text")
        self.assertTrue(dict(w.inspector.style_colors)["shadow_color"].isEnabled())

    def test_deliver_blocks_commands_shortcuts_drops_and_mouse_edits(self):
        w=self.window; t=w.timeline; w.timeline.select_ids({"v"},"v"); w.set_timeline_tool("blade")
        set_page(w,1); self.app.processEvents(); before=self.project_key()
        for control in w.timeline_edit_tools:self.assertFalse(control.isEnabled())
        self.assertFalse(w.shortcut_actions["cut"].isEnabled()); self.assertTrue(w.shortcut_actions["play_pause"].isEnabled())
        for function,args in [(w.split_selected,()),(w.delete_selected,(True,)),(w.apply_effect,("Sepia",)),(w.add_title_object,("Text",)),(w.undo,()),(w.viewer_command,("reset","v")),(t.link_clips,()),(t.set_speed,(2,)),(t.delete_caption,()),(w.inspector.add_caption,())]:function(*args)
        for key,modifier in [(Qt.Key_B,Qt.ControlModifier),(Qt.Key_Delete,Qt.NoModifier),(Qt.Key_Z,Qt.ControlModifier)]:QTest.keyClick(w,key,modifier)
        for item in w.project.timeline:
            pos=t.item_rect(item).center(); QTest.mousePress(t.viewport(),Qt.LeftButton,Qt.NoModifier,pos.toPoint()); QTest.mouseMove(t.viewport(),(pos+QPointF(40,0)).toPoint()); QTest.mouseRelease(t.viewport(),Qt.LeftButton,Qt.NoModifier,(pos+QPointF(40,0)).toPoint())
        QTest.mouseClick(t.viewport(),Qt.LeftButton,Qt.NoModifier,QPoint(58,round(t.track_rect("video_1").bottom()-15)))
        QTest.mouseClick(w.preview,Qt.LeftButton,Qt.NoModifier,w.preview.rect().center())
        mime=QMimeData(); mime.setData("application/x-kinetic-effect",b"Sepia")
        event=QDropEvent(t.item_rect(w.project.timeline[0]).center(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); t.dropEvent(event)
        self.assertFalse(event.isAccepted()); self.assertEqual(before,self.project_key())
        self.assertGreater(w.project.playhead,0); self.assertFalse(w.preview.transform_controls_visible)
        set_page(w,0); self.assertTrue(w.preview.transform_controls_visible)
        w.timeline.select_ids({"v"},"v"); w.seek(2); w.split_selected(); self.assertEqual(len(w.project.timeline),3)

    def test_deliver_preserves_user_transform_overlay_preference(self):
        self.window.transform_box_tool.setChecked(False); set_page(self.window,1); set_page(self.window,0)
        self.assertFalse(self.window.preview.transform_controls_visible)

    def test_project_defaults_and_settings_dialog_do_not_mutate_until_saved(self):
        from kinetic_cut.project_settings import ProjectSettingsDialog
        w=self.window; before=self.project_key(); dialog=ProjectSettingsDialog(w.project,w)
        self.assertEqual((w.project.settings.width,w.project.settings.height,w.project.settings.fps),(1080,1920,60))
        self.assertEqual(dialog.fps.currentText(),"60"); self.assertIn("Project Settings",w.project_settings_action.text())
        dialog.format.setCurrentIndex(1); dialog.fps.setCurrentText("30")
        name,settings=dialog.values(); self.assertEqual((settings.width,settings.height,settings.fps),(1920,1080,30))
        dialog.reject(); self.assertEqual(self.project_key(),before)
        w.apply_project_settings(name,settings)
        self.assertEqual(w.delivery.output_project().settings.width,1920)
        self.assertEqual(w.delivery.fps.currentText(),"30"); self.assertEqual(w.transport.timer.interval(),33)
        self.assertEqual(w.project.timeline[0].duration,10)
        w.undo(); self.assertEqual((w.project.settings.width,w.project.settings.height,w.project.settings.fps),(1080,1920,60))
        self.assertEqual(w.delivery.fps.currentText(),"60"); self.assertEqual(w.transport.timer.interval(),17)

    def test_project_format_updates_export_but_not_queued_snapshots(self):
        w=self.window; d=w.delivery
        with tempfile.TemporaryDirectory() as folder:
            d.location.setText(folder); d.name.setText("portrait-snapshot"); d.add_job()
            settings=copy.deepcopy(w.project.settings); settings.width=settings.height=1080; settings.fps=25
            w.apply_project_settings("Square project",settings)
            self.assertEqual((d.jobs[0]["project"].settings.width,d.jobs[0]["project"].settings.height),(1080,1920))
            self.assertEqual((d.output_project().settings.width,d.output_project().settings.height,d.output_project().settings.fps),(1080,1080,25))
            set_page(w,1); self.assertFalse(w.project_settings_action.isEnabled())
            before=self.project_key(); w.apply_project_settings("Not allowed",settings); self.assertEqual(before,self.project_key())

    def test_scrubber_autoscrolls_both_edges_while_pointer_is_stationary(self):
        w=self.window; t=w.timeline; w.project.timeline[0].duration=120; t.set_project(w.project); self.app.processEvents()
        for page in (0,1):
            set_page(w,page); bar=t.horizontalScrollBar(); bar.setValue(500)
            t.start_scrub(t.LABEL_WIDTH+2); initial=w.project.playhead
            for _ in range(12):t.scroll_scrub()
            self.assertLess(bar.value(),500); self.assertLess(w.project.playhead,initial)
            bar.setValue(0); t.scrub_at(t.viewport().width()-2); initial=w.project.playhead
            for _ in range(12):t.scroll_scrub()
            self.assertGreater(bar.value(),0); self.assertGreater(w.project.playhead,initial)
            t.mouseReleaseEvent(None); self.assertFalse(t.scrub_timer.isActive())
            stable=bar.value(); t.scroll_scrub(); self.assertEqual(bar.value(),stable)

    def test_explicit_seek_and_playback_reveal_offscreen_playhead(self):
        w=self.window; t=w.timeline; w.project.timeline[0].duration=120; t.set_project(w.project)
        t.horizontalScrollBar().setValue(t.horizontalScrollBar().maximum()); w.seek(0)
        self.assertEqual(t.horizontalScrollBar().value(),0)
        w.seek(100); self.assertGreater(t.horizontalScrollBar().value(),0)
        self.assertLessEqual(t.x_for_time(100),t.viewport().width()-23)
        t.horizontalScrollBar().setValue(0); w.transport.playing=True; w.transport_position(100); w.transport.playing=False
        self.assertLessEqual(t.x_for_time(100),t.viewport().width()-23)

    def test_video_wheel_up_reveals_higher_layers_down_returns_towards_v1(self):
        w=self.window; t=w.timeline
        for _ in range(6):w.project.add_track("video"); w.project.add_track("audio")
        t.set_project(w.project); self.app.processEvents()
        def wheel(section,delta):
            point=t._sections()[section].center()
            event=QWheelEvent(point,point,QPoint(),QPoint(0,delta),Qt.NoButton,Qt.NoModifier,Qt.ScrollUpdate,False); t.wheelEvent(event)
        self.assertEqual(t.video_scroll.value(),0)
        wheel("video",120); self.assertGreater(t.video_scroll.value(),0)
        wheel("video",-120); self.assertEqual(t.video_scroll.value(),0)
        self.assertAlmostEqual(t.track_rect("video_1").bottom(),t._sections()["video"].bottom())
        wheel("audio",-120); self.assertGreater(t.audio_scroll.value(),0)
        wheel("audio",120); self.assertEqual(t.audio_scroll.value(),0)

    def test_effect_drop_hover_clears_and_rejects_incompatible_or_locked_targets(self):
        w=self.window; t=w.timeline; pos=t.item_rect(w.project.timeline[0]).center().toPoint()
        before=t.viewport().grab().toImage()
        mime=QMimeData(); mime.setData("application/x-kinetic-effect",b"Sepia")
        move=QDragMoveEvent(pos,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); t.dragMoveEvent(move)
        self.assertTrue(move.isAccepted()); self.assertEqual(t.effect_hover[1],"v")
        after=t.viewport().grab().toImage(); sample=pos-QPoint(0,20)
        self.assertNotEqual(before.pixelColor(sample),after.pixelColor(sample))
        self.assertIsNone(t.effect_target("Sepia",t.item_rect(w.project.timeline[1]).center()))
        w.project.track_states["video_1"]={"locked":True}; self.assertIsNone(t.effect_target("Sepia",QPointF(pos)))
        w.project.track_states["video_1"]["locked"]=False
        event=QDropEvent(QPointF(pos),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); t.dropEvent(event)
        self.assertTrue(event.isAccepted()); self.assertIsNone(t.effect_hover)
        self.assertEqual(w.project.timeline[0].effects[0]["name"],"Sepia")

    def test_all_new_presets_are_editable_and_exported(self):
        w=self.window
        for name in ADJUSTABLE:
            item=next(item for item in w.project.timeline if compatible(name,item,w.project))
            w.timeline.select_ids({item.id},item.id); w.apply_effect(name)
            self.assertEqual(item.effects[-1]["name"],name)
            w.inspector.edit_effect("amount",37); self.assertEqual(item.effects[-1]["amount"],37)
            w.inspector.edit_effect("enabled",False); self.assertFalse(item.effects[-1]["enabled"])
            w.inspector.edit_effect("enabled",True)
        graph=command(w.project,"out.mp4",next(iter(PRESETS.values())),False)
        self.assertIn("colorchannelmixer=rr=",graph[graph.index("-filter_complex")+1])
        audio=audio_filters(w.project.timeline[1]); self.assertIn("equalizer=",audio); self.assertIn("highpass=",audio)
        for name in TITLES:
            w.add_title_object(name); item=w.project.item_by_id(w.timeline.selected_id)
            self.assertEqual(item.role,"title"); self.assertEqual(item.title_style.name,name)

    def test_preset_bypass_and_removal_preserve_stack_order(self):
        w=self.window; item=w.project.timeline[0]
        w.apply_effect("Light Boost"); first=item.brightness
        w.apply_effect("Cinematic Contrast"); second=item.brightness
        w.inspector.effect_picker.setCurrentIndex(0); w.inspector.edit_effect("enabled",False)
        self.assertEqual(item.brightness,second)
        w.inspector.effect_picker.setCurrentIndex(1); w.inspector.edit_effect("enabled",False)
        self.assertEqual(item.brightness,0)
        w.inspector.effect_picker.setCurrentIndex(0); w.inspector.edit_effect("enabled",True)
        self.assertEqual(item.brightness,first)
        w.inspector.remove_effect(); self.assertEqual(item.brightness,0)
        w.inspector.effect_picker.setCurrentIndex(0); w.inspector.edit_effect("enabled",True)
        self.assertEqual(item.brightness,second)

    def test_failed_render_retains_error_and_retry_state(self):
        d=self.window.delivery
        job=dict(project=copy.deepcopy(self.window.project),output="test-output.mp4",state="Rendering")
        d.jobs=[job]; d.running=True; d.complete(job,"Failed","Encoder was not available")
        self.assertEqual(job["error"],"Encoder was not available")
        self.assertIn("1 failed",d.status.text()); self.assertIn("Encoder",d.list.item(0).toolTip())
        self.assertFalse(d.render.isEnabled()); self.assertEqual(d.render.text(),"Render All")
        self.assertFalse(d.phone.isEnabled())
        with patch.object(d,"next_job"):d.render_all()
        self.assertEqual(job["state"],"Failed"); self.assertIn("error",job)
        from kinetic_cut.render_queue import elapsed_text
        self.assertEqual(elapsed_text(job),'RENDER FAILED')
        queued=dict(project=copy.deepcopy(self.window.project),output='new.mp4',state='Queued')
        d.running=False; d.jobs.append(queued)
        with patch.object(d,'next_job'):d.render_all()
        self.assertEqual(job['state'],'Failed'); self.assertEqual(queued['state'],'Queued')

    def test_splash_renders_real_progress_and_workspace_reports_stages(self):
        splash=StartupSplash(); splash.report(64,"Building timeline, inspector and effects")
        self.assertEqual(splash.progress,64); self.assertFalse(splash.grab().isNull()); splash.close()
        stages=[]; window=MainWindow(startup_progress=lambda percent,text:stages.append((percent,text)))
        self.assertEqual([x[0] for x in stages],sorted(x[0] for x in stages)); self.assertGreater(stages[-1][0],90)
        window.show(); window.close(); self.app.processEvents()

    def test_new_colour_effects_match_ffmpeg_pixels_and_preserve_alpha(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            image=QImage(8,8,QImage.Format_RGBA8888); image.fill(QColor(100,130,160,180))
            path=str(Path(folder)/"input.png"); image.save(path)
            for name in MATRICES:
                for amount in [0,37,100]:
                    effect={"name":name,"amount":amount}
                    preview=apply_color_effect(image,effect)
                    expected=np.frombuffer(preview.constBits(),dtype=np.uint8).reshape(8,8,4).astype(int)
                    result=run_process(["ffmpeg","-v","error","-i",path,"-vf",color_filter(effect),"-frames:v","1","-threads","1","-f","rawvideo","-pix_fmt","rgba","pipe:1"],capture_output=True,check=True)
                    actual=np.frombuffer(result.stdout,dtype=np.uint8).reshape(8,8,4).astype(int)
                    self.assertLessEqual(abs(expected-actual).max(),2,(name,amount))

    @unittest.skipUnless(os.name=="nt","Windows process flags")
    def test_dependency_subprocesses_are_hidden_and_keep_output_and_flags(self):
        from kinetic_cut.process import install_desktop_process_policy
        original=subprocess.Popen; execute=original._execute_child; signature=inspect.signature(execute); seen=[]
        def record(*args,**kwargs):
            values=signature.bind(*args,**kwargs).arguments; seen.append(values)
            return execute(*args,**kwargs)
        try:
            with patch.object(original,"_execute_child",record):
                install_desktop_process_policy()
                result=subprocess.run([sys.executable,"-c","print('child ready')"],capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            self.assertEqual(result.stdout.strip(),"child ready")
            self.assertTrue(seen[0]["creationflags"] & subprocess.CREATE_NO_WINDOW)
            self.assertTrue(seen[0]["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)
            self.assertEqual(seen[0]["startupinfo"].wShowWindow,subprocess.SW_HIDE)
        finally:subprocess.Popen=original


if __name__=="__main__":unittest.main()
