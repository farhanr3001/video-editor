import time
import unittest
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap,QColor
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,TimelineItem,MediaItem,Caption
from kinetic_cut.transitions import Transition
from kinetic_cut.timeline import TimelineWidget


class TimelineRendererTests(unittest.TestCase):
    def queued_fixture(self):
        app=QApplication.instance();t=TimelineWidget();t.resize(1000,400)
        t.set_project(Project(timeline=[TimelineItem(str(n),'','video_1',n,1,role='title',title_text='Title') for n in range(110)]))
        t.show();app.processEvents();jobs=[];t.start_worker=lambda job:jobs.append(job)
        t.set_zoom(30);t.viewport().repaint();self.assertEqual(len(jobs),1)
        self.addCleanup(lambda:(t.close_renderer(),t.close(),t.deleteLater(),app.processEvents()))
        return t,jobs
    def test_edited_project_rejects_inflight_raster_and_renders_latest_revision(self):
        t,jobs=self.queued_fixture();old=jobs.pop(0)
        t.project.timeline[0].title_text='Changed title';t.set_project(t.project);t.set_zoom(40);t.viewport().repaint()
        old.run();old.signals.deleteLater()
        self.assertFalse(t._view_rasters,'Old revision was published after edit')
        self.assertEqual(len(jobs),1);current=jobs.pop();current.run();current.signals.deleteLater()
        self.assertTrue(t._view_rasters);self.assertFalse(t._timeline_raster_failed)
    def test_failed_helper_returns_to_exact_timeline_without_mutating_project(self):
        t,jobs=self.queued_fixture();before=t.project.to_dict();job=jobs.pop()
        with patch.object(job,'function',side_effect=RuntimeError('fixture helper failure')):
            with self.assertLogs(level='WARNING'):job.run()
        job.signals.deleteLater();self.assertTrue(t._timeline_raster_failed);self.assertFalse(t._timeline_raster_busy)
        t.set_zoom(40);t.viewport().repaint()
        self.assertEqual(t.project.to_dict(),before);self.assertFalse(jobs)
        self.assertIsNotNone(t._timeline_backing)
    def test_native_helper_matches_timeline_and_reaps_on_close(self):
        app=QApplication.instance();t=TimelineWidget();t.resize(1100,460)
        p=Project();p.media=[MediaItem('m','fixture.mp4','video','Source',100,1920,1080,60,True,'fixture-thumb')]
        p.timeline=[TimelineItem(str(n),'m','video_1' if n%2 else 'audio_1',n*.35,1) for n in range(110)]
        p.timeline[1].effects=[{'name':'Gaussian Blur'}]
        p.captions=[Caption('caption',2,7,'Caption timing and selection')]
        p.transitions=[Transition('transition','Cross Dissolve',start=4,duration=.8,left_item_id='9',right_item_id='11')]
        t.set_project(p);pix=QPixmap(80,45);pix.fill(QColor('#e9af43'));t.thumbnails['fixture-thumb']=pix
        from kinetic_cut.waveforms import Waveform
        t.set_waveform('m',Waveform(np.tile(np.array([[-10000,18000],[-12000,8000]],dtype=np.int16),(50000,1))))
        t.show();app.processEvents()
        jobs=[];t.start_worker=lambda job:jobs.append(job)
        try:
            t.set_zoom(45);t.horizontalScrollBar().setValue(80);t.viewport().repaint()
            self.assertEqual(len(jobs),1);self.assertTrue(t._timeline_raster_busy)
            # New inputs replace the desired state, never enqueue more jobs.
            for offset in (90,100,110):t.horizontalScrollBar().setValue(offset);t.viewport().repaint()
            self.assertEqual(len(jobs),1)
            count=0
            while jobs:
                job=jobs.pop(0);job.run();job.signals.deleteLater();count+=1
                self.assertLess(count,5)
            self.assertFalse(t._timeline_raster_failed);self.assertTrue(t._view_rasters)
            t.viewport().repaint();actual=t._timeline_backing.toImage()
            with patch.object(t,'drag_mode','direct-reference'):
                t.viewport().repaint();expected=t._timeline_backing.toImage()
            a=np.frombuffer(actual.constBits(),np.uint8).astype(np.int16)
            b=np.frombuffer(expected.constBits(),np.uint8).astype(np.int16)
            self.assertLessEqual(int(np.abs(a-b).max()),2)
            from kinetic_cut.theme import PALETTES,get_theme_stylesheet
            previous_theme=app.property('kineticTheme');previous_style=app.styleSheet()
            try:
                for theme in ('final_cut_obsidian','ableton_gray'):
                    app.setProperty('kineticTheme',theme);app.setStyleSheet(get_theme_stylesheet(theme));t.set_theme(PALETTES[theme])
                    t.set_zoom(45);t.viewport().repaint()
                    while jobs:
                        job=jobs.pop(0);job.run();job.signals.deleteLater()
                    t.viewport().repaint();actual=t._timeline_backing.toImage()
                    with patch.object(t,'drag_mode','direct-reference'):
                        t.viewport().repaint();expected=t._timeline_backing.toImage()
                    a=np.frombuffer(actual.constBits(),np.uint8).astype(np.int16);b=np.frombuffer(expected.constBits(),np.uint8).astype(np.int16)
                    self.assertLessEqual(int(np.abs(a-b).max()),2,theme)
            finally:app.setProperty('kineticTheme',previous_theme);app.setStyleSheet(previous_style)
            process=t._timeline_renderer.process
            t.close_renderer();deadline=time.monotonic()+3
            while process.is_alive() and time.monotonic()<deadline:time.sleep(.02)
            self.assertFalse(process.is_alive())
        finally:
            t.close_renderer();t.close();t.deleteLater();app.processEvents()
