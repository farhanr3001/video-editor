"""Portable, model-free object trajectories in original-media coordinates.

Only the selected clip's source interval is analysed. Decoding and matching are
streamed in bounded batches; no downloaded model, disk cache or media path is
stored in the result. This is a region tracker, not a semantic object detector.
"""
from __future__ import annotations

import bisect
import hashlib
import io
import json
import math
import os
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

VERSION = 1
MAX_DURATION = 600.0
MAX_RECORDS = 10000
MAX_BYTES = 1024 * 1024
ANALYSIS_EDGE = 640
REVERSE_BATCH = 24


def _cancel(cancel):
    if cancel is not None and cancel.is_set():
        from .vocal_component import Cancelled
        raise Cancelled("Object tracking cancelled; the clip and source were not changed.")


class _QtInput(io.RawIOBase):
    """PyAV adapter over the editor's existing share-delete Windows input."""
    def __init__(self, device):
        super().__init__()
        self.device = device

    def readable(self):
        return True

    def seekable(self):
        return True

    def read(self, size=-1):
        return bytes(self.device.readAll() if size < 0 else self.device.read(size))

    def readinto(self, buffer):
        value = self.read(len(buffer))
        buffer[:len(value)] = value
        return len(value)

    def tell(self):
        return self.device.pos()

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_CUR:
            offset += self.tell()
        elif whence == io.SEEK_END:
            offset += self.device.size()
        if not self.device.seek(offset):
            raise OSError(self.device.errorString())
        return self.tell()

    def close(self):
        if not self.closed:
            self.device.close()
        super().close()


@contextmanager
def _source(path):
    if os.name == "nt":
        from .media_source import open_shared_media
        stream = _QtInput(open_shared_media(str(path)))
    else:
        stream = open(path, "rb")
    try:
        yield stream
    finally:
        stream.close()


@lru_cache(maxsize=32)
def _digest(path, size, modified, changed, inode):
    # Distributed bounded reads avoid hashing many gigabytes on a viewer frame.
    # The mtime additionally invalidates ordinary in-place changes between reads.
    digest = hashlib.sha256()
    with _source(path) as stream:
        digest.update(stream.read(128 * 1024))
        if size > 128 * 1024:
            stream.seek(max(128 * 1024, size - 128 * 1024))
            digest.update(stream.read(128 * 1024))
        if size > 256 * 1024:
            for fraction in (1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6):
                stream.seek(max(0, min(size - 65536, int(size * fraction))))
                digest.update(stream.read(65536))
    return digest.hexdigest()


