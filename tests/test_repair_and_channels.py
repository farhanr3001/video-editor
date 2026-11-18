import hashlib,io,json,threading,unittest
from unittest.mock import patch
import test_incremental_updates as fixtures
from kinetic_cut import updates,update_files as f

class Repair(unittest.TestCase):
    setUp=fixtures.IncrementalUpdates.setUp
    release=fixtures.IncrementalUpdates.release
    install=fixtures.IncrementalUpdates.install
    def test_same_version_repairs_missing_files_with_explicit_intent(self):
        manifest,stage,payload=self.release('1.1.31',{'KineticCut.exe':b'good','_internal/tool.dll':b'original'})
        self.install(stage);(self.root/'_internal/tool.dll').unlink()
        sentinel=self.root/'personal.kcut';sentinel.write_bytes(b'project')
        selection=f.plan(self.root,manifest,repair=True)
        job=f.stage_update(self.root,manifest,selection,self.base/'repair',self.cancel,local_payloads=payload)
        with self.assertRaises(ValueError):f.apply_job(job)
        f.apply_job(job,repair_version='1.1.31');f.verify_install(self.root,manifest);self.assertEqual(sentinel.read_bytes(),b'project')
    def test_corrupt_local_inventory_can_be_repaired_without_trusting_it(self):
        manifest,stage,payload=self.release('1.1.31',{'KineticCut.exe':b'good'})
        self.install(stage);(self.root/f.MANIFEST).write_text('{broken');(self.root/'KineticCut.exe').write_bytes(b'bad')
        selected=f.plan(self.root,manifest,repair=True);job=f.stage_update(self.root,manifest,selected,self.base/'repair',self.cancel,local_payloads=payload)
        f.apply_job(job,repair_version='1.1.31');f.verify_install(self.root,manifest)
    def test_repair_does_not_allow_a_version_downgrade(self):
        manifest,stage,payload=self.release('1.1.32',{'KineticCut.exe':b'new'});self.install(stage)
        older,_,_=self.release('1.1.31',{'KineticCut.exe':b'old'})
        with self.assertRaises(ValueError):f.plan(self.root,older,repair=True)
    def test_missing_repair_helper_uses_verified_full_installer(self):
        from kinetic_cut import application_repair
        manifest,stage,_=self.release('1.1.31',{'KineticCut.exe':b'good','KineticCutUpdater.exe':b'helper'})
        self.install(stage);(self.root/'KineticCutUpdater.exe').unlink()
        release=updates.Release('1.1.31','', 'a'*64,1,manifest=manifest,incremental=True)
        with patch.object(updates,'repair_release',return_value=release),patch.object(updates,'repair_installer',return_value=release),patch.object(updates,'download',return_value=self.base/'setup.exe') as download:
            result=application_repair.prepare(self.root,self.cancel)
        self.assertFalse(result['incremental']);download.assert_called_once();self.assertEqual((self.root/'KineticCut.exe').read_bytes(),b'good')
    def test_healthy_application_does_not_download_or_modify_anything(self):
        from kinetic_cut import application_repair
        manifest,stage,_=self.release('1.1.31',{'KineticCut.exe':b'good','KineticCutUpdater.exe':b'helper'})
        self.install(stage);release=updates.Release('1.1.31','', 'a'*64,1,manifest=manifest,incremental=True)
        with patch.object(updates,'repair_release',return_value=release),patch.object(updates,'download',side_effect=AssertionError('No repair needed')):
            self.assertIsNone(application_repair.prepare(self.root,self.cancel))
    def test_repair_keeps_unpublished_local_improvements(self):
        from kinetic_cut import application_repair
        public,_,_=self.release('1.1.31',{'KineticCut.exe':b'public','KineticCutUpdater.exe':b'helper'})
        # A developer-local inventory accurately describes a different working EXE.
        local=dict(public,files=dict(public['files']));local['files']['KineticCut.exe']=dict(public['files']['KineticCut.exe'],sha256=hashlib.sha256(b'local').hexdigest(),size=5)
        self.root.mkdir(exist_ok=True);(self.root/'KineticCut.exe').write_bytes(b'local');(self.root/'KineticCutUpdater.exe').write_bytes(b'helper')
        f.write_json(self.root/f.MANIFEST,local)
        release=updates.Release('1.1.31','', 'a'*64,1,manifest=public,incremental=True)
        with patch.object(updates,'repair_release',return_value=release),patch.object(updates,'download',side_effect=AssertionError('Local work must not be reverted')):
            self.assertTrue(application_repair.prepare(self.root,self.cancel)['unpublished'])
    def test_abandoned_job_cleanup_preserves_resumable_cache_and_other_directories(self):
        from kinetic_cut import config
        cache=self.base/'cache';folder=cache/'updates'/('pending-'+'a'*32);stage=folder/'files';stage.mkdir(parents=True)
        (stage/'KineticCut.exe').write_bytes(b'staged');job=folder/'job.json';f.write_json(job,dict(stage=str(stage)))
        payload=cache/'updates/payloads';payload.mkdir();archive=payload/('b'*64+'.zip');archive.write_bytes(b'verified')
        with patch.object(config,'CACHE_DIR',cache):
            self.assertTrue(f.discard_staged(job));self.assertFalse(stage.exists());self.assertTrue(archive.exists())
            private=self.base/'personal';private.mkdir();(private/'keep.kcut').write_bytes(b'project')
            self.assertFalse(f.discard_staged(private/'job.json'));self.assertTrue((private/'keep.kcut').exists())
    def test_official_repair_inventory_must_match_exact_version_and_digest(self):
        manifest,_,_=self.release('1.1.31',{'KineticCut.exe':b'good'});raw=json.dumps(manifest).encode()
        data=dict(tag_name='v1.1.31',assets=[dict(name='KineticCut-Inventory-1.1.31.json',size=len(raw),digest='sha256:'+hashlib.sha256(raw).hexdigest(),browser_download_url=f'https://github.com/{updates.REPOSITORY}/releases/download/v1.1.31/inventory.json')])
        values=[json.dumps(data).encode(),raw]
        release=updates.repair_release('1.1.31',lambda *a,**k:io.BytesIO(values.pop(0)));self.assertEqual(release.manifest,manifest)
        values=[json.dumps(data).encode(),b'corrupt']
        with self.assertRaises(ValueError):updates.repair_release('1.1.31',lambda *a,**k:io.BytesIO(values.pop(0)))

class Channels(unittest.TestCase):
    def release(self,version,preview=False):
        return dict(tag_name='v'+version,prerelease=preview,assets=[dict(name=f'KineticCut-Setup-{version}.exe',size=5,digest='sha256:'+'a'*64,browser_download_url=f'https://github.com/{updates.REPOSITORY}/releases/download/v{version}/setup.exe')])
    def test_stable_ignores_preview_and_preview_is_explicit(self):
        self.assertIsNone(updates.parse_release(self.release('9.0.0',True)))
        self.assertTrue(updates.parse_release(self.release('9.0.0',True),allow_preview=True).preview)
        entries=[self.release('9.0.1',True),self.release('9.0.0')]
        result=updates.check('1.0.0',lambda *a,**k:io.BytesIO(json.dumps(entries).encode()),channel='preview')
        self.assertEqual(result.version,'9.0.1');self.assertTrue(result.preview)
    def test_preview_never_selects_drafts_or_downgrades(self):
        draft=self.release('99.0.0',True);draft['draft']=True
        data=[draft,self.release('1.0.0')]
        self.assertIsNone(updates.check('2.0.0',lambda *a,**k:io.BytesIO(json.dumps(data).encode()),channel='preview'))
