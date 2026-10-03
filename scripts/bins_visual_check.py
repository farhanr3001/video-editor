"""Native widget captures and actual preview/export comparisons for this follow-up."""
import os,sys,json
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/"build/bins-visual-check"; OUT.mkdir(parents=True,exist_ok=True)
os.environ.setdefault("KINETIC_CUT_HOME",str(OUT/"home")); os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PIL import Image,ImageDraw
from PySide6.QtWidgets import QApplication,QFontComboBox
from PySide6.QtGui import QFontDatabase,QImage,QPainter,QColor
from PySide6.QtCore import Qt,QRectF
from kinetic_cut.model import Project,MediaItem,TimelineItem,Caption
from kinetic_cut.ui import MainWindow
from kinetic_cut.theme import STYLESHEET
from kinetic_cut.visuals import draw_caption
from kinetic_cut.exporter import write_ass,_escape_ass_path,export,PRESETS
from kinetic_cut.process import run
from kinetic_cut import binclips
from kinetic_cut.workspace import PowerBins
app=QApplication([]); app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
for f in ("arial.ttf","arialbd.ttf","segoeui.ttf","segoeuib.ttf"):QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+f)
logo=Image.new("RGBA",(600,160),(255,255,255,0)); draw=ImageDraw.Draw(logo); draw.rounded_rectangle((5,50,594,110),radius=4,fill="#000000"); draw.text((16,55),"KINETIC",fill="#44ff33",font=__import__('PIL.ImageFont',fromlist=['truetype']).truetype("arialbd.ttf",38)); logo.save(OUT/"transparent-logo.png")
for name,color in (("lower","#42667a"),("upper","#a36c68")):Image.new("RGB",(720,1280),color).save(OUT/(name+".png"))
p=Project(media=[MediaItem(name,str(OUT/(name+".png")),"image",name,4,720,1280) for name in ("lower","upper")]); p.media.append(MediaItem("logo",str(OUT/"transparent-logo.png"),"image","Transparent logo",4,600,160))
lower=TimelineItem("lower","lower","video_1",0,4,role="content"); lower.transform.scale=.7; lower.transform.y=.62
upper=TimelineItem("upper","upper",p.add_track("video"),0,4); upper.transform.scale=.65; upper.transform.y=.3; p.timeline=[lower,upper]; p.captions=[Caption("c",0,4,"Make words matter 🥹")]; p.subtitle_style.animation="word highlight"; p.subtitle_style.position_y=.88
w=MainWindow(); w.resize(1680,1000); w.show(); w.set_project(p); w.timeline.select_ids({lower.id},lower.id); w.seek(.25); app.processEvents()
w.preview.set_transform_controls_visible(False); clean=w.preview.grab().toImage(); w.preview.set_transform_controls_visible(True); shown=w.preview.grab().toImage()
target=next(rect for item,_,rect in w.preview._visible_items() if item.id==lower.id); point=target.topLeft()+__import__('PySide6.QtCore',fromlist=['QPointF']).QPointF(target.width()*.3,0)
assert any(shown.pixelColor(round(point.x()),round(point.y())+dy)!=clean.pixelColor(round(point.x()),round(point.y())+dy) for dy in (-1,0,1))
w.grab().save(str(OUT/"workspace.png")); w.media_panel.grab().save(str(OUT/"media-pool.png")); w.preview.grab().save(str(OUT/"overlay.png"))
saved=binclips.asset(binclips.snapshot(p,{lower.id},set(),lower.id)); w.media_panel.power=PowerBins(OUT/"powerbins.json"); w.media_panel.power.add(saved,"Master"); w.media_panel.folder="Master"; w.media_panel.refresh(); w.media_panel.grab().save(str(OUT/"power-bin.png"))
def caption_dialog(dialog):
    dialog.show(); app.processEvents(); dialog.grab().save(str(OUT/"caption-setup.png")); font=dialog.findChild(QFontComboBox); font.showPopup(); app.processEvents(); font.view().grab().save(str(OUT/"font-dropdown.png")); font.hidePopup(); dialog.close(); return 0
with patch("kinetic_cut.ui.QDialog.exec",caption_dialog):w.generate_captions()
w.timeline._razor_cursor().pixmap().save(str(OUT/"razor-cursor.png"))
test=Project(captions=[Caption("c",0,4,"Make words matter 🥹")]); test.subtitle_style.animation="word highlight"; test.subtitle_style.shadow_enabled=False; test.subtitle_style.outline_width=3
ass=OUT/"highlight.ass"; write_ass(test,ass); differences=[]
import numpy as np
for at in (.25,1.25,2.25):
    test.playhead=at; image=QImage(1080,1920,QImage.Format_RGB32); image.fill(QColor("#202020")); painter=QPainter(image); painter.setRenderHint(QPainter.Antialiasing); draw_caption(painter,test,test.captions[0],QRectF(0,0,1080,1920)); painter.end(); preview=OUT/f"highlight-preview-{at}.png"; image.save(str(preview))
    output=OUT/f"highlight-export-{at}.png"; run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=c=0x202020:s=1080x1920:r=60:d=4","-vf","ass='"+_escape_ass_path(str(ass))+"'","-ss",str(at),"-frames:v","1",str(output)],check=True,capture_output=True)
    a=np.asarray(Image.open(preview).convert("RGB")).astype(float); b=np.asarray(Image.open(output).convert("RGB")).astype(float); mask=np.any(a!=32,axis=2)|np.any(b!=32,axis=2); mae=float(np.abs(a-b)[mask].mean()); differences.append(mae); assert mae<16,mae
out=str(OUT/"highlight-60fps.mp4"); export(test,out,PRESETS["TikTok · Fast"],hardware="CPU",export_audio=False)
info=json.loads(run(["ffprobe","-v","error","-show_streams","-of","json",out],capture_output=True,text=True,check=True).stdout); assert info["streams"][0]["r_frame_rate"]=="60/1"
(OUT/"report.json").write_text(json.dumps({"highlight_frame_mae":differences,"fps":"60/1","overlay_above_upper_layer":True,"passed":True},indent=2)); w.close(); print("PASS visual and 60 fps export checks",differences)
