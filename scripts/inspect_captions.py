import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

def main():
    s = call("get_state")
    captions = s["project"].get("captions", [])
    print(f"Total captions: {len(captions)}")
    for i, c in enumerate(captions):
        words = c["text"].split()
        print(f"[{i:02d}] {c['start']:05.2f}s - {c['end']:05.2f}s ({len(words)}w): \"{c['text']}\"")
        
    print("\nCurrent subtitle_style:")
    style = s["project"].get("subtitle_style", {})
    for k in ["font", "size", "color", "outline", "outline_width", "shadow_enabled", "glow_enabled", "glow_color", "uppercase", "position_y"]:
        print(f"  {k}: {style.get(k)}")

if __name__ == "__main__":
    main()
