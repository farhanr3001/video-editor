"""Reversible timeline-focused layout; reuses the editor's live widgets."""
from PySide6.QtCore import QObject,Qt,QEvent,QPoint,QTimer,QSignalBlocker
from PySide6.QtWidgets import QApplication,QWidget,QFrame,QVBoxLayout,QSplitter
from PySide6.QtGui import QAction
from .theme_widgets import set_ui_style


class PanelOverlay(QFrame):
    def __init__(self,controller,kind):
        super().__init__(controller.w,Qt.Tool|Qt.FramelessWindowHint)
        self.controller=controller;self.kind=kind;self.editor_window=controller.w
        self.setObjectName('timelinePanelOverlay');self.setWindowTitle(kind)
        self.setAttribute(Qt.WA_StyledBackground)
        set_ui_style(self,'QFrame#timelinePanelOverlay {background:@bg_panel;border:1px solid @border;}')
        layout=QVBoxLayout(self);layout.setContentsMargins(1,1,1,1);layout.setSpacing(0)
        # Associate the existing actions with this tool window too. Their
        # shortcuts/callbacks stay shared, including user-customized bindings.
        for action in controller.w.findChildren(QAction,options=Qt.FindDirectChildrenOnly):
            if not action.shortcut().isEmpty():self.addAction(action)

    def closeEvent(self,event):
        self.controller.hide_overlay(self.kind);event.accept()


