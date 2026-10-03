import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

def main():
    state = call("get_state")
    rev = state["revision"]
    print("Initial revision:", rev)
    print("Video tracks in project:", state["project"]["video_tracks"])
    
    # 1. Clean out lingering transitions
    ops = []
    for t in state["project"].get("transitions", []):
        ops.append({"op": "remove", "collection": "transitions", "id": t["id"]})
    
    # Choose primary video track (e.g. video_2)
    video_track = state["project"]["video_tracks"][0]
    print(f"Target video track: {video_track}")
    
    # Also rename track to 'Video 1' if needed
    ops.append({"op": "track", "track": video_track, "name": "Video 1"})
    
    # Delete extra video tracks if empty
    for extra_track in state["project"]["video_tracks"][1:]:
        clips_on_track = [i for i in state["project"]["timeline"] if i.get("track") == extra_track]
        if not clips_on_track:
            ops.append({"op": "delete_track", "track": extra_track})
    
    # 2. Clips configuration
    clips_data = [
        {"media_id": "4de79c3c9c4c", "start": 0.0, "duration": 4.20, "desc": "Beat 01 - Car plunge"},
        {"media_id": "bec660164db8", "start": 4.2, "duration": 3.90, "desc": "Beat 02 - Water rushing windscreen"},
        {"media_id": "ee45c432ff1a", "start": 8.1, "duration": 3.90, "desc": "Beat 03 - Pushing locked door"},
        {"media_id": "dd34abe821fe", "start": 12.0, "duration": 3.50, "desc": "Beat 04 - Cabin flooding bubbles"},
        {"media_id": "3fa7b8c589b5", "start": 15.5, "duration": 3.80, "desc": "Beat 05 - Submerged air pocket breath"},
        {"media_id": "82f845b00504", "start": 19.3, "duration": 3.70, "desc": "Beat 06 - Seatbelt release"},
        {"media_id": "18c50f9305b3", "start": 23.0, "duration": 4.00, "desc": "Beat 07 - Driver helping passengers"},
        {"media_id": "899faefe01a9", "start": 27.0, "duration": 4.70, "desc": "Beat 08 - Window rolling down"},
        {"media_id": "6cf7ccab257e", "start": 31.7, "duration": 3.80, "desc": "Beat 09 - Laminated windshield unbreakable"},
        {"media_id": "1a23b0a358df", "start": 35.5, "duration": 4.00, "desc": "Beat 10 - Headrest removal metal prongs"},
        {"media_id": "88f853440b2c", "start": 39.5, "duration": 4.40, "desc": "Beat 11 - Window corner shattering"},
        {"media_id": "f7ae048fe1cf", "start": 43.9, "duration": 4.10, "desc": "Beat 12 - Escape head-first window"},
        {"media_id": "122cad4c902d", "start": 48.0, "duration": 4.00, "desc": "Beat 13 - Car sinking deep"},
        {"media_id": "1e03a21d80fa", "start": 52.0, "duration": 4.05, "desc": "Beat 14 - Swimming to surface light"},
    ]
    
    for c in clips_data:
        ops.append({
            "op": "insert_clip",
            "media_id": c["media_id"],
            "track": video_track,
            "start": c["start"],
            "duration": c["duration"],
            "in_point": 0.0,
            "role": "normal"
        })
        
    print(f"Applying {len(ops)} operations...")
    res = call("apply_edits", {"revision": rev, "operations": ops})
    print("apply_edits result:", res)

if __name__ == "__main__":
    main()
