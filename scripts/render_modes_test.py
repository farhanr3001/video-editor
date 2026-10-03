"""Exercise all exposed composite modes and border/softness/audio mix filters."""
import copy,os,sys,tempfile,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"render-modes-home"))
from kinetic_cut.model import Project,TimelineItem,Caption,Transform,uid
from kinetic_cut.media import probe
from kinetic_cut.exporter import export,PRESETS

def main():
    with tempfile.TemporaryDirectory(prefix="kinetic-modes-") as directory:
        d=Path(directory); source=d/"source.mp4"
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=size=320x180:rate=30:duration=1","-f","lavfi","-i","sine=frequency=440:duration=1","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",str(source)],check=True)
        media=probe(source); p=Project(media=[media]); p.settings.width=180; p.settings.height=320; p.settings.fps=30
        top=p.add_track("video"); music=p.add_track("audio")
        p.timeline=[TimelineItem("v1",media.id,"video_1",0,1,transform=Transform(.5,.5,2)),TimelineItem("v2",media.id,top,.1,.8,transform=Transform(.5,.6,.9)),TimelineItem("a",media.id,"audio_1",0,1,role="source_audio"),TimelineItem("m",media.id,music,0,1,role="music",gain_db=-12)]
        layer=p.timeline[1]; layer.opacity=70; layer.crop_softness=4; layer.transform.rotation=8; layer.transform.pitch=7; layer.transform.yaw=-5
        layer.effects=[dict(name="Gaussian Blur",horizontal=3,vertical=1,blend=70,border="Reflect")]
        p.captions=[Caption("c",.1,.9,"Visible caption")]; p.subtitle_style.size=18; p.subtitle_style.background_enabled=True; p.subtitle_style.shadow_blur=5
        for mode in ["Normal","Add","Multiply","Screen"]:
            layer.composite_mode=mode; output=d/(mode+".mp4"); export(p,str(output),PRESETS["TikTok · Fast"])
            assert output.stat().st_size>1000; print("PASS render",mode,flush=True)
        layer.effects[0]["border"]="Replicate"; export(p,str(d/"replicate.mp4"),PRESETS["TikTok · Fast"],export_audio=False)
        print("PASS Replicate border and silent export",flush=True)

if __name__=="__main__":main()
