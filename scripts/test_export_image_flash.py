"""Test that image media in export does not drop frames/flash at cuts."""
import os, sys, subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kinetic_cut.model import Project
from kinetic_cut.exporter import PRESETS, build_command

def run_test():
    p = Project.load("GTA.kcut")
    fps = p.settings.fps
    
    # We want to test the first cut in video_4 at 4.736975s
    # Extract 10 frames right around the cut: 5 frames before and 5 frames after
    cut_time = 4.736974552972178
    start_window = cut_time - (5 / fps)
    end_window = cut_time + (5 / fps)
    
    tmpdir = Path("build/test_flash_verify")
    tmpdir.mkdir(parents=True, exist_ok=True)
    for f in tmpdir.glob("*.png"):
        f.unlink()
        
    out_pattern = str(tmpdir / "frame_%04d.png")
    
    # Render just this small window (start_window to end_window) using the export pipeline
    from kinetic_cut.rendergraph import command
    # Only test the video_4 image clips
    test_project = Project.load("GTA.kcut")
    test_project.timeline = [it for it in test_project.timeline if it.track == "video_4"]
    
    args = command(test_project, out_pattern, PRESETS["TikTok · Fast"], False, "CPU", "ffmpeg", None, False, None, window=(start_window, end_window))
    # Replace encoder with png for image sequence
    c_idx = args.index('-c:v')
    args = args[:c_idx] + ['-c:v', 'png', out_pattern]
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        print("FFmpeg error:", res.stderr[-1000:])
        raise RuntimeError("FFmpeg failed")
        
    frames = sorted(tmpdir.glob("frame_*.png"))
    print(f"Generated {len(frames)} frames around the cut ({start_window:.3f}s to {end_window:.3f}s)")
    
    # Check logo bbox region (y in 743..831, x in 54..808) for image content
    import numpy as np
    missing_count = 0
    for idx, f in enumerate(frames):
        im = Image.open(f)
        arr = np.array(im)
        sub = arr[743:831, 54:808]
        non_zero = np.count_nonzero(sub > 30)
        if non_zero < 10000:
            print(f"FRAME {idx} ({f.name}) IS MISSING LOGO! (FLASH DETECTED, non_zero={non_zero})")
            missing_count += 1
        else:
            print(f"FRAME {idx} ({f.name}) OK (pixels={non_zero})")
            
    print(f"Verification complete: {missing_count} frames missing logo out of {len(frames)} frames.")
    assert missing_count == 0, f"Detected {missing_count} flashing/missing frames at cut!"
    print("SUCCESS: 0 frames dropped! The cut is completely seamless without any flash!")
    
    # Clean up
    for f in tmpdir.glob("*.png"):
        f.unlink()

if __name__ == "__main__":
    run_test()
