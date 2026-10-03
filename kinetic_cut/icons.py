from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def resource_path(*parts: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root.joinpath(*parts)


_CURRENT_ICON_COLOR: str = "#d8dae0"


def set_current_icon_color(color: str) -> None:
    """Update global icon color and invalidate cached pixmaps."""
    global _CURRENT_ICON_COLOR
    if color != _CURRENT_ICON_COLOR:
        _CURRENT_ICON_COLOR = color
        lucide_icon.cache_clear()
        create_nav_icon.cache_clear()


def get_current_icon_color() -> str:
    """Return active global icon color."""
    return _CURRENT_ICON_COLOR


@lru_cache(maxsize=512)
def lucide_icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    path = resource_path("assets", "icons", f"{name}.svg")
    if not path.exists():
        return QIcon()
    return QIcon(_ThemeIcon(path.read_text(encoding="utf-8"), color))


class _ThemeIcon(QIconEngine):
    """Existing tab, action and effect icons follow live theme changes too."""
    def __init__(self, svg, color):
        super().__init__()
        self.svg, self.color = svg, color

    def clone(self):
        return _ThemeIcon(self.svg, self.color)

    def ink(self, mode, state):
        from .theme_widgets import palette
        p = palette()
        role = self.color[1:] if self.color and self.color.startswith('@') else None
        ink = p[role] if role else self.color or p['icon_color']
        if mode == QIcon.Disabled:
            ink = p['text_disabled']
        elif role == 'tab_icon':
            ink = p['icon_color']
        elif mode == QIcon.Selected:
            ink = p['text_selected']
        elif state == QIcon.On:
            ink = p['text_tool_checked'] if role == 'icon_color' else p['text_selected']
        elif p['is_light'] and not role:
            # Explicit coloured UI icons retain their meaning, with dark ink.
            c = QColor(ink)
            hue, saturation, _, _ = c.getHsvF()
            if saturation > .4 and (hue < .06 or hue > .93):
                ink = p['danger']
            elif saturation > .4 and .22 < hue < .46:
                ink = p['success']
            else:
                ink = p['icon_color']
        return ink

    def paint(self, painter, rect, mode, state):
        scale = painter.device().devicePixelRatioF()
        pix = _icon_raster(self.svg, self.ink(mode, state), max(1, round(rect.width()*scale)), max(1, round(rect.height()*scale)))
        painter.drawPixmap(rect, pix)

    def pixmap(self, size, mode, state):
        return _icon_raster(self.svg, self.ink(mode, state), size.width(), size.height())


@lru_cache(maxsize=512)
def _svg_renderer(svg, color):
    return QSvgRenderer(QByteArray(svg.replace('currentColor', color).encode('utf-8')))


@lru_cache(maxsize=1024)
def _icon_raster(svg, color, width, height):
    pix = QPixmap(width, height)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    _svg_renderer(svg, color).render(painter, QRectF(1, 1, width-2, height-2))
    painter.end()
    return pix


@lru_cache(maxsize=128)
def create_nav_icon(name: str, color_off: str, color_on: str, size: int = 18) -> QIcon:
    path = resource_path("assets", "icons", f"{name}.svg")
    if not path.exists():
        return QIcon()
    scale = 2
    
    # Inactive (Off) pixmap
    svg_off = path.read_text(encoding="utf-8").replace("currentColor", color_off)
    ren_off = QSvgRenderer(QByteArray(svg_off.encode("utf-8")))
    pix_off = QPixmap(size * scale, size * scale)
    pix_off.fill(Qt.transparent)
    p1 = QPainter(pix_off)
    p1.setRenderHint(QPainter.Antialiasing)
    ren_off.render(p1, QRectF(1, 1, size * scale - 2, size * scale - 2))
    p1.end()
    pix_off.setDevicePixelRatio(scale)

    # Active (On) pixmap
    svg_on = path.read_text(encoding="utf-8").replace("currentColor", color_on)
    ren_on = QSvgRenderer(QByteArray(svg_on.encode("utf-8")))
    pix_on = QPixmap(size * scale, size * scale)
    pix_on.fill(Qt.transparent)
    p2 = QPainter(pix_on)
    p2.setRenderHint(QPainter.Antialiasing)
    ren_on.render(p2, QRectF(1, 1, size * scale - 2, size * scale - 2))
    p2.end()
    pix_on.setDevicePixelRatio(scale)

    icon = QIcon()
    icon.addPixmap(pix_off, QIcon.Normal, QIcon.Off)
    icon.addPixmap(pix_on, QIcon.Normal, QIcon.On)
    return icon
