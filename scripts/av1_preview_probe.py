"""Read-only Qt preview-decoder diagnostic for a supplied local video."""
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('KINETIC_CUT_HOME',str(ROOT/'build'/'av1-probe-home'))

from PySide6.QtCore import QTimer,QUrl
from PySide6.QtMultimedia import QMediaPlayer,QVideoSink
from PySide6.QtWidgets import QApplication


def main():
    source=Path(sys.argv[1]).resolve()
    app=QApplication([])
    player=QMediaPlayer()
    sink=QVideoSink()
    player.setVideoSink(sink)
    seen=[]
    errors=[]
    player.errorOccurred.connect(lambda error,message:errors.append(message))
    sink.videoFrameChanged.connect(lambda frame:seen.append((frame.isValid(),frame.startTime())))
    player.setSource(QUrl.fromLocalFile(str(source)))
    player.play()
    QTimer.singleShot(3500,app.quit)
    app.exec()
    print(json.dumps(dict(source=str(source),status=str(player.mediaStatus()),
                          error=player.errorString(),errors=errors,
                          frames=len(seen),valid_frames=sum(valid for valid,_ in seen),
                          position_ms=player.position()),indent=2))
    player.stop()


if __name__=='__main__':main()
