"""Download popular, universally recognized TikTok / YouTube Shorts soundtracks."""
import os
import subprocess
import sys
from pathlib import Path

PYTHON_BIN = r"C:\Python310\python.exe" if Path(r"C:\Python310\python.exe").exists() else sys.executable
FFMPEG_BIN = "ffmpeg"

SOUNDTRACKS_DIR = Path(r"c:\Users\F\Documents\AI Projects\video-editor\Soundtracks")
SOUNDTRACKS_DIR.mkdir(parents=True, exist_ok=True)

TRACKS = [
    # 1. Viral Comedy & Typical Shorts
    ("Viral_TikTok_Monkeys_Spinning_Monkeys.mp3", "ytsearch1:Kevin MacLeod Monkeys Spinning Monkeys official"),
    ("Viral_TikTok_Sneaky_Snitch.mp3", "ytsearch1:Kevin MacLeod Sneaky Snitch official"),
    ("Viral_TikTok_Fluffing_a_Duck.mp3", "ytsearch1:Kevin MacLeod Fluffing a Duck official"),
    ("Viral_TikTok_Carefree.mp3", "ytsearch1:Kevin MacLeod Carefree official"),
    ("Viral_TikTok_Funny_Song_Elevator.mp3", "ytsearch1:Local Forecast Elevator Kevin MacLeod"),
    ("Viral_TikTok_Scheming_Weasel.mp3", "ytsearch1:Kevin MacLeod Scheming Weasel official"),

    # 2. Viral Aesthetic, Emotional, Deep & Thinking
    ("Viral_TikTok_Paris_Else.mp3", "ytsearch1:Else Paris official audio"),
    ("Viral_TikTok_Memory_Reboot_Synthwave.mp3", "ytsearch1:VOJ Narvent Memory Reboot audio"),
    ("Viral_TikTok_Experience_Ludovico_Einaudi.mp3", "ytsearch1:Ludovico Einaudi Experience official audio"),
    ("Viral_TikTok_Cornfield_Chase_Piano.mp3", "ytsearch1:Cornfield Chase Dorian Marko piano audio"),
    ("Viral_TikTok_Past_Lives_Sapientdream.mp3", "ytsearch1:sapientdream Past Lives official audio"),

    # 3. Viral Phonk, Action & Gym Motivation
    ("Viral_Phonk_Murder_In_My_Mind_Kordhell.mp3", "ytsearch1:Kordhell Murder In My Mind official audio"),
    ("Viral_Phonk_METAMORPHOSIS_Interworld.mp3", "ytsearch1:INTERWORLD METAMORPHOSIS official audio"),
    ("Viral_Phonk_Close_Eyes_DVRST.mp3", "ytsearch1:DVRST Close Eyes official audio"),
    ("Viral_Phonk_GigaChad_Theme.mp3", "ytsearch1:GigaChad Theme Phonk audio SXMPRA"),

    # 4. Viral Vlog, Upbeat & Lifestyle
    ("Viral_Vlog_Better_Days_Lakey_Inspired.mp3", "ytsearch1:LAKEY INSPIRED Better Days official audio"),
    ("Viral_Vlog_Warm_Nights_Lakey_Inspired.mp3", "ytsearch1:LAKEY INSPIRED Warm Nights official audio"),
    ("Viral_Vlog_Not_For_Nothing_Otis_McDonald.mp3", "ytsearch1:Otis McDonald Not For Nothing official audio"),
]

def main():
    print(f"Downloading {len(TRACKS)} popular viral soundtracks into {SOUNDTRACKS_DIR}...")
    success = 0
    for filename, query in TRACKS:
        target = SOUNDTRACKS_DIR / filename
        if target.exists() and target.stat().st_size > 100_000:
            print(f"[SKIP] Already exists: {filename} ({target.stat().st_size} bytes)")
            success += 1
            continue

        temp_base = SOUNDTRACKS_DIR / f"temp_{filename.replace('.mp3', '')}"
        temp_mp3 = SOUNDTRACKS_DIR / f"temp_{filename}"

        cmd = [
            PYTHON_BIN, "-m", "yt_dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            query,
            "-o", f"{temp_base}.%(ext)s"
        ]
        print(f"[DOWNLOADING] {filename} with query: {query}")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if temp_mp3.exists():
            # Normalize with ffmpeg
            norm_cmd = [
                FFMPEG_BIN, "-y", "-i", str(temp_mp3),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-b:a", "192k",
                str(target)
            ]
            res = subprocess.run(norm_cmd, capture_output=True)
            try:
                temp_mp3.unlink()
            except Exception:
                pass
            if target.exists() and target.stat().st_size > 1000:
                print(f"[SUCCESS] Saved {filename} ({target.stat().st_size} bytes)")
                success += 1
            else:
                print(f"[ERROR] Failed normalization for {filename}")
        else:
            print(f"[FAIL] Download failed for {filename}:\n{proc.stderr[:300]}")

    print(f"\nCompleted: {success}/{len(TRACKS)} tracks ready.")

if __name__ == "__main__":
    main()
