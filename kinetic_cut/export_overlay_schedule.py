"""Conservative original-frame sampling for an exact, otherwise static ASS layer.

Only the transport cadence is reduced. Callers must evaluate retained frames at
their original timestamps and repeat them until the next retained frame. Unknown
or dense scripts keep the ordinary continuous renderer by returning ``None``.
"""
import math
import re
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path


_EVENT_FORMAT = (
    'layer', 'start', 'end', 'style', 'name', 'marginl', 'marginr',
    'marginv', 'effect', 'text',
)
_TIME = re.compile(r'([0-9]{1,9}):([0-5][0-9]):([0-5][0-9])\.([0-9]{2})\Z')
_INTEGER = re.compile(r'[+-]?[0-9]{1,9}\Z')
# Matching tag prefixes deliberately over-classifies malformed/escaped text.
# A false positive only disables sampling; missing a time-dependent tag could
# freeze an animation. In particular this includes \K, \kf, \ko and \kt.
_DYNAMIC = re.compile(r'\\(?:t|move|fad|fade|k)', re.IGNORECASE)
_POSITION = re.compile(r'(?<!\\)\\(pos|move)\(([^()]*)\)', re.IGNORECASE)
_MAX_FILE_BYTES = 64 * 1024 * 1024
_MAX_FRAMES = 250000


def _centiseconds(value):
    match = _TIME.fullmatch(value.strip())
    if match is None:
        raise ValueError('Unrecognised ASS timestamp')
    hours, minutes, seconds, centiseconds = map(int, match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 100 + centiseconds


def sample_frames(ass_path, fps, total_frames):
    """Return exact original frame indices, or ``None`` for continuous rendering.

    Generated ASS timestamps have centisecond precision. Neighboring frames on
    both sides of every boundary conservatively cover the renderer's millisecond
    clock rounding at the native exporter's supported frame rates. Any animation
    tag or Effect keeps its *entire* event interval, rather than trying to infer
    nested transform/karaoke timing. The last frame is retained so the producer's
    terminal success must be checked before an export can complete.
    """
    if isinstance(total_frames, bool) or not isinstance(total_frames, int):
        return None
    if not 1 <= total_frames <= _MAX_FRAMES:
        return None
    try:
        numeric_fps = float(fps)
        if isinstance(fps, bool) or not math.isfinite(numeric_fps) or not 1 <= numeric_fps <= 240:
            return None
        rate = Fraction(str(numeric_fps)).limit_denominator(1001000)
        path = Path(ass_path)
        if not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            return None
    except (OSError, TypeError, ValueError, OverflowError):
        return None

    retained = bytearray(total_frames)
    retained[0] = retained[-1] = 1
    section = ''
    format_seen = events_seen = False

    def frame_at(centiseconds):
        numerator = centiseconds * rate.numerator
        denominator = 100 * rate.denominator
        return (numerator + denominator - 1) // denominator

    def boundary(frame):
        for index in (frame - 1, frame, frame + 1):
            if 0 <= index < total_frames:
                retained[index] = 1

    try:
        # Read incrementally, with a total-size guard even if the file changes
        # after stat(). The input is an owned generated script, not a GUI object.
        consumed = 0
        with path.open('r', encoding='utf-8-sig') as stream:
            for raw in stream:
                consumed += len(raw)
                if consumed > _MAX_FILE_BYTES:
                    return None
                line = raw.strip()
                if not line or line.startswith(';'):
                    continue
                if line.startswith('[') and line.endswith(']'):
                    section = line.casefold()
                    if section not in ('[script info]', '[v4+ styles]', '[events]'):
                        return None
                    if section == '[events]':
                        if events_seen:
                            return None
                        events_seen = True
                    continue
                if ':' not in line:
                    return None
                kind, value = line.split(':', 1)
                kind = kind.strip().casefold()
                if section == '[script info]':
                    if kind == 'timer':
                        timer = Decimal(value.strip())
                        if not timer.is_finite() or timer != 100:
                            return None
                    elif kind == 'scripttype' and value.strip().casefold() != 'v4.00+':
                        return None
                    continue
                if section == '[v4+ styles]':
                    # Style fields are static. The event format is the one whose
                    # column order determines the timeline parsed below.
                    if kind not in ('format', 'style'):
                        return None
                    continue
                if section != '[events]':
                    return None
                if kind == 'format':
                    if format_seen or tuple(part.strip().casefold() for part in value.split(',')) != _EVENT_FORMAT:
                        return None
                    format_seen = True
                    continue
                if kind == 'comment':
                    continue
                if kind != 'dialogue' or not format_seen:
                    return None
                parts = value.split(',', 9)
                if len(parts) != 10 or not _INTEGER.fullmatch(parts[0].strip()):
                    return None
                if any(not _INTEGER.fullmatch(parts[index].strip()) for index in (5, 6, 7)):
                    return None
                start = _centiseconds(parts[1])
                finish = _centiseconds(parts[2])
                if finish < start:
                    return None
                # Automatic ASS collision placement can depend on render
                # history. Canonical app events position every component
                # explicitly, so decline scripts that could use that state.
                if not parts[9].startswith('{') or '}' not in parts[9]:
                    return None
                tags = parts[9][1:parts[9].find('}')]
                positioned = False
                for position in _POSITION.finditer(tags):
                    coordinates = [float(value.strip()) for value in position[2].split(',')]
                    expected = (2,) if position[1].casefold() == 'pos' else (4, 6)
                    if len(coordinates) in expected and all(math.isfinite(value) for value in coordinates):
                        positioned = True
                        break
                if not positioned:
                    return None
                first, stop = frame_at(start), frame_at(finish)
                boundary(first)
                boundary(stop)
                if parts[8].strip() or _DYNAMIC.search(parts[9]):
                    lower, upper = max(0, first), min(total_frames, stop)
                    if upper > lower:
                        retained[lower:upper] = b'\1' * (upper - lower)
    except (OSError, UnicodeError, ValueError, InvalidOperation, OverflowError):
        return None
    if not events_seen or not format_seen:
        return None
    # Keep the simple streaming path when sampling saves too little work.
    if sum(retained) * 5 >= total_frames * 4:
        return None
    return [index for index, keep in enumerate(retained) if keep]
