"""Partial repaint must never corrupt the retained static timeline raster."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import QRect
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project, TimelineItem
from kinetic_cut.timeline import TimelineWidget


class TimelinePartialPaintTests(unittest.TestCase):
    def test_partial_damage_and_resumed_playhead_preserve_all_tracks(self):
        app=QApplication.instance() or QApplication([])
        project=Project()
        project.timeline=[TimelineItem(str(n),'missing',track,n*2,1.8)
                          for track in (project.video_tracks[0],project.audio_tracks[0])
                          for n in range(8)]
        timeline=TimelineWidget(); timeline.resize(1100,460)
        timeline.set_project(project); timeline.show(); app.processEvents()
        try:
            timeline.viewport().repaint()
            expected=timeline._timeline_backing.toImage()
            for step in range(12):
                x=round(timeline.x_for_time(1+step*.7))
                damage=QRegion(QRect(x,0,13,timeline.viewport().height()))
                damage|=QRegion(QRect(x+105,40,9,180))
                # Ordinary expose/hover damage coalesces with cursor updates.
                timeline._content_damage|=damage
                timeline.viewport().repaint(damage)
                # Read the cache directly: grab() would force a full repaint and
                # hide the exact corruption reported during playback.
                actual=timeline._timeline_backing.toImage()
                if actual!=expected:
                    from pathlib import Path
                    out=Path('build/timeline-gap-pixel-failure'); out.mkdir(exist_ok=True)
                    expected.save(str(out/'expected.png')); actual.save(str(out/'actual.png'))
                self.assertEqual(actual,expected,step)
                project.playhead=1+step*.7
                with patch.object(timeline,'paint_track_header',wraps=timeline.paint_track_header) as headers:
                    timeline.update_playhead(); app.processEvents()
                    self.assertEqual(headers.call_count,0)
                self.assertEqual(timeline._timeline_backing.toImage(),expected)
        finally:
            timeline.close(); timeline.deleteLater(); app.processEvents()
