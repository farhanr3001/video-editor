"""Real media timing/quality checks; never writes the supplied project or sources."""
import os,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); OUT=ROOT/'build/current-followup-check'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(OUT/'home'); os.environ['HF_HUB_OFFLINE']='1'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PIL import Image
import numpy as np
from kinetic_cut.process import run
from kinetic_cut.captions import transcribe
from kinetic_cut.exporter import automatic_encoder
app=QApplication([])
for name in ('arial.ttf','arialbd.ttf','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
report={'auto_encoder':automatic_encoder('ffmpeg','h264')}
for mode in ('baseline','planar'):
    source=ROOT/'build/export-timing-check'/(mode+'.mp4'); target=OUT/(mode+'.png')
    run(['ffmpeg','-v','error','-y','-ss','3','-i',str(source),'-frames:v','1',str(target)],check=True)
original=np.array(Image.open(OUT/'baseline.png').convert('RGB'),dtype=float); optimized=np.array(Image.open(OUT/'planar.png').convert('RGB'),dtype=float)
report['export_mean_rgb_difference']=float(abs(original-optimized).mean())
assert report['export_mean_rgb_difference']<4,report
wav=ROOT/'build/caption-alignment-probe/first-22s.wav'
for count in (1,2):
    captions,backend=transcribe(str(wav),{'whisper_model':'base.en','caption_language':'en'},words_per_caption=count)
    feels=next(c for c in captions if c.text.lower().startswith('feels'))
    assert 12<feels.start<12.6,(count,feels)
    assert not any('cinema' in c.text.lower() and 'feels' in c.text.lower() for c in captions)
    report[f'captions_{count}_words']={'backend':backend,'feels_start':feels.start,'feels_end':feels.end,'text':feels.text}
    print(count,report[f'captions_{count}_words'],flush=True)
(OUT/'report.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2),flush=True)
