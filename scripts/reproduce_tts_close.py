"""Disposable native reproduction of closing a synthesizing TTS popup."""
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build/tts-stability/before-home"))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget
from kinetic_cut.tts_dialogue_dialog import TTSDialogueDialog

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
owner = QWidget()
owner.show()
dialog = TTSDialogueDialog(owner, "A delayed synthesis request.")

def delayed(**kwargs):
    time.sleep(1.8)
    return "dummy.mp3"

def dismiss():
    print("Cancel enabled:", dialog.cancel_btn.isEnabled(), flush=True)
    dialog.close()
    dialog.deleteLater()

with patch("kinetic_cut.tts_dialogue_dialog.synthesize_dialogue_batches", delayed):
    dialog.show()
    dialog._on_generate_clicked()
    QTimer.singleShot(80, dismiss)
    QTimer.singleShot(2500, app.quit)
    app.exec()
print("Survived close and worker completion", flush=True)
