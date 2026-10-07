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
import subprocess
import tempfile
import threading
import weakref
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


def _check_cancel(cancel_check):
    if cancel_check and cancel_check():
        raise InterruptedError("Speech generation cancelled.")


async def _await_cancellable(awaitable, cancel_check):
    """Interrupt a pending network operation, including a silent/blocked service."""
    task = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            _check_cancel(cancel_check)
            await asyncio.wait({task}, timeout=0.05)
        _check_cancel(cancel_check)
        return await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def _run_audio_process(cmd, cancel_check):
    """Drain output to bounded disk handles and reap the actual owned encoder."""
    from .process import run_cancellable
    _check_cancel(cancel_check)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            run_cancellable(cmd, stdout=stdout, stderr=stderr, check=True, cancel_check=cancel_check)
        except subprocess.CalledProcessError as err:
            stderr.seek(max(0, stderr.tell() - 8192))
            err.stderr = stderr.read()
            raise


_publication_guard = threading.Lock()
_publication_locks = weakref.WeakValueDictionary()


def _publish_audio(source, target, cancel_check):
    # Concurrent MoveFileEx replacements on Windows can conflict even though
    # each request owns its temporary file. Serialize just publication, keeping
    # network/encoding concurrent and retaining no permanent per-file locks.
    key = os.path.normcase(str(target.resolve()))
    with _publication_guard:
        lock = _publication_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _publication_locks[key] = lock
    with lock:
        _check_cancel(cancel_check)
        source.replace(target)


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
    ffmpeg_bin: str = "ffmpeg",
    cancel_check: Callable[[], bool] | None = None,
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
            pool.submit(lambda: asyncio.run(_synthesize_async(text, base_voice, rate_str, pitch_str, temp_raw, cancel_check))).result()
    else:
        asyncio.run(_synthesize_async(text, base_voice, rate_str, pitch_str, temp_raw, cancel_check))

    # Broadcast studio mastering: low-end proximity boost, clear presence EQ, and radio compression
    af = (
        "bass=g=4.2:f=125:w=0.6,"
        "equalizer=f=3300:t=q:w=1.1:g=2.4,"
        "acompressor=threshold=-17dB:ratio=3.2:attack=12:release=140:makeup=2.2dB"
    )
    cmd = [ffmpeg_bin, "-y", "-i", str(temp_raw), "-af", af, "-c:a", "libmp3lame", "-q:a", "2", str(temp_mastered)]
    try:
        _run_audio_process(cmd, cancel_check)
        if temp_mastered.exists():
            temp_mastered.replace(target)
        elif temp_raw.exists():
            temp_raw.replace(target)
    except InterruptedError:
        raise
    except (OSError, subprocess.CalledProcessError):
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
    target_path: Path | str | None = None,
    cancel_check: Callable[[], bool] | None = None,
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
    async def request_audio():
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(url, json=body, headers=headers) as resp:
                if resp.status >= 400:
                    error = await resp.json(content_type=None)
                    detail = error.get("detail", {})
                    message = detail.get("message") if isinstance(detail, dict) else str(detail)
                    raise RuntimeError(f"ElevenLabs error ({resp.status}): {message or resp.reason}")
                return await resp.read()
    try:
        audio_bytes = asyncio.run(_await_cancellable(request_audio(), cancel_check))
    except InterruptedError:
        raise
    except Exception as err:
        raise RuntimeError(f"ElevenLabs connection failed: {err}")

    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".tmp.mp3")
    temp_target.write_bytes(audio_bytes)
    if temp_target.exists():
        temp_target.replace(target)
    return str(target)


