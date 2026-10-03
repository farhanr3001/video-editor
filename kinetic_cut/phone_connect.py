"""Phone Connect workspace matching user mockup. No edit-model mutation or cloud transport."""
from __future__ import annotations

from .theme_widgets import set_ui_style, set_ui_icon
import copy
import os
import posixpath
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSplitter, QStackedWidget, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QHeaderView)

from .config import save_settings
from .icons import lucide_icon
from .phone_common import PhoneError, device_name, local_name, remote_path, size_text
from .phone_process import PhoneRequest, tool_path
from .phone_mirror import PhoneMirror


APPLE_SETUP = 'https://support.apple.com/guide/devices-windows/transfer-files-between-your-devices-mchl4bd77d3a/windows'
ANDROID_SETUP = 'https://developer.android.com/tools/adb#Enabling'


class FileDrop(QFrame):
    filesDropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName('phoneDrop')
        self.setAcceptDrops(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel()
        set_ui_icon(icon_lbl, 'cloud-upload', '#60a5fa', 20)
        layout.addWidget(icon_lbl)

        title = QLabel('Drag & drop files here to upload to this folder')
        set_ui_style(title, 'font-size: 12px; font-weight: 500; color: @text_main;')
        layout.addWidget(title)
        self.setFixedHeight(46)

    def dragEnterEvent(self, event):
        if self.isEnabled() and event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            self.setProperty('hover', True); self.style().unpolish(self); self.style().polish(self)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._reset(); event.accept()

    def _reset(self):
        self.setProperty('hover', False); self.style().unpolish(self); self.style().polish(self)

    def dropEvent(self, event):
        self._reset()
        if not self.isEnabled(): return
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths: self.filesDropped.emit(paths); event.acceptProposedAction()


def label(text, style=''):
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setMinimumWidth(0)
    if style: set_ui_style(widget, style)
    return widget


def action(text, callback, icon=None):
    button = QPushButton(text)
    if icon: button.setIcon(lucide_icon(icon, '#9dc7e7'))
    button.clicked.connect(callback)
    button.setMinimumHeight(32)
    button.setCursor(Qt.PointingHandCursor)
    button.setProperty('class', 'utilityBtn')
    return button


class PhoneConnectPage(QWidget):
    def __init__(self, window, request_factory=PhoneRequest):
        super().__init__()
        self.window_ = window
        self.settings = window.settings
        self.request_factory = request_factory
        self.platform = 'iphone'
        self.device = None
        self.location = None
        self.path = ''
        self.generation = 0
        self.pending = None
        self.requests = set()
        self.jobs = []
        self.active_job = None
        self.closed = False
        self.loaded = False
        self.folder_ready = False
        self.staged_files = []
        self.setObjectName('phoneConnect')
        self.setAttribute(Qt.WA_StyledBackground, True)
        set_ui_style(self, '''
            QWidget#phoneConnect { background:@bg_panel; }
            QFrame.panelCard { background:@bg_panel; border:1px solid @border_subtle; border-radius:8px; }
            QFrame#connectedCard { background:@success_bg; border:none; border-radius:8px; }
            QFrame#phoneDrop { border:1px dashed @border_subtle; border-radius:8px; background:@bg_panel; }
            QFrame#phoneDrop[hover="true"] { border:2px solid @accent; background:@bg_panel; }

            QPushButton.segmentedBtn {
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                border: 1px solid @border_subtle;
                background: @bg_panel;
                color: @text_main;
            }
            QPushButton.segmentedBtn:hover {
                background: @bg_hover;
                border-color: @accent;
                color: @text_main;
            }
            QPushButton.segmentedBtn:checked {
                border: 1px solid @accent;
                background: @bg_selected;
                color: @text_selected;
            }
            QPushButton.segmentedBtn:checked:hover {
                background: @danger_bg;
                border-color: @accent;
            }

            QPushButton.actionCard {
                text-align: left;
                padding: 10px 14px;
                border-radius: 8px;
                border: 1px solid @border_subtle;
                background: @bg_panel;
                color: @text_main;
                font-weight: 500;
            }
            QPushButton.actionCard:hover {
                background: @bg_hover;
                border: 1px solid @accent;
                color: @text_main;
            }
            QPushButton.actionCard:pressed {
                background: @bg_panel;
                border-color: @accent;
            }
            QPushButton.actionCard:disabled {
                background: @bg_panel;
                border-color: @border_subtle;
                color: @text_disabled;
            }

            QPushButton.categoryBtn {
                text-align: left;
                padding: 9px 14px;
                border-radius: 6px;
                border: 1px solid @border_subtle;
                background: @bg_panel;
                color: @text_main;
                font-weight: 500;
            }
            QPushButton.categoryBtn:hover {
                background: @bg_hover;
                border: 1px solid @accent;
                color: @text_main;
            }
            QPushButton.categoryBtn:pressed {
                background: @bg_panel;
                border-color: @accent;
            }

            QPushButton.utilityBtn {
                padding: 6px 12px;
                border-radius: 6px;
                background: @bg_panel;
                border: 1px solid @border_subtle;
                color: @text_main;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton.utilityBtn:hover {
                background: @bg_hover;
                border-color: @accent;
                color: @text_main;
            }
            QPushButton.utilityBtn:pressed {
                background: @bg_panel;
            }
            QPushButton.utilityBtn:disabled {
                background: @bg_panel;
                border-color: @border_subtle;
                color: @text_disabled;
            }

            QFrame#driveCard {
                background: @bg_panel;
                border: 1px solid @border_subtle;
                border-radius: 8px;
            }
            QFrame#driveCard:hover {
                background: @bg_hover;
                border-color: @accent;
            }

            QPushButton.crumbBtn {
                background: transparent;
                border: 1px solid transparent;
                color: @text_sub;
                font-size: 12px;
                font-weight: 500;
                padding: 3px 8px;
                border-radius: 4px;
            }
            QPushButton.crumbBtn:hover {
                background: @bg_hover;
                border-color: @accent;
                color: @text_main;
            }

            QPushButton.chipBtn {
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 500;
                border-radius: 6px;
                border: 1px solid @border_subtle;
                background: @bg_panel;
                color: @text_main;
            }
            QPushButton.chipBtn:hover {
                background: @bg_hover;
                border-color: @accent;
                color: @text_main;
            }
            QPushButton.chipBtn:pressed {
                background: @bg_panel;
            }

            QPushButton.primaryActionBtn {
                padding: 7px 14px;
                border-radius: 6px;
                background: @accent;
                border: 1px solid @accent;
                color: @accent_text;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton.primaryActionBtn:hover {
                background: @accent;
                border-color: @accent;
            }
            QPushButton.primaryActionBtn:pressed {
                background: @accent;
            }
            QPushButton.primaryActionBtn:disabled {
                background: @bg_panel;
                border-color: @border_subtle;
                color: @text_disabled;
            }

            QProgressBar#storageBar { border: none; border-radius: 3px; background: @bg_panel; }
            QProgressBar#storageBar::chunk { border-radius: 3px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @accent, stop:1 @accent); }
            QTreeWidget { background:@bg_input; border: 1px solid @border_subtle; border-radius: 6px; alternate-background-color:@bg_input; }
            QTabWidget::pane { border: 1px solid @border_subtle; border-radius: 6px; background: @bg_panel; }
            QTabBar::tab { background: @bg_panel; color: @text_sub; padding: 8px 18px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
            QTabBar::tab:hover { background: @bg_hover; color: @text_main; }
            QTabBar::tab:selected { background: @bg_selected; color: @text_selected; border-bottom: 2px solid @accent; }
        ''')

        from PySide6.QtWidgets import QGraphicsBlurEffect
        self.download_content = QWidget(self)
        outer = QGridLayout(self); outer.setContentsMargins(0,0,0,0)
        outer.addWidget(self.download_content,0,0)
        self.download_blur = QGraphicsBlurEffect(self.download_content); self.download_blur.setBlurRadius(12)
        self.download_content.setGraphicsEffect(self.download_blur); self.download_blur.setEnabled(False)
        root = QVBoxLayout(self.download_content)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # Three-column Splitter (Left Setup, Center Mirror/Phone, Right Files)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        root.addWidget(split, 1)

        # ---------------------------------------------------------------------
        # LEFT PANEL: Phone Connect & Setup
        # ---------------------------------------------------------------------
        left = QWidget()
        left.setMinimumWidth(250)
        left.setMaximumWidth(340)
        setup = QVBoxLayout(left)
        setup.setContentsMargins(0, 0, 16, 0)
        setup.setSpacing(14)

        # Title with Phone Icon
        title_row = QHBoxLayout()
        title_icon = QLabel()
        set_ui_icon(title_icon, 'smartphone', '#60a5fa', 24)
        title_row.addWidget(title_icon)
        title_lbl = label('Phone Connect', 'font-size:18px;font-weight:700;color:@text_main;')
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        setup.addLayout(title_row)

        setup.addWidget(label('Mirror your phone and easily transfer files between your computer and device.', 'color:@text_sub;font-size:11px;'))

        # Platform Toggle [ iPhone ] [ Android ]
        platforms = QHBoxLayout()
        platforms.setSpacing(8)
        group = QButtonGroup(self)
        self.platform_buttons = {}
        for name, key, icon in [('iPhone', 'iphone', 'apple'), ('Android', 'android', 'android')]:
            button = QPushButton(f'  {name}')
            button.setProperty('class', 'segmentedBtn')
            button.setIcon(lucide_icon(icon, '#f1f5f9', 16))
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, p=key: self.switch_platform(p))
            group.addButton(button)
            platforms.addWidget(button)
            self.platform_buttons[key] = button
        self.platform_buttons['iphone'].setChecked(True)
        setup.addLayout(platforms)

        # Steps 1, 2, 3 Wizard Frame
        self.steps_frame = QFrame()
        self.steps_frame.setProperty('class', 'panelCard')
        steps_layout = QVBoxLayout(self.steps_frame)
        steps_layout.setContentsMargins(12, 12, 12, 12)
        steps_layout.setSpacing(10)

        self.step1_row, self.step1_title, self.step1_sub = self._create_step_row(1, 'Connect your iPhone', 'Use a USB cable (USB-C)')
        self.step2_row, self.step2_title, self.step2_sub = self._create_step_row(2, 'Trust this computer', "Tap 'Trust' on your iPhone if prompted")
        self.step3_row, self.step3_title, self.step3_sub = self._create_step_row(3, 'Start mirroring', 'Your iPhone screen will appear here')
        steps_layout.addLayout(self.step1_row)
        steps_layout.addLayout(self.step2_row)
        steps_layout.addLayout(self.step3_row)
        setup.addWidget(self.steps_frame)

        # Connected Card (Green Tinted / Disconnected State)
        self.connected_card = QFrame()
        self.connected_card.setObjectName('connectedCard')
        self.connected_card.setCursor(Qt.PointingHandCursor)
        self.connected_card.mousePressEvent = self._on_card_clicked
        cc_layout = QHBoxLayout(self.connected_card)
        cc_layout.setContentsMargins(12, 12, 12, 12)
        cc_layout.setSpacing(10)

        self.connected_badge = QLabel()
        self.connected_badge.setFixedSize(30, 30)
        set_ui_style(self.connected_badge, 'background: @badge_bg; border-radius: 15px;')
        self.connected_badge.setAlignment(Qt.AlignCenter)
        set_ui_icon(self.connected_badge, 'check', '@on_badge', 18)
        cc_layout.addWidget(self.connected_badge)

        cc_text = QVBoxLayout()
        cc_text.setSpacing(2)
        self.connected_header = QLabel('iPhone Connected')
        self.connected_header.setWordWrap(True)
        set_ui_style(self.connected_header, 'font-size: 13px; font-weight: 700; color: @text_main;')
        cc_text.addWidget(self.connected_header)
        self.connected_model = QLabel('iPhone 15')
        set_ui_style(self.connected_model, 'font-size: 11px; color: @text_main;')
        cc_text.addWidget(self.connected_model)
        self.connected_os = QLabel('iOS 17.4')
        set_ui_style(self.connected_os, 'font-size: 10px; color: @success;')
        cc_text.addWidget(self.connected_os)
        cc_layout.addLayout(cc_text, 1)

        self.refresh_devices = QPushButton()
        self.refresh_devices.setIcon(lucide_icon('refresh-cw', '#86efac', 14))
        self.refresh_devices.setFixedSize(28, 28)
        self.refresh_devices.setCursor(Qt.PointingHandCursor)
        set_ui_style(self.refresh_devices, '''
            QPushButton { border: none; border-radius: 4px; background: transparent; }
            QPushButton:hover { background: @success_bg; }
            QPushButton:pressed { background: @success_bg; }
        ''')
        self.refresh_devices.setToolTip('Refresh USB connection')
        self.refresh_devices.clicked.connect(self.discover)
        cc_layout.addWidget(self.refresh_devices)

        setup.addWidget(self.connected_card)

        # Legacy Controls compatibility for tests
        self.devices = QComboBox()
        self.devices.currentIndexChanged.connect(self.device_changed)
        self.devices.hide()
        setup.addWidget(self.devices)

        self.connect_button = action('Connect / Trust', self.connect_device, 'link')
        self.connect_button.hide()
        setup.addWidget(self.connect_button)

        self.device_status = label('Checking USB connection…', 'color:@text_sub; font-size: 11px;')
        setup.addWidget(self.device_status)

        # Prominent Start Mirroring Button
        mirror_box = QVBoxLayout()
        mirror_box.setSpacing(4)
        self.mirror_button = QPushButton('  Start Mirroring')
        self.mirror_button.setIcon(lucide_icon('smartphone', '#f8fafc', 16))
        self.mirror_button.setMinimumHeight(40)
        self.mirror_button.setCursor(Qt.PointingHandCursor)
        self.mirror_button_idle_style = '''
            QPushButton {
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                background: @bg_panel;
                border: 1px solid @border_subtle;
                color: @text_main;
            }
            QPushButton:hover {
                background: @bg_hover;
                border-color: @accent;
                color: @text_main;
            }
            QPushButton:pressed {
                background: @bg_panel;
                border-color: @accent;
            }
            QPushButton:disabled {
                background: @bg_panel;
                border-color: @border_subtle;
                color: @text_disabled;
            }
        '''
        self.mirror_button_active_style = '''
            QPushButton {
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                background: @danger_bg;
                border: 1px solid @accent;
                color: @text_main;
            }
            QPushButton:hover {
                background: @danger_bg;
                border-color: @accent;
                color: @text_main;
            }
            QPushButton:pressed {
                background: @danger_bg;
            }
        '''
        set_ui_style(self.mirror_button, self.mirror_button_idle_style)
        self.mirror_button.clicked.connect(self.toggle_mirror)
        mirror_box.addWidget(self.mirror_button)

        self.mirror_subtext = QLabel('The screen will appear in the centre panel')
        set_ui_style(self.mirror_subtext, 'font-size: 10px; color: @text_sub; text-align: center;')
        self.mirror_subtext.setAlignment(Qt.AlignCenter)
        mirror_box.addWidget(self.mirror_subtext)
        setup.addLayout(mirror_box)

        # Other Options Section
        setup.addWidget(label('Other Options', 'font-size: 12px; font-weight: 700; color: @text_main; margin-top: 6px;'))

        self.btn_open_files = QPushButton('   Open Device Files\n   Browse and manage files')
        self.btn_open_files.setProperty('class', 'actionCard')
        self.btn_open_files.setCursor(Qt.PointingHandCursor)
        self.btn_open_files.setIcon(lucide_icon('folder-open', '#60a5fa', 18))
        self.btn_open_files.clicked.connect(self._open_device_files)
        setup.addWidget(self.btn_open_files)

        self.btn_quick_send = QPushButton('   Quick Send to Photos\n   Drag & drop videos/images to send directly')
        self.btn_quick_send.setProperty('class', 'actionCard')
        self.btn_quick_send.setCursor(Qt.PointingHandCursor)
        self.btn_quick_send.setIcon(lucide_icon('image-plus', '#f43f5e', 18))
        self.btn_quick_send.clicked.connect(self._quick_send_guide)
        setup.addWidget(self.btn_quick_send)

        setup.addStretch()

        # Tools & Settings
        tools_row = QHBoxLayout()
        btn_tools = action('USB Setup / Tools…', self.setup_dialog, 'settings')
        tools_row.addWidget(btn_tools)
        setup.addLayout(tools_row)

        self.guidance = label('', 'color:@text_sub; font-size:10px;')
        self.instructions = label('')
        self.instructions.hide()
        setup.addWidget(self.guidance)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(250)
        left_scroll.setMaximumWidth(340)
        left_scroll.setWidget(left)
        split.addWidget(left_scroll)

        # ---------------------------------------------------------------------
        # CENTER PANEL: Live Mirror & Interactive Phone Frame
        # ---------------------------------------------------------------------
        center = QWidget()
        center.setMinimumWidth(280)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(8, 0, 8, 0)
        self.mirror = PhoneMirror()
        self.mirror.status.connect(self.show_status)
        self.mirror.activeChanged.connect(self.mirror_state)
        self.mirror.disconnectRequested.connect(self._on_disconnect_requested)
        self.mirror.reconnectRequested.connect(self.discover)
        center_layout.addWidget(self.mirror, 1)
        split.addWidget(center)

        # ---------------------------------------------------------------------
        # RIGHT PANEL: Storage, Files & Transfer Queue
        # ---------------------------------------------------------------------
        right = QWidget()
        right.setMinimumWidth(380)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs)
        split.addWidget(right)

        # Files Tab - Modern Device Drive Explorer
        files_widget = QWidget()
        fl = QVBoxLayout(files_widget)
        fl.setContentsMargins(14, 14, 14, 14)
        fl.setSpacing(10)

        # 1. Device Drive Storage Card
        self.drive_card = QFrame()
        self.drive_card.setObjectName('driveCard')
        self.drive_card.setCursor(Qt.PointingHandCursor)
        self.drive_card.mousePressEvent = lambda e: self.go_to_root()
        self.drive_card.setToolTip('Click to view root storage')
        dc_layout = QVBoxLayout(self.drive_card)
        dc_layout.setContentsMargins(12, 10, 12, 10)
        dc_layout.setSpacing(6)

        dc_top = QHBoxLayout()
        dc_top.setSpacing(8)
        self.drive_icon = QLabel()
        set_ui_icon(self.drive_icon, 'hard-drive', '#60a5fa', 18)
        dc_top.addWidget(self.drive_icon)

        self.drive_title = QLabel('Internal shared storage')
        set_ui_style(self.drive_title, 'font-size: 13px; font-weight: 700; color: @text_main;')
        dc_top.addWidget(self.drive_title)
        dc_top.addStretch()

        self.storage_label = QLabel('Connect a device to view storage')
        set_ui_style(self.storage_label, 'font-size: 11px; color: @text_sub;')
        dc_top.addWidget(self.storage_label)
        dc_layout.addLayout(dc_top)

        self.storage_bar = QProgressBar()
        self.storage_bar.setObjectName('storageBar')
        self.storage_bar.setFixedHeight(6)
        self.storage_bar.setTextVisible(False)
        self.storage_bar.setValue(0)
        dc_layout.addWidget(self.storage_bar)
        fl.addWidget(self.drive_card)

        # 2. Quick Access Shortcut Chips
        shortcuts_row = QGridLayout()
        shortcuts_row.setSpacing(6)
        shortcuts_label = QLabel('Quick Access:')
        set_ui_style(shortcuts_label, 'font-size: 11px; color: @text_sub; font-weight: 600;')
        shortcuts_row.addWidget(shortcuts_label, 0, 0, 1, 3)

        self.category_buttons = []
        categories = [
            ('Camera (DCIM)', 'DCIM', 'image', '#38bdf8', '/DCIM'),
            ('Downloads', 'Downloads', 'download', '#34d399', '/Downloads'),
            ('Movies', 'Movies', 'video', '#a855f7', '/DCIM'),
            ('Pictures', 'Pictures', 'image-plus', '#ec4899', '/DCIM'),
            ('All Files', 'Storage', 'hard-drive', '#94a3b8', '/DCIM'),
        ]
        for index, (name, sub, icon, col, target_path) in enumerate(categories):
            btn = QPushButton(f'  {name}')
            btn.setProperty('class', 'chipBtn')
            btn.setIcon(lucide_icon(icon, col, 13))
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, tp=target_path: self.navigate_to_path(tp))
            shortcuts_row.addWidget(btn, 1 + index // 3, index % 3)
            self.category_buttons.append(btn)
        fl.addLayout(shortcuts_row)

        # 3. Interactive Breadcrumb Navigation & Up/Refresh
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)

        self.breadcrumb_container = QWidget()
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_container)
        self.breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        self.breadcrumb_layout.setSpacing(2)
        nav_row.addWidget(self.breadcrumb_container, 1)

        self.folder_label = QLineEdit('/DCIM')
        self.folder_label.hide()

        self.locations = QComboBox()
        self.locations.currentIndexChanged.connect(self.location_changed)
        self.locations.hide()
        fl.addWidget(self.locations)

        self.up = action('Up', self.parent_folder, 'chevron-up')
        self.up.setFixedWidth(65)
        self.up.setToolTip('Go to parent folder')
        nav_row.addWidget(self.up)

        self.refresh_folder = action('Refresh', self.refresh_files, 'refresh-cw')
        self.refresh_folder.setFixedWidth(80)
        self.refresh_folder.setToolTip('Refresh folder contents')
        nav_row.addWidget(self.refresh_folder)
        fl.addLayout(nav_row)

        # 4. File List Tree (Explorer View)
        self.files = QTreeWidget()
        self.files.setHeaderLabels(['Name', 'Size', 'Modified'])
        self.files.setAlternatingRowColors(True)
        self.files.setRootIsDecorated(False)
        self.files.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.files.itemDoubleClicked.connect(self.open_folder)
        self.files.itemSelectionChanged.connect(self.update_controls)
        self.files.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files.setColumnWidth(1, 85)
        self.files.setColumnWidth(2, 130)
        self.files.setMinimumHeight(150)
        fl.addWidget(self.files, 1)

        self.destination_hint = label('Connect a device to browse its accessible files.', 'color:@text_sub; font-size:11px;')
        fl.addWidget(self.destination_hint)

        # 5. Explorer Action Bar
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.btn_import_project = QPushButton('  Import into Project')
        self.btn_import_project.setProperty('class', 'primaryActionBtn')
        self.btn_import_project.setIcon(lucide_icon('folder-input', '#ffffff', 16))
        self.btn_import_project.setCursor(Qt.PointingHandCursor)
        self.btn_import_project.setToolTip('Copy selected media and add directly to Kinetic Cut project')
        self.btn_import_project.clicked.connect(self.import_to_project)
        actions_row.addWidget(self.btn_import_project, 1)

        self.btn_import_phone = QPushButton('  Save to PC…')
        self.btn_import_phone.setProperty('class', 'utilityBtn')
        self.btn_import_phone.setIcon(lucide_icon('download', '#60a5fa', 15))
        self.btn_import_phone.setCursor(Qt.PointingHandCursor)
        self.btn_import_phone.setToolTip('Save selected files to a folder on your computer')
        self.btn_import_phone.clicked.connect(self.receive_files)
        actions_row.addWidget(self.btn_import_phone)

        self.send = QPushButton('  Send to Phone…')
        self.send.setProperty('class', 'utilityBtn')
        self.send.setIcon(lucide_icon('upload', '#38bdf8', 15))
        self.send.setCursor(Qt.PointingHandCursor)
        self.send.setToolTip('Choose files from PC to upload to this folder')
        self.send.clicked.connect(self.choose_files)
        actions_row.addWidget(self.send)

        fl.addLayout(actions_row)

        # 6. Compact Drop Zone
        self.drop = FileDrop()
        self.drop.filesDropped.connect(self.send_files)
        fl.addWidget(self.drop)

        # Hidden legacy action buttons for tests
        self.receive = action('Copy to PC…', self.receive_files, 'download')
        self.receive.hide()
        fl.addWidget(self.receive)

        self.btn_send_photos = action('Send to Photos', self.choose_files, 'image-plus')
        self.btn_send_photos.hide()
        fl.addWidget(self.btn_send_photos)

        self.staged_label = label('')
        self.staged_label.hide()
        fl.addWidget(self.staged_label)

        self.send_staged = action('Send selected export', self.send_staged_files, 'upload')
        self.send_staged.hide()
        fl.addWidget(self.send_staged)

        self.tabs.addTab(files_widget, 'Files')

        # Transfer Queue Tab
        queue = QWidget()
        ql = QVBoxLayout(queue)
        ql.setContentsMargins(12, 12, 12, 12)
        self.queue = QTreeWidget()
        self.queue.setRootIsDecorated(False)
        self.queue.setHeaderLabels(['File / destination', 'Progress', 'Status'])
        self.queue.setWordWrap(True)
        self.queue.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.queue.setColumnWidth(1, 85)
        self.queue.setColumnWidth(2, 90)
        self.queue.itemSelectionChanged.connect(self.update_controls)
        ql.addWidget(self.queue)

        self.queue_detail = label('Transfers are local. Existing files are never overwritten.')
        ql.addWidget(self.queue_detail)
        self.queue.itemSelectionChanged.connect(self.queue_selected)

        qb = QHBoxLayout()
        self.cancel_button = action('Cancel', self.cancel_selected)
        self.retry_button = action('Retry', self.retry_selected)
        qb.addWidget(self.cancel_button)
        qb.addWidget(self.retry_button)
        ql.addLayout(qb)

        self.tabs.addTab(queue, 'Transfer Queue (0)')

        self.status = label('Connect an unlocked phone by USB to get started.', 'color:@text_sub; font-size:11px;')
        root.addWidget(self.status)

        split.setSizes([260, 480, 460])
        self.apply_platform_text()
        self.update_controls()

        self.download_overlay = QFrame(self)
        self.download_overlay.setObjectName('phoneDownloadPanel'); self.download_overlay.setMaximumWidth(480)
        set_ui_style(self.download_overlay, 'QFrame#phoneDownloadPanel { background:@bg_panel; border:1px solid @border_subtle; border-radius:8px; }')
        gate = QVBoxLayout(self.download_overlay); gate.setContentsMargins(24,24,24,24)
        title = QLabel('Phone tools need to be downloaded'); title.setWordWrap(True); gate.addWidget(title)
        self.download_details = QLabel(); self.download_details.setWordWrap(True); gate.addWidget(self.download_details)
        platforms = QHBoxLayout(); gate.addLayout(platforms)
        for key, name in (('android','Android'),('iphone','iPhone')):
            choose = QPushButton(name); choose.clicked.connect(lambda checked=False,k=key:self.switch_platform(k)); platforms.addWidget(choose)
        self.download_button = QPushButton('Download phone tools'); gate.addWidget(self.download_button)
        self.download_button.clicked.connect(self.download_phone_tools)
        outer.addWidget(self.download_overlay,0,0,Qt.AlignCenter)
        from .component_ui import events
        events().changed.connect(self.refresh_download_gate)
        self.refresh_download_gate()

    def refresh_download_gate(self):
        if not hasattr(self,'download_overlay'):return
        from .feature_packs import available, manifest
        missing = not available(self.platform,self.settings)
        self.download_blur.setEnabled(missing); self.download_content.setEnabled(not missing)
        self.download_overlay.setVisible(missing)
        if missing:
            info = manifest().get(self.platform,{})
            size = info.get('installed_bytes',266850000 if self.platform=='iphone' else 26240000)
            detail = f"{self.platform.title()} tools are not installed.\nInstalled size: {size/1e6:.1f} MB"
            if info:detail += f"\nDownload: {info['download_bytes']/1e6:.1f} MB"
            self.download_details.setText(detail+'\nDownload to enable phone mirroring and device tools.')
            self.download_overlay.raise_()

    def download_phone_tools(self):
        from .component_ui import offer
        if offer(self,self.platform):self.refresh_download_gate(); self.activate()

    def _create_step_row(self, num: int, title: str, subtitle: str):
        row = QHBoxLayout()
        row.setSpacing(10)
        num_circle = QLabel(str(num))
        num_circle.setFixedSize(22, 22)
        set_ui_style(num_circle, 'background: @accent; color: @accent_text; font-weight: 700; border-radius: 11px; font-size: 11px;')
        num_circle.setAlignment(Qt.AlignCenter)
        row.addWidget(num_circle)

        text_v = QVBoxLayout()
        text_v.setSpacing(1)
        t_lbl = QLabel(title)
        set_ui_style(t_lbl, 'font-size: 12px; font-weight: 600; color: @text_main;')
        sub_lbl = QLabel(subtitle)
        set_ui_style(sub_lbl, 'font-size: 10px; color: @text_sub;')
        text_v.addWidget(t_lbl)
        text_v.addWidget(sub_lbl)
        row.addLayout(text_v, 1)
        return row, t_lbl, sub_lbl

    def _create_category_button(self, name: str, sub: str, icon: str, color: str, target_path: str) -> QPushButton:
        btn = QPushButton(f'  {name}')
        btn.setProperty('class', 'chipBtn')
        btn.setIcon(lucide_icon(icon, color, 14))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda: self.navigate_to_path(target_path))
        return btn

    def _select_category(self, name: str, target_path: str):
        self.navigate_to_path(target_path)

    def update_breadcrumbs(self):
        if not hasattr(self, 'breadcrumb_layout'): return
        while self.breadcrumb_layout.count():
            item = self.breadcrumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        root_path = self.location['root'] if self.location else ('/sdcard' if self.platform == 'android' else '/DCIM')
        current_path = self.path or root_path

        root_name = 'Internal Storage' if self.platform == 'android' else 'Camera Roll'
        btn_root = QPushButton(f'  {root_name}')
        btn_root.setIcon(lucide_icon('hard-drive' if self.platform == 'android' else 'camera', '#60a5fa', 14))
        btn_root.setProperty('class', 'crumbBtn')
        btn_root.setCursor(Qt.PointingHandCursor)
        btn_root.clicked.connect(lambda: self.navigate_to_path(root_path))
        self.breadcrumb_layout.addWidget(btn_root)

        norm_curr = posixpath.normpath(current_path)
        norm_root = posixpath.normpath(root_path)
        if norm_curr != norm_root and norm_curr.startswith(norm_root.rstrip('/') + '/'):
            rel = norm_curr[len(norm_root):].strip('/')
            parts = rel.split('/')
            accum = norm_root
            for part in parts:
                accum = posixpath.join(accum, part)
                sep = QLabel('›')
                set_ui_style(sep, 'color: @text_sub; font-size: 13px; font-weight: 700; margin: 0 1px;')
                self.breadcrumb_layout.addWidget(sep)

                crumb_btn = QPushButton(part)
                crumb_btn.setProperty('class', 'crumbBtn')
                crumb_btn.setCursor(Qt.PointingHandCursor)
                target = accum
                crumb_btn.clicked.connect(lambda checked=False, p=target: self.navigate_to_path(p))
                self.breadcrumb_layout.addWidget(crumb_btn)

        self.breadcrumb_layout.addStretch()

    def navigate_to_path(self, target_path: str):
        if self.platform == 'iphone' and target_path in ('/Downloads', '/KineticCut'):
            self.show_status('Downloads uses iOS App File Sharing. Install iTunes for app file access.')
            return
        self.path = target_path
        self.folder_label.setText(self.path)
        self.update_breadcrumbs()
        self.refresh_files()

    def go_to_root(self):
        root_path = self.location['root'] if self.location else ('/sdcard' if self.platform == 'android' else '/DCIM')
        self.navigate_to_path(root_path)

    def import_to_project(self):
        selected = [item.data(0, Qt.UserRole) for item in self.files.selectedItems()]
        if not selected:
            if self.files.topLevelItemCount() > 0:
                first = self.files.topLevelItem(0)
                first.setSelected(True)
                selected = [first.data(0, Qt.UserRole)]
            else:
                self.show_status('Select one or more photos or videos to import into your project.')
                return

        media_files = [entry for entry in selected if not entry.get('folder')]
        if not media_files:
            self.show_status('Open the folder and select video/image files to import.')
            return

        cache_dir = Path.home() / 'Videos' / 'KineticCut_Imports'
        cache_dir.mkdir(parents=True, exist_ok=True)

        for entry in media_files:
            try:
                name = local_name(entry['name'])
                target = cache_dir / name
                if target.is_file() and target.stat().st_size == entry.get('size', -1):
                    if hasattr(self.window_, 'import_media_files'):
                        self.window_.import_media_files([str(target)])
                    self.show_status(f'Imported {name} into project.')
                    continue

                if target.exists():
                    target = cache_dir / f"{target.stem}_{uuid.uuid4().hex[:6]}{target.suffix}"

                request = self.payload('pull')
                request['local'] = str(target)
                request['path'] = posixpath.join(self.path, name)
                self.enqueue(request, name, str(target), import_on_complete=True)
            except PhoneError as exc:
                self.show_status(str(exc))

    def _open_device_files(self):
        self.tabs.setCurrentIndex(0)
        self.go_to_root()

    def _quick_send_guide(self):
        self.tabs.setCurrentIndex(0)
        self.choose_files()

    def _on_card_clicked(self, event):
        if not self.device:
            self.discover()

    def _on_disconnect_requested(self):
        self.device = None
        self.location = None
        self.folder_ready = False
        self.files.clear()
        set_ui_style(self.connected_card, 'background: @bg_panel; border: none; border-radius: 8px;')
        set_ui_style(self.connected_badge, 'background: @bg_panel; border-radius: 15px;')
        set_ui_icon(self.connected_badge, 'link-2-off', '#9ca3af', 16)
        self.connected_header.setText('Phone Disconnected')
        set_ui_style(self.connected_header, 'font-size: 13px; font-weight: 700; color: @text_sub;')
        self.connected_model.setText('Click to Reconnect')
        set_ui_style(self.connected_model, 'font-size: 11px; color: @text_sub;')
        self.connected_os.setText('Tap Reconnect button below')
        set_ui_style(self.connected_os, 'font-size: 10px; color: @text_sub;')
        self.connected_card.show()
        self.device_status.setText('Phone disconnected · Click Reconnect')
        self.show_status('Device disconnected. Click Reconnect to pair again.')
        self.update_controls()

    def show_status(self, text):
        self.status.setText(str(text))
        self.status.setToolTip(str(text))

    def apply_platform_text(self):
        iphone = self.platform == 'iphone'
        if iphone:
            self.step1_title.setText('Connect your iPhone')
            self.step1_sub.setText('Use a USB cable (USB-C)')
            self.step2_title.setText('Trust this computer')
            self.step2_sub.setText("Tap 'Trust' on your iPhone if prompted")
            self.step3_title.setText('Start mirroring')
            self.step3_sub.setText('Your iPhone screen will appear here')
            self.guidance.setText('To reach Photos: send to a compatible app, then use its Share → Save Video/Image action on the iPhone.')
            self.destination_hint.setText('Read-only camera media (DCIM). Choose an app with File Sharing to send files.')
            self.mirror_subtext.setText('The screen will appear in the centre panel')
        else:
            self.step1_title.setText('Connect Android by USB')
            self.step1_sub.setText('Plug in your phone using a USB cable')
            self.step2_title.setText('Enable USB debugging')
            self.step2_sub.setText("In Developer options, enable 'USB debugging' and tap Allow")
            self.step3_title.setText('Start mirroring & control')
            self.step3_sub.setText('Control Android screen with mouse and keyboard')
            self.guidance.setText('Browse shared storage, not private app data. ADB authorization is required.')
            self.destination_hint.setText('Direct bidirectional transfer to /sdcard storage.')
            self.mirror_subtext.setText('Click inside mirror to control with mouse & keyboard')

        self._update_category_buttons()
        self.mirror.set_platform(self.platform)

    def _update_category_buttons(self):
        iphone = self.platform == 'iphone'
        categories = [
            ('Camera (DCIM)', 'DCIM', 'image', '#38bdf8', '/DCIM' if iphone else '/sdcard/DCIM'),
            ('Photos & Videos', 'Media', 'video', '#a855f7', '/DCIM' if iphone else '/sdcard/DCIM'),
            ('Downloads', 'On My iPhone' if iphone else '/sdcard/Download', 'download', '#34d399', '/Downloads' if iphone else '/sdcard/Download'),
            ('Movies', 'Videos', 'video', '#f43f5e', '/DCIM' if iphone else '/sdcard/Movies'),
            ('All Files', 'Storage root', 'hard-drive', '#94a3b8', '/DCIM' if iphone else '/sdcard'),
        ]
        for i, (name, sub, icon, col, target_path) in enumerate(categories):
            if i < len(self.category_buttons):
                btn = self.category_buttons[i]
                btn.setText(f'  {name}')
                btn.setToolTip(f'{name} · {sub}')
                btn.setIcon(lucide_icon(icon, col, 13))
                try:
                    btn.clicked.disconnect()
                except Exception:
                    pass
                btn.clicked.connect(lambda checked=False, tp=target_path: self.navigate_to_path(tp))

    def activate(self):
        self.refresh_download_gate()
        if hasattr(self,'download_overlay') and not self.download_content.isEnabled():return
        if not self.loaded:
            self.loaded = True
            self.discover()

    def deactivate(self):
        if not self.mirror.is_popped_out:
            self.mirror.stop(immediate=True)
            self.invalidate()

    def switch_platform(self, platform):
        if self.platform == platform: return
        self.mirror.stop(immediate=True)
        self.platform = platform
        self.refresh_download_gate()
        self.platform_buttons[platform].setChecked(True)
        self.device = None
        self.location = None
        self.folder_ready = False
        self.files.clear()
        self.path = '/sdcard' if platform == 'android' else '/DCIM'
        self.folder_label.setText(self.path)
        self.drive_title.setText('Internal shared storage' if platform == 'android' else 'iPhone Storage')
        self.storage_label.setText('Connect a device to view storage')
        self.storage_bar.setValue(0)
        self.connected_card.hide()
        self.apply_platform_text()
        self.update_breadcrumbs()
        if self.download_content.isEnabled():self.discover()

    def invalidate(self):
        self.generation += 1
        if self.pending and not self.pending.done:
            self.pending.cancel()
        self.pending = None

    def request(self, payload, callback, metadata=True):
        request = self.request_factory(payload, self)
        self.requests.add(request)
        generation = self.generation
        if metadata: self.pending = request

        def finished(ok, result):
            self.requests.discard(request)
            if metadata and self.pending is request: self.pending = None
            if not self.closed and (not metadata or generation == self.generation):
                callback(ok, result)
            request.deleteLater()
            if not self.closed:
                self.update_controls()

        request.finished.connect(finished)
        request.start()
        self.update_controls()
        return request

    def payload(self, op):
        return dict(
            platform=self.platform, op=op, adb=tool_path(self.settings, 'adb'),
            device=self.device['id'] if self.device else '', location=copy.deepcopy(self.location),
            path=self.path
        )

    def discover(self):
        if self.closed: return
        self.invalidate()
        self.mirror.stop()
        self.device = None
        self.location = None
        self.folder_ready = False
        self.devices.clear()
        self.locations.clear()
        self.files.clear()
        self.folder_label.setText(self.path)
        self.device_status.setText('Checking USB devices…')
        self.show_status('Checking local USB connection…')

        def ready(ok, data):
            self.devices.blockSignals(True)
            if ok:
                for device in data:
                    self.devices.addItem(device['name'] + ' · ' + device['state'], device)
            self.devices.blockSignals(False)
            self.device_changed()
            if not ok:
                self.connected_card.hide()
                self.device_status.setText('Connection unavailable')
                self.show_status(data)
            elif not data:
                self.connected_card.hide()
                self.device_status.setText('No USB device found')
                self.show_status('No USB device found. Check the cable, unlock the phone and review USB Setup.')
            else:
                self.connected_card.show()

        self.request(self.payload('discover'), ready)

    def device_changed(self, *_):
        self.invalidate()
        self.mirror.stop()
        self.device = self.devices.currentData()
        self.location = None
        self.folder_ready = False
        self.locations.clear()
        self.files.clear()
        self.folder_label.setText(self.path)

        if self.device:
            state = self.device.get('state', 'ready')
            name = self.device.get('name', 'Phone')
            model = self.device.get('model', name)
            version = self.device.get('version', '')

            set_ui_style(self.connected_card, 'background: @success_bg; border: none; border-radius: 8px;')
            self.connected_card.show()

            if state == 'ready':
                set_ui_style(self.connected_badge, 'background: @badge_bg; border-radius: 15px;')
                set_ui_icon(self.connected_badge, 'check', '@on_badge', 18)
                self.connected_header.setText(f"{name} Connected")
                set_ui_style(self.connected_header, 'font-size: 13px; font-weight: 700; color: @text_main;')
                self.connected_model.setText(model)
                set_ui_style(self.connected_model, 'font-size: 11px; color: @text_main;')
                self.connected_os.setText(version if version else 'USB Connected · Ready')
                set_ui_style(self.connected_os, 'font-size: 10px; color: @success;')
                self.device_status.setText(self.device.get('detail', 'USB Connected'))
                self.mirror.set_device_info(name, connected=True)
                self.show_status('Device connected · ready for mirroring & files.')
                self.connect_device()
            elif state == 'need_usb_debugging':
                set_ui_style(self.connected_badge, 'background: @warning_badge; border-radius: 15px;')
                set_ui_icon(self.connected_badge, 'alert-circle', '@on_badge', 18)
                self.connected_header.setText(f"{name} (USB Detected)")
                set_ui_style(self.connected_header, 'font-size: 13px; font-weight: 700; color: @warning;')
                self.connected_model.setText(model)
                set_ui_style(self.connected_model, 'font-size: 11px; color: @text_main;')
                self.connected_os.setText('Turn ON USB debugging in Settings')
                set_ui_style(self.connected_os, 'font-size: 10px; color: @warning;')
                self.device_status.setText('USB connected · Enable "USB debugging" in Developer options')
                self.mirror.set_device_info(name, connected=True)
                self.show_status('USB detected! On your phone: Open Settings → Developer options → turn ON "USB debugging".')
            elif state == 'unauthorized':
                set_ui_style(self.connected_badge, 'background: @warning_badge; border-radius: 15px;')
                set_ui_icon(self.connected_badge, 'shield-alert', '@on_badge', 18)
                self.connected_header.setText(f"{name} (Authorize)")
                set_ui_style(self.connected_header, 'font-size: 13px; font-weight: 700; color: @warning;')
                self.connected_model.setText(model)
                set_ui_style(self.connected_model, 'font-size: 11px; color: @text_main;')
                self.connected_os.setText('Tap "Allow USB debugging" on phone')
                set_ui_style(self.connected_os, 'font-size: 10px; color: @warning;')
                self.device_status.setText('Check phone screen: Tap "Allow USB debugging"')
                self.mirror.set_device_info(name, connected=True)
                self.show_status('Authorization prompt sent. Check phone screen and tap Allow.')
            else:
                set_ui_style(self.connected_badge, 'background: @bg_panel; border-radius: 15px;')
                set_ui_icon(self.connected_badge, 'smartphone', '#ffffff', 18)
                self.connected_header.setText(f"{name} ({state})")
                set_ui_style(self.connected_header, 'font-size: 13px; font-weight: 700; color: @text_main;')
                self.connected_model.setText(model)
                set_ui_style(self.connected_model, 'font-size: 11px; color: @text_sub;')
                self.connected_os.setText(self.device.get('detail', state))
                set_ui_style(self.connected_os, 'font-size: 10px; color: @text_sub;')
                self.device_status.setText(self.device.get('detail', state))
                self.mirror.set_device_info(name, connected=True)

            storage = self.device.get('storage')
            if storage:
                self.drive_title.setText(f"{self.device.get('name', 'Phone')} · Storage")
                self.storage_label.setText(f"{storage.get('used_str', '')} / {storage.get('total_str', '')} used")
                self.storage_bar.setValue(int(storage.get('percent', 59)))
            elif state != 'ready':
                self.drive_title.setText('Device Storage (Locked)')
                self.storage_label.setText('Enable USB debugging to view storage')
                self.storage_bar.setValue(0)
            else:
                self.drive_title.setText('Internal shared storage')
        else:
            self.connected_card.hide()
            self.device_status.setText('No device selected')
            self.mirror.set_device_info('No Device', connected=False)
            self.drive_title.setText('Internal shared storage')
            self.storage_label.setText('Connect a device to view storage')
            self.storage_bar.setValue(0)

        self.update_controls()

    def connect_device(self):
        if not self.device or self.pending: return
        self.invalidate()
        self.show_status('Connecting… unlock the phone and accept Trust / USB debugging if prompted.')

        def ready(ok, data):
            if not ok:
                self.show_status(data)
                return
            self.device['state'] = 'ready'
            self.device_status.setText(data.get('detail', 'Connected'))
            storage = data.get('storage')
            if storage:
                self.drive_title.setText(f"{self.device.get('name', 'Phone')} · Storage")
                self.storage_label.setText(f"{storage.get('used_str', '')} / {storage.get('total_str', '')} used")
                self.storage_bar.setValue(int(storage.get('percent', 59)))

            self.locations.blockSignals(True)
            self.locations.clear()
            for location in data.get('locations', []):
                self.locations.addItem(location['name'], location)
            self.locations.blockSignals(False)
            self.location_changed()

        self.request(self.payload('locations'), ready)

    def location_changed(self, *_):
        self.invalidate()
        self.location = self.locations.currentData()
        self.folder_ready = False
        default_root = '/sdcard' if self.platform == 'android' else '/DCIM'
        self.path = self.location['root'] if self.location else default_root
        self.update_breadcrumbs()
        self.refresh_files()

    def refresh_files(self):
        if not self.device:
            self.update_controls()
            return
        self.invalidate()
        self.folder_ready = False
        self.files.clear()
        default_root = '/sdcard' if self.platform == 'android' else '/DCIM'
        if not self.path or (self.platform == 'android' and self.path == '/DCIM'):
            self.path = self.location['root'] if self.location else default_root
        self.folder_label.setText(self.path or default_root)
        self.update_breadcrumbs()
        writable = bool(self.location and self.location.get('writable', False))

        self.destination_hint.setText(
            ('Read-only camera media (DCIM). Choose an app with File Sharing to send files.')
            if self.platform == 'iphone' and not writable else
            ('USB destination: ' + (self.location['name'] if self.location else 'shared storage'))
        )
        self.show_status('Loading device folder…')

        def ready(ok, data):
            if not ok:
                self.show_status(data)
                return
            for entry in sorted(data, key=lambda value: (not value['folder'], value['name'].casefold())):
                item = QTreeWidgetItem([entry['name'], '' if entry['folder'] else size_text(entry['size']), entry.get('modified', '')[:19]])
                item.setData(0, Qt.UserRole, entry)
                item.setToolTip(0, entry['name'])
                lower = entry['name'].lower()
                if entry['folder']:
                    icon_name, col = 'folder', '#38bdf8'
                elif lower.endswith(('.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi')):
                    icon_name, col = 'video', '#a855f7'
                elif lower.endswith(('.png', '.jpg', '.jpeg', '.heic', '.webp', '.gif', '.dng')):
                    icon_name, col = 'image', '#ec4899'
                elif lower.endswith(('.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg')):
                    icon_name, col = 'music', '#10b981'
                else:
                    icon_name, col = 'file', '#94a3b8'
                item.setIcon(0, lucide_icon(icon_name, col, 16))
                if not entry.get('supported', True): item.setDisabled(True)
                self.files.addTopLevelItem(item)
            self.folder_ready = True
            loc_name = self.location['name'] if self.location else ('Shared Storage' if self.platform == 'android' else 'DCIM')
            self.show_status(f'{len(data)} items · {loc_name} · {self.path}')

        self.request(self.payload('list'), ready)

    def open_folder(self, item, *_):
        entry = item.data(0, Qt.UserRole)
        if self.folder_ready and entry:
            if entry.get('folder'):
                self.path = posixpath.join(self.path, device_name(entry['name']))
                self.folder_label.setText(self.path)
                self.update_breadcrumbs()
                self.refresh_files()
            else:
                self.import_to_project()

    def parent_folder(self):
        root_path = self.location['root'] if self.location else ('/sdcard' if self.platform == 'android' else '/DCIM')
        if self.path and self.path != root_path:
            norm_curr = posixpath.normpath(self.path)
            norm_root = posixpath.normpath(root_path)
            parent = posixpath.dirname(norm_curr)
            if not parent or not (parent == norm_root or parent.startswith(norm_root.rstrip('/') + '/')):
                self.path = root_path
            else:
                self.path = parent
            self.folder_label.setText(self.path)
            self.update_breadcrumbs()
            self.refresh_files()

    def update_controls(self):
        busy = self.pending is not None
        writable = bool(self.folder_ready and self.location and self.location.get('writable'))
        self.connect_button.setEnabled(bool(self.device) and not busy)
        self.refresh_devices.setEnabled(not busy)
        self.locations.setEnabled(bool(self.device) and not busy)
        self.refresh_folder.setEnabled(bool(self.device) and not busy)
        root_path = self.location['root'] if self.location else ('/sdcard' if self.platform == 'android' else '/DCIM')
        self.up.setEnabled(self.folder_ready and bool(self.device) and self.path != root_path and not busy)
        self.send.setEnabled(writable and not busy)
        self.drop.setEnabled(writable and not busy)
        self.send_staged.setEnabled(writable and not busy)
        has_sel = self.folder_ready and bool(self.files.selectedItems()) and not busy
        self.receive.setEnabled(has_sel)
        self.btn_import_phone.setEnabled(bool(self.device) and not busy)
        if hasattr(self, 'btn_import_project'):
            self.btn_import_project.setEnabled(bool(self.device) and not busy)
        self.mirror_button.setEnabled(bool(self.device))
        job = self.selected_job()
        self.cancel_button.setEnabled(bool(job and job['state'] in {'Queued', 'Transferring'}))
        self.retry_button.setEnabled(bool(job and job['state'] in {'Failed', 'Cancelled'}))

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, 'Send files to phone', '',
            'Videos and images (*.mp4 *.mov *.mkv *.webm *.jpg *.jpeg *.png *.heic);;All files (*)'
        )
        if paths:
            self.send_files(paths)

    def stage_files(self, paths):
        self.staged_files = list(paths)
        self.staged_label.setText('Ready to send: ' + ', '.join(Path(p).name for p in paths))
        self.staged_label.show()
        self.send_staged.show()
        self.tabs.setCurrentIndex(0)

    def send_staged_files(self):
        self.send_files(self.staged_files)

    def send_files(self, paths):
        if not self.folder_ready or not self.location or not self.location.get('writable'):
            self.show_status('Choose an accessible writable destination first.')
            return

        errors = []
        for path in paths:
            if not Path(path).is_file():
                errors.append(Path(path).name + ': not a regular file')
                continue
            request = self.payload('push')
            request['local'] = str(Path(path).resolve())
            self.enqueue(request, Path(path).name, self.path + ' · ' + self.device['name'])
        if errors:
            self.show_status('; '.join(errors))

    def receive_files(self):
        selected = [item.data(0, Qt.UserRole) for item in self.files.selectedItems()]
        if not selected:
            # If no items selected in tree, prompt user to select from current folder
            if self.files.topLevelItemCount() > 0:
                first = self.files.topLevelItem(0)
                first.setSelected(True)
                selected = [first.data(0, Qt.UserRole)]
            else:
                self.show_status('Select one or more photos or videos to copy to PC.')
                return

        if any(entry.get('folder') for entry in selected):
            self.show_status('Open folders and select files inside them; folder copying is not supported.')
            return

        folder = QFileDialog.getExistingDirectory(self, 'Copy phone files to PC')
        if not folder: return
        for entry in selected:
            try:
                name = local_name(entry['name'])
                target = Path(folder) / name
                if target.exists():
                    raise PhoneError(name + ': destination already exists; choose another folder.')
                request = self.payload('pull')
                request['local'] = str(target)
                request['path'] = posixpath.join(self.path, name)
                self.enqueue(request, name, str(target))
            except PhoneError as exc:
                self.show_status(str(exc))

    def enqueue(self, request, name, destination, import_on_complete=False):
        job = dict(request=copy.deepcopy(request), name=name, destination=destination, state='Queued', detail='', worker=None, import_on_complete=import_on_complete)
        item = QTreeWidgetItem([name, '0%', 'Queued'])
        item.setToolTip(0, destination)
        job['item'] = item
        self.jobs.append(job)
        self.queue.addTopLevelItem(item)
        self.tabs.setTabText(1, f'Transfer Queue ({len(self.jobs)})')
        self.tabs.setCurrentIndex(1)
        self.queue.setCurrentItem(item)
        self.start_next()

    def start_next(self):
        if self.active_job or self.closed: return
        job = next((j for j in self.jobs if j['state'] == 'Queued'), None)
        if not job: return
        self.active_job = job
        job['state'] = 'Transferring'
        job['item'].setText(2, 'Transferring')

        def progress(done, total):
            percent = min(99, int(100 * done / total)) if total else 0
            job['item'].setText(1, f'{percent}%')
            job['detail'] = f'{size_text(done)} / {size_text(total)} → {job["destination"]}'
            if self.selected_job() is job:
                self.queue_detail.setText(job['detail'])

        def finished(ok, data):
            job['state'] = 'Complete' if ok else ('Cancelled' if job.get('cancelled') else 'Failed')
            job['detail'] = ('Copied to ' + data['destination']) if ok else str(data)
            job['item'].setText(2, job['state'])
            job['item'].setToolTip(2, job['detail'])
            if ok:
                job['item'].setText(1, '100%')
                if job.get('import_on_complete'):
                    dest = data.get('destination')
                    if dest and hasattr(self.window_, 'import_media_files'):
                        self.window_.import_media_files([dest])
                        self.show_status(f"Imported {job['name']} directly into project!")
            job['worker'] = None
            self.active_job = None
            self.queue_selected()
            self.start_next()
            if not self.active_job and self.location and self.device and job['request']['device'] == self.device['id'] and self.isVisible():
                self.refresh_files()

        job['worker'] = self.request(job['request'], finished, metadata=False)
        job['worker'].bytesChanged.connect(progress)
        self.update_controls()

    def selected_job(self):
        item = self.queue.currentItem()
        return next((job for job in self.jobs if job['item'] is item), None)

    def queue_selected(self):
        job = self.selected_job()
        if job:
            self.queue_detail.setText(job['name'] + '\n' + job['destination'] + '\n' + (job['detail'] or job['state']))

    def cancel_selected(self):
        job = self.selected_job()
        if not job: return
        if job['state'] == 'Queued':
            job['state'] = 'Cancelled'
            job['item'].setText(2, 'Cancelled')
        elif job['state'] == 'Transferring':
            job['cancelled'] = True
            job['item'].setText(2, 'Cancelling…')
            job['worker'].cancel()
        self.update_controls()

    def retry_selected(self):
        job = self.selected_job()
        if job and job['state'] in {'Failed', 'Cancelled'}:
            job.update(state='Queued', detail='', cancelled=False)
            job['item'].setText(1, '0%')
            job['item'].setText(2, 'Queued')
            self.start_next()

    def mirror_state(self, active):
        if active:
            self.mirror_button.setText('  Stop Mirroring')
            self.mirror_button.setIcon(lucide_icon('square', '#f87171', 14))
            set_ui_style(self.mirror_button, self.mirror_button_active_style)
            self.mirror_subtext.setText('Mirroring active · Tap to stop')
        else:
            self.mirror_button.setText('  Start Mirroring')
            self.mirror_button.setIcon(lucide_icon('smartphone', '#f8fafc', 16))
            set_ui_style(self.mirror_button, self.mirror_button_idle_style)
            self.mirror_subtext.setText('The screen will appear in the centre panel')

    def toggle_mirror(self):
        if self.mirror.is_mirroring():
            self.mirror.stop()
            self.mirror_state(False)
            self.show_status('Mirroring stopped.')
            return
        if not self.device:
            self.show_status('Connect an unlocked phone first.')
            return

        state = self.device.get('state')
        if state == 'need_usb_debugging':
            QMessageBox.information(
                self,
                'USB Debugging Required',
                f"Your {self.device.get('name', 'Android phone')} is detected over USB!\n\n"
                "To start screen mirroring and interactive control:\n"
                "1. Open Settings on your phone\n"
                "2. Tap System → Developer options\n"
                "3. Turn ON the 'USB debugging' toggle switch\n"
                "4. When prompted on your phone screen, check 'Always allow' and tap 'Allow'\n\n"
                "Then click Start Mirroring again."
            )
            self.show_status('Turn ON "USB debugging" in Developer options on your phone, then tap Start Mirroring.')
            return
        if state == 'unauthorized':
            QMessageBox.information(
                self,
                'Device Authorization Required',
                f"Your {self.device.get('name', 'Android phone')} is connected, but waiting for permission:\n\n"
                "1. Unlock your phone screen\n"
                "2. Look for the pop-up 'Allow USB debugging?'\n"
                "3. Check 'Always allow from this computer' and tap 'Allow'\n\n"
                "Then click Start Mirroring again."
            )
            self.show_status('Tap "Allow USB debugging" on your phone screen, then retry.')
            return
        if state != 'ready':
            self.show_status('Connect an unlocked phone first.')
            return
        if self.platform == 'iphone':
            executable = tool_path(self.settings, 'uxplay-windows')
            if not executable:
                executable = tool_path(self.settings, 'uxplay')
            if not executable:
                self.show_status('AirPlay mirror tool is missing. Download iPhone mirroring from File → Optional downloads, or select your existing tool in USB Setup / Tools.')
                return
            self.mirror.start_airplay(executable, self.device.get('name', 'iPhone'))
            self.mirror_state(True)
            self.show_status('AirPlay receiver active · On iPhone, open Control Center and tap Screen Mirroring')
        elif self.platform == 'android':
            executable = tool_path(self.settings, 'scrcpy')
            if not executable:
                self.show_status('scrcpy is missing. Download Android mirroring from File → Optional downloads, or select your existing tool in USB Setup / Tools.')
                return
            self.mirror.start(executable, tool_path(self.settings, 'adb'), self.device['id'])

    def setup_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Phone Connect · USB Setup')
        dialog.resize(660, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('iPhone: connect with a USB-C cable, unlock and tap Trust. Windows WPD provides high-speed DCIM photo/video importing. For app file sharing, install iTunes from Microsoft Store.'))
        layout.addWidget(action('Apple USB / file-sharing instructions', lambda: QDesktopServices.openUrl(QUrl(APPLE_SETUP))))
        layout.addWidget(label('Android: enable USB debugging and approve this PC. Bundled official scrcpy/ADB provide mirroring and shared-storage access.'))
        layout.addWidget(action('Android USB debugging instructions', lambda: QDesktopServices.openUrl(QUrl(ANDROID_SETUP))))
        form = QFormLayout()
        edits = {}
        for name in ('adb', 'scrcpy'):
            row = QWidget()
            horizontal = QHBoxLayout(row)
            horizontal.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(self.settings.get('phone_' + name, ''))
            edit.setPlaceholderText('Bundled tool (default)')
            edits[name] = edit
            horizontal.addWidget(edit)
            def browse(checked=False, field=edit, tool=name):
                path, _ = QFileDialog.getOpenFileName(dialog, 'Select ' + tool + '.exe', '', 'Executable (*.exe)')
                if path: field.setText(path)
            horizontal.addWidget(action('Browse…', browse))
            form.addRow(name, row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            for name, edit in edits.items():
                self.settings['phone_' + name] = edit.text().strip()
            save_settings(self.settings)
            self.show_status('Tool settings saved. Refresh Devices to reconnect.')

    def shutdown(self):
        self.closed = True
        self.mirror.shutdown()
        for request in list(self.requests):
            request.shutdown()
