"""Visual graphics rendering engine for shapes, timers, callouts and overlays."""
from __future__ import annotations

import copy
import math
from typing import Any
from PySide6.QtCore import QPointF, QRectF, Qt, QSize
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter,
    QPainterPath, QPen, QPolygonF, QTransform
)

# Catalog display names mapped to metadata
GRAPHICS_CATALOG: dict[str, dict[str, Any]] = {
    "Circle": {"kind": "circle", "default_duration": 2.0},
    "Pointing Arrow": {"kind": "arrow", "default_duration": 2.0},
    "Square": {"kind": "square", "default_duration": 2.0},
    "Rectangle": {"kind": "rectangle", "default_duration": 2.0},
    "Timer / Countdown": {"kind": "timer", "default_duration": 10.0},
    "Speech Bubble / Quote Card": {"kind": "speech_bubble", "default_duration": 3.0},
    "Progress Bar": {"kind": "progress_bar", "default_duration": 5.0},
    "Callout Badge": {"kind": "callout_badge", "default_duration": 2.5},
}

DEFAULT_GRAPHIC_DATA: dict[str, dict[str, Any]] = {
    "circle": {
        "color": "#ff3b30",
        "thickness": 8.0,
        "radius": 140.0,
        "dash_style": "Solid",
        "fill_enabled": False,
        "fill_color": "#ff3b30",
        "fill_opacity": 25.0,
    },
    "arrow": {
        "color": "#ffcc00",
        "thickness": 12.0,
        "head_size": 48.0,
        "length": 220.0,
        "direction": "Right",
        "style": "Straight",
    },
    "square": {
        "color": "#00e5ff",
        "thickness": 8.0,
        "size": 260.0,
        "corner_radius": 16.0,
        "dash_style": "Solid",
        "fill_enabled": False,
        "fill_color": "#00e5ff",
        "fill_opacity": 25.0,
    },
    "rectangle": {
        "color": "#00e5ff",
        "thickness": 8.0,
        "width": 420.0,
        "height": 240.0,
        "corner_radius": 16.0,
        "dash_style": "Solid",
        "fill_enabled": False,
        "fill_color": "#00e5ff",
        "fill_opacity": 25.0,
    },
    "timer": {
        "mode": "Countdown",
        "duration": 10.0,
        "format": "MM:SS",
        "font": "Arial",
        "font_size": 72.0,
        "color": "#ffffff",
        "glow_enabled": False,
        "glow_color": "#55ffff",
        "glow_radius": 12.0,
        "glow_opacity": 55.0,
        "bg_enabled": True,
        "bg_color": "#15181f",
        "bg_opacity": 88.0,
        "corner_radius": 16.0,
        "border_color": "#3d8cff",
        "border_width": 2.5,
    },
    "speech_bubble": {
        "text": "Your quote or callout here!",
        "font": "Segoe UI",
        "font_size": 42.0,
        "color": "#ffffff",
        "bg_color": "#1f242d",
        "bg_opacity": 94.0,
        "border_color": "#62d0ff",
        "border_width": 2.5,
        "corner_radius": 18.0,
        "tail_position": "Bottom-Left",
        "tail_size": 28.0,
    },
    "progress_bar": {
        "bar_color": "#d9ff43",
        "bg_color": "#23262f",
        "thickness": 12.0,
        "width_percent": 88.0,
        "corner_radius": 6.0,
        "position": "Bottom",
    },
    "callout_badge": {
        "text": "WAIT FOR IT ⚠️",
        "font": "Impact",
        "font_size": 52.0,
        "color": "#11130d",
        "bg_color": "#d9ff43",
        "bg_opacity": 100.0,
        "corner_radius": 26.0,
        "border_color": "#000000",
        "border_width": 0.0,
    },
}


