"""Source-domain object markers, shared by the viewer and lossless export.

Tracking coordinates always describe the full original media. Cropping and
clip transforms remain the compositor's responsibility. Analysis contains only
small trajectory records; source pixels and generated caches never enter it.
"""
from __future__ import annotations

import math
import bisect
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QImageReader,
                           QPainter, QPainterPath, QPen, QPolygonF, QTransform)

from .image_cache import FileImageCache

NAME = 'Object Tracking'
MODES = ('Blur', 'Pixelate', 'Censor Bar', 'Arrow', 'Circle', 'Rectangle', 'Label', 'Image', 'Follow Crop')
CENSOR_MODES = frozenset(('Blur', 'Pixelate', 'Censor Bar'))
LOSS_POLICIES = ('Full frame', 'Hold', 'Hide')
VISION_CONFLICT_ERROR = 'Follow Crop cannot be combined with face/background analysis effects on the same clip. Remove one of these effects before exporting.'
_images = FileImageCache(32 * 1024**2, max_entries=16)
_render_lock = RLock()


@contextmanager
def prepared(project):
    """Lease generated trajectories through the complete export consumption.

    Normal exports never wait. Reentrant locking also permits compound/CPU
    fallback exports on the same worker without deleting their live cache files.
    """
    if not any(active(item) for item in project.timeline):
        yield; return
    with _render_lock:
        try:
            yield
        finally:
            from .config import CACHE_DIR
            prune(CACHE_DIR / 'vision-renders')


def default_effect(mode='Censor Bar'):
    if mode not in MODES:
        raise ValueError('Unknown object tracking marker')
    return dict(name=NAME, enabled=True, mode=mode, analysis={},
                loss_policy='Full frame' if mode in CENSOR_MODES else 'Hold' if mode == 'Follow Crop' else 'Hide',
                loss_reviewed=False, follow_scale=True, width=100., height=100.,
                padding=12., offset_x=0., offset_y=0., rotation=0., opacity=100.,
                color='#000000', stroke_width=6., fill=False, blur=30., pixel_size=18.,
                arrow_length=120., arrow_head=28., label='Tracked object',
                font='Segoe UI', font_size=48., label_color='#ffffff',
                label_background='#000000', label_padding=12., radius=8., image='')


def active(item):
    return [e for e in item.effects if e.get('name') == NAME and e.get('enabled', True)]


def follow_effect(item):
    """The last enabled viewport wins; preceding viewport settings are inert."""
    return next((e for e in reversed(active(item)) if e.get('mode') == 'Follow Crop'), None)


def render_effects(item):
    follow = follow_effect(item)
    return [e for e in active(item) if e.get('mode') != 'Follow Crop' or e is follow]


def _vision_conflict(item):
    from .vision_effects import active as vision_active
    return bool(follow_effect(item) and vision_active(item))


