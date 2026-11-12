"""Shared upper-left asset browser; navigation only, no editing commands."""
import logging

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QToolButton, QButtonGroup, QStyle, QStylePainter, QStyleOptionToolButton, QSizePolicy

from .icons import lucide_icon

HEADER_HEIGHT = 66

class LibraryCommand(QToolButton):
    """Keep complete command names readable when the library gets narrower."""
    def paintEvent(self,event):
        option=QStyleOptionToolButton(); self.initStyleOption(option)
        icon=QIcon(self.icon()); option.icon=QIcon(); option.text=''
        painter=QStylePainter(self); painter.drawComplexControl(QStyle.CC_ToolButton,option)
        icon.paint(painter,QRect((self.width()-18)//2,9,18,18),mode=QIcon.Normal if self.isEnabled() else QIcon.Disabled)
        painter.setFont(self.font()); painter.setPen(self.palette().color(QPalette.Active if self.isEnabled() else QPalette.Disabled,QPalette.ButtonText))
        painter.drawText(QRect(4,30,self.width()-8,self.height()-32),Qt.AlignHCenter|Qt.AlignVCenter|Qt.TextWordWrap,self.text())

class LibraryPanel(QWidget):
    tabs = (('Media', 'image-plus'), ('Effects', 'wand-sparkles'))

    def __init__(self, window, media, effects, actions=()):
        super().__init__()
        self.window, self.media, self.effects = window, media, effects
        self.active = 'Media'
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        bar = QWidget(); self.header = bar; bar.setFixedHeight(HEADER_HEIGHT)
        row = QHBoxLayout(bar); row.setContentsMargins(4, 0, 4, 0); row.setSpacing(1)
        self.group = QButtonGroup(self); self.buttons = {}
        for name, icon in self.tabs:
            button = QToolButton(); button.setText(name); button.setIcon(lucide_icon(icon))
            button.setIconSize(QSize(18, 18)); button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setCheckable(True); button.setProperty('panelToggle', True)
            button.setFixedHeight(HEADER_HEIGHT)
            button.setProperty('iconName', icon)
            button.setMinimumWidth(max(62, button.fontMetrics().horizontalAdvance(name)+28))
            button.setToolTip('Browse '+name.lower()); row.addWidget(button)
            self.group.addButton(button); self.buttons[name] = button
            button.toggled.connect(lambda checked, n=name: self.select(n) if checked else None)
        row.addSpacing(6)
        for action in actions: row.addWidget(action)
        row.addStretch(1); layout.addWidget(bar)
        self.stack = QStackedWidget(); self.stack.addWidget(media); self.stack.addWidget(effects)
        layout.addWidget(self.stack, 1)
        saved = window.settings.get('library_tab', 'Media')
        self.select(saved if saved in self.buttons else 'Media', restore=True)

    def save(self, key, value):
        if self.window.settings.get(key) == value: return
        self.window.settings[key] = value
        from .config import save_settings
        try: save_settings(self.window.settings)
        except OSError: logging.warning('Could not save library navigation', exc_info=True)

    def select(self, name, restore=False):
        self.active = name
        for key, button in self.buttons.items():
            button.blockSignals(True); button.setChecked(key == name); button.blockSignals(False)
        self.stack.setCurrentIndex(0 if name == 'Media' else 1)
        if not restore: self.save('library_tab', name)
