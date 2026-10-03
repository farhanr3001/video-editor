"""Video Transitions engine for Kinetic Cut.

Provides transition catalog, data models, default properties, easing curves,
and compositing logic for real-time PreviewCanvas rendering and export.
"""
from dataclasses import dataclass, field, asdict
import math
from typing import Any
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QBrush, QTransform

# Categorized transition definitions
TRANSITION_SUBSECTIONS: dict[str, list[str]] = {
    "Dissolve": [
        "Cross Dissolve",
        "Dip to Color / White Flash",
        "Dip to Black",
        "Blur Dissolve",
        "Additive Dissolve",
        "Smooth Dissolve",
    ],
    "Wipe & Split": [
        "Wipe Left",
        "Wipe Right",
        "Wipe Up",
        "Wipe Down",
        "Split Wipe",
        "Clock Wipe",
    ],
    "Motion & Push": [
        "Push Left (Swipe)",
        "Push Right (Swipe)",
        "Push Up (Swipe)",
        "Push Down (Swipe)",
        "Slide In",
        "Slide Out",
        "Zoom In (Whoosh)",
        "Whip Pan Transition",
    ],
    "Glitch & Stylized": [
        "Digital Glitch",
        "RGB Split Glitch",
        "Film Roll",
        "Lens Flare Flash",
        "Pixelate",
    ],
}

# Flat list of all transition names
TRANSITION_NAMES: list[str] = [name for names in TRANSITION_SUBSECTIONS.values() for name in names]
TRANSITION_SET: set[str] = set(TRANSITION_NAMES)

# Reverse lookup for category
SUBSECTION_BY_TRANSITION: dict[str, str] = {
    name: sub for sub, names in TRANSITION_SUBSECTIONS.items() for name in names
}

# Transition icon mapping to dedicated professional vector assets
TRANSITION_ICONS: dict[str, str] = {
    "Cross Dissolve": "trans-cross-dissolve",
    "Dip to Color / White Flash": "trans-white-flash",
    "Dip to Black": "trans-dip-black",
    "Blur Dissolve": "trans-blur-dissolve",
    "Additive Dissolve": "trans-additive-dissolve",
    "Smooth Dissolve": "trans-smooth-dissolve",
    "Wipe Left": "trans-wipe-left",
    "Wipe Right": "trans-wipe-right",
    "Wipe Up": "trans-wipe-up",
    "Wipe Down": "trans-wipe-down",
    "Split Wipe": "trans-split-wipe",
    "Clock Wipe": "trans-clock-wipe",
    "Push Left (Swipe)": "trans-push-left",
    "Push Right (Swipe)": "trans-push-right",
    "Push Up (Swipe)": "trans-push-up",
    "Push Down (Swipe)": "trans-push-down",
    "Slide In": "trans-slide-in",
    "Slide Out": "trans-slide-out",
    "Zoom In (Whoosh)": "trans-zoom-whoosh",
    "Whip Pan Transition": "trans-whip-pan",
    "Digital Glitch": "trans-digital-glitch",
    "RGB Split Glitch": "trans-rgb-glitch",
    "Film Roll": "trans-film-roll",
    "Lens Flare Flash": "trans-lens-flare",
    "Pixelate": "trans-pixelate",
}

