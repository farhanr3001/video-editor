"""Embed scrcpy or AirPlay stream window owned by our process; display realistic phone frame."""
from __future__ import annotations

from .theme_widgets import set_ui_style, set_ui_icon
import datetime
import os
import uuid

from PySide6.QtCore import QDateTime, QPointF, QProcess, QProcessEnvironment, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient, QWindow)
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QSizePolicy, QSpacerItem,
                             QVBoxLayout, QWidget)

from .icons import lucide_icon


def stream_window(pid):
    if os.name != 'nt' or not pid: return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    pids = {pid}
    try:
        import psutil
        proc = psutil.Process(pid)
        for child in proc.children(recursive=True):
            pids.add(child.pid)
    except Exception:
        pass

    class RECT(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

    handles = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(handle, unused):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value in pids and user32.IsWindowVisible(handle):
            length = user32.GetWindowTextLengthW(handle)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, buff, length + 1)
            title = buff.value
            if 'QTrayIcon' not in title and 'Default IME' not in title:
                rect = RECT()
                user32.GetWindowRect(handle, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w >= 150 and h >= 150:
                    handles.append(handle)
        return True

    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows(visit, 0)
    return handles[0] if handles else None


def owned_window(pid):
    return stream_window(pid)


class PhoneScreenCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mirror = parent
        self.platform = 'iphone'
        self.device_name = 'iPhone 15'
        self.connected = True
        self.rotated = False
        self.mirroring = False
        self.airplay_listening = False
        self.pulse_phase = 0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self._on_tick)
        self.clock_timer.start()

    def _on_tick(self):
        self.pulse_phase = (self.pulse_phase + 1) % 4
        self.update()

    def set_platform(self, platform: str):
        self.platform = platform
        self.update()

    def set_device_info(self, name: str, connected: bool = True):
        self.device_name = name
        self.connected = connected
        self.update()

    def set_rotated(self, rotated: bool):
        self.rotated = rotated
        self.update()

    def set_mirroring(self, mirroring: bool):
        self.mirroring = mirroring
        self.update()

    def set_airplay_listening(self, listening: bool):
        self.airplay_listening = listening
        self.update()

    def get_screen_rect(self) -> QRectF:
        vw, vh = self.width(), self.height()
        base_w, base_h = (580, 290) if self.rotated else (290, 580)
        scale = min((vw - 20) / base_w, (vh - 20) / base_h, 1.15)
        scale = max(scale, 0.55)
        pw, ph = base_w * scale, base_h * scale
        x = (vw - pw) / 2
        y = (vh - ph) / 2
        return QRectF(x + 5 * scale, y + 5 * scale, pw - 10 * scale, ph - 10 * scale)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        vw, vh = self.width(), self.height()
        base_w, base_h = (580, 290) if self.rotated else (290, 580)
        scale = min((vw - 20) / base_w, (vh - 20) / base_h, 1.15)
        scale = max(scale, 0.55)
        pw, ph = base_w * scale, base_h * scale
        x = (vw - pw) / 2
        y = (vh - ph) / 2

        # Outer Titanium frame
        outer_rect = QRectF(x, y, pw, ph)
        corner_r = 38 * scale
        outer_pen = QPen(QColor('#383e48'), 3 * scale)
        p.setPen(outer_pen)
        p.setBrush(QColor('#1c1e24'))
        p.drawRoundedRect(outer_rect, corner_r, corner_r)

        # Subtle frame edge highlight
        highlight_pen = QPen(QColor('#555f6e'), 1 * scale)
        p.setPen(highlight_pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(outer_rect.adjusted(1.5, 1.5, -1.5, -1.5), corner_r - 1.5, corner_r - 1.5)

        # Screen area
        screen_r = corner_r - 4 * scale
        screen_rect = QRectF(x + 5 * scale, y + 5 * scale, pw - 10 * scale, ph - 10 * scale)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(screen_rect, screen_r, screen_r)
        p.setClipPath(clip_path)

        if not self.mirroring:
            if not self.connected:
                # Disconnected State
                p.fillRect(screen_rect, QColor('#0f1117'))
                center_y = screen_rect.center().y()

                badge_size = 46 * scale
                badge_rect = QRectF(screen_rect.center().x() - badge_size / 2, center_y - 65 * scale, badge_size, badge_size)
                p.setBrush(QColor('#261619'))
                p.setPen(QPen(QColor('#ef4444'), 1.5 * scale))
                p.drawEllipse(badge_rect)

                p.setPen(QColor('#ef4444'))
                p.setFont(QFont('Segoe UI', max(int(14 * scale), 9), QFont.Bold))
                p.drawText(badge_rect, Qt.AlignCenter, '✕')

                p.setPen(QColor('#f87171'))
                p.setFont(QFont('Segoe UI', max(int(13 * scale), 9), QFont.Bold))
                p.drawText(QRectF(screen_rect.x(), center_y - 8 * scale, screen_rect.width(), 22 * scale),
                           Qt.AlignCenter, f"{self.device_name} Disconnected")

                p.setPen(QColor('#94a3b8'))
                p.setFont(QFont('Segoe UI', max(int(10 * scale), 8)))
                p.drawText(QRectF(screen_rect.x(), center_y + 16 * scale, screen_rect.width(), 20 * scale),
                           Qt.AlignCenter, "Tap 'Reconnect' below to pair device")

            elif self.airplay_listening:
                # AirPlay Listening / Waiting for stream state
                bg_grad = QLinearGradient(screen_rect.topLeft(), screen_rect.bottomRight())
                bg_grad.setColorAt(0.0, QColor('#0a1120'))
                bg_grad.setColorAt(0.5, QColor('#111d35'))
                bg_grad.setColorAt(1.0, QColor('#070b14'))
                p.fillRect(screen_rect, bg_grad)

                # Ambient cyan/blue glow
                glow = QRadialGradient(screen_rect.center().x(), screen_rect.center().y() - 20 * scale, 160 * scale)
                glow.setColorAt(0.0, QColor(59, 130, 246, 75))
                glow.setColorAt(0.6, QColor(37, 99, 235, 30))
                glow.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.fillRect(screen_rect, glow)

                # AirPlay icon & Title
                top_y = screen_rect.y() + (55 * scale if not self.rotated else 24 * scale)
                icon_box = QRectF(screen_rect.center().x() - 24 * scale, top_y, 48 * scale, 48 * scale)
                p.setBrush(QColor(30, 58, 138, 120))
                p.setPen(QPen(QColor('#60a5fa'), 1.5 * scale))
                p.drawRoundedRect(icon_box, 10 * scale, 10 * scale)

                p.setPen(QColor('#93c5fd'))
                p.setFont(QFont('Segoe UI', max(int(18 * scale), 10), QFont.Bold))
                p.drawText(icon_box, Qt.AlignCenter, '⧉')

                p.setPen(QColor('#ffffff'))
                p.setFont(QFont('Segoe UI', max(int(13 * scale), 9), QFont.Bold))
                p.drawText(QRectF(screen_rect.x(), top_y + 54 * scale, screen_rect.width(), 22 * scale),
                           Qt.AlignCenter, "AirPlay Mirroring Active")

                # Step-by-step instructions box
                box_w = screen_rect.width() - 36 * scale
                box_h = 135 * scale
                guide_box = QRectF(screen_rect.x() + 18 * scale, top_y + 84 * scale, box_w, box_h)
                p.setBrush(QColor(15, 23, 42, 180))
                p.setPen(QPen(QColor('#334155'), 1 * scale))
                p.drawRoundedRect(guide_box, 8 * scale, 8 * scale)

                steps = [
                    "1. Swipe down from top-right corner",
                    "2. Tap Screen Mirroring  [ ⧉ ]",
                    "3. Select this PC to stream live"
                ]
                step_y = guide_box.y() + 14 * scale
                for step in steps:
                    p.setPen(QColor('#e2e8f0'))
                    p.setFont(QFont('Segoe UI', max(int(9.5 * scale), 8), QFont.Medium))
                    p.drawText(QRectF(guide_box.x() + 12 * scale, step_y, box_w - 24 * scale, 24 * scale),
                               Qt.AlignLeft | Qt.AlignVCenter, step)
                    step_y += 36 * scale

                # Pulsing connection status
                dots = '.' * (self.pulse_phase + 1)
                p.setPen(QColor('#4ade80'))
                p.setFont(QFont('Segoe UI', max(int(10 * scale), 8), QFont.Bold))
                p.drawText(QRectF(screen_rect.x(), guide_box.bottom() + 18 * scale, screen_rect.width(), 20 * scale),
                           Qt.AlignCenter, f"● Waiting for iPhone connection{dots}")

            else:
                # Standard connected lockscreen wallpaper
                bg_grad = QLinearGradient(screen_rect.topLeft(), screen_rect.bottomRight())
                if self.platform == 'iphone':
                    bg_grad.setColorAt(0.0, QColor('#0f1118'))
                    bg_grad.setColorAt(0.4, QColor('#1e1422'))
                    bg_grad.setColorAt(0.7, QColor('#2b141d'))
                    bg_grad.setColorAt(1.0, QColor('#0a0d14'))
                else:
                    bg_grad.setColorAt(0.0, QColor('#0b1716'))
                    bg_grad.setColorAt(0.5, QColor('#112423'))
                    bg_grad.setColorAt(1.0, QColor('#0a0e14'))
                p.fillRect(screen_rect, bg_grad)

                # Ambient warm radial glows
                if self.platform == 'iphone':
                    glow1 = QRadialGradient(screen_rect.center().x(), screen_rect.center().y() + 30 * scale, 150 * scale)
                    glow1.setColorAt(0.0, QColor(245, 110, 60, 110))
                    glow1.setColorAt(0.5, QColor(190, 50, 90, 50))
                    glow1.setColorAt(1.0, QColor(0, 0, 0, 0))
                    p.fillRect(screen_rect, glow1)

                    glow2 = QRadialGradient(screen_rect.center().x() - 40 * scale, screen_rect.center().y() - 50 * scale, 120 * scale)
                    glow2.setColorAt(0.0, QColor(140, 70, 180, 70))
                    glow2.setColorAt(1.0, QColor(0, 0, 0, 0))
                    p.fillRect(screen_rect, glow2)

                now = QDateTime.currentDateTime()
                date_str = now.toString('dddd d MMMM')
                time_str = now.toString('HH:mm')

                # Date & Clock
                p.setPen(QColor('#e2e8f0'))
                font_date = QFont('Segoe UI', max(int(9 * scale), 8), QFont.Medium)
                p.setFont(font_date)
                date_y = screen_rect.y() + (58 * scale if not self.rotated else 28 * scale)
                p.drawText(QRectF(screen_rect.x(), date_y, screen_rect.width(), 18 * scale), Qt.AlignCenter, date_str)

                font_clock = QFont('Segoe UI', max(int(36 * scale), 18), QFont.Bold)
                p.setFont(font_clock)
                clock_y = date_y + 18 * scale
                p.drawText(QRectF(screen_rect.x(), clock_y, screen_rect.width(), 46 * scale), Qt.AlignCenter, time_str)

                # Flashlight & Camera shortcut circles
                if not self.rotated:
                    btn_size = 38 * scale
                    pad_x = 24 * scale
                    bottom_y = screen_rect.bottom() - 44 * scale

                    # Flashlight (left)
                    fl_rect = QRectF(screen_rect.left() + pad_x, bottom_y, btn_size, btn_size)
                    p.setBrush(QColor(255, 255, 255, 45))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(fl_rect)
                    p.setPen(QColor('#ffffff'))
                    p.setFont(QFont('Segoe UI', max(int(11 * scale), 8)))
                    p.drawText(fl_rect, Qt.AlignCenter, '🔦')

                    # Camera (right)
                    cam_rect = QRectF(screen_rect.right() - pad_x - btn_size, bottom_y, btn_size, btn_size)
                    p.setBrush(QColor(255, 255, 255, 45))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(cam_rect)
                    p.setPen(QColor('#ffffff'))
                    p.drawText(cam_rect, Qt.AlignCenter, '📷')

            # Home indicator bar
            p.setBrush(QColor(255, 255, 255, 180))
            p.setPen(Qt.NoPen)
            bar_w = 95 * scale
            bar_h = 3.5 * scale
            p.drawRoundedRect(QRectF(x + (pw - bar_w) / 2, screen_rect.bottom() - 10 * scale, bar_w, bar_h), 2, 2)

        # Dynamic Island (iPhone) or Punch-hole camera (Android)
        p.setClipping(False)
        if self.platform == 'iphone' and not self.rotated:
            island_w = 82 * scale
            island_h = 22 * scale
            island_rect = QRectF(x + (pw - island_w) / 2, y + 13 * scale, island_w, island_h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#000000'))
            p.drawRoundedRect(island_rect, 11 * scale, 11 * scale)

            # Subtle sensor reflections
            p.setBrush(QColor('#151820'))
            p.drawEllipse(QPointF(island_rect.left() + 18 * scale, island_rect.center().y()), 4.5 * scale, 4.5 * scale)
            p.setBrush(QColor('#102230'))
            p.drawEllipse(QPointF(island_rect.right() - 20 * scale, island_rect.center().y()), 4 * scale, 4 * scale)
        elif self.platform == 'android' and not self.rotated:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#000000'))
            p.drawEllipse(QPointF(x + pw / 2, y + 16 * scale), 5 * scale, 5 * scale)

        p.end()

    def mousePressEvent(self, event):
        if hasattr(self, 'mirror') and self.mirror and self.mirror.container:
            self.mirror.container.setFocus()
            if self.mirror.foreign:
                self.mirror.foreign.requestActivate()
        super().mousePressEvent(event)

class PhoneMirrorPopoutWindow(QWidget):
    def __init__(self, mirror: PhoneMirror):
        super().__init__(None, Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.mirror = mirror
        self.setObjectName('phoneMirrorPopout')
        self.setWindowTitle(f'Kinetic Cut Mirror · {mirror.device_name}')
        self.setWindowIcon(lucide_icon('smartphone', '#60a5fa'))
        self.resize(420, 740)
        self.setMinimumSize(300, 480)
        set_ui_style(self, '''
            QWidget#phoneMirrorPopout {
                background: @bg_panel;
            }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # Top bar
        top_bar = QHBoxLayout()
        self.title_lbl = QLabel(mirror.device_name)
        set_ui_style(self.title_lbl, 'font-size: 14px; font-weight: 600; color: @text_main;')
        top_bar.addWidget(self.title_lbl)

        self.status_dot = QLabel('●')
        set_ui_style(self.status_dot, f"color: {'@success' if mirror.connected else '@danger'}; font-size: 12px; margin-left: 4px;")
        top_bar.addWidget(self.status_dot)
        top_bar.addStretch()

        btn_style = '''
            QPushButton { border: 1px solid @border_subtle; border-radius: 4px; background: @bg_panel; color: @text_main; padding: 4px 8px; font-size: 11px; }
            QPushButton:hover { background: @bg_hover; border-color: @accent; color: @text_main; }
            QPushButton:pressed { background: @bg_panel; }
        '''

        btn_rotate = QPushButton()
        btn_rotate.setIcon(lucide_icon('rotate-cw', '#94a3b8', 14))
        btn_rotate.setToolTip('Rotate')
        btn_rotate.setFixedSize(28, 28)
        btn_rotate.setCursor(Qt.PointingHandCursor)
        set_ui_style(btn_rotate, btn_style)
        btn_rotate.clicked.connect(mirror._rotate)
        top_bar.addWidget(btn_rotate)

        btn_screenshot = QPushButton()
        btn_screenshot.setIcon(lucide_icon('camera', '#94a3b8', 14))
        btn_screenshot.setToolTip('Screenshot')
        btn_screenshot.setFixedSize(28, 28)
        btn_screenshot.setCursor(Qt.PointingHandCursor)
        set_ui_style(btn_screenshot, btn_style)
        btn_screenshot.clicked.connect(mirror._screenshot)
        top_bar.addWidget(btn_screenshot)

        self.btn_dock = QPushButton('  Dock Back')
        self.btn_dock.setIcon(lucide_icon('minimize-2', '#60a5fa', 14))
        self.btn_dock.setToolTip('Dock mirror back into Kinetic Cut')
        set_ui_style(self.btn_dock, btn_style)
        self.btn_dock.setCursor(Qt.PointingHandCursor)
        self.btn_dock.clicked.connect(mirror.dock_back)
        top_bar.addWidget(self.btn_dock)

        layout.addLayout(top_bar)

        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.content_layout, 1)

    def set_canvas(self, canvas):
        self.content_layout.addWidget(canvas, 1)

    def update_info(self, name: str, connected: bool):
        self.title_lbl.setText(name)
        self.setWindowTitle(f'Kinetic Cut Mirror · {name}')
        set_ui_style(self.status_dot, f"color: {'@success' if connected else '@danger'}; font-size: 12px; margin-left: 4px;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self.mirror, 'container') and self.mirror.container:
            s_rect = self.mirror.canvas.get_screen_rect()
            self.mirror.container.setGeometry(int(s_rect.x()), int(s_rect.y()), int(s_rect.width()), int(s_rect.height()))

    def closeEvent(self, event):
        top = self.mirror.window()
        is_phone_page = getattr(top, 'current_page', None) == 2
        self.mirror.dock_back()
        if not is_phone_page:
            self.mirror.stop(immediate=True)
        event.accept()


class PhoneMirror(QWidget):
    status = Signal(str)
    activeChanged = Signal(bool)
    disconnectRequested = Signal()
    reconnectRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('phoneMirror')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.platform = 'iphone'
        self.device_name = 'iPhone 15'
        self.connected = True
        self.rotated = False
        self.airplay_active = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        # Header Bar: Device name + Connected status dot + Tools
        top_bar = QHBoxLayout()
        self.device_title = QLabel('iPhone 15')
        set_ui_style(self.device_title, 'font-size: 15px; font-weight: 600; color: @text_main;')
        top_bar.addWidget(self.device_title)

        self.status_dot = QLabel('●')
        set_ui_style(self.status_dot, 'color: @success; font-size: 12px; margin-left: 4px;')
        top_bar.addWidget(self.status_dot)

        self.status_label = QLabel('Connected')
        set_ui_style(self.status_label, 'color: @success; font-size: 12px; font-weight: 500;')
        top_bar.addWidget(self.status_label)
        top_bar.addStretch()

        self.btn_recenter = QPushButton()
        self.btn_recenter.setIcon(lucide_icon('crosshair', '#94a3b8'))
        self.btn_recenter.setToolTip('Re-center screen')
        self.btn_recenter.setFixedSize(28, 28)
        self.btn_recenter.setCursor(Qt.PointingHandCursor)
        set_ui_style(self.btn_recenter, '''
            QPushButton { border: 1px solid @border_subtle; border-radius: 4px; background: @bg_panel; }
            QPushButton:hover { background: @bg_hover; border-color: @accent; }
            QPushButton:pressed { background: @bg_panel; }
        ''')
        self.btn_recenter.clicked.connect(self._recenter)
        top_bar.addWidget(self.btn_recenter)

        self.btn_fullscreen_top = QPushButton()
        self.btn_fullscreen_top.setIcon(lucide_icon('maximize-2', '#94a3b8'))
        self.btn_fullscreen_top.setToolTip('Fullscreen preview')
        self.btn_fullscreen_top.setFixedSize(28, 28)
        self.btn_fullscreen_top.setCursor(Qt.PointingHandCursor)
        set_ui_style(self.btn_fullscreen_top, '''
            QPushButton { border: 1px solid @border_subtle; border-radius: 4px; background: @bg_panel; }
            QPushButton:hover { background: @bg_hover; border-color: @accent; }
            QPushButton:pressed { background: @bg_panel; }
        ''')
        self.btn_fullscreen_top.clicked.connect(self._fullscreen)
        top_bar.addWidget(self.btn_fullscreen_top)

        self.btn_popout = QPushButton()
        self.btn_popout.setIcon(lucide_icon('external-link', '#94a3b8'))
        self.btn_popout.setToolTip('Pop out mirror into standalone window')
        self.btn_popout.setFixedSize(28, 28)
        self.btn_popout.setCursor(Qt.PointingHandCursor)
        set_ui_style(self.btn_popout, '''
            QPushButton { border: 1px solid @border_subtle; border-radius: 4px; background: @bg_panel; }
            QPushButton:hover { background: @bg_hover; border-color: @accent; }
            QPushButton:pressed { background: @bg_panel; }
        ''')
        self.btn_popout.clicked.connect(self.toggle_popout)
        top_bar.addWidget(self.btn_popout)

        root.addLayout(top_bar)

        self.root_layout = root
        self.is_popped_out = False
        self.popout_window = None

        # Center Phone Canvas
        self.canvas = PhoneScreenCanvas(self)
        root.addWidget(self.canvas, 1)

        # Placeholder when canvas is popped out into standalone window
        self.popout_placeholder = QFrame()
        set_ui_style(self.popout_placeholder, 'background: @bg_panel; border: 1px dashed @border_subtle; border-radius: 12px;')
        ph_layout = QVBoxLayout(self.popout_placeholder)
        ph_layout.setAlignment(Qt.AlignCenter)
        ph_layout.setSpacing(12)
        ph_icon = QLabel()
        set_ui_icon(ph_icon, 'smartphone', '#60a5fa', 44)
        ph_icon.setAlignment(Qt.AlignCenter)
        ph_layout.addWidget(ph_icon)
        ph_title = QLabel('Mirror is popped out')
        set_ui_style(ph_title, 'font-size: 15px; font-weight: 700; color: @text_main;')
        ph_title.setAlignment(Qt.AlignCenter)
        ph_layout.addWidget(ph_title)
        ph_sub = QLabel('Live phone mirror is running in a separate window.\nYou can navigate to Edit or Deliver while keeping your phone screen active.')
        set_ui_style(ph_sub, 'font-size: 11px; color: @text_sub;')
        ph_sub.setAlignment(Qt.AlignCenter)
        ph_layout.addWidget(ph_sub)
        self.btn_dock_placeholder = QPushButton('  Dock Mirror Back Here')
        self.btn_dock_placeholder.setIcon(lucide_icon('minimize-2', '#60a5fa', 14))
        set_ui_style(self.btn_dock_placeholder, '''
            QPushButton { padding: 8px 18px; border-radius: 6px; background: @bg_panel; border: 1px solid @accent; color: @info; font-weight: 600; font-size: 12px; }
            QPushButton:hover { background: @bg_hover; border-color: @accent; color: @text_main; }
            QPushButton:pressed { background: @bg_panel; }
        ''')
        self.btn_dock_placeholder.setCursor(Qt.PointingHandCursor)
        self.btn_dock_placeholder.clicked.connect(self.dock_back)
        ph_layout.addWidget(self.btn_dock_placeholder, 0, Qt.AlignCenter)
        root.addWidget(self.popout_placeholder, 1)
        self.popout_placeholder.hide()

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)
        bottom_bar.addStretch()

        btn_style = '''
            QPushButton {
                padding: 6px 14px;
                border-radius: 6px;
                background: @bg_panel;
                border: 1px solid @border_subtle;
                color: @text_main;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: @bg_hover;
                border-color: @accent;
                color: @text_main;
            }
            QPushButton:pressed {
                background: @bg_panel;
            }
        '''

        self.btn_screenshot = QPushButton('  Screenshot')
        self.btn_screenshot.setIcon(lucide_icon('camera', '#94a3b8', 14))
        self.btn_screenshot.setCursor(Qt.PointingHandCursor)
        set_ui_style(self.btn_screenshot, btn_style)
        self.btn_screenshot.clicked.connect(self._screenshot)
        bottom_bar.addWidget(self.btn_screenshot)

        self.btn_rotate = QPushButton('  Rotate')
        self.btn_rotate.setIcon(lucide_icon('rotate-cw', '#94a3b8', 14))
        self.btn_rotate.setCursor(Qt.PointingHandCursor)
        set_ui_style(self.btn_rotate, btn_style)
        self.btn_rotate.clicked.connect(self._rotate)
        bottom_bar.addWidget(self.btn_rotate)

        self.btn_fullscreen = QPushButton('  Fullscreen')
        self.btn_fullscreen.setIcon(lucide_icon('maximize-2', '#94a3b8', 14))
        self.btn_fullscreen.setCursor(Qt.PointingHandCursor)
        set_ui_style(self.btn_fullscreen, btn_style)
        self.btn_fullscreen.clicked.connect(self._fullscreen)
        bottom_bar.addWidget(self.btn_fullscreen)

        self.btn_disconnect = QPushButton('  Disconnect')
        self.btn_disconnect.setCursor(Qt.PointingHandCursor)
        self.btn_disconnect.clicked.connect(self._on_disconnect_click)
        bottom_bar.addWidget(self.btn_disconnect)

        bottom_bar.addStretch()
        root.addLayout(bottom_bar)

        self._update_disconnect_button(True)

        # Process management
        self.process = QProcess(self)
        self.process.readyReadStandardError.connect(self._log)
        self.process.readyReadStandardOutput.connect(self._log)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._embed)
        self.container = None
        self.foreign = None
        self.attempts = 0
        self.logs = ''
        self.stopping = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.container:
            s_rect = self.canvas.get_screen_rect()
            self.container.setGeometry(int(s_rect.x()), int(s_rect.y()), int(s_rect.width()), int(s_rect.height()))

    def set_platform(self, platform: str):
        self.platform = platform
        self.canvas.set_platform(platform)
        if platform == 'iphone':
            self.device_title.setText(self.device_name if self.connected else 'iPhone 15')
        else:
            self.device_title.setText(self.device_name if self.connected else 'Android Device')

    def set_device_info(self, name: str, connected: bool = True):
        self.device_name = name
        self.connected = connected
        self.device_title.setText(name)
        set_ui_style(self.status_dot, f"color: {'@success' if connected else '@danger'}; font-size: 12px; margin-left: 4px;")
        self.status_label.setText('Connected' if connected else 'Disconnected')
        set_ui_style(self.status_label, f"color: {'@success' if connected else '@danger'}; font-size: 12px; font-weight: 500;")
        self.canvas.set_device_info(name, connected)
        self._update_disconnect_button(connected)
        if hasattr(self, 'popout_window') and self.popout_window:
            self.popout_window.update_info(name, connected)

    def toggle_popout(self):
        if self.is_popped_out:
            self.dock_back()
        else:
            self.pop_out()

    def pop_out(self):
        if self.is_popped_out: return
        self.is_popped_out = True
        if not self.popout_window:
            self.popout_window = PhoneMirrorPopoutWindow(self)
        self.popout_window.update_info(self.device_name, self.connected)
        self.canvas.setParent(self.popout_window)
        self.popout_window.set_canvas(self.canvas)
        self.canvas.show()
        self.popout_placeholder.show()
        self.btn_popout.setIcon(lucide_icon('minimize-2', '#60a5fa'))
        self.btn_popout.setToolTip('Dock mirror back into page')
        self.popout_window.show()
        self.popout_window.raise_()
        self.popout_window.activateWindow()
        if self.container:
            s_rect = self.canvas.get_screen_rect()
            self.container.setGeometry(int(s_rect.x()), int(s_rect.y()), int(s_rect.width()), int(s_rect.height()))
            self.container.show()
            self.container.raise_()
            self.container.setFocus()

    def dock_back(self):
        if not self.is_popped_out: return
        self.is_popped_out = False
        if self.popout_window:
            self.popout_window.hide()
        self.popout_placeholder.hide()
        self.canvas.setParent(self)
        self.root_layout.insertWidget(1, self.canvas, 1)
        self.canvas.show()
        self.btn_popout.setIcon(lucide_icon('external-link', '#94a3b8'))
        self.btn_popout.setToolTip('Pop out mirror into standalone window')
        if self.container:
            s_rect = self.canvas.get_screen_rect()
            self.container.setGeometry(int(s_rect.x()), int(s_rect.y()), int(s_rect.width()), int(s_rect.height()))
            self.container.show()
            self.container.raise_()
            self.container.setFocus()

    def _update_disconnect_button(self, connected: bool):
        if connected:
            self.btn_disconnect.setText('  Disconnect')
            self.btn_disconnect.setIcon(lucide_icon('power', '#ef4444', 14))
            set_ui_style(self.btn_disconnect, '''
                QPushButton {
                    padding: 6px 14px;
                    border-radius: 6px;
                    background: @danger_bg;
                    border: 1px solid @border_subtle;
                    color: @danger;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: @danger_bg;
                    border-color: @accent;
                    color: @text_main;
                }
                QPushButton:pressed {
                    background: @danger_bg;
                }
            ''')
            self.btn_disconnect.setToolTip('Disconnect phone')
        else:
            self.btn_disconnect.setText('  Reconnect')
            self.btn_disconnect.setIcon(lucide_icon('refresh-cw', '#22c55e', 14))
            set_ui_style(self.btn_disconnect, '''
                QPushButton {
                    padding: 6px 14px;
                    border-radius: 6px;
                    background: @success_bg;
                    border: 1px solid @accent;
                    color: @success;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: @success_bg;
                    border-color: @accent;
                    color: @text_main;
                }
                QPushButton:pressed {
                    background: @success_bg;
                }
            ''')
            self.btn_disconnect.setToolTip('Reconnect to phone')

    def _on_disconnect_click(self):
        if self.connected:
            self.stop()
            self.set_device_info(self.device_name, connected=False)
            self.disconnectRequested.emit()
            self.status.emit('Phone disconnected. Tap Reconnect to pair again.')
        else:
            self.status.emit('Reconnecting to phone…')
            self.reconnectRequested.emit()

    def _recenter(self):
        self.canvas.update()

    def _rotate(self):
        self.rotated = not self.rotated
        self.canvas.set_rotated(self.rotated)
        if self.container:
            s_rect = self.canvas.get_screen_rect()
            self.container.setGeometry(int(s_rect.x()), int(s_rect.y()), int(s_rect.width()), int(s_rect.height()))

    def _fullscreen(self):
        top = self.window()
        if top.isFullScreen():
            top.showNormal()
        else:
            top.showFullScreen()

    def _screenshot(self):
        pixmap = self.canvas.grab()
        pictures_dir = os.path.expanduser('~/Pictures')
        path, _ = QFileDialog.getSaveFileName(self, 'Save Phone Screenshot',
                                             os.path.join(pictures_dir, f'phone_screenshot_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.png'),
                                             'PNG Image (*.png)')
        if path:
            pixmap.save(path)
            self.status.emit(f'Screenshot saved to {os.path.basename(path)}')

    def is_mirroring(self):
        return self.process.state() != QProcess.NotRunning or self.canvas.mirroring or self.airplay_active

    def start(self, executable, adb, serial):
        if self.process.state() != QProcess.NotRunning: return
        self.logs = ''; self.attempts = 0; self.stopping = False; self.airplay_active = False
        self.canvas.set_airplay_listening(False)
        env = QProcessEnvironment.systemEnvironment(); env.insert('ADB', adb)
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(os.path.dirname(executable))
        args = [
            '--serial=' + serial,
            '--window-title=Kinetic Cut Phone ' + uuid.uuid4().hex[:8],
            '--window-borderless',
            '--no-window-aspect-ratio-lock',
            '--max-size=1440',
            '--max-fps=60',
            '--stay-awake',
        ]
        self.process.start(executable, args)
        self.timer.setInterval(100)
        self.timer.start()
        self.activeChanged.emit(True)
        self.status.emit('Starting scrcpy mirror… authorize on the phone if prompted.')

    def start_airplay(self, executable, device_name='iPhone'):
        if self.process.state() != QProcess.NotRunning: return
        self.logs = ''; self.attempts = 0; self.stopping = False; self.airplay_active = True
        self.canvas.set_airplay_listening(True)
        self.process.setWorkingDirectory(os.path.dirname(executable))
        self.process.start(executable, [])
        self.timer.setInterval(100)
        self.timer.start()
        self.activeChanged.emit(True)
        self.status.emit('AirPlay receiver active · On iPhone, open Control Center and tap Screen Mirroring')

    def _log(self):
        self.logs = (self.logs + bytes(self.process.readAllStandardError()).decode('utf-8', 'replace') +
                     bytes(self.process.readAllStandardOutput()).decode('utf-8', 'replace'))[-4000:]

    def _embed(self):
        self.attempts += 1
        pid = int(self.process.processId()) if self.process.processId() else None
        handle = stream_window(pid) if pid else None
        if handle:
            self.foreign = QWindow.fromWinId(handle)
            if self.foreign:
                self.container = QWidget.createWindowContainer(self.foreign, self.canvas)
                self.container.setFocusPolicy(Qt.StrongFocus)
                s_rect = self.canvas.get_screen_rect()
                self.container.setGeometry(int(s_rect.x()), int(s_rect.y()), int(s_rect.width()), int(s_rect.height()))
                self.container.show()
                self.container.setFocus()
                self.foreign.requestActivate()
                self.canvas.set_mirroring(True)
                self.timer.stop()
                msg = 'Live iPhone AirPlay screen mirroring active.' if self.airplay_active else 'Live Android mirror active · click inside screen to control with mouse & keyboard.'
                self.status.emit(msg)
        elif self.attempts >= 150 and not self.airplay_active:
            self.timer.stop()
            self.status.emit('Could not embed scrcpy window. Check external window or Stop and retry.')
        elif self.attempts >= 300 and self.airplay_active:
            self.timer.setInterval(500)

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self.timer.stop()
            self.airplay_active = False
            self.canvas.set_airplay_listening(False)
            self.activeChanged.emit(False)
            self.status.emit('Mirroring could not start: ' + self.process.errorString())

    def _finished(self, *_):
        self.timer.stop()
        self._log()
        self.airplay_active = False
        self.canvas.set_airplay_listening(False)
        if self.container:
            self.container.hide()
            self.container.setParent(None)
            self.container.deleteLater()
            self.container = None
        if self.foreign:
            try:
                self.foreign.setVisible(False)
                handle = int(self.foreign.winId()) if self.foreign else None
                if os.name == 'nt' and handle:
                    import ctypes
                    ctypes.windll.user32.ShowWindow(handle, 0)
            except Exception:
                pass
            self.foreign = None
        self.canvas.set_mirroring(False)
        self.activeChanged.emit(False)
        self.status.emit('Mirroring stopped.' if self.stopping else 'Mirror disconnected. ' + self.logs[-700:])

    def stop(self, immediate=False):
        self.stopping = True
        self.timer.stop()
        self.airplay_active = False
        self.canvas.set_airplay_listening(False)
        if self.container:
            self.container.hide()
            self.container.setParent(None)
            self.container.deleteLater()
            self.container = None
        if self.foreign:
            try:
                self.foreign.setVisible(False)
                handle = int(self.foreign.winId()) if self.foreign else None
                if os.name == 'nt' and handle:
                    import ctypes
                    ctypes.windll.user32.ShowWindow(handle, 0)
            except Exception:
                pass
            self.foreign = None
        self.canvas.set_mirroring(False)
        if self.process.state() != QProcess.NotRunning:
            if immediate:
                self.process.kill()
                self.process.waitForFinished(100)
            else:
                self.process.terminate()
                QTimer.singleShot(1000, self, self._kill_if_running)
        self.activeChanged.emit(False)

    def _kill_if_running(self):
        if self.stopping and self.process.state() != QProcess.NotRunning:
            self.process.kill()

    def shutdown(self):
        if self.is_popped_out:
            self.dock_back()
        self.stop(immediate=True)
