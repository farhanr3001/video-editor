import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kinetic_cut.assistant import connection_file
from kinetic_cut.mcp_bridge import send_mcp_request

cf = connection_file()
data = json.loads(cf.read_text(encoding='utf-8'))
PORT = data['port']
TOKEN = data['token']
URL = f"http://127.0.0.1:{PORT}/mcp"

def call(tool_name, arguments={}):
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000) % 1000000,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    res = send_mcp_request(URL, TOKEN, payload)
    if "result" in res and "content" in res["result"]:
        text = res["result"]["content"][0]["text"]
        try:
            return json.loads(text)
        except Exception:
            return text
    return res

print("Connected to live editor at:", URL)
state = call("get_state")
print("Project name:", state["name"], "Revision:", state["revision"])
