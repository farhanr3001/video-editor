"""Source-app visual checks plus real FFmpeg colour-emoji output."""
import os,sys,time,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); os.environ.setdefault("QT_QPA_PLATFORM","offscreen"); os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build/sept8-visual-home"))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase,QImage,QPainter,QColor
from PySide6.QtCore import QRectF,Qt,QPoint,QPointF,QEvent
from PySide6.QtTest import QTest
from kinetic_cut.ui import MainWindow
from kinetic_cut.model import Project,TimelineItem,Caption
from kinetic_cut.headline import headline_style
from kinetic_cut.emoji import EmojiPicker
from kinetic_cut.attributes import PasteAttributesDialog
from kinetic_cut.visuals import draw_caption
from kinetic_cut.exporter import write_ass,_escape_ass_path,export,PRESETS
from kinetic_cut.process import run
from kinetic_cut.theme import STYLESHEET
app=QApplication([])
for f in ("arial.ttf","arialbd.ttf","segoeui.ttf","segoeuib.ttf"):QFontDatabase.addApplicationFont("C:/Windows/Fonts/"+f)
app.setStyle("Fusion"); app.setStyleSheet(STYLESHEET)
w=MainWindow(); w.resize(1680,1000); w.show(); w.add_title_object("Headline"); title=w.project.item_by_id(w.timeline.selected_id); title.title_text="xQc can't believe DLSS\n5 applied on GTA 5 🥹"; w.model_changed(); app.processEvents()
w.grab().save(str(ROOT/"build/sept8-headline-workspace.png"))
picker=EmojiPicker(w); picker.show(); app.processEvents(); picker.grab().save(str(ROOT/"build/sept8-emoji-picker.png")); picker.close()
dialog=PasteAttributesDialog("Source clip.mp4","3 selected video clips","video",w); dialog.show(); app.processEvents(); dialog.grab().save(str(ROOT/"build/sept8-paste-attributes.png")); dialog.close()
p=Project(timeline=[TimelineItem("t","","video_1",0,1,role="title",title_text="Google emoji 🥹 👩🏽‍💻\n🇬🇧 👨‍👩‍👧‍👦 🦍",title_style=headline_style())]); p.settings.fps=60
q=QImage(1080,1920,QImage.Format_RGB32); q.fill(QColor("#202020")); painter=QPainter(q); painter.setRenderHint(QPainter.Antialiasing); draw_caption(painter,p,Caption("c",0,1,p.timeline[0].title_text,p.timeline[0].title_style,False,True),QRectF(0,0,1080,1920)); painter.end(); q.save(str(ROOT/"build/sept8-emoji-preview.png"))
ass=ROOT/"build/sept8-emoji.ass"; write_ass(p,ass); started=time.monotonic()
run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=c=0x202020:s=1080x1920:r=60:d=1","-vf","ass='"+_escape_ass_path(str(ass))+"'","-frames:v","1",str(ROOT/"build/sept8-emoji-export.png")],check=True,capture_output=True)
from PIL import Image
import numpy as np
a=np.asarray(Image.open(ROOT/"build/sept8-emoji-preview.png").convert("RGB")); b=np.asarray(Image.open(ROOT/"build/sept8-emoji-export.png").convert("RGB"))
color=lambda data:(np.max(data,axis=2).astype(int)-np.min(data,axis=2).astype(int)>50)&(np.max(data,axis=2)>100)
assert color(a).sum()>1500 and color(b).sum()>1500
mask=np.any(a!=32,axis=2)|np.any(b!=32,axis=2); mae=float(np.abs(a.astype(float)-b.astype(float))[mask].mean()); print("Emoji preview/export difference",round(mae,2),"ASS size",ass.stat().st_size,"render seconds",round(time.monotonic()-started,2)); assert mae<18
out=str(ROOT/"build/sept8-emoji-video.mp4"); export(p,out,PRESETS["TikTok · Fast"],hardware="CPU",export_audio=False)
info=json.loads(run(["ffprobe","-v","error","-show_streams","-of","json",out],capture_output=True,text=True,check=True).stdout); assert info["streams"][0]["r_frame_rate"]=="60/1"
w.close(); print("PASS emoji video export + layout captures")
