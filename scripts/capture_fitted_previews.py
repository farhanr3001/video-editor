import sys
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import URL, TOKEN, send_mcp_request, call

out_dir = ROOT / "assets_docker_guide" / "previews"
out_dir.mkdir(parents=True, exist_ok=True)

timestamps = [
    (12.0, "preview_fitted_12s_vm.png"),
    (26.0, "preview_fitted_26s_containers.png"),
    (42.0, "preview_fitted_42s_layers.png"),
    (48.0, "preview_fitted_48s_terminal.png"),
    (58.0, "preview_fitted_58s_verdict.png"),
]

for sec, filename in timestamps:
    call("seek", {"seconds": sec})
    payload = {
        "jsonrpc": "2.0",
        "id": int(sec * 100),
        "method": "tools/call",
        "params": {
            "name": "get_preview",
            "arguments": {"area": "preview", "max_width": 720}
        }
    }
    res = send_mcp_request(URL, TOKEN, payload)
    contents = res.get("result", {}).get("content", [])
    img_item = next((c for c in contents if c.get("type") == "image"), None)
    if img_item and "data" in img_item:
        img_bytes = base64.b64decode(img_item["data"])
        target = out_dir / filename
        target.write_bytes(img_bytes)
        print(f"Captured {target} ({len(img_bytes)} bytes)")
    else:
        print(f"Failed to capture {filename}:", res)

