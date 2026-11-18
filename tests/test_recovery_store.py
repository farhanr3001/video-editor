import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kinetic_cut import recovery_store as store,config
from kinetic_cut.model import Project,TimelineItem

class RecoveryCopies(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        for name,path in [('DATA_DIR',self.base/'data'),('CACHE_DIR',self.base/'cache'),('AUTOSAVE_PATH',self.base/'data/recovery.kcut'),('SESSION_LOCK_PATH',self.base/'data/active_session.lock')]:
            p=patch.object(config,name,path);p.start();self.addCleanup(p.stop)
        self.project=Project(name='Example',timeline=[TimelineItem('t','','video_1',0,2,role='title',title_text='First')])
    def test_projects_and_sessions_are_independent_and_originals_unchanged(self):
        original=self.base/'original.kcut';self.project.save(original);before=original.read_bytes()
        a,b=store.session(),store.session();first=store.save(copy.deepcopy(self.project),a)
        other=copy.deepcopy(self.project);other.name='Second';second=store.save(other,b)
        self.assertNotEqual(first,second);self.assertEqual(original.read_bytes(),before)
        self.assertEqual(len(store.entries()),2);self.assertTrue(all(x['active'] for x in store.entries()))
    def test_unchanged_state_not_duplicated_and_history_is_spaced(self):
        token=store.session();path=store.save(self.project,token);stamp=path.stat().st_mtime_ns
        self.project.playhead=1;store.save(self.project,token);self.assertEqual(stamp,path.stat().st_mtime_ns)
        self.project.timeline[0].title_text='Second';store.save(self.project,token)
        self.assertEqual(len(store.entries()),2)
        self.project.timeline[0].title_text='Third';store.save(self.project,token)
        self.assertEqual(len(store.entries()),2)
        body=json.loads(path.read_text());self.assertEqual(body['timeline'][0]['title_text'],'Third')
    def test_active_copies_protected_delete_never_touches_original_or_missing_media(self):
        token=store.session();path=store.save(self.project,token)
        with self.assertRaises(ValueError):store.remove(path)
        original=self.base/'important.kcut';original.write_text('personal')
        with self.assertRaises(ValueError):store.remove(original)
        store.finish(token);store.remove(path);self.assertEqual(original.read_text(),'personal')
    def test_crashed_session_detected_but_normal_close_not_reported_as_crash(self):
        token=store.session();store.save(self.project,token)
        with patch.object(store,'alive',return_value=False):
            self.assertTrue(store.has_crashed());self.assertTrue(store.entries()[0]['crashed'])
        store.finish(token);self.assertFalse(store.has_crashed());self.assertFalse(store.entries()[0]['crashed'])
    def test_explicit_clear_only_removes_inactive_managed_copies(self):
        first=store.session();second=store.session();a=store.save(self.project,first);b=store.save(self.project,second);store.finish(first)
        count,size=store.clear_inactive();self.assertEqual(count,1);self.assertGreater(size,0);self.assertFalse(a.exists());self.assertTrue(b.exists())
    def test_invalid_session_and_failed_publication_preserve_last_good_copy(self):
        with self.assertRaises(ValueError):store.save(self.project,'../../outside')
        token=store.session();path=store.save(self.project,token);before=path.read_bytes()
        self.project.name='Changed'
        with patch.object(Path,'replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):store.save(self.project,token)
        self.assertEqual(path.read_bytes(),before)
    def test_missing_media_is_reported_and_never_causes_automatic_removal(self):
        from kinetic_cut.model import MediaItem
        self.project.media=[MediaItem('missing',str(self.base/'disconnected.mp4'),'video','Missing',3)]
        token=store.session();path=store.save(self.project,token);store.finish(token)
        row=store.entries()[0];self.assertEqual(row['missing'],1);self.assertTrue(path.exists())
    def test_restored_or_deleted_crash_copy_stops_startup_prompt_without_losing_history(self):
        token=store.session();path=store.save(self.project,token)
        marker=store.root()/'sessions'/(token+'.json');store.atomic(marker,dict(pid=2_000_000_000,created=0))
        self.assertTrue(store.has_crashed());store.acknowledge(path)
        self.assertFalse(store.has_crashed());self.assertTrue(path.exists())
        data=json.loads(marker.read_text());data.pop('reviewed');store.atomic(marker,data)
        store.remove(path);self.assertFalse(store.has_crashed())
    def test_legacy_crash_is_discoverable_and_other_live_editor_marker_is_preserved(self):
        config.DATA_DIR.mkdir(parents=True);config.AUTOSAVE_PATH.write_text(json.dumps(self.project.to_dict()));config.SESSION_LOCK_PATH.write_text('pid=2000000000\n')
        self.assertTrue(store.has_crashed());self.assertTrue(store.entries()[0]['crashed'])
        config.SESSION_LOCK_PATH.write_text('pid=12345\n')
        with patch('psutil.pid_exists',return_value=True):store.finish_legacy()
        self.assertTrue(config.SESSION_LOCK_PATH.exists())

    def test_native_diagnostic_uses_current_session_and_checks_actual_edit(self):
        from types import SimpleNamespace
        from kinetic_cut.freeze_interaction_diagnostics import saved_session_recovery
        token=store.session();other=store.session()
        path=store.save(self.project,token)
        foreign=copy.deepcopy(self.project);foreign.name='Other window';store.save(foreign,other)
        window=SimpleNamespace(_recovery_session=token,compounds=SimpleNamespace(root=lambda:self.project))
        store.finish(token)
        self.assertEqual(saved_session_recovery(window),path)
        self.project.timeline[0].title_text='Unsaved later edit'
        with self.assertRaisesRegex(AssertionError,'latest edit'):saved_session_recovery(window)

    def test_native_diagnostic_rejects_legacy_copy_and_unretired_session(self):
        from types import SimpleNamespace
        from kinetic_cut.freeze_interaction_diagnostics import saved_session_recovery
        config.DATA_DIR.mkdir(parents=True);config.AUTOSAVE_PATH.write_text(json.dumps(self.project.to_dict()))
        token=store.session();window=SimpleNamespace(_recovery_session=token,compounds=SimpleNamespace(root=lambda:self.project))
        with self.assertRaisesRegex(AssertionError,'one latest recovery'):saved_session_recovery(window)
        store.save(self.project,token)
        with self.assertRaisesRegex(AssertionError,'retire'):saved_session_recovery(window)
