from __future__ import annotations

import hashlib
import json
from .process import run as run_process
from pathlib import Path

from PIL import Image

from .config import CACHE_DIR
from .model import MediaItem, uid

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".ts"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def media_kind(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "unknown"


def _rate(value: str) -> float:
    try:
        left, right = value.split("/")
        return float(left) / float(right) if float(right) else 0.0
    except (ValueError, AttributeError, ZeroDivisionError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


def probe(path: str | Path, ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg", *, timeout=None) -> MediaItem:
    path = Path(path).resolve()
    kind = media_kind(path)
    if kind == "unknown":
        raise ValueError(f"Unsupported media type: {path.suffix}")
    if kind == "image":
        with Image.open(path) as image:
            width, height = image.size
        thumb = make_thumbnail(path, kind, ffmpeg, timeout=timeout)
        return MediaItem(uid(), str(path), kind, path.name, 5.0, width, height, 0, False, thumb)
    command = [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    result = run_process(command, capture_output=True, text=True, check=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    payload = json.loads(result.stdout)
    video = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = any(s.get("codec_type") == "audio" for s in payload.get("streams", []))
    duration = float(payload.get("format", {}).get("duration") or video.get("duration") or 0)
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    fps = _rate(video.get("avg_frame_rate", "0/1"))
    thumb = make_thumbnail(path, kind, ffmpeg, timeout=timeout) if kind == "video" else ""
    media=MediaItem(uid(), str(path), kind, path.name, duration, width, height, fps, audio, thumb)
    media.video_codec = str(video.get("codec_name") or "").lower()
    for stream in payload.get('streams',[]):
        stream_kind=stream.get('codec_type')
        if stream_kind not in {'video','audio'} or stream_kind in media.stream_durations:continue
        try:
            value=float(stream.get('duration') or duration)
            if value>0:media.stream_durations[stream_kind]=value
        except (TypeError,ValueError):pass
    return media


def video_codec(path: str | Path, ffprobe: str = "ffprobe") -> str:
    """Inspect old project media without generating thumbnails or touching sources."""
    result = run_process([ffprobe, "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
                          str(path)], capture_output=True, text=True, check=True,
                         encoding="utf-8", errors="replace", timeout=15)
    return result.stdout.strip().splitlines()[0].lower() if result.stdout.strip() else ""


def make_thumbnail(path: str | Path, kind: str, ffmpeg: str = "ffmpeg", *, timeout=None) -> str:
    source=Path(path).resolve()
    stat=source.stat()
    signature=str(source)+f':{stat.st_size}:{stat.st_mtime_ns}:rgba-v3'
    digest = hashlib.sha1(signature.encode()).hexdigest()[:16]
    target = CACHE_DIR / "thumbs" / (digest+(".png" if kind=="image" else ".jpg"))
    if target.exists():
        return str(target)
    if kind == "image":
        with Image.open(path) as image:
            from PIL import ImageOps
            converted = ImageOps.exif_transpose(image).convert("RGBA")
            converted.thumbnail((320, 180))
            converted.save(target)
    else:
        run_process([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.5",
                        "-i", str(path), "-frames:v", "1", "-vf",
                        "scale=320:180:force_original_aspect_ratio=decrease", str(target)],
                       check=False, capture_output=True, timeout=timeout)
    return str(target) if target.exists() else ""


def generate_proxy(media: MediaItem, ffmpeg: str = "ffmpeg", cancel=None,
                   compatibility: bool = False, progress=None) -> str:
    profile = 'compat-h264-full-v1' if compatibility else 'seek-proxy-v3'
    digest = hashlib.sha1((media.path + str(Path(media.path).stat().st_mtime_ns)+profile).encode()).hexdigest()[:16]
    target = CACHE_DIR / "proxies" / f"{digest}.mp4"
    if target.exists():
        return str(target)
    from .exporter import automatic_encoder
    codec=['-c:v','h264_nvenc','-preset','p2','-cq','18','-b:v','0'] if automatic_encoder(ffmpeg,'h264')=='NVIDIA' else ['-c:v','libx264','-preset','ultrafast','-crf','18']
    pending=target.with_suffix('.pending.mp4')
    # Short GOPs bound random-seek decoding. Compatibility previews preserve
    # the source's dimensions (up to 1920px wide); export and audio stay original.
    from .export_process import render
    args=[ffmpeg,'-hide_banner','-loglevel','error','-y','-threads','0' if compatibility else '2','-i',media.path,
          '-vf',f"scale='min({1920 if compatibility else 960},iw)':-2",'-an']+codec+['-g','15','-bf','0','-pix_fmt','yuv420p','-progress','pipe:1','-nostats',str(pending)]
    code,tail=render(args,media.duration,progress,cancel)
    if code or cancel and cancel.is_set():raise RuntimeError('Preview preparation stopped: '+'\n'.join(tail)[-1500:])
    pending.replace(target)
    return str(target)


from .waveforms import waveform