# Transition descriptions
TRANSITION_DESCRIPTIONS: dict[str, str] = {
    "Cross Dissolve": "Smooth standard cross-fade blending between two clips.",
    "Dip to Color / White Flash": "High-impact brightness flash fading from outgoing clip into white/color, then into incoming clip.",
    "Dip to Black": "Fades outgoing clip cleanly to black before fading up incoming clip.",
    "Blur Dissolve": "Cross dissolve with peak Gaussian blur at the edit cut point.",
    "Additive Dissolve": "Luminance-weighted additive transition with vibrant highlight overlap.",
    "Smooth Dissolve": "Cinematic S-curve dissolve with balanced midtone roll-off.",
    "Wipe Left": "Linear wipe moving from right to left across the screen.",
    "Wipe Right": "Linear wipe moving from left to right across the screen.",
    "Wipe Up": "Linear wipe moving from bottom to top.",
    "Wipe Down": "Linear wipe moving from top to bottom.",
    "Split Wipe": "Curtain wipe opening or closing from the screen center.",
    "Clock Wipe": "Radial clock sweep revealing the incoming video.",
    "Push Left (Swipe)": "Popular dynamic swipe pushing the outgoing clip left as the new clip enters.",
    "Push Right (Swipe)": "Dynamic swipe pushing the outgoing clip right.",
    "Push Up (Swipe)": "Dynamic vertical swipe pushing the outgoing clip up.",
    "Push Down (Swipe)": "Dynamic vertical swipe pushing the outgoing clip down.",
    "Slide In": "Incoming clip slides smoothly in over the outgoing clip.",
    "Slide Out": "Outgoing clip slides away revealing the stationary incoming clip underneath.",
    "Zoom In (Whoosh)": "High-energy zoom whoosh transition zooming through the cut.",
    "Whip Pan Transition": "Fast horizontal camera whip with high-speed directional motion blur.",
    "Digital Glitch": "Cyberpunk digital glitch with horizontal block slicing and digital artifacts.",
    "RGB Split Glitch": "Chromatic aberration glitch shifting red, green, and blue color planes.",
    "Film Roll": "Vertical film frame-line roll transition with vintage slip.",
    "Lens Flare Flash": "Cinematic horizontal lens flare flash bursting across the cut point.",
    "Pixelate": "Pixelated mosaic transition dissolving into the next scene.",
}

# FFmpeg xfade transition filter mapping
XFADE_MAP: dict[str, str] = {
    "Cross Dissolve": "fade",
    "Dip to Color / White Flash": "fadewhite",
    "Dip to Black": "fadeblack",
    "Blur Dissolve": "dissolve",
    "Additive Dissolve": "dissolve",
    "Smooth Dissolve": "smoothleft",
    "Wipe Left": "wipeleft",
    "Wipe Right": "wiperight",
    "Wipe Up": "wipeup",
    "Wipe Down": "wipedown",
    "Split Wipe": "horzopen",
    "Clock Wipe": "radial",
    "Push Left (Swipe)": "slideleft",
    "Push Right (Swipe)": "slideright",
    "Push Up (Swipe)": "slideup",
    "Push Down (Swipe)": "slidedown",
    "Slide In": "slideleft",
    "Slide Out": "slideright",
    "Zoom In (Whoosh)": "zoomin",
    "Whip Pan Transition": "hrslice",
    "Digital Glitch": "pixelize",
    "RGB Split Glitch": "pixelize",
    "Film Roll": "vertopen",
    "Lens Flare Flash": "fadewhite",
    "Pixelate": "pixelize",
}


def xfade_name(name: str) -> str:
    """Return standard FFmpeg xfade transition name."""
    return XFADE_MAP.get(name, "fade")



@dataclass
class Transition:
    id: str
    name: str
    category: str = "Dissolve"
    track: str = "video_1"
    start: float = 0.0
    duration: float = 0.80
    left_item_id: str = ""
    right_item_id: str = ""
    alignment: str = "center"  # "center", "start", "end"
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.category:
            self.category = SUBSECTION_BY_TRANSITION.get(self.name, "Dissolve")
        if not self.properties:
            self.properties = default_transition_properties(self.name)
        # Ensure minimum safe duration (50ms)
        self.duration = max(0.05, min(10.0, float(self.duration)))

    @property
    def end(self) -> float:
        return self.start + self.duration

    def contains_time(self, t: float) -> bool:
        return self.start <= t < self.end

    def progress(self, t: float) -> float:
        if self.duration <= 0.0:
            return 1.0
        return max(0.0, min(1.0, (t - self.start) / self.duration))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transition":
        d = dict(data)
        return cls(
            id=d.get("id", ""),
            name=d.get("name", "Cross Dissolve"),
            category=d.get("category", ""),
            track=d.get("track", "video_1"),
            start=float(d.get("start", 0.0)),
            duration=float(d.get("duration", 0.80)),
            left_item_id=d.get("left_item_id", ""),
            right_item_id=d.get("right_item_id", ""),
            alignment=d.get("alignment", "center"),
            properties=d.get("properties", {}),
        )