class TimelineWorkspace(QObject):
    def __init__(self,w):
        super().__init__(w);self.w=w;self.active=False;self.return_from_deliver=False
        self.normal={};self.full_sizes=None;self.overlays={}
        self.page=QWidget();layout=QVBoxLayout(self.page);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        self.split=QSplitter(Qt.Horizontal);self.split.setHandleWidth(7);self.split.setChildrenCollapsible(False)
        layout.addWidget(self.split,1);w.page_content.addWidget(self.page)
        self.position_timer=QTimer(self);self.position_timer.setSingleShot(True);self.position_timer.timeout.connect(self.relayout)
        self.split.splitterMoved.connect(lambda *_:self.position_timer.start(0))
        QApplication.instance().installEventFilter(self)

    def toggle(self,checked):self.set_active(checked)

    def set_active(self,active):
        w=self.w
        if active==self.active or (active and w.current_page!=0):return
        # Only widget ownership/geometry changes. No project binding, seek,
        # playback pause, selection reset or edit-history entry occurs here.
        scroll=w.timeline.horizontalScrollBar().value()
        # Qt reparents can rehighlight text fields and emit textChanged even
        # though their values did not change. Keep those presentation signals
        # out of the Inspector's edit/history handlers during the move.
        blockers=[QSignalBlocker(widget) for widget in [w.inspector,*w.inspector.findChildren(QWidget)]]
        w.setUpdatesEnabled(False)
        try:
            if active:
                if not hasattr(self,'bottom'):
                    from .timeline_bottom import BottomTimeline
                    self.bottom=BottomTimeline(w)
                self.bottom.set_active(True)
                self.normal=dict(center=w.center_split.sizes(),workspace=w.workspace_split.sizes(),
                    inspector=w.inspector_toggle.isChecked(),tab=w.left_panels.active,
                    timeline_min=w.timeline_panel.minimumWidth(),viewer_min=w.viewer_panel.minimumWidth())
                self.active=True
                w.left_panels.group.setExclusive(False)
                w.left_panels.layout().removeWidget(w.left_panels.header)
                self.page.layout().insertWidget(0,w.left_panels.header)
                self.split.addWidget(w.timeline_panel);self.split.addWidget(w.viewer_panel)
                w.timeline_panel.setMinimumWidth(680);w.viewer_panel.setMinimumWidth(240)
                w.timeline_panel.show();w.viewer_panel.show()
                self._overlay('Library').layout().addWidget(w.left_panels.stack)
                self._overlay('Inspector').layout().addWidget(w.inspector)
                w.left_panels.header.show();w.left_panels.stack.show();w.inspector.show()
                self._checked(w.inspector_toggle,False);self._library_checks(None)
                w.page_content.setCurrentWidget(self.page)
                width=max(1,w.page_content.width()-7)
                self.split.setSizes(self.full_sizes or [round(width*.76),round(width*.24)])
            else:
                self.bottom.set_active(False)
                self.full_sizes=self.split.sizes();self.close_overlays()
                self.active=False
                w.left_panels.layout().insertWidget(0,w.left_panels.header)
                w.left_panels.layout().addWidget(w.left_panels.stack,1);w.left_panels.stack.show()
                w.right_stack.insertWidget(0,w.inspector);w.inspector.show()
                w.right_stack.setCurrentWidget(w.inspector);w.left_stack.setCurrentWidget(w.left_panels)
                w.viewer_split.insertWidget(0,w.viewer_panel);w.center_split.addWidget(w.timeline_panel)
                w.viewer_split.setStretchFactor(0,1);w.viewer_split.setStretchFactor(1,0)
                w.viewer_split.handle(1).setEnabled(False)
                w.timeline_panel.setMinimumWidth(self.normal['timeline_min']);w.viewer_panel.setMinimumWidth(self.normal['viewer_min'])
                w.page_content.setCurrentWidget(w.center_split)
                w.left_panels.group.setExclusive(True);w.left_panels.select(self.normal['tab'])
                self._checked(w.inspector_toggle,self.normal['inspector'])
                w.left_stack.show();w.right_stack.setVisible(self.normal['inspector'])
                w.viewer_panel.show();w.timeline_panel.show();w.left_panels.header.show()
                w.workspace_split.setSizes(self.normal['workspace']);w.center_split.setSizes(self.normal['center'])
            self._checked(w.fullscreen_timeline,self.active)
            w.fullscreen_timeline.setToolTip('Return to normal timeline layout' if self.active else 'Fullscreen timeline')
            self.page.layout().activate();w.page_content.layout().activate()
            self.relayout();w.timeline.horizontalScrollBar().setValue(scroll)
        finally:
            blockers.clear();w.setUpdatesEnabled(True)
        w.timeline.viewport().update();w.preview.update()

    def _overlay(self,kind):
        if kind not in self.overlays:self.overlays[kind]=PanelOverlay(self,kind)
        return self.overlays[kind]

    @staticmethod
    def _checked(button,value):
        with QSignalBlocker(button):button.setChecked(value)

    def _library_checks(self,name):
        for key,button in self.w.left_panels.buttons.items():self._checked(button,key==name)

    def toggle_library(self,name):
        overlay=self._overlay('Library');library=self.w.left_panels
        if overlay.isVisible() and library.active==name:self.hide_overlay('Library');return
        library.select(name);self._library_checks(name);self.show_overlay('Library')

    def update_panels(self):
        self.w.left_stack.hide();self.w.right_stack.hide()
        if self.w.inspector_toggle.isChecked():self.show_overlay('Inspector')
        else:self.hide_overlay('Inspector')

    def show_overlay(self,kind):
        if not self.active:return
        overlay=self._overlay(kind);self.place(overlay);overlay.show();overlay.raise_()

    def hide_overlay(self,kind):
        overlay=self.overlays.get(kind)
        if overlay:overlay.hide()
        if kind=='Library':self._library_checks(None)
        else:self._checked(self.w.inspector_toggle,False)

    def close_overlays(self):
        for kind in self.overlays:self.hide_overlay(kind)

    def place(self,overlay):
        area=self.split.rect();origin=self.split.mapToGlobal(QPoint())
        width=min(350 if overlay.kind=='Inspector' else max(380,self.normal['workspace'][0]),area.width()-12)
        x=origin.x()+6 if overlay.kind=='Library' else origin.x()+area.width()-width-6
        height=area.height()-12
        y=origin.y()+6
        if overlay.kind=='Library':height=min(height,max(300,self.normal['center'][0]))
        else:
            button=self.w.inspector_toggle;below=button.mapToGlobal(QPoint(button.width(),button.height()))
            preview=self.w.viewer_panel.mapToGlobal(QPoint())
            x=preview.x()-width-6;y=below.y()+4
            height=origin.y()+area.height()-6-y
        overlay.setGeometry(x,y,width,max(160,height))

    def relayout(self):
        w=self.w;compact=self.active and w.timeline_panel.width()<1000
        w.timeline_zoom.setFixedWidth(70 if compact else 110)
        w.timeline_zoom.setVisible(not self.active or w.timeline_panel.width()>=760)
        w.timeline_selector.setMinimumWidth(110 if compact else 120)
        w.timeline_selector.setMinimumContentsLength(9 if compact else 12)
        w.timeline_selector.setMaximumWidth(200 if self.active else 260)
        w.monitor_control.update_layout()
        for overlay in self.overlays.values():
            if overlay.isVisible():self.place(overlay)

    def before_page(self,page):
        if page==1 and self.active:self.set_active(False);self.return_from_deliver=True

    def after_page(self,page):
        if page==0 and self.return_from_deliver:self.return_from_deliver=False;self.set_active(True)

    def eventFilter(self,watched,event):
        kind=event.type();w=self.w
        if watched in (w,w.timeline_panel) and kind in (QEvent.Resize,QEvent.Move):
            if not self.position_timer.isActive():self.position_timer.start(0)
        if not self.active:return False
        if watched is w and kind==QEvent.Hide:self.close_overlays()
        if kind==QEvent.ApplicationDeactivate:self.close_overlays()
        if kind in (QEvent.DragEnter,QEvent.DragMove):
            overlay=self.overlays.get('Library')
            if overlay and overlay.isVisible() and hasattr(watched,'mapToGlobal'):
                point=watched.mapToGlobal(event.position().toPoint())
                if not overlay.frameGeometry().contains(point):self.hide_overlay('Library')
            return False
        if kind==QEvent.KeyPress and event.key()==Qt.Key_Escape and not QApplication.activePopupWidget() and not QApplication.activeModalWidget():
            visible=any(o.isVisible() for o in self.overlays.values())
            if visible:self.close_overlays();return True
        if kind!=QEvent.MouseButtonPress or QApplication.activeModalWidget():return False
        point=event.globalPosition().toPoint()
        # Let a toggle handle its own click, avoiding close-then-reopen. Popup
        # menus/combos retain ownership even when they extend beyond the panel.
        for button in (w.media_toggle,w.effects_toggle,w.inspector_toggle):
            if button.isVisible() and button.rect().contains(button.mapFromGlobal(point)):return False
        if QApplication.activePopupWidget():return False
        for name,overlay in self.overlays.items():
            if overlay.isVisible() and not overlay.frameGeometry().contains(point):self.hide_overlay(name)
        return False
