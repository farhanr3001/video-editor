import subprocess
import json
import os

VIDEOS_DIR = r"c:\Users\F\Documents\AI Projects\video-editor\build\sinking_car_assets\videos"

for f in os.listdir(VIDEOS_DIR):
    if f.endswith(".mp4"):
        p = os.path.join(VIDEOS_DIR, f)
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_name", "-of", "json", p]
        out = subprocess.check_output(cmd).decode()
        data = json.loads(out)
        dur = float(data["format"]["duration"])
        st = data["streams"][0]
        print(f"{f}: {st['width']}x{st['height']}, {dur:.1f}s")
