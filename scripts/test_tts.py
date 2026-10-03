import asyncio
import edge_tts
from pathlib import Path

async def main():
    voices = await edge_tts.list_voices()
    en_us = [v for v in voices if v['Locale'].startswith('en-US')]
    print(f"Total en-US voices: {len(en_us)}")
    for v in en_us:
        print(f"  {v['ShortName']}: {v['Gender']}")
    
    # Test generating with Christopher (the famous deep narrator male voice used in Shorts/TikTok)
    text = "In 2026, scientists discovered something terrifying at the bottom of the ocean."
    output_mp3 = Path("build/test_tts_christopher.mp3")
    output_mp3.parent.mkdir(parents=True, exist_ok=True)
    
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(str(output_mp3))
    print(f"Generated TTS file: {output_mp3}, exists: {output_mp3.exists()}, size: {output_mp3.stat().st_size} bytes")

if __name__ == "__main__":
    asyncio.run(main())