def default_graphic_data(kind: str) -> dict[str, Any]:
    """Return a deep copy of default settings for the given graphic type."""
    k = kind.lower()
    if "circle" in k: return copy.deepcopy(DEFAULT_GRAPHIC_DATA["circle"])
    if "arrow" in k: return copy.deepcopy(DEFAULT_GRAPHIC_DATA["arrow"])
    if "square" in k: return copy.deepcopy(DEFAULT_GRAPHIC_DATA["square"])
    if "rectangle" in k: return copy.deepcopy(DEFAULT_GRAPHIC_DATA["rectangle"])
    if "timer" in k or "countdown" in k: return copy.deepcopy(DEFAULT_GRAPHIC_DATA["timer"])
    if "speech" in k or "quote" in k: return copy.deepcopy(DEFAULT_GRAPHIC_DATA["speech_bubble"])
    if "progress" in k: return copy.deepcopy(DEFAULT_GRAPHIC_DATA["progress_bar"])
    if "badge" in k or "callout" in k: return copy.deepcopy(DEFAULT_GRAPHIC_DATA["callout_badge"])
    return copy.deepcopy(DEFAULT_GRAPHIC_DATA["circle"])


def _wrap_text(text: str, metrics: QFontMetricsF, max_width: float) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for w in words[1:]:
            cand = current + " " + w
            if metrics.horizontalAdvance(cand) <= max_width:
                current = cand
            else:
                lines.append(current)
                current = w
        lines.append(current)
    return lines or [""]


def _pen_style(name: str) -> Qt.PenStyle:
    if name == "Dashed":
        return Qt.DashLine
    if name == "Dotted":
        return Qt.DotLine
    return Qt.SolidLine


def _render_glow_text(
    painter: QPainter,
    text: str,
    font: QFont,
    rect: QRectF,
    text_color: QColor,
    glow_color: str = "#55ffff",
    glow_radius: float = 12.0,
    glow_opacity: float = 55.0,
) -> None:
    try:
        from PIL import Image, ImageFilter
        metrics = QFontMetricsF(font)
        tw = metrics.horizontalAdvance(text)
        th = metrics.height()
        pad = int(glow_radius * 2.5) + 8
        iw = max(1, int(math.ceil(tw)) + pad * 2)
        ih = max(1, int(math.ceil(th)) + pad * 2)
        img = QImage(iw, ih, QImage.Format_RGBA8888)
        img.fill(Qt.transparent)
        ip = QPainter(img)
        ip.setRenderHint(QPainter.Antialiasing, True)
        ip.setFont(font)
        ip.setPen(QColor(glow_color))
        ip.drawText(QRectF(pad, pad, tw, th), Qt.AlignCenter, text)
        ip.end()

        pixels = Image.frombytes("RGBA", (iw, ih), bytes(img.constBits()))
        alpha = pixels.getchannel("A").filter(ImageFilter.GaussianBlur(max(0.1, glow_radius)))
        glow_pil = Image.new("RGBA", (iw, ih), glow_color)
        glow_pil.putalpha(alpha)

        glow_qimg = QImage(glow_pil.tobytes(), iw, ih, QImage.Format_RGBA8888)
        painter.save()
        painter.setOpacity(painter.opacity() * (max(0.0, min(100.0, glow_opacity)) / 100.0))
        gx = rect.center().x() - iw / 2.0
        gy = rect.center().y() - ih / 2.0
        painter.drawImage(QPointF(gx, gy), glow_qimg)
        painter.restore()
    except Exception:
        pass

    painter.setFont(font)
    painter.setPen(QPen(text_color))
    painter.drawText(rect, Qt.AlignCenter, text)


