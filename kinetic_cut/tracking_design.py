"""Scoped, theme-aware presentation for the tracking authoring workspace."""
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLabel,QToolButton,QSizePolicy,QHeaderView,QCheckBox,QPushButton,QStyle,QStyleOptionButton)
from .icons import lucide_icon
from .theme_widgets import set_ui_style,set_ui_icon,palette
from .controls import SafeComboBox


def _button(button,icon,text=None):
    button.setIcon(lucide_icon(icon));button.setIconSize(QSize(16,16))
    if text is not None:button.setText(text)


class TrackingComboBox(SafeComboBox):
    """Tracking choices open below their field and use a scrolling list."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setMaxVisibleItems(7)

    def showPopup(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QPoint
        super().showPopup()
        popup=self.view().window()
        below=self.mapToGlobal(QPoint(0,self.height()))
        screen=QApplication.screenAt(below) or QApplication.primaryScreen()
        available=screen.availableGeometry()
        height=min(popup.height(),max(24,available.bottom()-below.y()))
        popup.resize(max(self.width(),popup.width()),height)
        popup.move(max(available.left(),min(below.x(),available.right()-popup.width()+1)),below.y())


class TrackingCheckBox(QCheckBox):
    """Native checkbox semantics with a legible, explicitly themed indicator."""
    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text())+28,max(24,self.fontMetrics().height()+4))

    def paintEvent(self,event):
        p=palette();painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        box=QRectF(1,(self.height()-16)/2,16,16)
        painter.setPen(QPen(QColor(p['text_sub'] if self.isEnabled() else p['border_subtle']),1))
        painter.setBrush(QColor(p['bg_input']));painter.drawRoundedRect(box,3,3)
        ink=QColor(p['text_main'] if self.isEnabled() else p['text_disabled'])
        if self.isChecked():
            path=QPainterPath();path.moveTo(box.left()+3,box.center().y())
            path.lineTo(box.left()+7,box.bottom()-4);path.lineTo(box.right()-3,box.top()+4)
            painter.setPen(QPen(ink,2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));painter.drawPath(path)
        painter.setPen(ink);painter.drawText(self.rect().adjusted(26,0,0,0),Qt.AlignVCenter|Qt.AlignLeft,self.text())
        if self.hasFocus():
            painter.setPen(QPen(QColor(p['info']),1,Qt.DotLine));painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),3,3)
        painter.end()


class ColourSwatchButton(QPushButton):
    def set_swatch(self,colour):
        self.swatch=QColor(colour);self.update()

    def paintEvent(self,event):
        option=QStyleOptionButton();self.initStyleOption(option)
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        self.style().drawControl(QStyle.CE_PushButtonBevel,option,painter,self)
        p=palette();painter.setPen(QColor(p['text_main'] if self.isEnabled() else p['text_disabled']))
        painter.drawText(self.rect().adjusted(10,0,-47,0),Qt.AlignLeft|Qt.AlignVCenter,self.text())
        painter.setBrush(getattr(self,'swatch',QColor('#ffffff')))
        painter.setPen(QPen(QColor(p['text_sub']),1))
        painter.drawRoundedRect(QRectF(self.width()-40,(self.height()-16)/2,30,16),3,3)
        painter.end()


class TrackingCard(QFrame):
    def __init__(self,title,icon,parent=None,collapsible=False):
        super().__init__(parent)
        self.setProperty('trackingCard',True)
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        header=QWidget(self);header.setProperty('trackingCardHeader',True)
        self.header=header
        line=QHBoxLayout(header);line.setContentsMargins(12,9,12,9);line.setSpacing(8)
        glyph=QLabel();glyph.setFixedSize(18,18);set_ui_icon(glyph,icon,size=18)
        line.addWidget(glyph)
        self.title_label=QLabel(title);self.title_label.setProperty('trackingHeading',True)
        line.addWidget(self.title_label,1)
        if collapsible:
            self.toggle=QToolButton()
            self.toggle.setProperty('trackingSectionToggle',True)
            self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.toggle.setCheckable(True);self.toggle.setChecked(True)
            self.toggle.setArrowType(Qt.DownArrow)
            self.toggle.setToolTip('Show or hide '+title.lower())
            line.addWidget(self.toggle)
        root.addWidget(header)
        self.header_line=line
        self.body=QWidget(self);self.body.setProperty('trackingBody',True)
        self.content=QVBoxLayout(self.body);self.content.setContentsMargins(12,12,12,12);self.content.setSpacing(10)
        root.addWidget(self.body,1)
        if collapsible:
            self.toggle.toggled.connect(self.body.setVisible)
            self.toggle.toggled.connect(lambda shown:self.toggle.setArrowType(Qt.DownArrow if shown else Qt.RightArrow))


STYLE='''
QDialog#trackingWorkspace { background: @bg_main; }
QWidget { font-size: 12px; color: @text_main; }
QWidget[trackingBody="true"] { background: transparent; border: none; }
QFrame[trackingCard="true"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 @bg_panel,stop:1 @bg_main); border:1px solid @border_subtle; border-radius:10px; }
QWidget[trackingCardHeader="true"] { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 @bg_surface,stop:1 @bg_panel); border:none; border-bottom:1px solid @border_subtle; border-top-left-radius:10px; border-top-right-radius:10px; }
QLabel { background:transparent; border:none; }
QLabel[trackingHeading="true"] { font-size:13px; font-weight:600; }
QLabel#trackingTitle { font-size:18px; font-weight:600; }
QLabel#trackingSource { color:@text_sub; }
QLabel[trackingStep="true"] { font-size:13px; }
QLabel[trackingNumber="true"] { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 @bg_hover,stop:1 @bg_surface); border:1px solid @border_subtle; border-radius:12px; font-size:13px; font-weight:600; }
QLabel#trackingBudget { color:@text_sub; }
QPushButton,QToolButton { min-height:28px; padding:3px 10px; border:1px solid @border_subtle; border-radius:6px; background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 @bg_surface,stop:1 @bg_panel); }
QPushButton:hover,QToolButton:hover { background:@bg_hover; border-color:@text_disabled; }
QPushButton:pressed,QToolButton:pressed { background:@bg_selected; }
QPushButton:disabled,QToolButton:disabled { color:@text_disabled; background:@bg_panel; }
QPushButton[trackingPrimary="true"] { font-weight:600; border-color:@text_disabled; min-height:32px; }
QToolButton[trackingSectionToggle="true"] { border:none; background:transparent; padding:0px; min-height:20px; text-align:left; font-size:13px; font-weight:600; }
QComboBox,QDoubleSpinBox,QLineEdit { background:@bg_input; color:@text_main; border:1px solid @border_subtle; border-radius:6px; min-height:28px; padding:0px 7px; font-size:13px; }
QComboBox:focus,QDoubleSpinBox:focus,QLineEdit:focus { border-color:@text_disabled; }
QComboBox::drop-down { background:transparent; border:none; width:24px; }
QComboBox { combobox-popup:0; }
QComboBox::down-arrow { image:url("@arrow_combo"); width:12px; height:12px; border:none; margin:0; }
QTableWidget { background:@bg_input; alternate-background-color:@bg_panel; border:1px solid @border_subtle; border-radius:6px; gridline-color:@border_subtle; }
QHeaderView::section { background:@bg_surface; color:@text_sub; border:none; border-bottom:1px solid @border_subtle; padding:7px 4px; }
QTableWidget::item { padding:3px 5px; border:none; }
QTableWidget::item:selected { background:@bg_selected; color:@text_selected; }
QScrollArea { background:transparent; border:none; }
QScrollArea > QWidget > QWidget { background:transparent; }
QScrollBar:vertical { width:7px; background:transparent; margin:3px 0; }
QScrollBar::handle:vertical { background:@bg_hover; border-radius:3px; min-height:30px; }
QCheckBox { background:transparent; spacing:8px; min-height:24px; }
QSplitter::handle { background:transparent; width:9px; }
QSlider::groove:horizontal { height:4px; background:@bg_hover; border-radius:2px; }
QSlider::handle:horizontal { background:@text_main; border:0; width:12px; margin:-4px 0; border-radius:6px; }
QFrame#trackingFooter { border:none; border-top:1px solid @border_subtle; background:@bg_topbar; }
QFrame#trackingDivider { background:@border_subtle; border:none; max-height:1px; }
'''
