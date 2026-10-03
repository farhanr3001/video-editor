import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

def main():
    s = call("get_state")
    v_clips = [i for i in s["project"]["timeline"] if i.get("track") in s["project"]["video_tracks"]]
    print(f"Total video clips: {len(v_clips)}")
    for c in v_clips:
        m = next((m for m in s["project"]["media"] if m["id"] == c["media_id"]), None)
        w = m.get("width") if m else "?"
        h = m.get("height") if m else "?"
        print(f"{c['id']} | {c.get('media_name')} ({w}x{h}):")
        print(f"  transform: {c.get('transform')}")
        print(f"  crop: {c.get('crop')}")
        
    print("\nProject settings:")
    print("  width:", s["project"]["settings"]["width"])
    print("  height:", s["project"]["settings"]["height"])

if __name__ == "__main__":
    main()
