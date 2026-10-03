"""Polish only our freshly generated draft, preserving its first render."""
import os,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['KINETIC_CUT_HOME']=str(ROOT/'build/apartment-edit/home')
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project
from kinetic_cut.exporter import export,PRESETS
app=QApplication([])
path=ROOT/'Apartment Tour - xQc.kcut'; p=Project.load(path)
assert p.name=='Apartment Tour | xQc' and len(p.media)==3
p.settings.background_brightness=.85
for c in p.captions:
    if c.is_hook:c.is_hook=False; c.customize=True
output=ROOT/'exports/Apartment Tour - xQc.mp4'
backup=ROOT/'build/apartment-edit/first-cut.mp4'
if backup.exists():raise SystemExit('First cut already preserved; no automatic rerun.')
shutil.copy2(output,backup)
p.save(path)
export(p,str(output),PRESETS['YouTube Shorts · Quality'],progress=lambda v,t:print(f'{v:.3f} {t}',flush=True))
