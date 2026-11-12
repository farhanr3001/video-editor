"""Independent clip monitor and transactional grading workspace."""
import math
from pathlib import Path

from PySide6.QtCore import QDeadlineTimer, QEvent, QPointF, QRectF, QSize, QSignalBlocker, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import (QColor, QConicalGradient, QKeySequence,
                           QPainter, QPen, QRadialGradient, QShortcut, QVector2D, QVector4D)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy, QSlider,
                               QStyle, QStyleOptionSlider, QTabWidget, QVBoxLayout, QWidget)

from .colour_grade import PRESETS, PRESETS_KEY, PRESET_LIMIT, TONE, WHEELS, clean, publish, saved_presets
from .icons import lucide_icon
from .quick_surface import Surface


class ColourWheel(QWidget):
    changed = Signal(float, float)
    started = Signal()
    released = Signal()

    def __init__(self, label, hint, parent=None):
        super().__init__(parent)
        self.setAccessibleName(label + " colour wheel")
        self.setToolTip(hint + ". Drag to tint. Arrow keys adjust the tint.")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(80, 80)
        self.point = QPointF()
        self.dragging = False

    def disk(self):
        return QRectF(self.rect()).adjusted(8, 8, -8, -8)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        disk = self.disk()
        centre = disk.center()
        radius = disk.width()/2
        hue = QConicalGradient(centre, 0)
        for turn in range(7):
            hue.setColorAt(turn/6, QColor.fromHsvF((turn % 6)/6, .8, .92))
        painter.setPen(Qt.NoPen)
        painter.setBrush(hue)
        painter.drawEllipse(disk)
        neutral = QRadialGradient(centre, radius)
        neutral.setColorAt(0, QColor("#aaaeb6"))
        neutral.setColorAt(1, QColor(170, 174, 182, 0))
        painter.setBrush(neutral)
        painter.drawEllipse(disk)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(self.palette().highlight().color() if self.hasFocus() else QColor("#282a31"), 2))
        painter.drawEllipse(disk)
        painter.setPen(QPen(QColor(255, 255, 255, 105), 1))
        painter.drawLine(centre+QPointF(-4, 0), centre+QPointF(4, 0))
        painter.drawLine(centre+QPointF(0, -4), centre+QPointF(0, 4))
        marker = centre + QPointF(self.point.x(), -self.point.y())*radius
        painter.setPen(QPen(QColor("#18191c"), 4))
        painter.drawEllipse(marker, 5, 5)
        painter.setPen(QPen(QColor("white"), 2))
        painter.drawEllipse(marker, 5, 5)

    def pick(self, point):
        self.changed.emit(point.x(), point.y())

    def pick_mouse(self, position):
        disk = self.disk()
        point = (position-disk.center())/(disk.width()/2)
        self.pick(QPointF(point.x(), -point.y()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.disk().contains(event.position()):
            self.setFocus(Qt.MouseFocusReason)
            self.dragging = True
            self.started.emit()
            self.pick_mouse(event.position())
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.pick_mouse(event.position())

    def mouseReleaseEvent(self, event):
        if self.dragging and event.button() == Qt.LeftButton:
            self.pick_mouse(event.position())
            self.dragging = False
            self.released.emit()

    def keyPressEvent(self, event):
        directions = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, 1), Qt.Key_Down: (0, -1)}
        if event.key() in directions:
            dx, dy = directions[event.key()]
            self.pick(self.point+QPointF(dx, dy)*(.1 if event.modifiers() & Qt.ShiftModifier else .02))
            event.accept()
        else:
            super().keyPressEvent(event)


class GradeSurface(Surface):
    def __init__(self, viewport):
        super().__init__(viewport, "GpuGradeMonitor.qml")
        self.geometry(viewport.rect())

    def schedule(self):
        self.geometry(self.viewport.rect())

    def eventFilter(self, watched, event):
        if watched is self.viewport and event.type() in (QEvent.Resize, QEvent.Show) and not self.closed:
            self.schedule()
        elif watched in (self.view, self.container) and event.type() == QEvent.MouseButtonPress:
            self.viewport.setFocus(Qt.MouseFocusReason)
        elif watched is self.view and event.type() in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(self.viewport, event)
            return event.isAccepted()
        # This monitor has no editor drag, crop handles or context menus.
        return False


