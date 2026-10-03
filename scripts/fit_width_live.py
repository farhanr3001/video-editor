import sys
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call
from kinetic_cut.assistant import connection_file
from kinetic_cut.mcp_bridge import send_mcp_request

state = call("get_state")
rev = state["revision"]
v2_items = [i for i in state["project"]["timeline"] if i["track"] == "video_2"]

print(f"Setting scale=0.5625 (exact fit width) on {len(v2_items)} foreground clips...")
ops = []
for item in v2_items:
    ops.append({
        "op": "item_property",
        "item_id": item["id"],
        "property": "transform",
        "value": {
            "x": 0.5,
            "y": 0.46,
            "scale": 0.5625,
            "scale_linked": True
        }
    })

res = call("apply_edits", {"revision": rev, "operations": ops})
print("apply_edits result:", res.get("undoable"))

call("seek", {"seconds": 26.0})

with open("C:/Users/F/AppData/Local/KineticCut/KineticCut/assistant-connection.json") as f:
    cf = json.load(f)
port = cf["port"]
token = cf["token"]

res_img = send_mcp_request(f"http://127.0.0.1:{port}/mcp", token, {
    "jsonrpc": "2.0", "id": 9,
    "method": "tools/call",
    "params": {"name": "get_preview", "arguments": {"area": "preview", "max_width": 720}}
})

img_item = next((c for c in res_img["result"]["content"] if c["type"] == "image"), None)
if img_item:
    p = ROOT / "assets_docker_guide" / "previews" / "preview_fit_width_26s.png"
    p.write_bytes(base64.b64decode(img_item["data"]))
    print("Saved preview to", p)

call("seek", {"seconds": 0.0})
call("project_file", {"operation": "save"})
print("Project saved!")
