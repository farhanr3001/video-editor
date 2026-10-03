import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

state = call("get_state")
v2_items = [i for i in state["project"]["timeline"] if i["track"] == "video_2"]
v2_items.sort(key=lambda x: x["start"])
print(f"Found {len(v2_items)} items on video_2:")

vfx_plan = [
    ("Slow Push-In", {"start_zoom": 1.0, "target_zoom": 1.15, "duration": 5.0, "easing": "Ease Out"}),
    ("Ken Burns", {"start_scale": 1.0, "end_scale": 1.18, "duration": 4.77}),
    ("Slow Push-In", {"start_zoom": 1.0, "target_zoom": 1.14, "duration": 4.73}),
    ("Punch Zoom", {"start_zoom": 1.0, "target_zoom": 1.30, "duration": 0.5, "easing": "Ease Out"}),
    ("Slow Push-In", {"start_zoom": 1.0, "target_zoom": 1.12, "duration": 5.10}),
    ("Slow Push-In", {"start_zoom": 1.0, "target_zoom": 1.12, "duration": 5.40}),
    ("Slow Push-In", {"start_zoom": 1.0, "target_zoom": 1.16, "duration": 5.50}),
    ("Punch Zoom", {"start_zoom": 1.0, "target_zoom": 1.35, "duration": 0.5, "easing": "Ease Out"}),
    ("Slow Push-In", {"start_zoom": 1.0, "target_zoom": 1.14, "duration": 6.54}),
    ("Slow Push-In", {"start_zoom": 1.0, "target_zoom": 1.15, "duration": 6.54}),
    ("Punch Zoom", {"start_zoom": 1.0, "target_zoom": 1.28, "duration": 0.45, "easing": "Ease Out"}),
    ("Slow Push-In", {"start_zoom": 1.0, "target_zoom": 1.14, "duration": 5.50}),
]

for idx, (effect, props) in enumerate(vfx_plan):
    item = v2_items[idx]
    item_id = item["id"]
    print(f"Applying {effect} to shot {idx+1} (id={item_id})...")
    res = call("apply_visual_fx", {
        "item_id": item_id,
        "effect": effect,
        "properties": props
    })

call("seek", {"seconds": 0.0})
call("project_file", {"operation": "save"})
print("All 12 procedural Visual FX applied and project saved!")
