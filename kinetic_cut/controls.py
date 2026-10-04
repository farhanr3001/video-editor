import time
from PySide6.QtCore import Qt, QEvent, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QAbstractScrollArea, QComboBox, QDoubleSpinBox, QSpinBox, QSlider, QToolButton, QVBoxLayout, QHBoxLayout, QWidget, QLayout, QSizePolicy,QStyle,QStyleOptionSlider
from .icons import resource_path, lucide_icon
from .theme_widgets import set_ui_style


class _NoAccidentalWheel:
    """Numeric fields never consume wheel input; the surrounding Inspector scrolls."""

    def wheelEvent(self, event):
        parent=self.parentWidget()
        while parent and not isinstance(parent,QAbstractScrollArea):parent=parent.parentWidget()
        if parent:
            bar=parent.verticalScrollBar(); bar.setValue(bar.value()-event.angleDelta().y()); event.accept()
        else:event.ignore()


def scrub_delta(pixels, seconds, sensitivity, modifiers=Qt.NoModifier):
    """Units are independent of decimal precision; fast gestures accelerate."""
    speed=abs(pixels)/max(.008,min(.25,seconds))
    acceleration=1+min(4.25,max(0.,speed-100)/400)
    precision=.1 if modifiers&Qt.ShiftModifier else 10 if modifiers&Qt.ControlModifier else 1
    return pixels*sensitivity*acceleration*precision


class _ValueScrub:
    def _init_scrub(self):
        self._drag_start=None; self.drag_sensitivity=None; self._typing=False; self._finishing_edit=False
        self.setFocusPolicy(Qt.NoFocus); self.installEventFilter(self); self.lineEdit().installEventFilter(self)
        self.lineEdit().setToolTip("Drag to adjust · Shift: fine · Ctrl: coarse · Double-click to type")

    def _end_scrub(self):
        if self._drag_start is None:return
        anchor=self._drag_start; self._drag_start=None
        QGuiApplication.instance().removeEventFilter(self)
        self.lineEdit().releaseMouse(); self.lineEdit().unsetCursor()
        if QGuiApplication.platformName()!="offscreen":QCursor.setPos(anchor)
        self.scrubFinished.emit()

    def eventFilter(self, watched, event):
        # Native Qt routes spin-box keyboard input to the spin box itself,
        # although the embedded line edit displays the selection/caret.
        if watched in (self,self.lineEdit()) and event.type()==QEvent.KeyPress and event.key() in (Qt.Key_Return,Qt.Key_Enter):
            self._finish_keyboard_edit(); return True
        if self._drag_start is not None:
            if event.type() in (QEvent.ApplicationDeactivate,QEvent.WindowDeactivate):self._end_scrub()
            elif event.type()==QEvent.KeyPress and event.key()==Qt.Key_Escape:self._end_scrub(); return True
        if watched is self.lineEdit():
            kind=event.type()
            if kind==QEvent.Wheel:self.wheelEvent(event); return True
            if kind==QEvent.MouseButtonDblClick and event.button()==Qt.LeftButton:
                self._end_scrub(); self._typing=True; self.setKeyboardTracking(False); self.setFocusPolicy(Qt.StrongFocus); watched.setFocus(); watched.selectAll(); return True
            if kind==QEvent.MouseButtonPress and event.button()==Qt.LeftButton and not self._typing and not self.isReadOnly():
                self._drag_start=event.globalPosition().toPoint(); self._drag_value=float(self.value()); self._drag_time=time.perf_counter()
                QGuiApplication.instance().installEventFilter(self)
                watched.setCursor(Qt.BlankCursor)
                if QGuiApplication.platformName()!="offscreen":watched.grabMouse()
                self.scrubStarted.emit(); return True
            if kind==QEvent.MouseMove and self._drag_start is not None:
                dx=event.globalPosition().x()-self._drag_start.x()
                if dx:
                    now=time.perf_counter(); sensitivity=self.drag_sensitivity
                    if sensitivity is None:sensitivity=max(.01,min(1.,(self.maximum()-self.minimum())/500))
                    self._drag_value=max(self.minimum(),min(self.maximum(),self._drag_value+scrub_delta(dx,now-self._drag_time,sensitivity,event.modifiers())))
                    self._drag_time=now
                    self.setValue(round(self._drag_value) if isinstance(self,QSpinBox) else self._drag_value)
                    if QGuiApplication.platformName()!="offscreen":QCursor.setPos(self._drag_start)
                return True
            if kind==QEvent.MouseButtonRelease and self._drag_start is not None:self._end_scrub(); return True
            if kind in (QEvent.Hide,QEvent.UngrabMouse,QEvent.WindowDeactivate):self._end_scrub()
            if kind==QEvent.KeyPress:
                if event.key()==Qt.Key_Escape and self._drag_start is not None:self._end_scrub(); return True
                if event.key() in (Qt.Key_Return,Qt.Key_Enter) and self._typing:
                    self._finish_keyboard_edit(); return True
            if kind==QEvent.FocusOut and self._typing:self._finish_keyboard_edit()
        return super().eventFilter(watched,event)

    def _finish_keyboard_edit(self):
        if self._finishing_edit:return
        self._finishing_edit=True
        try:
            self.interpretText(); self._typing=False; self.setKeyboardTracking(True)
            self.lineEdit().deselect(); self.lineEdit().clearFocus(); self.clearFocus(); self.setFocusPolicy(Qt.NoFocus)
            self.editingFinished.emit()
            self.lineEdit().deselect(); self.lineEdit().clearFocus(); self.clearFocus()
        finally:self._finishing_edit=False


