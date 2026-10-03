import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

state = call("get_state")
rev = state["revision"]
timeline = state["project"]["timeline"]

ops = []
v2_clips = [i for i in timeline if i["track"] == "video_2"]
v1_clips = [i for i in timeline if i["track"] == "video_1"]

print(f"Updating {len(v2_clips)} foreground clips and {len(v1_clips)} background clips...")

# 1. Update foreground clips on video_2:
# 16:9 diagram fitted to canvas with safe margin (scale: 0.30)
# Centered at x: 0.50, y: 0.46 (leaving lower third for captions)
for clip in v2_clips:
    ops.append({
        "op": "update",
        "collection": "timeline",
        "id": clip["id"],
        "values": {
            "transform": {
                "x": 0.5,
                "y": 0.46,
                "scale": 0.30,
                "scale_y": 0.30,
                "scale_linked": True,
                "rotation": 0.0,
                "shape": "rectangle",
                "anchor_x": 0.0,
                "anchor_y": 0.0,
                "pitch": 0.0,
                "yaw": 0.0
            },
            "role": "normal",
            "effects": [
                {
                    "name": "Slow Push-In",
                    "enabled": True,
                    "category": "Visual FX",
                    "subcategory": "Zooms",
                    "start_zoom": 1.0,
                    "target_zoom": 1.03,
                    "duration": clip["duration"],
                    "easing": "Ease Out"
                }
            ]
        }
    })

# 2. Update background clips on video_1:
# Full media item below it with Gaussian Blur effect dragged onto it
for clip in v1_clips:
    ops.append({
        "op": "update",
        "collection": "timeline",
        "id": clip["id"],
        "values": {
            "transform": {
                "x": 0.5,
                "y": 0.5,
                "scale": 1.0,
                "scale_y": 1.0,
                "scale_linked": True,
                "rotation": 0.0,
                "shape": "rectangle",
                "anchor_x": 0.0,
                "anchor_y": 0.0,
                "pitch": 0.0,
                "yaw": 0.0
            },
            "role": "normal",
            "opacity": 85.0,
            "brightness": -0.15,
            "effects": [
                {
                    "name": "Gaussian Blur",
                    "enabled": True,
                    "horizontal": 45.0,
                    "vertical": 45.0,
                    "linked": True,
                    "border": "Reflect",
                    "blend": 100.0
                }
            ]
        }
    })

res = call("apply_edits", {"revision": rev, "operations": ops})
print("apply_edits raw response:", repr(res))
if isinstance(res, dict):
    print("apply_edits result:", res.get("undoable"), "New revision:", res.get("revision"))
else:
    print("apply_edits returned non-dict:", res)

# Save to Tech_Guide_Docker.kcut so the project is persisted on disk
save_res = call("project_file", {
    "operation": "save",
    "path": str(ROOT / "Tech_Guide_Docker.kcut"),
    "overwrite": True
})
print("project save result:", save_res)