class ClipMonitor(QWidget):
    def __init__(self, item, media, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(155)
        self.setFocusPolicy(Qt.StrongFocus)
        self.surface = GradeSurface(self)
        self.still = media.kind == "image"
        self.message = "Opening clip…"
        crop = item.crop.clamped()
        self.layer = self.surface.item("gradeLayer")
        self.video = self.surface.item("gradeVideo")
        self.photo = self.surface.item("gradePhoto")
        self.surface.root.setProperty("still", self.still)
        self.surface.root.setProperty("aspect", max(1, media.width)*crop.width/(max(1, media.height)*crop.height))
        horizontal, vertical = item.transform.flip_horizontal, item.transform.flip_vertical
        self.layer.setProperty("cropRect", QVector4D(
            crop.x+crop.width*horizontal, crop.y+crop.height*vertical,
            -crop.width if horizontal else crop.width, -crop.height if vertical else crop.height))
        self.layer.setProperty("pixelStep", QVector2D(1/max(1, media.width*crop.width), 1/max(1, media.height*crop.height)))
        self.sharpen = max(0., item.sharpen*2)
        self.basic_grade = QVector4D(item.brightness, item.contrast, 0 if item.grayscale else item.saturation, 1)
        # Bound the monitor capture size even for unusually large sources.
        scale = min(1., 2048/max(1, media.width, media.height))
        self.video.setProperty("pixelWidth", max(2, round(media.width*scale)))
        self.video.setProperty("pixelHeight", max(2, round(media.height*scale)))
        self.sink = self.video.property("sink")

    def open_image(self, url):
        self.photo.setProperty("source", url)

    def admit_video(self):
        self.video.setProperty("admitted", True)
        if self.message:
            self.set_message("")

    def set_message(self, message):
        self.message = message
        self.surface.root.setProperty("message", message)

    def grade(self, raw, original=False):
        self.surface.properties(self.layer, {
            "sharpen": 0. if original else self.sharpen,
            "grade": QVector4D(0, 1, 1, 1) if original else self.basic_grade,
        })
        publish(self.layer, {} if original else raw)

    def paintEvent(self, event):
        self.surface.paint_underlay(event, "#101114")

    def close_surface(self):
        self.surface.close()


class ClipScrubber(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            handle = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)
            groove = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderGroove, self)
            if not handle.contains(event.position().toPoint()):
                position = round(event.position().x()-groove.left()-handle.width()/2)
                self.setValue(QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                             position, max(1, groove.width()-handle.width())))
                event.accept()
                return
        super().mousePressEvent(event)


class OriginalButton(QPushButton):
    def hitButton(self, pos):
        # Keep the comparison active when the pointer leaves the button
        # during a captured press.
        return self.isDown() or super().hitButton(pos)


