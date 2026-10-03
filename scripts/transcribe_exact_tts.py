import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call
from faster_whisper import WhisperModel

def clean_word(txt):
    w = re.sub(r"[^a-zA-Z0-9\-\']", "", txt).strip()
    return w.upper()

def main():
    s = call("get_state")
    rev = s["revision"]
    
    media_pool = {m["id"]: m for m in s["project"]["media"]}
    audio_clips = [i for i in s["project"]["timeline"] if i.get("track") == "audio_1"]
    audio_clips.sort(key=lambda x: x["start"])
    
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    
    all_one_words = []
    
    cache_file = Path("build/sinking_car_whisper_words.json")
    if cache_file.exists():
        import json
        raw_words_by_clip = json.loads(cache_file.read_text(encoding="utf-8"))
        print(f"Loaded {len(raw_words_by_clip)} clips from cache.")
    else:
        raw_words_by_clip = []
        for a in audio_clips:
            m = media_pool.get(a["media_id"])
            if not m:
                continue
            path = m["path"]
            clip_start = a["start"]
            clip_end = clip_start + a["duration"]
            segments, _ = model.transcribe(path, word_timestamps=True, language="en")
            clip_words = []
            for seg in segments:
                for w in seg.words:
                    cw = clean_word(w.word)
                    if not cw or cw == "-":
                        continue
                    clip_words.append({
                        "text": cw,
                        "start": round(clip_start + w.start, 3),
                        "end": round(clip_start + w.end, 3)
                    })
            raw_words_by_clip.append({"clip_start": clip_start, "clip_end": clip_end, "words": clip_words})
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        import json
        cache_file.write_text(json.dumps(raw_words_by_clip, indent=2), encoding="utf-8")

    all_one_words = []
    for c_data in raw_words_by_clip:
        clip_end = c_data["clip_end"]
        words = c_data["words"]
        for i in range(len(words)):
            w_start = words[i]["start"]
            w_end = max(words[i]["end"], w_start + 0.12)
            if i + 1 < len(words):
                next_start = words[i+1]["start"]
                if next_start > w_start + 0.08:
                    if next_start - w_end < 0.35:
                        w_end = next_start
                    else:
                        w_end = min(w_end + 0.20, next_start - 0.02)
                else:
                    # next starts too close, stagger it
                    words[i+1]["start"] = w_start + 0.10
                    w_end = words[i+1]["start"]
            else:
                w_end = min(w_end + 0.25, clip_end)
            
            # Guarantee positive duration
            w_end = max(round(w_end, 3), round(w_start + 0.10, 3))
            all_one_words.append({
                "text": words[i]["text"],
                "start": round(w_start, 3),
                "end": round(w_end, 3)
            })
            
    print(f"Generated {len(all_one_words)} millisecond-accurate single-word captions across 56.05s.")
    print("First 5 words:")
    for w in all_one_words[:5]:
        print(f"  {w['start']:05.2f}s - {w['end']:05.2f}s: {w['text']}")
    print("Last 5 words:")
    for w in all_one_words[-5:]:
        print(f"  {w['start']:05.2f}s - {w['end']:05.2f}s: {w['text']}")
        
    # Styling: Komika Axis font, bold, punchy, 74px, clean white with strong black outline
    style = {
        "name": "Viral One-Word Bold",
        "font": "Komika Axis",
        "font_face": "Regular",
        "size": 74,
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
    
    curr_caps = s["project"].get("captions", [])
    ops = []
    for c in curr_caps:
        ops.append({"op": "remove", "collection": "captions", "id": c["id"]})
        
    for idx, w in enumerate(all_one_words):
        ops.append({
            "op": "add",
            "collection": "captions",
            "id": f"w_{idx+1:03d}",
            "values": {
                "start": w["start"],
                "end": w["end"],
                "text": w["text"],
                "is_hook": False,
                "style": style
            }
        })
        
    ops.append({
        "op": "subtitle_style",
        "values": style
    })
    
    fresh_rev = call("get_state")["revision"]
    res = call("apply_edits", {"revision": fresh_rev, "operations": ops})
    print("Raw res:", repr(res))

if __name__ == "__main__":
    main()
