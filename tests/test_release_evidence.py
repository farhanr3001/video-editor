import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import release_gate as gate

class ReleaseEvidence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        for p in (patch.object(gate,'ROOT',self.root),patch.object(gate,'fingerprint',return_value='current')):
            p.start();self.addCleanup(p.stop)
        release=self.root/'release';release.mkdir()
        for name in (f'KineticCut-Setup-{gate.VERSION}.exe',f'KineticCut-FullSetup-{gate.VERSION}.exe',f'KineticCut-Update-{gate.VERSION}.json','build-report.json','KineticCut-Baseline-1.1.0.json'):(release/name).write_bytes(b'fixture')
        self.reports={}
        for kind in gate.REQUIRED:
            path=self.root/(kind+'.json');path.write_text(json.dumps(dict(passed=True,source_fingerprint='current',kind=kind,full=kind=='source',exe_sha256='staged-exe')));self.reports[kind]=path
        (release/'build-report.json').write_text(json.dumps(dict(source_fingerprint='current',stage_exe_sha256='staged-exe',
            full_setup_sha256=gate.sha(release/f'KineticCut-FullSetup-{gate.VERSION}.exe'),setup_sha256=gate.sha(release/f'KineticCut-Setup-{gate.VERSION}.exe'))))
        self.output=self.root/'gate.json'
    def test_all_milestones_are_required_and_bound_to_source(self):
        gate.seal(self.output,self.reports);self.assertTrue(gate.validate(self.output)['passed'])
        with patch.object(gate,'fingerprint',return_value='changed'):
            with self.assertRaises(ValueError):gate.validate(self.output)
        with self.assertRaises(ValueError):gate.seal(self.output,{'source':self.reports['source']})
    def test_changed_artifact_or_evidence_invalidates_publication(self):
        gate.seal(self.output,self.reports);self.reports['installed'].write_text('{}')
        with self.assertRaises(ValueError):gate.validate(self.output)
        self.reports['installed'].write_text(json.dumps(dict(passed=True,source_fingerprint='current',kind='installed')))
        gate.seal(self.output,self.reports)
        (self.root/f'release/KineticCut-Setup-{gate.VERSION}.exe').write_bytes(b'changed')
        with self.assertRaises(ValueError):gate.validate(self.output)
    def test_focused_suite_cannot_be_presented_as_complete_checkpoint(self):
        path=self.reports['source'];body=json.loads(path.read_text());body['full']=False;path.write_text(json.dumps(body))
        with self.assertRaises(ValueError):gate.seal(self.output,self.reports)
    def test_new_payload_cannot_bypass_a_sealed_inventory(self):
        gate.seal(self.output,self.reports);folder=self.root/'release/update-payloads';folder.mkdir();(folder/'extra.zip').write_bytes(b'extra')
        with self.assertRaises(ValueError):gate.validate(self.output)
    def test_stale_installer_cannot_borrow_passing_tests_from_a_newer_app(self):
        path=self.root/'release/build-report.json';body=json.loads(path.read_text());body['stage_exe_sha256']='old-exe';path.write_text(json.dumps(body))
        with self.assertRaises(ValueError):gate.seal(self.output,self.reports)
