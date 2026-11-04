"""Per-frame description of a motion composition for the GPU renderer (assets/qml/GpuMotion.qml).

Python only evaluates keyframes and layout here (a few hundred numbers per frame). All pixels are drawn by the GPU:
paths, text outlines, strokes, gradients, blur, glow, blend modes, bloom and the grade run in Qt Quick shaders.
"""
import math
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QTransform
from . import motion as M
from . import motion_fx as fx

PARTICLE_CAP = 700


_TEXT_SVG = {}


def text_svg(path):
    """Text outline -> SVG path data with overlaps and degenerate cusps resolved. Some Windows font outlines (e.g. Newsreader's
    'g') contain spikes that the Direct3D curve renderer silently drops; simplified() makes every glyph a clean set of contours.
    Cached by the raw outline, so animating text costs no extra work per frame."""
    key = svg(path); value = _TEXT_SVG.get(key)
    if value is None:
        if len(_TEXT_SVG) > 4096: _TEXT_SVG.clear()
        value = _TEXT_SVG[key] = svg(path.simplified())
    return value


def svg(path):
    """QPainterPath -> SVG path data (cubics and lines; Qt stores curves as three elements)."""
    out = []; n = 0; count = path.elementCount()
    while n < count:
        e = path.elementAt(n)
        if e.isMoveTo():
            out.append('M%.2f %.2f' % (e.x, e.y)); n += 1
        elif e.isLineTo():
            out.append('L%.2f %.2f' % (e.x, e.y)); n += 1
        else:
            if n + 2 >= count: break
            a, b = path.elementAt(n + 1), path.elementAt(n + 2)
            out.append('C%.2f %.2f %.2f %.2f %.2f %.2f' % (e.x, e.y, a.x, a.y, b.x, b.y)); n += 3
    return ''.join(out)


def matrix(t):
    return [t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy()]


def brush(node, w, h):
    gradient = node.get('gradient'); fill = node.get('fill', '#ffffff')
    if isinstance(gradient, list) and len(gradient) >= 2:
        stops = node.get('gradient_stops') or [n / (len(gradient) - 1) for n in range(len(gradient))]
        out = {'type': node.get('gradient_type', 'linear'), 'stops': [[s, QColor(c).name(QColor.HexArgb)] for s, c in zip(stops, gradient)]}
        if out['type'] == 'radial':
            cx, cy = node.get('gradient_center', [.5, .5]); out.update(cx=(cx - .5) * w, cy=(cy - .5) * w, r=max(1, w / 2 * node.get('gradient_radius', 1)), squash=h / max(1, w))
        else:
            a = math.radians(node.get('gradient_angle', 0)); out.update(x1=-math.cos(a) * w / 2, y1=-math.sin(a) * h / 2, x2=math.cos(a) * w / 2, y2=math.sin(a) * h / 2)
        return out
    return None if fill == 'none' else {'type': 'solid', 'color': QColor(fill).name(QColor.HexArgb)}


def stroke_of(node, t):
    s = node.get('stroke', 'none'); width = max(0, M.curve(node, 'stroke_width', t))
    if s == 'none' or width <= 0: return None
    out = {'color': QColor(s).name(QColor.HexArgb), 'width': width, 'cap': node.get('cap', 'round'), 'join': node.get('join', 'round')}
    if node.get('dash'): out.update(dash=list(node['dash']), offset=M.curve(node, 'dash_offset', t))
    return out


def shadowed(item, node, base, opacity, out):
    """Append item, wrapped in a GPU drop-shadow layer when the layer has an enabled shadow (shapes, images, video)."""
    sh = node.get('shadow', {})
    if not (sh.get('enabled', False) and sh.get('opacity', 20)): out.append(item); return
    lin = base['matrix']; dx = sh.get('x', 0) * lin[0] + sh.get('y', 8) * lin[2]; dy = sh.get('x', 0) * lin[1] + sh.get('y', 8) * lin[3]
    sk = math.sqrt(abs(lin[0] * lin[3] - lin[1] * lin[2]))
    out.append({'k': 'layer', 'opacity': opacity, 'blend': 'normal', 'blur': 0, 'items': [dict(item, opacity=1.)],
                'shadow': {'color': QColor(sh.get('color', '#000000')).name(), 'opacity': sh.get('opacity', 20) / 100., 'blur': sh.get('blur', 20) * sk, 'dx': dx, 'dy': dy}})


