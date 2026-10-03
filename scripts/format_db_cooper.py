"""Script to refine framing, background roles, and caption styling in The_Mystery_of_DB_Cooper.kcut."""
import sys
sys.path.insert(0, ".")
import json
import copy
from pathlib import Path
from kinetic_cut.caption_presets import CAPTION_PRESETS

project_path = Path("The_Mystery_of_DB_Cooper.kcut")
with open(project_path, "r", encoding="utf-8") as f:
    p = json.load(f)

# 1. Update background fill clips on video_1
for item in p["timeline"]:
    if item["track"] == "video_1":
        item["role"] = "background"
        item["transform"]["x"] = 0.5
        item["transform"]["y"] = 0.5
        item["transform"]["scale"] = 1.0
        item["transform"]["scale_y"] = 1.0
        # Clean up any manual gaussian blur effect since role="background" uses the engine's auto-blur
        item["effects"] = []

# 2. Update foreground clips on video_2
scales = {
    "fg_01_cockpit": 1.35,
    "fg_02_storm": 1.40,
    "fg_03_briefcase": 1.35,
    "fg_04_money": 1.35,
    "fg_05_news": 1.40,
    "fg_06_diagram": 1.35,
    "fg_07_jump": 1.35,
    "fg_08_evidence": 1.35,
    "fg_09_sketch": 1.45,
}

for item in p["timeline"]:
    if item["track"] == "video_2":
        item["transform"]["y"] = 0.5
        item["transform"]["anchor_y"] = 0.0
        item["transform"]["x"] = 0.5
        item["transform"]["anchor_x"] = 0.0
        cid = item["id"]
        s = scales.get(cid, 1.35)
        item["transform"]["scale"] = s
        item["transform"]["scale_y"] = s
        # Ensure Visual FX parameters are smooth and crisp
        for fx in item.get("effects", []):
            if fx.get("name") == "Punch Zoom":
                fx["zoom_start"] = 1.0
                fx["zoom_target"] = 1.38
                fx["duration"] = 0.5
                fx["easing"] = "Ease Out"
            elif fx.get("name") == "Slow Push-In":
                fx["zoom_start"] = 1.0
                fx["zoom_target"] = 1.25
                fx["easing"] = "Linear"

# 3. Apply Crime Red caption preset
crime_red = CAPTION_PRESETS["crime_red"]
p["subtitle_style"] = copy.deepcopy(crime_red)

# 4. Clean up caption text artifacts (e.g. ",000", "-flight", ".B")
captions = p.get("captions", [])
merged_caps = []
skip = False
for i, cap in enumerate(captions):
    if skip:
        skip = False
        continue
    text = cap["text"].strip()
    # Check if next word is continuation like ",000"
    if i + 1 < len(captions):
        nxt = captions[i + 1]
        nxt_text = nxt["text"].strip()
        if nxt_text.startswith(",000") or nxt_text.startswith("-") or (text in {"D", "D."} and nxt_text.startswith(".B")):
            cap["end"] = nxt["end"]
            cap["text"] = (text + nxt_text).replace("D.B", "D.B.")
            if cap.get("word_timings") and nxt.get("word_timings"):
                cap["word_timings"] = cap["word_timings"] + nxt["word_timings"]
            skip = True
    cap["style"] = copy.deepcopy(crime_red)
    cap["customize"] = False
    merged_caps.append(cap)

p["captions"] = merged_caps

with open(project_path, "w", encoding="utf-8") as f:
    json.dump(p, f, indent=2)

print(f"Successfully formatted {project_path}:")
print(f"  - Foreground clips centered at y=0.5 and scaled for 9:16")
print(f"  - Background clips configured as role='background' for ambient blur fill")
print(f"  - Captions styled with Crime Red preset (Anton 64, red glow, punch anim, y=0.72)")
print(f"  - Cleaned caption count: {len(merged_caps)}")
