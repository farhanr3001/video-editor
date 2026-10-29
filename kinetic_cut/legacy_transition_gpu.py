"""Crop-local GPU descriptors for the original 25 QPainter transitions.

The original compositor interpolates one destination rectangle, then performs
the transition *inside* that rectangle.  It does not transform two full-canvas
images independently.  Sampling matrices here reproduce that outer painter
transform, while the native shader mirrors the inner draw operations.
"""
import copy
import math

NAMES = (
    'Cross Dissolve', 'Dip to Color / White Flash', 'Dip to Black',
    'Blur Dissolve', 'Additive Dissolve', 'Smooth Dissolve',
    'Wipe Left', 'Wipe Right', 'Wipe Up', 'Wipe Down', 'Split Wipe',
    'Clock Wipe', 'Push Left (Swipe)', 'Push Right (Swipe)',
    'Push Up (Swipe)', 'Push Down (Swipe)', 'Slide In', 'Slide Out',
    'Zoom In (Whoosh)', 'Whip Pan Transition', 'Digital Glitch',
    'RGB Split Glitch', 'Film Roll', 'Lens Flare Flash', 'Pixelate',
)


def descriptor(transition):
    from PySide6.QtGui import QColor
    props = transition.properties or {}
    color = QColor(props.get('color', '#ffffff' if 'White' in transition.name else '#000000'))
    return dict(mode=25 + NAMES.index(transition.name), legacy=True,
                params=[color.redF(), color.greenF(), color.blueF(), color.alphaF()],
                easing=props.get('easing', 'Ease In-Out'))


def _evaluated(project, item, at):
    if not item:
        return None
    from .keyframes import evaluated
    from .visual_fx import evaluate_visual_fx, apply_visual_fx_to_transform
    elapsed = max(0., min(item.duration, at - item.start))
    current = evaluated(item, elapsed)
    fx = evaluate_visual_fx(current, elapsed, project.settings.width, project.settings.height)
    if fx.is_active:
        current = copy.copy(current)
        current.transform = copy.copy(current.transform)
        apply_visual_fx_to_transform(current.transform, fx)
    return current


def _target(project, item):
    """The floating-point PreviewCanvas._layer_rect, without a widget/image."""
    from PySide6.QtCore import QRectF
    if not item:
        return None
    width, height = project.settings.width, project.settings.height
    if item.role == 'background':
        return QRectF(0, 0, width, height)
    media = project.media_by_id(item.media_id)
    if not media or not media.width or not media.height:
        raise ValueError('transition source dimensions are unavailable')
    crop, tx = item.crop.clamped(), item.transform
    full_w, full_h = max(1., media.width), max(1., media.height)
    input_scale = max(width / full_w, height / full_h)
    factor = .92 if item.role == 'facecam' else 1.
    w = full_w * crop.width * input_scale * factor * tx.scale
    h = full_h * crop.height * input_scale * factor * tx.effective_scale_y
    ax, ay = tx.anchor_x * (tx.scale - 1), tx.anchor_y * (tx.effective_scale_y - 1)
    if item.retain_image_position:
        ax -= (crop.x + crop.width / 2 - .5) * w / crop.width
        ay -= (crop.y + crop.height / 2 - .5) * h / crop.height
    return QRectF(tx.x * width - w / 2 - ax, tx.y * height - h / 2 - ay, w, h)


def sample_geometry(project, transition, at):
    """Return [box4, rotation, opacity, inverse-homography9, circle].

    Rectangle/transform/opacity interpolation uses raw progress.  Easing belongs
    solely to the inner transition shader, exactly as in the preview.  The
    inverse homography also includes the reference endpoint's flips.
    """
    from PySide6.QtGui import QTransform
    from PySide6.QtCore import Qt, QPointF, QRectF
    a = _evaluated(project, project.item_by_id(transition.left_item_id), at) if transition.left_item_id else None
    b = _evaluated(project, project.item_by_id(transition.right_item_id), at) if transition.right_item_id else None
    p = transition.progress(at)
    ref = a if a and (p < .5 or not b) else b or a
    if not ref:
        raise ValueError('transition has no available endpoint')
    ra, rb = _target(project, a), _target(project, b)
    if ra is not None and rb is not None:
        rect = QRectF(*(x * (1 - p) + y * p for x, y in zip(
            (ra.x(), ra.y(), ra.width(), ra.height()),
            (rb.x(), rb.y(), rb.width(), rb.height()))))
    else:
        rect = ra or rb
    width, height = rect.width(), rect.height()
    if width <= 0 or height <= 0:
        raise ValueError('transition has singular target geometry')
    def lerp(name):
        return getattr(a.transform if a else ref.transform, name) * (1 - p) + getattr(b.transform if b else ref.transform, name) * p
    matrix = QTransform()
    if ref.role == 'background':
        rect = QRectF(0, 0, project.settings.width, project.settings.height)
        width, height = rect.width(), rect.height()
        matrix.translate(width / 2, height / 2)
        opacity, angle, circle = 1., 0., False
    else:
        angle = lerp('rotation')
        anchor = QPointF(lerp('anchor_x'), lerp('anchor_y'))
        pivot = rect.center() + anchor
        matrix.translate(pivot.x(), pivot.y())
        matrix.rotate(angle)
        matrix.translate(-anchor.x(), -anchor.y())
        matrix.rotate(lerp('pitch'), Qt.XAxis)
        matrix.rotate(lerp('yaw'), Qt.YAxis)
        matrix.scale(-1 if ref.transform.flip_horizontal else 1,
                     -1 if ref.transform.flip_vertical else 1)
        opacity = ((a.opacity if a else 100.) * (1 - p) + (b.opacity if b else 100.) * p) / 100.
        circle = ref.transform.shape == 'circle'
    inverse, valid = matrix.inverted()
    if not valid:
        raise ValueError('transition has singular perspective geometry')
    x, y, z = inverse.m13(), inverse.m23(), inverse.m33()
    homography = [inverse.m11() / width + .5 * x, inverse.m21() / width + .5 * y, inverse.dx() / width + .5 * z,
                  inverse.m12() / height + .5 * x, inverse.m22() / height + .5 * y, inverse.dy() / height + .5 * z,
                  x, y, z]
    return [rect.x(), rect.y(), width, height, math.radians(angle), max(0., min(1., opacity)), *homography, int(circle)]


