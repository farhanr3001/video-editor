"""Explicit UI-only colour bindings. Never recolours media, thumbnails or swatches.

Local styles use @palette_role tokens and retain their canonical template so a
dark/light/dark round trip is lossless. Refresh runs only on theme changes, not
on painting, scrubbing or playback. New dialogs use the active palette at birth.
"""
import re
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from .theme import get_active_theme_palette, get_theme_stylesheet


def palette():
    app = QApplication.instance()
    return get_active_theme_palette(app.property('kineticTheme') if app else 'default')


def ui_color(role):
    return QColor(palette()[role])


def set_ui_style(widget, template):
    widget._theme_style_template = template
    p = palette()
    if '@arrow_' in template:
        from .icons import resource_path
        p = dict(p)
        for key, filename in (('arrow_up', 'spin-up'), ('arrow_down', 'spin-down'), ('arrow_combo', 'dropdown-chevron')):
            p[key] = resource_path('assets', 'icons', filename + ('-dark' if p['is_light'] else '') + '.svg').as_posix()
    widget.setStyleSheet(re.sub(r'@([a-z_]+)', lambda m: p[m[1]], template))


def set_ui_icon(label, name, color=None, size=20):
    """QLabel holds a raster pixmap, so explicitly refresh it on theme changes."""
    from .icons import lucide_icon
    label._theme_icon = (name, color, size)
    label.setPixmap(lucide_icon(name, color, size).pixmap(size, size))


def apply_application_theme(theme_id):
    app = QApplication.instance()
    if not app:
        return
    p = get_active_theme_palette(theme_id)
    stylesheet = get_theme_stylesheet(p['id'])
    if app.property('kineticTheme') == p['id'] and app.styleSheet() == stylesheet:
        return
    app.setProperty('kineticTheme', p['id'])
    q = QPalette()
    roles = {'Window': 'bg_main', 'WindowText': 'text_main', 'Base': 'bg_input',
             'AlternateBase': 'bg_panel', 'Text': 'text_main', 'Button': 'bg_panel',
             'ButtonText': 'text_main', 'Highlight': 'bg_selected',
             'HighlightedText': 'text_selected', 'ToolTipBase': 'bg_panel',
             'ToolTipText': 'text_main', 'Link': 'info', 'LinkVisited': 'info',
             'PlaceholderText': 'text_sub', 'Light': 'border_subtle', 'Mid': 'border',
             'Dark': 'border', 'BrightText': 'text_main'}
    for role, token in roles.items():
        q.setColor(getattr(QPalette, role), QColor(p[token]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        q.setColor(QPalette.Disabled, role, QColor(p['text_disabled']))
    if app.palette() != q:
        app.setPalette(q)
    if app.styleSheet() != stylesheet:
        app.setStyleSheet(stylesheet)
    for widget in app.allWidgets():
        if hasattr(widget, '_theme_style_template'):
            set_ui_style(widget, widget._theme_style_template)
        if hasattr(widget, '_theme_icon'):
            set_ui_icon(widget, *widget._theme_icon)
        # Secondary preview windows can remain open during a theme change.
        if widget.__class__.__name__ == 'PreviewCanvas':
            widget.set_theme(p)
        widget.update()
