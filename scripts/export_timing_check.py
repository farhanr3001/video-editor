"""Read-only source-project export timing; writes only build/export-timing-check."""
import os,sys,json,time,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'build/export-timing-check'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['KINETIC_CUT_HOME']=str(OUT/'home')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from kinetic_cut.model import Project
from kinetic_cut.exporter import build_command,write_ass,PRESETS
from kinetic_cut.process import run
app=QApplication([])
for name in ('arial.ttf','arialbd.ttf','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
p=Project.load(ROOT/'TestEdit.kcut')
summary={'duration':p.duration,'layers':[{'track':i.track,'role':i.role,'start':i.start,'duration':i.duration,'in':i.in_point,'crop':vars(i.crop),'transform':vars(i.transform),'effects':i.effects} for i in p.timeline]}
print(json.dumps(summary,indent=2),flush=True)
label=sys.argv[1] if len(sys.argv)>1 else 'baseline'
start=time.perf_counter(); ass=OUT/(label+'.ass'); write_ass(p,ass)
setup=time.perf_counter()-start
command=build_command(p,str(OUT/(label+'.mp4')),next(iter(PRESETS.values())),True,'NVIDIA',ass_path=str(ass))
if label=='lowdelay':command[-1:-1]=['-delay','0','-rc-lookahead','0']
if label=='cpu':command=build_command(p,str(OUT/(label+'.mp4')),next(iter(PRESETS.values())),True,'CPU',ass_path=str(ass))
(OUT/(label+'-command.json')).write_text(json.dumps(command,indent=2),encoding='utf-8')
if label in {'auto','captions'}:
    from kinetic_cut.exporter import export
    from types import SimpleNamespace
    export(p,str(OUT/(label+'.mp4')),next(iter(PRESETS.values())),label=='captions','Auto',progress=lambda value,text:print(text,flush=True))
    result=SimpleNamespace(returncode=0)
else:
    with (OUT/(label+'.log')).open('w',encoding='utf-8') as log:result=run(command,stdout=log,stderr=log,timeout=240)
report={'label':label,'seconds':time.perf_counter()-start,'ass_setup_seconds':setup,'returncode':result.returncode,'timeline_seconds':p.duration}
(OUT/(label+'-report.json')).write_text(json.dumps(report,indent=2)); print(json.dumps(report),flush=True)
sys.exit(result.returncode)
