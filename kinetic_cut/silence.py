from __future__ import annotations

import re
from .process import run as run_process


START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def parse_silences(text: str, duration: float) -> list[tuple[float, float]]:
    events: list[tuple[str, float]] = []
    for line in text.splitlines():
        start = START_RE.search(line)
        end = END_RE.search(line)
        if start:
            events.append(("start", float(start.group(1))))
        if end:
            events.append(("end", float(end.group(1))))
    silences: list[tuple[float, float]] = []
    open_start: float | None = None
    for kind, timestamp in events:
        if kind == "start":
            open_start = timestamp
        elif open_start is not None:
            silences.append((open_start, timestamp))
            open_start = None
    if open_start is not None:
        silences.append((open_start, duration))
    return silences


def keep_ranges(silences: list[tuple[float, float]], duration: float,
                padding: float = 0.12, minimum_keep: float = 0.08) -> list[tuple[float, float]]:
    if not silences:
        return [(0.0, duration)] if duration > 0 else []
    kept: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in silences:
        start = min(duration, max(0.0, start))
        end = min(duration, max(start, end))
        if start >= duration:
            break
        cut_start = max(cursor, start + padding)
        cut_end = min(duration, end - padding)
        if cut_start > cursor + minimum_keep:
            kept.append((cursor, cut_start))
        cursor = max(cursor, cut_end)
    if duration > cursor + minimum_keep:
        kept.append((cursor, duration))
    return kept


def detect(path: str, duration: float, threshold_db: float = -34.0,
           minimum_silence: float = 0.42, padding: float = 0.12,
           ffmpeg: str = "ffmpeg", in_point: float = 0.0) -> list[tuple[float, float]]:
    command = [ffmpeg, "-hide_banner", "-nostats", "-ss", f"{in_point:.6f}",
               "-t", f"{duration:.6f}", "-i", path, "-af",
               f"silencedetect=noise={threshold_db}dB:d={minimum_silence}", "-f", "null", "-"]
    result = run_process(command, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return keep_ranges(parse_silences(result.stderr, duration), duration, padding)
