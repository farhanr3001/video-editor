import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kinetic_cut.model import Project,TimelineItem
from kinetic_cut.exporter import ExportPreset,encoding_options,automatic_bitrate
from kinetic_cut import render_history as history


class RenderHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'edit.kcut'
        self.p=Project(name='Test',timeline=[TimelineItem('title','','video_1',0,2,role='title',title_text='Saved')]);self.p.save(self.path)
        self.job=dict(project=copy.deepcopy(self.p),output=str(self.path.with_suffix('.mp4')),preset=ExportPreset('Custom','h264',15,192,'Custom','auto'),state='Complete',elapsed=12.5,audio=True)
    def tearDown(self):self.temp.cleanup()
    def test_completion_patches_only_history_and_retains_unsaved_edits(self):
        before=json.loads(self.path.read_text());self.p.timeline[0].title_text='Unsaved'
        self.assertTrue(history.add(self.p,self.job));after=json.loads(self.path.read_text());rows=after.pop('render_history');before.pop('render_history')
        self.assertEqual(before,after);self.assertEqual(self.p.timeline[0].title_text,'Unsaved');self.assertEqual(len(rows),1)
        self.assertNotIn('project',rows[0]);self.assertNotIn('timeline',rows[0]);self.assertEqual(rows[0]['preset']['quality'],'auto')
        restored=history.restore(Project.load(self.path).render_history);self.assertEqual(restored[0]['elapsed'],12.5);self.assertEqual(restored[0]['project'].settings.fps,60)
        self.assertFalse(restored[0]['project'].timeline);self.assertEqual(restored[0]['state'],'Complete')
    def test_unsaved_session_later_save_and_removal_roundtrip(self):
        p=Project();self.assertTrue(history.add(p,self.job));p.save(self.path);loaded=Project.load(self.path)
        self.assertEqual(len(loaded.render_history),1);self.assertTrue(history.remove(loaded,loaded.render_history[0]['id']));self.assertEqual(Project.load(self.path).render_history,[])
    def test_failed_atomic_publish_preserves_original_and_leaves_no_temp(self):
        before=self.path.read_bytes()
        with patch('kinetic_cut.render_history.os.replace',side_effect=PermissionError('busy')):self.assertFalse(history.add(self.p,self.job))
        self.assertEqual(self.path.read_bytes(),before);self.assertFalse(list(self.path.parent.glob('*.tmp')));self.assertEqual(len(self.p.render_history),1)
    def test_replaced_project_identity_is_not_overwritten(self):
        other=Project(name='Other');other.save(self.path);before=self.path.read_bytes()
        self.assertFalse(history.add(self.p,self.job));self.assertEqual(self.path.read_bytes(),before)
    def test_history_is_metadata_not_an_edit_or_close_prompt(self):
        from kinetic_cut.close_guard import document_key
        before=document_key(self.p);history.add(self.p,self.job);self.assertEqual(document_key(self.p),before)
    def test_loading_validates_records_deduplicates_and_rejects_pending_jobs(self):
        good=history.completed_record(self.job);bad=copy.deepcopy(good);bad['id']='bad';bad['elapsed']=float('nan')
        queued=dict(good,id='queued',state='Queued');malformed=dict(good,id='malformed',preset={'codec':'h264'})
        values=[good,copy.deepcopy(good),bad,queued,malformed]
        self.assertEqual(len(history.records(values)),1);p=Project.from_dict(dict(render_history=values));self.assertEqual(len(p.render_history),1)
        self.assertEqual(Project.from_dict({'render_history':'bad'}).render_history,[])
    def test_automatic_quality_and_explicit_bitrate_keep_distinct_encoder_modes(self):
        auto=self.job['preset'];manual=ExportPreset('Manual','h264',10,192,'Custom')
        args=encoding_options(auto,'NVIDIA');self.assertEqual(args[args.index('-cq')+1],'19');self.assertEqual(args[args.index('-b:v')+1],'0')
        args=encoding_options(auto,'CPU');self.assertIn('-crf',args);self.assertNotIn('-b:v',args)
        args=encoding_options(manual,'NVIDIA');self.assertEqual(args[args.index('-b:v')+1],'10M');self.assertNotIn('-cq',args)
        self.assertAlmostEqual(automatic_bitrate(self.p.settings),14.92992)
    def test_late_writer_cannot_restore_removed_or_obsolete_history(self):
        history.add(self.p,self.job,publish=False);first=history.issue_write(self.p)
        history.remove(self.p,self.job['history_id'],publish=False);newest=history.issue_write(self.p)
        self.assertTrue(history.publish_write(newest));self.assertTrue(history.publish_write(first))
        self.assertEqual(Project.load(self.path).render_history,[])