def draw_graphic(
    painter: QPainter,
    project: Any,
    item: Any,
    frame_rect: QRectF,
    playhead: float
) -> QRectF:
    """Render graphic onto frame_rect with QPainter and return canvas bounding rect."""
    elapsed = playhead - item.start
    if elapsed < 0 or elapsed >= item.duration:
        return QRectF()

    # Fade calculation
    fade = min(1.0, max(0.0, elapsed / item.fade_in)) if getattr(item, "fade_in", 0) > 0 else 1.0
    if getattr(item, "fade_out", 0) > 0:
        fade *= min(1.0, max(0.0, (item.duration - elapsed) / item.fade_out))
    opacity = (getattr(item, "opacity", 100.0) / 100.0) * fade
    if opacity <= 0.001:
        return QRectF()

    data = getattr(item, "graphic_data", {}) or {}
    kind = getattr(item, "graphic_type", "circle").lower()

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setOpacity(painter.opacity() * opacity)

    # Scale factor relative to 1080p base resolution
    scale_factor = frame_rect.width() / max(1.0, float(project.settings.width))

    # Center position
    center_x = frame_rect.left() + item.transform.x * frame_rect.width()
    center_y = frame_rect.top() + item.transform.y * frame_rect.height()

    # Local transformation matrix
    transform = QTransform()
    transform.translate(center_x, center_y)
    transform.translate(item.transform.anchor_x * scale_factor,item.transform.anchor_y * scale_factor)
    transform.rotate(item.transform.rotation)
    transform.scale(item.transform.scale * scale_factor, item.transform.effective_scale_y * scale_factor)
    transform.translate(-item.transform.anchor_x,-item.transform.anchor_y)

    painter.setTransform(transform, True)

    local_bounds = QRectF()

    # 1. Circle
    if "circle" in kind:
        r = float(data.get("radius", 140.0))
        th = float(data.get("thickness", 8.0))
        col = QColor(data.get("color", "#ff3b30"))
        pen = QPen(col, th, _pen_style(data.get("dash_style", "Solid")), Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)

        if data.get("fill_enabled", False):
            fill_col = QColor(data.get("fill_color", col.name()))
            fill_col.setAlpha(round(255 * float(data.get("fill_opacity", 25.0)) / 100.0))
            painter.setBrush(QBrush(fill_col))
        else:
            painter.setBrush(Qt.NoBrush)

        local_bounds = QRectF(-r, -r, 2 * r, 2 * r)
        painter.drawEllipse(local_bounds)

    # 2. Pointing Arrow
    elif "arrow" in kind:
        length = float(data.get("length", 220.0))
        th = float(data.get("thickness", 12.0))
        hs = float(data.get("head_size", 48.0))
        col = QColor(data.get("color", "#ffcc00"))
        direction = data.get("direction", "Right")

        dir_angle = {"Right": 0, "Down": 90, "Left": 180, "Up": 270}.get(direction, 0)
        painter.rotate(dir_angle)

        half_len = length / 2.0
        shaft_end = half_len - hs * 0.75

        # Shaft
        pen = QPen(col, th, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(QPointF(-half_len, 0), QPointF(shaft_end, 0))

        # Arrowhead
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(col))
        head_poly = QPolygonF([
            QPointF(half_len, 0),
            QPointF(half_len - hs, -hs * 0.55),
            QPointF(half_len - hs * 0.7, 0),
            QPointF(half_len - hs, hs * 0.55),
        ])
        painter.drawPolygon(head_poly)

        if data.get("style") == "Double-Headed":
            painter.drawLine(QPointF(-shaft_end, 0), QPointF(shaft_end, 0))
            head_poly_left = QPolygonF([
                QPointF(-half_len, 0),
                QPointF(-half_len + hs, -hs * 0.55),
                QPointF(-half_len + hs * 0.7, 0),
                QPointF(-half_len + hs, hs * 0.55),
            ])
            painter.drawPolygon(head_poly_left)

        local_bounds = QRectF(-half_len - hs, -hs, length + 2 * hs, 2 * hs)

    # 3. Square
    elif "square" in kind:
        s = float(data.get("size", 260.0))
        th = float(data.get("thickness", 8.0))
        cr = float(data.get("corner_radius", 16.0))
        col = QColor(data.get("color", "#00e5ff"))
        pen = QPen(col, th, _pen_style(data.get("dash_style", "Solid")), Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)

        if data.get("fill_enabled", False):
            fill_col = QColor(data.get("fill_color", col.name()))
            fill_col.setAlpha(round(255 * float(data.get("fill_opacity", 25.0)) / 100.0))
            painter.setBrush(QBrush(fill_col))
        else:
            painter.setBrush(Qt.NoBrush)

        local_bounds = QRectF(-s / 2.0, -s / 2.0, s, s)
        painter.drawRoundedRect(local_bounds, cr, cr)

    # 4. Rectangle
    elif "rectangle" in kind:
        w = float(data.get("width", 420.0))
        h = float(data.get("height", 240.0))
        th = float(data.get("thickness", 8.0))
        cr = float(data.get("corner_radius", 16.0))
        col = QColor(data.get("color", "#00e5ff"))
        pen = QPen(col, th, _pen_style(data.get("dash_style", "Solid")), Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)

        if data.get("fill_enabled", False):
            fill_col = QColor(data.get("fill_color", col.name()))
            fill_col.setAlpha(round(255 * float(data.get("fill_opacity", 25.0)) / 100.0))
            painter.setBrush(QBrush(fill_col))
        else:
            painter.setBrush(Qt.NoBrush)

        local_bounds = QRectF(-w / 2.0, -h / 2.0, w, h)
        painter.drawRoundedRect(local_bounds, cr, cr)

    # 5. Timer / Countdown
    elif "timer" in kind:
        mode = data.get("mode", "Countdown")
        timer_dur = float(data.get("duration", item.duration))
        if mode == "Countdown":
            val = max(0.0, timer_dur - elapsed)
        else:
            val = max(0.0, elapsed)

        fmt = data.get("format", "MM:SS")
        if fmt == "SS":
            text = f"{int(math.ceil(val) if mode == 'Countdown' else math.floor(val))}"
        elif fmt == "MM:SS.ms":
            m = int(val) // 60
            s = int(val) % 60
            ms = int((val * 10) % 10)
            text = f"{m:02d}:{s:02d}.{ms}"
        else:  # MM:SS
            m = int(math.ceil(val) if mode == 'Countdown' else math.floor(val)) // 60
            s = int(math.ceil(val) if mode == 'Countdown' else math.floor(val)) % 60
            text = f"{m:02d}:{s:02d}"

        font = QFont(data.get("font", "Arial"), round(float(data.get("font_size", 72.0))), QFont.Bold)
        metrics = QFontMetricsF(font)
        text_w = metrics.horizontalAdvance(text)
        text_h = metrics.height()

        pad_x = 36.0
        pad_y = 20.0
        card_w = text_w + pad_x * 2.0
        card_h = text_h + pad_y * 2.0
        cr = float(data.get("corner_radius", 16.0))
        local_bounds = QRectF(-card_w / 2.0, -card_h / 2.0, card_w, card_h)

        if data.get("bg_enabled", True):
            bg_col = QColor(data.get("bg_color", "#15181f"))
            bg_col.setAlpha(round(255 * float(data.get("bg_opacity", 88.0)) / 100.0))
            b_width = float(data.get("border_width", 2.5))
            b_col = QColor(data.get("border_color", "#3d8cff"))
            painter.setPen(QPen(b_col, b_width) if b_width > 0 else Qt.NoPen)
            painter.setBrush(QBrush(bg_col))
            painter.drawRoundedRect(local_bounds, cr, cr)

        if data.get("glow_enabled", False):
            _render_glow_text(
                painter,
                text,
                font,
                local_bounds,
                QColor(data.get("color", "#ffffff")),
                data.get("glow_color", "#55ffff"),
                float(data.get("glow_radius", 12.0)),
                float(data.get("glow_opacity", 55.0)),
            )
        else:
            painter.setFont(font)
            painter.setPen(QPen(QColor(data.get("color", "#ffffff"))))
            painter.drawText(local_bounds, Qt.AlignCenter, text)

    # 6. Speech Bubble / Quote Card
    elif "speech" in kind or "quote" in kind:
        text = str(data.get("text", "Your quote or callout here!"))
        font = QFont(data.get("font", "Segoe UI"), round(float(data.get("font_size", 42.0))), QFont.DemiBold)
        metrics = QFontMetricsF(font)
        pad = 28.0
        tail_pos = data.get("tail_position", "Bottom-Left")
        tail_s = float(data.get("tail_size", 28.0)) if tail_pos != "None (Card)" else 0.0

        max_text_w = 460.0
        lines = _wrap_text(text, metrics, max_text_w)
        line_h = metrics.lineSpacing()
        text_w = max((metrics.horizontalAdvance(line) for line in lines), default=120.0)
        text_h = len(lines) * line_h

        bubble_w = text_w + pad * 2.0
        bubble_h = text_h + pad * 2.0
        cr = float(data.get("corner_radius", 18.0))

        # Bubble body rect
        body_rect = QRectF(-bubble_w / 2.0, -bubble_h / 2.0, bubble_w, bubble_h)

        path = QPainterPath()
        path.addRoundedRect(body_rect, cr, cr)

        # Tail attachment
        if tail_s > 0:
            tail_poly = QPolygonF()
            if tail_pos == "Bottom-Left":
                p1 = QPointF(body_rect.left() + cr, body_rect.bottom())
                p2 = QPointF(body_rect.left() + cr + tail_s * 1.2, body_rect.bottom())
                tip = QPointF(body_rect.left() + cr - tail_s * 0.4, body_rect.bottom() + tail_s)
                tail_poly = QPolygonF([p1, tip, p2])
            elif tail_pos == "Bottom-Right":
                p1 = QPointF(body_rect.right() - cr - tail_s * 1.2, body_rect.bottom())
                p2 = QPointF(body_rect.right() - cr, body_rect.bottom())
                tip = QPointF(body_rect.right() - cr + tail_s * 0.4, body_rect.bottom() + tail_s)
                tail_poly = QPolygonF([p1, tip, p2])
            elif tail_pos == "Top-Left":
                p1 = QPointF(body_rect.left() + cr, body_rect.top())
                p2 = QPointF(body_rect.left() + cr + tail_s * 1.2, body_rect.top())
                tip = QPointF(body_rect.left() + cr - tail_s * 0.4, body_rect.top() - tail_s)
                tail_poly = QPolygonF([p1, tip, p2])
            elif tail_pos == "Top-Right":
                p1 = QPointF(body_rect.right() - cr - tail_s * 1.2, body_rect.top())
                p2 = QPointF(body_rect.right() - cr, body_rect.top())
                tip = QPointF(body_rect.right() - cr + tail_s * 0.4, body_rect.top() - tail_s)
                tail_poly = QPolygonF([p1, tip, p2])

            if not tail_poly.isEmpty():
                tail_path = QPainterPath()
                tail_path.addPolygon(tail_poly)
                path = path.united(tail_path)

        bg_col = QColor(data.get("bg_color", "#1f242d"))
        bg_col.setAlpha(round(255 * float(data.get("bg_opacity", 94.0)) / 100.0))
        b_width = float(data.get("border_width", 2.5))
        b_col = QColor(data.get("border_color", "#62d0ff"))

        painter.setPen(QPen(b_col, b_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin) if b_width > 0 else Qt.NoPen)
        painter.setBrush(QBrush(bg_col))
        painter.drawPath(path)

        painter.setFont(font)
        painter.setPen(QPen(QColor(data.get("color", "#ffffff"))))
        # Draw wrapped lines
        start_y = body_rect.top() + pad + metrics.ascent()
        for i, line in enumerate(lines):
            line_rect = QRectF(body_rect.left() + pad, start_y + i * line_h - metrics.ascent(), text_w, line_h)
            painter.drawText(line_rect, Qt.AlignCenter, line)

        local_bounds = path.boundingRect()

    # 7. Progress Bar
    elif "progress" in kind:
        th = float(data.get("thickness", 12.0))
        pct_width = float(data.get("width_percent", 88.0))
        total_w = (frame_rect.width() / scale_factor) * (pct_width / 100.0)
        cr = float(data.get("corner_radius", 6.0))

        prog = min(1.0, max(0.0, elapsed / max(0.001, item.duration)))
        bg_rect = QRectF(-total_w / 2.0, -th / 2.0, total_w, th)

        # Background track
        bg_col = QColor(data.get("bg_color", "#23262f"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg_col))
        painter.drawRoundedRect(bg_rect, cr, cr)

        # Filled bar
        bar_w = max(cr * 2.0, total_w * prog) if prog > 0 else 0.0
        if bar_w > 0:
            bar_rect = QRectF(-total_w / 2.0, -th / 2.0, bar_w, th)
            painter.setBrush(QBrush(QColor(data.get("bar_color", "#d9ff43"))))
            painter.drawRoundedRect(bar_rect, cr, cr)

        local_bounds = bg_rect

    # 8. Callout Badge
    elif "badge" in kind or "callout" in kind:
        text = str(data.get("text", "WAIT FOR IT ⚠️"))
        font = QFont(data.get("font", "Impact"), round(float(data.get("font_size", 52.0))))
        metrics = QFontMetricsF(font)
        text_w = metrics.horizontalAdvance(text)
        text_h = metrics.height()
        pad_x = 32.0
        pad_y = 16.0
        badge_w = text_w + pad_x * 2.0
        badge_h = text_h + pad_y * 2.0
        cr = float(data.get("corner_radius", badge_h / 2.0))

        local_bounds = QRectF(-badge_w / 2.0, -badge_h / 2.0, badge_w, badge_h)
        bg_col = QColor(data.get("bg_color", "#d9ff43"))
        bg_col.setAlpha(round(255 * float(data.get("bg_opacity", 100.0)) / 100.0))
        b_width = float(data.get("border_width", 0.0))

        if b_width > 0:
            painter.setPen(QPen(QColor(data.get("border_color", "#000000")), b_width))
        else:
            painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg_col))
        painter.drawRoundedRect(local_bounds, cr, cr)

        painter.setFont(font)
        painter.setPen(QPen(QColor(data.get("color", "#11130d"))))
        painter.drawText(local_bounds, Qt.AlignCenter, text)

    painter.restore()

    # Map local bounds back to frame coordinates
    return transform.mapRect(local_bounds)


