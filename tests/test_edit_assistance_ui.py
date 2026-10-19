import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption,Transform
from kinetic_cut.assistant_api import EditorAPI,revision,TOOLS
from kinetic_cut import transcripts


class EditAssistanceUITests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.app=QApplication.instance() or QApplication([])
        self.compositor=patch.dict('os.environ',{'KINETIC_COMPOSITION_PROCESS':'0'}); self.compositor.start()
        self.w=MainWindow(); self.w.autosave_timer.stop(); self.w.show()
    def tearDown(self):self.w.close(); self.app.processEvents(); self.compositor.stop()
    def settle(self,ms=80):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    def test_sound_bin_picker_confirm_search_nested_and_readonly(self):
        from kinetic_cut.sound_picker import SoundBinPicker
        from PySide6.QtWidgets import QDialog
        from PySide6.QtGui import QIcon,QPixmap
        thumbnail=QPixmap(110,65); thumbnail.fill(Qt.green)
        mock_icons=patch.object(self.w.media_panel.audio_thumbnails,'icon',return_value=QIcon(thumbnail)); mock_icons.start(); self.addCleanup(mock_icons.stop)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'cash.wav'; source.write_bytes(b'fixture')
            audio=MediaItem('cash',str(source),'audio','Cash cue',2,has_audio=True)
            self.w.project=Project(media=[audio,MediaItem('offline',str(source)+'missing','audio','Offline',2)])
            panel=self.w.media_panel; old=panel.power.data
            from dataclasses import asdict
            panel.power.data={'folders':['Master','Master/Sounds','Master/Sounds/Cash'],'media':[{'folder':'Master/Sounds/Cash','media':asdict(audio)}]}
            before=copy.deepcopy(panel.power.data); project=self.w.project.to_dict()
            dialog=SoundBinPicker(self.w)
            try:
                self.assertEqual(dialog.rows.topLevelItemCount(),2); self.assertFalse(dialog.confirm.isEnabled())
                self.assertEqual(dialog.rows.topLevelItem(0).text(1),'0:02')
                self.assertEqual(dialog.rows.topLevelItem(0).icon(0).actualSize(thumbnail.size()),thumbnail.size())
                dialog.rows.setCurrentItem(dialog.rows.topLevelItem(0)); self.assertTrue(dialog.confirm.isEnabled())
                self.assertEqual(dialog.path,str(source)); self.assertNotEqual(dialog.result(),QDialog.Accepted)
                dialog.search.setText('missing'); self.assertEqual(dialog.rows.topLevelItemCount(),0); self.assertFalse(dialog.confirm.isEnabled())
                dialog.search.clear()
                nested=dialog.tree.topLevelItem(1).child(0).child(0).child(0)
                dialog.tree.setCurrentItem(nested); self.assertEqual(dialog.rows.topLevelItemCount(),1)
                dialog.rows.setCurrentItem(dialog.rows.topLevelItem(0)); dialog.confirm.click(); self.assertEqual(dialog.result(),QDialog.Accepted)
                self.assertEqual(panel.power.data,before); self.assertEqual(self.w.project.to_dict(),project)
                source.unlink(); dialog.accept(); self.assertFalse(dialog.confirm.isEnabled())
            finally:dialog.close(); dialog.deleteLater(); panel.power.data=old
    def test_audio_subtab_remembers_user_choice_across_all_selections(self):
        p=Project(media=[MediaItem('m','fixture.mp4','video','Source',3,has_audio=True)],timeline=[TimelineItem('v','m','video_1',0,3),TimelineItem('a','m','audio_1',0,3),TimelineItem('b','m','audio_1',4,3)])
        with patch.object(self.w,'request_waveform'):self.w.set_project(p)
        panel=self.w.inspector
        self.assertEqual(panel.audio_subtabs.currentIndex(),0)
        for index in range(3):
            panel.select('a'); panel.audio_subtabs.setCurrentIndex(index)
            panel.select('v'); panel.select(''); panel.select('b')
            self.assertEqual(panel.tabs.currentIndex(),1)
            self.assertEqual(panel.audio_subtabs.currentIndex(),index)
            self.assertTrue(panel.audio.isEnabled()); self.assertTrue(panel.audio_subtabs.widget(1).isEnabled())
    def test_sound_dropdown_routes_confirmed_bin_and_local_file(self):
        from kinetic_cut.motion_editor import MotionEditor
        from PySide6.QtWidgets import QDialog
        item=TimelineItem('graphic','','video_1',0,3,role='graphic',graphic_type='Motion Composition')
        self.w.set_project(Project(timeline=[item])); editor=MotionEditor(self.w,item); editor.show(); self.settle()
        try:
            panel=editor.sound_panel
            self.assertEqual([a.text() for a in panel.add.menu().actions() if not a.isSeparator()],['Media Bin…','Power Bin…','Local file…'])
            with patch('kinetic_cut.sound_picker.SoundBinPicker') as picker,patch.object(panel,'add_path') as add:
                picker.return_value.exec.return_value=QDialog.Accepted; picker.return_value.path='cash.wav'
                panel.add.menu().actions()[1].trigger(); add.assert_called_once_with('cash.wav')
                self.assertEqual(picker.call_args.args[1],'power'); add.reset_mock()
                picker.return_value.exec.return_value=QDialog.Rejected; panel.choose_bin('project'); add.assert_not_called()
            with patch('kinetic_cut.motion_audio_ui.QFileDialog.getOpenFileName',return_value=('local.wav','')),patch.object(panel,'add_path') as add:
                panel.add.menu().actions()[-1].trigger(); add.assert_called_once_with('local.wav')
        finally:editor.reject(); editor.deleteLater(); self.settle()
    def test_source_browser_index_search_and_timeline_click_no_edit(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(transcripts.config,'CACHE_DIR',Path(folder)/'cache'):
            import wave
            source=Path(folder)/'a.wav'
            with wave.open(str(source),'wb') as stream:stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000); stream.writeframes(b'\0\0'*8000)
            media=MediaItem('m',str(source),'audio','Imported speech',30,has_audio=True)
            p=Project(media=[media],timeline=[TimelineItem('a','m','audio_1',5,5,10)])
            stamp=transcripts.identity(media,self.w.settings); file=transcripts.cache_path(stamp); file.parent.mkdir(parents=True)
            file.write_text(json.dumps(dict(source=stamp,timing='word',segments=[dict(text='Watch price',start=11,end=12,words=[])])))
            self.w.set_project(p); self.w.timeline.select_ids({'a'},'a'); self.w.inspector.select('a')
            panel=self.w.inspector.transcript_panel; panel.query.setText('watch')
            self.w.inspector.tabs.setCurrentIndex(1); self.w.inspector.audio_subtabs.setCurrentWidget(panel)
            for _ in range(30):
                self.settle()
                if panel.rows.count():break
            self.assertEqual(panel.rows.count(),1); before=revision(p)
            with patch.object(self.w,'seek') as seek:panel.activate(panel.rows.item(0)); seek.assert_called_once_with(6)
            self.assertEqual(revision(p),before)
            self.w.timeline.select_ids(set()); self.w.inspector.select('')
            self.assertTrue(self.w.inspector.tabs.isTabEnabled(1)); self.assertEqual(panel.source.count(),1)
            # The fixture owns a real source file. Retire its metadata/waveform
            # readers before TemporaryDirectory deletes it, rather than waiting
            # until tearDown (which runs after this with-block has already left).
            import time
            from PySide6.QtCore import QThreadPool,QEvent
            self.w.close();deadline=time.monotonic()+10
            while (self.w._workers or self.w.isVisible()) and time.monotonic()<deadline:self.settle(10)
            self.assertFalse(self.w._workers);self.assertFalse(self.w.isVisible())
            self.assertTrue(QThreadPool.globalInstance().waitForDone(10000))
            self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
    def test_tools_discovery_and_atomic_caption_anchoring_guards(self):
        api=EditorAPI(self.w)
        names={t['name'] for t in TOOLS}
        self.assertTrue({'search_transcripts','generate_source_transcripts','review_caption_timing','anchor_captions_to_video','add_motion_sound_cue','review_edit','create_edit_contact_sheet','get_edit_contact_sheet'}<=names)
        p=Project(media=[MediaItem('m','fixture.mp4','video','source',3,320,180)],timeline=[TimelineItem('web','m','video_1',0,3,transform=Transform(.5,.3,.4))],captions=[Caption('c',0,1,'Hi')])
        p.settings.width=320; p.settings.height=568; p.captions[0].style.size=14; self.w.set_project(p)
        with self.assertRaises(ValueError):api.call_anchor_captions_to_video('stale','video_1',['c'])
        before=p.to_dict(); result=api.call_anchor_captions_to_video(revision(p),'video_1',['c'],5)
        self.assertTrue(result['undoable']); self.assertEqual(p.to_dict(),before)
        self.assertTrue(self.w.project.captions[0].customize)
        api.call_history('undo'); self.assertFalse(self.w.project.captions[0].customize)
        self.w.project.track_states['subtitle_1']={'locked':True}
        with self.assertRaises(ValueError):api.call_anchor_captions_to_video(revision(self.w.project),'video_1',['c'])
    def test_composition_sound_history_timeline_and_cancel_are_local(self):
        from kinetic_cut.motion_editor import MotionEditor
        from kinetic_cut.motion import validate
        scene=validate(dict(canvas=[320,568],nodes=[dict(id='g',kind='rectangle',start=.5,end=2)]))
        item=TimelineItem('g','','video_1',0,3,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':scene},transform=Transform(.5,.5))
        p=Project(timeline=[item]); self.w.set_project(p); before=p.to_dict(); dialog=MotionEditor(self.w,item); dialog.show()
        try:
            panel=dialog.sound_panel; dialog.begin_edit(); dialog.scene['sound_cues']=[dict(id='s',source='cash.wav',time=1,in_point=0,duration=1,source_duration=2,gain_db=-3,event='layer_start',node_id='g')]; dialog.end_edit(); panel.refresh()
            self.assertIn(('__sound__s','sound'),dialog.timeline.rows); self.assertEqual(panel.rows.count(),1)
            dialog.local_history(-1); self.assertNotIn('sound_cues',dialog.scene)
            dialog.local_history(1); self.assertEqual(len(dialog.scene['sound_cues']),1)
            dialog.select_node('g'); dialog.remove(); self.assertEqual(dialog.scene['sound_cues'],[])
            dialog.reject(); self.assertEqual(p.to_dict(),before)
        finally:dialog.reject()
    def test_transcript_jobs_cancel_settle_and_never_change_project(self):
        from kinetic_cut.transcript_ui import service
        p=Project(media=[MediaItem('m','source.wav','audio','Speech',3,has_audio=True)])
        with patch.object(self.w,'request_waveform'):self.w.set_project(p)
        before=revision(p); jobs=[]; svc=service(self.w)
        with patch.object(self.w,'start_worker',side_effect=jobs.append):
            job=svc.start(['m']); worker=jobs[-1]
            with self.assertRaises(ValueError):svc.start(['m'])
            svc.cancel(job['id']); worker.signals.result.emit([dict(media_id='m')]); worker.signals.finished.emit()
            self.assertEqual(svc.jobs[job['id']]['state'],'Cancelled'); self.assertFalse(svc.jobs[job['id']]['cancellable'])
            with self.assertRaises(ValueError):svc.cancel(job['id'])
            success=svc.start(['m']); jobs[-1].signals.result.emit([]); jobs[-1].signals.finished.emit()
            self.assertEqual(svc.jobs[success['id']]['state'],'Complete'); self.assertEqual(revision(p),before)
            self.w._closing=True
            with self.assertRaises(ValueError):svc.start(['m'])
            self.w._closing=False
    def test_sound_import_rejects_stale_project_and_cancel_without_partial_scene(self):
        from kinetic_cut.motion import default_scene
        item=TimelineItem('g','','video_1',0,3,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':default_scene()},transform=Transform(.5,.5))
        p=Project(timeline=[item]); self.w.set_project(p); api=EditorAPI(self.w); jobs=[]
        result=dict(source='cash.wav',source_duration=1,in_point=.1,duration=.5,peaks=[.1])
        with patch.object(self.w,'start_worker',side_effect=jobs.append):
            stale=api.call_add_motion_sound_cue(revision(p),'g','cash.wav',.5); p.name='Changed during import'
            jobs[-1].signals.result.emit(copy.deepcopy(result)); jobs[-1].signals.finished.emit()
            self.assertEqual(api.jobs[stale['id']]['state'],'Failed'); self.assertNotIn('sound_cues',item.graphic_data['scene'])
            cancelled=api.call_add_motion_sound_cue(revision(p),'g','cash.wav',.5); api.call_motion_sound_job_control(cancelled['id'])
            jobs[-1].signals.result.emit(copy.deepcopy(result)); jobs[-1].signals.finished.emit()
            self.assertEqual(api.jobs[cancelled['id']]['state'],'Cancelled'); self.assertNotIn('sound_cues',item.graphic_data['scene'])

if __name__=='__main__':unittest.main()
