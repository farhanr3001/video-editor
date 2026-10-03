import sys
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

# Exact curated 2-3 word phrases matching the audio verbatim
CURATED_CHUNKS = [
    # Beat 1
    ["If", "your", "car"],
    ["ever", "plunges", "into"],
    ["deep", "water,"],
    ["you", "have", "less"],
    ["than", "60", "seconds"],
    ["to", "survive,"],
    ["and", "what", "most"],
    ["people", "do", "first"],
    ["will", "get"],
    ["them", "killed."],
    # Beat 2
    ["Do", "not", "try"],
    ["to", "open"],
    ["the", "door!"],
    ["Water", "pressure"],
    ["from", "the", "outside"],
    ["exerts", "thousands"],
    ["of", "pounds"],
    ["against", "it,"],
    ["making", "it"],
    ["impossible", "to", "budge."],
    ["Remember", "three", "letters:"],
    ["S", "-", "W", "-", "O."],
    # Beat 3
    ["First:", "seatbelts"],
    ["off", "immediately!"],
    ["If", "you", "have"],
    ["children,", "unbuckle"],
    ["them", "now!"],
    ["Second:", "open"],
    ["the", "window!"],
    ["Even", "while", "sinking,"],
    ["electric", "windows"],
    ["will", "usually", "work"],
    ["for", "the", "first"],
    ["30", "to"],
    ["60", "seconds."],
    # Beat 4
    ["If", "the", "window"],
    ["is", "jammed,"],
    ["never", "hit"],
    ["the", "windshield!"],
    ["It's", "unbreakable"],
    ["laminated", "glass!"],
    ["Instead,", "pull", "off"],
    ["your", "headrest"],
    ["and", "jam", "the"],
    ["steel", "prongs"],
    ["into", "the", "bottom"],
    ["corner", "of", "the"],
    ["side", "window"],
    ["to", "shatter", "it!"],
    # Beat 5
    ["Third:", "Out!"],
    ["Climb", "out"],
    ["through", "the", "window"],
    ["head", "first,"],
    ["pushing", "kids", "out"],
    ["ahead", "of", "you!"],
    ["Never", "wait", "for"],
    ["the", "car", "to"],
    ["fill", "with", "water!"],
    ["Memorize", "S-W-O:"],
    ["Seatbelt,", "Window,", "Out."],
    ["It", "could", "save"],
    ["your", "life!"]
]

def clean_w(w):
    return re.sub(r"[^a-zA-Z0-9]", "", w).lower()

def main():
    s = call("get_state")
    caps = s["project"].get("captions", [])
    
    # Collect all words with absolute timestamps
    words = []
    for c in caps:
        for w in c.get("word_timings", []):
            words.append({
                "raw": w["text"],
                "clean": clean_w(w["text"]),
                "start": round(c["start"] + w["start"], 3),
                "end": round(c["start"] + w["end"], 3)
            })
            
    print(f"Extracted {len(words)} timed words from Whisper.")
    
    # Match each curated chunk to word timestamps
    matched_captions = []
    w_idx = 0
    num_words = len(words)
    
    for c_idx, chunk in enumerate(CURATED_CHUNKS):
        chunk_text = " ".join(chunk)
        # Find matching range in words
        chunk_clean = [clean_w(x) for x in chunk if clean_w(x)]
        if not chunk_clean:
            continue
            
        start_t = None
        end_t = None
        
        # Advance w_idx to find the start word
        target = chunk_clean[0]
        while w_idx < num_words and words[w_idx]["clean"] != target:
            # allow skip if mismatch
            w_idx += 1
            
        if w_idx < num_words:
            start_t = words[w_idx]["start"]
            # match remaining words in chunk
            for cw in chunk_clean:
                if w_idx < num_words and (words[w_idx]["clean"] == cw or not cw):
                    end_t = words[w_idx]["end"]
                    w_idx += 1
                else:
                    break
        else:
            # Fallback if past end
            start_t = matched_captions[-1]["end"] if matched_captions else 0.0
            end_t = start_t + 1.2
            
        if end_t is None or end_t <= start_t:
            end_t = start_t + 0.8
            
        matched_captions.append({
            "id": f"caption_{c_idx+1:03d}",
            "start": round(start_t, 2),
            "end": round(end_t, 2),
            "text": chunk_text
        })
        
    # Extend gaps smoothly so there's no flashing between adjacent cards (max 0.2s extension)
    for i in range(len(matched_captions) - 1):
        curr_end = matched_captions[i]["end"]
        next_start = matched_captions[i+1]["start"]
        gap = next_start - curr_end
        if 0 < gap <= 0.35:
            matched_captions[i]["end"] = next_start
        elif gap > 0.35:
            matched_captions[i]["end"] = round(curr_end + 0.2, 2)
            
    print(f"Created {len(matched_captions)} matched captions.")
    for i, c in enumerate(matched_captions):
        w_len = len(c["text"].split())
        print(f"[{i:02d}] {c['start']:05.2f}s - {c['end']:05.2f}s ({w_len}w): \"{c['text']}\"")
        
    return matched_captions

if __name__ == "__main__":
    main()
