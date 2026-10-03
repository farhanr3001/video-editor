import unittest
from dataclasses import asdict
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,MediaItem,TimelineItem,Crop,Transform
from kinetic_cut.exporter import _target_size


class ViewerWidthFitTests(unittest.TestCase):
    def setUp(self):
        self.w=MainWindow(); self.w.autosave_timer.stop()
    def tearDown(self):
        self.w.close(); self.w.deleteLater()
    def scene(self,role,crop):
        m=MediaItem('m','missing.mp4','video','fixture',5,1920,1080,60,False)
        i=TimelineItem('v','m','video_1',0,5,crop=crop,role=role,
                       transform=Transform(x=.5,y=.18,scale=.3,scale_y=.4,anchor_x=12,anchor_y=23))
        self.w.set_project(Project(media=[m],timeline=[i])); return m,i
    def test_width_fill_cropped_webcam_and_tall_crop_preserves_position(self):
        for role,crop in [('facecam',Crop(0,.2,.205,.283)),('normal',Crop(.2,0,.12,1))]:
            with self.subTest(role=role):
                m,i=self.scene(role,crop); before=asdict(i.transform)
                self.w.viewer_command('fit',i.id)
                self.assertEqual(_target_size(i,m,1080,.92 if role=='facecam' else 1,1920)[0],1080)
                source=QImage(1920,1080,QImage.Format_RGB32)
                preview=self.w.preview._layer_rect(i,source,QRectF(0,0,108,192),role=='facecam')
                self.assertAlmostEqual(preview.width(),108)
                self.assertEqual(i.transform.scale,i.transform.scale_y)
                for key in ('x','y','anchor_x','anchor_y','rotation','scale_linked'):
                    self.assertEqual(getattr(i.transform,key),before[key])
                restored=Project.from_dict(self.w.project.to_dict()).item_by_id(i.id)
                self.assertEqual(asdict(restored.transform),asdict(i.transform))
                self.w.undo(); self.assertEqual(asdict(self.w.project.item_by_id(i.id).transform),before)
    def test_locked_fit_and_viewer_tooltip(self):
        _,i=self.scene('facecam',Crop()); before=asdict(i.transform)
        self.w.project.track_states['video_1']={'locked':True}
        self.w.viewer_command('fit',i.id)
        self.assertEqual(asdict(i.transform),before)
        self.assertEqual(self.w.preview.toolTip(),'')
