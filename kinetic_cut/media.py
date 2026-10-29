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


def _thumbnail_target(path,kind):
    source=Path(path).resolve()
    stat=source.stat()
    signature=str(source)+f':{stat.st_size}:{stat.st_mtime_ns}:rgba-v3'
    digest = hashlib.sha1(signature.encode()).hexdigest()[:16]
    return CACHE_DIR / "thumbs" / (digest+(".png" if kind=="image" else ".jpg"))


def cached_thumbnail(path,kind):
    """Find existing small artwork without decoding the original image/video."""
    try:
        target=_thumbnail_target(path,kind)
        return str(target) if target.is_file() and target.stat().st_size else ''
    except OSError:return ''


def planned_thumbnail(path,kind):
    """Stable derived path, assigned before asynchronous work/snapshots start."""
    try:return str(_thumbnail_target(path,kind))
    except OSError:return ''


def make_thumbnail(path: str | Path, kind: str, ffmpeg: str = "ffmpeg", *, timeout=None, cancel_check=None) -> str:
    target=_thumbnail_target(path,kind)
    if target.exists():
        return str(target)
    import tempfile
    # A cancelled/failed writer must never leave a partial image that the next
    # project load mistakes for a completed thumbnail.
    with tempfile.NamedTemporaryFile(dir=target.parent,suffix=target.suffix,delete=False) as pending:
        temporary=Path(pending.name)
    try:
        if cancel_check and cancel_check():raise InterruptedError('Thumbnail generation cancelled')
        if kind == "image":
            with Image.open(path) as image:
                from PIL import ImageOps
                converted = ImageOps.exif_transpose(image).convert("RGBA")
                converted.thumbnail((320, 180))
                converted.save(temporary)
        else:
            from .process import run_cancellable
            runner=run_cancellable if cancel_check is not None else run_process
            options=dict(cancel_check=cancel_check) if cancel_check is not None else {}
            result=runner([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.5",
                            "-i", str(path), "-frames:v", "1", "-vf",
                            "scale=320:180:force_original_aspect_ratio=decrease", str(temporary)],
                           check=False, capture_output=True, timeout=timeout,**options)
            if result.returncode:return ""
        if cancel_check and cancel_check():raise InterruptedError('Thumbnail generation cancelled')
        if temporary.stat().st_size:
            temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return str(target) if target.exists() else ""


def proxy_path(media: MediaItem, *, compatibility=False, seek_cache=False):
    profile = 'seek-full-v2' if seek_cache else 'compat-h264-full-v1' if compatibility else 'seek-proxy-v3'
    stat=Path(media.path).stat()
    digest = hashlib.sha1((media.path + str(stat.st_mtime_ns)+(str(stat.st_size) if seek_cache else '')+profile).encode()).hexdigest()[:16]
    return CACHE_DIR / "proxies" / f"{'full-seek-' if seek_cache else ''}{digest}.mp4"


def generate_proxy(media: MediaItem, ffmpeg: str = "ffmpeg", cancel=None,
                   compatibility: bool = False, progress=None, seek_cache: bool = False, protected=()) -> str:
    target=proxy_path(media,compatibility=compatibility,seek_cache=seek_cache)
    if target.exists():
        return str(target)
    if seek_cache:
        import av,shutil,os
        if target.parent.is_symlink() or not target.parent.resolve().is_relative_to(CACHE_DIR.resolve()):
            raise ValueError('Keeping original preview for linked cache directory')
        protected={os.path.normcase(str(Path(path).resolve())) for path in protected}
        with av.open(media.path) as source:
            first=next(source.decode(video=0))
            if first.format.name not in ('yuv420p','yuvj420p','nv12') or getattr(first,'rotation',0) or first.interlaced_frame:
                raise ValueError('Keeping original preview for this source colour/field/orientation format')
        # Seek copies are regenerable, with a bounded footprint. Never evict a
        # path currently used by a player or an open project cache map.
        entries=[]
        for path in target.parent.glob('full-seek-*.mp4'):
            import re
            if path.is_symlink() or not re.fullmatch(r'full-seek-[0-9a-f]{16}\.mp4',path.name):continue
            info=path.stat(); entries.append((info.st_mtime,info.st_size,path))
        total=sum(size for _,size,_ in entries)
        for _,size,path in sorted(entries):
            if total<=1536*1024**2:break
            if os.path.normcase(str(path.resolve())) not in protected:
                path.unlink(); total-=size
        if total>1536*1024**2 or shutil.disk_usage(target.parent).free<768*1024**2:
            raise ValueError('Keeping original preview: seek-cache storage budget reached')
    if seek_cache:
        codec=['-c:v','libx264','-preset','veryfast','-crf','14','-threads','2']
    else:
        from .exporter import automatic_encoder
        codec=['-c:v','h264_nvenc','-preset','p2','-cq','18','-b:v','0'] if automatic_encoder(ffmpeg,'h264')=='NVIDIA' else ['-c:v','libx264','-preset','ultrafast','-crf','18']
    pending=target.with_suffix('.pending.mp4')
    # Short GOPs bound random-seek decoding. Compatibility previews preserve
    # the source's dimensions (up to 1920px wide); export and audio stay original.
    from .export_process import render
    args=[ffmpeg,'-hide_banner','-loglevel','error','-y','-threads','0' if compatibility and not seek_cache else '2','-i',media.path]
    if not seek_cache:args += ['-vf',f"scale='min({1920 if compatibility else 960},iw)':-2"]
    else:args += ['-fps_mode','passthrough']
    args += ['-an']+codec+['-g','15','-bf','0','-pix_fmt','yuv420p','-progress','pipe:1','-nostats',str(pending)]
    def report(fraction,message):
        if seek_cache and pending.exists() and pending.stat().st_size>512*1024**2:
            raise RuntimeError('Keeping original preview: per-source seek-cache budget reached')
        if progress:progress(fraction,message)
    try:code,tail=render(args,media.duration,report if seek_cache else progress,cancel)
    except BaseException:
        if seek_cache:pending.unlink(missing_ok=True)
        raise
    if code or cancel and cancel.is_set():
        if seek_cache:pending.unlink(missing_ok=True)
        raise RuntimeError('Preview preparation stopped: '+'\n'.join(tail)[-1500:])
    pending.replace(target)
    return str(target)


from .waveforms import waveform