async def _synthesize_async(text: str, voice: str, rate: str, pitch: str, target: Path, cancel_check=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_suffix(".tmp.mp3")
    com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await _await_cancellable(com.save(str(temp_target)), cancel_check)
    _check_cancel(cancel_check)
    if temp_target.exists():
        temp_target.replace(target)


def synthesize_speech(
    text: str,
    voice: str = DEFAULT_VOICE,
    rate_percent: int = 0,
    pitch_hz: int = 0,
    output_path: str | Path | None = None,
    api_key: str = "",
    ffmpeg_bin: str = "ffmpeg",
    cancel_check: Callable[[], bool] | None = None,
) -> str:
    cleaned_text = text.strip()
    _check_cancel(cancel_check)
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
        target.parent.mkdir(parents=True, exist_ok=True)
        # Every request owns its temporary paths. Simultaneous previews of the
        # same text cannot overwrite/delete each other's partial audio.
        with tempfile.TemporaryDirectory(prefix=".tts-", dir=target.parent) as work_dir:
            work_target = Path(work_dir) / "speech.mp3"
            _synthesize_to_target(cleaned_text, voice, rate_percent, pitch_hz,
                                  work_target, api_key, ffmpeg_bin, cancel_check)
            _check_cancel(cancel_check)
            _publish_audio(work_target, target, cancel_check)

    _check_cancel(cancel_check)
    return str(target)


def _synthesize_to_target(cleaned_text, voice, rate_percent, pitch_hz, target,
                          api_key, ffmpeg_bin, cancel_check):
        rate_str = f"{rate_percent:+d}%"
        pitch_str = f"{pitch_hz:+d}Hz"
        if voice in ("adam-narrator", "adam-shorts") or voice.startswith("adam"):
            _synthesize_adam(cleaned_text, rate_percent=rate_percent, pitch_hz=pitch_hz, target_path=target, ffmpeg_bin=ffmpeg_bin, cancel_check=cancel_check)
        elif voice.startswith("elevenlabs:"):
            if api_key.strip():
                voice_id = voice.split(":", 1)[1]
                synthesize_elevenlabs(cleaned_text, api_key=api_key, voice_id=voice_id, rate_percent=rate_percent, target_path=target, cancel_check=cancel_check)
            else:
                _synthesize_adam(cleaned_text, rate_percent=rate_percent, pitch_hz=pitch_hz, target_path=target, ffmpeg_bin=ffmpeg_bin, cancel_check=cancel_check)
        else:
            _ensure_windows_asyncio()
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(lambda: asyncio.run(_synthesize_async(cleaned_text, voice, rate_str, pitch_str, target, cancel_check))).result()
            else:
                asyncio.run(_synthesize_async(cleaned_text, voice, rate_str, pitch_str, target, cancel_check))


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
    _check_cancel(cancel_check)
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
        synthesize_speech(cleaned_text, voice, rate_percent, pitch_hz, output_path=target, api_key=api_key, ffmpeg_bin=ffmpeg_bin, cancel_check=cancel_check)
        _check_cancel(cancel_check)
        if progress_callback:
            progress_callback(100, "Dialogue ready")
        return str(target)

    # Multi-batch execution
    target.parent.mkdir(parents=True, exist_ok=True)
    batch_dir = Path(tempfile.mkdtemp(prefix=".tts-batch-", dir=target.parent))
    chunk_files: list[Path] = []

    try:
        for i, batch_text in enumerate(batches):
            if cancel_check and cancel_check():
                raise InterruptedError("Dialogue generation cancelled.")

            chunk_path = batch_dir / f"part_{i:04d}.mp3"
            synthesize_speech(batch_text, voice, rate_percent, pitch_hz, output_path=chunk_path, api_key=api_key, ffmpeg_bin=ffmpeg_bin, cancel_check=cancel_check)
            _check_cancel(cancel_check)
            chunk_files.append(chunk_path)

            pct = int(((i + 1) / total_batches) * 90)
            if progress_callback:
                progress_callback(pct, f"Generating dialogue: {pct}% ({i+1}/{total_batches})...")

        if cancel_check and cancel_check():
            raise InterruptedError("Dialogue generation cancelled.")

        if progress_callback:
            progress_callback(95, "Assembling dialogue audio...")

        list_file = batch_dir / "concat_list.txt"
        paths = [cf.resolve().as_posix().replace("'", "'\\''") for cf in chunk_files]
        lines = [f"file '{path}'\n" for path in paths]
        list_file.write_text("".join(lines), encoding="utf-8")

        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = batch_dir / "assembled.mp3"

        cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(temp_target)]
        try:
            _run_audio_process(cmd, cancel_check)
        except subprocess.CalledProcessError:
            filter_inputs = []
            for cf in chunk_files:
                filter_inputs.extend(["-i", str(cf)])
            concat_str = "".join(f"[{k}:a]" for k in range(len(chunk_files))) + f"concat=n={len(chunk_files)}:v=0:a=1[out]"
            reencode_cmd = [ffmpeg_bin, "-y"] + filter_inputs + ["-filter_complex", concat_str, "-map", "[out]", "-c:a", "libmp3lame", "-q:a", "2", str(temp_target)]
            _run_audio_process(reencode_cmd, cancel_check)

        _check_cancel(cancel_check)
        if temp_target.exists():
            _publish_audio(temp_target, target, cancel_check)

    finally:
        shutil.rmtree(batch_dir, ignore_errors=True)

    if progress_callback:
        progress_callback(100, "Dialogue ready")

    return str(target)
