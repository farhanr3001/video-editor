"""Metadata, cancellation and edit geometry at the GPU process boundary.

Actual D3D11 presentation/input/lifecycle is checked on a private Windows
desktop by --gpu-functional-selftest, rather than claimed from offscreen Qt.
"""
import pickle
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtCore import QObject,QPointF
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QImage
from kinetic_cut.model import Project,TimelineItem,MediaItem,Transform
from kinetic_cut.widgets import PreviewCanvas
from kinetic_cut.gpu_preview_process import Peer
from kinetic_cut.remote_preview import RemotePreview


class GpuProcessTests(unittest.TestCase):
    def test_renderer_reports_startup_failure_without_windowed_standard_streams(self):
        from kinetic_cut.gpu_preview_process import renderer
        connection=Mock()
        with patch('kinetic_cut.gpu_preview_process._renderer',side_effect=OSError('desktop unavailable')):
            renderer(connection,'fixture',123,456)
        kind,detail=connection.send.call_args.args[0]
        self.assertEqual(kind,'error');self.assertIn('desktop unavailable',detail)
        connection.close.assert_called_once()

    def mailbox(self):
        peer=Peer.__new__(Peer);peer.lock=threading.Lock();peer.wake=threading.Event();peer.stopping=threading.Event()
        peer.latest=None;peer.replaced=0;peer.commands=[];peer.responses={};peer._stop_started=None
        return peer

    def test_latest_scene_retains_explicit_seek_and_close_rejects_new_work(self):
        peer=self.mailbox()
        for index in range(1000):peer.submit(dict(at=index,force=index==0))
        self.assertEqual(peer.latest,dict(at=999,force=True));self.assertEqual(peer.replaced,999)
        peer.close();peer.submit(dict(at=-1,force=False))
        self.assertEqual(peer.latest['at'],999);self.assertTrue(peer.stopping.is_set())

    def test_capture_commands_are_bounded_and_delivered_only_once(self):
        peer=self.mailbox()
        for serial in range(8):self.assertTrue(peer.command(('capture',serial)))
        self.assertFalse(peer.command(('capture',9)));peer.responses[5]=(2,3)
        self.assertEqual(peer.take_response(5),(2,3));self.assertIsNone(peer.take_response(5))
        peer.close();self.assertFalse(peer.command(('capture',10)))

    def frontend(self,project,at=2):
        window=QWidget();canvas=PreviewCanvas();canvas.setParent(window);canvas.resize(900,600);canvas.project=project
        window.transport=SimpleNamespace(position=at,origin=at,started=1.,rate=1.,playing=False,scrubbing=False)
        window.proxies={};window.timeline=SimpleNamespace(selected_ids=set(),selected_caption_ids=set())
        front=RemotePreview.__new__(RemotePreview);QObject.__init__(front,canvas)
        front.canvas=canvas;front.closed=front.suspended=False;front._signature=None;front._sequence=0;front._force=False;front._cache_epoch=0
        front.identity_image=QImage(1,1,QImage.Format_ARGB32_Premultiplied);front.geometry=Mock();front.peer=SimpleNamespace(submit=Mock())
        return window,canvas,front

    def test_cache_clear_generation_survives_replaced_scenes(self):
        project=Project();window,canvas,front=self.frontend(project)
        front.schedule=Mock()
        try:
            front.invalidate_caches();front.invalidate_caches();front.refresh()
            self.assertEqual(front.peer.submit.call_args.args[0]['cache_epoch'],2)
            self.assertEqual(front.schedule.call_count,2)
            front.refresh();self.assertEqual(front.peer.submit.call_args.args[0]['cache_epoch'],2)
        finally:window.close();window.deleteLater()

    def test_scene_wire_data_has_only_nearby_items_and_preserves_live_document(self):
        project=Project(media=[MediaItem('source','C:/fixture.mp4','video','Source',3000,1920,1080)])
        track=project.video_tracks[0]
        project.timeline=[TimelineItem(str(n),'source',track,n*3,2) for n in range(1000)]
        before=project.to_dict();window,canvas,front=self.frontend(project,at=1)
        try:
            front.refresh();payload=front.peer.submit.call_args.args[0]
            decoded=pickle.loads(pickle.dumps(payload))
            self.assertEqual([i['id'] for i in decoded['document']['timeline']],['0'])
            self.assertEqual(decoded['duration'],2999);self.assertNotIn('frames',decoded)
            self.assertEqual(project.to_dict(),before)
            project.timeline[0].transform.x=.7;project.touch();front.refresh()
            self.assertEqual(front.peer.submit.call_args.args[0]['document']['timeline'][0]['transform']['x'],.7)
            self.assertEqual(payload['document']['timeline'][0]['transform']['x'],.5,'Sent metadata must remain immutable')
        finally:window.close();window.deleteLater()

    def test_preview_hit_geometry_uses_current_edit_not_delayed_child_status(self):
        project=Project(media=[MediaItem('source','C:/fixture.mp4','video','Source',20,1920,1080)])
        project.playhead=2
        item=TimelineItem('clip','source',project.video_tracks[0],0,10,transform=Transform(.5,.5,.6))
        project.timeline=[item];window,canvas,front=self.frontend(project)
        try:
            first=front.targets[0][2];item.transform.x=.75;second=front.targets[0][2]
            self.assertGreater(second.center().x(),first.center().x())
            self.assertEqual(second.size(),first.size())
            item.muted=True;self.assertEqual(front.targets,[])
        finally:window.close();window.deleteLater()


if __name__=='__main__':unittest.main()
