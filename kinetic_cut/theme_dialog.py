"""Accessible live theme picker with genuine miniature workspace previews."""
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QAbstractButton
from .theme import THEME_DEFINITIONS, get_active_theme_palette
from .theme_widgets import set_ui_style, apply_application_theme, palette


class ThemeCard(QAbstractButton):
    def __init__(self, theme_info, is_active, select_callback):
        super().__init__()
        self.theme_info = theme_info
        self.setCheckable(True)
        self.set_active(is_active)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(theme_info['name'])
        self.setAccessibleDescription(theme_info['tagline'] + ' Apply theme with Space.')
        self.setMinimumSize(220, 238)
        self.clicked.connect(lambda: select_callback(theme_info['id']))

    def sizeHint(self):
        return QSize(240, 252)

    def set_active(self, active):
        self.is_active = active
        self.setChecked(active)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = get_active_theme_palette(self.theme_info['id'])
        host = palette()
        def fill(rect, color):
            p.fillRect(QRectF(*rect), QColor(t[color] if color in t else color))
        edge = host['accent_ink'] if self.is_active or self.hasFocus() else host['border_subtle']
        p.setPen(QPen(QColor(edge), 3 if self.is_active or self.hasFocus() else 1))
        p.setBrush(QColor(t['bg_main']))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(3, 3, -3, -3), 9, 9)
        w = self.width() - 24
        fill((12, 14, w, 19), 'bg_topbar')
        for x in (19, 39, 59):
            fill((x, 21, 12, 3), 'text_sub')
        fill((12, 36, w * .21, 69), 'bg_surface')
        fill((15 + w * .21, 36, w * .51, 69), 'bg_viewer')
        fill((18 + w * .72, 36, w * .28 - 6, 69), 'bg_panel')
        fill((w * .40, 42, 31, 57), '#090a0c')
        for y in (47, 61, 75, 89):
            fill((20, y, w * .13, 3), 'text_sub')
            fill((23 + w * .72, y, w * .20 - 6, 4), 'text_sub')
        fill((12, 109, w, 13), 'timeline_ruler_bg')
        fill((12, 123, w, 40), 'timeline_bg')
        for x, y, width, color in ((30, 128, 66, '#3c6c90'), (99, 128, 47, '#3c6c90'), (30, 145, 116, '#326951')):
            fill((x, y, width, 12), color)
        fill((w * .58, 111, 2, 51), 'accent')
        p.setPen(QColor(t['text_main']))
        font = p.font(); font.setPixelSize(14); font.setBold(True); p.setFont(font)
        p.drawText(QRectF(16, 173, w - 8, 23), self.theme_info['name'])
        font.setPixelSize(11); font.setBold(False); p.setFont(font)
        p.setPen(QColor(t['text_sub']))
        p.drawText(QRectF(16, 200, w - 8, 35), Qt.TextWordWrap, self.theme_info['tagline'])
        if self.is_active:
            fill((w - 70, 15, 70, 16), 'bg_selected')
            p.setPen(QColor(t['text_selected']))
            p.drawText(QRectF(w - 70, 15, 70, 16), Qt.AlignCenter, '✓ Selected')
        p.end()


class UIThemesDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window_ = window
        self.setWindowTitle('UI Themes')
        self.resize(790, 370)
        self.setModal(True)
        self.current_theme = get_active_theme_palette(window.settings.get('ui_theme', 'default'))['id']
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel('Make the workspace yours')
        set_ui_style(title, 'font-size:18px; font-weight:600;')
        layout.addWidget(title)
        subtitle = QLabel('Choose a preview to apply instantly. Your choice is remembered on launch.')
        set_ui_style(subtitle, 'color:@text_sub;')
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.cards = []
        for theme in THEME_DEFINITIONS:
            card = ThemeCard(theme, theme['id'] == self.current_theme, self.apply_theme)
            self.cards.append(card)
            row.addWidget(card, 1)
        layout.addLayout(row, 1)
        bottom = QHBoxLayout()
        note = QLabel('Appearance only — your media and exports stay unchanged.')
        set_ui_style(note, 'color:@text_sub; font-size:11px;')
        bottom.addWidget(note, 1)
        done = QPushButton('Done')
        done.setMinimumWidth(90)
        done.clicked.connect(self.accept)
        bottom.addWidget(done)
        layout.addLayout(bottom)

    def apply_theme(self, theme_id):
        self.current_theme = get_active_theme_palette(theme_id)['id']
        if hasattr(self.window_, 'apply_theme'):
            self.window_.apply_theme(self.current_theme, save=True)
        else:
            from .config import save_settings
            self.window_.settings['ui_theme'] = self.current_theme
            save_settings(self.window_.settings)
            apply_application_theme(self.current_theme)
        for card in self.cards:
            card.set_active(card.theme_info['id'] == self.current_theme)