def geometry(project, transition):
    fps = project.settings.fps
    first = math.ceil(transition.start * fps - 1e-7)
    last = math.ceil(transition.end * fps - 1e-7)
    if last - first > 100000:
        raise ValueError('large legacy transition geometry stream')
    return dict(legacy_first_frame=first,
                legacy_geometry=[sample_geometry(project, transition, n / fps) for n in range(first, last)])


def configure_layers(project, layers, error):
    """Attach native local pairs after ordinary endpoint recipes have succeeded."""
    transitions = [t for t in project.transitions if t.name in NAMES and t.track in project.video_tracks
                   and project.track_states.get(t.track, {}).get('visible', True)]
    if not transitions:
        return layers
    by_id = {layer['id']: layer for layer in layers}
    pairs = []
    for trans in transitions:
        if any(t is not trans and t.track == trans.track and t.start < trans.end and t.end > trans.start for t in project.transitions):
            raise error('overlapping transition windows')
        originals = [project.item_by_id(identifier) if identifier else None for identifier in (trans.left_item_id, trans.right_item_id)]
        try:
            data = dict(descriptor(trans), **geometry(project, trans))
        except ValueError as exc:
            raise error(str(exc)) from exc
        data.update(has_a=bool(originals[0]), has_b=bool(originals[1]))
        for side, (identifier, original) in enumerate(zip((trans.left_item_id, trans.right_item_id), originals)):
            if original and (original.muted or original.track != trans.track):
                raise error('muted or mismatched transition endpoint')
            source = by_id.get(identifier)
            if identifier and not source:
                raise error('transition endpoint requires exact preparation')
            layer = copy.deepcopy(source) if source else dict(path='', empty=True, still=True, cpu=False, size=[2, 2], crop=[0, 0, 1, 1],
                box=[0, 0, project.settings.width, project.settings.height], opacity=1., operations=[], clock='', in_point=0., speed=1.)
            if original:
                media = project.media_by_id(original.media_id)
                if source['path'] != media.path:
                    raise error('legacy transition endpoint requires unplaced pixels')
                # The source crop is unflipped.  The reference endpoint controls
                # one shared flip after interpolation, not each source crop.
                crop = original.crop.clamped()
                if original.role != 'background':
                    layer['crop'] = [crop.x, crop.y, crop.width, crop.height]
                operations = []
                for op in layer.get('operations', []):
                    if op.get('kind') == 'mask' and op.get('circle'):
                        if not op.get('softness'):
                            continue
                        op = dict(op, circle=False)
                    operations.append(op)
                layer['operations'] = operations
                source.setdefault('skip_ranges', []).append([trans.start, trans.end])
            layer.update(id='__transition_' + trans.id + '_' + str(side), track=trans.track, start=trans.start, end=trans.end,
                transitions=[], skip_ranges=[], fade_in=0., fade_out=0.,
                pair=dict(id=trans.id, side=side, start=trans.start, duration=trans.duration, **data),
                source_origin=original.start if original else trans.start, source_in=source['in_point'] if source else 0.,
                source_duration=original.duration if original else trans.duration, source_speed=original.speed if original else 1.,
                effect_origin=original.start if original else trans.start)
            pairs.append(layer)
    order = {track: n for n, track in enumerate(project.video_tracks)}
    return sorted([*layers, *pairs], key=lambda v: (order.get(v.get('track'), 0), bool(v.get('pair')),
                  v.get('pair', {}).get('start', v['start']), v.get('pair', {}).get('side', 0)))
