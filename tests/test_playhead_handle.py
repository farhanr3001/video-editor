import unittest
from pathlib import Path
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from kinetic_cut.timeline import TimelineWidget
from kinetic_cut.model import Project


class PlayheadHandleTests(unittest.TestCase):
    def test_pointed_silhouette_and_unchanged_ruler_drag(self):
        t=TimelineWidget(); t.resize(900,420); t.set_project(Project(playhead=3)); t.show()
        QApplication.processEvents()
        try:
            x=round(t.x_for_time(3)); image=t.viewport().grab().toImage()
            def red(dx,y):
                c=image.pixelColor(x+dx,y); return c.red()>200 and c.green()<100 and c.blue()<120
            self.assertTrue(red(-5,2)); self.assertTrue(red(5,2))
            self.assertTrue(red(2,8)); self.assertFalse(red(5,10))
            self.assertTrue(red(0,12)); self.assertTrue(red(0,70))
            out=Path('build/playhead-handle-check'); out.mkdir(parents=True,exist_ok=True)
            image.save(str(out/'timeline.png'))
            QTest.mousePress(t.viewport(),Qt.LeftButton,Qt.NoModifier,QPoint(x,5))
            self.assertEqual(t.drag_mode,'playhead')
            destination=round(t.x_for_time(5))
            QTest.mouseMove(t.viewport(),QPoint(destination,5))
            QTest.mouseRelease(t.viewport(),Qt.LeftButton,Qt.NoModifier,QPoint(destination,5))
            self.assertAlmostEqual(t.project.playhead,5,delta=1/t.pixels_per_second)
        finally:t.close(); t.deleteLater()
