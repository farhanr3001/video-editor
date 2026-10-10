import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt,QPoint,QEvent,QThreadPool
from PySide6.QtWidgets import QApplication,QLabel
from kinetic_cut.model import Project,TimelineItem,CaptionStyle
from kinetic_cut.headline import headline_style
from kinetic_cut.exporter import PRESETS,write_ass


class TitleDeliveryTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); self.w=MainWindow(); self.w.show(); self.w.autosave_timer.stop()
        self.item=TimelineItem('title','','video_1',0,2,role='title',title_text='Fade 🥹',title_style=CaptionStyle(animation='none',size=42,shadow_enabled=False,color='#ffffff'),fade_in=.5,fade_out=.5)
        p=Project(timeline=[self.item]); p.settings.width=320; p.settings.height=180; p.settings.fps=20; self.w.set_project(p); self.app=QApplication.instance(); self.app.processEvents()
    def tearDown(self):
        self.w.close(); QThreadPool.globalInstance().waitForDone(10000); self.w.deleteLater(); self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents(); self.temp.cleanup()
    def test_preview_text_and_headline_fade_in_and_out(self):
        for style in (self.item.title_style,headline_style()):
            self.item.title_style=copy.deepcopy(style); self.item.title_style.size=42
            values=[]
            for at in (0,.25,1,1.75,1.99):
                self.w.project.playhead=at; image=self.w.preview.grab().toImage().copy(self.w.preview.composition_rect().toRect()).convertToFormat(__import__('PySide6.QtGui',fromlist=['QImage']).QImage.Format_RGBA8888)
                values.append(np.frombuffer(image.constBits(),dtype=np.uint8).reshape(image.height(),image.width(),4)[:,:,:3].sum())
            self.assertLess(values[0],values[2]*.1); self.assertGreater(values[1],values[2]*.2); self.assertLess(values[1],values[2]*.85); self.assertLess(values[3],values[2]*.85); self.assertLess(values[4],values[2]*.15)
    def test_export_headline_background_letters_and_emoji_all_fade(self):
        self.item.title_style=headline_style(); path=self.root/'title.ass'; write_ass(self.w.project,path,False)
        events=[line for line in path.read_text(encoding='utf-8-sig').splitlines() if line.startswith('Dialogue:')]
        self.assertGreater(len(events),2)
        self.assertTrue(all('\\t(0,500,\\alpha&H00&)' in line or '\\t(0,500,\\alpha&H' in line for line in events))
        self.assertTrue(all('\\t(1500,2000,\\alpha&HFF&)' in line for line in events))
    def test_title_opacity_and_overlapping_fades_multiply(self):
        from kinetic_cut.title_fades import opacity
        self.item.fade_in=2; self.item.fade_out=2; self.item.opacity=50
        self.assertAlmostEqual(opacity(self.item,1),.125)
        self.assertEqual(opacity(self.item,0),0); self.assertEqual(opacity(self.item,2),0)
    def test_recent_folders_keep_last_five_unique_and_persist(self):
        d=self.w.delivery
        with patch('kinetic_cut.config.save_settings') as save:
            for n in range(7):d.location.remember(self.root/str(n),self.w.settings)
            d.location.remember(self.root/'3',self.w.settings)
        self.assertTrue(save.called); self.assertEqual(d.location.count(),5); self.assertEqual(Path(d.location.itemText(0)).name,'3')
        self.assertEqual(len(set(self.w.settings['export_recent_locations'])),5); self.assertTrue(d.location.isEditable())
    def job(self,name,state='Queued'):
        return dict(project=copy.deepcopy(self.w.project),output=str(self.root/(name+'.mp4')),preset=next(iter(PRESETS.values())),hardware='CPU',burn=False,audio=False,state=state,elapsed=0.)
    def test_delivery_has_no_phone_or_wireless_buttons_and_queue_still_updates(self):
        from PySide6.QtWidgets import QPushButton
        d=self.w.delivery
        texts={button.text() for button in d.queue.findChildren(QPushButton)}
        self.assertNotIn('Send Completed Video to Phone',texts)
        self.assertNotIn('Wireless Download',texts)
        for state in ('Queued','Rendering','Complete','Failed'):
            d.jobs=[self.job('fixture',state)];d.refresh();d.list.setCurrentRow(0);d.update_controls()
            self.assertEqual(d.remove.isEnabled(),state!='Rendering')
        d.jobs=[];d.refresh();self.assertFalse(d.remove.isEnabled())
    def test_elapsed_starts_only_on_own_turn_and_freezes_on_completion(self):
        from kinetic_cut.render_queue import elapsed
        d=self.w.delivery; first=self.job('one'); second=self.job('two'); d.jobs=[first,second]
        with patch.object(self.w,'start_worker'),patch('kinetic_cut.workspace.time.monotonic',return_value=100):d.render_all()
        with patch('kinetic_cut.render_queue.time.monotonic',return_value=108):
            self.assertEqual(elapsed(first),8); self.assertEqual(elapsed(second),0)
            with patch.object(self.w,'start_worker'),patch('kinetic_cut.config.save_settings'):d.complete(first,'Complete')
        with patch('kinetic_cut.render_queue.time.monotonic',return_value=112):self.assertEqual(elapsed(first),8); self.assertEqual(elapsed(second),4)
        d.running=False
        with patch('kinetic_cut.render_queue.time.monotonic',return_value=115):d.complete(second,'Failed','test')
        self.assertEqual(elapsed(second),7); self.assertFalse(d.clock.isActive())
    def test_close_button_removes_only_queued_job_by_identity(self):
        d=self.w.delivery; active=self.job('active','Rendering'); waiting=self.job('waiting'); completed=self.job('done','Complete'); d.jobs=[active,waiting,completed]; d.refresh()
        active_card=d.list.itemWidget(d.list.item(0)); queued_card=d.list.itemWidget(d.list.item(1)); done_card=d.list.itemWidget(d.list.item(2))
        self.assertTrue(active_card.remove_button.isHidden()); self.assertTrue(done_card.remove_button.isHidden()); self.assertFalse(queued_card.remove_button.isHidden())
        queued_card.remove_button.click(); self.assertEqual(d.jobs,[active,completed]); d.remove_specific_job(active); self.assertEqual(d.jobs,[active,completed])
    def test_queue_context_location_is_complete_only(self):
        d=self.w.delivery; d.jobs=[self.job('one'),self.job('two','Complete')]; d.refresh()
        for row,enabled in ((0,False),(1,True)):
            d.queue_context(d.list.visualItemRect(d.list.item(row)).center()); self.assertEqual(d._queue_menu.actions()[0].isEnabled(),enabled); d._queue_menu.close()
        with patch('kinetic_cut.workspace.QDesktopServices.openUrl',return_value=True) as opened:
            d.open_job_location(d.jobs[0]); opened.assert_not_called(); d.open_job_location(d.jobs[1]); self.assertEqual(Path(opened.call_args.args[0].toLocalFile()),self.root)
    def test_deliver_settings_stay_fixed_and_fields_fit_small_window(self):
        from kinetic_cut.workspace import set_page
        set_page(self.w,1)
        for width in (1100,1480,1920,1100):
            self.w.resize(width,700); self.app.processEvents(); self.assertEqual(self.w.left_stack.width(),360); self.assertFalse(self.w.workspace_split.handle(1).isEnabled())
            body=self.w.delivery.settings_scroll.widget(); viewport=self.w.delivery.settings_scroll.viewport()
            self.assertLessEqual(body.width(),viewport.width())
            for field in (self.w.delivery.location,self.w.delivery.hardware,self.w.delivery.bitrate):self.assertLessEqual(field.mapTo(viewport,QPoint(field.width(),0)).x(),viewport.width())
        set_page(self.w,0); self.assertTrue(self.w.workspace_split.handle(1).isEnabled()); self.assertGreater(self.w.left_stack.maximumWidth(),360)
    def test_chocolatey_ffmpeg_is_resolved_without_spawning(self):
        from kinetic_cut.process import resolve_tool
        resolve_tool.cache_clear()
        with patch('kinetic_cut.process.shutil.which',return_value=r'C:\ProgramData\chocolatey\bin\ffmpeg.exe'),patch('kinetic_cut.process.Path.is_file',return_value=True):
            self.assertIn('lib\\ffmpeg\\tools',resolve_tool('ffmpeg'))
        self.assertEqual(resolve_tool('custom-encoder.exe'),'custom-encoder.exe'); resolve_tool.cache_clear()
