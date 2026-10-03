import os,sys,json,copy,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/'build/vision-visual-check'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(OUT/'home')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QFontDatabase
from PySide6.QtCore import QEventLoop,QTimer
from kinetic_cut.model import Project,Transform
from kinetic_cut.widgets import extract_frame,PreviewCanvas
from kinetic_cut.vision_effects import apply,prepare_export
from kinetic_cut.exporter import export,PRESETS
from kinetic_cut.ui import MainWindow
from kinetic_cut.vision_component import analyse
app=QApplication([]); app.setQuitOnLastWindowClosed(False)
from kinetic_cut.theme import STYLESHEET
app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
for font in ('arial.ttf','arialbd.ttf','segoeui.ttf','segoeuib.ttf'):QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/font))
info=json.loads((ROOT/'build/vision-component-check/report.json').read_text()); p=Project.load(ROOT/'TestEdit.kcut'); item=next(i for i in p.timeline if i.track=='video_3'); item=copy.deepcopy(item); item.duration=2; item.start=0; item.transform=Transform(.5,.5,2)
p.timeline=[item]; p.captions=[]; p.settings.width=360; p.settings.height=640; p.settings.fps=30
for media in p.media:media.thumbnail=''
media=p.media_by_id(item.media_id); image=PreviewCanvas._source_crop(extract_frame(media.path,.5),item.crop); image.save(str(OUT/'source.png'))
names=['Remove Person Background','Party Hat','Face Mask','Big Eyes']
for name in names:
    item.effects=[dict(name=name,enabled=True,analysis=info)]; result=apply(image,item,media,.5); result.save(str(OUT/(name+'.png')))
    if name=='Remove Person Background':assert result.pixelColor(0,0).alpha()<128
item.effects=[dict(name=n,enabled=True,analysis=info) for n in ['Remove Person Background','Party Hat','Big Eyes']]
result=apply(image,item,media,.5); result.save(str(OUT/'combined.png'))
export(p,str(OUT/'combined.mp4'),next(iter(PRESETS.values())),False,'CPU',progress=lambda v,t:print(t,flush=True))
w=MainWindow(); w.resize(1680,1000); w.show(); w.set_project(p); w.seek(.5)
loop=QEventLoop(); QTimer.singleShot(500,loop.quit); loop.exec(); w.select_item(item.id); w.inspector.tabs.setCurrentIndex(2); w.grab().save(str(OUT/'workspace.png')); w.close()
loop=QEventLoop(); QTimer.singleShot(100,loop.quit); loop.exec()
print('PASS: previews, alpha and real stacked-effect export',flush=True)
