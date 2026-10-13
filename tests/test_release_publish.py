"""Installer checkpoint discovery must not accidentally use the old delta path."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PublishTests(unittest.TestCase):
    def fixture(self, root):
        release=root/'release';release.mkdir()
        for name in ('KineticCut-Setup-9.0.0.exe','KineticCut-FullSetup-9.0.0.exe',
                     'KineticCut-Update-9.0.0.json','KineticCut-Baseline-1.1.0.json','components.json'):
            (release/name).write_bytes(b'full payload' if 'FullSetup' in name else b'old')
        (release/'build-report.json').write_text('{}')
        spec=importlib.util.spec_from_file_location('release_publisher',Path(__file__).resolve().parents[1]/'scripts/publish_release.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.ROOT=root;module.VERSION='9.0.0';return module

    def test_full_installer_channel_has_no_discovery_manifest(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);module=self.fixture(root);uploaded=[]
            release=dict(tag_name='v9.0.0',assets_url='https://api.example/assets',upload_url='https://upload.example/{name}',html_url='https://example/release',draft=True)
            def opener(request, **kwargs):
                if request.full_url.endswith('/releases'):value=[release]
                elif 'api.example/assets' in request.full_url:value=[]
                else:
                    name=request.full_url.split('?name=')[1];uploaded.append(name)
                    content=request.data.read();value=dict(name=name,size=len(content),digest='sha256:'+hashlib.sha256(content).hexdigest())
                return io.BytesIO(json.dumps(value).encode())
            with patch.object(module,'credentials',return_value='test'),patch.object(module.sys,'argv',['publish','--installer-update']),patch.object(module.urllib.request,'urlopen',side_effect=opener):
                module.main()
            self.assertNotIn('KineticCut-Update-9.0.0.json',uploaded)
            self.assertIn('KineticCut-Inventory-9.0.0.json',uploaded)
            self.assertEqual((root/'release/KineticCut-Setup-9.0.0.exe').read_bytes(),b'full payload')
            self.assertEqual(json.loads((root/'release/build-report.json').read_text())['update_channel'],'full-installer')

    def test_existing_incremental_manifest_blocks_checkpoint_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            module=self.fixture(Path(tmp))
            release=dict(tag_name='v9.0.0',assets_url='https://api.example/assets')
            def opener(request, **kwargs):
                value=[release] if request.full_url.endswith('/releases') else [dict(name='KineticCut-Update-9.0.0.json')]
                return io.BytesIO(json.dumps(value).encode())
            with patch.object(module,'credentials',return_value='test'),patch.object(module.sys,'argv',['publish','--installer-update']),patch.object(module.urllib.request,'urlopen',side_effect=opener):
                with self.assertRaisesRegex(RuntimeError,'incremental-channel'):module.main()


if __name__=='__main__':unittest.main()
