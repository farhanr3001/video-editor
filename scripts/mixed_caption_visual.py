"""Caption form snapshot at a normal, non-maximized window height."""
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
out=ROOT/'build/mixed-subtitle-visual'; out.mkdir(parents=True,exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(out/'home')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop,QTimer
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,Caption
from kinetic_cut.theme import STYLESHEET
app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
w=MainWindow(); w.resize(1200,700); w.show(); w.autosave_timer.stop()
try:
    w.set_project(Project(captions=[Caption('c',0,2,'Customize this caption')]))
    w.timeline.select_captions({'c'},'c'); panel=w.inspector; panel.customize.setChecked(True)
    loop=QEventLoop(); QTimer.singleShot(100,loop.quit); loop.exec()
    outer=panel.subtitle.widget(0)
    panel.grab().save(str(out/'header.png'))
    outer.verticalScrollBar().setValue(300); app.processEvents(); panel.grab().save(str(out/'controls.png'))
    result=dict(passed=panel.style_scroll.isHidden() and outer.verticalScrollBar().maximum()>0,
        window_height=w.height(),viewport_height=outer.viewport().height(),content_height=panel.style_content.height(),
        scroll_max=outer.verticalScrollBar().maximum())
    (out/'report.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result))
finally:w.close(); app.processEvents()
