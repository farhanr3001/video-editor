"""Read-only GTA reproduction; existing effect caches only, outputs in build."""
import os,sys,time,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
OUT=ROOT/'build/gta-export-check'; OUT.mkdir(parents=True,exist_ok=True)
os.environ['QT_QPA_PLATFORM']='offscreen'; os.environ['KINETIC_CUT_HOME']=str(OUT/'home')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from kinetic_cut.model import Project
from kinetic_cut.vision_effects import active,fingerprint
from kinetic_cut.exporter import build_command,write_ass,PRESETS
from kinetic_cut.export_process import render
app=QApplication([])
for name in ('impact.ttf','arial.ttf','arialbd.ttf','segoeui.ttf'):QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
project=Project.load(ROOT/'GTA.kcut'); prepared={}
for item in project.timeline:
    effects=active(item)
    if not effects:continue
    media=project.media_by_id(item.media_id); fps=max(1,min(60,project.settings.fps/max(.05,item.speed)))
    key=hashlib.sha256(json.dumps([fingerprint(media),vars(item.crop.clamped()),item.in_point,item.source_duration,fps,effects],sort_keys=True).encode()).hexdigest()
    target=Path(effects[0]['analysis']['root']).parent.parent/'vision-renders'/(key+'.mkv')
    if not target.is_file():raise RuntimeError('Missing existing prepared cache: '+str(target))
    prepared[item.id]=str(target)
label=sys.argv[1] if len(sys.argv)>1 else 'baseline'
if label=='validate':
    from kinetic_cut import config
    from kinetic_cut.vision_effects import prepare_export
    config.CACHE_DIR=Path(next(iter(prepared.values()))).parent.parent
    actual=prepare_export(project,'ffmpeg',None,None)
    assert actual==prepared, 'Production cache preparation differs from test inputs'
    print(json.dumps({'passed':True,'validated_effect_clips':len(actual)}),flush=True)
    sys.exit(0)
ass=OUT/(label+'.ass'); write_ass(project,ass)
command=build_command(project,str(OUT/(label+'.mp4')),next(iter(PRESETS.values())),True,'NVIDIA',ass_path=str(ass),prepared=prepared)
if label=='bounded':
    rewritten=[]
    for arg in command:
        if arg=='-i':rewritten+=['-threads','1']
        rewritten.append(arg)
    command=rewritten
if label=='nocaptions':
    command=build_command(project,str(OUT/(label+'.mp4')),next(iter(PRESETS.values())),False,'NVIDIA',prepared=prepared)
(OUT/(label+'-command.json')).write_text(json.dumps(command,indent=2))
last=[-10]; start=time.monotonic()
def progress(value,text):
    if time.monotonic()-last[0]>5:print(text,flush=True); last[0]=time.monotonic()
try:
    if label=='batches':
        from unittest.mock import patch
        from kinetic_cut.exporter import export
        with patch('kinetic_cut.vision_effects.prepare_export',return_value=prepared):
            export(project,str(OUT/'batches.mp4'),next(iter(PRESETS.values())),True,'NVIDIA',progress=progress)
        code,tail=0,[]
    else:code,tail=render(command,project.duration,progress,stall_timeout=25)
    result=dict(returncode=code,elapsed=time.monotonic()-start,tail=tail)
except Exception as error:result=dict(error=str(error),elapsed=time.monotonic()-start)
(OUT/(label+'-report.json')).write_text(json.dumps(result,indent=2)); print(json.dumps(result),flush=True)
