from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import traceback
import copy
import logging
from dataclasses import asdict
from pathlib import Path

from .playback_config import configure as configure_playback
from .config import load_settings as _playback_settings
configure_playback(_playback_settings())

from PySide6.QtCore import QObject, QRunnable, QSize, QThreadPool, QTimer, QUrl, Qt, Signal, Slot, QEventLoop
from PySide6.QtGui import QAction, QCloseEvent, QColor, QCursor, QDesktopServices, QIcon, QImage, QKeySequence, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from .media_source import set_media_source
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QDockWidget, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QButtonGroup, QProgressDialog, QFontComboBox, QScrollArea, QSlider, QSpinBox, QSplitter, QStatusBar, QTabWidget,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from .captions import CaptionBackendError, merge_captions, split_caption, transcribe
from .controls import InspectorSection, SafeComboBox, SafeDoubleSpinBox
from .config import (AUTOSAVE_PATH, CACHE_DIR, SESSION_LOCK_PATH, load_settings, load_templates, save_settings,
                     save_templates)
from .delivery import WirelessShare, detect_adb_devices, detect_mtp_devices, send_adb, send_mtp
from .exporter import PRESETS, estimate, export
from .media import IMAGE_EXTENSIONS, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, generate_proxy, probe, waveform
from .model import Caption, CaptionStyle, Crop, Project, TimelineItem, Transform, make_vertical_group, uid
from .icons import lucide_icon
from .silence import detect
from .theme import STYLESHEET
from .editing import edit_only
from .widgets import CropDialog, MediaList, PreviewCanvas, TimelineWidget, extract_frame


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(object)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, function, *args, **kwargs):
        super().__init__(); self.function=function; self.args=args; self.kwargs=kwargs; self.signals=WorkerSignals()
        self.cancel_callback = None

    def cancel(self):
        if self.cancel_callback:
            self.cancel_callback()

    @Slot()
    def run(self):
        try:
            value=self.function(*self.args, **self.kwargs)
            try:self.signals.result.emit(value)
            except RuntimeError:return
        except InterruptedError:
            # Existing consumers use error as a terminal callback (including
            # render queue unlock). Keep that contract without a crash log.
            try:self.signals.error.emit('Operation cancelled.')
            except RuntimeError:pass
        except Exception:
            logging.exception("Background task failed: %s",getattr(self.function,"__name__","task"))
            try:self.signals.error.emit(traceback.format_exc())
            except RuntimeError:return
        finally:
            try:self.signals.finished.emit()
            except RuntimeError:pass


def button(text: str, callback=None, accent=False, quiet=False, tooltip="", icon="") -> QPushButton:
    widget=QPushButton(text); widget.setProperty("accent", accent); widget.setProperty("quiet", quiet)
    if icon:
        widget.setProperty("iconName", icon)
        widget.setIcon(lucide_icon(icon, "#11130d" if accent else None, 18)); widget.setIconSize(QSize(18,18))
    if callback: widget.clicked.connect(callback)
    if tooltip: widget.setToolTip(tooltip)
    return widget


def tool_button(icon: str, callback=None, tooltip="", checkable=False) -> QToolButton:
    widget=QToolButton(); widget.setProperty("iconName", icon)
    widget.setIcon(lucide_icon(icon, None, 18)); widget.setIconSize(QSize(18,18))
    widget.setProperty("editorTool",True); widget.setCheckable(checkable); widget.setToolTip(tooltip)
    if callback:widget.clicked.connect(callback)
    return widget



def timecode(seconds: float, fps: int = 60) -> str:
    frames=round(max(0,seconds)*fps); return f"{frames//(fps*3600):02d}:{(frames//(fps*60))%60:02d}:{(frames//fps)%60:02d}:{frames%fps:02d}"


class CaptionPanel(QWidget):
    changed = Signal()
    seek = Signal(float)

    def __init__(self, project_getter, parent=None):
        super().__init__(parent); self.project_getter=project_getter
        layout=QVBoxLayout(self); layout.setContentsMargins(8,8,8,8)
        actions=QHBoxLayout(); actions.addWidget(button("+ Caption",self.add)); actions.addWidget(button("+ Hook",self.add_hook)); actions.addWidget(button("Split",self.split)); actions.addWidget(button("Merge",self.merge)); layout.addLayout(actions)
        self.table=QTableWidget(0,3); self.table.setHorizontalHeaderLabels(["IN","OUT","TEXT"]); self.table.horizontalHeader().setStretchLastSection(True); self.table.verticalHeader().hide(); self.table.itemChanged.connect(self.edit); self.table.cellDoubleClicked.connect(self.jump); layout.addWidget(self.table,1)
        style=QGroupBox("CAPTION LOOK"); form=QFormLayout(style)
        self.style_name=QComboBox(); self.style_name.addItems(["Impact Pop","Clean Card","Streamer Lime","Minimal White"]); self.animation=QComboBox(); self.animation.addItems(["pop","word reveal","fade","none"])
        self.size=QSpinBox(); self.size.setRange(24,140); self.size.setValue(72)
        self.upper=QCheckBox("Uppercase"); self.apply_style=button("Apply to all",self.apply,accent=True)
        form.addRow("Template",self.style_name); form.addRow("Animation",self.animation); form.addRow("Size",self.size); form.addRow("",self.upper); form.addRow(self.apply_style); layout.addWidget(style)

    def refresh(self):
        project=self.project_getter(); self.table.blockSignals(True); self.table.setRowCount(len(project.captions))
        for row,c in enumerate(sorted(project.captions,key=lambda x:x.start)):
            a=QTableWidgetItem(f"{c.start:.2f}"); a.setData(Qt.UserRole,c.id); self.table.setItem(row,0,a); self.table.setItem(row,1,QTableWidgetItem(f"{c.end:.2f}")); self.table.setItem(row,2,QTableWidgetItem(c.text))
            if c.is_hook:
                for col in range(3): self.table.item(row,col).setBackground(QColor("#343b18"))
        self.table.blockSignals(False)

    def selected(self):
        project=self.project_getter(); ids={self.table.item(i.row(),0).data(Qt.UserRole) for i in self.table.selectionModel().selectedRows()}
        return [c for c in project.captions if c.id in ids]

    def add(self):
        p=self.project_getter(); start=p.playhead; p.captions.append(Caption(uid(),start,start+1.5,"Double-click to edit")); self.refresh(); self.changed.emit()

    def add_hook(self):
        p=self.project_getter(); p.captions.append(Caption(uid(),0,min(5,max(1,p.duration)),"What happens next changes everything",CaptionStyle(name="Hook Card",size=62,color="#111216",outline="#FFFFFF",outline_width=0,animation="fade",position_y=.08),True)); self.refresh(); self.changed.emit()

    def split(self):
        selected=self.selected()
        if len(selected)!=1:return
        pair=split_caption(selected[0],self.project_getter().playhead)
        if pair:
            p=self.project_getter(); p.captions.remove(selected[0]); p.captions.extend(pair); self.refresh(); self.changed.emit()

    def merge(self):
        selected=self.selected(); merged=merge_captions(selected)
        if merged:
            p=self.project_getter(); p.captions=[c for c in p.captions if c not in selected]+[merged]; self.refresh(); self.changed.emit()

    def edit(self,item):
        if not item:return
        caption=next((c for c in self.project_getter().captions if c.id==self.table.item(item.row(),0).data(Qt.UserRole)),None)
        if not caption:return
        try:
            if item.column()==0: caption.start=float(item.text())
            elif item.column()==1: caption.end=float(item.text())
            else: caption.text=item.text()
            self.changed.emit()
        except ValueError:self.refresh()

    def jump(self,row,_): self.seek.emit(float(self.table.item(row,0).text()))

    def apply(self):
        p=self.project_getter(); name=self.style_name.currentText(); presets={
            "Impact Pop":dict(color="#FFFFFF",highlight="#E8FF4D",outline="#111318",outline_width=7),
            "Clean Card":dict(color="#FFFFFF",highlight="#FFFFFF",outline="#1A1B20",outline_width=4),
            "Streamer Lime":dict(color="#DFFF45",highlight="#FFFFFF",outline="#0A0B0E",outline_width=8),
            "Minimal White":dict(color="#FFFFFF",highlight="#FFFFFF",outline="#000000",outline_width=2),}
        style=p.subtitle_style
        style.name=name; style.animation=self.animation.currentText(); style.size=self.size.value(); style.uppercase=self.upper.isChecked()
        for key,value in presets[name].items():setattr(style,key,value)
        self.changed.emit(); self.refresh()


class ExportDialog(QDialog):
    def __init__(self, project:Project, settings:dict, parent=None):
        super().__init__(parent); self.project=project; self.settings=settings; self.output=""; self.share=None; self.setWindowTitle("Finish the short"); self.resize(570,440)
        layout=QVBoxLayout(self); title=QLabel("EXPORT / DELIVER"); title.setObjectName("brand"); layout.addWidget(title)
        form=QFormLayout(); self.preset=QComboBox(); self.preset.addItems(PRESETS.keys()); self.preset.setCurrentText("TikTok · Fast"); self.resolution=QComboBox(); self.resolution.addItems(["1080 × 1920","720 × 1280"]); self.resolution.setCurrentIndex(0 if project.settings.width==1080 else 1); self.hardware=QComboBox(); self.hardware.addItems(["Auto","CPU","NVIDIA","Intel/AMD"]); self.burn=QCheckBox("Burn captions into video"); self.burn.setChecked(True)
        self.path=QLineEdit(str(Path.home()/"Videos"/(project.name.replace(" ","-")+".mp4"))); browse=button("Browse",self.browse); pathrow=QHBoxLayout(); pathrow.addWidget(self.path,1); pathrow.addWidget(browse)
        self.estimate=QLabel(); form.addRow("Social preset",self.preset); form.addRow("Frame",self.resolution); form.addRow("Encoder",self.hardware); form.addRow("",self.burn); form.addRow("Save to",pathrow); form.addRow("Estimate",self.estimate); layout.addLayout(form)
        self.progress=QProgressBar(); self.progress.setRange(0,1000); self.status=QLabel("Ready"); layout.addWidget(self.progress); layout.addWidget(self.status)
        actions=QHBoxLayout(); self.render=button("Export video",self.begin,accent=True); self.phone=button("Send to phone",self.send_phone); self.phone.setEnabled(False); self.wireless=button("Wireless link",self.wireless_share); self.wireless.setEnabled(False); actions.addWidget(self.render); actions.addWidget(self.phone); actions.addWidget(self.wireless); layout.addLayout(actions)
        self.preset.currentTextChanged.connect(self.refresh_estimate); self.resolution.currentTextChanged.connect(self.refresh_estimate); self.refresh_estimate()

    def browse(self):
        path,_=QFileDialog.getSaveFileName(self,"Export vertical video",self.path.text(),"MP4 video (*.mp4)")
        if path:self.path.setText(path)

    def refresh_estimate(self):
        preset=PRESETS[self.preset.currentText()]; size,seconds=estimate(self.project,preset,self.hardware.currentText()!="CPU"); self.estimate.setText(f"≈ {size/1024/1024:.1f} MB  ·  roughly {seconds:.0f}s on this preset")

    def begin(self):
        self.output=self.path.text().strip()
        if not self.output:return
        if self.resolution.currentIndex()==0:self.project.settings.width,self.project.settings.height=1080,1920
        else:self.project.settings.width,self.project.settings.height=720,1280
        self.render.setEnabled(False); self.status.setText("Preparing FFmpeg graph…")
        def do_export():
            export(self.project,self.output,PRESETS[self.preset.currentText()],self.burn.isChecked(),self.hardware.currentText(),self.settings.get("ffmpeg","ffmpeg"),lambda value,text:self.signals.progress.emit((value,text)))
            return self.output
        worker=Worker(lambda: export(self.project,self.output,PRESETS[self.preset.currentText()],self.burn.isChecked(),self.hardware.currentText(),self.settings.get("ffmpeg","ffmpeg"),lambda value,text:worker.signals.progress.emit((value,text))) or self.output)
        worker.signals.progress.connect(lambda x:(self.progress.setValue(round(x[0]*1000)),self.status.setText(x[1])))
        worker.signals.result.connect(self.done); worker.signals.error.connect(self.failed); QThreadPool.globalInstance().start(worker)

    def done(self,path):
        self.output=path; self.progress.setValue(1000); self.status.setText("Finished · ready for your phone"); self.phone.setEnabled(True); self.wireless.setEnabled(True); self.render.setEnabled(True)

    def failed(self,detail):
        self.render.setEnabled(True); self.status.setText("Export failed"); QMessageBox.critical(self,"Export failed",detail[-2600:])

    def send_phone(self):
        adb=detect_adb_devices(); mtp=detect_mtp_devices();
        try:
            if adb: destination=send_adb(self.output,self.settings.get("phone_folder","/sdcard/Movies/KineticCut"),adb[0])
            elif mtp: destination=send_mtp(self.output,mtp[0])
            else: raise RuntimeError("No Android phone was detected. Unlock the phone, choose File Transfer for USB, or install ADB and enable USB debugging.")
            QMessageBox.information(self,"Sent to phone",f"Copied to {destination}")
        except Exception as error:QMessageBox.warning(self,"Phone delivery",str(error))

    def wireless_share(self):
        if self.share:self.share.stop()
        self.share=WirelessShare(self.output); url=self.share.start(); dialog=QDialog(self); dialog.setWindowTitle("Wireless delivery"); box=QVBoxLayout(dialog); box.addWidget(QLabel("Scan on your phone while both devices are on the same Wi-Fi."))
        try:
            import qrcode
            image=qrcode.make(url); from io import BytesIO; data=BytesIO(); image.save(data,format="PNG"); pix=QPixmap(); pix.loadFromData(data.getvalue()); label=QLabel(); label.setPixmap(pix.scaled(260,260,Qt.KeepAspectRatio,Qt.SmoothTransformation)); label.setAlignment(Qt.AlignCenter); box.addWidget(label)
        except ImportError:pass
        link=QLabel(f"<a style='color:#dfff45' href='{url}'>{url}</a>"); link.setOpenExternalLinks(True); link.setAlignment(Qt.AlignCenter); box.addWidget(link); close=QDialogButtonBox(QDialogButtonBox.Close); close.rejected.connect(dialog.reject); box.addWidget(close); dialog.exec()

    def closeEvent(self,event):
        if self.share:self.share.stop()
        super().closeEvent(event)


