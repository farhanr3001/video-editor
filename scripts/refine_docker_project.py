import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kinetic_cut.model import Project

project_path = ROOT / "Tech_Guide_Docker.kcut"
print(f"Loading {project_path}...")
project = Project.load(project_path)

# 1. Project settings: rich ambient blur and contrast
project.settings.width = 1080
project.settings.height = 1920
project.settings.fps = 60
project.settings.blur = 35.0
project.settings.background_brightness = 0.52
project.settings.background_contrast = 1.12
project.settings.auto_duck = True
project.settings.duck_amount_db = -11.0

# 2. Re-scale foreground and configure background
v2_items = [i for i in project.timeline if i.track == "video_2"]
v1_items = [i for i in project.timeline if i.track == "video_1"]

print(f"Refining {len(v2_items)} foreground clips on video_2...")
for item in v2_items:
    # 100% width fit, zero cropping on left/right edges!
    item.transform.x = 0.5
    item.transform.y = 0.46
    item.transform.scale = 1.0
    item.transform.scale_y = 1.0
    item.transform.scale_linked = True
    item.transform.anchor_x = 0.0
    item.transform.anchor_y = 0.0
    item.role = "normal"

    # Gentle, subtle push-in (1.0 -> 1.04) so text remains completely inside frame
    item.effects = [
        {
            "name": "Slow Push-In",
            "enabled": True,
            "category": "Visual FX",
            "subcategory": "Zooms",
            "start_zoom": 1.0,
            "target_zoom": 1.04,
            "duration": item.duration,
            "easing": "Ease Out"
        }
    ]

print(f"Refining {len(v1_items)} background clips on video_1...")
for item in v1_items:
    item.role = "background"
    item.transform.x = 0.5
    item.transform.y = 0.5
    item.transform.scale = 1.0
    item.transform.scale_y = 1.0
    # Add Gaussian Blur effect to ensure deep background blur
    item.effects = [
        {
            "name": "Gaussian Blur",
            "enabled": True,
            "horizontal": 32.0,
            "vertical": 32.0,
            "linked": True,
            "border": "Reflect",
            "blend": 100.0
        }
    ]

# 3. Position captions safely below the 16:9 chart
project.subtitle_style.position_x = 0.5
project.subtitle_style.position_y = 0.78
project.subtitle_style.font = "Montserrat"
project.subtitle_style.font_face = "Bold"
project.subtitle_style.size = 60
project.subtitle_style.color = "#00F0FF"
project.subtitle_style.outline = "#050B14"
project.subtitle_style.outline_width = 6
project.subtitle_style.glow_enabled = True
project.subtitle_style.glow_follow_color = True
project.subtitle_style.glow_color = "#00F0FF"
project.subtitle_style.glow_radius = 15.0
project.subtitle_style.glow_opacity = 75.0
project.subtitle_style.highlight = "#00F0FF"
project.subtitle_style.animation = "punch"
project.subtitle_style.uppercase = True

for c in project.captions:
    c.style.position_x = 0.5
    c.style.position_y = 0.78
    c.style.font = "Montserrat"
    c.style.font_face = "Bold"
    c.style.size = 60
    c.style.color = "#00F0FF"
    c.style.outline = "#050B14"
    c.style.outline_width = 6
    c.style.glow_enabled = True
    c.style.glow_follow_color = True
    c.style.glow_color = "#00F0FF"
    c.style.glow_radius = 15.0
    c.style.glow_opacity = 75.0
    c.style.highlight = "#00F0FF"
    c.style.animation = "punch"
    c.style.uppercase = True

# Reset playhead to start
project.playhead = 0.0

project.save(project_path)
print(f"Successfully refined and saved project to {project_path}!")
