"""Isolated pool/monitor visual check with generated, non-user media."""
import os,sys,wave,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
out=ROOT/'build/pool-polish-visual'; out.mkdir(parents=True,exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(out/'home')
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool,QEventLoop,QTimer,QEvent
from PySide6.QtGui import QImage,QColor
from kinetic_cut.ui import MainWindow
from kinetic_cut.theme import STYLESHEET
from kinetic_cut.model import Project,MediaItem
from kinetic_cut.pool_tools import set_view
app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
image=QImage(640,360,QImage.Format_RGB32); image.fill(QColor('#487e95')); image.save(str(out/'sample.png'))
t=np.arange(48000*3)/48000; samples=(np.sin(t*2*np.pi*440)*(.1+.85*np.sin(t*3)**2)*32760).astype('<i2')
with wave.open(str(out/'sample.wav'),'wb') as f:f.setnchannels(1); f.setsampwidth(2); f.setframerate(48000); f.writeframes(samples.tobytes())
w=MainWindow(); w.resize(1450,850); w.show(); w.autosave_timer.stop()
try:
    w.set_project(Project(media=[MediaItem('i',str(out/'sample.png'),'image','Apartment reference',5,640,360),MediaItem('a',str(out/'sample.wav'),'audio','Doorbell sound effect',3,has_audio=True)]))
    loop=QEventLoop(); QTimer.singleShot(1500,loop.quit); loop.exec(); QThreadPool.globalInstance().waitForDone(10000); app.processEvents()
    set_view(w.media_panel,False,False); app.processEvents(); w.grab().save(str(out/'gallery.png'))
    set_view(w.media_panel,True,False); app.processEvents(); w.grab().save(str(out/'list.png'))
    print([(w.media_panel.grid.item(n).text(),w.media_panel.grid.visualItemRect(w.media_panel.grid.item(n))) for n in range(w.media_panel.grid.count())])
    w.resize(1100,750); app.processEvents(); w.monitor_control.popup(); app.processEvents(); w.monitor_control._menu.grab().save(str(out/'volume.png'))
    (out/'report.json').write_text(json.dumps({'audio_cached':bool(w.media_panel.audio_thumbnails.cache),'compact_volume':w.monitor_control.slider.isHidden()},indent=2))
finally:
    w.close(); QThreadPool.globalInstance().waitForDone(10000); app.processEvents(); w.deleteLater(); app.sendPostedEvents(None,QEvent.DeferredDelete)