class GradeDialog(QDialog):
    def __init__(self, window, item, media):
        super().__init__(window)
        self.setWindowTitle("Advanced Colours")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumSize(600, 550)
        self.current = clean(item.colour_grade)
        self.history = [self.current]
        self.history_index = 0
        self.editing = None
        self.dragging = False
        self.original_mouse = False
        self.original_key = False
        self.preset_settings = window.settings
        self.custom_presets = saved_presets(self.preset_settings)
        self.selected_custom = next((r["id"] for r in self.custom_presets if r["values"] == self.current), None)
        self.start_ms = round(item.in_point*1000)
        self.speed = max(.01, item.speed)
        self.fps = max(1, window.project.settings.fps)
        self.last_frame = max(0, math.ceil(item.duration*self.fps-1e-7)-1)
        self.end_ms = self.start_ms + max(1, round(item.duration*self.speed*1000))
        self.pending_seek = min(self.last_frame, max(0, round((window.project.playhead-item.start)*self.fps)))
        self.initial_seek = True
        self.prime_ms = None
        self.prime_retry = None
        self.resume_after_seek = False
        self.shuttle_rate = 1
        self.wheels, self.tone = {}, {}
        self.settle = QTimer(self, singleShot=True, interval=280)
        self.settle.timeout.connect(self.finish_edit)
        self.seek_timer = QTimer(self, singleShot=True, interval=32)
        self.seek_timer.timeout.connect(lambda: self.seek(self.pending_seek))
        self.boundary_timer = QTimer(self, interval=16)
        self.boundary_timer.timeout.connect(self.check_end)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        header = QHBoxLayout()
        clip_name = QLabel(media.name)
        clip_name.setTextFormat(Qt.PlainText)
        clip_name.setMinimumWidth(0)
        clip_name.setToolTip(media.name)
        clip_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        header.addWidget(clip_name, 1)
        self.before_button = OriginalButton("Hold for Original")
        self.before_button.setMinimumWidth(108)
        self.before_button.setAutoDefault(False)
        self.before_button.setToolTip("Hold this button or the backslash key to see the source colours.")
        self.before_button.pressed.connect(lambda: self.hold_original(True))
        self.before_button.released.connect(lambda: self.hold_original(False))
        header.addWidget(self.before_button)
        root.addLayout(header)
        self.monitor = ClipMonitor(item, media)
        root.addWidget(self.monitor, 1)
        transport = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setMinimumWidth(60)
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_play)
        transport.addWidget(self.play_button)
        self.scrubber = ClipScrubber(Qt.Horizontal)
        self.scrubber.setAccessibleName("Clip position")
        self.scrubber.setRange(0, self.last_frame)
        self.scrubber.setValue(self.pending_seek)
        self.scrubber.valueChanged.connect(self.request_seek)
        self.scrubber.sliderPressed.connect(self.start_scrub)
        self.scrubber.sliderReleased.connect(self.end_scrub)
        transport.addWidget(self.scrubber, 1)
        self.timestamp = QLabel()
        transport.addWidget(self.timestamp)
        root.addLayout(transport)
        self.show_position(self.pending_seek)

        tools = QHBoxLayout()
        self.presets = QComboBox()
        self.presets.setAccessibleName("Grading preset")
        self.presets.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.presets.setMinimumWidth(132)
        self.presets.activated.connect(self.apply_preset)
        tools.addWidget(self.presets, 1)
        self.save_preset_button = QPushButton("Save Preset")
        self.delete_preset_button = QPushButton("Delete Preset")
        self.save_preset_button.clicked.connect(self.save_preset)
        self.delete_preset_button.clicked.connect(self.delete_preset)
        tools.addWidget(self.save_preset_button)
        tools.addWidget(self.delete_preset_button)
        self.reload_presets()
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        tools.addWidget(self.undo_button)
        tools.addWidget(self.redo_button)
        self.reset_grade_button = self.reset_button("Reset Grade", self.reset_grade)
        tools.addWidget(self.reset_grade_button)
        root.addLayout(tools)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.make_wheels(), "Wheels")
        self.tabs.addTab(self.make_tone(), "Tone")
        root.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoSink(self.monitor.sink)
        self.player.setPlaybackRate(self.speed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.play_state)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.seekableChanged.connect(self.prime_initial)
        self.player.errorOccurred.connect(self.media_error)
        self.frame_timer = QTimer(self, interval=16)
        self.frame_timer.timeout.connect(self.poll_frame)
        self.finished.connect(self.stop_monitor)
        url = QUrl.fromLocalFile(str(Path(media.path).resolve()))
        if self.monitor.still:
            self.scrubber.setEnabled(False)
            self.monitor.open_image(url)
        else:
            from .media_source import set_media_source
            set_media_source(self.player, url)
            self.frame_timer.start()

        self.install_shortcuts(window)
        self.refresh_controls()
        self.resize(920, 725)
        self.monitor.setFocus(Qt.OtherFocusReason)

    @staticmethod
    def spin(low, high, step, suffix=""):
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(0 if step >= 1 else 2)
        spin.setSingleStep(step)
        spin.setKeyboardTracking(False)
        spin.setSuffix(suffix)
        return spin

    @staticmethod
    def reset_button(label, reset):
        button = QPushButton()
        button.setIcon(lucide_icon("refresh-cw"))
        button.setIconSize(QSize(15, 15))
        button.setFixedWidth(34)
        button.setAutoDefault(False)
        button.setAccessibleName(label)
        button.setToolTip(label)
        button.clicked.connect(reset)
        return button

    def make_wheels(self):
        page = QWidget()
        page.setMinimumHeight(183)
        row = QHBoxLayout(page)
        row.setContentsMargins(8, 5, 8, 7)
        for key, title, hint in WHEELS:
            column = QVBoxLayout()
            label = QLabel(title + " · " + hint.split()[0], alignment=Qt.AlignCenter)
            label.setToolTip(hint)
            column.addWidget(label)
            wheel = ColourWheel(title, hint)
            wheel.setFixedSize(108, 108)
            column.addWidget(wheel, alignment=Qt.AlignHCenter)
            level = self.spin(-100, 100, 1)
            level.setAccessibleName(title + " level")
            level.setToolTip(hint + " level")
            reset = self.reset_button("Reset " + title, lambda _, k=key: self.reset_wheel(k))
            line = QHBoxLayout()
            line.addWidget(level)
            line.addWidget(reset)
            column.addLayout(line)
            row.addLayout(column, 1)
            self.wheels[key] = wheel, level, reset
            wheel.started.connect(lambda k=key: self.start_gesture(k))
            wheel.changed.connect(lambda x, y, k=key: self.wheel_changed(k, x, y))
            wheel.released.connect(self.finish_edit)
            level.valueChanged.connect(lambda value, k=key: self.level_changed(k, value))
        return page

    def make_tone(self):
        page = QWidget()
        grid = QGridLayout(page)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 1)
        for index, (key, label, low, high, default, step, suffix) in enumerate(TONE):
            slider = QSlider(Qt.Horizontal)
            slider.setAccessibleName(label)
            slider.setRange(round(low/step), round(high/step))
            spin = self.spin(low, high, step, suffix)
            spin.setAccessibleName(label + " value")
            column = 3*(index//4)
            caption = QLabel(label)
            caption.setBuddy(spin)
            grid.addWidget(caption, index%4, column)
            grid.addWidget(slider, index%4, column+1)
            grid.addWidget(spin, index%4, column+2)
            slider.sliderPressed.connect(lambda k=key: self.start_gesture(k))
            slider.sliderReleased.connect(self.finish_edit)
            slider.valueChanged.connect(lambda value, k=key, s=step: self.edit(k, value*s))
            spin.valueChanged.connect(lambda value, k=key: self.edit(k, value))
            self.tone[key] = slider, spin, step, default
        return page

    def install_shortcuts(self, window):
        self.shortcuts = []
        keys = window.settings.get("shortcuts", {})
        bindings = (("undo", "Ctrl+Z", self.undo), ("redo", "Ctrl+Shift+Z", self.redo),
                    ("play_pause", "Space", self.toggle_play), ("shuttle_back", "J", self.back),
                    ("shuttle_stop", "K", self.stop), ("shuttle_forward", "L", self.forward))
        self.edit_keys = {}
        for name, default, fn in bindings:
            key = QKeySequence(keys.get(name, default))
            if not key.isEmpty() and name in ("undo", "redo"):
                self.edit_keys[key[0].toCombined()] = fn
            self.shortcut(key, fn)
        # The embedded spin editors normally reserve Ctrl+Z for text. Here it
        # always means undoing a grade change, including with a number focused.
        for widget in [self, *self.findChildren(QWidget)]:
            widget.installEventFilter(self)

    def shortcut(self, sequence, action):
        shortcut = QShortcut(sequence, self)
        shortcut.setContext(Qt.WindowShortcut)
        shortcut.activated.connect(action)
        self.shortcuts.append(shortcut)

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self and kind == QEvent.WindowDeactivate:
            self.original_key = False
            self.before_button.setDown(False)
            self.hold_original(False)
        if watched is self.before_button and kind == QEvent.UngrabMouse:
            self.before_button.setDown(False)
            self.hold_original(False)
        if (kind in (QEvent.ShortcutOverride, QEvent.KeyPress, QEvent.KeyRelease)
                and event.key() == Qt.Key_Backslash and (self.original_key or event.modifiers() == Qt.NoModifier)):
            if kind != QEvent.ShortcutOverride and not event.isAutoRepeat():
                self.original_key = kind == QEvent.KeyPress
                self.refresh_monitor()
            event.accept()
            return True
        if event.type() in (QEvent.ShortcutOverride, QEvent.KeyPress):
            fn = getattr(self, "edit_keys", {}).get(event.keyCombination().toCombined())
            if fn:
                if event.type() == QEvent.KeyPress:
                    fn()
                event.accept()
                return True
            if (event.type() == QEvent.KeyPress and watched in (self.monitor, self.scrubber)
                    and event.modifiers() == Qt.NoModifier):
                if event.key() in (Qt.Key_Left, Qt.Key_Right):
                    self.stop()
                    self.scrubber.setValue(self.scrubber.value()+(1 if event.key()==Qt.Key_Right else -1))
                    return True
        return super().eventFilter(watched, event)

    def start_gesture(self, key):
        self.finish_edit()
        self.editing = key
        self.dragging = True

    def edit(self, key, value):
        if self.editing != key:
            self.finish_edit()
            self.editing = key
        self.current = clean({**self.current, key: value})
        if not self.dragging:
            self.settle.start()
        self.refresh_controls()

    def wheel_changed(self, key, x, y):
        radius = max(1., math.hypot(x, y))
        self.edit(key, (x/radius, y/radius, self.current.get(key, (0, 0, 0))[2]))

    def level_changed(self, key, value):
        x, y, _ = self.current.get(key, (0, 0, 0))
        self.edit(key, (x, y, value/100))

    def reset_wheel(self, key):
        self.finish_edit()
        self.replace({name: value for name, value in self.current.items() if name != key})

    def finish_edit(self):
        self.settle.stop()
        self.editing = None
        self.dragging = False
        if self.current != self.history[self.history_index]:
            self.history = (self.history[:self.history_index+1]+[self.current])[-100:]
            self.history_index = len(self.history)-1
        self.update_history_buttons()

    def replace(self, grade):
        self.finish_edit()
        self.current = clean(grade)
        self.finish_edit()
        self.refresh_controls()

    def apply_preset(self, index):
        self.selected_custom = self.presets.itemData(index)
        if index == 0:
            self.sync_preset()
        elif self.selected_custom:
            self.replace(self.current_preset()["values"])
        else:
            self.replace(PRESETS[index-1][1])

    def reset_grade(self):
        self.selected_custom = None
        self.replace({})

    def current_preset(self):
        return next((r for r in self.custom_presets if r["id"] == self.selected_custom), None)

    def reload_presets(self):
        self.edited_preset_index = None
        with QSignalBlocker(self.presets):
            self.presets.clear()
            self.presets.addItems(["Choose a preset…", *(name for name, _ in PRESETS)])
            for record in self.custom_presets:
                self.presets.addItem(record["name"], record["id"])
        self.sync_preset()

    def sync_preset(self):
        current = self.current_preset()
        match = current or next((r for r in self.custom_presets if r["values"] == self.current), None)
        index = (self.presets.findData(match["id"]) if match else
                 next((i for i, (_, values) in enumerate(PRESETS, 1) if clean(values) == self.current), 0))
        edited = index if current and current["values"] != self.current else None
        with QSignalBlocker(self.presets):
            if edited != self.edited_preset_index:
                if self.edited_preset_index is not None:
                    record = self.custom_presets[self.edited_preset_index-len(PRESETS)-1]
                    self.presets.setItemText(self.edited_preset_index, record["name"])
                if edited is not None:
                    self.presets.setItemText(edited, current["name"] + " (edited)")
                self.edited_preset_index = edited
            self.presets.setCurrentIndex(index)
        self.presets.setToolTip(self.presets.currentText())
        self.delete_preset_button.setEnabled(match is not None)

    def store_presets(self, records, selected=None):
        from .config import save_settings
        previous = self.preset_settings.get(PRESETS_KEY)
        self.preset_settings[PRESETS_KEY] = records
        try:
            save_settings(self.preset_settings)
        except OSError as error:
            if previous is None:
                self.preset_settings.pop(PRESETS_KEY, None)
            else:
                self.preset_settings[PRESETS_KEY] = previous
            QMessageBox.warning(self, "Could not save colour presets", str(error))
            return
        self.custom_presets = records
        self.selected_custom = selected
        self.reload_presets()

    def save_preset(self):
        from .model import uid
        from .video_presets import PresetNameDialog

        current = self.current_preset() or next((r for r in self.custom_presets
                                                if r["id"] == self.presets.currentData()), None)
        if current:
            prompt = QMessageBox(self)
            prompt.setWindowTitle("Save colour preset")
            prompt.setText("Overwrite current preset?")
            prompt.setInformativeText(current["name"])
            overwrite = prompt.addButton("Overwrite", QMessageBox.AcceptRole)
            new = prompt.addButton("Save as new", QMessageBox.ActionRole)
            prompt.addButton(QMessageBox.Cancel)
            prompt.exec()
            if prompt.clickedButton() is overwrite:
                records = [dict(r, values=clean(self.current)) if r is current else r for r in self.custom_presets]
                self.store_presets(records, current["id"])
                return
            if prompt.clickedButton() is not new:
                return
        if len(self.custom_presets) >= PRESET_LIMIT:
            QMessageBox.information(self, "Colour presets", "Remove an unused preset before saving another.")
            return
        names = [{"name": name} for name, _ in PRESETS] + self.custom_presets
        prompt = PresetNameDialog(self, names, "Save colour preset")
        if prompt.exec() == QDialog.Accepted:
            record = dict(id=uid(), name=prompt.name.text().strip(), values=clean(self.current))
            self.store_presets([*self.custom_presets, record], record["id"])

    def delete_preset(self):
        key = self.presets.currentData()
        record = next((r for r in self.custom_presets if r["id"] == key), None)
        if record and QMessageBox.question(self, "Delete colour preset", f'Delete preset "{record["name"]}"?',
                                           QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes:
            self.store_presets([r for r in self.custom_presets if r is not record])

    def undo(self):
        self.finish_edit()
        self.history_index = max(0, self.history_index-1)
        self.current = self.history[self.history_index]
        self.refresh_controls()

    def redo(self):
        self.finish_edit()
        self.history_index = min(len(self.history)-1, self.history_index+1)
        self.current = self.history[self.history_index]
        self.refresh_controls()

    def update_history_buttons(self):
        changed = self.current != self.history[self.history_index]
        self.undo_button.setEnabled(changed or self.history_index > 0)
        self.redo_button.setEnabled(not changed and self.history_index < len(self.history)-1)

    def refresh_controls(self):
        for key, (wheel, spin, reset) in self.wheels.items():
            x, y, level = self.current.get(key, (0, 0, 0))
            point = QPointF(x, y)
            if wheel.point != point:
                wheel.point = point
                wheel.update()
            with QSignalBlocker(spin):
                spin.setValue(level*100)
            reset.setEnabled(key in self.current)
        for key, (slider, spin, step, default) in self.tone.items():
            value = self.current.get(key, default)
            with QSignalBlocker(slider), QSignalBlocker(spin):
                slider.setValue(round(value/step))
                spin.setValue(value)
        self.sync_preset()
        self.update_history_buttons()
        self.refresh_monitor()

    def hold_original(self, pressed):
        self.original_mouse = pressed
        self.refresh_monitor()

    def refresh_monitor(self):
        self.monitor.grade(self.current, original=self.original_mouse or self.original_key)

    def show_position(self, frame):
        from .ui import timecode
        rate = round(self.fps)
        self.timestamp.setText(f"{timecode(frame/rate, rate)} / {timecode(self.last_frame/rate, rate)}")

    def request_seek(self, frame):
        self.pending_seek = frame
        self.show_position(frame)
        self.seek_timer.start()

    def seek(self, frame):
        self.seek_timer.stop()
        if not self.monitor.still and self.player.isSeekable():
            self.player.setPosition(min(self.end_ms-1, self.start_ms+round(frame/self.fps*self.speed*1000)))

    def position_changed(self, position):
        if self.prime_ms is not None or self.scrubber.isSliderDown() or self.seek_timer.isActive() or position < self.start_ms:
            return
        frame = min(self.last_frame, max(0, round((position-self.start_ms)*self.fps/(self.speed*1000))))
        with QSignalBlocker(self.scrubber):
            self.scrubber.setValue(frame)
        self.show_position(frame)
        self.check_end()

    def media_status(self, status):
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self.prime_initial()
        elif status == QMediaPlayer.EndOfMedia:
            self.stop()

    def prime_initial(self, *_):
        if (self.initial_seek and self.player.isSeekable()
                and self.player.mediaStatus() in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia, QMediaPlayer.BufferingMedia)):
            self.initial_seek = False
            self.prime_ms = self.start_ms+round(self.pending_seek/self.fps*self.speed*1000)
            self.audio.setMuted(True)
            self.seek(self.pending_seek)
            self.player.play()

    def poll_frame(self):
        frame = self.monitor.sink.videoFrame()
        if not frame.isValid():
            return
        if self.prime_ms is not None:
            target = self.prime_ms*1000
            if 0 <= frame.endTime() < target-25_000:
                return
            if self.player.playbackState() == QMediaPlayer.PlayingState:
                self.player.pause()
                return
            # Some backends have already advanced while the initial frame
            # was queued. Correct it once while paused before revealing it.
            if frame.startTime() > target+40_000:
                if self.prime_retry is None:
                    self.prime_retry = QDeadlineTimer(750)
                    self.player.setPosition(self.prime_ms)
                    return
                if not self.prime_retry.hasExpired():
                    return
            self.prime_ms = None
            self.audio.setMuted(False)
        self.monitor.admit_video()
        self.play_button.setEnabled(True)
        self.frame_timer.stop()

    def media_error(self, _error, message):
        self.monitor.set_message("Could not play this clip. " + message)

    def start_scrub(self):
        self.resume_after_seek = self.player.playbackState() == QMediaPlayer.PlayingState
        self.player.pause()

    def end_scrub(self):
        self.seek(self.scrubber.value())
        if self.resume_after_seek:
            self.player.play()
        self.resume_after_seek = False

    def play_state(self, state):
        playing = self.prime_ms is None and state == QMediaPlayer.PlayingState
        self.play_button.setText("Pause" if playing else "Play")
        if playing:
            self.boundary_timer.start()
        else:
            self.boundary_timer.stop()

    def check_end(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState and self.player.position() >= self.end_ms:
            self.stop()
            self.seek(self.last_frame)

    def toggle_play(self):
        if not self.play_button.isEnabled():
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.stop()
        else:
            self.forward()

    def forward(self):
        if not self.play_button.isEnabled():
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.shuttle_rate = min(4, self.shuttle_rate*2)
        elif self.scrubber.value() == self.last_frame and self.last_frame:
            self.seek(0)
        elif self.seek_timer.isActive() or self.player.position() < self.start_ms:
            self.seek(self.pending_seek)
        self.player.setPlaybackRate(self.speed*self.shuttle_rate)
        self.player.play()

    def back(self):
        self.stop()
        self.scrubber.setValue(max(0, self.scrubber.value()-round(self.fps*.5)))

    def stop(self):
        self.player.pause()
        self.shuttle_rate = 1
        self.player.setPlaybackRate(self.speed)

    def stop_monitor(self, _result):
        self.seek_timer.stop()
        self.settle.stop()
        self.boundary_timer.stop()
        self.frame_timer.stop()
        self.player.stop()
        self.player.setVideoSink(None)
        from .media_source import set_media_source
        set_media_source(self.player, QUrl())
        self.monitor.close_surface()