class MainWindow(QMainWindow):
    shutdownFinished=Signal()
    def __init__(self, startup_progress=None):
        progress=startup_progress or (lambda *_:None)
        progress(45,"Loading preferences and project services")
        super().__init__(); self.settings=load_settings(); self.project=Project(); self.thread_pool=QThreadPool.globalInstance(); self.current_media_id=""; self.current_play_item:TimelineItem|None=None; self.loading=False; self.shortcut_actions={}; self.proxies={}; self._workers=set(); self._history=[]; self._history_index=-1; self._restoring=False
        self.setWindowTitle("Kinetic Cut"); self.resize(1480,900); self.setMinimumSize(1100,700); self.setAcceptDrops(True)
        from .icons import resource_path
        self.setWindowIcon(QIcon(str(resource_path("assets","kinetic-cut.svg"))))
        progress(53,"Initializing preview playback")
        self.player=QMediaPlayer(self); self.audio=QAudioOutput(self); self.video_sink=QVideoSink(self); self.player.setAudioOutput(self.audio); self.player.setVideoSink(self.video_sink); self.audio.setVolume(.75)
        self.video_sink.videoFrameChanged.connect(self.source_video_frame,Qt.QueuedConnection)
        self.player.positionChanged.connect(self.player_position); self.player.playbackStateChanged.connect(self.play_state)
        progress(64,"Building timeline, inspector and effects")
        self.build_ui(); self.build_actions(); self.bind_shortcuts()
        progress(84,"Connecting audio and video transport")
        from .transport import TimelineTransport
        self.transport=TimelineTransport(self); self.transport.changed.connect(self.transport_position)
        self.transport.levelsChanged.connect(self.timeline.set_audio_levels)
        self.transport.levelsChanged.connect(self.inspector.set_audio_levels)
        from .compound_ui import CompoundController
        self.compounds=CompoundController(self)
        self.transport.stateChanged.connect(lambda playing:self.play_button.setIcon(lucide_icon("pause" if playing else "play")))
        self.transport.stateChanged.connect(lambda playing:self.preview.set_transform_controls_visible(not playing and self.current_page==0 and self.transform_box_tool.isChecked()))
        self.transport.stateChanged.connect(lambda playing:None if playing else self.preview_quality.apply())
        self.transport.stateChanged.connect(lambda _:self.preview.update())
        progress(94,"Preparing workspace")
        self.set_project(self.project)
        self.autosave_timer=QTimer(self); self.autosave_timer.timeout.connect(self.autosave); self.autosave_timer.start(15000)
        self.autosave_debounce_timer=QTimer(self); self.autosave_debounce_timer.setSingleShot(True); self.autosave_debounce_timer.setInterval(1500); self.autosave_debounce_timer.timeout.connect(self.autosave)
        self.statusBar().showMessage("Ready · Drop stream clips anywhere to begin")
        from .assistant import AssistantConnection
        self.assistant_connection=AssistantConnection(self)
        self.assistant_button=button('AI Assistant',self.assistant_connection.show,quiet=True,tooltip='MCP connection setup and status — no built-in chatbot',icon='sparkles')
        self.assistant_button.setObjectName('assistantConnectionButton')
        self.menuBar().setCornerWidget(self.assistant_button,Qt.TopRightCorner)
        self.assistant_connection.changed.connect(self.assistant_connection.refresh_button)
        self.assistant_connection.refresh_button()
        crashed_previous=SESSION_LOCK_PATH.exists() and AUTOSAVE_PATH.exists() and AUTOSAVE_PATH.stat().st_size>50
        try:
            import time
            SESSION_LOCK_PATH.write_text(f"pid={os.getpid()}\ntime={time.time()}\n",encoding="utf-8")
        except Exception:logging.exception("Could not write active session lock")

        if crashed_previous:QTimer.singleShot(350,self.check_crash_recovery)
        active_theme = self.settings.get("ui_theme", "default")
        self.apply_theme(active_theme, save=False)



    def build_ui(self):
        from .workspace import build_workspace
        build_workspace(self)

    def build_actions(self):
        self.editing_actions=[]
        file_menu=self.menuBar().addMenu("File"); edit_menu=self.menuBar().addMenu("Edit"); workflow=self.menuBar().addMenu("Workflow")

        # File menu
        act_new = QAction("New project", self); act_new.triggered.connect(self.new_project); act_new.setShortcut(QKeySequence("Ctrl+N")); file_menu.addAction(act_new)
        act_open = QAction("Open project…", self); act_open.triggered.connect(self.open_project); act_open.setShortcut(QKeySequence("Ctrl+O")); file_menu.addAction(act_open)
        self.recent_menu = file_menu.addMenu("Open Recent")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        act_rec = QAction("Open Last Recovery File…", self); act_rec.triggered.connect(self.offer_manual_recovery); file_menu.addAction(act_rec)
        file_menu.addSeparator()
        act_save = QAction("Save project", self); act_save.triggered.connect(self.save_project); act_save.setShortcut(QKeySequence("Ctrl+S")); file_menu.addAction(act_save); self.shortcut_actions["save"]=act_save
        act_save_as = QAction("Save project as…", self); act_save_as.triggered.connect(lambda:self.save_project(True)); act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S")); file_menu.addAction(act_save_as)
        act_versions = QAction("Restore saved version…", self); act_versions.triggered.connect(self.restore_saved_version); file_menu.addAction(act_versions)
        file_menu.addSeparator()
        manager=QAction("Project Manager…",self); manager.triggered.connect(self.open_project_manager); file_menu.addAction(manager)
        self.project_settings_action=QAction("Project Settings…",self); self.project_settings_action.triggered.connect(self.open_project_settings); file_menu.addAction(self.project_settings_action); self.editing_actions.append(self.project_settings_action)
        file_menu.addSeparator()
        act_cache = QAction("Cache Manager…", self); act_cache.triggered.connect(self.open_cache_manager); file_menu.addAction(act_cache)
        act_components = QAction("Optional downloads…", self)
        act_components.triggered.connect(self.open_optional_downloads); file_menu.addAction(act_components)
        act_updates = QAction("Check for updates…", self)
        act_updates.triggered.connect(self.check_for_updates); file_menu.addAction(act_updates)
        act_themes = QAction("UI Themes…", self); act_themes.triggered.connect(self.open_ui_themes_dialog); file_menu.addAction(act_themes)

        # Preserved application shortcuts (removed from File menu per design)
        act_import = QAction("Import Media", self); act_import.triggered.connect(self.import_media); act_import.setShortcut(QKeySequence(self.settings.get("shortcuts", {}).get("import", "Ctrl+I"))); self.addAction(act_import); self.shortcut_actions["import"]=act_import; self.editing_actions.append(act_import)
        act_dl = QAction("Download Media", self); act_dl.triggered.connect(self.open_media_downloader); act_dl.setShortcut(QKeySequence("Ctrl+Shift+D")); self.addAction(act_dl)
        act_export = QAction("Export", self); act_export.triggered.connect(self.open_export); act_export.setShortcut(QKeySequence(self.settings.get("shortcuts", {}).get("export", "Ctrl+E"))); self.addAction(act_export); self.shortcut_actions["export"]=act_export

        # Edit and Workflow menus
        entries=[(edit_menu,"Undo",self.undo,"Ctrl+Z","undo"),(edit_menu,"Redo",self.redo,"Ctrl+Shift+Z","redo"),(edit_menu,"Select All",self.select_all,"Ctrl+A",None),(edit_menu,"Split Clip",self.split_selected,"Ctrl+B","cut"),(edit_menu,"Delete gaps",self.delete_gaps,"",None),(edit_menu,"Lift",lambda:self.delete_selected(False),"Backspace","delete"),(edit_menu,"Ripple Delete",lambda:self.delete_selected(True),"Delete","ripple_delete"),(workflow,"Apply vertical layout",self.apply_vertical,"V","vertical_layout"),(workflow,"Remove Silence (linked audio)",self.remove_silence,"Shift+S","remove_silence"),(workflow,"Generate captions",self.generate_captions,"G","captions"),(workflow,"Generate TTS Dialogue…",self.generate_tts_dialogue,"","tts_dialogue"),(workflow,"AI Voiceover (Text to Speech)…",self.open_tts_dialog,"Alt+T",None),(workflow,"Instant cut package",self.instant_package,"Ctrl+Shift+I","instant_package"),(workflow,"Save layout template…",self.save_template,"",None),(workflow,"Apply layout template…",self.apply_template,"",None),(workflow,"UI Themes…",self.open_ui_themes_dialog,"",None),(workflow,"Settings…",self.open_settings,"Ctrl+,",None)]
        for menu,text,callback,shortcut,logical in entries:
            action=QAction(text,self); action.triggered.connect(callback)
            if shortcut:action.setShortcut(QKeySequence(self.settings.get("shortcuts",{}).get(logical,shortcut) if logical else shortcut))
            if logical:self.shortcut_actions[logical]=action
            # Keep existing keyboard shortcuts/actions while simplifying the
            # visible Workflow menu to Settings alone.
            if menu is workflow and text != "Settings…":self.addAction(action)
            else:menu.addAction(action)
            if text not in {"Settings…"}:self.editing_actions.append(action)
        edit_menu.addSeparator()
        for command,key in (("cut","Ctrl+X"),("copy","Ctrl+C"),("paste","Ctrl+V")):
            action=QAction(command.title(),self); action.setShortcut(QKeySequence(key)); action.triggered.connect(lambda checked=False,c=command:self.timeline_clipboard(c)); edit_menu.addAction(action); self.editing_actions.append(action)
        attributes=QAction("Paste Attributes…",self); attributes.setShortcut(QKeySequence("Alt+V")); attributes.triggered.connect(self.paste_attributes); edit_menu.addAction(attributes); self.editing_actions.append(attributes)

    def bind_shortcuts(self):
        action=QAction(self); action.setShortcut(QKeySequence(self.settings["shortcuts"].get("retime_controls","Ctrl+R"))); action.triggered.connect(self.timeline.toggle_retime); self.addAction(action); self.shortcut_actions["retime_controls"]=action
        for key,callback in [("Ctrl+Shift+L",lambda:self.link_toggle.toggle()),("Ctrl+Alt+L",lambda:self.timeline.link_clips(False))]:
            action=QAction(self); action.setShortcut(QKeySequence(key)); action.triggered.connect(callback); self.addAction(action); self.editing_actions.append(action)
        # The conventional editing shortcuts are registered as actions; transport keys need no modifiers.
        for logical,key,callback in (("play_pause","Space",self.toggle_play),("shuttle_back","J",lambda:self.shuttle(-1)),("shuttle_stop","K",self.stop),("shuttle_forward","L",lambda:self.shuttle(1)),("mark_in","I",self.mark_in),("mark_out","O",self.mark_out)):
            action=QAction(self); action.setShortcut(QKeySequence(self.settings["shortcuts"].get(logical,key))); action.setShortcutContext(Qt.ApplicationShortcut); action.triggered.connect(callback); self.addAction(action); self.shortcut_actions[logical]=action
        for logical,key,callback in (("selection_mode","A",lambda:self.set_timeline_tool("select")),("blade_mode","B",lambda:self.set_timeline_tool("blade")),("crop_selected","C",lambda:self.frame_source(self.timeline.selected_id)),("snapping","N",self.toggle_snapping)):
            action=QAction(self); action.setShortcut(QKeySequence(self.settings["shortcuts"].get(logical,key))); action.setShortcutContext(Qt.ApplicationShortcut); action.triggered.connect(callback); self.addAction(action); self.shortcut_actions[logical]=action

    def apply_shortcuts(self):
        for logical,action in self.shortcut_actions.items():
            action.setShortcut(QKeySequence(self.settings.get("shortcuts",{}).get(logical,"")))

    def set_project(self,project:Project):
        self.flush_text_edit()
        if getattr(self,"current_page",0):
            from .workspace import set_page
            set_page(self,0)
        if hasattr(self,"transport"):self.transport.pause()
        # Older builds imported Power Bin preset wrappers into Master. Remove
        # only unused wrappers, never referenced media or any source file.
        used_media={i.media_id for i in project.timeline}
        project.media=[m for m in project.media if not m.timeline_preset or m.id in used_media]
        project.ensure_track_model(); self.project=project; self.preview.set_project(project); self.timeline.set_project(project); self.project_label.setText(project.name); self.caption_panel.refresh(); self.refresh_media(); self.seek(project.playhead)
        self.timeline.set_audio_levels({}); self.inspector.set_audio_levels({})
        self.timeline.waveforms={key:value for key,value in self.timeline.waveforms.items() if project.media_by_id(key)}
        self.timeline.waveform_pending.clear(); self.timeline.waveform_failures.clear()
        self.refresh_project_settings()
        self.refresh_inspector()
        if not self._restoring:self._history=[copy.deepcopy(project)]; self._history_index=0
        for media in project.media:
            self.request_waveform(media)
        if hasattr(self,'compounds'):self.compounds.switched()
        self.preview_quality.apply(); self.preview_quality.request()

    def request_waveform(self,media):
        from .missing_media import is_missing
        if is_missing(media):return
        if not (media.has_audio or media.kind=='audio'):return
        if not hasattr(self,'_waveform_pending'):self._waveform_pending=set()
        if not hasattr(self,'_waveform_sources'):self._waveform_sources={}
        from .waveforms import source_key
        key=(media.id,source_key(media.path))
        if self._waveform_sources.get(media.id)!=key:
            self.timeline.waveforms.pop(media.id,None)
            self.timeline.waveform_failures.discard(media.id)
            self._waveform_sources[media.id]=key
        if media.id in self.timeline.waveforms:return
        self.timeline.waveform_pending.add(media.id); self.timeline.waveform_failures.discard(media.id)
        # A compound's audio is published atomically with its render cache. Keep
        # this visibly pending, and request again when preparation finishes.
        if media.compound and not Path(media.path).is_file():return
        if key in self._waveform_pending:return
        self._waveform_pending.add(key)
        media_id=media.id; source=media.path
        def current_matches():
            current=self.project.media_by_id(media_id)
            return current and (media_id,source_key(current.path))==key
        def ready(values):
            if current_matches():
                self.timeline.waveform_failures.discard(media_id)
                self.timeline.set_waveform(media_id,values)
        worker=Worker(waveform,source,self.settings.get('ffmpeg','ffmpeg'))
        def failed(_):
            if current_matches():self.timeline.waveform_failures.add(media_id)
        def finished():
            self._waveform_pending.discard(key)
            if current_matches():self.timeline.waveform_pending.discard(media_id)
            self.timeline.viewport().update()
        worker.signals.result.connect(ready); worker.signals.error.connect(failed); worker.signals.finished.connect(finished); self.start_worker(worker)

    def _history_key(self,project):
        payload=project.to_dict(); payload.pop("modified_at",None); payload.pop("playhead",None); return json.dumps(payload,sort_keys=True,default=str)
    def commit_history(self):
        if self._restoring or getattr(self,"_property_scrubbing",False):return
        if hasattr(self,'_text_history_timer'):self._text_history_timer.stop()
        from dataclasses import fields
        previous=self._history[self._history_index] if self._history_index>=0 else None
        if previous and all(getattr(previous,f.name)==getattr(self.project,f.name) for f in fields(Project) if f.name not in {'playhead','modified_at'}):return
        # History objects are immutable; reuse unchanged records between snapshots.
        # Only changed live records are copied, never referenced from history.
        snapshot=copy.copy(self.project)
        for field in fields(Project):
            value=getattr(self.project,field.name)
            if previous and field.name in {'timeline','captions','media'}:
                old={i.id:i for i in getattr(previous,field.name)}
                value=[old[i.id] if i.id in old and old[i.id]==i else copy.deepcopy(i) for i in value]
            else:value=copy.deepcopy(value)
            setattr(snapshot,field.name,value)
        self._history=self._history[:self._history_index+1]; self._history.append(snapshot)
        if len(self._history)>100:self._history.pop(0)
        self._history_index=len(self._history)-1
        if hasattr(self,"autosave_debounce_timer"):self.autosave_debounce_timer.start()
    def text_edited(self):
        self.project.touch(); self.preview.update(); self.timeline.viewport().update()
        if not hasattr(self,'_text_history_timer'):
            self._text_history_timer=QTimer(self); self._text_history_timer.setSingleShot(True); self._text_history_timer.timeout.connect(self.commit_history)
        self._text_history_timer.start(350)
    def flush_text_edit(self):
        if hasattr(self,'_text_history_timer') and self._text_history_timer.isActive():self.commit_history()
    def _restore_history(self,index):
        if self._restoring or index<0 or index>=len(self._history):return
        self._history_index=index; self._restoring=True
        try:
            position=self.project.playhead
            old_media=self.project.media if self.project else []
            self.project=copy.deepcopy(self._history[index]); self.project.playhead=position
            self.project.ensure_track_model(); self.preview.set_project(self.project); self.timeline.set_project(self.project); self.project_label.setText(self.project.name); self.caption_panel.refresh()
            if self.project.media!=old_media:
                self.refresh_media()
            self.seek(position); self.refresh_inspector()
            self.refresh_project_settings()
        finally:self._restoring=False
        self._schedule_history_settled()
    def _schedule_history_settled(self):
        if not hasattr(self,'_history_settle_timer'):
            self._history_settle_timer=QTimer(self); self._history_settle_timer.setSingleShot(True); self._history_settle_timer.timeout.connect(self._on_history_settled)
        self._history_settle_timer.start(80)
    def _on_history_settled(self):
        if self._restoring:return
        if hasattr(self,"transport"):
            self.transport.seek(self.project.playhead)
        self.compounds.synchronize(); self.compounds.request_caches()
        self.preview_quality.request()
        for media in self.project.media:self.request_waveform(media)
    @edit_only
    def undo(self):
        if self._restoring:return
        self.flush_text_edit(); self._restore_history(self._history_index-1)
    @edit_only
    def redo(self):
        if self._restoring:return
        self._restore_history(self._history_index+1)

    def start_worker(self,worker:Worker):
        if getattr(self, '_closing', False):
            worker.cancel()
            worker.signals.deleteLater()
            return
        self._workers.add(worker)
        self.update_job_status()
        worker.signals.finished.connect(self.worker_finished,Qt.QueuedConnection)
        self.thread_pool.start(worker)

    def update_job_status(self):
        if not hasattr(self,"job_status"):return
        # File/folder presence polling is maintenance, not an import/render job.
        # Keep its lifetime tracked for shutdown without relayout/animation on
        # every no-change scan while the owner plays or interacts with the UI.
        count=sum(not getattr(job,'maintenance',False) for job in self._workers)
        self.job_status.setVisible(count>0); self.job_progress.setVisible(count>0)
        self.job_status.setText(f"{count} background task{'s' if count!=1 else ''}")
        self.job_status.setToolTip("Processing media, audio previews or renders. The workspace remains responsive.")

    @Slot()
    def worker_finished(self):
        signals=self.sender()
        worker=next((job for job in self._workers if job.signals is signals),None)
        if worker is None:return
        self._workers.discard(worker)
        # Release signal callbacks and their captured project/media snapshots once
        # queued result/error handlers have run. Never destroy them in Worker.run.
        signals.deleteLater()
        self.update_job_status()

    def check_crash_recovery(self):
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or (QApplication.instance() and QApplication.platformName() == "offscreen"):
            return
        if not AUTOSAVE_PATH.exists() or AUTOSAVE_PATH.stat().st_size < 50:
            return
        try:
            import time
            info = json.loads(AUTOSAVE_PATH.read_text(encoding="utf-8"))
            proj_name = info.get("name", "Untitled Short")
            clip_count = len(info.get("timeline", []))
            media_count = len(info.get("media", []))
            mtime = AUTOSAVE_PATH.stat().st_mtime
            time_str = time.strftime("%b %d, %Y at %I:%M %p", time.localtime(mtime))
        except Exception:
            proj_name = "Autosaved Project"
            clip_count = "?"
            media_count = "?"
            time_str = "recent"

        box = QMessageBox(self)
        box.setWindowTitle("Crash Recovery Detected")
        box.setIcon(QMessageBox.Question)
        box.setText(
            "<h3>Recover Unsaved Work?</h3>"
            "<p>Kinetic Cut detected an unexpected shutdown during your last session.</p>"
            f"<p><b>Project:</b> {proj_name}<br>"
            f"<b>Saved:</b> {time_str}<br>"
            f"<b>Timeline:</b> {clip_count} clip(s), {media_count} media file(s)</p>"
            "<p>Would you like to recover this project now?</p>"
        )
        recover_btn = box.addButton("Recover Project", QMessageBox.AcceptRole)
        discard_btn = box.addButton("Discard Work", QMessageBox.DestructiveRole)
        box.setDefaultButton(recover_btn)
        box.exec()

        if box.clickedButton() == recover_btn:
            try:
                backup_dir = CACHE_DIR / "recovered"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"recovered_{int(time.time())}.kcut"
                shutil.copy2(AUTOSAVE_PATH, backup_path)

                loaded = Project.load(AUTOSAVE_PATH)
                self.set_project(loaded)
                self.project.path = ""
                self._saved_project_key = None
                self.commit_history()
                self.statusBar().showMessage(f"Recovered '{proj_name}' from crash · Remember to save your project", 8000)
            except Exception as error:
                logging.exception("Failed to recover autosaved project")
                QMessageBox.critical(self, "Recovery Failed", f"Could not recover autosaved project:\n{error}")
        elif box.clickedButton() == discard_btn:
            confirm = QMessageBox.question(
                self,
                "Discard Autosave?",
                "Are you sure you want to permanently discard this autosaved work?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                try:
                    AUTOSAVE_PATH.unlink(missing_ok=True)
                    self.statusBar().showMessage("Autosave discarded", 3000)
                except Exception:
                    pass

    def offer_manual_recovery(self):
        from .project_manager import folder
        from PySide6.QtGui import QCursor
        from .config import DATA_DIR
        import time
        candidates = []
        for p in [DATA_DIR / "recovery_backup_user_work.kcut", AUTOSAVE_PATH]:
            if p.is_file() and p.stat().st_size > 50 and p not in candidates:
                candidates.append(p)
        rec_dir = CACHE_DIR / "recovered"
        if rec_dir.is_dir():
            for p in sorted(rec_dir.glob("*.kcut"), key=lambda x: x.stat().st_mtime, reverse=True):
                if p not in candidates:
                    candidates.append(p)
        root_dir = folder(self.settings)
        if root_dir.is_dir():
            for p in root_dir.glob("Recovered*.kcut"):
                if p not in candidates:
                    candidates.append(p)

        if not candidates:
            path, _ = QFileDialog.getOpenFileName(self, "Open Recovery File", str(DATA_DIR), "Kinetic Cut (*.kcut);;All Files (*)")
            if path:
                self.load_project_path(path)
            return

        menu = QMenu(self)
        for c in candidates:
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
                mtime = time.strftime("%b %d %I:%M %p", time.localtime(c.stat().st_mtime))
                label = f"{c.stem} — {data.get('name', 'Project')} ({len(data.get('timeline', []))} clips · {mtime})"
            except Exception:
                label = f"{c.name} ({c.stat().st_size} bytes)"
            menu.addAction(label, lambda p=str(c.resolve()): self.load_project_path(p))
        menu.addSeparator()
        menu.addAction("Browse all recovery files in Data folder…", self._browse_manual_recovery)
        menu.exec(QCursor.pos())

    def _browse_manual_recovery(self):
        from .config import DATA_DIR
        path, _ = QFileDialog.getOpenFileName(self, "Open Recovery File", str(DATA_DIR), "Kinetic Cut (*.kcut);;All Files (*)")
        if path:
            self.load_project_path(path)

    def offer_recovery(self):
        self.offer_manual_recovery()

    @edit_only
    def open_tts_dialog(self, initial_text: str = ""):
        from .tts_dialog import TTSDialog
        if not initial_text and getattr(self, "timeline", None) and self.timeline.selected_caption:
            cap = next((c for c in self.project.captions if c.id == self.timeline.selected_caption), None)
            if cap:
                initial_text = cap.text

        destination = self.project
        dialog = TTSDialog(self, initial_text=initial_text)
        if (dialog.exec() == QDialog.Accepted and dialog.generated_data
                and self.project is destination and not getattr(self, '_closing', False)):
            self._apply_generated_tts(dialog.generated_data)

    def _apply_generated_tts(self, data: dict):
        audio_path = data["audio_path"]
        text = data["text"]
        insert_timeline = data.get("insert_timeline", True)
        dest_track = data.get("destination_track", "auto")
        gen_captions = data.get("generate_captions", True)

        try:
            probed = probe(audio_path, self.settings.get("ffprobe", "ffprobe"), self.settings.get("ffmpeg", "ffmpeg"))
        except Exception as err:
            logging.exception("Failed to probe TTS audio")
            QMessageBox.warning(self, "TTS Import Failed", f"Could not index synthesized audio:\n{err}")
            return

        self.project.add_media(probed)
        self.refresh_media()
        self.request_waveform(probed)

        if insert_timeline:
            if dest_track == "auto" or dest_track not in self.project.audio_tracks:
                dest_track = self.project.audio_tracks[0] if self.project.audio_tracks else self.project.add_track("audio")

            start = self.project.playhead
            duration = max(0.1, probed.duration)
            clip_id = uid()
            item = TimelineItem(
                id=clip_id,
                media_id=probed.id,
                track=dest_track,
                start=start,
                duration=duration,
                in_point=0.0,
                group_id=uid(),
                role="sfx"
            )
            self.project.timeline.append(item)
            self.project.overwrite({clip_id})

            if gen_captions:
                sentences = [s.strip() for s in re.split(r'(?<=[.!?\n])\s+', text) if s.strip()]
                if not sentences:
                    sentences = [text]
                total_chars = max(1, sum(len(s) for s in sentences))
                cur_start = start
                cap_ids = set()
                for s in sentences:
                    s_dur = duration * (len(s) / total_chars)
                    cap = Caption(uid(), cur_start, cur_start + s_dur, s)
                    self.project.captions.append(cap)
                    cap_ids.add(cap.id)
                    cur_start += s_dur
                if cap_ids:
                    self.project.overwrite_captions(cap_ids)

            self.timeline.select_ids({clip_id})
            self.statusBar().showMessage(f"Generated voiceover: '{text[:30]}…' ({duration:.1f}s)", 4000)
            self.model_changed()

    @edit_only
    def generate_tts_dialogue(
        self,
        initial_text: str = "",
        voice: str = "adam-narrator",
        headless: bool = False,
        start: float | None = None,
        track: str | None = None,
        rate: int = 0,
        pitch: int = 0,
        gain_db: float = 0.0
    ):
        if not initial_text and getattr(self, "timeline", None) and self.timeline.selected_caption:
            cap = next((c for c in self.project.captions if c.id == self.timeline.selected_caption), None)
            if cap:
                initial_text = cap.text

        if headless or (initial_text and voice and not QApplication.activeModalWidget()):
            # Headless / MCP programmatic execution
            from .tts import synthesize_speech
            # Preserve the synchronous MCP result while allowing the GUI to
            # process playback, close/cancel and project-switch events.
            destination = self.project
            destination_key = self._history_key(destination)
            cancel = threading.Event()
            loop = QEventLoop(self)
            result, errors = [], []
            worker = Worker(synthesize_speech, initial_text, voice=voice,
                            rate_percent=rate, pitch_hz=pitch,
                            ffmpeg_bin=self.settings.get('ffmpeg', 'ffmpeg'),
                            cancel_check=cancel.is_set)
            worker.cancel_callback = cancel.set
            worker.signals.result.connect(result.append)
            worker.signals.error.connect(errors.append)
            worker.signals.finished.connect(loop.quit)
            self.start_worker(worker)
            if not getattr(self, '_closing', False):loop.exec()
            loop.deleteLater()
            if getattr(self, '_closing', False) or cancel.is_set():return None
            if errors:raise RuntimeError(errors[0])
            if not result:return None
            if self.project is not destination or self._history_key(destination)!=destination_key:
                self.statusBar().showMessage('Dialogue result discarded because the project changed', 5000)
                return None
            audio_path = result[0]
            return self._apply_generated_dialogue({
                "audio_path": audio_path,
                "text": initial_text,
                "start": start,
                "track": track,
                "gain_db": gain_db
            })

        destination = self.project
        from .tts_dialogue_dialog import TTSDialogueDialog
        dialog = TTSDialogueDialog(self, initial_text=initial_text)
        res = dialog.exec()
        data = getattr(dialog, "result_data", None)
        dialog.deleteLater()
        QApplication.processEvents()

        if res == QDialog.Accepted and data and self.project is destination and not getattr(self, '_closing', False):
            return self._apply_generated_dialogue(data)
        return None

    def _apply_generated_dialogue(self, data: dict):
        audio_path = data.get("audio_path", "")
        text = data.get("text", "")
        if not audio_path:
            return None

        try:
            probed = probe(audio_path, self.settings.get("ffprobe", "ffprobe"), self.settings.get("ffmpeg", "ffmpeg"))
        except Exception as err:
            logging.exception("Failed to probe TTS dialogue audio")
            if not getattr(self, "_headless_api", False) and not QApplication.activeModalWidget():
                QMessageBox.warning(self, "TTS Dialogue Import Failed", f"Could not index synthesized dialogue audio:\n{err}")
            return None

        self.project.add_media(probed)
        self.refresh_media()
        self.request_waveform(probed)

        start = data.get("start") if data.get("start") is not None else self.project.playhead
        duration = max(0.1, probed.duration)

        dest_track = data.get("track")
        if not dest_track or dest_track not in self.project.audio_tracks or self.project.track_states.get(dest_track, {}).get("locked"):
            dest_track = None
            for track_id in self.project.audio_tracks:
                if self.project.track_states.get(track_id, {}).get("locked"):
                    continue
                overlaps = any(
                    item.track == track_id and not (start + duration <= item.start or start >= item.start + item.duration)
                    for item in self.project.timeline
                )
                if not overlaps:
                    dest_track = track_id
                    break

        if not dest_track:
            dest_track = self.project.add_track("audio")

        clip_id = uid()
        gain_db = float(data.get("gain_db", 0.0))
        item = TimelineItem(
            id=clip_id,
            media_id=probed.id,
            track=dest_track,
            start=start,
            duration=duration,
            in_point=0.0,
            group_id=uid(),
            role="source_audio",
            gain_db=gain_db,
        )
        self.project.timeline.append(item)
        try:
            self.project.overwrite({clip_id})
        except Exception as err:
            logging.warning("Non-fatal overwrite conflict in dialogue placement: %s", err)

        self.timeline.select_ids({clip_id})
        self.seek(start)
        self.commit_history()
        self.model_changed()
        self.statusBar().showMessage(f"Generated TTS dialogue ({duration:.1f}s) placed on track {dest_track}.", 4000)
        return {
            "media_id": probed.id,
            "clip_id": clip_id,
            "track": dest_track,
            "start": start,
            "duration": duration,
            "path": probed.path
        }

    def new_project(self):
        from .project_settings import ProjectSettingsDialog
        dialog=ProjectSettingsDialog(Project(),self,new_project=True); dialog.setWindowTitle("New Project — Settings")
        for box in dialog.findChildren(QDialogButtonBox):box.button(QDialogButtonBox.Save).setText("Create Project")
        if dialog.exec()!=QDialog.Accepted:return
        if not self.confirm_project_switch():return
        p=Project(); p.name,p.settings=dialog.values(); self.set_project(p); self._saved_project_key=None

    def confirm_project_switch(self):
        if not (self.project.timeline or self.project.media or self.project.captions):return True
        if getattr(self,"_saved_project_key",None)==self._history_key(self.project):return True
        answer=QMessageBox.question(self,"Save current project?","Save your changes before switching projects?",QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        if answer==QMessageBox.Cancel:return False
        return bool(self.save_project()) if answer==QMessageBox.Save else True

    def open_project_manager(self):
        from .project_manager import ProjectManagerDialog
        dialog=ProjectManagerDialog(self)
        if dialog.exec()==QDialog.Accepted:
            if dialog.choice:self.load_project_path(dialog.choice)
            else:self.new_project()

    def _populate_recent_menu(self):
        self.recent_menu.clear()
        recent = [p for p in self.settings.get("recent_projects", []) if p and Path(p).is_file()][:10]
        if not recent:
            no_rec = QAction("No Recent Projects", self)
            no_rec.setEnabled(False)
            self.recent_menu.addAction(no_rec)
            return
        for path_str in recent:
            name = Path(path_str).name
            action = QAction(name, self)
            action.setToolTip(path_str)
            action.setStatusTip(path_str)
            action.triggered.connect(lambda checked=False, p=path_str: self.load_project_path(p))
            self.recent_menu.addAction(action)
        self.recent_menu.addSeparator()
        clear_act = QAction("Clear Recent Projects", self)
        clear_act.triggered.connect(self._clear_recent_projects)
        self.recent_menu.addAction(clear_act)

    def _clear_recent_projects(self):
        self.settings["recent_projects"] = []
        from .config import save_settings
        save_settings(self.settings)

    def check_for_updates(self, checked=False, startup=False):
        from .update_ui import UpdateController
        if not hasattr(self, 'update_controller'):
            self.update_controller = UpdateController(self)
        self.update_controller.check(startup=startup)

    def open_optional_downloads(self):
        from .component_ui import ComponentsDialog
        ComponentsDialog(self).exec()

    def open_ui_themes_dialog(self):
        from .theme_dialog import UIThemesDialog
        dialog = UIThemesDialog(self)
        dialog.exec()

    def open_cache_manager(self):
        from .cache_manager import CacheManagerDialog
        CacheManagerDialog(self).exec()

    def apply_theme(self, theme_id: str, save: bool = True):
        from .theme import get_theme_stylesheet, get_active_theme_palette, PALETTES
        if theme_id not in PALETTES:
            theme_id = "default"
        self.settings["ui_theme"] = theme_id
        if save:
            from .config import save_settings
            save_settings(self.settings)

        palette = get_active_theme_palette(theme_id)
        from .icons import set_current_icon_color
        set_current_icon_color(palette.get("icon_color", "#d8dae0"))

        from .theme_widgets import apply_application_theme
        apply_application_theme(theme_id)

        if hasattr(self, "preview") and self.preview:
            self.preview.set_theme(palette)

        if hasattr(self, "timeline") and self.timeline:
            self.timeline.set_theme(palette)

        from .workspace import refresh_workspace_theme
        refresh_workspace_theme(self, palette)


    def load_project_path(self,path):
        from .project_manager import remember
        from .config import save_settings
        try:project=Project.load(path)
        except Exception as error:QMessageBox.critical(self,"Open failed",str(error)); return False
        if not self.confirm_project_switch():return False
        self.set_project(project); self._saved_project_key=self._history_key(project)
        from .close_guard import mark_saved
        mark_saved(self,project); remember(self,path)
        self.settings["last_open_project_dir"] = str(Path(path).parent)
        save_settings(self.settings)
        return True

    def open_project(self):
        from .project_manager import folder
        from .config import save_settings
        start_dir = self.settings.get("last_open_project_dir") or str(folder(self.settings))
        if not Path(start_dir).is_dir():
            start_dir = str(folder(self.settings))
        path,_=QFileDialog.getOpenFileName(self,"Open Kinetic Cut project",start_dir,"Kinetic Cut (*.kcut);;JSON (*.json)")
        if path:
            self.settings["last_open_project_dir"] = str(Path(path).parent)
            save_settings(self.settings)
            self.load_project_path(path)

    def save_project(self,save_as=False):
        from .project_manager import folder,remember
        from .config import save_settings
        from .project_safety import preserve_version
        document=self.compounds.root(); path=document.path
        if save_as or not path:
            start_dir = self.settings.get("last_open_project_dir") or str(folder(self.settings))
            if not Path(start_dir).is_dir():
                start_dir = str(folder(self.settings))
            root=Path(start_dir)
            try:root.mkdir(parents=True,exist_ok=True)
            except OSError as error:
                QMessageBox.warning(self,"Save failed",str(error)); return False
            name="".join(c if c not in '<>:"/\\|?*' else '_' for c in self.project.name)
            path,_=QFileDialog.getSaveFileName(self,"Save project",str(root/(name+".kcut")),"Kinetic Cut (*.kcut)")
        if path:
            if not Path(path).suffix:path += ".kcut"
            try:
                preserve_version(path)
                document.save(path)
            except Exception as error:QMessageBox.warning(self,"Save failed",str(error)); return False
            self._saved_project_key=self._history_key(self.project)
            from .close_guard import mark_saved
            mark_saved(self,document)
            self.settings["last_open_project_dir"] = str(Path(path).parent)
            save_settings(self.settings)
            try:remember(self,path,capture=True)
            except Exception:logging.exception("Could not cache project thumbnail")
            self.project_label.setText(self.project.name); self.statusBar().showMessage(f"Saved {Path(path).name}",3000); return True
        return False

    def restore_saved_version(self):
        from .project_safety import versions
        document=self.compounds.root()
        if not document.path:
            QMessageBox.information(self,"Saved versions","Save this project first to start a version history.")
            return
        available=versions(document.path)
        if not available:
            QMessageBox.information(self,"Saved versions","No earlier saved versions are available yet.")
            return
        labels=[f"{p.stat().st_mtime:%Y-%m-%d %H:%M:%S}  ·  {p.name}" for p in available]
        chosen,ok=QInputDialog.getItem(self,"Restore saved version","Choose a saved version to open as an unsaved edit:",labels,0,False)
        if not ok:return
        if not self.confirm_project_switch():return
        try:project=Project.load(available[labels.index(chosen)])
        except Exception as error:QMessageBox.warning(self,"Restore failed",str(error)); return
        project.path=""  # Save As, never overwrite the original project silently.
        self.set_project(project)
        self._saved_project_key=None
        self.statusBar().showMessage("Saved version opened as an unsaved edit — use Save As to keep it",7000)

    def collect_project_media(self):
        from .project_safety import collect_project
        document=self.compounds.root()
        parent=QFileDialog.getExistingDirectory(self,"Choose where to create the collected project folder",str(Path(document.path).parent) if document.path else str(Path.home()))
        if not parent:return
        suggested="".join(c if c not in '<>:"/\\|?*' else '_' for c in document.name).strip() or "Project"
        name,ok=QInputDialog.getText(self,"Collect project and media","New folder name:",text=suggested+" - Collected")
        if not ok or not name.strip():return
        if Path(name).name!=name or name in {'.','..'}:
            QMessageBox.warning(self,"Collect project","Enter one folder name, not a path."); return
        destination=Path(parent)/name
        if destination.exists():
            QMessageBox.warning(self,"Collect project",f"The destination already exists:\n{destination}"); return
        snapshot=copy.deepcopy(document)
        worker=Worker(lambda:collect_project(snapshot,destination,lambda update:worker.signals.progress.emit(update)))
        worker.signals.progress.connect(lambda update:self.statusBar().showMessage(f"Collecting media {update[0]}/{update[1]} · {update[2]}"))
        worker.signals.result.connect(lambda output:(self.statusBar().showMessage(f"Collected {output.name}",5000),QMessageBox.information(self,"Project collected",f"Portable copy created:\n{output}\n\nThe open project and its original sources were not changed.")))
        worker.signals.error.connect(lambda detail:(self.statusBar().showMessage("Project collection incomplete",7000),QMessageBox.warning(self,"Collection incomplete",f"No portable project was published. Check missing sources and retry.\n\n{detail.splitlines()[-1] if detail else 'Unknown error'}")))
        self.start_worker(worker)
        self.statusBar().showMessage(f"Collecting source media into {destination.name}…",5000)

    def autosave(self):
        document=self.compounds.root()
        if document.media or document.timeline:
            original=document.path
            try:
                document.save(AUTOSAVE_PATH)
            except Exception as error:
                logging.warning("Autosave skipped: %s", error)
            finally:
                document.path=original

    @edit_only
    def import_media(self):
        extensions=" ".join(f"*{x}" for x in sorted(VIDEO_EXTENSIONS|AUDIO_EXTENSIONS|IMAGE_EXTENSIONS)); paths,_=QFileDialog.getOpenFileNames(self,"Add clips, images or audio","",f"Media ({extensions});;All files (*)")
        if paths:self.add_media_paths(paths)

    def import_media_files(self, paths: list[str]):
        return self.add_media_paths(paths)

    @edit_only
    def open_media_downloader(self, initial_url: str = ""):
        from .downloader_dialog import MediaDownloaderDialog
        dialog = MediaDownloaderDialog(self, initial_url=initial_url)
        dialog.mediaDownloaded.connect(lambda path: self.add_media_paths([path]))
        dialog.exec()
        dialog.deleteLater()

    @edit_only
    def download_media(self, url: str, mode: str = "video", target_res: str = "", cookies_path: str = "", auto_import: bool = True) -> dict:
        """Download social media / YouTube video or audio and optionally import into the project."""
        from .downloader_dialog import download_media_synchronous
        from .media import probe
        destination=self.project
        cancel=threading.Event(); loop=QEventLoop(self); results=[]; errors=[]
        settings=copy.deepcopy(self.settings)
        def work():
            res=download_media_synchronous(url,mode=mode,target_res=target_res,cookies_path=cookies_path or None,cancel_check=cancel.is_set)
            path=res.get('path')
            item=probe(path,settings.get('ffprobe','ffprobe'),settings.get('ffmpeg','ffmpeg')) if auto_import and path and Path(path).is_file() else None
            return res,item
        worker=Worker(work); worker.cancel_callback=cancel.set
        worker.signals.result.connect(results.append); worker.signals.error.connect(errors.append); worker.signals.finished.connect(loop.quit)
        self.start_worker(worker)
        if not getattr(self,'_closing',False):loop.exec()
        loop.deleteLater()
        if cancel.is_set() or getattr(self,'_closing',False):raise InterruptedError('Download cancelled')
        if errors:raise RuntimeError(errors[0])
        if not results:raise RuntimeError('Download did not complete')
        res,probe_item=results[0]
        path = res.get("path")
        imported_media_id = None
        if probe_item and self.project is destination:
            self.media_added([probe_item])
            imported_media_id = probe_item.id
        res["media_id"] = imported_media_id
        res["imported"] = bool(imported_media_id)
        return res

    @edit_only
    def add_media_paths(self,paths:list[str]):
        valid=[p for p in paths if Path(p).is_file()]
        if not valid:return
        self.statusBar().showMessage(f"Indexing {len(valid)} media file(s)…")
        destination=self.project; settings=copy.deepcopy(self.settings); cancel=threading.Event()
        def work():
            items=[]
            for path in valid:
                if cancel.is_set():raise InterruptedError('Import cancelled')
                items.append(probe(path,settings.get('ffprobe','ffprobe'),settings.get('ffmpeg','ffmpeg'),timeout=30))
            return items
        def ready(items):
            if not cancel.is_set() and self.project is destination and not getattr(self,'_closing',False):self.media_added(items)
        worker=Worker(work); worker.cancel_callback=cancel.set
        worker.signals.result.connect(ready)
        worker.signals.error.connect(lambda detail:None if cancel.is_set() or getattr(self,'_closing',False) else QMessageBox.warning(self,'Media import',detail[-1800:]))
        self.start_worker(worker)

    def media_added(self,items):
        self.media_panel.on_import(items)
        for item in items:self.project.add_media(item)
        self.refresh_media(); self.statusBar().showMessage(f"Added {len(items)} item(s)",3000)
        if items:self.current_media_id=items[0].id
        self.commit_history()
        for media in items:
            self.request_waveform(media)
            if media.kind=="video" and media.video_codec=="av1":
                # Begin the compatibility job while the clip is still in the
                # pool, so placing it on the timeline need not start the wait.
                self.preview_quality.extra_ids.add(media.id)
                self.preview_quality.request()
            elif media.kind=="video" and (media.width>2560 or media.height>1440):
                self.queue_proxy(media)

    def refresh_media(self):
        if hasattr(self,"media_panel"):self.media_panel.refresh(); return
        if not hasattr(self,"media_list"):return
        filter_text=self.media_filter.currentText(); self.media_list.clear()
        for media in self.project.media:
            if filter_text=="Video" and media.kind!="video":continue
            if filter_text=="Audio + SFX" and media.kind!="audio":continue
            if filter_text=="Images" and media.kind!="image":continue
            duration=f"{int(media.duration)//60}:{int(media.duration)%60:02d}" if media.duration else "STILL"
            item=QListWidgetItem(f"{media.name}\n{media.kind.upper()}  ·  {duration}"); item.setData(Qt.UserRole,media.id)
            if media.thumbnail and Path(media.thumbnail).exists():item.setIcon(QIcon(media.thumbnail))
            self.media_list.addItem(item)

    def media_selected(self):
        selected=self.media_list.selectedItems()
        if not selected:return
        media=self.media_panel.resolve_media(selected[0].data(Qt.UserRole))
        if media:self.current_media_id=media.id

    def preview_media(self,media):
        if media.kind=="video":set_media_source(self.player,QUrl.fromLocalFile(self.proxies.get(media.id,media.path))); self.player.pause(); self.player.setPosition(round(self.project.mark_in*1000)); self.current_play_item=None
        elif media.kind=="image":self.preview.set_frame(QImage(media.path))

    def make_proxy(self):
        media=self.project.media_by_id(self.current_media_id)
        if media and media.kind=="video":self.queue_proxy(media)

    def queue_proxy(self,media):
        self.preview_quality.extra_ids.add(media.id); self.preview_quality.setCurrentIndex(1); self.preview_quality.request()

    def add_selected_to_timeline(self):
        self.media_panel.append_selected()

    @edit_only
    def add_media_batch(self,ids,track="",start=None):
        assets=[self.media_panel.resolve_media(id) for id in dict.fromkeys(ids) if id]; assets=[m for m in assets if m]
        self.insert_media_assets(assets,track,start)

    @edit_only
    def insert_media_assets(self,assets,track="",start=None):
        from .media_insert import plan,commit
        if not assets:return
        initial=self.project.duration if start is None else max(0.,float(start))
        try:
            stage,added,captions=plan(self.project,assets,track,initial)
        except (ValueError,KeyError,TypeError) as error:self.statusBar().showMessage(str(error),4500); return
        commit(self.project,stage)
        for media in self.project.media:
            self.request_waveform(media)
        self.timeline.select_ids(added,next((i.id for i in self.project.timeline if i.id in added),""))
        if captions and not added:self.timeline.select_captions(captions)
        self.timeline.selected_caption_ids=captions
        if self.page_group.checkedId()==0:self.inspector_toggle.setChecked(True)
        self.model_changed(); self.refresh_media(); self.seek(initial)
        self.statusBar().showMessage(f"Placed {len(assets)} media items consecutively in pool order",4000)

    @edit_only
    def add_media_to_track(self,media_id:str,track="",start=None):
        self.add_media_batch([media_id],track,start)

    @edit_only
    def add_title_object(self,name="Text",track="",start=None):
        from .effects import GRAPHICS
        if name in GRAPHICS:
            self.add_graphic_object(name,track,start)
            return
        track=track if track in self.project.video_tracks else self.timeline.selected_track if self.timeline.selected_track in self.project.video_tracks else self.project.video_tracks[-1]
        if self.project.track_states.get(track,{}).get("locked"):self.statusBar().showMessage("Unlock the destination track before adding a title.",4000); return
        start=self.project.playhead if start is None else max(0.,float(start)); style=copy.deepcopy(self.project.subtitle_style)
        style.name=name; style.animation="none" if name in {"Text","Lower Third"} else "pop"; style.position_x=.5; style.position_y=.5
        style.background_enabled=name in {"Hook Card","Lower Third"}; style.background_override=False
        style.background_color="#20242b"; style.background_opacity=88
        if name=="Caption Pop":style.position_y=.76; style.size=72
        elif name=="Lower Third":style.position_x=.08; style.position_y=.8; style.alignment="Left"; style.size=54; style.outline_width=0
        elif name=="Headline":
            from .headline import headline_style
            style=headline_style()
        text={"Text":"Basic Title","Hook Card":"Your hook goes here","Caption Pop":"Make this moment count","Lower Third":"Name · Context","Headline":"Your headline"}.get(name,name)
        item=TimelineItem(uid(),"",track,start,5.,group_id=uid(),role="title",title_text=text,title_style=style)
        self.project.timeline.append(item); self.timeline.select_ids({item.id},item.id); self.model_changed(); self.select_item(item.id); self.seek(start)

    @edit_only
    def add_graphic_object(self,name="Circle",track="",start=None,duration=None,properties=None):
        from .graphics import default_graphic_data, GRAPHICS_CATALOG
        track=track if track in self.project.video_tracks else self.timeline.selected_track if self.timeline.selected_track in self.project.video_tracks else self.project.video_tracks[-1]
        if self.project.track_states.get(track,{}).get("locked"):self.statusBar().showMessage("Unlock the destination track before adding a graphic.",4000); return None
        start=self.project.playhead if start is None else max(0.,float(start))
        cat=GRAPHICS_CATALOG.get(name,{})
        dur=float(duration) if duration is not None else float(cat.get("default_duration",2.0))
        graphic_data=default_graphic_data(name)
        if name.lower() in ('motion','motion composition'):
            from .motion import default_scene
            graphic_data['scene']=default_scene([self.project.settings.width,self.project.settings.height])
        if properties and isinstance(properties,dict):
            import copy
            graphic_data.update(copy.deepcopy(properties))
        item=TimelineItem(uid(),"",track,start,dur,group_id=uid(),role="graphic",graphic_type=name,graphic_data=graphic_data)
        if name.lower() in ('motion','motion composition'):item.transform.y=.5
        self.project.timeline.append(item); self.timeline.select_ids({item.id},item.id); self.model_changed(); self.select_item(item.id); self.seek(start)
        return item

    @edit_only
    def remove_media(self,media_id:str):
        media=self.project.media_by_id(media_id)
        if not media:return
        if any(i.media_id==media_id for i in self.project.timeline):return QMessageBox.information(self,"Media in use","Remove its timeline clips before removing it from the Media Pool.")
        self.project.media=[m for m in self.project.media if m.id!=media_id]; self.current_media_id="" if self.current_media_id==media_id else self.current_media_id; self.model_changed(); self.refresh_media()

    @edit_only
    def apply_vertical(self):
        selected=self.project.item_by_id(self.timeline.selected_id)
        if selected and selected.track not in self.project.video_tracks:selected=None
        media=self.project.media_by_id(selected.media_id if selected else self.current_media_id)
        if not media:
            main=next((i for i in self.project.timeline if i.role=="content"),None); media=self.project.media_by_id(main.media_id) if main else None
        if not media or media.kind not in {"video","image"}:QMessageBox.information(self,"Apply vertical","Select a video or image in Media first."); return
        while len(self.project.video_tracks)<3:self.project.add_track("video")
        if not self.project.audio_tracks:self.project.add_track("audio")
        existing=selected or next((i for i in self.project.timeline if i.media_id==media.id and i.role=="content" and i.start<=self.project.playhead<i.start+i.duration),None)
        if existing:
            if self.project.track_states.get(existing.track,{}).get("locked"):return
            linked=self.project.linked_items(existing)
            if not any(i.role=="background" for i in linked):
                tracks=self.project.video_tracks[:3]
                # Do not overwrite other edits when the preset needs three lanes.
                if any(i not in linked and i.track in tracks and i.start<existing.start+existing.duration and i.start+i.duration>existing.start for i in self.project.timeline):
                    tracks=[self.project.add_track("video") for _ in range(3)]
                stack=make_vertical_group(media,existing.start,existing.in_point,existing.duration,tracks,self.project.audio_tracks[0])
                if existing.link_id=="":existing.link_id=uid()
                existing.track=tracks[1]; existing.role="content"; existing.transform=stack[1].transform
                for layer in (stack[0],stack[2]):
                    layer.group_id=existing.group_id; layer.link_id=existing.link_id; layer.speed=existing.speed
                    self.project.timeline.append(layer)
            self.timeline.select_ids({i.id for i in self.project.linked_items(existing)},existing.id)
        else:self.project.timeline.extend(make_vertical_group(media,self.project.duration,self.project.mark_in,(self.project.mark_out-self.project.mark_in) if self.project.mark_out>self.project.mark_in else None,self.project.video_tracks[:3],self.project.audio_tracks[0]))
        self.model_changed(); self.statusBar().showMessage("Vertical stack built — draw the source regions, then drag layers in the viewer",5000)

    def active_main(self):
        t=self.project.playhead; videos=[i for i in self.project.timeline if i.track in self.project.video_tracks and i.role in {"content","normal"}]
        return next((i for i in videos if i.role=="content" and i.start<=t<i.start+i.duration),next((i for i in videos if i.start<=t<i.start+i.duration),next(iter(videos),None)))

    def seek(self,value:float):
        if self.timeline.drag_mode!="playhead":self.timeline.ensure_playhead_visible(value)
        if hasattr(self,"transport"):
            if self.timeline.drag_mode=="playhead" or getattr(self,"_restoring",False):self.transport.scrub(value)
            else:self.transport.seek(value)
            return
        self.project.playhead=max(0,value); self.time_label.setText(timecode(value,self.project.settings.fps)); self.timeline.viewport().update(); self.preview.update()

    def finish_scrub(self):
        if hasattr(self,"transport"):self.transport.finish_scrub()
        main=self.active_main()
        if main:
            media=self.project.media_by_id(main.media_id)
            if media and media.kind=="video":
                if not self.current_play_item or self.current_play_item.media_id!=main.media_id:
                    set_media_source(self.player,QUrl.fromLocalFile(self.proxies.get(media.id,media.path))); self.current_play_item=main
                desired=round((main.in_point+self.project.playhead-main.start)*1000)
                if abs(self.player.position()-desired)>80:self.loading=True; self.player.setPosition(desired); self.loading=False

    def player_position(self,milliseconds:int):
        if hasattr(self,"transport"):return
        if self.loading:return
        if self.current_play_item and self.player.playbackState()==QMediaPlayer.PlayingState:
            timeline_time=self.current_play_item.start+milliseconds/1000-self.current_play_item.in_point
            if timeline_time>self.current_play_item.start+self.current_play_item.duration:
                next_item=next((i for i in sorted((x for x in self.project.timeline if x.role=="content"),key=lambda x:x.start) if i.start>self.current_play_item.start),None)
                if next_item:self.current_play_item=next_item; self.seek(next_item.start); self.player.play()
                else:self.stop()
            else:self.project.playhead=max(0,timeline_time); self.time_label.setText(timecode(self.project.playhead,self.project.settings.fps)); self.timeline.viewport().update(); self.preview.update()

    @Slot()
    def source_video_frame(self):
        frame=self.video_sink.videoFrame()
        if frame.isValid():self.preview.set_frame(frame.toImage().copy())

    def toggle_play(self):
        if hasattr(self,"transport"):
            self.transport.pause() if self.transport.playing else self.transport.play(); return
        if self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause()
        else:
            if not self.active_main():return
            self.seek(self.project.playhead); self.player.play()

    def play_state(self,state):self.play_button.setIcon(lucide_icon("pause" if state==QMediaPlayer.PlayingState else "play","#d8dae0",18))
    def stop(self):
        if hasattr(self,"transport"):self.transport.pause(); self.transport.rate=1.
        self.player.pause(); self.player.setPlaybackRate(1.0)

    def transport_position(self,value):
        self.project.playhead=value; self.time_label.setText(timecode(value,self.project.settings.fps)); self.timeline.update_playhead(); self.preview.update()
        if self.transport.playing and self.timeline.drag_mode!="playhead":self.timeline.ensure_playhead_visible(value)
    def shuttle(self,direction:int):
        if hasattr(self,"transport"):
            if direction<0:self.transport.pause(); self.seek(max(0,self.project.playhead-.5))
            else:self.transport.rate=min(4,self.transport.rate*2) if self.transport.playing else 1.; self.transport.play()
            return
        if direction<0:self.seek(max(0,self.project.playhead-.5)); self.player.pause()
        else:self.player.setPlaybackRate(2.0 if self.player.playbackRate()<1.5 else min(4,self.player.playbackRate()*2)); self.toggle_play() if self.player.playbackState()!=QMediaPlayer.PlayingState else None
    @edit_only
    def mark_in(self):self.project.mark_in=self.project.playhead; self.statusBar().showMessage(f"In · {timecode(self.project.mark_in,self.project.settings.fps)}",2500)
    @edit_only
    def mark_out(self):self.project.mark_out=self.project.playhead; self.statusBar().showMessage(f"Out · {timecode(self.project.mark_out,self.project.settings.fps)}",2500)

    def select_item(self,item_id:str):
        item=self.project.item_by_id(item_id)
        if item_id:
            if item_id not in self.timeline.selected_ids:
                self.timeline.selected_caption=""; self.timeline.selected_caption_ids=set(); self.timeline.selected_ids={item_id}
            self.timeline.selected_transition_id=""
            self.timeline.selected_id=item_id; self.inspector.select(item_id); self.preview.select_item(item_id)
            if item:self.timeline.selected_track=item.track
        else:
            self.timeline.selected_id=""
            self.preview.select_item("")
            if not getattr(self.timeline, "selected_transition_id", "") and not getattr(self.timeline, "selected_caption", ""):
                self.inspector.select("")
        self.timeline.viewport().update()
        self.update_keyframe_button()

    def update_keyframe_button(self):
        if not hasattr(self,'keyframe_button'):return
        item=self.project.item_by_id(self.timeline.selected_id); media=self.project.media_by_id(item.media_id) if item else None
        self.keyframe_button.setEnabled(bool(item and (item.role in ('title','graphic') or media and media.kind in {'video','image'}) and item.track in self.project.video_tracks and not self.project.track_states.get(item.track,{}).get('locked') and self.current_page==0))

    @edit_only
    def open_keyframes(self,item_id=None):
        item=self.project.item_by_id(item_id or self.timeline.selected_id); media=self.project.media_by_id(item.media_id) if item else None
        if not item or not (item.role in ('title','graphic') or media and media.kind in {'video','image'}) or item.track not in self.project.video_tracks or self.project.track_states.get(item.track,{}).get('locked'):return
        from .keyframe_editor import KeyframeEditor
        self.transport.pause(); dialog=KeyframeEditor(self,item); dialog.setAttribute(Qt.WA_DeleteOnClose); dialog.show(); self._keyframe_dialog=dialog

    @edit_only
    def open_motion_composition(self,item_id=None):
        item=self.project.item_by_id(item_id or self.timeline.selected_id)
        if not item or item.role!='graphic' or item.graphic_type.lower() not in ('motion','motion composition') or self.project.track_states.get(item.track,{}).get('locked'):return
        from .motion_editor import MotionEditor
        self.transport.pause(); dialog=MotionEditor(self,item); dialog.setAttribute(Qt.WA_DeleteOnClose); dialog.show(); self._motion_dialog=dialog

    def select_caption(self,caption_id):
        if hasattr(self,'keyframe_button'):self.keyframe_button.setEnabled(False)
        self.timeline.selected_transition_id=""
        if not caption_id:
            self.timeline.selected_caption=""; self.timeline.selected_caption_ids=set(); self.timeline.selected_ids=set(); self.timeline.selected_id=""; self.preview.select_caption(""); self.inspector.select(""); return
        if caption_id not in self.timeline.selected_caption_ids:
            self.timeline.selected_caption_ids={caption_id}; self.timeline.selected_ids=set(); self.timeline.selected_id=""
        self.timeline.selected_caption=caption_id
        self.inspector_toggle.setChecked(True); self.inspector.select_caption(caption_id); self.preview.select_caption(caption_id)
        if hasattr(self,'caption_focus'):self.caption_focus.selected(caption_id)

    def select_transition(self,transition_id:str):
        if hasattr(self,'keyframe_button'):self.keyframe_button.setEnabled(False)
        self.timeline.selected_transition_id=transition_id
        if transition_id:
            self.timeline.selected_ids=set(); self.timeline.selected_id=""
            self.timeline.selected_caption=""; self.timeline.selected_caption_ids=set()
            self.preview.select_item(""); self.preview.select_caption("")
            self.inspector_toggle.setChecked(True)
            if hasattr(self.inspector, "select_transition"):
                self.inspector.select_transition(transition_id)
        else:
            self.inspector.select("")
        self.timeline.viewport().update()

    @edit_only
    def apply_transition(self,name:str,track:str="",left_item_id:str="",right_item_id:str="",cut_time:float=None,duration:float=0.80,alignment:str="center",properties:dict=None):
        import copy
        from .transitions import Transition, SUBSECTION_BY_TRANSITION, default_transition_properties
        category=SUBSECTION_BY_TRANSITION.get(name,"Dissolve")
        props=default_transition_properties(name)
        if properties and isinstance(properties,dict):
            props.update(copy.deepcopy(properties))
        dur=max(0.05,min(10.0,float(duration)))
        align=alignment if alignment in {"center","start","end"} else "center"

        # 1. Explicit clip IDs
        left_item=self.project.item_by_id(left_item_id) if left_item_id else None
        right_item=self.project.item_by_id(right_item_id) if right_item_id else None
        if left_item and right_item:
            target_track=track or left_item.track
            cut_t=left_item.start+left_item.duration
            start_t=cut_t-dur/2.0 if align=="center" else (cut_t if align=="start" else cut_t-dur)
            trans=Transition(uid(),name,category,target_track,start_t,dur,left_item.id,right_item.id,align,props)
            self.project.add_transition(trans)
            self.select_transition(trans.id)
            self.model_changed()
            return trans
        if left_item and not right_item:
            target_track=track or left_item.track
            cut_t=left_item.start+left_item.duration
            start_t=cut_t-dur/2.0 if align=="center" else (cut_t if align=="start" else cut_t-dur)
            trans=Transition(uid(),name,category,target_track,start_t,dur,left_item.id,"",align,props)
            self.project.add_transition(trans)
            self.select_transition(trans.id)
            self.model_changed()
            return trans
        if right_item and not left_item:
            target_track=track or right_item.track
            cut_t=right_item.start
            start_t=cut_t-dur/2.0 if align=="center" else (cut_t if align=="start" else cut_t-dur)
            trans=Transition(uid(),name,category,target_track,start_t,dur,"",right_item.id,align,props)
            self.project.add_transition(trans)
            self.select_transition(trans.id)
            self.model_changed()
            return trans

        # 2. Target track resolution
        target_track=track if track in self.project.video_tracks else (
            self.timeline.selected_track if hasattr(self.timeline,"selected_track") and self.timeline.selected_track in self.project.video_tracks else self.project.video_tracks[0]
        )
        track_items=sorted([i for i in self.project.timeline if i.track==target_track],key=lambda i:i.start)

        # 3. Explicit cut_time
        if cut_time is not None:
            t=float(cut_time)
            for idx in range(len(track_items)-1):
                l,r=track_items[idx],track_items[idx+1]
                cut_t=l.start+l.duration
                if abs(cut_t-r.start)<=0.15 and abs(t-cut_t)<=1.0:
                    clip_dur=min(dur,min(l.duration,r.duration)*2.0)
                    start_t=cut_t-clip_dur/2.0 if align=="center" else (cut_t if align=="start" else cut_t-clip_dur)
                    trans=Transition(uid(),name,category,target_track,start_t,clip_dur,l.id,r.id,align,props)
                    self.project.add_transition(trans)
                    self.select_transition(trans.id)
                    self.model_changed()
                    return trans
            hit=next((i for i in track_items if i.start<=t<=i.start+i.duration),None)
            if hit:
                clip_dur=min(dur,hit.duration)
                start_t=hit.start if align=="start" else (hit.start+hit.duration-clip_dur if align=="end" else t-clip_dur/2.0)
                trans=Transition(uid(),name,category,target_track,start_t,clip_dur,"",hit.id,align,props)
                self.project.add_transition(trans)
                self.select_transition(trans.id)
                self.model_changed()
                return trans

        # 4. Playhead or selected item in GUI
        t=self.project.playhead
        selected_item=self.project.item_by_id(self.timeline.selected_id)
        if selected_item and selected_item.track in self.project.video_tracks:
            target_track=selected_item.track
            track_items=sorted([i for i in self.project.timeline if i.track==target_track],key=lambda i:i.start)
            idx=next((n for n,it in enumerate(track_items) if it.id==selected_item.id),-1)
            if 0<=idx<len(track_items)-1 and abs((selected_item.start+selected_item.duration)-track_items[idx+1].start)<=0.12:
                cut_t=selected_item.start+selected_item.duration
                clip_dur=min(dur,max(0.05,min(selected_item.duration,track_items[idx+1].duration)*2.0))
                trans=Transition(uid(),name,category,target_track,cut_t-clip_dur/2.0,clip_dur,selected_item.id,track_items[idx+1].id,align,props)
                self.project.add_transition(trans)
                self.select_transition(trans.id)
                self.model_changed()
                return trans
            else:
                clip_dur=min(dur,max(0.05,selected_item.duration))
                trans=Transition(uid(),name,category,target_track,selected_item.start,clip_dur,"",selected_item.id,"start",props)
                self.project.add_transition(trans)
                self.select_transition(trans.id)
                self.model_changed()
                return trans
        for idx in range(len(track_items)-1):
            left,right=track_items[idx],track_items[idx+1]
            cut_t=left.start+left.duration
            if abs(cut_t-right.start)<=0.12 and abs(t-cut_t)<=1.0:
                clip_dur=min(dur,max(0.05,min(left.duration,right.duration)*2.0))
                trans=Transition(uid(),name,category,target_track,cut_t-clip_dur/2.0,clip_dur,left.id,right.id,align,props)
                self.project.add_transition(trans)
                self.select_transition(trans.id)
                self.model_changed()
                return trans
        if track_items:
            item=track_items[0]
            clip_dur=min(dur,max(0.05,item.duration))
            trans=Transition(uid(),name,category,target_track,item.start,clip_dur,"",item.id,"start",props)
            self.project.add_transition(trans)
            self.select_transition(trans.id)
            self.model_changed()
            return trans
        return None

    @edit_only
    def remove_transition(self,transition_id:str)->bool:
        if not transition_id:return False
        removed=self.project.remove_transition(transition_id)
        if removed:
            if getattr(self.timeline,"selected_transition_id","")==transition_id:
                self.select_transition("")
            self.model_changed()
        return removed

    def select_all(self):
        if not self.project:return
        all_ids={i.id for i in self.project.timeline}
        self.timeline.select_ids(all_ids,primary=self.timeline.selected_id or (next(iter(all_ids)) if all_ids else ""))

    def apply_effect_to(self,name,item_id):
        if item_id in self.timeline.selected_ids and len(self.timeline.selected_ids)>1:
            self.apply_effect(name)
        else:
            self.timeline.select_ids({item_id},item_id); self.apply_effect(name)

    @edit_only
    def apply_visual_fx(self, item_id: str, effect: str, properties: dict | None = None):
        item = self.project.item_by_id(str(item_id))
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        if item.track not in self.project.video_tracks:
            raise ValueError("Visual FX can only be applied to video track items")
        from .visual_fx import default_visual_fx, VISUAL_FX_SET
        if effect not in VISUAL_FX_SET:
            raise ValueError(f"Unknown Visual FX: {effect}")
        fx_dict = default_visual_fx(effect)
        if properties and isinstance(properties, dict):
            for k, v in properties.items():
                if k in fx_dict:
                    fx_dict[k] = type(fx_dict[k])(v) if not isinstance(fx_dict[k], bool) else bool(v)
                else:
                    fx_dict[k] = v
        self.commit_history()
        item.effects = [e for e in item.effects if e.get("name") != effect]
        item.effects.append(fx_dict)
        self.timeline.select_ids({item.id}, item.id)
        if hasattr(self, 'inspector') and self.inspector:
            self.inspector.select(item.id)
            if hasattr(self.inspector, 'tabs'):
                self.inspector.tabs.setCurrentIndex(2)
            if hasattr(self.inspector, 'effect_picker') and item.effects:
                self.inspector.effect_picker.setCurrentIndex(len(item.effects) - 1)
        self.model_changed()
        return fx_dict

    @edit_only
    def set_caption_style(self, preset: str | None = None, template: str | None = None, properties: dict | None = None, caption_ids: list[str] | None = None) -> dict:
        from .caption_presets import CAPTION_PRESETS
        from .caption_templates import CAPTION_TEMPLATES
        template_map = {t["id"]: t for t in CAPTION_TEMPLATES}
        merged = {}
        target = template or preset
        if target:
            if target in template_map:
                merged = copy.deepcopy(template_map[target])
            elif target in CAPTION_PRESETS:
                merged = copy.deepcopy(CAPTION_PRESETS[target])
            else:
                raise ValueError(f"Unknown template/preset: {target}. Available presets: {list(CAPTION_PRESETS.keys())}, templates: {list(template_map.keys())}")
        if properties and isinstance(properties, dict):
            merged.update(properties)
        if not merged:
            raise ValueError("Provide a template, preset or properties dictionary")
        self.commit_history()
        for k, v in merged.items():
            if hasattr(self.project.subtitle_style, k):
                cur = getattr(self.project.subtitle_style, k)
                if isinstance(cur, bool):
                    setattr(self.project.subtitle_style, k, bool(v))
                elif isinstance(cur, (int, float)):
                    setattr(self.project.subtitle_style, k, type(cur)(v))
                else:
                    setattr(self.project.subtitle_style, k, v)
        if caption_ids:
            for cap in self.project.captions:
                if cap.id in caption_ids:
                    cap.customize = True
                    for k, v in merged.items():
                        if hasattr(cap.style, k):
                            cur = getattr(cap.style, k)
                            if isinstance(cur, bool):
                                setattr(cap.style, k, bool(v))
                            elif isinstance(cur, (int, float)):
                                setattr(cap.style, k, type(cur)(v))
                            else:
                                setattr(cap.style, k, v)
        else:
            for cap in self.project.captions:
                for k, v in merged.items():
                    if hasattr(cap.style, k):
                        cur = getattr(cap.style, k)
                        if isinstance(cur, bool):
                            setattr(cap.style, k, bool(v))
                        elif isinstance(cur, (int, float)):
                            setattr(cap.style, k, type(cur)(v))
                        else:
                            setattr(cap.style, k, v)
        self.model_changed()
        if hasattr(self, 'caption_style_changed'):
            self.caption_style_changed()
        if hasattr(self, 'preview'):
            self.preview.update()
        return merged

    @edit_only
    def apply_vertical_framing(self, mode: str = "center_and_fill", foreground_track: str = "video_2", background_track: str = "video_1", scale: float | None = None) -> dict:
        self.commit_history()
        fg_count = 0
        bg_count = 0
        for item in self.project.timeline:
            if item.track == foreground_track:
                item.transform.y = 0.5
                item.transform.anchor_y = 0.0
                if scale is not None:
                    item.transform.scale = float(scale)
                    if item.transform.scale_linked:
                        item.transform.scale_y = float(scale)
                fg_count += 1
            elif item.track == background_track:
                item.role = "background"
                item.transform.x = 0.5
                item.transform.y = 0.5
                item.transform.scale = 1.0
                if item.transform.scale_linked:
                    item.transform.scale_y = 1.0
                bg_count += 1
        self.model_changed()
        if hasattr(self, 'preview'):
            self.preview.update()
        return {"foreground_count": fg_count, "background_count": bg_count, "mode": mode}

    def viewer_transform_changed(self,item_id:str):
        item=self.project.item_by_id(item_id)
        if item:
            if item.role=='title':
                for other in self.inspector.targets(False):other.title_style.position_x=item.title_style.position_x; other.title_style.position_y=item.title_style.position_y
            else:
                attributes={'move':('x','y'),'graphic_move':('x','y'),'rotate':('rotation',),'anchor':('anchor_x','anchor_y'),'scale':('scale','scale_y'),'scale_x':('scale',),'scale_y':('scale_y',)}.get(self.preview.drag_mode,())
                for other in self.inspector.targets(False):
                    for attr in attributes:setattr(other.transform,attr,getattr(item.transform,attr))
        self.inspector.select(item_id); self.project.touch(); self.timeline.viewport().update()

    def viewer_caption_changed(self,caption_id:str):
        caption=next((c for c in self.project.captions if c.id==caption_id),None)
        if caption and len(self.timeline.selected_caption_ids)>1:
            style=self.project.caption_style(caption)
            for other in self.inspector.caption_targets():
                if not other.customize:other.style=copy.deepcopy(self.project.caption_style(other)); other.customize=True
                other.style.position_x=style.position_x; other.style.position_y=style.position_y
        self.inspector.select_caption(caption_id); self.project.touch(); self.timeline.viewport().update()

    @edit_only
    def viewer_command(self,command:str,item_id):
        item=self.project.item_by_id(str(item_id))
        if not item:return
        if self.project.track_states.get(item.track,{}).get("locked"):return
        if command=="mark_webcam":
            item.is_webcam=not item.is_webcam; self.model_changed(); return
        if command in {"position_top","below_webcam"}:
            from PySide6.QtGui import QPolygonF
            visible=self.preview._visible_items(); entry=next(((i,r) for i,_,r in visible if i.id==item.id),None)
            if not entry:return
            bounds=QPolygonF(self.preview._transform_geometry(item,entry[1])[1]).boundingRect()
            frame=self.preview.composition_rect(); top=frame.top()
            if command=="below_webcam":
                camera=next(((i,r) for i,_,r in reversed(visible) if i.is_webcam and i.id!=item.id),None)
                if not camera:return QMessageBox.information(self,"Position below webcam","Mark a visible clip as webcam first.")
                top=QPolygonF(self.preview._transform_geometry(camera[0],camera[1])[1]).boundingRect().bottom()
            item.transform.x+=(frame.center().x()-bounds.center().x())/frame.width()
            item.transform.y+=(top-bounds.top())/frame.height()
            self.model_changed(); return
        if command=="crop":self.frame_source(item.id); return
        if command=="fit":
            media=self.project.media_by_id(item.media_id); crop=item.crop.clamped()
            if media:
                source_w=max(1,media.width*crop.width)
                input_scale=max(self.project.settings.width/max(1,media.width),self.project.settings.height/max(1,media.height))
                # Fill the output width, not a contain-inside-frame fit. Webcam
                # rendering applies the same .92 factor in preview and export.
                # Position/anchor alignment is a separate command and must survive.
                role_factor=.92 if item.role=="facecam" else 1.
                fitted=self.project.settings.width/(source_w*input_scale*role_factor)
                item.transform.scale=fitted; item.transform.scale_y=fitted
        elif command=="flip_h":item.transform.flip_horizontal=not item.transform.flip_horizontal
        elif command=="flip_v":item.transform.flip_vertical=not item.transform.flip_vertical
        elif command=="reset":item.transform=Transform(.5,.5,1)
        self.select_item(item.id); self.model_changed()

    def track_selected(self,track:str):
        item=next((i for i in self.project.timeline if i.track==track and i.start<=self.project.playhead<i.start+i.duration),None)
        if item:self.select_item(item.id)

    @edit_only
    def add_video_track(self,above_track=None):
        old_tracks=list(self.project.video_tracks)
        track=self.project.add_track("video")
        if above_track in self.project.video_tracks:
            self.project.video_tracks.remove(track)
            self.project.video_tracks.insert(self.project.video_tracks.index(above_track)+1,track)
            for index,existing in enumerate(old_tracks,1):
                if self.project.track_names.get(existing)==f'Video {index}':
                    self.project.track_names[existing]=f'Video {self.project.video_tracks.index(existing)+1}'
            self.project.track_names[track]=f'Video {self.project.video_tracks.index(track)+1}'
        self.timeline.selected_track=track; self.model_changed()
        self.statusBar().showMessage(f"Added V{self.project.video_tracks.index(track)+1}",2500); return track

    @edit_only
    def add_audio_track(self):
        track=self.project.add_track("audio"); self.timeline.selected_track=track; self.model_changed(); self.statusBar().showMessage(f"Added A{len(self.project.audio_tracks)}",2500); return track

    @edit_only
    def set_timeline_tool(self,tool:str):
        if tool not in {"select","blade"}:tool="select"
        self.timeline.set_tool(tool); buttons={"select":self.select_tool,"blade":self.blade_tool}; buttons[tool].setChecked(True); self.statusBar().showMessage({"select":"Selection Mode · A","blade":"Cut/Split · B"}[tool],1800)
    @edit_only
    def toggle_snapping(self):
        self.timeline.setProperty("snapping",not bool(self.timeline.property("snapping"))); self.statusBar().showMessage(f"Snapping {'on' if self.timeline.property('snapping') else 'off'} · N",1800)
        if hasattr(self,"snap_tool") and self.snap_tool.isChecked()!=bool(self.timeline.property("snapping")):self.snap_tool.setChecked(bool(self.timeline.property("snapping")))

    @edit_only
    def split_at(self,item_id:str,at:float):
        self.project.split_selection({item_id},at,self.timeline.linked_selection)
        self.model_changed()

    @edit_only
    def split_caption_at(self,caption_id:str,at:float):
        self.timeline.select_captions({caption_id},caption_id); self.timeline.split_caption(at)

    @edit_only
    def timeline_clipboard(self,command,from_timeline=False):
        from . import clipboard
        from PySide6.QtWidgets import QLineEdit,QPlainTextEdit,QTextEdit
        focus=QApplication.focusWidget()
        if not from_timeline and isinstance(focus,(QLineEdit,QPlainTextEdit,QTextEdit)):
            getattr(focus,command)(); return
        ids=self.timeline.expanded(self.timeline.selected_ids); captions=set(self.timeline.selected_caption_ids)
        try:
            if command=="paste":
                ids,captions=clipboard.paste(self.project,clipboard.get(),self.project.playhead)
                self.model_changed(); self.refresh_media()
                if ids:self.timeline.select_ids(ids)
                elif captions:self.timeline.select_captions(captions)
                self.timeline.selected_caption_ids=captions; self.timeline.viewport().setFocus()
                self.statusBar().showMessage(f"Pasted {len(ids)+len(captions)} clips at the playhead · Overwrite",4000)
                return
            payload=clipboard.capture(self.project,ids,captions)
            if not payload:self.statusBar().showMessage("Select timeline clips to "+command,3000); return
            payload["primary_id"]=self.timeline.selected_id or self.timeline.selected_caption
            if command=="cut":
                tracks={i.track for i in self.project.timeline if i.id in ids}|({"subtitle_1"} if captions else set())
                if any(self.project.track_states.get(track,{}).get("locked",False) for track in tracks):raise ValueError("Unlock the selected tracks before cutting.")
            clipboard.put(payload)
            if command=="cut":
                self.timeline.cancel_drag(); self.project.delete(ids,caption_ids=captions)
                self.timeline.select_ids(set()); self.model_changed()
            self.statusBar().showMessage(f"{'Cut' if command=='cut' else 'Copied'} {len(ids)+len(captions)} clips · Paste at the playhead with Ctrl+V",4000)
        except (ValueError,TypeError,KeyError) as error:self.statusBar().showMessage(str(error),5000)

    @edit_only
    def paste_attributes(self):
        from . import attributes,clipboard
        selected=self.timeline.selected_items()+[c for c in self.project.captions if c.id in self.timeline.selected_caption_ids]
        primary=self.project.item_by_id(self.timeline.selected_id) or next(iter(selected),None)
        if primary is None:return
        category=attributes.kind(self.project,primary); payload=clipboard.get(); source=attributes.source_for(payload,category)
        if source is None:self.statusBar().showMessage("Copy a "+category+" clip before pasting its attributes.",4500); return
        targets=[item for item in selected if attributes.kind(self.project,item)==category]
        if any(self.project.track_states.get(getattr(item,"track","subtitle_1"),{}).get("locked") for item in targets):self.statusBar().showMessage("Unlock selected tracks before pasting attributes.",4000); return
        media=self.project.media_by_id(source.get("media_id","")); name=source.get("title_text") or source.get("text") or (media.name if media else "Copied "+category+" clip")
        remembered=getattr(self,'_paste_attribute_choices',{})
        dialog=attributes.PasteAttributesDialog(name.replace("\n"," ")[:70],f"{len(targets)} selected {category} clip(s)",category,self,remembered.get(category,set()))
        if dialog.exec():
            count=attributes.apply(self.project,source,targets,category,dialog.selected()); self.model_changed(); self.statusBar().showMessage(f"Pasted attributes onto {count} clips",4000)
            if count:
                self._paste_attribute_choices=dict(remembered)
                self._paste_attribute_choices[category]=set(dialog.selected())
            if category=='video' and 'effects' in dialog.selected():
                from .vision_ui import reanalyse_pasted
                reanalyse_pasted(self,targets)

    @edit_only
    def timeline_command(self,command:str,payload):
        if command=='relink_media':
            item=self.project.item_by_id(payload); media=self.project.media_by_id(item.media_id) if item else None
            if media:
                self.media_panel.folder='project'; self.media_panel.missing_media.choose_file(media)
            return
        if command=='compound_retry':self.compounds.retry(); return
        if command=='compound_create':self.compounds.new(); return
        if command=='compound_open':self.compounds.open(payload); return
        if command=='keyframes':self.open_keyframes(payload); return
        if command=="paste_attributes":self.paste_attributes(); return
        if command in {"cut","copy","paste"}:self.timeline_clipboard(command,True); return
        if command in {"split","lift","ripple"}:
            self.select_item(str(payload)); self.split_selected() if command=="split" else self.delete_selected(command=="ripple"); return
        if command=="move_clip":
            item_id,destination=payload; item=self.project.item_by_id(item_id)
            if item:item.track=destination; self.model_changed(); self.select_item(item.id)
            return
        if command=="add_video":self.add_video_track(payload); return
        if command=="add_audio":
            track=self.project.add_track("audio"); self.timeline.selected_track=track; self.model_changed(); return
        track=str(payload or "")
        if command=="duplicate_track":self.timeline.selected_track=self.project.duplicate_track(track)
        elif command=="move_track_up":self.project.move_track(track,1 if track in self.project.video_tracks else -1)
        elif command=="move_track_down":self.project.move_track(track,-1 if track in self.project.video_tracks else 1)
        elif command=="rename_track":
            dialog=__import__("PySide6.QtWidgets",fromlist=["QInputDialog"]).QInputDialog; name,ok=dialog.getText(self,"Rename track","Track name",text=self.project.track_names.get(track,""))
            if not ok or not name.strip():return
            self.project.track_names[track]=name.strip()
        elif command=="delete_track":
            if (any(i.track==track for i in self.project.timeline) or track=='subtitle_1' and self.project.captions) and QMessageBox.question(self,"Delete track",f"Delete {self.project.track_names.get(track,track)} and every clip on it?")!=QMessageBox.Yes:return
            if not self.project.delete_track(track):return QMessageBox.information(self,"Delete track","A timeline must keep at least one track of each type.")
            if track=='subtitle_1':self.timeline.select_captions(set(),''); self.preview.select_caption('')
        elif command=="delete_empty_tracks":
            for candidate in list(reversed(self.project.video_tracks[1:])):
                if not any(i.track==candidate for i in self.project.timeline):self.project.delete_track(candidate)
            for candidate in list(reversed(self.project.audio_tracks[1:])):
                if not any(i.track==candidate for i in self.project.timeline):self.project.delete_track(candidate)
        self.model_changed()

    @edit_only
    def apply_effect(self,name:str):
        from .effects import TITLES, GRAPHICS, ADJUSTABLE, compatible, preset_owner
        if name in TITLES:self.add_title_object(name); return
        if name in GRAPHICS:self.add_graphic_object(name); return
        if name=='Object Tracking':
            item=self.project.item_by_id(self.timeline.selected_id)
            if not compatible(name,item,self.project):
                self.statusBar().showMessage('Select an unlocked video or image clip to track.',5000); return
            from .tracking_ui import begin
            begin(self); return
        from .vision_effects import NAMES as VISION_NAMES
        if name in VISION_NAMES:
            item=self.project.item_by_id(self.timeline.selected_id)
            if not compatible(name,item,self.project):
                self.statusBar().showMessage("Select an unlocked, compatible video clip to apply "+name,4000); return
            from .vision_ui import begin
            begin(self,name); return
        if name in {"Cut curse words","Remove Silence"}:
            item=self.project.item_by_id(self.timeline.selected_id)
            if not compatible(name,item,self.project):
                self.statusBar().showMessage("Select an unlocked, compatible clip to apply "+name,4000); return
            from .audio_actions import run_action
            run_action(self,cut_words=name=="Cut curse words"); return
        if name=="Vocal Only":
            item=self.project.item_by_id(self.timeline.selected_id)
            if not compatible(name,item,self.project):
                self.statusBar().showMessage("Select an unlocked audio clip to apply Vocal Only",4000); return
            from .vocal_ui import begin
            begin(self); return
        if name=="Soft Background":
            self.project.settings.blur=36; self.project.settings.background_brightness=.52; self.project.settings.background_contrast=1.08; self.inspector.sync_scene()
            self.statusBar().showMessage(f"Applied {name}",2500); return
        selected_candidates=[self.project.item_by_id(i) for i in self.timeline.selected_ids] if self.timeline.selected_ids else ([self.project.item_by_id(self.timeline.selected_id)] if self.timeline.selected_id else [])
        targets=[it for it in selected_candidates if it and compatible(name,it,self.project)]
        if not targets:
            self.statusBar().showMessage("Select an unlocked, compatible video or audio clip to apply "+name,4000); return
        for item in targets:
            from .visual_fx import VISUAL_FX_SET, default_visual_fx
            from .voice_effects import NAMES as VOICE_NAMES, default_effect as default_voice_effect
            if name in VISUAL_FX_SET:
                item.effects.append(default_visual_fx(name))
            elif name in VOICE_NAMES:
                item.effects.append(default_voice_effect(name))
            elif name in {"Chroma Key","Green Screen"}:
                item.effects.append(dict(name=name,enabled=True,color="#00ff00",similarity=15.,softness=8.))
            elif name in ADJUSTABLE:
                item.effects.append(dict(name=name,enabled=True,amount=100. if name not in {"Voice Clarity","Low Cut"} else 50.))
            elif name=="Gaussian Blur":
                item.effects.append(dict(name="Gaussian Blur",enabled=True,horizontal=12.,vertical=12.,linked=True,border="Reflect",blend=100.))
            elif name=="Circle Facecam":
                before={"shape":item.transform.shape}; item.transform.shape="circle"; item.effects.append(dict(name=name,enabled=True,before=before))
            elif name in {"Black & White","Light Boost","Cinematic Contrast"}:
                before={key:getattr(item,key) for key in ("grayscale","brightness","contrast","saturation","sharpen")}
                values={"Black & White":(True,0,1.08,0,.2),"Light Boost":(False,.08,1.08,1.06,.2),"Cinematic Contrast":(False,-.03,1.16,.84,.18)}[name]
                item.grayscale,item.brightness,item.contrast,item.saturation,item.sharpen=values; item.effects.append(dict(name=name,enabled=True,before=before))
            elif name=="Noise Clean":
                item.effects.append(dict(name=name,enabled=True))
            elif name=="Auto Duck":
                self.duck.setChecked(True); item.effects.append(dict(name=name,enabled=True))
            elif name=="Fade In / Out":
                before={"fade_in":item.fade_in,"fade_out":item.fade_out}
                item.fade_in=.25; item.fade_out=.25; item.effects.append(dict(name=name,enabled=True,before=before))
            if item.effects:
                effect=item.effects[-1]
                if effect.get("before"):effect["after"]={key:getattr(preset_owner(item,name),key) for key in effect["before"]}
        self.model_changed()
        primary=self.project.item_by_id(self.timeline.selected_id)
        active=primary if primary and primary in targets else targets[0]
        self.inspector.select(active.id)
        if active.effects:self.inspector.effect_picker.setCurrentIndex(len(active.effects)-1); self.inspector.tabs.setCurrentIndex(2)
        count=len(targets)
        self.statusBar().showMessage(f"Applied {name}" if count<=1 else f"Applied {name} to {count} clips",2500)

    @edit_only
    def frame_source(self,item_id=""):
        if not isinstance(item_id,str):item_id=""
        item=self.project.item_by_id(item_id or self.timeline.selected_id) or self.active_main()
        if not item or item.track not in self.project.video_tracks:QMessageBox.information(self,"Frame source","Select a video clip first."); return
        media=self.project.media_by_id(item.media_id)
        if not media:return
        image=QImage(media.path) if media.kind=="image" else self.preview.frames.get(self.preview.active_frames.get(item.id),QImage())
        exact=not image.isNull()
        if image.isNull() and media.thumbnail:image=QImage(media.thumbnail)
        if image.isNull():
            image=QImage(max(16,media.width or 1280),max(16,media.height or 720),QImage.Format_RGB32); image.fill(QColor("black"))
        dialog=CropDialog(image,item.crop,self.project.track_names.get(item.track,"video layer"),self)
        self._crop_dialogs=getattr(self,"_crop_dialogs",set()); self._crop_dialogs.add(dialog)
        def commit():
            target=self.project.item_by_id(item.id)
            if target:target.crop=copy.deepcopy(dialog.crop); self.model_changed()
        dialog.accepted.connect(commit)
        dialog.finished.connect(lambda _:(self._crop_dialogs.discard(dialog),dialog.deleteLater()))
        dialog.open()
        # Decoding no longer blocks the GUI.  The dialog opens from the live or
        # cached frame immediately, then swaps in an exact source frame when it
        # arrives.
        if media.kind=="video" and not exact:
            at=item.source_time(max(item.start,min(item.start+item.duration,self.project.playhead)))
            worker=Worker(extract_frame,media.path,at,self.settings.get("ffmpeg","ffmpeg"))
            worker.signals.result.connect(lambda decoded,d=dialog:d.set_image(decoded) if d in getattr(self,"_crop_dialogs",set()) else None)
            QTimer.singleShot(0,lambda w=worker:self.start_worker(w))

    @edit_only
    def split_selected(self):
        if self.timeline.selected_caption:self.timeline.split_caption(); return
        item=self.project.item_by_id(self.timeline.selected_id)
        if not item:return
        ids=self.timeline.selected_ids or {item.id}
        self.project.split_selection(ids,self.project.playhead,self.timeline.linked_selection)
        self.model_changed()

    @edit_only
    def delete_selected(self,ripple=False):
        timeline=self.timeline
        if getattr(timeline, "selected_transition_id", ""):
            tid=timeline.selected_transition_id
            timeline.selected_transition_id=""
            self.project.remove_transition(tid)
            self.select_transition("")
            self.model_changed()
            return
        ids=timeline.expanded(timeline.selected_ids or ({timeline.selected_id} if timeline.selected_id else set()))
        captions=timeline.selected_caption_ids or ({timeline.selected_caption} if timeline.selected_caption else set())
        if not ids and not captions:return
        timeline.cancel_drag(); self.project.delete(ids,ripple,caption_ids=captions)
        timeline.select_ids(set()); self.preview.select_caption(""); self.model_changed()

    def slip(self,amount):
        item=self.project.item_by_id(self.timeline.selected_id)
        if not item:return
        for candidate in self.project.linked_items(item):candidate.in_point=max(0,candidate.in_point+amount)
        self.model_changed(); self.inspector.select(item.id)

    @edit_only
    def remove_silence(self):
        from .audio_actions import run_action
        run_action(self)

    @edit_only
    def delete_gaps(self):
        from .timeline_actions import delete_gaps
        try:removed,gaps=delete_gaps(self.project)
        except ValueError as error:QMessageBox.information(self,"Delete gaps",str(error)); return
        if gaps:
            self.timeline.select_ids(set()); self.model_changed(); self.seek(self.project.playhead)
        self.statusBar().showMessage(f"Closed {len(gaps)} gap(s), removing {removed:.2f}s. Later clips retain their relative timing.",6000)

    @edit_only
    def generate_captions(self, headless: bool = False, words_per_card: int | None = None, style_override: dict | None = None):
        if self.project.track_states.get("subtitle_1",{}).get("locked"):
            self.statusBar().showMessage("Unlock the subtitle track before generating captions.",4000)
            return None
        main=self.active_main()
        if not main:
            if not headless and not QApplication.activeModalWidget():
                QMessageBox.information(self,"Generate captions","Add a video clip to the timeline first.")
            return None

        if not headless:
            from .caption_style_dialog import CaptionStyleDialog
            dialog=CaptionStyleDialog(self.project.subtitle_style,self.settings,self)
            if not dialog.exec():
                return None
            style=dialog.selected_style()
            caption_word_count=dialog.words.value()
            censor_captions=dialog.censor.isChecked()
            strip_periods=dialog.remove_periods.isChecked()
            self.settings["caption_remove_periods"]=strip_periods
            self.settings["caption_words_per_card"]=caption_word_count
            self.settings["caption_censor"]=censor_captions
            save_settings(self.settings)
            self.project.subtitle_style=style
            self.model_changed()
        else:
            style=copy.deepcopy(self.project.subtitle_style)
            if style_override and isinstance(style_override, dict):
                for k, v in style_override.items():
                    if hasattr(style, k):
                        setattr(style, k, v)
                self.project.subtitle_style = style
                self.model_changed()
            caption_word_count = words_per_card or self.settings.get("caption_words_per_card", 1)
            censor_captions = bool(self.settings.get("caption_censor", False))
            strip_periods = bool(self.settings.get("caption_remove_periods", True))

        destination_project=self.project
        snapshot=copy.deepcopy(self.project)
        selected=self.timeline.selected_ids
        targets=[i for i in snapshot.timeline if i.track in snapshot.audio_tracks and i.role in {"source_audio","dialogue"} and not i.muted]
        if selected:
            related=set(selected)
            for item in snapshot.timeline:
                if item.id in selected:
                    related.update(i.id for i in snapshot.linked_items(item))
            chosen=[i for i in targets if i.id in related]
            if chosen:
                targets=chosen
        if not targets:
            targets=[copy.deepcopy(main)]
        offset=min(i.start for i in targets)
        duration=max(i.start+i.duration for i in targets)-offset
        settings=copy.deepcopy(self.settings)
        self.statusBar().showMessage("Preparing timeline speech for local captions…")

        cancel=threading.Event()
        settled=[False]
        self._caption_cancel=cancel
        progress_dialog=None
        if not headless and not QApplication.activeModalWidget():
            progress_dialog=QProgressDialog("Preparing timeline audio…","Cancel",0,100,self)
            progress_dialog.setWindowTitle("Generating Auto Captions")
            progress_dialog.canceled.connect(lambda:None if settled[0] else cancel.set())
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setValue(5)
            progress_dialog.show()

        def work():
            import tempfile
            from .process import run_cancellable
            with tempfile.TemporaryDirectory(prefix="kinetic-caption-timeline-") as directory:
                wav=str(Path(directory)/"speech.wav")
                args=[settings.get("ffmpeg","ffmpeg"),"-hide_banner","-loglevel","error","-y"]
                filters=[]
                labels=[]
                for item in targets:
                    media=snapshot.media_by_id(item.media_id)
                    if not media or not media.has_audio:
                        continue
                    from .rendergraph import audio_filters
                    index=len(labels)
                    args += ["-ss",str(item.in_point),"-t",str(item.source_duration),"-i",media.path]
                    filters.append(f"[{index}:a]{audio_filters(item)},adelay={round((item.start-offset)*1000)}:all=1[a{index}]")
                    labels.append(f"[a{index}]")
                if not labels:
                    raise CaptionBackendError("The selected range contains no speech audio.")
                filters.append("".join(labels)+f"amix=inputs={len(labels)}:duration=longest:normalize=0[out]")
                args += ["-filter_complex",";".join(filters),"-map","[out]","-ac","1","-ar","16000","-t",str(duration),wav]
                run_cancellable(args,check=True,capture_output=True,cancel_check=cancel.is_set)
                worker.signals.progress.emit((20,"Audio prepared · loading speech model…"))
                return transcribe(wav,settings,offset,lambda value:worker.signals.progress.emit(value if isinstance(value,tuple) else (45,value)),caption_word_count,.5,cancel_check=cancel.is_set)
        worker=Worker(work)
        worker.cancel_callback=cancel.set
        def caption_progress(value):
            if cancel.is_set() or getattr(self,'_closing',False):return
            percent,text=value if isinstance(value,tuple) else (45,str(value))
            if progress_dialog:
                progress_dialog.setValue(percent)
                progress_dialog.setLabelText(text)
            self.statusBar().showMessage(text)
        worker.signals.progress.connect(caption_progress)
        def ready(result):
            if cancel.is_set() or getattr(self,'_closing',False):return
            settled[0]=True
            if progress_dialog:
                progress_dialog.setValue(100)
                progress_dialog.close()
            if (self.project is not destination_project or self._history_key(self.project)!=self._history_key(snapshot)
                    or self.project.track_states.get('subtitle_1',{}).get('locked')):
                self.statusBar().showMessage("Caption result discarded because the project changed",5000)
                return
            captions,backend=result
            from .caption_words import prepare_generated
            prepare_generated(captions,style,strip_periods,censor_captions)
            for caption in captions:
                caption.style=copy.deepcopy(style)
            self.project.captions.extend(captions)
            self.project.overwrite_captions({c.id for c in captions})
            self.caption_panel.refresh()
            self.model_changed()
            if captions:
                self.select_caption(captions[0].id)
                self.seek(captions[0].start)
            self.statusBar().showMessage(f"Generated {len(captions)} captions locally with {backend}",5000)
            if not headless and style.animation in ('fade every word','word highlight','word reveal') and any(not c.word_timings for c in captions):
                QMessageBox.information(self,'Estimated word timing','This speech engine did not provide individual word timestamps. Word animation timing is estimated. Generate with local Whisper for speech-aligned word timings.')
        worker.signals.result.connect(ready)
        def failed(detail):
            if cancel.is_set() or getattr(self,'_closing',False):return
            settled[0]=True
            if not headless and not QApplication.activeModalWidget():QMessageBox.warning(self,'Caption engine',detail[-1800:])
            else:logging.error('Caption engine error: %s',detail)
        def finished():
            settled[0]=True
            if progress_dialog:progress_dialog.close(); progress_dialog.deleteLater()
            if getattr(self,'_caption_cancel',None) is cancel:self._caption_cancel=None
            if cancel.is_set() and not getattr(self,'_closing',False):self.statusBar().showMessage('Caption generation cancelled',4000)
        worker.signals.error.connect(failed)
        worker.signals.finished.connect(finished)
        self.start_worker(worker)
        return worker

    def highlight_reel(self):
        videos=[m for m in self.project.media if m.kind=="video"]
        if not videos:return QMessageBox.information(self,"Highlight reel","Import two or more clips first.")
        self.project.timeline=[]; cursor=0
        for media in videos:
            duration=min(media.duration,30); self.project.timeline.extend(make_vertical_group(media,cursor,0,duration,self.project.video_tracks[:3],self.project.audio_tracks[0])); cursor+=duration
        self.model_changed(); self.seek(0); self.statusBar().showMessage(f"Arranged {len(videos)} highlights with vertical layouts",5000)

    @edit_only
    def instant_package(self):
        self.apply_vertical()
        main=self.project.item_by_id(self.timeline.selected_id) or self.active_main()
        audio=next((i for i in self.project.linked_items(main) if i.track in self.project.audio_tracks),None) if main else None
        if not audio:return QMessageBox.information(self,"Instant package","Select a clip with linked video and audio first.")
        self.timeline.select_ids({i.id for i in self.project.linked_items(audio)},audio.id)
        from .audio_actions import run_action
        # Captions must use the packed timeline, not race the silence worker.
        run_action(self,on_complete=self.generate_captions)

    def audio_settings(self):
        self.project.settings.normalize_audio=self.normalize.isChecked(); self.project.settings.noise_reduction=self.noise.isChecked(); self.project.settings.auto_duck=self.duck.isChecked(); self.model_changed()

    def save_template(self):
        main=self.active_main()
        if not main:return
        name,ok=__import__("PySide6.QtWidgets",fromlist=["QInputDialog"]).QInputDialog.getText(self,"Save layout template","Template name")
        if ok and name:
            group=[i for i in self.project.timeline if i.group_id==main.group_id]; templates=load_templates(); templates.append({"name":name,"settings":asdict(self.project.settings),"layers":[{"role":i.role,"crop":asdict(i.crop),"transform":asdict(i.transform)} for i in group if i.track in self.project.video_tracks],"caption_style":asdict(self.project.captions[0].style) if self.project.captions else asdict(CaptionStyle())}); save_templates(templates); self.statusBar().showMessage(f"Saved template · {name}",4000)

    @edit_only
    def apply_template(self):
        templates=load_templates(); main=self.active_main()
        if not templates:return QMessageBox.information(self,"Layout templates","No saved templates yet. Frame a clip, then choose Save layout template.")
        if not main:return QMessageBox.information(self,"Layout templates","Add a clip to the timeline first.")
        dialog_type=__import__("PySide6.QtWidgets",fromlist=["QInputDialog"]).QInputDialog
        name,ok=dialog_type.getItem(self,"Apply layout template","Template",[x["name"] for x in templates],0,False)
        if not ok:return
        template=next(x for x in templates if x["name"]==name); group=[i for i in self.project.timeline if i.group_id==main.group_id]
        for saved in template.get("layers",[]):
            item=next((i for i in group if i.role==saved.get("role")),None)
            if item:item.crop=Crop(**saved.get("crop",{})); item.transform=Transform(**saved.get("transform",{}))
        style=CaptionStyle(**template.get("caption_style",{}))
        self.project.subtitle_style=copy.deepcopy(style)
        for caption in self.project.captions:
            if not caption.is_hook:caption.style=CaptionStyle(**asdict(style))
        for key,value in template.get("settings",{}).items():
            if hasattr(self.project.settings,key):setattr(self.project.settings,key,value)
        self.model_changed(); self.statusBar().showMessage(f"Applied template · {name}",4000)

    @edit_only
    def open_project_settings(self):
        from .project_settings import ProjectSettingsDialog
        dialog=ProjectSettingsDialog(self.project,self)
        if dialog.exec():self.apply_project_settings(*dialog.values())

    @edit_only
    def apply_project_settings(self,name,settings):
        if not 64<=settings.width<=8192 or not 64<=settings.height<=8192 or settings.width%2 or settings.height%2 or not 1<=settings.fps<=240:
            raise ValueError("Use even canvas dimensions from 64–8192 pixels and a valid frame rate.")
        self.transport.pause(); self.project.name=name; self.project.settings=copy.deepcopy(settings)
        self.refresh_project_settings(); self.project_label.setText(name)
        self.model_changed(); self.statusBar().showMessage(f"Project settings · {settings.width} × {settings.height} · {settings.fps} fps",5000)

    def refresh_project_settings(self):
        settings=self.project.settings
        for control,value in [(self.normalize,settings.normalize_audio),(self.noise,settings.noise_reduction),(self.duck,settings.auto_duck)]:
            control.blockSignals(True); control.setChecked(value); control.blockSignals(False)
        if hasattr(self,"transport"):self.transport.timer.setInterval(max(4,round(1000/settings.fps)))
        self.preview.effect_cache.clear(); self.delivery.sync_project_settings()

    def open_settings(self):
        dialog=QDialog(self); dialog.setWindowTitle("Kinetic Cut settings"); dialog.resize(610,740); form=QFormLayout(dialog); ffmpeg=QLineEdit(self.settings.get("ffmpeg","ffmpeg")); ffprobe=QLineEdit(self.settings.get("ffprobe","ffprobe")); whisper_size=QComboBox(); whisper_size.addItems(["tiny.en","base.en","small.en"]); whisper_size.setCurrentText(self.settings.get("whisper_model","base.en")); whisper=QLineEdit(self.settings.get("whisper_cli","")); model=QLineEdit(self.settings.get("whisper_model_path","")); sfx=QLineEdit(self.settings.get("sfx_folder","")); phone=QLineEdit(self.settings.get("phone_folder","/sdcard/Movies/KineticCut")); buttons=QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Save); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow("FFmpeg command",ffmpeg); form.addRow("ffprobe command",ffprobe); form.addRow("Whisper model",whisper_size); form.addRow("whisper-cli override",whisper); form.addRow("whisper.cpp model",model); form.addRow("Auto-index SFX folder",sfx); form.addRow("Android folder",phone)
        from .playback_config import MODES
        decoder=QComboBox(); decoder.addItems(MODES); decoder.setCurrentText(self.settings.get('playback_decoder',MODES[0])); form.addRow('Playback decoder',decoder)
        note=QLabel('Restart after changing decoder. GPU decoding depends on codec/driver support.\nPreview effects/composition use CPU; export encoder is selected in Deliver.'); note.setWordWrap(True); form.addRow(note)
        shortcut_box=QGroupBox("KEYBOARD SHORTCUTS"); shortcut_grid=QGridLayout(shortcut_box); shortcut_edits={}; labels={"import":"Import media","save":"Save project","export":"Export","undo":"Undo","redo":"Redo","selection_mode":"Selection mode","blade_mode":"Cut/Split","snapping":"Toggle snapping","play_pause":"Play / pause","shuttle_back":"Shuttle back","shuttle_stop":"Stop","shuttle_forward":"Shuttle forward","mark_in":"Mark in","mark_out":"Mark out","cut":"Split clip","delete":"Lift","ripple_delete":"Ripple delete","vertical_layout":"Vertical layout","captions":"Generate captions","remove_silence":"Remove silence","instant_package":"Instant package"}
        for index,(logical,label) in enumerate(labels.items()):
            edit=QLineEdit(self.settings.get("shortcuts",{}).get(logical,"")); edit.setPlaceholderText("e.g. Ctrl+Shift+K"); shortcut_edits[logical]=edit; shortcut_grid.addWidget(QLabel(label),index//2,index%2*2); shortcut_grid.addWidget(edit,index//2,index%2*2+1)
        form.addRow(shortcut_box); form.addRow(buttons)
        if dialog.exec():
            self.settings['playback_decoder']=decoder.currentText()
            self.settings.update(ffmpeg=ffmpeg.text(),ffprobe=ffprobe.text(),whisper_model=whisper_size.currentText(),whisper_cli=whisper.text(),whisper_model_path=model.text(),sfx_folder=sfx.text(),phone_folder=phone.text()); self.settings["shortcuts"].update({key:edit.text().strip() for key,edit in shortcut_edits.items()}); save_settings(self.settings); self.apply_shortcuts()
            folder=Path(sfx.text())
            if folder.is_dir():self.add_media_paths([str(x) for x in folder.iterdir() if x.suffix.lower() in AUDIO_EXTENSIONS])

    def open_export(self):
        from .workspace import set_page
        set_page(self,1)

    def refresh_inspector(self):
        if getattr(self.timeline, "selected_transition_id", ""):
            if hasattr(self.inspector, "select_transition"):
                self.inspector.select_transition(self.timeline.selected_transition_id)
        elif getattr(self.timeline, "selected_caption", ""):
            self.inspector.select_caption(self.timeline.selected_caption)
        else:
            self.inspector.select(self.timeline.selected_id or self.inspector.item_id)

    def model_changed(self):
        self.project.touch(); self.preview.update()
        if getattr(self,'_property_scrubbing',False):self.timeline._range(); self.timeline.viewport().update(); return
        self.project.ensure_track_model(); self.timeline.set_project(self.project)
        if self.caption_panel.isVisible():self.caption_panel.refresh()
        self.refresh_inspector(); self.time_label.setText(timecode(self.project.playhead,self.project.settings.fps)); self.commit_history()
        if hasattr(self,"transport"):self.transport.sync()
        if hasattr(self,"preview_quality"):self.preview_quality.request()
        self.update_keyframe_button()
        self.compounds.synchronize(); self.compounds.request_caches()

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()

    def dropEvent(self,event):self.add_media_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]); event.acceptProposedAction()

    def closeEvent(self,event:QCloseEvent):
        from .close_guard import confirm_close
        if getattr(self,'_closing',False):
            from .dialog_jobs import active_dialog_threads
            if self._workers or active_dialog_threads():event.ignore(); return
            self._shutdown_wait_timer.stop()
            try:SESSION_LOCK_PATH.unlink(missing_ok=True)
            except OSError:logging.exception('Could not remove active session marker')
            self.shutdownFinished.emit()
            event.accept(); return
        if not confirm_close(self):
            event.ignore(); return
        if hasattr(self,'phone_connect'):
            if self.phone_connect.active_job and QMessageBox.question(self,'Cancel phone transfers?','A phone transfer is running. Cancel it and close Kinetic Cut?')!=QMessageBox.Yes:
                event.ignore(); return
        self._closing=True
        self.setEnabled(False)
        self.autosave_timer.stop(); self.autosave_debounce_timer.stop()
        for name in ('_history_settle_timer','_text_history_timer'):
            timer=getattr(self,name,None)
            if timer:timer.stop()
        if hasattr(self,'phone_connect'):self.phone_connect.shutdown()
        if hasattr(self.inspector,'cancel_title_tts'):self.inspector.cancel_title_tts()
        self.compounds.cancel()
        self.media_panel.watch_folders.stop()
        self.preview_quality.cancel()
        if hasattr(self,'assistant_connection'):self.assistant_connection.stop()
        self.delivery.clock.stop()
        if getattr(self,'_vision_cancel',None):self._vision_cancel.set()
        if getattr(self,'_tracking_cancel',None):self._tracking_cancel.set()
        if getattr(self.delivery,'render_cancel',None):self.delivery.render_cancel.set()
        if getattr(self,"_vocal_cancel",None):self._vocal_cancel.set()
        if getattr(self,'_caption_cancel',None):self._caption_cancel.set()
        from .dialog_jobs import cancel_dialog_threads, active_dialog_threads
        cancel_dialog_threads()
        from .component_ui import cancel_component_downloads
        cancel_component_downloads()
        for worker in tuple(self._workers):
            worker.cancel()
            # The window remains alive until finished. Discard late feature
            # mutations/progress, while retaining terminal cleanup/ownership.
            for signal,signature in ((worker.signals.result,'2result(PyObject)'),(worker.signals.error,'2error(QString)'),(worker.signals.progress,'2progress(PyObject)')):
                try:
                    if worker.signals.receivers(signature):signal.disconnect()
                except RuntimeError:pass
        if hasattr(self, 'update_controller') and hasattr(self.update_controller, '_cancel'):
            self.update_controller._cancel.set()
        if hasattr(self,"transport"):self.transport.shutdown()
        self.autosave(); self.player.stop()
        self._shutdown_wait_timer=QTimer(self)
        self._shutdown_wait_timer.setInterval(50)
        self._shutdown_wait_timer.timeout.connect(self.close)
        if self._workers or active_dialog_threads():
            self.statusBar().showMessage('Closing · waiting for background tasks to finish…')
            self._shutdown_wait_timer.start(); event.ignore()
        else:
            try:SESSION_LOCK_PATH.unlink(missing_ok=True)
            except OSError:logging.exception('Could not remove active session marker')
            self.shutdownFinished.emit(); event.accept()


def run():
    from .startup import run as desktop_run
    sys.exit(desktop_run())
