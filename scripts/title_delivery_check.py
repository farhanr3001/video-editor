"""Real export and small-window visual checks; isolated test-only media/output."""
import os,sys,json,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/'build/title-delivery-check'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['KINETIC_CUT_HOME']=str(OUT/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
from kinetic_cut.process import install_desktop_process_policy
install_desktop_process_policy()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from kinetic_cut.theme import STYLESHEET
app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
for font in ('arial.ttf','arialbd.ttf','segoeui.ttf','segoeuib.ttf'):QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/font))
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem,CaptionStyle
from kinetic_cut.headline import headline_style
from kinetic_cut.exporter import export,PRESETS
from kinetic_cut.widgets import extract_frame
from kinetic_cut.workspace import set_page
import numpy as np
w=MainWindow(); w.show(); p=Project(); p.settings.width=320; p.settings.height=180; p.settings.fps=20
item=TimelineItem('t','','video_1',0,2,role='title',title_text='Fade 🥹',fade_in=.5,fade_out=.5); p.timeline=[item]; results={}
for name,style in [('Text',CaptionStyle(animation='none',color='#ffffff',background_enabled=True,background_color='#224488',shadow_enabled=False)),('Headline',headline_style())]:
    style.size=42; item.title_style=style; w.set_project(p); output=OUT/(name+'.mp4'); export(p,str(output),next(iter(PRESETS.values())),False,'CPU'); values=[]
    for at in (.1,.25,1,1.75,1.9):
        image=extract_frame(str(output),at); image.save(str(OUT/f'{name}-{at}.png')); from PySide6.QtGui import QImage
        image=image.convertToFormat(QImage.Format_RGBA8888); values.append(int(np.frombuffer(image.constBits(),dtype=np.uint8).reshape(image.height(),image.width(),4)[:,:,:3].sum()))
    assert values[0]<values[1]<values[2] and values[4]<values[3]<values[2],values
    results[name]=values
set_page(w,1); d=w.delivery; d.location.setText(str(OUT)); d.name.setText('Queued sample'); d.add_job(); d.name.setText('Completed sample'); d.add_job(); d.jobs[1].update(state='Complete',elapsed=88); d.refresh()
w.resize(1100,700); app.processEvents(); w.grab().save(str(OUT/'deliver-small.png'))
assert w.left_stack.width()==360 and d.settings_scroll.widget().width()<=d.settings_scroll.viewport().width()
w.resize(1480,900); app.processEvents(); w.grab().save(str(OUT/'deliver-large.png')); w.close()
(OUT/'report.json').write_text(json.dumps(dict(passed=True,fade_luma=results),indent=2)); print('PASS: text/headline export fades and fixed delivery layout')
