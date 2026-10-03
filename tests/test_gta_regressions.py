import copy
import unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint,QPointF,Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,TimelineItem,MediaItem,Caption
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.exporter import PRESETS


class GTARegressions(unittest.TestCase):
    def test_blade_sticks_to_playhead_for_media_and_captions(self):
        p=Project(timeline=[TimelineItem('v','m','video_1',0,10)],captions=[Caption('c',0,10,'words')]); p.playhead=5
        t=TimelineWidget(); t.set_project(p); t.pixels_per_second=100; t.setProperty('snapping',True)
        for item in (p.timeline[0],p.captions[0]):
            t._blade_snap=None
            self.assertEqual(t._blade_time(item,t.x_for_time(5.1)),5)
            self.assertEqual(t._blade_time(item,t.x_for_time(5.17)),5)
            self.assertNotEqual(t._blade_time(item,t.x_for_time(5.2)),5)
        t.setProperty('snapping',False)
        self.assertAlmostEqual(t._blade_time(p.timeline[0],t.x_for_time(3.123))*60,187)
        t.close()

    def test_alt_zoom_centres_playhead_ctrl_scroll_does_not_zoom(self):
        p=Project(timeline=[TimelineItem('v','m','video_1',0,180)]); p.playhead=100
        t=TimelineWidget(); t.resize(900,340); t.set_project(p); t.show(); QApplication.processEvents()
        def wheel(mod):t.wheelEvent(QWheelEvent(QPointF(250,180),QPointF(250,180),QPoint(),QPoint(0,120),Qt.NoButton,mod,Qt.ScrollUpdate,False))
        old=t.pixels_per_second; wheel(Qt.AltModifier)
        self.assertGreater(t.pixels_per_second,old)
        self.assertAlmostEqual(t.x_for_time(100),(t.LABEL_WIDTH+t.viewport().width())/2,delta=1)
        old=t.pixels_per_second; scroll=t.horizontalScrollBar().value(); wheel(Qt.ControlModifier)
        self.assertEqual(t.pixels_per_second,old); self.assertLess(t.horizontalScrollBar().value(),scroll)
        t.close()

    def test_delete_subtitle_track_removes_captions_only(self):
        p=Project(timeline=[TimelineItem('v','m','video_1',0,10)],captions=[Caption('c',0,10,'words')])
        self.assertTrue(p.delete_track('subtitle_1')); self.assertFalse(p.captions); self.assertEqual(len(p.timeline),1)

    def test_blur_has_no_framesync_cycle_and_batch_preserves_fade_clock(self):
        from kinetic_cut.rendergraph import command
        from kinetic_cut.render_batches import ranges
        i=TimelineItem('v','m','video_1',0,12,fade_in=5,fade_out=3,effects=[dict(name='Gaussian Blur',horizontal=49,vertical=49,blend=100)])
        p=Project(media=[MediaItem('m','test.mp4','video','test',20,640,360,60)],timeline=[i]); before=copy.deepcopy(p.to_dict())
        args=command(p,'out.mkv',next(iter(PRESETS.values())),False,'CPU',export_audio=False,window=(2,4))
        graph=args[args.index('-filter_complex')+1]
        self.assertNotIn('scale2ref',graph); self.assertIn('setpts=PTS+2.000000/TB,fade=t=in',graph); self.assertIn('setpts=PTS+-2.000000/TB',graph)
        self.assertEqual(args[args.index('-ss')+1],'2.000000'); self.assertEqual(p.to_dict(),before)
        self.assertEqual(ranges(p),[(0,10),(10,12)])

    def test_render_locks_edit_and_playback_hides_transform(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.workspace import set_page
        w=MainWindow(); w.autosave_timer.stop()
        try:
            set_page(w,1); w.delivery.running=True; w.delivery.update_controls(); set_page(w,0)
            self.assertEqual(w.current_page,1); self.assertFalse(w.page_group.button(0).isEnabled())
            w.delivery.running=False; w.delivery.update_controls(); set_page(w,0)
            self.assertEqual(w.current_page,0); self.assertTrue(w.page_group.button(0).isEnabled())
            with patch.object(w.preview,'set_transform_controls_visible') as visible:
                w.transport.stateChanged.emit(True); visible.assert_called_with(False)
        finally:w.close(); w.deleteLater()

    def test_pasted_vision_reuses_valid_analysis_without_worker(self):
        from kinetic_cut.vision_ui import reanalyse_pasted
        from types import SimpleNamespace
        i=TimelineItem('v','m','video_1',0,1,effects=[dict(name='Remove Person Background',analysis={'root':'existing'})])
        w=SimpleNamespace(project=Project(timeline=[i]))
        with patch('kinetic_cut.vision_ui.valid',return_value=True),patch('kinetic_cut.vision_ui.component.install') as install:
            reanalyse_pasted(w,[i]); install.assert_not_called()

    def test_pasted_vision_analyses_destination_and_reuses_batch_result(self):
        from kinetic_cut.ui import MainWindow
        from kinetic_cut.vision_ui import reanalyse_pasted
        w=MainWindow(); w.autosave_timer.stop(); jobs=[]
        try:
            first=TimelineItem('a','m','video_1',0,1,effects=[dict(name='Remove Person Background',analysis={'root':'old'})])
            second=copy.deepcopy(first); second.id='b'; second.start=2
            w.project=Project(media=[MediaItem('m','destination.mp4','video','destination',10)],timeline=[first,second])
            with patch('kinetic_cut.vision_ui.valid',side_effect=lambda a,m,i,*requirements:a.get('root')=='new'),patch('kinetic_cut.vision_ui.component.ready',return_value=True),patch('kinetic_cut.vision_ui.component.install'),patch('kinetic_cut.vision_ui.component.analyse',return_value={'root':'new'}) as analyse,patch.object(w,'start_worker',side_effect=jobs.append),patch.object(w,'model_changed'):
                reanalyse_pasted(w,[first,second]); self.assertEqual(len(jobs),1); jobs[0].run()
                QApplication.processEvents()
                self.assertEqual(analyse.call_count,1); self.assertEqual(analyse.call_args.args[1].path,'destination.mp4')
                self.assertEqual(first.effects[0]['analysis'],{'root':'new'}); self.assertEqual(second.effects[0]['analysis'],{'root':'new'})
                self.assertFalse(w._vision_busy)
        finally:w.close(); w.deleteLater()