class SafeDoubleSpinBox(_ValueScrub, _NoAccidentalWheel, QDoubleSpinBox):
    scrubStarted=Signal()
    scrubFinished=Signal()
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.setMinimumHeight(24); self._install_arrows(); self._init_scrub()
    def _install_arrows(self):
        up=resource_path("assets","icons","spin-up.svg").as_posix(); down=resource_path("assets","icons","spin-down.svg").as_posix()
        set_ui_style(self, 'QDoubleSpinBox::up-arrow { image: url("@arrow_up"); width: 11px; height: 11px; } QDoubleSpinBox::down-arrow { image: url("@arrow_down"); width: 11px; height: 11px; }')

    def stepBy(self,steps):
        # An ellipsis represents a mixed multi-selection and is not valid numeric
        # text, so Qt's default stepper refuses it. Step from the stored mean.
        if self.lineEdit().text()=="…":self.setValue(self.value()+steps*self.singleStep())
        else:super().stepBy(steps)


class SafeSpinBox(_ValueScrub, _NoAccidentalWheel, QSpinBox):
    scrubStarted=Signal()
    scrubFinished=Signal()
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self._init_scrub()
        up=resource_path("assets","icons","spin-up.svg").as_posix(); down=resource_path("assets","icons","spin-down.svg").as_posix()
        set_ui_style(self, 'QSpinBox::up-arrow { image: url("@arrow_up"); width: 11px; height: 11px; } QSpinBox::down-arrow { image: url("@arrow_down"); width: 11px; height: 11px; }')


class SafeComboBox(_NoAccidentalWheel, QComboBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.setMinimumHeight(24)


class SafeSlider(_NoAccidentalWheel,QSlider):
    def _position_value(self,pos):
        option=QStyleOptionSlider(); self.initStyleOption(option)
        groove=self.style().subControlRect(QStyle.CC_Slider,option,QStyle.SC_SliderGroove,self)
        handle=self.style().subControlRect(QStyle.CC_Slider,option,QStyle.SC_SliderHandle,self)
        horizontal=self.orientation()==Qt.Horizontal
        length=handle.width() if horizontal else handle.height(); start=groove.left() if horizontal else groove.top()
        span=(groove.width() if horizontal else groove.height())-length
        pixel=(pos.x() if horizontal else pos.y())-start-length/2
        val = QStyle.sliderValueFromPosition(self.minimum(),self.maximum(),round(pixel),max(1,span),option.upsideDown)
        return max(self.minimum(), min(self.maximum(), val)), handle
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            value,handle=self._position_value(event.position())
            self._jump_drag=True
            self.setSliderDown(True)
            self.setValue(value)
            event.accept()
            return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if getattr(self,'_jump_drag',False):
            val, _ = self._position_value(event.position())
            self.setValue(val)
            event.accept()
            return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if getattr(self,'_jump_drag',False) and event.button()==Qt.LeftButton:
            self._jump_drag=False
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class InspectorSection(QWidget):
    def __init__(self, title: str, content: QWidget, expanded: bool = True, parent=None, reset_callback=None, enabled_callback=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        if content.layout():content.layout().setSizeConstraint(QLayout.SetMinimumSize)
        header=QWidget(); header.setProperty("inspectorSectionHeader",True)
        header_layout=QHBoxLayout(header); header_layout.setContentsMargins(0,0,4,0); header_layout.setSpacing(0)
        self.enabled_button=None
        if enabled_callback:
            self.enabled_button=QToolButton(); self.enabled_button.setObjectName("sectionEnabled"); self.enabled_button.setCheckable(True); self.enabled_button.setText("●"); self.enabled_button.setFixedSize(26,18); self.enabled_button.setToolTip("Enable "+title); self.enabled_button.setAccessibleName("Enable "+title); self.enabled_button.toggled.connect(enabled_callback); header_layout.addWidget(self.enabled_button)
        self.toggle = QToolButton(text=title)
        self.toggle.setProperty("sectionToggle", True); self.toggle.setCheckable(True); self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed); self.toggle.setMinimumHeight(30)
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content = content
        self.toggle.toggled.connect(self._toggle)
        header_layout.addWidget(self.toggle,1)
        self.reset_button=QToolButton(); self.reset_button.setObjectName("sectionResetAll"); self.reset_button.setIcon(lucide_icon("rotate-ccw","#96989f",14)); self.reset_button.setToolTip(f"Reset all {title} properties")
        self.reset_button.setAccessibleName(f"Reset all {title} properties")
        if reset_callback:self.reset_button.clicked.connect(reset_callback)
        else:self.reset_button.setEnabled(False)
        header_layout.addWidget(self.reset_button)
        header.setMinimumHeight(30); layout.addWidget(header); layout.addWidget(content)
        # Adopt first: show() on unattached content briefly creates a separate
        # desktop window during startup and when constructing inspector dialogs.
        self.content.setVisible(expanded)

    def _toggle(self, expanded: bool):
        self.toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.content.setVisible(expanded)