def validate(effect):
    """Return bounded appearance settings without copying the large trajectory.

    Invalid numbers are rejected rather than silently disabling a censor. The
    renderer catches rejection and draws an opaque safety cover for censor modes.
    """
    if not isinstance(effect, dict) or effect.get('name') != NAME:
        raise ValueError('Invalid object tracking effect')
    mode = effect.get('mode', 'Censor Bar')
    result = default_effect(mode)
    result.update(effect)
    if result['loss_policy'] not in LOSS_POLICIES:
        raise ValueError('Invalid tracking loss policy')
    ranges = dict(width=(1, 1000), height=(1, 1000), padding=(0, 4096),
                  offset_x=(-32768, 32768), offset_y=(-32768, 32768),
                  rotation=(-3600, 3600), opacity=(0, 100), stroke_width=(0, 1024),
                  blur=(1, 500), pixel_size=(2, 512), arrow_length=(1, 8192),
                  arrow_head=(1, 2048), font_size=(4, 1024), label_padding=(0, 1024),
                  radius=(0, 1024))
    for name, (low, high) in ranges.items():
        value = result[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid object tracking property: ' + name)
        result[name] = float(value)
    for name in ('enabled', 'loss_reviewed', 'follow_scale', 'fill'):
        if not isinstance(result[name], bool):
            raise ValueError('Invalid object tracking switch: ' + name)
    for name in ('color', 'label_color', 'label_background'):
        if not isinstance(result[name], str) or not QColor(result[name]).isValid():
            raise ValueError('Invalid object tracking colour: ' + name)
    for name, limit in (('label', 512), ('font', 128), ('image', 4096)):
        if not isinstance(result[name], str) or len(result[name]) > limit:
            raise ValueError('Invalid object tracking text: ' + name)
    if not isinstance(result['analysis'], dict):
        raise ValueError('Invalid object tracking analysis')
    return result


def valid(effect, media, item=None):
    from .object_tracking import valid as valid_analysis
    try:
        settings = validate(effect)
        return valid_analysis(settings['analysis'], media, item)
    except (ValueError, TypeError, AttributeError, OSError):
        return False


def _sample(effect, media, item, source_time):
    from .object_tracking import sample
    return sample(effect['analysis'], source_time) if valid(effect, media, item) else None


def _held_box(analysis, source_time):
    """Keep only a genuinely observed previous target, never a failed estimate."""
    from .object_tracking import sample
    try:
        frames = analysis['frames']
        index = bisect.bisect_right(frames, source_time + 1e-8, key=lambda frame: frame['time']) - 1
        while index >= 0:
            frame = frames[index]; index -= 1
            if frame['status'] in ('tracked', 'manual'):
                record = sample(analysis, frame['time'])
                return record['box'] if record and record['status'] != 'lost' else None
    except (TypeError, KeyError, ValueError, IndexError):
        pass
    return None


def box_at(effect, media, item, source_time):
    """Return a normalized full-source box, or None for hidden/unsafe motion."""
    try:
        effect = validate(effect)
    except (ValueError, TypeError):
        return None
    record = _sample(effect, media, item, source_time)
    if record and record['status'] in ('tracked', 'manual'):
        return list(record['box'])
    if record and effect['loss_policy'] == 'Hold':
        return _held_box(effect['analysis'], source_time)
    return None


def has_losses(effect, media, item):
    from .object_tracking import sample
    if not valid(effect, media, item):
        return True
    a = effect['analysis']; start = item.in_point; end = start + item.source_duration
    return (any(f['status'] == 'lost' and start - 1e-8 <= f['time'] <= end + 1e-8 for f in a['frames'])
            or any((sample(a, t) or {}).get('status') == 'lost' for t in (start, end)))


def _usable_image(path):
    try:
        reader = QImageReader(path)
        size = reader.size()
        return (Path(path).is_file() and 0 < size.width() <= 8192 and 0 < size.height() <= 8192
                and size.width() * size.height() <= 32 * 1024**2 and reader.canRead())
    except (OSError, TypeError):
        return False


def export_error(effect, media, item):
    from .object_tracking import validate as validate_analysis
    if effect.get('mode') == 'Follow Crop':
        from .vision_effects import active as vision_active
        if vision_active(item):
            return VISION_CONFLICT_ERROR
    if not valid(effect, media, item) or not validate_analysis(effect.get('analysis', {})):
        return 'Object tracking is missing or its source/range changed. Select the clip and analyse the target again before exporting.'
    effect = validate(effect)
    if effect['mode'] == 'Image' and not _usable_image(effect['image']):
        return 'The tracked image marker is missing or unreadable. Choose its image again before exporting.'
    if (effect['mode'] in CENSOR_MODES and effect['loss_policy'] != 'Full frame'
            and not effect['loss_reviewed'] and has_losses(effect, media, item)):
        return 'Object tracking lost the censored target. Review the failed sections or choose Full frame protection before exporting.'
    return ''


def status(item, media, source_time):
    if _vision_conflict(item):
        return 'Follow Crop unavailable with face/background analysis effects — remove one effect'
    for effect in render_effects(item):
        if not valid(effect, media, item):
            if effect.get('mode') == 'Follow Crop':
                return 'Follow Crop needs analysis — original crop retained'
            return 'Object tracking needs analysis — censor protected; markers hidden'
        settings = validate(effect)
        if settings['mode'] == 'Image' and not _usable_image(settings['image']):
            return 'Tracked image missing — choose the marker image again'
        record = _sample(settings, media, item, source_time)
        if not record or record['status'] == 'lost':
            if settings['mode'] == 'Follow Crop':
                return 'Tracking lost — crop held at last position' if settings['loss_policy'] == 'Hold' else 'Tracking lost — crop fallback active'
            if settings['mode'] in CENSOR_MODES:
                return 'Tracking lost — ' + ('full-frame censor protection' if settings['loss_policy'] == 'Full frame' else 'review censor coverage before export')
            return 'Tracking lost — marker ' + ('held at last position' if settings['loss_policy'] == 'Hold' else 'hidden')
    return ''


def cache_key(item, media, source_time):
    """Compact dynamic signature: trajectories need not be repr'd every frame."""
    records = []
    for effect in item.effects:
        if effect.get('name') != NAME:
            records.append(repr(effect)); continue
        appearance = {k: v for k, v in effect.items() if k != 'analysis'}
        sample = _sample(effect, media, item, source_time)
        records.append((repr(appearance), repr(sample)))
        if effect.get('mode') == 'Image':
            try:
                stat = Path(effect.get('image', '')).stat()
                records.append((stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            except OSError:
                records.append(None)
    return tuple(records), round(source_time, 9)


def _cover(image):
    result = QImage(image.size(), QImage.Format_RGBA8888)
    result.fill(QColor('#000000'))
    return result


def _reference_box(analysis):
    from .object_tracking import sample
    record = sample(analysis, analysis.get('reference_time', analysis.get('source_start', 0)))
    if record and record['status'] != 'lost':
        return record['box']
    # A damaged old project must never crash painting while it is waiting for
    # re-analysis. Ask the sampler to validate each candidate instead of using
    # an unchecked persisted box or indexing a malformed record directly.
    for frame in analysis.get('frames', ()):
        if not isinstance(frame, dict) or frame.get('status') not in ('tracked', 'manual'):
            continue
        record = sample(analysis, frame.get('time'))
        if record and record['status'] != 'lost':
            return record['box']
    return [0, 0, 1, 1]


def effective_crop(item, media, source_time, base_crop=None):
    """A full-source viewport, resampled into the clip's fixed crop geometry.

    Width/height percentages refer to the original fixed crop dimensions, not
    the tracked object's dimensions. Clamping preserves the viewport dimensions
    near a source edge. This mode has no censorship semantics.
    """
    from .model import Crop
    base = (base_crop if base_crop is not None else item.crop).clamped()
    raw = follow_effect(item)
    if not raw or _vision_conflict(item):
        return base
    try:
        effect = validate(raw)
    except (ValueError, TypeError):
        return base
    record = _sample(effect, media, item, source_time)
    if not record:
        return base
    if record['status'] in ('tracked', 'manual'):
        box = record['box']
    elif effect['loss_policy'] == 'Hold':
        box = _held_box(effect['analysis'], source_time)
        if box is None:
            return base
    else:
        return Crop() if effect['loss_policy'] == 'Full frame' else base
    width = min(1., max(.02, base.width * effect['width'] / 100))
    height = min(1., max(.02, base.height * effect['height'] / 100))
    cx = box[0] + box[2] / 2 + effect['offset_x'] / max(1, media.width)
    cy = box[1] + box[3] / 2 + effect['offset_y'] / max(1, media.height)
    return Crop(min(1-width, max(0., cx-width/2)), min(1-height, max(0., cy-height/2)), width, height)


def crop_source(image, item, media, source_time, base_crop=None, output_size=None):
    """Extract fractional source pixels into a stable, source-crop-sized image.

    Qt performs the same smooth fractional sampling in the viewer and cached
    export. Following changes content inside the media rectangle, never its
    timeline transforms, scale, crop metadata or output dimensions.
    """
    if image.isNull():
        return image
    base = (base_crop if base_crop is not None else item.crop).clamped()
    viewport = effective_crop(item, media, source_time, base)
    width, height = output_size or (max(1, round(image.width()*base.width)), max(1, round(image.height()*base.height)))
    width, height = max(1, int(width)), max(1, int(height))
    result = QImage(width, height, QImage.Format_RGBA8888); result.fill(Qt.transparent)
    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawImage(QRectF(0, 0, width, height), image,
                          QRectF(viewport.x*image.width(), viewport.y*image.height(),
                                 viewport.width*image.width(), viewport.height*image.height()))
    finally:
        painter.end()
    return result


def apply(image, item, media, source_time, crop=None):
    """Paint into cropped source pixels; subsequent media transforms follow it.

    A failed censor has an opaque black fallback independent of marker opacity.
    Blur/pixelation strength is an editorial choice, not an anonymity guarantee.
    """
    if image.isNull():
        return image
    effects = [effect for effect in render_effects(item) if effect.get('mode') != 'Follow Crop']
    if not effects:
        return image
    result = image.convertToFormat(QImage.Format_RGBA8888).copy()
    for raw in effects:
        censor = raw.get('mode', 'Censor Bar') in CENSOR_MODES or raw.get('mode', 'Censor Bar') not in MODES
        try:
            effect = validate(raw)
        except (ValueError, TypeError):
            if censor:
                result = _cover(result)
            continue
        record = _sample(effect, media, item, source_time)
        if not record:
            if censor:
                result = _cover(result)
            continue
        if record['status'] == 'lost':
            if censor and (effect['loss_policy'] == 'Full frame' or not effect['loss_reviewed']):
                result = _cover(result); continue
            box = _held_box(effect['analysis'], source_time) if effect['loss_policy'] == 'Hold' else None
            if not box:
                # Holding with no earlier reliable box cannot protect anything.
                if censor and effect['loss_policy'] == 'Hold':
                    result = _cover(result)
                continue
        else:
            box = record['box']
        _paint(result, effect, media, crop or item.crop.clamped(), box)
    return result


def _paint(image, effect, media, crop, box):
    width, height = image.width(), image.height()
    sx = width / max(1., media.width * crop.width)
    sy = height / max(1., media.height * crop.height)
    unit = math.sqrt(sx * sy)
    x, y, bw, bh = box
    cx = (x + bw / 2 - crop.x) / crop.width * width + effect['offset_x'] * sx
    cy = (y + bh / 2 - crop.y) / crop.height * height + effect['offset_y'] * sy
    if not effect['follow_scale']:
        _, _, bw, bh = _reference_box(effect['analysis'])
    rw = bw / crop.width * width * effect['width'] / 100 + effect['padding'] * sx * 2
    rh = bh / crop.height * height * effect['height'] / 100 + effect['padding'] * sy * 2
    rect = QRectF(-rw / 2, -rh / 2, rw, rh)
    transform = QTransform(); transform.translate(cx, cy); transform.rotate(effect['rotation'])
    path = QPainterPath(); path.addRoundedRect(rect, effect['radius'] * unit, effect['radius'] * unit)
    region = transform.map(path)
    mode = effect['mode']
    if mode in ('Blur', 'Pixelate'):
        bounds = region.boundingRect().toAlignedRect().intersected(image.rect())
        if bounds.isEmpty():
            return
        original = image.copy(bounds)
        if mode == 'Blur':
            from .visuals import blur_image
            filtered = blur_image(original, effect['blur'] * unit, effect['blur'] * unit)
        else:
            step = max(2, effect['pixel_size'] * unit)
            filtered = original.scaled(max(1, round(bounds.width() / step)), max(1, round(bounds.height() / step)),
                                       Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            filtered = filtered.scaled(bounds.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
        painter = QPainter(image)
        try:
            painter.setOpacity(effect['opacity'] / 100)
            painter.setClipPath(region); painter.drawImage(bounds.topLeft(), filtered)
        finally:
            painter.end()
        return
    painter = QPainter(image)
    try:
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        painter.setOpacity(effect['opacity'] / 100); painter.setTransform(transform)
        color = QColor(effect['color']); pen = QPen(color, effect['stroke_width'] * unit)
        pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen if effect['stroke_width'] else Qt.NoPen)
        painter.setBrush(color if effect['fill'] else Qt.NoBrush)
        if mode == 'Censor Bar':
            painter.setPen(Qt.NoPen); painter.setBrush(color); painter.drawPath(path)
        elif mode == 'Circle':
            painter.drawEllipse(rect)
        elif mode == 'Rectangle':
            painter.drawPath(path)
        elif mode == 'Arrow':
            length = effect['arrow_length'] * unit; head = min(length, effect['arrow_head'] * unit)
            painter.drawLine(QPointF(-length, 0), QPointF(-head * .65, 0))
            painter.setPen(Qt.NoPen); painter.setBrush(color)
            painter.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(-head, -head * .55), QPointF(-head, head * .55)]))
        elif mode == 'Label':
            font = QFont(effect['font']); font.setPixelSize(max(4, round(effect['font_size'] * unit)))
            font.setBold(True); painter.setFont(font); metrics = QFontMetricsF(font)
            text = effect['label']; padding = effect['label_padding'] * unit
            label_rect = QRectF(-metrics.horizontalAdvance(text) / 2 - padding,
                                -metrics.height() / 2 - padding,
                                metrics.horizontalAdvance(text) + padding * 2, metrics.height() + padding * 2)
            painter.setPen(Qt.NoPen); painter.setBrush(QColor(effect['label_background']))
            painter.drawRoundedRect(label_rect, effect['radius'] * unit, effect['radius'] * unit)
            painter.setPen(QColor(effect['label_color']))
            painter.drawText(label_rect.adjusted(padding, padding, -padding, -padding), Qt.AlignCenter, text)
        elif mode == 'Image' and _usable_image(effect['image']):
            stamp = _images.load(effect['image'])
            if not stamp.isNull():
                factor = min(rect.width() / stamp.width(), rect.height() / stamp.height())
                painter.drawImage(QRectF(-stamp.width() * factor / 2, -stamp.height() * factor / 2,
                                         stamp.width() * factor, stamp.height() * factor), stamp)
    finally:
        painter.end()


def prune(directory, used=(), budget=1024**3):
    """Bound this feature's regenerable caches, preserving the active export."""
    directory = Path(directory)
    if directory.is_symlink():
        return
    entries = []
    for path in directory.glob('track-*.mkv'):
        try:
            if path.is_symlink():
                continue
            stat = path.stat(); entries.append((stat.st_mtime_ns, stat.st_size, path))
        except OSError:
            continue
    total = sum(size for _, size, _ in entries)
    for _, size, path in sorted(entries):
        if total <= budget:
            break
        if str(path) not in used:
            try:
                path.unlink(); total -= size
            except OSError:
                pass
