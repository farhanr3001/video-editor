import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call
from scripts.align_curated_captions import CURATED_CHUNKS, clean_w

def main():
    s = call("get_state")
    rev = s["revision"]
    print("Current revision:", rev)
    
    video_tracks = s["project"]["video_tracks"]
    v_clips = [i for i in s["project"]["timeline"] if i.get("track") in video_tracks]
    print(f"Found {len(v_clips)} video clips to re-center.")
    
    ops = []
    # 1. Re-center all video clips to x=0.5, y=0.5, scale=1.0 (perfect edge-to-edge 9:16 vertical fill)
    for c in v_clips:
        ops.append({
            "op": "update",
            "collection": "timeline",
            "id": c["id"],
            "values": {
                "transform": {
                    "x": 0.5,
                    "y": 0.5,
                    "scale": 1.0,
                    "scale_y": None,
                    "scale_linked": True,
                    "rotation": 0.0
                },
                "crop": {
                    "x": 0.0,
                    "y": 0.0,
                    "width": 1.0,
                    "height": 1.0
                }
            }
        })
        
    print(f"Applying centering edits for {len(v_clips)} clips...")
    res = call("apply_edits", {"revision": rev, "operations": ops})
    print("apply_edits centering result:", res.get("undoable"))
    new_rev = res.get("revision")
    
    # 2. Extract words and build 2-3 word captions
    s2 = call("get_state")
    curr_caps = s2["project"].get("captions", [])
    words = []
    for c in curr_caps:
        for w in c.get("word_timings", []):
            words.append({
                "raw": w["text"],
                "clean": clean_w(w["text"]),
                "start": round(c["start"] + w["start"], 3),
                "end": round(c["start"] + w["end"], 3)
            })
            
    print(f"Collected {len(words)} word timings.")
    
    # Match curated 2-3 word chunks
    w_idx = 0
    num_words = len(words)
    new_captions = []
    
    for c_idx, chunk in enumerate(CURATED_CHUNKS):
        chunk_clean = [clean_w(x) for x in chunk if clean_w(x)]
        if not chunk_clean:
            continue
            
        target = chunk_clean[0]
        while w_idx < num_words and words[w_idx]["clean"] != target:
            w_idx += 1
            
        start_t = None
        end_t = None
        if w_idx < num_words:
            start_t = words[w_idx]["start"]
            for cw in chunk_clean:
                if w_idx < num_words and (words[w_idx]["clean"] == cw or not cw):
                    end_t = words[w_idx]["end"]
                    w_idx += 1
                else:
                    break
        else:
            start_t = new_captions[-1]["end"] if new_captions else 0.0
            end_t = start_t + 1.1
            
        if end_t is None or end_t <= start_t:
            end_t = start_t + 0.8
            
        new_captions.append({
            "id": f"cap_{c_idx+1:03d}",
            "start": round(start_t, 2),
            "end": round(end_t, 2),
            "text": " ".join(chunk)
        })
        
    for i in range(len(new_captions) - 1):
        c_end = new_captions[i]["end"]
        n_start = new_captions[i+1]["start"]
        gap = n_start - c_end
        if 0 < gap <= 0.35:
            new_captions[i]["end"] = n_start
        elif gap > 0.35:
            new_captions[i]["end"] = round(c_end + 0.2, 2)
            
    # 3. Clean and modern caption style
    clean_style = {
        "name": "Clean Modern Shorts",
        "font": "Montserrat",
        "font_face": "Bold",
        "size": 52,
        "uppercase": False,
        "color": "#FFFFFF",
        "outline": "#000000",
        "outline_width": 4,
        "shadow_enabled": True,
        "shadow_color": "#000000",
        "shadow_x": 2.0,
        "shadow_y": 2.0,
        "shadow_blur": 4.0,
        "shadow_opacity": 85.0,
        "glow_enabled": False,
        "highlight": "#FFE600",
        "animation": "pop",
        "position_x": 0.5,
        "position_y": 0.76,
        "background_enabled": False
    }
    
    # Replace captions via apply_edits
    cap_ops = []
    # Remove existing captions
    for old_c in curr_caps:
        cap_ops.append({"op": "remove", "collection": "captions", "id": old_c["id"]})
        
    # Add new rechunked captions
    for nc in new_captions:
        cap_ops.append({
            "op": "add",
            "collection": "captions",
            "id": nc["id"],
            "values": {
                "start": nc["start"],
                "end": nc["end"],
                "text": nc["text"],
                "is_hook": nc["start"] < 8.0,
                "style": clean_style
            }
        })
        
    # Set subtitle_style
    cap_ops.append({
        "op": "subtitle_style",
        "values": clean_style
    })
    
    print(f"Applying {len(cap_ops)} caption operations...")
    res2 = call("apply_edits", {"revision": new_rev, "operations": cap_ops})
    print("apply_edits captions result:", res2.get("undoable"), "New revision:", res2.get("revision"))

if __name__ == "__main__":
    main()
