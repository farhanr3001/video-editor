"""Verify offscreen preview composition and sharpness on The_Mystery_of_DB_Cooper.kcut."""
import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KINETIC_CUT_HOME", os.path.abspath("build/test-home"))

from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter
from kinetic_cut.model import Project
from kinetic_cut.widgets import PreviewCanvas, extract_frame

app = QApplication.instance() or QApplication([])

project_path = Path("The_Mystery_of_DB_Cooper.kcut")
project = Project.load(str(project_path))

out_dir = Path("build/verify-db-cooper")
out_dir.mkdir(parents=True, exist_ok=True)

canvas = PreviewCanvas()
canvas.set_project(project)
canvas.resize(540, 960)

timestamps = [0.5, 5.5, 10.0, 19.5, 29.0, 34.0, 39.0, 44.0]
results = []

for t in timestamps:
    project.playhead = t
    canvas.fallback_frames = {}
    for item in project.timeline:
        if item.track in project.video_tracks and item.start <= t < item.start + item.duration:
            media = project.media_by_id(item.media_id)
            if not media:
                continue
            if media.kind == "image":
                canvas.fallback_frames[item.id] = QImage(media.path)
            else:
                rel_t = item.source_time(t)
                canvas.fallback_frames[item.id] = extract_frame(media.path, rel_t)

    image = QImage(540, 960, QImage.Format_ARGB32)
    image.fill(Qt.black)
    canvas.render(image)
    grab_path = out_dir / f"frame_{t:.1f}s.png"
    image.save(str(grab_path))
    results.append(str(grab_path))

print(f"Rendered {len(results)} preview frames to {out_dir}:")
for r in results:
    print(f"  Saved: {r}")

