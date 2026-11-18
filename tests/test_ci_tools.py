"""Clean CI uses the release's tools, never an unpinned machine-wide install."""
import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from scripts import prepare_ci_tools as tools


class CiTools(unittest.TestCase):
    def test_bounded_copy_requires_exact_length(self):
        for data,size in ((b'abc',2),(b'a',2)):
            with self.assertRaises(ValueError):tools.bounded_copy(io.BytesIO(data),io.BytesIO(),size)
        target=io.BytesIO();tools.bounded_copy(io.BytesIO(b'abc'),target,3);self.assertEqual(target.getvalue(),b'abc')

    def fixture(self):
        data=b'owned tool fixture';raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as archive:
            archive.writestr('_internal/assets/tools/ffmpeg.exe',data)
            archive.writestr('../outside.txt',b'must not extract')
        blob=raw.getvalue()
        spec=dict(sha256=hashlib.sha256(data).hexdigest(),size=len(data),bundle=hashlib.sha256(blob).hexdigest(),bundle_size=len(blob))
        return data,blob,spec

    def test_only_verified_exact_member_published_and_existing_valid_tool_reused(self):
        data,blob,spec=self.fixture()
        with tempfile.TemporaryDirectory() as directory,patch.dict(tools.TOOLS,{'ffmpeg.exe':spec},clear=True):
            root=Path(directory)/'tools'
            with patch.object(tools.urllib.request,'urlopen',return_value=io.BytesIO(blob)) as download:
                tools.install(root);self.assertEqual((root/'ffmpeg.exe').read_bytes(),data);download.assert_called_once()
            self.assertFalse((root.parent/'outside.txt').exists())
            with patch.object(tools.urllib.request,'urlopen',side_effect=AssertionError('Redownloaded verified tool')):tools.install(root)

    def test_failed_integrity_keeps_previous_tool_and_removes_pending_download(self):
        _,blob,spec=self.fixture();spec['bundle']='0'*64
        with tempfile.TemporaryDirectory() as directory,patch.dict(tools.TOOLS,{'ffmpeg.exe':spec},clear=True),patch.object(tools.urllib.request,'urlopen',return_value=io.BytesIO(blob)):
            root=Path(directory);target=root/'ffmpeg.exe';target.write_bytes(b'previous valid application tool')
            with self.assertRaisesRegex(ValueError,'payload hash'):tools.install(root)
            self.assertEqual(target.read_bytes(),b'previous valid application tool');self.assertEqual(list(root.iterdir()),[target])


if __name__=='__main__':unittest.main()
