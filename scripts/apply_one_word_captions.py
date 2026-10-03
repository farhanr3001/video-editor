import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

def clean_word(txt):
    # Strip stray punctuation for clean 1-word display
    w = re.sub(r"[^a-zA-Z0-9\-\']", "", txt).strip()
    return w.upper()

def main():
    s = call("get_state")
    rev = s["revision"]
    print("Initial revision:", rev)
    
    curr_caps = s["project"].get("captions", [])
    
    # Collect all individual words with absolute start & end
    words = []
    for c in curr_caps:
        c_start = c["start"]
        for w in c.get("word_timings", []):
            raw = w["text"].strip()
            cw = clean_word(raw)
            if not cw:
                continue
            words.append({
                "text": cw,
                "start": round(c_start + w["start"], 3),
                "end": round(c_start + w["end"], 3)
            })
            
    # Also if captions didn't have word_timings, extract from text if needed
    if not words and curr_caps:
        for c in curr_caps:
            parts = c["text"].split()
            dur = c["end"] - c["start"]
            step = dur / max(1, len(parts))
            for idx, p in enumerate(parts):
                cw = clean_word(p)
                if cw:
                    words.append({
                        "text": cw,
                        "start": round(c["start"] + idx * step, 3),
                        "end": round(c["start"] + (idx + 1) * step, 3)
                    })
                    
    # Remove any trailing stray artifact (e.g. "I" at 55.46s)
    if words and words[-1]["text"] in {"I", "A"} and words[-1]["start"] > 55.3:
        words.pop()
        
    print(f"Extracted {len(words)} individual words.")
    
    # Build 1-word captions with smooth hold (no flicker between words)
    one_word_caps = []
    for i, w in enumerate(words):
        start_t = w["start"]
        end_t = w["end"]
        if i + 1 < len(words):
            next_start = words[i+1]["start"]
            gap = next_start - end_t
            if 0 < gap <= 0.40:
                end_t = next_start  # seamless handoff
            elif gap > 0.40:
                end_t = min(round(end_t + 0.25, 3), next_start)
        else:
            end_t = round(end_t + 0.35, 3)
            
        one_word_caps.append({
            "id": f"word_{i+1:03d}",
            "start": start_t,
            "end": end_t,
            "text": w["text"]
        })
        
    # High-impact, viral 1-word caption style:
    # Komika Axis (or Montserrat Black), bold punchy uppercase with thick outline and drop shadow
    style = {
        "name": "Viral One-Word Bold",
        "font": "Komika Axis",
        "font_face": "Regular",
        "size": 72,
        "uppercase": True,
        "color": "#FFFFFF",
        "outline": "#000000",
        "outline_width": 8,
        "shadow_enabled": True,
        "shadow_color": "#000000",
        "shadow_x": 4.0,
        "shadow_y": 4.0,
        "shadow_blur": 6.0,
        "shadow_opacity": 90.0,
        "glow_enabled": False,
        "highlight": "#FFE600",
        "animation": "pop",
        "position_x": 0.5,
        "position_y": 0.70,
        "background_enabled": False
    }
    
    ops = []
    # Remove existing captions
    for c in curr_caps:
        ops.append({"op": "remove", "collection": "captions", "id": c["id"]})
        
    # Insert one-word captions
    for owc in one_word_caps:
        ops.append({
            "op": "add",
            "collection": "captions",
            "id": owc["id"],
            "values": {
                "start": owc["start"],
                "end": owc["end"],
                "text": owc["text"],
                "is_hook": False,
                "style": style
            }
        })
        
    ops.append({
        "op": "subtitle_style",
        "values": style
    })
    
    print(f"Applying {len(ops)} operations for 1-word captions...")
    res = call("apply_edits", {"revision": rev, "operations": ops})
    print("Result:", res.get("undoable"), "New revision:", res.get("revision"))

if __name__ == "__main__":
    main()
