"""Isolated threaded Qt scene-graph surfaces; QWidget remains the input owner.

QQuickWidget deliberately is not used: it disables Qt's threaded render loop.
Images supplied here are immutable prepared assets, never video readbacks.
"""
import os
import sys
import threading
from PySide6.QtCore import QObject, QEvent, QUrl, Qt, QPointF, QTimer
from PySide6.QtGui import QImage, QMouseEvent, QWheelEvent, QColor, QRegion, QPainter
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtQuick import QQuickView, QQuickItem, QQuickImageProvider,QQuickGraphicsConfiguration
from PySide6.QtQml import QQmlComponent


def enabled():
    return (sys.platform == 'win32' and os.environ.get('KINETIC_GPU_PREVIEW','1') != '0'
            and QApplication.platformName() not in ('offscreen','minimal'))


class Images(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.lock=threading.Lock(); self.images={}
    def requestImage(self,identifier,size,requestedSize):
        with self.lock:image=QImage(self.images.get(identifier.split('?')[0],QImage()))
        if size is not None:size.setWidth(image.width());size.setHeight(image.height())
        return image
    def put(self,key,image):
        with self.lock:self.images[str(key)]=QImage(image)
    def remove(self,key):
        with self.lock:self.images.pop(str(key),None)


class RendererContainer(QObject):
    """Child-only window adapter; never creates a second top-level QWidget."""
    def __init__(self,view):
        super().__init__();self.view=view;self.rect=None
    def setGeometry(self,rect):self.rect=rect;self.view.resize(rect.size())
    def geometry(self):return self.rect
    def isVisible(self):return self.view.isVisible()
    def show(self):self.view.show()
    def hide(self):self.view.hide()
    def setCursor(self,cursor):self.view.setCursor(cursor)
    def deleteLater(self):self.view.deleteLater();super().deleteLater()


class Surface(QObject):
    def __init__(self,owner,qml,viewport=None):
        super().__init__(owner)
        from .icons import resource_path
        self.owner=owner;self.viewport=viewport or owner;self.closed=False
        self.view=QQuickView();self.view.setResizeMode(QQuickView.SizeRootObjectToView)
        # DWM handles final window composition. Never make the editor GUI wait
        # for a preview swapchain's refresh interval during scene sync.
        presentation=self.view.format();presentation.setSwapInterval(0);self.view.setFormat(presentation)
        # Native child windows may be exposed before their first scene-graph
        # frame. Match the surface background rather than flashing the default
        # black clear colour over an incompletely laid-out editor.
        self.view.setColor(QColor('#191a1e'))
        graphics=QQuickGraphicsConfiguration();graphics.setTimestamps(True);self.view.setGraphicsConfiguration(graphics)
        self.images=Images();self.view.engine().addImageProvider('prepared',self.images)
        self.view.setSource(QUrl.fromLocalFile(str(resource_path('assets','qml',qml))))
        if self.view.status()==QQuickView.Error:
            raise RuntimeError('\n'.join(e.toString() for e in self.view.errors()))
        self.root=self.view.rootObject()
        detached=bool(getattr(owner,'_gpu_renderer_child',False))
        if detached:
            self.view.setFlags(Qt.FramelessWindowHint|Qt.WindowDoesNotAcceptFocus)
            self.container=RendererContainer(self.view)
        else:
            self.container=QWidget.createWindowContainer(self.view,self.viewport)
            self.container.setFocusPolicy(Qt.NoFocus)
            self.container.setAcceptDrops(True)
        self.container.hide()
        self.container.setGeometry(self.viewport.rect())
        # Embed both surfaces through their own native containers. Qt otherwise
        # attaches a non-scroll-area preview directly to the top-level HWND,
        # behind the native ancestors created by the timeline's scroll area.
        # Establish this before first Show: a QQuickWindow grab alone cannot
        # detect that native child stacking failure.
        if not detached:
            self.container.setAttribute(Qt.WA_NativeWindow)
            self.container.winId()
        self.view.installEventFilter(self);self.viewport.installEventFilter(self);self.container.installEventFilter(self)
        self._viewport_update=None
        if self.viewport is not self.owner:
            self._viewport_update=self.viewport.update
            def request_update(*args):
                if not self.closed and getattr(self,'timer',None) is not None:self.schedule()
                self._viewport_update(*args)
            self.viewport.update=request_update
        self.components={};self.offset=QPointF();self.frames=0
        self.view.frameSwapped.connect(self._swapped,Qt.QueuedConnection)
        from .qt_native import LIB,RenderTiming
        self.timing=RenderTiming(self.view) if LIB else None
        self._expose_pending=False
    def _swapped(self):self.frames+=1
    def item(self,name):return self.root.findChild(QQuickItem,name)
    @staticmethod
    def properties(obj,values):
        cached=getattr(obj,'_published_properties',None)
        if cached is None:cached={};obj._published_properties=cached
        for name,value in values.items():
            if name not in cached or cached[name]!=value:
                obj.setProperty(name,value);cached[name]=value
    def create(self,name,parent=None):
        from .icons import resource_path
        component=self.components.get(name)
        if component is None:
            component=QQmlComponent(self.view.engine(),QUrl.fromLocalFile(str(resource_path('assets','qml',name))))
            self.components[name]=component
        item=component.create()
        if item is None:raise RuntimeError('\n'.join(e.toString() for e in component.errors()))
        item.setParent(self.root);item.setParentItem(parent or self.root)
        return item
    def geometry(self,rect):
        self.offset=QPointF(rect.topLeft());self.container.setGeometry(rect)
        if not self.container.isVisible() and self.viewport.isVisible() and not self._expose_pending:
            self._expose_pending=True;QTimer.singleShot(0,self._expose)
    def paint_underlay(self,event,color):
        region=event.region() if event is not None else QRegion(self.viewport.rect())
        if self.frames and self.container.isVisible():region=region.subtracted(QRegion(self.container.geometry()))
        if region.isEmpty():return
        painter=QPainter(self.viewport)
        try:painter.setClipRegion(region);painter.fillRect(self.viewport.rect(),QColor(color))
        finally:painter.end()
    def _expose(self):
        self._expose_pending=False
        if not self.closed and self.viewport.isVisible() and not getattr(self.owner,'caption_focus',False):
            color=self.root.property('color')
            if isinstance(color,QColor):self.view.setColor(color)
            self.container.show();self.view.update()
    def eventFilter(self,watched,event):
        if self.closed:return False
        kind=event.type()
        if watched is self.viewport and kind in (QEvent.Resize,QEvent.Show):
            # Native children can completely occlude QWidget paint events.
            # Geometry/scene publication must not depend on such a paint.
            if getattr(self,'timer',None) is not None:self.schedule()
            self.owner.update();return False
        if watched not in (self.view,self.container):return False
        if kind==QEvent.Leave:
            self.owner.leaveEvent(event);return False
        if kind in (QEvent.MouseButtonPress,QEvent.MouseButtonRelease,QEvent.MouseButtonDblClick,QEvent.MouseMove):
            forwarded=QMouseEvent(kind,event.position()+self.offset,event.globalPosition(),event.button(),event.buttons(),event.modifiers(),event.pointingDevice())
            # Call the original handlers, preserving all selection/trim/snap/undo
            # algorithms. Sending through QObject would re-enter viewport filters.
            method={QEvent.MouseButtonPress:'mousePressEvent',QEvent.MouseButtonRelease:'mouseReleaseEvent',
                    QEvent.MouseButtonDblClick:'mouseDoubleClickEvent',QEvent.MouseMove:'mouseMoveEvent'}[kind]
            if kind==QEvent.MouseButtonPress:self.owner.setFocus(Qt.MouseFocusReason)
            getattr(self.owner,method)(forwarded)
            if kind==QEvent.MouseButtonPress:
                self._mouse_context_position=None
            if kind==QEvent.MouseButtonRelease and event.button()==Qt.RightButton:
                # QQuickWindow does not synthesize QWidget context-menu events.
                # Route the release through the original editor menu handler.
                from PySide6.QtGui import QContextMenuEvent
                self._mouse_context_position=event.globalPosition().toPoint()
                context=QContextMenuEvent(QContextMenuEvent.Mouse,forwarded.position().toPoint(),
                                          self._mouse_context_position,event.modifiers())
                self.owner.contextMenuEvent(context)
            self.container.setCursor(self.viewport.cursor());event.setAccepted(forwarded.isAccepted());return True
        if kind==QEvent.Wheel:
            forwarded=QWheelEvent(event.position()+self.offset,event.globalPosition(),event.pixelDelta(),event.angleDelta(),event.buttons(),event.modifiers(),event.phase(),event.inverted(),event.source(),event.pointingDevice())
            self.owner.wheelEvent(forwarded);event.setAccepted(forwarded.isAccepted());return True
        if kind in (QEvent.KeyPress,QEvent.KeyRelease):
            QApplication.sendEvent(self.owner,event);return event.isAccepted()
        if kind==QEvent.ContextMenu:
            from PySide6.QtGui import QContextMenuEvent
            if event.reason()==QContextMenuEvent.Mouse and event.globalPos()==getattr(self,'_mouse_context_position',None):
                self._mouse_context_position=None
                return True
            forwarded=QContextMenuEvent(event.reason(),event.pos()+self.offset.toPoint(),event.globalPos(),event.modifiers())
            self.owner.contextMenuEvent(forwarded);return True
        # Drag events retain their original mime data/action. Their coordinates
        # are translated through a copy because the content surface excludes headers.
        if kind in (QEvent.DragEnter,QEvent.DragMove,QEvent.Drop,QEvent.DragLeave):
            from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDropEvent
            if kind==QEvent.DragLeave:self.owner.dragLeaveEvent(event);return True
            cls={QEvent.DragEnter:QDragEnterEvent,QEvent.DragMove:QDragMoveEvent,QEvent.Drop:QDropEvent}[kind]
            pos=event.position()+self.offset
            forwarded=cls(pos if kind==QEvent.Drop else pos.toPoint(),event.possibleActions(),event.mimeData(),event.buttons(),event.modifiers())
            getattr(self.owner,{QEvent.DragEnter:'dragEnterEvent',QEvent.DragMove:'dragMoveEvent',QEvent.Drop:'dropEvent'}[kind])(forwarded)
            event.setDropAction(forwarded.dropAction());event.setAccepted(forwarded.isAccepted());return True
        return False
    def diagnostics(self):
        return dict(graphics_backend=self.view.rendererInterface().graphicsApi().name,
                    scene_graph_frames=self.frames,render_loop=os.environ.get('QSG_RENDER_LOOP','threaded'),
                    native_timing=self.timing.read() if self.timing else None)
    def close(self):
        if self.closed:return
        self.closed=True;self.view.removeEventFilter(self);self.viewport.removeEventFilter(self);self.container.removeEventFilter(self)
        if self._viewport_update is not None:self.viewport.update=self._viewport_update
        self.container.hide();self.view.releaseResources();self.container.deleteLater()
