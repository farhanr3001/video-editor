"""Offscreen visual check for the compact track and Inspector level meters."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
output = Path(sys.argv[1]).resolve()
output.mkdir(parents=True, exist_ok=True)
os.environ["KINETIC_CUT_HOME"] = str(output / "home")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from kinetic_cut.model import MediaItem, Project, TimelineItem
from kinetic_cut.ui import MainWindow

app = QApplication([])
window = MainWindow()
window.request_waveform = lambda media: None
source = output / 'audio-check.wav'
import wave
with wave.open(str(source), 'wb') as sample:
    sample.setnchannels(1); sample.setsampwidth(2); sample.setframerate(8000)
    sample.writeframes(b'\0\0' * 8000)
window.set_project(Project(name="Audio meter visual check",
                           media=[MediaItem("audio", str(source), "audio", "Visual check")],
                           timeline=[TimelineItem("clip", "audio", "audio_1", 0, 8)]))
window.timeline.select_ids({"clip"}, "clip")
window.inspector.select("clip")
window.inspector.audio_subtabs.setCurrentIndex(1)
window.show()
app.processEvents()
window.transport.levelsChanged.emit({"audio_1": (.67, .91, True)})
app.processEvents()
window.grab().save(str(output / "audio-levels.png"))
window.close()