def fingerprint(media):
    path = Path(media.path).resolve()
    stat = path.stat()
    return dict(size=stat.st_size, mtime_ns=stat.st_mtime_ns,
                digest=_digest(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino),
                width=int(media.width), height=int(media.height))


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _box(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4 or not all(_number(v) for v in value):
        raise ValueError("Select a rectangular object region inside the source frame.")
    x, y, width, height = map(float, value)
    if width < .004 or height < .004 or x < 0 or y < 0 or x + width > 1.000001 or y + height > 1.000001:
        raise ValueError("The tracking region must fit inside the source and have a visible size.")
    return [x, y, width, height]


def _record_valid(record):
    try:
        _box(record["box"])
        return (_number(record["time"]) and _number(record["confidence"])
                and 0 <= record["confidence"] <= 1
                and record["status"] in ("tracked", "manual", "lost"))
    except (TypeError, KeyError, ValueError):
        return False


def validate(analysis):
    """Strict structural check for incoming persisted/MCP data, without media I/O."""
    try:
        frames = analysis["frames"]
        if (analysis["version"] != VERSION or not isinstance(frames, list)
                or not 1 <= len(frames) <= MAX_RECORDS
                or not _number(analysis["source_start"]) or not _number(analysis["source_end"])
                or not 0 <= analysis["source_start"] <= analysis["source_end"]
                or analysis["source_end"] - analysis["source_start"] > MAX_DURATION + .001
                or not _number(analysis["sample_fps"]) or not 1 <= analysis["sample_fps"] <= 60
                or len(json.dumps(analysis).encode("utf-8")) > MAX_BYTES):
            return False
        previous = -math.inf
        for record in frames:
            if not _record_valid(record) or record["time"] <= previous:
                return False
            previous = record["time"]
        return (abs(frames[0]["time"] - analysis["source_start"]) < .00001
                and abs(frames[-1]["time"] - analysis["source_end"]) < .00001)
    except (TypeError, KeyError, ValueError):
        return False


def valid(analysis, media, item=None):
    """Fast preview guard; sample() additionally validates its neighboring points.

    Use validate() once when accepting analysis. The path-independent identity
    permits a timestamp-preserving identical source relink and rejects ordinary
    replaced/modified sources. A copy with a different mtime needs re-analysis.
    """
    try:
        frames = analysis["frames"]
        if (analysis["version"] != VERSION or not isinstance(frames, list)
                or not 1 <= len(frames) <= MAX_RECORDS
                or not _record_valid(frames[0]) or not _record_valid(frames[-1])
                or analysis["source"] != fingerprint(media)
                or not _number(analysis["source_start"]) or not _number(analysis["source_end"])
                or not 0 <= analysis["source_start"] <= analysis["source_end"]):
            return False
        if item is not None:
            start, end = sorted((item.in_point, item.in_point + item.source_duration))
            if start < analysis["source_start"] - .00001 or end > analysis["source_end"] + .00001:
                return False
        return True
    except (TypeError, KeyError, OSError, ValueError, AttributeError):
        return False


def sample(analysis, source_time):
    """Sample a trajectory, returning None outside it and explicit lost spans."""
    try:
        if not _number(source_time):
            return None
        if source_time < analysis["source_start"] - .000001 or source_time > analysis["source_end"] + .000001:
            return None
        frames = analysis["frames"]
        index = bisect.bisect_right(frames, source_time, key=lambda point: point["time"])
        left = frames[max(0, index - 1)]
        right = frames[min(len(frames) - 1, index)]
        if not _record_valid(left) or not _record_valid(right):
            return None
        if abs(source_time - right["time"]) < .000001:
            return dict(time=float(source_time), box=list(right["box"]),
                        confidence=right["confidence"], status=right["status"])
        if abs(source_time - left["time"]) < .000001:
            return dict(time=float(source_time), box=list(left["box"]),
                        confidence=left["confidence"], status=left["status"])
        if right["time"] <= left["time"]:
            return dict(time=float(source_time), box=list(left["box"]),
                        confidence=left["confidence"], status=left["status"])
        fraction = (source_time - left["time"]) / (right["time"] - left["time"])
        if "lost" in (left["status"], right["status"]):
            nearest = left if fraction < .5 else right
            return dict(time=float(source_time), box=list(nearest["box"]),
                        confidence=min(left["confidence"], right["confidence"]), status="lost")
        return dict(time=float(source_time),
                    box=[a + (b - a) * fraction for a, b in zip(left["box"], right["box"])],
                    confidence=min(left["confidence"], right["confidence"]), status="tracked")
    except (TypeError, KeyError, ValueError, IndexError):
        return None


def _resize(gray, width, height):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.fromarray(gray.astype("float32"), mode="F").resize(
        (max(4, int(width)), max(4, int(height))), Image.Resampling.BILINEAR), dtype="float32")


def _integral(array):
    import numpy as np
    return np.pad(array.cumsum(0, dtype="float64").cumsum(1), ((1, 0), (1, 0)))


def _sums(integral, height, width):
    return integral[height:, width:] - integral[:-height, width:] - integral[height:, :-width] + integral[:-height, :-width]


def _correlation(image, template):
    """Normalized correlation using FFT and integral local variance, without cv2."""
    import numpy as np
    height, width = template.shape
    if image.shape[0] < height or image.shape[1] < width:
        return None
    centered = template.astype("float64")
    centered -= centered.mean()
    energy = float((centered * centered).sum())
    if energy < 1e-6:
        return None
    shape = tuple(1 << (n - 1).bit_length() for n in (image.shape[0] + height - 1, image.shape[1] + width - 1))
    numerator = np.fft.irfft2(np.fft.rfft2(image, shape) * np.fft.rfft2(centered[::-1, ::-1], shape), shape)
    numerator = numerator[height - 1:image.shape[0], width - 1:image.shape[1]]
    sums = _sums(_integral(image), height, width)
    squares = _sums(_integral(image.astype("float64") ** 2), height, width)
    variance = np.maximum(0, squares - sums * sums / (height * width))
    result = np.clip(numerator / np.sqrt(np.maximum(variance * energy, 1e-12)), -1, 1)
    # A flat occluder has no matchable texture. Floating-point residue divided
    # by near-zero local energy must never turn it into a confident match.
    result[variance <= height * width * 1e-5] = -1
    return result


