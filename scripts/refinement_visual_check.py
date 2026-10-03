"""Offscreen layout captures and an actual libass headline export comparison."""
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen"); os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build/refinement-visual-home"))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QImage,QPainter,QColor
from PySide6.QtCore import QRectF
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,Caption,TimelineItem
from kinetic_cut.headline import headline_style
from kinetic_cut.visuals import draw_caption
from kinetic_cut.exporter import write_ass,_escape_ass_path
from kinetic_cut.process import run
from kinetic_cut.controls import InspectorSection
from kinetic_cut.theme import STYLESHEET

app=QApplication.instance() or QApplication([])
for filename in ("segoeui.ttf","segoeuib.ttf","seguisb.ttf","arial.ttf","arialbd.ttf"):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+filename)
app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
w=MainWindow(); w.resize(1480,900); w.show(); w.add_title_object("Headline")
title=w.project.item_by_id(w.timeline.selected_id); title.title_text="NoPixel 5 lore trailer (RP\nBegins tomorrow)"; w.model_changed(); app.processEvents()
w.grab().save(str(ROOT/"build/refinement-headline-workspace.png"))
style=headline_style(); p=Project(timeline=[TimelineItem("t","","video_1",0,2,role="title",title_text=title.title_text,title_style=style)])
image=QImage(1080,1920,QImage.Format_RGB32); image.fill(QColor("#202020")); painter=QPainter(image); painter.setRenderHint(QPainter.Antialiasing)
draw_caption(painter,p,Caption("c",0,2,title.title_text,style,False,True),QRectF(0,0,1080,1920)); painter.end(); image.save(str(ROOT/"build/refinement-headline-preview.png"))
ass=ROOT/"build/refinement-headline.ass"; write_ass(p,ass)
output=ROOT/"build/refinement-headline-export.png"
run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=c=0x202020:s=1080x1920:r=60:d=1","-vf","ass='"+_escape_ass_path(str(ass))+"'","-frames:v","1",str(output)],check=True,capture_output=True)
from PIL import Image
import numpy as np
a=np.asarray(Image.open(ROOT/"build/refinement-headline-preview.png").convert("RGB")); b=np.asarray(Image.open(output).convert("RGB"))
def bounds(pixels):
    mask=np.min(pixels,axis=2)>230; y,x=np.nonzero(mask); return [int(x.min()),int(y.min()),int(x.max()),int(y.max())]
print("Headline white bounds (preview, export):",bounds(a),bounds(b))
assert max(abs(x-y) for x,y in zip(bounds(a),bounds(b)))<=2
mask=np.any(a!=32,axis=2)|np.any(b!=32,axis=2)
mae=float(np.abs(a.astype(float)-b.astype(float))[mask].mean()); print("Headline mean pixel difference:",round(mae,2)); assert mae<15
w.add_title_object("Text"); app.processEvents()
section=next(section for section in w.inspector.findChildren(InspectorSection) if section.toggle.text()=="Drop Shadow")
w.inspector.style_scroll.ensureWidgetVisible(section,0,0); app.processEvents(); w.inspector.grab().save(str(ROOT/"build/refinement-shadow-inspector.png"))
w.grab().save(str(ROOT/"build/refinement-styled-workspace.png")); w.close()
print("PASS refinement visual/export checks")