def graphic_to_ass_events(project: Any, item: Any) -> list[str]:
    """Generate ASS subtitle dialogue events for burning graphic overlays into exported video."""
    data = getattr(item, "graphic_data", {}) or {}
    kind = getattr(item, "graphic_type", "circle").lower()
    start_time = item.start
    end_time = item.start + item.duration

    from .exporter import _ass_color, _ass_time

    events = []
    w = float(project.settings.width)
    h = float(project.settings.height)

    center_x = item.transform.x * w
    center_y = item.transform.y * h
    angle=math.radians(item.transform.rotation)
    ax=item.transform.anchor_x; ay=item.transform.anchor_y
    sx=item.transform.scale; sy=item.transform.effective_scale_y
    center_x+=ax-math.cos(angle)*sx*ax+math.sin(angle)*sy*ay
    center_y+=ay-math.sin(angle)*sx*ax-math.cos(angle)*sy*ay

    def alpha_hex(opacity: float) -> str:
        return f"&H{max(0, min(255, round(255 * (1.0 - opacity / 100.0)))):02X}&"

    # 1. Timer: emits interval dialogue events updating second-by-second
    if "timer" in kind:
        mode = data.get("mode", "Countdown")
        timer_dur = float(data.get("duration", item.duration))
        fmt = data.get("format", "MM:SS")
        font = data.get("font", "Arial")
        size = round(float(data.get("font_size", 72.0)))
        font_col = _ass_color(data.get("color", "#ffffff"))
        bg_enabled = data.get("bg_enabled", True)
        bg_col = _ass_color(data.get("bg_color", "#15181f"))
        bg_alpha = alpha_hex(float(data.get("bg_opacity", 88.0)))
        bord_col = _ass_color(data.get("border_color", "#3d8cff"))
        bord_w = round(float(data.get("border_width", 2.5)))

        step = 1.0
        cur_t = 0.0
        while cur_t < item.duration:
            seg_start = start_time + cur_t
            seg_end = min(end_time, start_time + cur_t + step)
            val = max(0.0, timer_dur - cur_t) if mode == "Countdown" else cur_t

            if fmt == "SS":
                text = f"{int(math.ceil(val) if mode == 'Countdown' else math.floor(val))}"
            else:
                m = int(math.ceil(val) if mode == 'Countdown' else math.floor(val)) // 60
                s = int(math.ceil(val) if mode == 'Countdown' else math.floor(val)) % 60
                text = f"{m:02d}:{s:02d}"

            if data.get("glow_enabled", False):
                glow_col = _ass_color(data.get("glow_color", "#55ffff"))
                glow_rad = float(data.get("glow_radius", 12.0))
                glow_op = float(data.get("glow_opacity", 55.0))
                glow_alpha = alpha_hex(glow_op)
                glow_tags = (
                    f"\\an5\\pos({center_x:.1f},{center_y:.1f})"
                    f"\\fn{font}\\fs{size}\\1c{glow_col}\\bord0\\shad0\\blur{glow_rad:.1f}\\alpha{glow_alpha}"
                )
                events.append(f"Dialogue: 1,{_ass_time(seg_start)},{_ass_time(seg_end)},Default,,0,0,0,,{{{glow_tags}}}{text}")

            tags = (
                f"\\an5\\pos({center_x:.1f},{center_y:.1f})"
                f"\\fn{font}\\fs{size}\\1c{font_col}\\bord{bord_w}\\3c{bord_col}"
            )
            if bg_enabled:
                tags += f"\\4c{bg_col}\\shad0\\2a{bg_alpha}"
            events.append(f"Dialogue: 1,{_ass_time(seg_start)},{_ass_time(seg_end)},Default,,0,0,0,,{{{tags}}}{text}")
            cur_t += step

    # 2. Text badges & Speech bubbles
    elif "speech" in kind or "quote" in kind or "badge" in kind or "callout" in kind:
        text = str(data.get("text", "Callout"))
        font = data.get("font", "Segoe UI" if "speech" in kind else "Impact")
        size = round(float(data.get("font_size", 44.0 if "speech" in kind else 52.0)))
        font_col = _ass_color(data.get("color", "#ffffff" if "speech" in kind else "#11130d"))
        bg_col = _ass_color(data.get("bg_color", "#1f242d" if "speech" in kind else "#d9ff43"))
        bg_alpha = alpha_hex(float(data.get("bg_opacity", 94.0 if "speech" in kind else 100.0)))
        bord_col = _ass_color(data.get("border_color", "#62d0ff" if "speech" in kind else "#000000"))
        bord_w = round(float(data.get("border_width", 2.0)))

        esc_text = text.replace("\n", "\\N")
        tags = (
            f"\\an5\\pos({center_x:.1f},{center_y:.1f})"
            f"\\fn{font}\\fs{size}\\1c{font_col}\\bord{bord_w}\\3c{bord_col}\\4c{bg_col}\\shad0"
        )
        events.append(f"Dialogue: 1,{_ass_time(start_time)},{_ass_time(end_time)},Default,,0,0,0,,{{{tags}}}{esc_text}")

    elif 'progress' in kind:
        from .headline import ass_path
        width=w*float(data.get('width_percent',88))/100
        height=float(data.get('thickness',12)); radius=float(data.get('corner_radius',6))
        def bar_event(start,end,bar_width,color,offset=0):
            path=QPainterPath(); path.addRoundedRect(QRectF(-bar_width/2,-height/2,bar_width,height),radius,radius)
            x=center_x+math.cos(angle)*sx*offset; y=center_y+math.sin(angle)*sx*offset
            tags=f'\\an5\\pos({x:.3f},{y:.3f})\\p1\\bord0\\shad0\\1c{_ass_color(color)}'
            return f'Dialogue: 1,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{{{tags}}}{ass_path(path)}'
        events.append(bar_event(start_time,end_time,width,data.get('bg_color','#23262f')))
        step=1/max(1,project.settings.fps); elapsed=0.
        while elapsed<item.duration:
            fraction=min(1,max(0,elapsed/max(.001,item.duration)))
            bar_width=min(width,max(radius*2,width*fraction))
            if fraction>0:events.append(bar_event(start_time+elapsed,min(end_time,start_time+elapsed+step),bar_width,data.get('bar_color','#d9ff43'),(bar_width-width)/2))
            elapsed+=step

    # 3. Geometric Shapes (Circle, Arrow, Square, Rectangle) via ASS \p1 vector drawing
    else:
        path = QPainterPath()
        col = _ass_color(data.get("color", "#ff3b30"))
        th = round(float(data.get("thickness", 8.0)))
        rot = item.transform.rotation

        if "circle" in kind:
            r = float(data.get("radius", 140.0))
            path.addEllipse(QRectF(-r, -r, 2 * r, 2 * r))
        elif "square" in kind:
            s = float(data.get("size", 260.0))
            cr = float(data.get("corner_radius", 16.0))
            path.addRoundedRect(QRectF(-s / 2.0, -s / 2.0, s, s), cr, cr)
        elif "rectangle" in kind:
            rw = float(data.get("width", 420.0))
            rh = float(data.get("height", 240.0))
            cr = float(data.get("corner_radius", 16.0))
            path.addRoundedRect(QRectF(-rw / 2.0, -rh / 2.0, rw, rh), cr, cr)
        elif "arrow" in kind:
            alen = float(data.get("length", 220.0))
            hs = float(data.get("head_size", 48.0))
            ath = float(data.get("thickness", 12.0))
            half = alen / 2.0
            shaft_end = half - hs * 0.75
            path.addRect(QRectF(-half, -ath / 2.0, shaft_end + half, ath))
            poly = QPolygonF([
                QPointF(half, 0),
                QPointF(half - hs, -hs * 0.55),
                QPointF(half - hs * 0.7, 0),
                QPointF(half - hs, hs * 0.55),
            ])
            path.addPolygon(poly)

        from .headline import ass_path
        drawing = ass_path(path)
        if drawing:
            fill_en = data.get("fill_enabled", False)
            fill_col = _ass_color(data.get("fill_color", data.get("color", "#ff3b30"))) if fill_en else "&H000000&"
            fill_alpha = alpha_hex(float(data.get("fill_opacity", 25.0))) if fill_en else "&HFF&"
            tags = (
                f"\\an5\\pos({center_x:.1f},{center_y:.1f})"
                f"\\p1\\bord{th}\\3c{col}\\1c{fill_col}\\1a{fill_alpha}\\shad0"
            )
            events.append(f"Dialogue: 1,{_ass_time(start_time)},{_ass_time(end_time)},Default,,0,0,0,,{{{tags}}}{drawing}")

    transform_tags=f"\\fscx{sx*100:.3f}\\fscy{sy*100:.3f}\\frz{-item.transform.rotation:.3f}"
    return [event.replace(',,{',',,{'+transform_tags,1) for event in events]
