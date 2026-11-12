"""Playback monitoring only: never writes project/export gain."""
from PySide6.QtCore import Qt,QEvent,QSignalBlocker,QPoint
from PySide6.QtWidgets import QWidget,QHBoxLayout,QToolButton,QSlider,QMenu,QWidgetAction,QVBoxLayout,QLabel
from .icons import lucide_icon
from .controls import SafeSlider as QSlider


class MonitorControl(QWidget):
    def __init__(self,window):
        super().__init__(window); self.window=window
        self.level=100; self.muted=False; self.compact=None; self._menu=None
        layout=QHBoxLayout(self); layout.setContentsMargins(4,0,8,0); layout.setSpacing(3)
        self.button=QToolButton(); self.button.setFixedSize(28,28); self.button.clicked.connect(self.activate); self.button.setContextMenuPolicy(Qt.CustomContextMenu); self.button.customContextMenuRequested.connect(self.popup)
        layout.addWidget(self.button)
        self.slider=QSlider(Qt.Horizontal); self.slider.setRange(0,100); self.slider.setValue(100); self.slider.setFixedWidth(85); self.slider.setToolTip('Playback monitor volume — does not affect exports')
        self.slider.valueChanged.connect(self.set_level); layout.addWidget(self.slider)
        window.installEventFilter(self); self.update_layout(); self.refresh()
    def eventFilter(self,watched,event):
        if watched is self.window and event.type()==QEvent.Resize:
            self.update_layout()
        return super().eventFilter(watched,event)
    def update_layout(self):
        compact=self.window.width()<1200
        if compact==self.compact:return
        self.compact=compact
        if self._menu:self._menu.close()
        self.slider.setVisible(not compact); self.setFixedWidth(40 if compact else 128)
        self.button.setToolButtonStyle(Qt.ToolButtonIconOnly); self.refresh()
    def activate(self):
        self.popup() if self.compact else self.toggle()
    def toggle(self):self.muted=not self.muted; self.refresh()
    def set_level(self,value):self.level=value; self.refresh()
    def refresh(self):
        self.button.setIcon(lucide_icon('volume-x' if self.muted or not self.level else 'volume-2'))
        tip='Playback volume · Click to adjust' if self.compact else ('Unmute' if self.muted else 'Mute')+' playback · Right-click for volume'
        self.button.setToolTip(tip); self.button.setAccessibleName('Playback volume' if self.compact else ('Unmute playback' if self.muted else 'Mute playback'))
        with QSignalBlocker(self.slider):self.slider.setValue(self.level)
        if self._menu:
            with QSignalBlocker(self.popup_slider):self.popup_slider.setValue(self.level)
            self.volume_label.setText(f'{self.level}%')
            self.mute_button.setText('Unmute' if self.muted else 'Mute')
            self.mute_button.setIcon(lucide_icon('volume-x' if self.muted else 'volume-2'))
        if hasattr(self.window,'transport'):
            self.window.transport.set_monitor_gain(0. if self.muted else self.level/100)
    def popup(self,*_):
        if self._menu and self._menu.isVisible():self._menu.close();return
        if self._menu is None:
            menu=QMenu(self); host=QWidget(); layout=QVBoxLayout(host); layout.setContentsMargins(12,10,12,10); layout.addWidget(QLabel('Playback volume'))
            self.popup_slider=QSlider(Qt.Vertical); self.popup_slider.setRange(0,100); self.popup_slider.setValue(self.level); self.popup_slider.setFixedSize(30,140); self.popup_slider.setAccessibleName('Playback volume')
            self.popup_slider.valueChanged.connect(self.set_level); layout.addWidget(self.popup_slider,0,Qt.AlignHCenter)
            self.volume_label=QLabel(); self.volume_label.setAlignment(Qt.AlignCenter); layout.addWidget(self.volume_label)
            self.mute_button=QToolButton(); self.mute_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); self.mute_button.clicked.connect(self.toggle); layout.addWidget(self.mute_button,0,Qt.AlignHCenter)
            action=QWidgetAction(menu); action.setDefaultWidget(host); menu.addAction(action); self._menu=menu
        self.refresh(); self._menu.ensurePolished(); self._menu.adjustSize()
        position=self.button.mapToGlobal(QPoint(self.button.width()//2,self.button.height()+4))
        area=self.button.screen().availableGeometry(); position.setX(max(area.left()+4,min(position.x()-self._menu.width()//2,area.right()-self._menu.width()-4)))
        self._menu.popup(position)