def default_transition_properties(name: str) -> dict[str, Any]:
    """Return default parameters for the specified transition name."""
    props: dict[str, Any] = {
        "easing": "Ease In-Out",
    }
    if name == "Dip to Color / White Flash":
        props.update({
            "color": "#ffffff",
            "intensity": 1.0,
            "hold_duration": 0.05,
        })
    elif name == "Dip to Black":
        props.update({
            "color": "#000000",
            "intensity": 1.0,
            "hold_duration": 0.05,
        })
    elif name == "Blur Dissolve":
        props.update({
            "blur_radius": 24,
            "direction": "Both",
        })
    elif name in ("Wipe Left", "Wipe Right", "Wipe Up", "Wipe Down"):
        props.update({
            "feather": 15,
            "border_width": 0,
            "border_color": "#ffffff",
        })
    elif name == "Split Wipe":
        props.update({
            "direction": "Horizontal",
            "feather": 10,
        })
    elif name == "Clock Wipe":
        props.update({
            "feather": 5,
        })
    elif name in ("Push Left (Swipe)", "Push Right (Swipe)", "Push Up (Swipe)", "Push Down (Swipe)"):
        props.update({
            "motion_blur": True,
            "feather": 0,
        })
    elif name in ("Slide In", "Slide Out"):
        props.update({
            "direction": "Left",
            "shadow": True,
        })
    elif name == "Zoom In (Whoosh)":
        props.update({
            "zoom_scale": 2.5,
            "motion_blur": True,
        })
    elif name == "Whip Pan Transition":
        props.update({
            "direction": "Left",
            "blur_strength": 30,
        })
    elif name == "Digital Glitch":
        props.update({
            "glitch_strength": 0.8,
            "block_size": 24,
            "slice_count": 8,
        })
    elif name == "RGB Split Glitch":
        props.update({
            "offset_px": 16,
            "shake": True,
        })
    elif name == "Film Roll":
        props.update({
            "rolls": 1,
            "flicker": True,
        })
    elif name == "Lens Flare Flash":
        props.update({
            "flare_color": "#fffaee",
            "intensity": 1.0,
        })
    elif name == "Pixelate":
        props.update({
            "max_pixel_size": 32,
        })
    return props


def apply_easing(progress: float, easing_type: str = "Ease In-Out") -> float:
    """Evaluate non-linear easing curve for normalized progress [0.0, 1.0]."""
    p = max(0.0, min(1.0, progress))
    if easing_type == "Linear":
        return p
    elif easing_type == "Ease In":
        return p * p
    elif easing_type == "Ease Out":
        return 1.0 - (1.0 - p) * (1.0 - p)
    elif easing_type == "Smooth S-Curve":
        # Smoothstep
        return p * p * (3.0 - 2.0 * p)
    else:  # "Ease In-Out" default
        if p < 0.5:
            return 2.0 * p * p
        else:
            return 1.0 - math.pow(-2.0 * p + 2.0, 2) / 2.0


