import hashlib,io,json,tempfile,threading,unittest
from pathlib import Path
from kinetic_cut.verified_download import fetch

class Response(io.BytesIO):
    def __init__(self,data,status=200,headers=None):super().__init__(data);self.status=status;self.headers=headers or {}

class Downloads(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'payload.zip';self.data=b'abcdef'*100000
        self.sha=hashlib.sha256(self.data).hexdigest();self.cancel=threading.Event();self.requests=[]
    def run_fetch(self,opener,**kwargs):return fetch('https://example.test/a',self.sha,len(self.data),self.path,self.cancel,opener=opener,**kwargs)
    def paused(self):
        def progress(done,total):
            if done:self.cancel.set()
        with self.assertRaises(InterruptedError):self.run_fetch(lambda *a,**k:Response(self.data,headers={'ETag':'"a"'}),progress=progress)
        self.cancel.clear();return self.path.with_suffix('.zip.partial').stat().st_size
    def test_cancel_then_resume_exact_range_and_verified_publish(self):
        offset=self.paused();self.assertFalse(self.path.exists())
        def server(request,**kwargs):
            self.assertEqual(request.get_header('Range'),f'bytes={offset}-');self.assertEqual(request.get_header('If-range'),'"a"')
            return Response(self.data[offset:],206,{'Content-Range':f'bytes {offset}-{len(self.data)-1}/{len(self.data)}'})
        self.run_fetch(server);self.assertEqual(self.path.read_bytes(),self.data)
        self.assertFalse(self.path.with_suffix('.zip.partial').exists())
    def test_server_ignores_range_restarts_instead_of_appending(self):
        self.paused();self.run_fetch(lambda *a,**k:Response(self.data));self.assertEqual(self.path.read_bytes(),self.data)
    def test_invalid_range_and_changed_content_never_published(self):
        self.paused()
        with self.assertRaises(ValueError):self.run_fetch(lambda *a,**k:Response(self.data,206,{'Content-Range':'bytes 0-4/5'}))
        self.assertFalse(self.path.exists());self.assertFalse(self.path.with_suffix('.zip.partial').exists())
        with self.assertRaises(ValueError):self.run_fetch(lambda *a,**k:Response(b'x'*len(self.data)))
        self.assertFalse(self.path.exists())
    def test_verified_complete_download_is_reused(self):
        self.path.write_bytes(self.data)
        self.run_fetch(lambda *a,**k:self.fail('Already downloaded'))
    def test_network_disconnect_retries_from_persisted_offset(self):
        calls=[]
        def server(request,**kwargs):
            calls.append(request)
            if len(calls)==1:return Response(self.data[:300000])
            self.assertEqual(request.get_header('Range'),'bytes=300000-')
            return Response(self.data[300000:],206,{'Content-Range':f'bytes 300000-{len(self.data)-1}/{len(self.data)}'})
        self.run_fetch(server);self.assertEqual(len(calls),2)
    def test_unrelated_partial_identity_not_reused(self):
        self.paused();meta=self.path.with_suffix('.zip.partial.json');value=json.loads(meta.read_text());value['url']='https://other.test/';meta.write_text(json.dumps(value))
        def server(request,**kwargs):
            self.assertIsNone(request.get_header('Range'));return Response(self.data)
        self.run_fetch(server)
    def test_existing_destination_is_preserved_on_failure(self):
        self.path.write_bytes(b'previous')
        with self.assertRaises(ValueError):self.run_fetch(lambda *a,**k:Response(b'x'*len(self.data)))
        self.assertEqual(self.path.read_bytes(),b'previous')
    def test_two_clients_share_only_the_verified_completed_file(self):
        from concurrent.futures import ThreadPoolExecutor
        calls=[]
        def server(*args,**kwargs):calls.append(1);return Response(self.data)
        with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:self.run_fetch(server),range(2)))
        self.assertEqual(calls,[1]);self.assertEqual(self.path.read_bytes(),self.data)
    def test_cache_cleanup_skips_a_download_that_another_window_owns(self):
        from kinetic_cut import cache_manager
        from kinetic_cut.verified_download import file_lock
        from concurrent.futures import ThreadPoolExecutor
        base=Path(self.temp.name);folder=base/'updates/payloads';folder.mkdir(parents=True)
        name='a'*64+'.zip';part=folder/(name+'.partial');part.write_bytes(b'partial')
        entered=threading.Event();release=threading.Event()
        def hold():
            with file_lock(folder/(name+'.lock'),threading.Event()):entered.set();release.wait(3)
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(hold);self.assertTrue(entered.wait(2))
            try:self.assertEqual(cache_manager.clear(['update-downloads'],base),(0,0));self.assertTrue(part.exists())
            finally:release.set();future.result()
        self.assertEqual(cache_manager.clear(['update-downloads'],base),(1,7))
