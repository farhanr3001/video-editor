"""Verify rendered source timing, fades, duration and pitch-preserving retiming."""
import os,sys,subprocess,tempfile,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
os.environ.setdefault("KINETIC_CUT_HOME",str(ROOT/"build"/"retime-render-home"))
from kinetic_cut.model import Project,TimelineItem,Transform
from kinetic_cut.media import probe
from kinetic_cut.exporter import export,PRESETS

def run(args):return subprocess.run(args,check=True,capture_output=True).stdout

def pixel(path,t):
    data=run(["ffmpeg","-v","error","-ss",str(t),"-i",str(path),"-frames:v","1","-vf","scale=1:1","-f","rawvideo","-pix_fmt","rgb24","pipe:1"])
    return np.frombuffer(data,dtype=np.uint8).astype(float)

def main():
    with tempfile.TemporaryDirectory(prefix="kinetic-retime-") as directory:
        d=Path(directory); source=d/"source.mp4"
        run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=red:s=160x90:r=30:d=2","-f","lavfi","-i","color=blue:s=160x90:r=30:d=2","-f","lavfi","-i","sine=frequency=440:duration=4:sample_rate=48000","-filter_complex","[0:v][1:v]concat=n=2:v=1:a=0[v]","-map","[v]","-map","2:a","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac",str(source)])
        media=probe(source)
        for speed in [.5,2,8]:
            duration=4/speed
            p=Project(media=[media],timeline=[TimelineItem("v",media.id,"video_1",0,duration,transform=Transform(.5,.5,1),speed=speed,fade_in=duration*.2,fade_out=duration*.2),TimelineItem("a",media.id,"audio_1",0,duration,speed=speed)])
            p.settings.width=160; p.settings.height=90; p.settings.fps=30; p.settings.normalize_audio=False
            output=d/f"speed-{speed}.mp4"; export(p,str(output),PRESETS["TikTok · Fast"])
            info=json.loads(run(["ffprobe","-v","error","-show_format","-of","json",str(output)]))
            assert abs(float(info["format"]["duration"])-duration)<.08
            red=pixel(output,duration*.3); blue=pixel(output,duration*.7)
            assert red[0]>180 and red[2]<30,(speed,red)
            assert blue[2]>180 and blue[0]<30,(speed,blue)
            assert pixel(output,0).max()<30
            assert pixel(output,duration*.9).max()<150
            audio=np.frombuffer(run(["ffmpeg","-v","error","-i",str(output),"-vn","-ac","1","-ar","48000","-f","f32le","pipe:1"]),dtype=np.float32)
            segment=audio[round(.15*len(audio)):round(.85*len(audio))]
            spectrum=abs(np.fft.rfft(segment*np.hanning(len(segment))))
            frequency=np.argmax(spectrum)*48000/len(segment)
            assert abs(frequency-440)<8,(speed,frequency)
            print(f"PASS speed {speed}: duration {duration}, source frames, alpha fades, audio {frequency:.1f}Hz",flush=True)

if __name__=="__main__":main()
