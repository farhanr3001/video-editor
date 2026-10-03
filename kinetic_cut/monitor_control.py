"""Playback monitoring only: never writes project/export gain."""
from PySide6.QtCore import Qt,QEvent,QSignalBlocker
from PySide6.QtWidgets import QWidget,QHBoxLayout,QToolButton,QSlider,QMenu,QWidgetAction,QVBoxLayout,QLabel
from .icons import lucide_icon
from .controls import SafeSlider as QSlider


class MonitorControl(QWidget):
    def __init__(self,window):
        super().__init__(window); self.window=window
        self.level=100; self.muted=False
        layout=QHBoxLayout(self); layout.setContentsMargins(4,0,0,0); layout.setSpacing(3)
        self.setFixedWidth(118)
        self.button=QToolButton(); self.button.clicked.connect(self.toggle); self.button.setContextMenuPolicy(Qt.CustomContextMenu); self.button.customContextMenuRequested.connect(self.popup)
        layout.addWidget(self.button)
        self.slider=QSlider(Qt.Horizontal); self.slider.setRange(0,100); self.slider.setValue(100); self.slider.setFixedWidth(85); self.slider.setToolTip('Playback monitor volume — does not affect exports')
        self.slider.valueChanged.connect(self.set_level); layout.addWidget(self.slider)
        window.installEventFilter(self); self.refresh()
    def eventFilter(self,watched,event):
        if watched is self.window and event.type()==QEvent.Resize:
            compact=self.window.width()<1200; self.slider.setVisible(not compact)
            self.setFixedWidth(30 if compact else 118)
            self.button.setText('▾' if compact else ''); self.button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if compact else Qt.ToolButtonIconOnly)
        return super().eventFilter(watched,event)
    def toggle(self):self.muted=not self.muted; self.refresh()
    def set_level(self,value):self.level=value; self.refresh()
    def refresh(self):
        self.button.setIcon(lucide_icon('volume-x' if self.muted or not self.level else 'volume-2'))
        self.button.setToolTip(('Unmute' if self.muted else 'Mute')+' playback · Right-click for volume')
        with QSignalBlocker(self.slider):self.slider.setValue(self.level)
        if hasattr(self.window,'transport'):
            self.window.transport.set_monitor_gain(0. if self.muted else self.level/100)
    def popup(self,*_):
        menu=QMenu(self); host=QWidget(); layout=QVBoxLayout(host); label=QLabel('Monitor'); layout.addWidget(label)
        slider=QSlider(Qt.Vertical); slider.setRange(0,100); slider.setValue(self.level); slider.setFixedHeight(140); slider.valueChanged.connect(self.set_level); layout.addWidget(slider,0,Qt.AlignHCenter)
        action=QWidgetAction(menu); action.setDefaultWidget(host); menu.addAction(action); self._menu=menu
        menu.popup(self.button.mapToGlobal(self.button.rect().bottomLeft()))