class RegionTracker:
    """Bounded grayscale region matching; independently adapts width and height."""
    def __init__(self, frame, region, search_radius=.22, confidence_threshold=.58):
        import numpy as np
        self.height, self.width = frame.shape
        self.box = [region[0] * self.width, region[1] * self.height,
                    region[2] * self.width, region[3] * self.height]
        self.search_radius = search_radius
        self.threshold = confidence_threshold
        self.velocity = np.zeros(2, dtype="float64")
        self.lost = 0
        self.template = self._extract(frame, self.box)
        if self.template.shape[0] < 6 or self.template.shape[1] < 6 or self.template.std() < .015:
            raise ValueError("The selected region is too small or featureless. Include visible texture or an edge.")
        self.reference = self.template.copy()

    def _extract(self, frame, box):
        x, y, width, height = box
        left, top = max(0, round(x)), max(0, round(y))
        right, bottom = min(self.width, round(x + width)), min(self.height, round(y + height))
        return frame[top:bottom, left:right].copy()

    def _normalized(self):
        x, y, width, height = self.box
        return [round(x / self.width, 7), round(y / self.height, 7),
                round(width / self.width, 7), round(height / self.height, 7)]

    def update(self, frame, cancel=None):
        import numpy as np
        _cancel(cancel)
        x, y, width, height = self.box
        center = np.array([x + width / 2, y + height / 2])
        predicted = center + self.velocity * (0 if self.lost else 1)
        radius_x = max(20, self.width * self.search_radius * (1.6 if self.lost else 1))
        radius_y = max(20, self.height * self.search_radius * (1.6 if self.lost else 1))
        left = max(0, int(predicted[0] - width / 2 - radius_x))
        top = max(0, int(predicted[1] - height / 2 - radius_y))
        right = min(self.width, int(predicted[0] + width / 2 + radius_x + 1))
        bottom = min(self.height, int(predicted[1] + height / 2 + radius_y + 1))
        search = frame[top:bottom, left:right]
        best = None
        sizes = {(max(6, round(width * sx)), max(6, round(height * sy)))
                 for sx, sy in ((1, 1), (.92, 1), (1.08, 1), (1, .92), (1, 1.08), (.92, .92), (1.08, 1.08))}
        # Pixel-sized refinement matters for small crops: an 8% step alone can
        # skip a one-pixel scale change and lose an otherwise perfect target.
        sizes.update((max(6, round(width) + dx), max(6, round(height) + dy))
                     for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        for candidate_width, candidate_height in sorted(sizes):
            _cancel(cancel)
            if candidate_width > self.width or candidate_height > self.height:
                continue
            template = _resize(self.template, candidate_width, candidate_height)
            correlation = _correlation(search, template)
            if correlation is None or not correlation.size:
                continue
            iy, ix = np.unravel_index(int(correlation.argmax()), correlation.shape)
            score = float(correlation[iy, ix])
            # Prefer a stable scale when different sizes match equally well.
            rank = score - .006 * (abs(candidate_width / width - 1) + abs(candidate_height / height - 1))
            if best is None or rank > best[0]:
                best = (rank, score, left + int(ix), top + int(iy), candidate_width, candidate_height, correlation, int(ix), int(iy))
        if best is None:
            self.lost += 1
            return dict(box=self._normalized(), confidence=0.0, status="lost")
        _, score, found_x, found_y, found_width, found_height, correlation, ix, iy = best
        # A repeated identical object is ambiguous: retain an explicit lost span.
        competitors = correlation.copy()
        exclusion_x, exclusion_y = max(3, found_width // 3), max(3, found_height // 3)
        competitors[max(0, iy - exclusion_y):iy + exclusion_y + 1,
                    max(0, ix - exclusion_x):ix + exclusion_x + 1] = -1
        second = float(competitors.max()) if competitors.size else -1
        ambiguous = second > score - .035 and second > .70
        threshold = max(self.threshold, .68) if self.lost else self.threshold
        if score < threshold or ambiguous:
            self.lost += 1
            self.velocity *= .4
            return dict(box=self._normalized(), confidence=round(max(0, score), 5), status="lost")
        found_center = np.array([found_x + found_width / 2, found_y + found_height / 2])
        self.velocity = .35 * self.velocity + .65 * (found_center - center)
        self.box = [found_x, found_y, found_width, found_height]
        self.lost = 0
        # Update only confidently matched, unambiguous texture. Following gradual
        # appearance changes (a leaning head, lighting or expression) requires
        # learning the observed patch before it diverges from the first frame.
        # Keep a small fixed-reference contribution; never learn from lost,
        # ambiguous or weak matches, including a uniform occluder.
        if score >= .68:
            patch = _resize(self._extract(frame, self.box), self.template.shape[1], self.template.shape[0])
            self.template = .69 * self.template + .30 * patch + .01 * self.reference
        return dict(box=self._normalized(), confidence=round(max(0, min(1, score)), 5), status="tracked")


class _Frames:
    """Seekable PyAV samples; backward work retains at most 24 downscaled frames."""
    def __init__(self, media, cancel):
        self.media, self.cancel = media, cancel

    def __enter__(self):
        import av
        self.source = _source(self.media.path)
        self.file = self.source.__enter__()
        try:
            self.movie = av.open(self.file)
            self.stream = self.movie.streams.video[0]
            self.origin = float((self.stream.start_time or 0) * self.stream.time_base)
        except Exception:
            self.source.__exit__(*__import__("sys").exc_info())
            raise
        return self

    def __exit__(self, kind, value, traceback):
        self.movie.close()
        self.source.__exit__(kind, value, traceback)

    def _gray(self, frame):
        import numpy as np
        scale = min(1.0, ANALYSIS_EDGE / max(frame.width, frame.height))
        image = frame.reformat(width=max(2, round(frame.width * scale)),
                               height=max(2, round(frame.height * scale)), format="gray")
        return image.to_ndarray().astype(np.float32) / 255.0

    def forward(self, times):
        if not times:
            return
        _cancel(self.cancel)
        self.movie.seek(max(0, int((times[0] + self.origin) / self.stream.time_base)), stream=self.stream, backward=True)
        decoded = iter(self.movie.decode(self.stream))
        previous = None
        current = None
        exhausted = False
        for timestamp in times:
            _cancel(self.cancel)
            while not exhausted and (current is None or float(current.time or 0) - self.origin < timestamp):
                previous = current
                try:
                    current = next(decoded)
                except StopIteration:
                    exhausted = True
            if current is None:
                raise ValueError("The clip has no decodable video frames in the selected interval.")
            selected = current
            if previous is not None and abs(float(previous.time or 0) - self.origin - timestamp) <= abs(float(current.time or 0) - self.origin - timestamp):
                selected = previous
            yield timestamp, self._gray(selected)

    def read(self, times):
        if not times:
            return
        if len(times) < 2 or times[0] < times[-1]:
            yield from self.forward(times)
        else:
            for start in range(0, len(times), REVERSE_BATCH):
                batch = times[start:start + REVERSE_BATCH]
                frames = list(self.forward(list(reversed(batch))))
                yield from reversed(frames)


def _analyze_frames(reader, times, seeds, search_radius, confidence_threshold, progress, cancel):
    records = {}
    completed = 0
    for index, (timestamp, box) in enumerate(seeds):
        _cancel(cancel)
        seed_frame = next(reader.read([timestamp]))[1]
        records[timestamp] = dict(time=timestamp, box=list(box), confidence=1.0, status="manual")
        if timestamp in times:
            completed += 1
        previous_midpoint = (seeds[index - 1][0] + timestamp) / 2 if index else -math.inf
        next_midpoint = (timestamp + seeds[index + 1][0]) / 2 if index + 1 < len(seeds) else math.inf
        directions = ([t for t in reversed(times) if previous_midpoint < t < timestamp],
                      [t for t in times if timestamp < t <= next_midpoint])
        for direction in directions:
            if not direction:
                continue
            tracker = RegionTracker(seed_frame, box, search_radius, confidence_threshold)
            for time, frame in reader.read(direction):
                _cancel(cancel)
                result = tracker.update(frame, cancel)
                records[time] = dict(time=time, **result)
                completed += 1
                if progress is not None:
                    progress(min(99.0, completed / len(times) * 100),
                             f"Tracking object · {completed} / {len(times)} samples" + (" · target lost" if result["status"] == "lost" else ""))
    return [records[time] for time in sorted(records)]


def analyze(media, item, reference_source_time, region, anchors=None, progress=None, cancel=None,
            *, sample_fps=15, search_radius=.22, confidence_threshold=.58):
    """Track outward from reference/correction frames through a trimmed clip.

    ``region`` and anchor ``box`` are [x,y,width,height] normalized full-source
    rectangles. ``anchors`` is a list of {time:source_seconds, box:[...]}.
    Sampling and correction times are source times, independent of timeline
    position, crop and playback speed. Width/height can change independently;
    automatic rotation/perspective tracking is deliberately not claimed.
    """
    _cancel(cancel)
    if media.kind not in ("video", "image", "compound"):
        raise ValueError("Object tracking requires a video or still-image clip.")
    if not _number(sample_fps) or not 1 <= sample_fps <= 60:
        raise ValueError("Tracking sample rate must be between 1 and 60 fps.")
    if not _number(search_radius) or not .02 <= search_radius <= .6:
        raise ValueError("Search radius must be between .02 and .6 of the source frame.")
    if not _number(confidence_threshold) or not .2 <= confidence_threshold <= .95:
        raise ValueError("Confidence threshold must be between .2 and .95.")
    start, end = float(item.in_point), float(item.in_point + item.source_duration)
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError("The clip must have a valid positive source interval.")
    if end - start > MAX_DURATION:
        raise ValueError("Track clips up to 10 minutes at a time. Split a longer source into shorter clips first.")
    if not _number(reference_source_time) or not start <= reference_source_time <= end:
        raise ValueError("The reference frame must be inside the selected clip's source interval.")
    if anchors is None:
        anchors = []
    if not isinstance(anchors, list) or len(anchors) > 128:
        raise ValueError("At most 128 manual correction anchors can be analysed at once.")
    seed_map = {round(float(reference_source_time), 7): _box(region)}
    for anchor in anchors:
        if not isinstance(anchor, dict) or not _number(anchor.get("time")) or not start <= anchor["time"] <= end:
            raise ValueError("Manual corrections must use source times inside the selected clip.")
        seed_map[round(float(anchor["time"]), 7)] = _box(anchor.get("box", anchor.get("region")))
    count = math.ceil((end - start) * sample_fps)
    times = sorted(set([round(start + n / sample_fps, 7) for n in range(count)] +
                       [round(start, 7), round(end, 7)] + list(seed_map)))
    if len(times) > MAX_RECORDS:
        raise ValueError("Too many tracking samples; lower the sample rate or shorten the clip.")
    source = fingerprint(media)
    if media.kind == "image":
        from PIL import Image
        with _source(media.path) as stream:
            with Image.open(stream) as image:
                image.verify()
        endpoints = dict(seed_map)
        endpoints.setdefault(round(start, 7), seed_map[min(seed_map)])
        endpoints.setdefault(round(end, 7), seed_map[max(seed_map)])
        frames = [dict(time=t, box=list(box), confidence=1.0, status="manual")
                  for t, box in sorted(endpoints.items())]
    else:
        with _Frames(media, cancel) as reader:
            frames = _analyze_frames(reader, times, sorted(seed_map.items()), search_radius,
                                     confidence_threshold, progress, cancel)
    _cancel(cancel)
    if fingerprint(media) != source:
        raise ValueError("The source changed during tracking. No analysis was applied; select the region and retry.")
    result = dict(version=VERSION, source=source, source_start=round(start, 7), source_end=round(end, 7),
                  sample_fps=float(sample_fps), reference_time=round(float(reference_source_time), 7), frames=frames,
                  anchors=[dict(time=t, box=b) for t, b in sorted(seed_map.items())],
                  search_radius=float(search_radius), confidence_threshold=float(confidence_threshold))
    if len(json.dumps(result).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Tracking data exceeds 1 MiB. Shorten the clip or lower the sample rate, then analyse again.")
    if not validate(result):
        raise ValueError("Object analysis did not produce a complete valid trajectory.")
    if progress is not None:
        lost = sum(frame["status"] == "lost" for frame in frames)
        progress(100.0, "Tracking complete" + (f" · review {lost} lost samples" if lost else ""))
    return result
