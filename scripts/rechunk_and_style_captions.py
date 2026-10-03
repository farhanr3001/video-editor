import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.execute_live_edit import call

def get_words_and_rechunk():
    s = call("get_state")
    caps = s["project"].get("captions", [])
    
    words = []
    for c in caps:
        c_start = c["start"]
        for w in c.get("word_timings", []):
            txt = w["text"].strip()
            # Clean unwanted artifacts
            if not txt:
                continue
            words.append({
                "text": txt,
                "start": round(c_start + w["start"], 3),
                "end": round(c_start + w["end"], 3)
            })
            
    # Filter out stray artifact at the very end if any (like single stray "I")
    if words and words[-1]["text"].lower() in {"i", "a", "."} and words[-1]["start"] > 55.3:
        words.pop()
        
    print(f"Extracted {len(words)} clean timed words.")
    
    # Chunk into 2-3 words per caption, NEVER 1 word!
    chunks = []
    i = 0
    n = len(words)
    while i < n:
        remaining = n - i
        # If remaining is 4: make 2 and 2
        # If remaining is 5: make 3 and 2
        # If remaining is 3: make 3
        # If remaining is 2: make 2
        # If remaining is 1: (should not happen with this logic, merged into prev)
        if remaining == 4:
            take = 2
        elif remaining == 1 and chunks:
            # merge into previous chunk
            chunks[-1].append(words[i])
            break
        elif remaining in {2, 3}:
            take = remaining
        else:
            # Default chunk size: 2 or 3 words based on punctuation or pause
            # If word 2 ends with punctuation, take 2, else 3
            w0 = words[i]["text"]
            w1 = words[i+1]["text"] if i+1 < n else ""
            w2 = words[i+2]["text"] if i+2 < n else ""
            
            # Check pause between words
            pause_after_1 = (words[i+1]["start"] - words[i]["end"]) if i+1 < n else 0
            pause_after_2 = (words[i+2]["start"] - words[i+1]["end"]) if i+2 < n else 0
            
            if pause_after_1 > 0.4:
                take = 2
            elif w1.endswith((".", ",", "!", "?", ";", ":")):
                take = 2
            elif pause_after_2 > 0.4 or w2.endswith((".", ",", "!", "?", ";", ":")):
                take = 3
            else:
                take = 3
                
        chunk = words[i:i+take]
        chunks.append(chunk)
        i += take
        
    new_captions = []
    for idx, ch in enumerate(chunks):
        ch_text = " ".join(w["text"] for w in ch)
        start_t = ch[0]["start"]
        end_t = ch[-1]["end"]
        # Add slight hold if next is not immediate
        new_captions.append({
            "id": f"cap_{idx:03d}",
            "start": start_t,
            "end": end_t,
            "text": ch_text,
            "word_timings": [
                {
                    "text": w["text"],
                    "start": round(w["start"] - start_t, 3),
                    "end": round(w["end"] - start_t, 3)
                } for w in ch
            ]
        })
        
    for idx, c in enumerate(new_captions):
        # extend end slightly to avoid flickering between adjacent cards
        if idx + 1 < len(new_captions):
            next_start = new_captions[idx+1]["start"]
            c["end"] = min(round(c["end"] + 0.15, 3), next_start)
        else:
            c["end"] = round(c["end"] + 0.3, 3)
            
    return new_captions

if __name__ == "__main__":
    caps = get_words_and_rechunk()
    print(f"\nGenerated {len(caps)} re-chunked captions (all 2-3 words):")
    for i, c in enumerate(caps):
        w_cnt = len(c['text'].split())
        print(f"[{i:02d}] {c['start']:05.2f}s - {c['end']:05.2f}s ({w_cnt}w): \"{c['text']}\"")
