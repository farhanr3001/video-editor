"""End-to-end media smoke test using generated footage only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("KINETIC_CUT_HOME", str(ROOT / "build" / "smoke-test-home"))
sys.path.insert(0, str(ROOT))

from kinetic_cut.exporter import PRESETS, export
from kinetic_cut.media import probe
from kinetic_cut.model import Caption, CaptionStyle, Project, TimelineItem, Transform, make_vertical_group, uid


def run(command):
    print(" ".join(str(x) for x in command[:8]), "…")
    subprocess.run(command, check=True)


def main():
    with tempfile.TemporaryDirectory(prefix="kinetic-smoke-") as directory:
        root = Path(directory)
        source = root / "source.mp4"
        logo_path = root / "logo.png"
        output = root / "vertical.mp4"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=2.2",
             "-f", "lavfi", "-i", "sine=frequency=520:sample_rate=48000:duration=2.2",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(source)])
        from PIL import Image, ImageDraw
        logo = Image.new("RGBA", (300, 120), (8, 10, 12, 220)); draw = ImageDraw.Draw(logo)
        draw.rectangle((8, 8, 292, 112), outline=(223, 255, 69, 255), width=8); draw.text((48, 43), "KINETIC", fill=(223, 255, 69, 255)); logo.save(logo_path)
        media = probe(source)
        logo_media = probe(logo_path)
        project = Project(name="Smoke Test", media=[media, logo_media], timeline=make_vertical_group(media))
        project.settings.width, project.settings.height, project.settings.fps = 720, 1280, 30
        face = next(x for x in project.timeline if x.role == "facecam")
        face.crop.x, face.crop.y, face.crop.width, face.crop.height = .62, .02, .35, .45
        face.transform.x, face.transform.y, face.transform.scale = .75, .18, .52
        face.transform.shape = "circle"
        overlay_track=project.add_track("video")
        project.timeline.append(TimelineItem(uid(), logo_media.id, overlay_track, .3, 1.4,
                                             transform=Transform(.18, .9, .28, rotation=-8),role="normal"))
        project.captions = [
            Caption(uid(), 0, 1.6, "A REAL EXPORT", CaptionStyle(animation="pop")),
            Caption(uid(), 0, 1.1, "Watch this workflow", CaptionStyle(size=52, color="#111216", outline_width=0), True),
        ]
        export(project, str(output), PRESETS["Instagram Reels · Compact"], progress=lambda value, text: print(f"{value:5.1%} {text}"))
        result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)], capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        video = next(x for x in payload["streams"] if x["codec_type"] == "video")
        assert (int(video["width"]), int(video["height"])) == (720, 1280), video
        assert any(x["codec_type"] == "audio" for x in payload["streams"])
        saved = root / "smoke.kcut"; project.save(saved); loaded = Project.load(saved)
        assert len(loaded.timeline) == 5 and len(loaded.captions) == 2
        print(f"PASS · {output.stat().st_size / 1024:.0f} KiB · 720×1280 · audio · captions · save/load")


if __name__ == "__main__":
    main()
