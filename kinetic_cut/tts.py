"""Text-to-Speech synthesis with curated viral voices (including ElevenLabs Adam) and batch processing."""
from __future__ import annotations

import asyncio
import hashlib
import concurrent.futures
import json
import os
import re
import shutil
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable
import edge_tts
from .config import CACHE_DIR

VOICES = [
    ("Adam (Viral Shorts Narrator)", "adam-narrator"),
    ("Brian (Deep Storyteller · TikTok/Shorts)", "en-US-BrianNeural"),
    ("Christopher (Viral Shorts · Deep Male)", "en-US-ChristopherNeural"),
    ("Guy (Casual Male · Upbeat / Gaming)", "en-US-GuyNeural"),
    ("Eric (Clear Male · Documentary / Authority)", "en-US-EricNeural"),
    ("Jenny (Natural Female · TikTok Story)", "en-US-JennyNeural"),
    ("Aria (Expressive Female · Vibrant)", "en-US-AriaNeural"),
    ("Andrew (Warm Male · Professional)", "en-US-AndrewNeural"),
]

DEFAULT_VOICE = "adam-narrator"


def _ensure_windows_asyncio():
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass


def _synthesize_adam(
    text: str,
    rate_percent: int = 0,
    pitch_hz: int = 0,
    target_path: Path | str | None = None,
    ffmpeg_bin: str = "ffmpeg"
) -> str:
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_raw = target.with_suffix(".raw.mp3")
    temp_mastered = target.with_suffix(".tmp.mp3")

    base_voice = "en-US-AndrewNeural"
    total_pitch = pitch_hz - 2
    rate_str = f"{rate_percent:+d}%"
    pitch_str = f"{total_pitch:+d}Hz"

    _ensure_windows_asyncio()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(lambda: asyncio.run(_synthesize_async(text, base_voice, rate_str, pitch_str, temp_raw))).result()
    else:
        asyncio.run(_synthesize_async(text, base_voice, rate_str, pitch_str, temp_raw))

    # Broadcast studio mastering: low-end proximity boost, clear presence EQ, and radio compression
    af = (
        "bass=g=4.2:f=125:w=0.6,"
        "equalizer=f=3300:t=q:w=1.1:g=2.4,"
        "acompressor=threshold=-17dB:ratio=3.2:attack=12:release=140:makeup=2.2dB"
    )
    from .process import run as run_process
    cmd = [ffmpeg_bin, "-y", "-i", str(temp_raw), "-af", af, "-c:a", "libmp3lame", "-q:a", "2", str(temp_mastered)]
    try:
        run_process(cmd, check=True, capture_output=True)
        if temp_mastered.exists():
            temp_mastered.replace(target)
        elif temp_raw.exists():
            temp_raw.replace(target)
    except Exception:
        if temp_raw.exists():
            temp_raw.replace(target)
    finally:
        if temp_raw.exists():
            temp_raw.unlink(missing_ok=True)
        if temp_mastered.exists():
            temp_mastered.unlink(missing_ok=True)

    return str(target)


def synthesize_elevenlabs(
    text: str,
    api_key: str,
    voice_id: str = "pNInz6obpgDQGcFmaJgB",
    rate_percent: int = 0,
    target_path: Path | str | None = None
) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Script text cannot be empty.")
    key = api_key.strip() if api_key else os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise ValueError("ElevenLabs API Key required. Enter your key or select a free voice like Adam or Christopher.")

    speed_factor = max(0.7, min(1.2, 1.0 + (rate_percent / 100.0)))
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg"
    }
    body = {
        "text": cleaned,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "speed": round(speed_factor, 2)
        }
    }
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio_bytes = resp.read()
    except urllib.error.HTTPError as err:
        try:
            err_json = json.loads(err.read().decode("utf-8", errors="replace"))
            detail = err_json.get("detail", {})
            msg = detail.get("message") if isinstance(detail, dict) else str(detail)
            msg = msg or str(err)
        except Exception:
            msg = str(err)
        raise RuntimeError(f"ElevenLabs error ({err.code}): {msg}")
    except Exception as err:
        raise RuntimeError(f"ElevenLabs connection failed: {err}")

    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".tmp.mp3")
    temp_target.write_bytes(audio_bytes)
    if temp_target.exists():
        temp_target.replace(target)
    return str(target)


async def _synthesize_async(text: str, voice: str, rate: str, pitch: str, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".tmp.mp3")
    com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await com.save(str(temp_target))
    if temp_target.exists():
        temp_target.replace(target)


def synthesize_speech(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate_percent: int = 0,
    pitch_hz: int = 0,
    output_path: str | Path | None = None,
    api_key: str = "",
    ffmpeg_bin: str = "ffmpeg"
) -> str:
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("Text cannot be empty.")
    rate_str = f"{rate_percent:+d}%"
    pitch_str = f"{pitch_hz:+d}Hz"
    if output_path:
        target = Path(output_path)
    else:
        sig = f"{cleaned_text}:{voice}:{rate_str}:{pitch_str}"
        digest = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:24]
        target = CACHE_DIR / "tts" / f"tts_{digest}.mp3"

    if not target.exists() or target.stat().st_size == 0:
        if voice in ("adam-narrator", "adam-shorts") or voice.startswith("adam"):
            _synthesize_adam(cleaned_text, rate_percent=rate_percent, pitch_hz=pitch_hz, target_path=target, ffmpeg_bin=ffmpeg_bin)
        elif voice.startswith("elevenlabs:"):
            if api_key.strip():
                voice_id = voice.split(":", 1)[1]
                synthesize_elevenlabs(cleaned_text, api_key=api_key, voice_id=voice_id, rate_percent=rate_percent, target_path=target)
            else:
                _synthesize_adam(cleaned_text, rate_percent=rate_percent, pitch_hz=pitch_hz, target_path=target, ffmpeg_bin=ffmpeg_bin)
        else:
            _ensure_windows_asyncio()
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(lambda: asyncio.run(_synthesize_async(cleaned_text, voice, rate_str, pitch_str, target))).result()
            else:
                asyncio.run(_synthesize_async(cleaned_text, voice, rate_str, pitch_str, target))

    return str(target)


