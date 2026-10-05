from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from functools import lru_cache

from .model import Caption, Project, TimelineItem
from .process import popen as popen_process


@dataclass(frozen=True)
class ExportPreset:
    name: str
    codec: str
    bitrate_mbps: float
    audio_kbps: int
    description: str


PRESETS = {
    "TikTok · Fast": ExportPreset("TikTok · Fast", "h264", 10.0, 192, "Fast 1080p upload"),
    "YouTube Shorts · Quality": ExportPreset("YouTube Shorts · Quality", "h264", 14.0, 192, "Higher YouTube quality"),
    "Instagram Reels · Compact": ExportPreset("Instagram Reels · Compact", "h264", 8.0, 160, "Smaller Instagram file"),
    "HEVC · Small": ExportPreset("HEVC · Small", "h265", 6.0, 160, "Small file; slower encode"),
}


def estimate(project: Project, preset: ExportPreset, hardware: bool = True) -> tuple[int, float]:
    seconds = project.duration
    size = int(seconds * ((preset.bitrate_mbps * 1_000_000) + preset.audio_kbps * 1000) / 8)
    pixels = project.settings.width * project.settings.height * project.settings.fps * seconds
    speed = 280_000_000 if hardware else 70_000_000
    return size, max(1.0, pixels / speed)


def _escape_ass_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _ass_color(hex_color: str, alpha: str = "00") -> str:
    value = hex_color.lstrip("#").rjust(6, "0")
    return f"&H{alpha}{value[4:6]}{value[2:4]}{value[0:2]}"


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    return f"{centiseconds // 360000}:{(centiseconds // 6000) % 60:02d}:{(centiseconds // 100) % 60:02d}.{centiseconds % 100:02d}"


def _crop_filter(item: TimelineItem) -> str:
    c = item.crop.clamped()
    return f"crop=iw*{c.width:.6f}:ih*{c.height:.6f}:iw*{c.x:.6f}:ih*{c.y:.6f}"


def write_ass(project,path,burn_captions=True):
    from .subtitle_render import write
    write(project,path,burn_captions)


def _encoder(codec: str, hardware: str) -> tuple[list[str], str]:
    if hardware == "NVIDIA":
        return (["-c:v", "hevc_nvenc" if codec == "h265" else "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-delay", "0", "-rc-lookahead", "0"], "nvenc")
    if hardware in {"Intel/AMD","Intel"}:
        return (["-c:v", "hevc_qsv" if codec == "h265" else "h264_qsv", "-preset", "medium"], "qsv")
    if hardware == "AMD":
        return (["-c:v", "hevc_amf" if codec == "h265" else "h264_amf", "-quality", "balanced"], "amf")
    return (["-c:v", "libx265" if codec == "h265" else "libx264", "-preset", "veryfast"], "cpu")


