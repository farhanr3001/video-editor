import sys
import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kinetic_cut.assistant import connection_file
from kinetic_cut.mcp_bridge import send_mcp_request

cf = connection_file()
data = json.loads(cf.read_text(encoding="utf-8"))
port = data["port"]
token = data["token"]
url = f"http://127.0.0.1:{port}/mcp"

out_dir = ROOT / "assets_docker_guide" / "previews"
out_dir.mkdir(parents=True, exist_ok=True)

for ts in [1.0, 12.0, 27.0, 43.0, 50.0, 60.0]:
    send_mcp_request(url, token, {
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": "seek", "arguments": {"seconds": ts}}
    })
    res = send_mcp_request(url, token, {
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": "get_preview", "arguments": {"area": "workspace", "max_width": 960}}
    })
    content = res.get("result", {}).get("content", [])
    img_item = next((c for c in content if c.get("type") == "image"), None)
    if img_item:
        img_bytes = base64.b64decode(img_item["data"])
        p_path = out_dir / f"preview_{ts:.1f}s.png"
        p_path.write_bytes(img_bytes)
        print(f"Saved preview at {ts:.1f}s -> {p_path} ({len(img_bytes)} bytes)")
    else:
        print(f"No image returned for {ts:.1f}s")
