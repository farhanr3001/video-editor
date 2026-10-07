from __future__ import annotations

import json
import copy
import shutil
import tempfile
from pathlib import Path

from .model import Caption, CaptionStyle, uid
from .process import run as run_process


class CaptionBackendError(RuntimeError):
    pass


class CaptionCancelled(InterruptedError):
    """Cancellation is terminal; it must never trigger another speech engine."""


def _check_cancel(cancel_check):
    if cancel_check and cancel_check():raise CaptionCancelled('Caption generation cancelled')


def run_caption_process(command, cancel_check=None, **kwargs):
    """Cooperative subprocess cancellation without blocking on silent tools."""
    if cancel_check is None:return run_process(command,**kwargs)
    from .process import run_cancellable
    _check_cancel(cancel_check)
    try:
        return run_cancellable(command,cancel_check=cancel_check,**kwargs)
    except InterruptedError as error:raise CaptionCancelled('Caption generation cancelled') from error


def _from_segments(segments: list[dict], offset: float = 0.0,
                   style: CaptionStyle | None = None, words_per_caption: int = 5,
                   hold_seconds: float = .5) -> list[Caption]:
    style = style or CaptionStyle()
    captions = []
    words_per_caption=max(1,int(words_per_caption))
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start, end = float(segment.get("start", 0)), float(segment.get("end", 0))
        timed=segment.get("words") or []
        if timed:
            words=[{"text":str(word.get("text",word.get("word",""))).strip(),"start":float(word.get("start",start)),"end":float(word.get("end",end))} for word in timed]
            words=[word for word in words if word["text"]]
        else:
            raw=text.split(); span=max(.01,end-start)
            words=[{"text":word,"start":start+span*n/max(1,len(raw)),"end":start+span*(n+1)/max(1,len(raw))} for n,word in enumerate(raw)]
        chunks=[]; chunk=[]
        for word in words:
            if chunk and (len(chunk)>=words_per_caption or word["start"]-chunk[-1]["end"]>.65):chunks.append(chunk); chunk=[]
            chunk.append(word)
        if chunk:chunks.append(chunk)
        for chunk in chunks:
            if not chunk:continue
            captions.append(Caption(uid(),offset+chunk[0]["start"],offset+chunk[-1]["end"],
                                    " ".join(word["text"] for word in chunk),CaptionStyle(**style.__dict__)))
            if timed:captions[-1].word_timings=[dict(text=word['text'],start=word['start']-chunk[0]['start'],end=word['end']-chunk[0]['start']) for word in chunk]
    captions.sort(key=lambda caption:(caption.start,caption.end))
    for index,caption in enumerate(captions):
        next_start=captions[index+1].start if index+1<len(captions) else None
        desired=caption.end+max(0.,hold_seconds)
        caption.end=desired if next_start is None else min(desired,next_start)
    return captions


def transcribe(path: str, settings: dict, offset: float = 0.0,
               progress=None, words_per_caption: int = 5,
               hold_seconds: float = .5, require_word_timestamps: bool = False,
               cancel_check=None) -> tuple[list[Caption], str]:
    """Transcribe locally, preferring faster-whisper, then whisper.cpp, then Windows Speech."""
    faster_error = ""
    _check_cancel(cancel_check)
    try:
        from faster_whisper import WhisperModel  # type: ignore
        if progress:
            progress("Loading local Whisper model…")
        _check_cancel(cancel_check)
        from .caption_runtime import model_arguments
        model_name, model_options = model_arguments(settings.get("whisper_model", "small.en"))
        model = WhisperModel(model_name, device="cpu", compute_type="int8", **model_options)
        _check_cancel(cancel_check)
        # Never concatenate distant speech islands. Restoring timestamps after
        # VAD concatenation can attach the first word after a pause to the
        # previous island (e.g. "feels" arriving four seconds too early).
        from faster_whisper.audio import decode_audio
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        audio=decode_audio(path, sampling_rate=16000)
        _check_cancel(cancel_check)
        regions=get_speech_timestamps(audio,VadOptions(min_silence_duration_ms=700,speech_pad_ms=200))
        _check_cancel(cancel_check)
        data=[]
        for region in regions:
            _check_cancel(cancel_check)
            origin=region["start"]/16000
            segments,_=model.transcribe(audio[region["start"]:region["end"]],
                language=settings.get("caption_language","en"),vad_filter=False,
                word_timestamps=True,condition_on_previous_text=False)
            for segment in segments:
                _check_cancel(cancel_check)
                if progress:progress((45+round(45*min(1,(origin+segment.end)/max(.01,len(audio)/16000))),f"Transcribing… {origin+segment.end:.1f}s / {len(audio)/16000:.1f}s"))
                _check_cancel(cancel_check)
                words=[word for word in (getattr(segment,"words",None) or []) if str(getattr(word,"word","")).strip() and word.end>word.start]
                if not words and require_word_timestamps:
                    raise CaptionBackendError("The recognizer returned no word-level timestamps; audio was not changed.")
                data.append({"start":origin+segment.start,"end":origin+segment.end,"text":segment.text,
                    "words":[{"start":origin+word.start,"end":origin+word.end,"text":word.word} for word in words]})
        _check_cancel(cancel_check)
        return _from_segments(data,offset,words_per_caption=words_per_caption,hold_seconds=hold_seconds), "faster-whisper"
    except CaptionCancelled:raise
    except Exception as error:
        # A model may not be downloaded yet or a machine may lack a compatible
        # runtime. Continue to configured whisper.cpp / Windows Speech fallbacks.
        faster_error = str(error)

    _check_cancel(cancel_check)
    if require_word_timestamps:
        raise CaptionBackendError("Cut curse words requires the local faster-whisper engine and its speech model for word-level timestamps. Configure/download the caption engine first; audio was not changed. " + faster_error)

    cli = settings.get("whisper_cli") or shutil.which("whisper-cli")
    model_path = settings.get("whisper_model_path", "")
    if cli and model_path and Path(model_path).exists():
        if progress:
            progress("Transcribing with whisper.cpp…")
        with tempfile.TemporaryDirectory(prefix="kinetic-caption-") as directory:
            output = str(Path(directory) / "captions")
            command = [cli, "-m", model_path, "-f", path, "-oj", "-of", output,
                       "-l", settings.get("caption_language", "en")]
            result = run_caption_process(command,cancel_check,capture_output=True,text=True)
            if result.returncode:
                raise CaptionBackendError(result.stderr[-1000:])
            payload = json.loads(Path(output + ".json").read_text(encoding="utf-8"))
            _check_cancel(cancel_check)
            segments = []
            for item in payload.get("transcription", []):
                timestamps = item.get("timestamps", {})
                segments.append({"start": timestamps.get("from", 0) / 1000,
                                 "end": timestamps.get("to", 0) / 1000,
                                 "text": item.get("text", "")})
            return _from_segments(segments,offset,words_per_caption=words_per_caption,hold_seconds=hold_seconds), "whisper.cpp"

    if __import__("sys").platform == "win32":
        try:
            return _windows_speech(path,settings.get("ffmpeg","ffmpeg"),offset,words_per_caption,hold_seconds,cancel_check), "Windows Speech"
        except CaptionBackendError as error:
            detail = f" Local Whisper: {faster_error}" if faster_error else ""
            raise CaptionBackendError(str(error) + detail) from error
    raise CaptionBackendError(
        "No local speech engine was found. Install faster-whisper or configure whisper-cli in Settings.")