def frame(scene, t, size=None, fps=60):
    """Return {canvas, background, items, post, unsupported}. Items are in paint order with world matrices."""
    canvas = scene.get('canvas', [1080, 1920]); nodes = scene.get('nodes', []); by_id = {n['id']: n for n in nodes}
    children = {}
    for n in nodes: children.setdefault(n.get('parent', ''), []).append(n)
    items = []; unsupported = set(); k = (size[0] / max(1, canvas[0])) if size else 1.; base_m = QTransform.fromScale(k, k)

    def emit(node, m, opacity, out):
        w = M.curve(node, 'width', t); h = M.curve(node, 'height', t); kind = node['kind']
        fill = brush(node, w, h); stroke = stroke_of(node, t)
        base = {'matrix': matrix(m), 'opacity': opacity}
        trail = node.get('trail')
        if trail: out.extend(trail_items(node, m, opacity))
        if kind == 'text':
            mode = node.get('text_mode', 'none')
            if mode == 'typewriter':
                typewriter(node, m, opacity, fill, stroke, out); return
            if mode == 'rolling':
                rolling(node, m, opacity, fill, stroke, out); return
            text = node.get('text', '')
            if mode == 'counter':
                from .motion_text import counter_text
                text = counter_text(node, t); mode = 'none'
            static = mode == 'none'; build = 'character' if (static and node.get('runs')) else mode
            parts = M.text_parts(text, node.get('font', 'Arial'), M.curve(node, 'font_size', t), bool(node.get('bold', True)), build, M.curve(node, 'tracking', t), node.get('text_align', 'center'), bool(node.get('italic', False)), M.run_styles(node))
            fills = M.token_fills(node, text, build, len(parts)); duration = max(.001, node.get('entry_duration', .4)); stagger = max(0, node.get('stagger', .04)); local = t - node.get('start', 0)
            blur_in = node.get('entry_blur', 0) * M.curve(node, 'entry_blur_amount', t)
            from .easing import ease
            for n, part in enumerate(parts):
                q = 1. if static else max(0, min(1, (local - n * stagger) / duration))
                if q <= 0: continue
                amount = ease(q, node.get('entry_easing', 'Ease Out'), node.get('entry_bezier'))
                c = part.boundingRect().center(); pm = QTransform(m); pm.translate(c.x(), c.y() + node.get('entry_y', 60) * (1 - amount)); pm.rotate(node.get('entry_rotation', 0) * (1 - amount))
                s = node.get('entry_scale', .85) + (1 - node.get('entry_scale', .85)) * amount; pm.scale(s, s); pm.translate(-c.x(), -c.y())
                f = {'type': 'solid', 'color': QColor(fills[n]).name(QColor.HexArgb)} if fills else fill
                if node.get('entry_color') and not static and f and f.get('type') == 'solid':
                    a, b = QColor(node['entry_color']), QColor(f['color'])
                    mix = lambda x, y: x + (y - x) * amount
                    f = {'type': 'solid', 'color': QColor.fromRgbF(mix(a.redF(), b.redF()), mix(a.greenF(), b.greenF()), mix(a.blueF(), b.blueF()), mix(a.alphaF(), b.alphaF())).name(QColor.HexArgb)}
                out.append({'k': 'path', 'd': text_svg(part), 'matrix': matrix(pm), 'opacity': opacity * q, 'fill': f, 'stroke': stroke, 'blur': blur_in * (1 - amount) if not static else 0})
        elif kind == 'image':
            shadowed(dict(base, k='image', source=node.get('source', ''), w=max(.01, w), h=max(.01, h), fit=node.get('image_fit', 'stretch')), node, base, opacity, out)
        elif kind == 'video':
            from .motion_video import source_time
            shadowed(dict(base, k='video', source=node.get('source', ''), t=source_time(node, t), w=max(.01, w), h=max(.01, h), fit=node.get('image_fit', 'cover')), node, base, opacity, out)
        elif kind == 'emitter':
            out.extend(particles(node, m, opacity))
        elif kind != 'group':
            shape = M.geometry(node, t)
            if fill and fill['type'] == 'radial' and abs(fill['squash'] - 1) > 1e-3:
                q = fill['squash']; shape = QTransform.fromScale(1, 1 / q).map(shape); mm = QTransform(m); mm.scale(1, q); base = dict(base, matrix=matrix(mm))
            item = dict(base, k='path', d=svg(shape), fill=fill, stroke=stroke)
            if fill or stroke: shadowed(item, node, base, opacity, out)
            else: out.append(item)

    def typewriter(node, m, opacity, fill, stroke, out):
        from PySide6.QtGui import QFont, QFontMetricsF
        from .motion_text import revealed_text
        size = M.curve(node, 'font_size', t); font = QFont(node.get('font', 'Arial')); font.setPixelSize(max(1, round(size))); font.setHintingPreference(QFont.PreferNoHinting); font.setItalic(bool(node.get('italic', False))); font.setBold(bool(node.get('bold', True))); font.setLetterSpacing(QFont.AbsoluteSpacing, M.curve(node, 'tracking', t))
        metrics = QFontMetricsF(font); complete = node.get('text', '').split('\n'); visible = revealed_text(node, t).split('\n')
        baseline = metrics.ascent() - len(complete) * metrics.height() / 2; alignment = node.get('text_align', 'center'); caret = QPointF(); path = QPainterPath()
        for row, line in enumerate(visible):
            width = metrics.horizontalAdvance(complete[row]); x = 0 if alignment == 'left' else -width if alignment == 'right' else -width / 2
            y = baseline + row * metrics.height(); path.addText(QPointF(x, y), font, line); caret = QPointF(x + metrics.horizontalAdvance(line) + max(2, size * .05), y)
        local = max(0, t - node.get('start', 0)); period = node.get('caret_period', .8)
        if node.get('caret', False) and local % period < period * .5: path.addRect(caret.x(), caret.y() - metrics.ascent() * .9, max(1, size * .045), metrics.ascent())
        out.append({'k': 'path', 'd': text_svg(path), 'matrix': matrix(m), 'opacity': opacity, 'fill': fill, 'stroke': stroke})

    def rolling(node, m, opacity, fill, stroke, out):
        from .motion_text import _rolling_layout
        from .easing import ease
        text = node.get('text', ''); size = M.curve(node, 'font_size', t); local = max(0, t - node.get('start', 0)); duration = max(.001, node.get('entry_duration', .9))
        if local >= duration:
            for part in M.text_parts(text, node.get('font', 'Arial'), size, bool(node.get('bold', True)), 'none', M.curve(node, 'tracking', t), node.get('text_align', 'center')):
                out.append({'k': 'path', 'd': text_svg(part), 'matrix': matrix(m), 'opacity': opacity, 'fill': fill, 'stroke': stroke})
            return
        fixed, cells, digits, height, ascent = _rolling_layout(text, node.get('font', 'Arial'), size, bool(node.get('bold', True)), M.curve(node, 'tracking', t), node.get('text_align', 'center'))
        out.append({'k': 'path', 'd': text_svg(fixed), 'matrix': matrix(m), 'opacity': opacity, 'fill': fill, 'stroke': stroke})
        progress = ease(min(1, local / duration), node.get('entry_easing', 'Ease Out'), node.get('entry_bezier'))
        for digit, x, y, width in cells:
            travel = (10 + digit) * progress; current = math.floor(travel); fraction = travel - current
            a = QTransform(); a.translate(0, -fraction * height); b = QTransform(); b.translate(0, (1 - fraction) * height)
            out.append({'k': 'clip', 'matrix': matrix(m), 'opacity': opacity, 'rect': [x - 1, y - ascent, width + 2, height], 'items': [
                {'k': 'path', 'd': text_svg(digits[current % 10]), 'matrix': matrix(QTransform.fromTranslate(x, y - fraction * height)), 'opacity': 1., 'fill': fill, 'stroke': stroke},
                {'k': 'path', 'd': text_svg(digits[(current + 1) % 10]), 'matrix': matrix(QTransform.fromTranslate(x, y + (1 - fraction) * height)), 'opacity': 1., 'fill': fill, 'stroke': stroke}]})

    def trail_items(node, m, opacity):
        r = node['trail']; inverse, ok = m.inverted()
        if not ok: return []
        n = r['samples']; pts = []
        for i in range(n + 1):
            tt = max(0, t - r['length'] * i / n); x, y, _ = M.node_origin(node, tt, by_id); parent = by_id.get(node.get('parent', ''))
            pm = M.node_matrix(parent, tt, by_id) if parent else QTransform()
            pts.append(inverse.map(pm.map(QPointF(x, y))))
        base = r.get('color') or (node.get('fill') if node.get('fill', 'none') != 'none' else node.get('stroke', '#ffffff'))
        segs = []
        for i in range(n):
            u = i / n; c = QColor(base); c.setAlphaF(max(0, min(1, (1 - u) ** r['fade'])))
            segs.append([pts[i].x(), pts[i].y(), pts[i + 1].x(), pts[i + 1].y(), c.name(QColor.HexArgb), max(.3, r['width'] * (1 - u) ** r['taper'])])
        return [{'k': 'trail', 'matrix': matrix(m), 'opacity': opacity, 'segments': segs, 'additive': bool(r['additive'])}]

    def particles(node, m, opacity):
        e = node['emitter']; start = node.get('start', 0); table = fx._table(e['seed'], 20000); births = []; lmax = e['life'][1]
        if e['rate'] > 0:
            last = min(t, start + e['spawn_end']); first = max(0, math.ceil((t - lmax - start) * e['rate']))
            for k in range(first, int((last - start) * e['rate']) + 1): births.append((k, start + k / e['rate']))
        for index, burst in enumerate(e['bursts']):
            if burst['time'] <= t <= burst['time'] + lmax:
                for j in range(burst['count']): births.append((10000 * (index + 1) + j, burst['time']))
        if len(births) > PARTICLE_CAP: births = births[-PARTICLE_CAP:]
        out = []
        for k, tb in births:
            tau = t - tb
            if tau < 0: continue
            r = table[k % 20000]; life = e['life'][0] + (e['life'][1] - e['life'][0]) * r[2]
            if tau >= life: continue
            u = tau / life; ang = math.radians(e['angle'] + (r[0] - .5) * e['spread']); sp = e['speed'][0] + (e['speed'][1] - e['speed'][0]) * r[1]
            d = e['drag']; td = (1 - math.exp(-d * tau)) / d if d > 0 else tau; vx = math.cos(ang) * sp; vy = math.sin(ang) * sp
            ox = oy = 0.
            if e['radius']: ox = math.cos(r[4] * 6.283) * e['radius'] * r[5]; oy = math.sin(r[4] * 6.283) * e['radius'] * r[5]
            x = ox + vx * td; y = oy + vy * td + .5 * e['gravity'] * tau * tau
            ex = math.exp(-d * tau); cx = vx * ex; cy = vy * ex + e['gravity'] * tau
            size = (e['size'][0] + (e['size'][1] - e['size'][0]) * u) * (.6 + .8 * r[3]); alpha = fx.clamp((1 - u) ** e['fade'], 0, 1)
            c = fx._ramp(e['colors'], (u + r[4] * .2) if len(e['colors']) > 1 else 0); c.setAlphaF(alpha)
            out.append([float(x), float(y), float(cx * e['trail']), float(cy * e['trail']), float(size), c.name(QColor.HexArgb), e['shape']])
        return [{'k': 'particles', 'matrix': matrix(m), 'opacity': opacity, 'additive': bool(e['additive']), 'list': out}] if out else []

    def walk(node, parent_m, parent_opacity, root, sink):
        if not node.get('visible', True) or not node.get('start', 0) <= t < node.get('end', 1e5): return
        m = QTransform(parent_m)
        if root:
            cam = fx.camera_transform(scene, t, node.get('depth', 1.), canvas)
            if cam: m = cam * m
        x, y, extra = M.node_origin(node, t, by_id); m.translate(x, y)
        s = node.get('stretch')
        if s:
            h = 1 / 240; x0, y0, _ = M.node_origin(node, t - h, by_id); x1, y1, _ = M.node_origin(node, t + h, by_id)
            vx = (x1 - x0) / (2 * h); vy = (y1 - y0) / (2 * h); f = 1 + min(s['max'], s['amount'] * math.hypot(vx, vy))
            if f > 1.001:
                ang = math.degrees(math.atan2(vy, vx)); m.rotate(ang); m.scale(f, 1 / math.sqrt(f) if s['squash'] else 1); m.rotate(-ang)
        m.rotate(M.curve(node, 'rotation', t) + extra); m.scale(M.curve(node, 'scale', t), M.curve(node, 'scale_y', t))
        rx = M.curve(node, 'rotate_x', t); ry = M.curve(node, 'rotate_y', t)
        if rx or ry:
            tilt = QTransform(); tilt.rotate(rx, 0); tilt.rotate(ry, 1); m = tilt * m
        m.translate(-node.get('anchor_x', 0), -node.get('anchor_y', 0))
        opacity = parent_opacity * max(0, min(1, M.curve(node, 'opacity', t) / 100))
        group = []; blur = M.curve(node, 'blur', t); glow = M.curve(node, 'glow_amount', t); g = node.get('glow')
        glowing = bool(g and g.get('enabled', True) and g.get('intensity', 1) > 0 and glow > 0)
        mask = node.get('mask')
        if mask:
            pass
            mt = QTransform(); mt.translate(M.curve(mask, 'x', t), M.curve(mask, 'y', t)); mt.rotate(M.curve(mask, 'rotation', t)); mt.scale(M.curve(mask, 'scale', t), M.curve(mask, 'scale_y', t))
        dblur = (M.curve(node, 'blur_x', t), M.curve(node, 'blur_y', t))
        layered = bool(blur > .05 or glowing or mask or node.get('blend', 'normal') != 'normal' or dblur[0] > .05 or dblur[1] > .05); inner = 1. if layered else opacity
        emit(node, m, inner, group)
        for child in children.get(node['id'], []): walk(child, m, inner, False, group)
        if not group: return
        if layered:
            layer = {'k': 'layer', 'opacity': opacity, 'blend': node.get('blend', 'normal'), 'blur': blur, 'items': group}
            if glowing: layer['glow'] = {'radius': g['radius'], 'intensity': g['intensity'] * glow, 'layers': g.get('layers', 2), 'color': g.get('color')}
            if mask: layer['mask'] = {'d': svg((mt * m).map(M.geometry(mask, t))), 'invert': bool(mask.get('invert')), 'feather': mask.get('feather', 0)}
            if dblur[0] > .05 or dblur[1] > .05: layer = {'k': 'dblur', 'dx': dblur[0], 'dy': dblur[1], 'items': [layer]}
            sink.append(layer)
        else: sink.extend(group)

    # Root layers
    for node in children.get('', []): walk(node, base_m, 1., True, items)
    floor = scene.get('floor')
    post = fx.post_values(scene, t)
    if post:
        a = QColor(post['tint']); b = QColor(post['tint_to']); mix = fx.clamp(post['tint_mix'], 0, 1)
        post['tint_rgb'] = QColor.fromRgbF(a.redF() + (b.redF() - a.redF()) * mix, a.greenF() + (b.greenF() - a.greenF()) * mix, a.blueF() + (b.blueF() - a.blueF()) * mix).name()
        post = {n: v for n, v in post.items() if isinstance(v, (int, float, str))}
    bg = scene.get('background')
    return {'canvas': list(canvas), 'seed': (int(round(t * max(1, fps))) * 7919 % 9973) / 9973., 'background': bg, 'items': items, 'post': post, 'floor': floor if floor and floor.get('enabled', True) else None, 'unsupported': sorted(unsupported)}
