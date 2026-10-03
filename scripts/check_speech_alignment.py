import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

def main():
    s = call("get_state")
    caps = s["project"].get("captions", [])
    print(f"Total captions: {len(caps)}")
    for c in caps[-15:]:
        print(f"{c['id']}: {c['start']:05.2f}s - {c['end']:05.2f}s | {c['text']}")
        
    audio_clips = [i for i in s["project"]["timeline"] if i.get("track") == "audio_1"]
    print("\nAudio 1 speech clips:")
    for a in audio_clips:
        print(f"{a['id']}: {a['start']:05.2f}s - {a['start']+a['duration']:05.2f}s (dur={a['duration']:.2f}s)")

if __name__ == "__main__":
    main()
