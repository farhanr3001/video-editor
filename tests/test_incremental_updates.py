import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from kinetic_cut import update_files as f, updates
from kinetic_cut.version import REPOSITORY
from scripts.build_update import build


class IncrementalUpdates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base / 'installed'; self.root.mkdir()
        self.payloads = self.base / 'release'
        self.cancel = threading.Event()

    def release(self, version, content, previous=None):
        stage = self.base / ('stage-' + version); stage.mkdir()
        for name, value in content.items():
            path = stage / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
        output = self.payloads / version
        manifest = build(stage, output, version, previous)
        return manifest, stage, output / 'update-payloads'

    def install(self, stage):
        import shutil
        shutil.copytree(stage, self.root, dirs_exist_ok=True)

    def job(self, manifest, payloads):
        return f.stage_update(self.root, manifest, f.plan(self.root, manifest), self.base / 'download', self.cancel, local_payloads=payloads)

    def test_changed_files_only_and_skipped_versions_preserve_user_data(self):
        old, stage, _ = self.release('1.0.0', {'KineticCut.exe':b'old', '_internal/model.bin':b'x'*400000, '_internal/old.txt':b'obsolete'})
        self.install(stage)
        personal = self.root / 'my-project.kcut'; personal.write_bytes(b'project')
        settings = self.base / 'settings.json'; settings.write_bytes(b'theme')
        power = self.base / 'powerbins.json'; power.write_bytes(b'media')
        component = self.base / 'components/model.bin'; component.parent.mkdir(); component.write_bytes(b'optional')
        model = self.root / '_internal/model.bin'; timestamp = model.stat().st_mtime_ns
        new, _, payloads = self.release('1.0.3', {'KineticCut.exe':b'new', '_internal/model.bin':b'x'*400000, '_internal/new.txt':b'added'}, old)
        selected = f.plan(self.root, new)
        self.assertNotIn('_internal/model.bin', selected['changed'])
        self.assertLess(selected['download_bytes'], sum(x['size'] for x in new['bundles'].values()))
        f.apply_job(self.job(new, payloads))
        self.assertEqual(model.stat().st_mtime_ns, timestamp)
        self.assertEqual((self.root/'KineticCut.exe').read_bytes(), b'new')
        self.assertFalse((self.root/'_internal/old.txt').exists())
        self.assertEqual([p.read_bytes() for p in (personal, settings, power, component)], [b'project',b'theme',b'media',b'optional'])
        self.assertFalse((self.root/f.JOURNAL).exists())
        with self.assertRaises(ValueError):f.plan(self.root, new)

    def test_payload_groups_are_deterministic_and_reused(self):
        content = {'KineticCut.exe':b'app', '_internal/model.bin':b'x'*400000}
        first, _, _ = self.release('1.0.0', content)
        second, _, folder = self.release('1.0.1', content, first)
        self.assertEqual(first['bundles'], second['bundles'])
        self.assertFalse(list(folder.glob('*.zip')))

    def test_cancel_and_corrupted_archive_do_not_modify_install(self):
        old, stage, _ = self.release('1.0.0', {'KineticCut.exe':b'old'}); self.install(stage)
        new, _, payloads = self.release('1.0.1', {'KineticCut.exe':b'new'})
        self.cancel.set()
        with self.assertRaises(InterruptedError):self.job(new, payloads)
        self.cancel.clear(); archive = next(payloads.glob('*.zip')); archive.write_bytes(b'broken')
        with self.assertRaises(ValueError):self.job(new, payloads)
        self.assertEqual((self.root/'KineticCut.exe').read_bytes(), b'old')
        self.assertFalse((self.base/'download/files').exists())

    def test_bad_members_and_path_traversal_rejected(self):
        for name in ('../other', '_internal/../other', '_internal/a\\b', '_internal/CON.txt', '_internal/a:stream', 'project.kcut', '_internal/private.kcut'):
            with self.assertRaises(ValueError):f.valid_name(name)
        new, _, payloads = self.release('1.0.1', {'KineticCut.exe':b'new'})
        archive = next(payloads.glob('*.zip'))
        with zipfile.ZipFile(archive, 'w') as z:z.writestr('../escape.exe',b'new')
        checksum = f.digest(archive); item = next(iter(new['bundles'].values()))
        new['bundles'] = {checksum:dict(item,sha256=checksum,size=archive.stat().st_size)}
        new['files']['KineticCut.exe']['bundle'] = checksum
        archive.rename(payloads/('KineticCut-Part-'+checksum+'.zip'))
        with self.assertRaises(ValueError):self.job(new, payloads)
        self.assertFalse((self.base/'escape.exe').exists())

    def test_failed_startup_restores_old_added_and_removed_files(self):
        old, stage, _ = self.release('1.0.0', {'KineticCut.exe':b'old','_internal/old.txt':b'old'}); self.install(stage)
        new, _, payloads = self.release('1.0.1', {'KineticCut.exe':b'new','_internal/new.txt':b'new'})
        with self.assertRaises(RuntimeError):f.apply_job(self.job(new,payloads),verify=lambda: (_ for _ in ()).throw(RuntimeError('startup failed')))
        f.verify_install(self.root, old)
        self.assertFalse((self.root/'_internal/new.txt').exists())
        self.assertEqual(json.loads((self.root/f.MANIFEST).read_text()),old)

    def test_partial_replacement_failure_restores_files(self):
        old, stage, _ = self.release('1.0.0', {'KineticCut.exe':b'old'}); self.install(stage)
        new, _, payloads = self.release('1.0.1', {'KineticCut.exe':b'new','_internal/new.txt':b'new'})
        count = 0
        def replacement(source, target):
            nonlocal count
            count += 1
            if count == 2:raise PermissionError('locked file')
            source.replace(target)
        with self.assertRaises(PermissionError):f.apply_job(self.job(new,payloads),replace=replacement)
        f.verify_install(self.root, old)
        self.assertFalse((self.root/'_internal/new.txt').exists())

    def test_interrupted_transaction_recovery_and_changed_preconditions(self):
        old, stage, _ = self.release('1.0.0', {'KineticCut.exe':b'old'}); self.install(stage)
        changed = {'KineticCut.exe':dict(sha256=hashlib.sha256(b'new').hexdigest())}
        expected = {'KineticCut.exe':f.digest(self.root/'KineticCut.exe')}
        f.prepare_transaction(self.root, changed, expected)
        (self.root/'KineticCut.exe').write_bytes(b'new'); f.rollback(self.root)
        self.assertEqual((self.root/'KineticCut.exe').read_bytes(), b'old')
        (self.root/'KineticCut.exe').write_bytes(b'other')
        with self.assertRaises(RuntimeError):f.prepare_transaction(self.root, changed, expected)

    def test_tampered_job_cannot_delete_unknown_files_or_publish_incomplete_install(self):
        old, stage, _ = self.release('1.0.0', {'KineticCut.exe':b'old'}); self.install(stage)
        new, _, payloads = self.release('1.0.1', {'KineticCut.exe':b'new','_internal/new.txt':b'new'})
        job = self.job(new,payloads); data = json.loads(job.read_text())
        data['removed']['_internal/unknown.txt'] = 'a'*64; f.write_json(job,data)
        with self.assertRaises(ValueError):f.apply_job(job)
        data['removed'] = {}; data['changed'].pop('_internal/new.txt'); data['expected'].pop('_internal/new.txt'); f.write_json(job,data)
        with self.assertRaises(RuntimeError):f.apply_job(job)
        f.verify_install(self.root, old)

    def test_manifest_http_digest_channel_and_size_verification(self):
        manifest, _, _ = self.release('9.0.0', {'KineticCut.exe':b'app'})
        raw = json.dumps(manifest).encode()
        data = dict(tag_name='v9.0.0',assets=[dict(name='KineticCut-Update-9.0.0.json',size=len(raw),digest='sha256:'+hashlib.sha256(raw).hexdigest(),browser_download_url=f'https://github.com/{REPOSITORY}/releases/download/v9.0.0/update.json')])
        calls = [json.dumps(data).encode(), raw]
        release = updates.check(opener=lambda *a, **k:io.BytesIO(calls.pop(0)))
        self.assertTrue(release.incremental); self.assertEqual(release.manifest,manifest)
        calls = [json.dumps(data).encode(), b'bad']
        with self.assertRaises(ValueError):updates.check(opener=lambda *a, **k:io.BytesIO(calls.pop(0)))
        bad = copy.deepcopy(manifest); next(iter(bad['bundles'].values()))['url'] = 'https://evil.example/model.zip'
        with self.assertRaises(ValueError):f.validate_manifest(bad)

    def test_legacy_migration_checks_complete_baseline_and_rolls_back(self):
        from kinetic_cut.update_helper import native_prepare
        old, stage, _ = self.release('1.1.0', {'KineticCut.exe':b'old'}); self.install(stage)
        (self.root/f.MANIFEST).unlink(); (self.root/f.INVENTORY).unlink()
        baseline = self.base/'baseline.json'; f.write_json(baseline,dict(files=old['files']))
        new, new_stage, _ = self.release('1.1.1', {'KineticCut.exe':b'new'})
        native_prepare(self.root,new_stage/f.MANIFEST,baseline)
        (self.root/'KineticCut.exe').write_bytes(b'new'); f.rollback(self.root)
        self.assertEqual((self.root/'KineticCut.exe').read_bytes(),b'old')
        (self.root/'KineticCut.exe').write_bytes(b'custom')
        with self.assertRaises(RuntimeError):native_prepare(self.root,new_stage/f.MANIFEST,baseline)


if __name__ == '__main__':unittest.main()