def extract_preview_sentence(text: str) -> str:
    """Extract first sentence or first few words for snappy voice preview."""
    cleaned = text.strip()
    if not cleaned:
        return "Welcome back to today's video."
    match = re.search(r"^.*?[.!?](\s|$)", cleaned)
    if match:
        sentence = match.group(0).strip()
        return sentence[:120]
    words = cleaned.split()
    return " ".join(words[:15])[:120]


def split_script_into_batches(text: str, max_chars: int = 350) -> list[str]:
    """Split script into natural sentence/paragraph batches for reliable generation of any script length."""
    cleaned = text.strip()
    if not cleaned:
        return []
    paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
    batches = []
    current_batch: list[str] = []
    current_len = 0

    for p in paragraphs:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', p) if s.strip()]
        if not sentences:
            sentences = [p]
        for s in sentences:
            if len(s) > max_chars:
                sub_parts = [sub.strip() for sub in re.split(r'(?<=[,;:])\s+', s) if sub.strip()]
                if not sub_parts:
                    sub_parts = [s]
            else:
                sub_parts = [s]

            for part in sub_parts:
                if current_len + len(part) + 1 <= max_chars:
                    current_batch.append(part)
                    current_len += len(part) + 1
                else:
                    if current_batch:
                        batches.append(" ".join(current_batch))
                    current_batch = [part]
                    current_len = len(part)

        if current_batch:
            batches.append(" ".join(current_batch))
            current_batch = []
            current_len = 0

    if current_batch:
        batches.append(" ".join(current_batch))

    return batches or [cleaned]


def synthesize_dialogue_batches(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate_percent: int = 0,
    pitch_hz: int = 0,
    output_path: str | Path | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
    ffmpeg_bin: str = "ffmpeg",
    cancel_check: Callable[[], bool] | None = None,
    api_key: str = "",
) -> str:
    """Synthesize dialogue of any length via batching with progress updates and ffmpeg concatenation."""
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("Script text cannot be empty.")

    rate_str = f"{rate_percent:+d}%"
    pitch_str = f"{pitch_hz:+d}Hz"

    sig = f"{cleaned_text}:{voice}:{rate_str}:{pitch_str}"
    digest = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:24]
    if output_path:
        target = Path(output_path)
    else:
        target = CACHE_DIR / "tts" / f"dialogue_{digest}.mp3"

    # Fast path if already cached and valid
    if target.exists() and target.stat().st_size > 0:
        if progress_callback:
            progress_callback(100, "Dialogue ready")
        return str(target)

    batches = split_script_into_batches(cleaned_text, max_chars=350)
    total_batches = len(batches)

    _ensure_windows_asyncio()

    # Single-batch fast path
    if total_batches <= 1:
        if progress_callback:
            progress_callback(10, "Generating dialogue...")
        synthesize_speech(cleaned_text, voice, rate_percent, pitch_hz, output_path=target, api_key=api_key, ffmpeg_bin=ffmpeg_bin)
        if progress_callback:
            progress_callback(100, "Dialogue ready")
        return str(target)

    # Multi-batch execution
    batch_dir = CACHE_DIR / "tts" / f"batch_{digest}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    chunk_files: list[Path] = []

    try:
        for i, batch_text in enumerate(batches):
            if cancel_check and cancel_check():
                raise InterruptedError("Dialogue generation cancelled.")

            chunk_path = batch_dir / f"part_{i:04d}.mp3"
            synthesize_speech(batch_text, voice, rate_percent, pitch_hz, output_path=chunk_path, api_key=api_key, ffmpeg_bin=ffmpeg_bin)
            chunk_files.append(chunk_path)

            pct = int(((i + 1) / total_batches) * 90)
            if progress_callback:
                progress_callback(pct, f"Generating dialogue: {pct}% ({i+1}/{total_batches})...")

        if cancel_check and cancel_check():
            raise InterruptedError("Dialogue generation cancelled.")

        if progress_callback:
            progress_callback(95, "Assembling dialogue audio...")

        list_file = batch_dir / "concat_list.txt"
        lines = [f"file '{cf.resolve().as_posix()}'\n" for cf in chunk_files]
        list_file.write_text("".join(lines), encoding="utf-8")

        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_suffix(".tmp.mp3")

        from .process import run as run_process
        cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(temp_target)]
        try:
            run_process(cmd, check=True, capture_output=True)
        except Exception:
            filter_inputs = []
            for cf in chunk_files:
                filter_inputs.extend(["-i", str(cf)])
            concat_str = "".join(f"[{k}:a]" for k in range(len(chunk_files))) + f"concat=n={len(chunk_files)}:v=0:a=1[out]"
            reencode_cmd = [ffmpeg_bin, "-y"] + filter_inputs + ["-filter_complex", concat_str, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", str(temp_target)]
            run_process(reencode_cmd, check=True, capture_output=True)

        if temp_target.exists():
            temp_target.replace(target)

    finally:
        shutil.rmtree(batch_dir, ignore_errors=True)

    if progress_callback:
        progress_callback(100, "Dialogue ready")

    return str(target)