def _windows_speech(path: str, ffmpeg: str, offset: float, words_per_caption: int = 5,
                    hold_seconds: float = .5, cancel_check=None) -> list[Caption]:
    with tempfile.TemporaryDirectory(prefix="kinetic-speech-") as directory:
        wav = str(Path(directory) / "speech.wav")
        run_caption_process([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
                        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav], cancel_check,check=True)
        script = r'''
param([string]$InputWav)
Add-Type -AssemblyName System.Speech
$recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$recognizer.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$recognizer.SetInputToWaveFile($InputWav)
$items = @()
while ($true) {
  $r = $recognizer.Recognize()
  if ($null -eq $r) { break }
  $items += [pscustomobject]@{start=$r.Audio.AudioPosition.TotalSeconds; end=($r.Audio.AudioPosition + $r.Audio.Duration).TotalSeconds; text=$r.Text}
}
$recognizer.Dispose()
$items | ConvertTo-Json -Compress
'''
        script_path = Path(directory) / "recognize.ps1"
        script_path.write_text(script, encoding="utf-8")
        result = run_caption_process(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", str(script_path), wav], cancel_check,capture_output=True,text=True)
        if result.returncode:
            raise CaptionBackendError("Windows Speech Recognition is unavailable: " + result.stderr[-600:])
        try:
            payload = json.loads(result.stdout or "[]")
            if isinstance(payload, dict):
                payload = [payload]
        except json.JSONDecodeError as error:
            raise CaptionBackendError("Windows Speech returned no usable transcript.") from error
        _check_cancel(cancel_check)
        return _from_segments(payload,offset,words_per_caption=words_per_caption,hold_seconds=hold_seconds)


def split_caption(caption: Caption, at: float | None = None) -> tuple[Caption, Caption] | None:
    if caption.end-caption.start<.02:return None
    split_time = at if at and caption.start < at < caption.end else (caption.start + caption.end) / 2
    left = Caption(uid(), caption.start, split_time, caption.text, copy.deepcopy(caption.style), caption.is_hook, caption.customize)
    right = Caption(uid(), split_time, caption.end, caption.text, copy.deepcopy(caption.style), caption.is_hook, caption.customize)
    left.word_timings=copy.deepcopy(caption.word_timings)
    right.word_timings=copy.deepcopy(caption.word_timings)
    from .caption_words import shift_origin
    shift_origin(right,split_time-caption.start)
    left.highlighted_words=list(caption.highlighted_words)
    right.highlighted_words=list(caption.highlighted_words)
    return left, right


def merge_captions(captions: list[Caption]) -> Caption | None:
    if len(captions) < 2:
        return None
    ordered = sorted(captions, key=lambda c: c.start)
    merged=Caption(uid(), ordered[0].start, ordered[-1].end,
                   " ".join(c.text.strip() for c in ordered), copy.deepcopy(ordered[0].style),
                   any(c.is_hook for c in ordered),ordered[0].customize)
    from .caption_words import timings
    offset=0
    for caption in ordered:
        merged.word_timings.extend(dict(text=word,start=start-merged.start,end=end-merged.start) for word,(start,end) in zip(caption.text.split(),timings(caption)))
        merged.highlighted_words.extend(offset+n for n in caption.highlighted_words); offset+=len(caption.text.split())
    return merged