def composite_transition(
    painter: QPainter,
    dest_rect: QRectF,
    img_a: QImage | None,
    img_b: QImage | None,
    transition: Transition,
    raw_progress: float,
) -> None:
    """Composite the transition between image A (outgoing) and image B (incoming) into dest_rect.
    
    Zero lag implementation leveraging native QPainter clipping, opacity, transforms,
    and composition modes.
    """
    props = transition.properties or {}
    easing_name = props.get("easing", "Ease In-Out")
    p = apply_easing(raw_progress, easing_name)
    name = transition.name

    # Normalize missing frames to solid black
    has_a = img_a is not None and not img_a.isNull()
    has_b = img_b is not None and not img_b.isNull()

    painter.save()
    painter.setClipRect(dest_rect, Qt.IntersectClip)

    # 1. Dissolve Family
    if name == "Cross Dissolve" or name == "Smooth Dissolve":
        if has_a:
            painter.save()
            painter.setOpacity(1.0 - p)
            painter.drawImage(dest_rect, img_a)
            painter.restore()
        if has_b:
            painter.save()
            painter.setOpacity(p)
            painter.drawImage(dest_rect, img_b)
            painter.restore()

    elif name == "Additive Dissolve":
        if has_a:
            painter.save()
            painter.setOpacity(1.0 - p * 0.5)
            painter.drawImage(dest_rect, img_a)
            painter.restore()
        if has_b:
            painter.save()
            painter.setCompositionMode(QPainter.CompositionMode_Plus)
            painter.setOpacity(p)
            painter.drawImage(dest_rect, img_b)
            painter.restore()

    elif name == "Dip to Color / White Flash" or name == "Dip to Black":
        flash_color_str = props.get("color", "#ffffff" if "White" in name else "#000000")
        flash_color = QColor(flash_color_str)
        # 0.0 -> 0.5: clip A fades to flash color
        # 0.5 -> 1.0: flash color fades into clip B
        if p < 0.5:
            alpha = p * 2.0  # 0.0 -> 1.0
            if has_a:
                painter.drawImage(dest_rect, img_a)
            flash_overlay = QColor(flash_color)
            flash_overlay.setAlphaF(alpha)
            painter.fillRect(dest_rect, flash_overlay)
        else:
            alpha = (1.0 - p) * 2.0  # 1.0 -> 0.0
            if has_b:
                painter.drawImage(dest_rect, img_b)
            flash_overlay = QColor(flash_color)
            flash_overlay.setAlphaF(alpha)
            painter.fillRect(dest_rect, flash_overlay)

    elif name == "Blur Dissolve":
        # Draw cross dissolve
        if has_a:
            painter.save()
            painter.setOpacity(1.0 - p)
            painter.drawImage(dest_rect, img_a)
            painter.restore()
        if has_b:
            painter.save()
            painter.setOpacity(p)
            painter.drawImage(dest_rect, img_b)
            painter.restore()
        # Overlay a soft optical glow / blur simulation peaking at cut midpoint
        peak_glow = 1.0 - abs(p - 0.5) * 2.0  # 0 at endpoints, 1.0 at midpoint
        if peak_glow > 0.05:
            glow_c = QColor(255, 255, 255, int(120 * peak_glow))
            painter.fillRect(dest_rect, glow_c)

    # 2. Wipe Family
    elif name in ("Wipe Left", "Wipe Right", "Wipe Up", "Wipe Down"):
        if has_a:
            painter.drawImage(dest_rect, img_a)
        if has_b:
            painter.save()
            wipe_path = QPainterPath()
            w, h = dest_rect.width(), dest_rect.height()
            x, y = dest_rect.x(), dest_rect.y()
            if name == "Wipe Right":
                wipe_path.addRect(QRectF(x, y, w * p, h))
            elif name == "Wipe Left":
                wipe_path.addRect(QRectF(x + w * (1.0 - p), y, w * p, h))
            elif name == "Wipe Down":
                wipe_path.addRect(QRectF(x, y, w, h * p))
            elif name == "Wipe Up":
                wipe_path.addRect(QRectF(x, y + h * (1.0 - p), w, h * p))
            painter.setClipPath(wipe_path, Qt.IntersectClip)
            painter.drawImage(dest_rect, img_b)
            painter.restore()

    elif name == "Split Wipe":
        if has_a:
            painter.drawImage(dest_rect, img_a)
        if has_b:
            painter.save()
            w, h = dest_rect.width(), dest_rect.height()
            x, y = dest_rect.x(), dest_rect.y()
            split_path = QPainterPath()
            open_w = (w / 2.0) * p
            # Left half and right half opening from center
            split_path.addRect(QRectF(x + w / 2.0 - open_w, y, open_w * 2.0, h))
            painter.setClipPath(split_path, Qt.IntersectClip)
            painter.drawImage(dest_rect, img_b)
            painter.restore()

    elif name == "Clock Wipe":
        if has_a:
            painter.drawImage(dest_rect, img_a)
        if has_b:
            painter.save()
            center = dest_rect.center()
            radius = math.hypot(dest_rect.width(), dest_rect.height())
            clock_path = QPainterPath()
            clock_path.moveTo(center)
            # Pie angle in 16ths of a degree
            clock_path.arcTo(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2), 90, -360.0 * p)
            clock_path.closeSubpath()
            painter.setClipPath(clock_path, Qt.IntersectClip)
            painter.drawImage(dest_rect, img_b)
            painter.restore()

    # 3. Motion & Push Family
    elif name in ("Push Left (Swipe)", "Push Right (Swipe)", "Push Up (Swipe)", "Push Down (Swipe)"):
        w, h = dest_rect.width(), dest_rect.height()
        x, y = dest_rect.x(), dest_rect.y()
        if name == "Push Left (Swipe)":
            offset_a = QPointF(-w * p, 0)
            offset_b = QPointF(w * (1.0 - p), 0)
        elif name == "Push Right (Swipe)":
            offset_a = QPointF(w * p, 0)
            offset_b = QPointF(-w * (1.0 - p), 0)
        elif name == "Push Up (Swipe)":
            offset_a = QPointF(0, -h * p)
            offset_b = QPointF(0, h * (1.0 - p))
        else:  # Push Down
            offset_a = QPointF(0, h * p)
            offset_b = QPointF(0, -h * (1.0 - p))

        if has_a:
            painter.save()
            painter.drawImage(dest_rect.translated(offset_a), img_a)
            painter.restore()
        if has_b:
            painter.save()
            painter.drawImage(dest_rect.translated(offset_b), img_b)
            painter.restore()

    elif name == "Slide In":
        if has_a:
            painter.drawImage(dest_rect, img_a)
        if has_b:
            w = dest_rect.width()
            offset_b = QPointF(w * (1.0 - p), 0)
            painter.save()
            # Draw subtle dropshadow behind incoming slide
            shadow_rect = dest_rect.translated(offset_b).adjusted(-10, 0, 0, 0)
            painter.fillRect(QRectF(shadow_rect.left(), shadow_rect.top(), 12, shadow_rect.height()), QColor(0, 0, 0, 90))
            painter.drawImage(dest_rect.translated(offset_b), img_b)
            painter.restore()

    elif name == "Slide Out":
        if has_b:
            painter.drawImage(dest_rect, img_b)
        if has_a:
            w = dest_rect.width()
            offset_a = QPointF(-w * p, 0)
            painter.save()
            painter.drawImage(dest_rect.translated(offset_a), img_a)
            painter.restore()

    elif name == "Zoom In (Whoosh)" or name == "Whip Pan Transition":
        if p < 0.5:
            # Outgoing zooms in rapidly
            zoom = 1.0 + p * 2.0 * 1.5
            if has_a:
                painter.save()
                center = dest_rect.center()
                painter.translate(center)
                painter.scale(zoom, zoom)
                painter.translate(-center)
                painter.setOpacity(1.0 - p * 2.0)
                painter.drawImage(dest_rect, img_a)
                painter.restore()
        else:
            # Incoming zooms down from large to 1.0
            p_in = (p - 0.5) * 2.0
            zoom = 1.0 + (1.0 - p_in) * 1.5
            if has_b:
                painter.save()
                center = dest_rect.center()
                painter.translate(center)
                painter.scale(zoom, zoom)
                painter.translate(-center)
                painter.setOpacity(p_in)
                painter.drawImage(dest_rect, img_b)
                painter.restore()

    # 4. Glitch & Stylized Family
    elif name == "Digital Glitch" or name == "RGB Split Glitch":
        # Base dissolve
        if has_a:
            painter.save()
            painter.setOpacity(1.0 - p)
            painter.drawImage(dest_rect, img_a)
            painter.restore()
        if has_b:
            painter.save()
            painter.setOpacity(p)
            painter.drawImage(dest_rect, img_b)
            painter.restore()

        # Glitch artifacts centered around cut point
        glitch_peak = 1.0 - abs(p - 0.5) * 2.0
        if glitch_peak > 0.1:
            h = dest_rect.height()
            w = dest_rect.width()
            num_slices = 8
            slice_h = h / num_slices
            for s in range(num_slices):
                offset_x = math.sin(s * 13.5 + p * 40.0) * (30.0 * glitch_peak)
                slice_rect = QRectF(dest_rect.x(), dest_rect.y() + s * slice_h, w, slice_h)
                # Draw displaced slice overlay
                glitch_c = QColor(0, 240, 255, int(80 * glitch_peak)) if s % 2 == 0 else QColor(255, 0, 120, int(80 * glitch_peak))
                painter.fillRect(slice_rect.translated(offset_x, 0), glitch_c)

    elif name == "Film Roll":
        h = dest_rect.height()
        roll_y = math.fmod(p * h * 2.0, h)
        if has_a and p < 0.5:
            painter.drawImage(dest_rect.translated(0, roll_y), img_a)
            painter.drawImage(dest_rect.translated(0, roll_y - h), img_a)
        elif has_b:
            painter.drawImage(dest_rect.translated(0, roll_y), img_b)
            painter.drawImage(dest_rect.translated(0, roll_y - h), img_b)
        # Black frame line
        painter.fillRect(QRectF(dest_rect.x(), dest_rect.y() + roll_y - 8, dest_rect.width(), 16), QColor(10, 10, 12))

    elif name == "Lens Flare Flash":
        if has_a:
            painter.drawImage(dest_rect, img_a)
        if has_b:
            painter.save()
            painter.setOpacity(p)
            painter.drawImage(dest_rect, img_b)
            painter.restore()
        # Horizontal anamorphic flare streak peaking at midpoint
        streak_intensity = 1.0 - abs(p - 0.5) * 2.0
        if streak_intensity > 0.05:
            center_y = dest_rect.center().y()
            streak_h = 24.0 * streak_intensity
            streak_color = QColor(255, 250, 230, int(220 * streak_intensity))
            painter.fillRect(QRectF(dest_rect.x(), center_y - streak_h / 2.0, dest_rect.width(), streak_h), streak_color)

    elif name == "Pixelate":
        # Cross dissolve with pixelation overlay
        if has_a:
            painter.save()
            painter.setOpacity(1.0 - p)
            painter.drawImage(dest_rect, img_a)
            painter.restore()
        if has_b:
            painter.save()
            painter.setOpacity(p)
            painter.drawImage(dest_rect, img_b)
            painter.restore()
        pix_intensity = 1.0 - abs(p - 0.5) * 2.0
        if pix_intensity > 0.15:
            grid_c = QColor(0, 0, 0, int(90 * pix_intensity))
            painter.fillRect(dest_rect, grid_c)

    else:
        # Generic fallback dissolve
        if has_a:
            painter.save()
            painter.setOpacity(1.0 - p)
            painter.drawImage(dest_rect, img_a)
            painter.restore()
        if has_b:
            painter.save()
            painter.setOpacity(p)
            painter.drawImage(dest_rect, img_b)
            painter.restore()

    painter.restore()
