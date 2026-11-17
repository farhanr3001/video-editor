"""Only exact-install helpers may be retired; lock failures precede mutation."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from kinetic_cut import update_helper as h
import test_incremental_updates as fixtures


class UpdateLocking(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'install';self.root.mkdir()

    def process(self,pid,args):
        process=Mock(pid=pid);process.exe.return_value=str(self.root/'KineticCut.exe')
        process.cmdline.return_value=['KineticCut.exe',*args];return process

    def test_installation_filter_excludes_updater_other_install_and_foreign_programs(self):
        import os
        paths=[self.root/'KineticCut.exe',self.root/'KineticCutUpdater.exe',self.root/'other.exe',
               self.root.parent/'elsewhere/KineticCut.exe',self.root/'KineticCut.old-bridge.exe']
        processes=[Mock(pid=os.getpid()+i+10,info=dict(exe=str(path),cmdline=['--mcp-bridge'])) for i,path in enumerate(paths)]
        with patch('psutil.process_iter',return_value=processes):
            self.assertEqual([p for p,_ in h.installation_processes(self.root)],[processes[0],processes[4]])

    def test_idle_bridge_is_terminated_only_after_identity_recheck(self):
        bridge=self.process(10,['--mcp-bridge'])
        with patch.object(h,'installation_processes',side_effect=[[(bridge,bridge.cmdline())],[]]),patch.object(h,'request_editor_close',return_value=set()),patch.object(h.time,'sleep'):
            h.wait_installation(self.root)
        bridge.terminate.assert_called_once()

    def test_changed_identity_is_not_terminated(self):
        bridge=self.process(10,['--mcp-bridge']);bridge.exe.return_value=str(self.root.parent/'other/KineticCut.exe')
        with patch.object(h,'installation_processes',side_effect=[[(bridge,bridge.cmdline())],[]]),patch.object(h,'request_editor_close',return_value=set()),patch.object(h.time,'sleep'):
            h.wait_installation(self.root)
        bridge.terminate.assert_not_called()

    def test_visible_editor_save_prompt_prevents_any_forced_termination(self):
        editor=self.process(11,[]);bridge=self.process(10,['--mcp-bridge'])
        with patch.object(h,'installation_processes',return_value=[(editor,editor.cmdline()),(bridge,bridge.cmdline())]),patch.object(h,'request_editor_close',return_value={11}) as close:
            with self.assertRaisesRegex(h.ApplicationBusy,'saving'):h.wait_installation(self.root,timeout=0)
        close.assert_called_once();editor.terminate.assert_not_called();bridge.terminate.assert_not_called()

    def test_workers_get_time_to_exit_normally(self):
        worker=self.process(12,['--multiprocessing-fork'])
        with patch.object(h,'installation_processes',side_effect=[[(worker,worker.cmdline())],[]]),patch.object(h,'request_editor_close',return_value=set()),patch.object(h.time,'sleep'):
            h.wait_installation(self.root)
        worker.terminate.assert_not_called()

    def test_lingering_known_worker_is_retired_after_grace(self):
        worker=self.process(12,['--multiprocessing-fork'])
        with patch.object(h,'installation_processes',side_effect=[[(worker,worker.cmdline())],[]]),patch.object(h,'request_editor_close',return_value=set()),patch.object(h.time,'monotonic',side_effect=[0,4,4]),patch.object(h.time,'sleep'):
            h.wait_installation(self.root)
        worker.terminate.assert_called_once()

    def test_unknown_headless_command_is_not_killed(self):
        unknown=self.process(13,['--something-else'])
        with patch.object(h,'installation_processes',return_value=[(unknown,unknown.cmdline())]),patch.object(h,'request_editor_close',return_value=set()):
            with self.assertRaises(h.ApplicationBusy):h.wait_installation(self.root,timeout=0)
        unknown.terminate.assert_not_called()

    def test_transient_replace_retries_and_permanent_lock_is_bounded(self):
        with patch.object(h.os,'name','nt'),patch.object(h.os,'replace',side_effect=[PermissionError('busy'),None]) as replace,patch.object(h.time,'sleep'):
            h.replace_with_retry('a','b');self.assertEqual(replace.call_count,2)
        with patch.object(h.os,'replace',side_effect=PermissionError('busy')) as replace:
            with self.assertRaises(PermissionError):h.replace_with_retry('a','b',timeout=0)
            self.assertEqual(replace.call_count,1)

    def test_installer_quiesce_does_not_replace_files_or_restart(self):
        with patch.object(h,'wait_installation') as wait,patch.object(h.files,'apply_job') as apply,patch.object(h.subprocess,'Popen') as launch:
            self.assertEqual(h.run(['quiesce',str(self.root),'--no-restart','--quiet']),0)
        wait.assert_called_once_with(self.root);apply.assert_not_called();launch.assert_not_called()

    def test_unrelated_errors_are_not_retried(self):
        with patch.object(h.os,'replace',side_effect=FileNotFoundError()) as replace:
            with self.assertRaises(FileNotFoundError):h.replace_with_retry('a','b')
            self.assertEqual(replace.call_count,1)

    def test_busy_update_does_not_restart_a_second_editor(self):
        job=self.root.parent/'job.json';job.write_text(json.dumps(dict(root=str(self.root))))
        with patch.object(h,'wait_process'),patch.object(h.files,'apply_job',side_effect=h.ApplicationBusy('still busy')),patch.object(h.subprocess,'Popen') as launch:
            self.assertEqual(h.run(['apply',str(job),'--quiet']),1)
        launch.assert_not_called();self.assertTrue((job.parent/'update-error.log').exists())


class UpdatePreflight(unittest.TestCase):
    # Reuse the real verified-download fixture, not a mocked transaction.
    setUp=fixtures.IncrementalUpdates.setUp
    release=fixtures.IncrementalUpdates.release
    install=fixtures.IncrementalUpdates.install
    job=fixtures.IncrementalUpdates.job
    def test_busy_preflight_does_not_create_journal_or_mutate_any_file(self):
        old,stage,_=self.release('1.0.0',{'KineticCut.exe':b'old'});self.install(stage)
        new,_,payloads=self.release('1.0.1',{'KineticCut.exe':b'new'})
        before=Mock(side_effect=h.ApplicationBusy('in use'))
        with self.assertRaises(h.ApplicationBusy):
            h.files.apply_job(self.job(new,payloads),before_apply=before)
        before.assert_called_once();h.files.verify_install(self.root,old)
        self.assertFalse((self.root/h.files.JOURNAL).exists())

    def test_tampered_job_never_closes_processes(self):
        old,stage,_=self.release('1.0.0',{'KineticCut.exe':b'old'});self.install(stage)
        new,_,payloads=self.release('1.0.1',{'KineticCut.exe':b'new'})
        job=self.job(new,payloads);data=json.loads(job.read_text());data['removed']['_internal/unknown.txt']='a'*64;h.files.write_json(job,data)
        before=Mock()
        with self.assertRaises(ValueError):h.files.apply_job(job,before_apply=before)
        before.assert_not_called()


if __name__=='__main__':unittest.main()
