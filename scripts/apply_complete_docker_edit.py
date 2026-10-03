import copy
from dataclasses import asdict
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kinetic_cut.assistant import connection_file
from kinetic_cut.mcp_bridge import send_mcp_request
from kinetic_cut.captions import transcribe
from kinetic_cut.model import Caption, CaptionStyle, uid

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
rev = state["revision"]
print(f"Current revision: {rev}, Project name: {state['name']}")

# Find media IDs from live project
media_map = {m['name']: m['id'] for m in state['project']['media']}
print("Live media map:", media_map)

ops = []

# 1. Project rename & settings
ops.append({"op": "rename_project", "name": "Docker in 60 Seconds"})
ops.append({
    "op": "settings",
    "values": {
        "width": 1080,
        "height": 1920,
        "fps": 60,
        "blur": 28.0,
        "background_brightness": 0.60,
        "background_contrast": 1.05,
        "auto_duck": True,
        "duck_amount_db": -11.0
    }
})

# 2. Add tracks if needed
video_tracks = state['project'].get('video_tracks', ['video_1'])
audio_tracks = state['project'].get('audio_tracks', ['audio_1'])

if "video_2" not in video_tracks:
    ops.append({"op": "add_track", "kind": "video"})
if "audio_2" not in audio_tracks:
    ops.append({"op": "add_track", "kind": "audio"})
if "audio_3" not in audio_tracks:
    ops.append({"op": "add_track", "kind": "audio"})

# Set track display names
ops.append({"op": "track", "track": "video_1", "name": "Background Ambient Blur"})
ops.append({"op": "track", "track": "video_2", "name": "Foreground Visuals"})
ops.append({"op": "track", "track": "audio_1", "name": "Voiceover Narration"})
ops.append({"op": "track", "track": "audio_2", "name": "Cyber Synth Music Bed"})
ops.append({"op": "track", "track": "audio_3", "name": "Tech SFX & Impacts"})

# 3. Insert Voiceovers on audio_1
vo_clips = [
    ("vo_beat1_hook.mp3", 0.0, 9.77),
    ("vo_beat2_vm_problem.mp3", 9.77, 14.83),
    ("vo_beat3_containers.mp3", 24.60, 15.86),
    ("vo_beat4_layers.mp3", 40.46, 13.08),
    ("vo_beat5_takeaway.mp3", 53.54, 10.46),
]

for name, start, dur in vo_clips:
    mid = media_map[name]
    ops.append({
        "op": "insert_clip",
        "media_id": mid,
        "track": "audio_1",
        "start": start,
        "duration": dur,
        "role": "source_audio",
        "gain_db": 1.2
    })

# 4. Insert Music Bed on audio_2
music_mid = media_map["cyber_synth_soundtrack.mp3"]
ops.append({
    "op": "insert_clip",
    "media_id": music_mid,
    "track": "audio_2",
    "start": 0.0,
    "duration": 64.0,
    "role": "music",
    "gain_db": -15.0,
    "fade_in": 0.5,
    "fade_out": 2.5
})

# 5. Insert SFX on audio_3
whoosh_mid = media_map["transition_whoosh.mp3"]
blip_mid = media_map["digital_blip.mp3"]
hit_mid = media_map["impact_hit.mp3"]

sfx_events = [
    (hit_mid, 0.0, 1.2, -2.0),
    (whoosh_mid, 9.77, 0.6, -6.0),
    (hit_mid, 24.60, 1.2, -2.0),
    (whoosh_mid, 24.60, 0.6, -6.0),
    (whoosh_mid, 40.46, 0.6, -6.0),
    (blip_mid, 47.00, 0.25, -4.0),
    (blip_mid, 50.50, 0.25, -4.0),
    (whoosh_mid, 53.54, 0.6, -6.0),
    (hit_mid, 58.50, 1.2, -1.5),
]

for mid, start, dur, gain in sfx_events:
    ops.append({
        "op": "insert_clip",
        "media_id": mid,
        "track": "audio_3",
        "start": start,
        "duration": dur,
        "role": "sfx",
        "gain_db": gain
    })

# 6. Insert Visuals (Foreground video_2 and Background video_1)
visual_shots = [
    # (name, start, dur, fg_x, fg_y, fg_scale)
    ("01_hook_dev_meme.png", 0.00, 5.00, 0.50, 0.55, 1.05),
    ("01_hook_dev_meme.png", 5.00, 4.77, 0.50, 0.62, 1.35),
    ("02_vm_architecture.png", 9.77, 4.73, 0.50, 0.54, 1.08),
    ("02_vm_architecture.png", 14.50, 5.00, 0.50, 0.62, 1.35),
    ("02_vm_architecture.png", 19.50, 5.10, 0.50, 0.45, 1.30),
    ("03_container_vs_vm.png", 24.60, 5.40, 0.50, 0.55, 1.08),
    ("03_container_vs_vm.png", 30.00, 5.50, 0.28, 0.58, 1.45),
    ("03_container_vs_vm.png", 35.50, 4.96, 0.28, 0.42, 1.60),
    ("04_docker_layers_stack.png", 40.46, 6.54, 0.50, 0.54, 1.08),
    ("05_terminal_dockerfile.png", 47.00, 6.54, 0.50, 0.55, 1.10),
    ("05_terminal_dockerfile.png", 53.54, 4.96, 0.30, 0.55, 1.35),
    ("06_final_takeaway.png", 58.50, 5.50, 0.50, 0.55, 1.08),
]

fg_clip_ids = []
for name, start, dur, fg_x, fg_y, fg_scale in visual_shots:
    mid = media_map[name]
    # Background blur layer on video_1
    ops.append({
        "op": "insert_clip",
        "media_id": mid,
        "track": "video_1",
        "start": start,
        "duration": dur,
        "role": "background",
        "transform": {
            "x": 0.5,
            "y": 0.5,
            "scale": 2.2,
            "scale_linked": True
        }
    })
    # Foreground focused visual on video_2
    ops.append({
        "op": "insert_clip",
        "media_id": mid,
        "track": "video_2",
        "start": start,
        "duration": dur,
        "role": "normal",
        "transform": {
            "x": fg_x,
            "y": fg_y,
            "scale": fg_scale,
            "scale_linked": True
        }
    })

# 7. Generate captions for each voiceover
print("Transcribing voiceover beats for word-level captions...")
for name, start, dur in vo_clips:
    vo_path = ROOT / "assets_docker_guide" / "audio" / name
    caps, _ = transcribe(str(vo_path), {"whisper_model": "base.en"}, offset=start, words_per_caption=2)
    for c in caps:
        cap_dict = asdict(c)
        ops.append({
            "op": "add",
            "collection": "captions",
            "values": cap_dict
        })

# 8. Apply cyber_cyan preset to all captions and subtitle_style
ops.append({
    "op": "set_caption_style",
    "preset": "cyber_cyan"
})

print(f"Applying atomic batch of {len(ops)} operations to live editor...")
res = call("apply_edits", {"revision": rev, "operations": ops})
print("apply_edits result:", res)

# Seek to beginning
call("seek", {"seconds": 0.0})

# Save the live project to Tech_Guide_Docker.kcut
save_path = str(ROOT / "Tech_Guide_Docker.kcut")
call("project_file", {"operation": "save", "path": save_path})
print(f"Saved live project to {save_path}")