@lru_cache(maxsize=12)
def automatic_encoder(ffmpeg,codec):
    """Probe actual driver/codec support, not merely FFmpeg's compiled encoder list."""
    from .process import run
    for hardware in ("NVIDIA","Intel","AMD"):
        options,_=_encoder(codec,hardware)
        try:
            result=run([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i","color=s=640x360:r=30:d=0.1","-frames:v","2","-pix_fmt","yuv420p"]+options+["-f","null","-"],capture_output=True,timeout=8)
            if result.returncode==0:return hardware
        except (OSError,subprocess.TimeoutExpired):pass
    return "CPU"


def _target_size(item: TimelineItem, media, frame_width: int, face_factor: float = 1.0,
                 frame_height: int | None = None) -> tuple[int,int]:
    crop=item.crop.clamped(); source_w=max(1,media.width*crop.width); source_h=max(1,media.height*crop.height)
    full_w=max(1,media.width); full_h=max(1,media.height); frame_height=frame_height or round(frame_width*16/9)
    input_scale=max(frame_width/full_w,frame_height/full_h)
    # Input scaling fills the output at Zoom 1.000; crop and user transforms
    # operate on top of that same stable base in both preview and export.
    # Keep filter intermediates even-sized; several FFmpeg YUV paths otherwise
    # round one blur branch differently from its unblurred sibling.
    width=max(32,round(source_w*input_scale*face_factor*item.transform.scale/2)*2)
    height=max(32,round(source_h*input_scale*face_factor*item.transform.effective_scale_y/2)*2)
    return width,height


def _flip_filter(item: TimelineItem) -> str:
    return (",hflip" if item.transform.flip_horizontal else "")+(",vflip" if item.transform.flip_vertical else "")


def build_command(project,output,preset,burn_captions=True,hardware="Auto",ffmpeg="ffmpeg",ass_path=None,export_audio=True,prepared=None,transparent=False):
    from .rendergraph import command
    return command(project,output,preset,burn_captions,hardware,ffmpeg,ass_path,export_audio,prepared,transparent=transparent)


def export(project: Project, output: str, preset: ExportPreset,
           burn_captions: bool = True, hardware: str = "Auto", ffmpeg: str = "ffmpeg",
           progress: Callable[[float, str], None] | None = None,
           cancel=None, export_audio=True, lossless=False) -> None:
    from .missing_media import export_issues
    issues=export_issues(project)
    if issues:raise ValueError('Relink missing or mismatched media before exporting:\n'+'\n'.join(issues[:20]))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    from .compounds import prepare as prepare_compounds
    project=prepare_compounds(project,ffmpeg,progress,cancel)
    from .native_animation import prepared
    with prepared(project,progress,cancel) as native_project:
        return _export_prepared(native_project,output,preset,burn_captions,hardware,ffmpeg,progress,cancel,export_audio,lossless)

def _export_prepared(project,output,preset,burn_captions,hardware,ffmpeg,progress,cancel,export_audio,lossless):
    automatic=hardware=="Auto"
    if hardware=="Auto":
        if progress:progress(0,"Checking available hardware encoders…")
        hardware=automatic_encoder(ffmpeg,preset.codec)
    if progress:progress(0,"Preparing export · "+hardware+" encoder")
    from .vision_effects import prepare_export
    prepared=prepare_export(project,ffmpeg,progress,cancel)
    with tempfile.TemporaryDirectory(prefix=".kinetic-export-",dir=str(Path(output).parent)) as directory:
        from .render_batches import needed,prepare
        batched=needed(project)
        render_project=prepare(project,directory,preset,ffmpeg,prepared,progress,cancel,transparent=lossless) if batched else project
        ass_path = str(Path(directory) / "captions.ass")
        pending_output=str(Path(directory)/('render.mkv' if lossless else 'render.mp4'))
        if (burn_captions and project.captions) or any(item.role in {"title","graphic"} for item in project.timeline):
            write_ass(project, ass_path,burn_captions)
        command = build_command(render_project, pending_output, preset, burn_captions, hardware, ffmpeg, ass_path,export_audio,prepared,transparent=lossless)
        if lossless:
            threads=str(os.cpu_count() or 4)
            command=command[:command.index('-c:v')]+['-c:v','ffv1','-level','3','-slices','16','-pix_fmt','bgra','-threads',threads]+(['-c:a','pcm_s16le'] if export_audio else [])+['-t',f'{project.duration:.6f}','-progress','pipe:1','-nostats',pending_output]
        from .export_process import render
        final_progress=(lambda value,text:progress(.8+.2*value,'Finalising captions and audio · '+text)) if batched and progress else progress
        code,log_tail=render(command,project.duration,final_progress,cancel)
        if code:
            detail="\n".join(log_tail)
            if automatic and hardware!="CPU" and any(message in detail.lower() for message in ("error while opening encoder","cannot load","no capable devices","initializeencoder failed","device failed")):
                if progress:progress(0,"Hardware encoder unavailable for this output; retrying with CPU…")
                return export(project,output,preset,burn_captions,"CPU",ffmpeg,progress,cancel,export_audio)
            raise RuntimeError("FFmpeg export failed:\n" + "\n".join(log_tail)[-3000:])
        if cancel and cancel.is_set():raise RuntimeError('Export cancelled. Previous output is unchanged.')
        os.replace(pending_output,output)
        if progress:progress(1.0, "Export complete")
