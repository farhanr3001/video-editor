import unittest,copy,tempfile,threading,zipfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image
from PySide6.QtCore import Qt,QEvent,QEventLoop,QTimer,QThreadPool,QPoint
from PySide6.QtGui import QPolygonF,QContextMenuEvent,QImage
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox,QMenu
from PySide6.QtTest import QTest
from kinetic_cut.model import Project,TimelineItem,MediaItem,Caption,CaptionStyle,Crop


class CurrentModelTests(unittest.TestCase):
    def test_duplicate_order_and_legacy_links_are_independent(self):
        p=Project(); p.add_track('video'); p.add_track('audio')
        p.timeline=[TimelineItem('v','m','video_1',2,5,group_id='old'),TimelineItem('a','m','audio_1',2,5,group_id='old')]
        p.timeline[0].effects=[dict(name='Gaussian Blur',horizontal=12)]
        v=p.duplicate_track('video_1'); a=p.duplicate_track('audio_1')
        self.assertEqual(p.video_tracks,['video_1',v,'video_2']); self.assertEqual(p.audio_tracks,[a,'audio_1','audio_2'])
        clones=[i for i in p.timeline if i.track in {v,a}]
        self.assertEqual(len(clones),2); self.assertTrue(all(len(p.linked_items(i))==1 for i in clones))
        self.assertEqual(len(p.linked_items(p.timeline[0])),2)
        clones[0].effects[0]['horizontal']=80; self.assertEqual(p.timeline[0].effects[0]['horizontal'],12)

    def test_caption_group_breaks_at_long_pause(self):
        from kinetic_cut.captions import _from_segments
        caps=_from_segments([dict(text='cinema feels',start=7.4,end=12.7,words=[dict(text='cinema',start=7.4,end=8.1),dict(text='feels',start=12.2,end=12.7)])],words_per_caption=2)
        self.assertEqual([c.text for c in caps],['cinema','feels']); self.assertEqual(caps[1].start,12.2)

    def test_auto_probes_encoder_and_falls_back(self):
        from kinetic_cut.exporter import automatic_encoder
        automatic_encoder.cache_clear()
        with patch('kinetic_cut.process.run',side_effect=[SimpleNamespace(returncode=1),SimpleNamespace(returncode=0)]) as run:
            self.assertEqual(automatic_encoder('test-ffmpeg','h264'),'Intel'); self.assertEqual(run.call_count,2)
        automatic_encoder.cache_clear()
        with patch('kinetic_cut.process.run',return_value=SimpleNamespace(returncode=1)):
            self.assertEqual(automatic_encoder('test-ffmpeg','h265'),'CPU')
        automatic_encoder.cache_clear()

    def test_titles_render_with_subtitle_burn_off_and_muted_audio_excluded(self):
        from kinetic_cut.exporter import write_ass,build_command,PRESETS
        p=Project(); p.timeline=[TimelineItem('title','','video_1',0,2,role='title',title_text='Headline',title_style=CaptionStyle(animation='none'))]
        p.captions=[Caption('c',0,1,'Secret caption')]
        p.media=[MediaItem('a','source.mp3','audio','audio',2,has_audio=True)]; p.timeline.append(TimelineItem('audio','a','audio_1',0,2)); p.track_states['audio_1']['muted']=True
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'text.ass'; write_ass(p,path,False); text=path.read_text(encoding='utf-8-sig')
            self.assertIn('Headline',text); self.assertNotIn('Secret caption',text)
            cmd=build_command(p,'out.mp4',next(iter(PRESETS.values())),False,'CPU',ass_path=str(path))
            self.assertIn('ass=',cmd[cmd.index('-filter_complex')+1]); self.assertNotIn('source.mp3',cmd)

    def test_vocal_cancel_and_archive_paths(self):
        from kinetic_cut import vocal_component as c
        event=threading.Event(); event.set()
        with self.assertRaises(c.Cancelled):c.check_cancel(event)
        with tempfile.TemporaryDirectory() as root:
            archive=Path(root)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside.txt','no')
            with self.assertRaisesRegex(RuntimeError,'Unsafe'):c.unzip(archive,Path(root)/'runtime')
            self.assertFalse((Path(root)/'outside.txt').exists())

    def test_project_discovery_and_recoverable_delete(self):
        from kinetic_cut.project_manager import project_paths,recoverable_delete
        with tempfile.TemporaryDirectory() as root:
            file=Path(root)/'project.kcut'; p=Project(name='My Edit'); p.save(file)
            settings=dict(project_folder=root,recent_projects=[str(file)])
            self.assertEqual(project_paths(settings),[file]); target=recoverable_delete(file)
            self.assertFalse(file.exists()); self.assertEqual(Project.load(target).name,'My Edit'); self.assertFalse(project_paths(settings))


class CurrentUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def wait(self,ms=40):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(10000); self.wait(); self.app.clipboard().clear()
        for widget in self.app.topLevelWidgets():widget.close(); widget.deleteLater()
        self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.wait(); self.temp.cleanup()
    def window(self):
        from kinetic_cut.ui import MainWindow
        w=MainWindow(); self.w=w; w.resize(1680,1000); w.show(); w.autosave_timer.stop(); self.wait(); return w
    def scene(self,w):
        path=self.root/'image.png'; Image.new('RGBA',(400,200),'orange').save(path)
        p=Project(); p.add_track('video'); p.media=[MediaItem('m',str(path),'image','Image',8,400,200)]
        camera=TimelineItem('cam','m','video_2',0,8,crop=Crop(.2,.2,.5,.5)); camera.transform.scale=.2; camera.transform.scale_y=.2
        game=TimelineItem('game','m','video_1',0,8); game.transform.scale=.25; game.transform.scale_y=.25
        p.timeline=[game,camera]; w.set_project(p); w.seek(.2); self.wait(); return p,camera,game
    def test_slider_defaults_center_and_endpoints_stay_usable(self):
        from kinetic_cut.properties import ValueRow
        for low,high,default in [(-60,18,0),(0,100,12),(.01,10,1)]:
            row=ValueRow(low,high,default); self.assertEqual(row.slider.value(),500)
            self.assertEqual(row.slider_to_value(0),low); self.assertEqual(row.slider_to_value(1000),high)
            row.slider.setValue(500); self.assertAlmostEqual(row.spin.value(),default)
        self.assertEqual(ValueRow(0,100,0).slider.value(),0)
    def test_webcam_alignment_and_blur_undo(self):
        w=self.window(); p,cam,game=self.scene(w)
        def bounds(item):
            rect=next(r for i,_,r in w.preview._visible_items() if i.id==item.id)
            return QPolygonF(w.preview._transform_geometry(item,rect)[1]).boundingRect()
        w.viewer_command('position_top',cam.id); self.assertAlmostEqual(bounds(cam).top(),w.preview.composition_rect().top(),places=3)
        w.viewer_command('mark_webcam',cam.id); self.assertTrue(cam.is_webcam)
        w.viewer_command('below_webcam',game.id); self.assertAlmostEqual(bounds(game).top(),bounds(cam).bottom(),places=3)
        self.assertAlmostEqual(bounds(game).center().x(),w.preview.composition_rect().center().x(),places=3)
        w.select_item(game.id); inspector=w.inspector
        self.assertFalse(inspector.background_blur_strength.isEnabled()); inspector.background_blur_enabled.setChecked(True)
        self.assertTrue(inspector.background_blur_strength.isEnabled()); self.assertEqual(len(game.effects),1)
        inspector.background_blur_enabled.setChecked(False); self.assertFalse(game.effects[0]['enabled'])
        w.undo(); self.assertTrue(w.project.item_by_id(game.id).effects[0]['enabled'])
    def test_header_mute_and_context_separation(self):
        w=self.window(); p,_,_=self.scene(w); t=w.timeline
        rect=t.header_controls('audio_1')[1]; QTest.mouseClick(t.viewport(),Qt.LeftButton,Qt.NoModifier,rect.center().toPoint())
        self.assertTrue(p.track_states['audio_1']['muted']); self.assertTrue(p.track_states['audio_1']['visible'])
        seen=[]
        def close_menu():
            for menu in w.findChildren(QMenu):
                if menu.isVisible():seen.extend(a.text() for a in menu.actions()); menu.close()
        point=QPoint(55,int(t.track_rect('video_1').top()+12))
        QTimer.singleShot(30,close_menu); t.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse,point,t.viewport().mapToGlobal(point)))
        self.assertIn('Duplicate Layer',seen); self.assertNotIn('Copy',seen); self.assertNotIn('Paste Attributes…',seen)
    def test_new_project_cancel_then_create_clears_everything(self):
        from kinetic_cut.project_settings import ProjectSettingsDialog
        w=self.window(); p,_,_=self.scene(w); p.captions=[Caption('c',0,1,'Old')]
        with patch.object(ProjectSettingsDialog,'exec',return_value=QDialog.Accepted),patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):w.new_project()
        self.assertIs(w.project,p)
        with patch.object(ProjectSettingsDialog,'exec',return_value=QDialog.Accepted),patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):w.new_project()
        self.assertFalse(w.project.timeline or w.project.media or w.project.captions or w.project.path)
        self.assertEqual(w.project.settings.fps,60); self.assertEqual(len(w._history),1)
        self.assertFalse(w.project.settings.auto_duck or w.project.settings.normalize_audio or w.project.settings.noise_reduction)

    def test_new_project_has_no_audio_processing_controls(self):
        from kinetic_cut.project_settings import ProjectSettingsDialog
        from PySide6.QtWidgets import QCheckBox
        p=Project(); p.settings.auto_duck=True; p.settings.normalize_audio=True; p.settings.noise_reduction=True
        dialog=ProjectSettingsDialog(p,new_project=True)
        self.assertFalse(dialog.findChildren(QCheckBox))
        _,settings=dialog.values()
        self.assertFalse(settings.auto_duck or settings.normalize_audio or settings.noise_reduction)
        existing=ProjectSettingsDialog(p); _,saved=existing.values()
        self.assertTrue(saved.auto_duck and saved.normalize_audio and saved.noise_reduction)
        fresh=Project(); self.assertFalse(fresh.settings.auto_duck or fresh.settings.normalize_audio or fresh.settings.noise_reduction)
    def test_delivery_titles_do_not_enable_subtitle_switch(self):
        w=self.window(); p,_,_=self.scene(w); p.timeline.append(TimelineItem('title','','video_2',0,3,role='title',title_text='Headline'))
        w.delivery.refresh_estimate(); self.assertFalse(w.delivery.burn.isEnabled()); self.assertEqual(w.delivery.hardware.currentText(),'Auto')
        p.captions=[Caption('c',0,1,'Subtitle')]; w.delivery.refresh_estimate(); self.assertTrue(w.delivery.burn.isEnabled()); self.assertTrue(w.delivery.burn.isChecked())
    def test_project_gallery_thumbnail_and_modes(self):
        from kinetic_cut.project_manager import ProjectManagerDialog,remember,thumbnail_path
        w=self.window(); p,_,_=self.scene(w); path=self.root/'Saved.kcut'; p.save(path); w.settings['project_folder']=str(self.root); w.settings['recent_projects']=[]
        remember(w,path,True); self.assertFalse(QImage(str(thumbnail_path(path))).isNull())
        d=ProjectManagerDialog(w); d.show()
        for _ in range(100):
            if d.items.count()==2:break
            self.wait()
        self.assertEqual(d.items.count(),2); self.assertEqual(d.items.item(0).text(),'New Project')
        d.set_list(True); d.set_list(False); d.activate(d.items.item(1)); self.assertEqual(d.choice,str(path))
    def test_vocal_replacement_preserves_video_and_timing_and_undo(self):
        from kinetic_cut.vocal_ui import begin
        from kinetic_cut import vocal_component
        w=self.window(); p,cam,game=self.scene(w)
        audio=TimelineItem('a','sound','audio_1',1,3,in_point=2,gain_db=-4,speed=1.5,group_id='pair'); game.group_id='pair'
        p.media.append(MediaItem('sound',str(self.root/'source.mp4'),'video','Source',12,400,200,60,True)); p.timeline.append(audio)
        jobs=[]; asset=MediaItem('vocal',str(self.root/'vocals.mp3'),'audio','Vocals',4.5,has_audio=True)
        with patch.object(w,'start_worker',side_effect=jobs.append),patch.object(w.transport,'sync'):
            w.model_changed(); w.select_item(audio.id)
            with patch.object(vocal_component,'ready',return_value=True),patch('kinetic_cut.vocal_ui.QFileDialog.getSaveFileName',return_value=(asset.path,'')):begin(w)
            self.assertTrue(w._vocal_busy)
            with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):jobs[-1].signals.result.emit(asset)
            self.assertEqual((audio.media_id,audio.in_point,audio.start,audio.duration,audio.speed,audio.gain_db),('vocal',0,1,3,1.5,-4))
            self.assertEqual(game.media_id,'m'); w.undo(); self.assertEqual(w.project.item_by_id('a').media_id,'sound')
        jobs.clear()
