"""Render-test the per-clip Colours pipeline."""
import os,sys,tempfile,subprocess,io
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"colour-render-home"))
from kinetic_cut.media import probe
from kinetic_cut.model import Project,TimelineItem,Transform
from kinetic_cut.exporter import export,PRESETS

def main():
    with tempfile.TemporaryDirectory(prefix="kinetic-colour-") as directory:
        d=Path(directory); source=d/"source.mp4"; output=d/"graded.mp4"
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","testsrc2=s=160x90:r=30:d=1","-c:v","libx264","-pix_fmt","yuv420p",str(source)],check=True)
        media=probe(source); item=TimelineItem("v",media.id,"video_1",0,1,transform=Transform(.5,.5,1),grayscale=True,brightness=.04,contrast=1.16,saturation=0,sharpen=.35)
        p=Project(media=[media],timeline=[item]); p.settings.width=160; p.settings.height=90; p.settings.fps=30
        export(p,str(output),PRESETS["TikTok · Fast"],export_audio=False)
        decoded=subprocess.run(["ffmpeg","-hide_banner","-ss","0.5","-i",str(output),"-frames:v","1","-threads","1","-f","image2pipe","-vcodec","png","pipe:1"],capture_output=True)
        assert decoded.returncode==0,decoded.stderr.decode(errors="replace"); frame=decoded.stdout
        from PIL import Image
        pixels=np.asarray(Image.open(io.BytesIO(frame)).convert("RGB")).reshape(-1,3).astype(int); assert np.abs(pixels[:,0]-pixels[:,1]).mean()<3 and np.abs(pixels[:,1]-pixels[:,2]).mean()<3
        assert output.stat().st_size>1000; print("PASS real grayscale/brightness/contrast/sharpen render",flush=True)
if __name__=="__main__":main()
