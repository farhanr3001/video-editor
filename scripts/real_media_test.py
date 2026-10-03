"""Exercise the real stream-clip framing workflow on a short marked range."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kinetic_cut.exporter import PRESETS, export
from kinetic_cut.media import probe
from kinetic_cut.model import Caption, CaptionStyle, Crop, Project, make_vertical_group, uid
from kinetic_cut.silence import detect


def main(source_name="xqc_royalty.mp4"):
    source = Path(source_name).resolve()
    output = Path("build/xqc-real-workflow-test.mp4").resolve()
    project_path = Path("build/xqc-real-workflow-test.kcut").resolve()
    media = probe(source)
    group = make_vertical_group(media, 0, 4.0, 4.0)
    project = Project(name="xQc Royalty Test", media=[media], timeline=group)
    project.settings.width, project.settings.height, project.settings.fps = 720, 1280, 30
    project.settings.blur = 24
    main = next(x for x in group if x.role == "content")
    face = next(x for x in group if x.role == "facecam")
    # Central TikTok content and lower-left xQc webcam, measured from the supplied real clip.
    main.crop = Crop(.401, .098, .267, .841)
    main.transform.x, main.transform.y, main.transform.scale = .5, .57, .91
    main.transform.scale_y = .96; main.transform.scale_linked = False
    face.crop = Crop(.0, .704, .231, .259)
    face.transform.x, face.transform.y, face.transform.scale = .5, .13, .78
    face.transform.flip_horizontal = True
    project.captions = [
        Caption(uid(), 0, 3.7, "xQc realizes the confidence was UNREAL 😂",
                CaptionStyle(name="Hook Card", size=48, color="#111216", outline_width=0,
                             animation="fade"), True),
        Caption(uid(), .9, 2.7, "HE WAS SO CONFIDENT",
                CaptionStyle(name="Streamer Lime", size=62, color="#DFFF45", animation="pop")),
    ]
    project.save(project_path)
    keep = detect(str(source), 4.0, -38, .35, .1, in_point=4.0)
    print("silence keep ranges:", keep)
    export(project, str(output), PRESETS["Instagram Reels · Compact"],
           progress=lambda value, text: print(f"{value:5.1%} {text}"))
    import subprocess
    raw = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,avg_frame_rate:format=duration,size",
                          "-of", "json", str(output)], capture_output=True, text=True, check=True)
    print(json.dumps(json.loads(raw.stdout), indent=2))
    print("PASS real-media workflow:", output)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "xqc_royalty.mp4")
