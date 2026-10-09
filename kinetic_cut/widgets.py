from __future__ import annotations

import copy
import math
from .process import run as run_process
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QDrag, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTransform
from PySide6.QtWidgets import (QAbstractScrollArea, QDialog, QDialogButtonBox, QLabel,
                               QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QHBoxLayout,
                               QPushButton, QToolButton, QWidget)

from .model import Caption, Crop, Project, TimelineItem
from .icons import lucide_icon
from .image_cache import FileImageCache


TRACK_LABELS = {
    "captions": "CC  CAPTIONS", "overlay": "V4  OVERLAY", "facecam": "V3  FACE CAM",
    "main": "V2  CONTENT", "background": "V1  BACKGROUND", "sfx": "A1  SFX", "music": "A2  MUSIC",
}
TRACK_COLORS = {
    "captions": "#dfff45", "overlay": "#36b9ff", "facecam": "#ff6fb1", "main": "#735cff",
    "background": "#343841", "sfx": "#ffab4d", "music": "#31c9a2",
}


class MediaList(QListWidget):
    filesDropped = Signal(list)
    addRequested = Signal(str)
    importRequested = Signal()
    removeRequested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setIconSize(QSize(84, 48))
        self.setSpacing(2)
        self.setDragEnabled(True)

    def startDrag(self, _):
        item=self.currentItem()
        if not item:return
        media_id=str(item.data(Qt.UserRole) or "")
        mime=QMimeData(); mime.setData("application/x-kinetic-media-id",media_id.encode("utf-8"))
        drag=QDrag(self); drag.setMimeData(mime)
        if not item.icon().isNull():drag.setPixmap(item.icon().pixmap(84,48))
        drag.exec(Qt.CopyAction)

    def contextMenuEvent(self,event):
        item=self.itemAt(event.pos()); menu=QMenu(self)
        add_media=menu.addAction(lucide_icon("plus"),"Add Media…")
        add_timeline=remove=None
        if item:
            menu.addSeparator(); add_timeline=menu.addAction(lucide_icon("plus"),"Add to Timeline")
            remove=menu.addAction(lucide_icon("trash-2"),"Remove from Media Pool")
        chosen=menu.exec(event.globalPos())
        if chosen==add_media:self.importRequested.emit()
        elif item and chosen==add_timeline:self.addRequested.emit(str(item.data(Qt.UserRole)))
        elif item and chosen==remove:self.removeRequested.emit(str(item.data(Qt.UserRole)))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class PreviewCanvas(QWidget):
    transformChanged = Signal(str)
    cropRequested = Signal(str)
    itemSelected = Signal(str)
    captionSelected = Signal(str)
    captionTransformChanged = Signal(str)
    layerSelected = Signal(str)
    commandRequested = Signal(str,object)
    interactionFinished = Signal(str)

    def __init__(self):
        super().__init__()
        self.project: Project | None = None
        self.frame = QImage()
        self.frames = {}; self.active_frames = {}
        self.view_zoom=1.; self.view_pan=QPointF(); self.pan_origin=None
        self.effect_cache={}; self.crop_cache={}
        self.still_cache=FileImageCache(128*1024*1024, max_entries=16)
        self.selected_layer = "main"
        self.selected_item_id = ""
        self.selected_caption_id = ""; self.text_rects={}; self.drag_text=None
        self.tool = "select"
        self.drag_origin: QPoint | None = None
        self.drag_mode = ""
        self.drag_item: TimelineItem | None = None
        self.drag_scale = 1.0
        self.drag_scale_y = 1.0
        self.drag_distance = 1.0
        self.drag_handle: int | str | None = None
        self.transform_controls_visible = True
        self.read_only = False
        self.setMinimumSize(240, 160)
        # This canvas paints every pixel itself. Do not propagate every video
        # frame through the styled parent/backing store and repaint its siblings.
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        from .theme_widgets import palette
        self.set_theme(palette())

    def set_project(self, project: Project):
        self.effect_cache.clear(); self.crop_cache.clear()
        self.still_cache.clear()
        self.project = project
        self.update()

    def set_tool(self, tool: str):
        self.tool = tool
        self.setCursor(Qt.CrossCursor if tool == "crop" else Qt.ArrowCursor)

    def set_transform_controls_visible(self, visible: bool):
        self.transform_controls_visible = bool(visible)
        if not visible:
            self.drag_origin=None; self.drag_item=None; self.drag_text=None; self.drag_mode=""; self.drag_handle=None
        self.update()

    def set_read_only(self, value):
        self.read_only=bool(value)
        self.drag_origin=None; self.drag_item=None; self.drag_text=None; self.drag_mode=""; self.drag_handle=None
        self.setCursor(Qt.ArrowCursor); self.update()

    def select_item(self, item_id: str):
        self.selected_item_id = item_id
        if item_id:self.selected_caption_id=""
        item = self.project.item_by_id(item_id) if self.project else None
        if item:
            self.selected_layer = item.track
        self.update()

    def select_caption(self,caption_id:str):
        self.selected_caption_id=caption_id; self.selected_item_id=""; self.update()

    def set_frame(self, image: QImage):
        if not image.isNull():
            self.frame = image
            self.update()

    def composition_rect(self) -> QRectF:
        if not self.project:
            return QRectF()
        ratio = self.project.settings.width / self.project.settings.height
        available_h = max(1, self.height() - 18)
        w = min(self.width() - 18, available_h * ratio)
        h = w / ratio
        if h > available_h:
            h = available_h; w = h * ratio
        w*=self.view_zoom; h*=self.view_zoom
        return QRectF((self.width() - w) / 2+self.view_pan.x(), (self.height() - h) / 2+self.view_pan.y(), w, h)

    def reset_view(self):
        self.view_zoom=1.; self.view_pan=QPointF(); self.update()

    def wheelEvent(self,event):
        if self.pan_origin is not None or event.buttons() & Qt.MiddleButton:
            event.accept(); return
        before=self.composition_rect(); factor=1.12 if event.angleDelta().y()>0 else 1/1.12
        old=self.view_zoom; self.view_zoom=max(.15,min(8.,old*factor)); factor=self.view_zoom/old
        anchor=event.position(); center=QPointF(self.width()/2,self.height()/2)
        self.view_pan=anchor-center-(anchor-center-self.view_pan)*factor
        self.update(); event.accept()

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MiddleButton:self.reset_view()

    def _active(self, track: str) -> TimelineItem | None:
        if not self.project:
            return None
        if not self.project.track_states.get(track,{}).get("visible",True):return None
        t = self.project.playhead
        return next((i for i in reversed(self.project.timeline)
                     if i.track == track and i.start <= t < i.start + i.duration and not i.muted), None)

    def _visible_items(self) -> list[tuple[TimelineItem, QImage, QRectF]]:
        if getattr(self,'caption_focus',False):return []
        if not self.project:
            return []
        frame_rect = self.composition_rect()
        visible: list[tuple[TimelineItem, QImage, QRectF]] = []
        for track in self.project.video_tracks:
            trans = self.project.transition_at_time(track, self.project.playhead) if getattr(self.project, "transitions", None) else None
            if trans:
                p_val = trans.progress(self.project.playhead)
                chosen_id = trans.right_item_id if p_val >= 0.5 and trans.right_item_id else (trans.left_item_id or trans.right_item_id)
                item = self.project.item_by_id(chosen_id) if chosen_id else self._active(track)
            else:
                item = self._active(track)
            if not item:
                continue
            if item.role=='graphic':
                if not self.project.track_states.get(track,{}).get('visible',True):continue
                visible.append((item,QImage(),self._graphic_rect(item,frame_rect)))
                continue
            from .keyframes import evaluated
            item=evaluated(item,self.project.playhead-item.start)
            from .visual_fx import evaluate_visual_fx, apply_visual_fx_to_transform
            vfx=evaluate_visual_fx(item,self.project.playhead-item.start,self.project.settings.width,self.project.settings.height)
            if vfx.is_active:
                item=copy.copy(item); item.transform=copy.copy(item.transform)
                apply_visual_fx_to_transform(item.transform,vfx)
            media = self.project.media_by_id(item.media_id)
            image = self.still_cache.load(media.path) if media and media.kind == "image" else self.frames.get(self.active_frames.get(item.id),getattr(self,'fallback_frames',{}).get(item.id,QImage()))
            if image.isNull():
                continue
            target=frame_rect if item.role=="background" else self._layer_rect(item,image,frame_rect,item.role=="facecam")
            visible.append((item,image,target))
        return visible

    @staticmethod
    def _handles(rect: QRectF) -> list[QPoint]:
        return [rect.topLeft().toPoint(), rect.topRight().toPoint(), rect.bottomRight().toPoint(), rect.bottomLeft().toPoint()]

    @staticmethod
    def _source_crop(image: QImage, crop: Crop) -> QImage:
        return image.copy(PreviewCanvas._source_rect(image, crop))

    @staticmethod
    def _source_rect(image: QImage, crop: Crop) -> QRect:
        c = crop.clamped()
        rect = QRect(round(c.x * image.width()), round(c.y * image.height()),
                     max(1, round(c.width * image.width())), max(1, round(c.height * image.height())))
        return rect.intersected(image.rect())

    @staticmethod
    def _has_pixel_effects(item):
        from .preview_raster import RasterContext
        return RasterContext._has_pixel_effects(item)

    def _layer_rect(self, item: TimelineItem, source: QImage, frame_rect: QRectF,
                    is_face: bool = False) -> QRectF:
        if source.isNull():
            return QRectF()
        media = self.project.media_by_id(item.media_id)
        crop = item.crop.clamped()
        full_w = max(1.0, media.width if media and media.width else source.width())
        full_h = max(1.0, media.height if media and media.height else source.height())
        source_w = full_w * crop.width
        source_h = full_h * crop.height
        width_factor = .92 if is_face else 1.0
        factor=frame_rect.width()/self.project.settings.width
        # Resolve-style input scaling fills the output without distorting the
        # source, while Inspector Zoom remains 1.000. Cropping then removes
        # pixels from that stable base geometry instead of re-fitting the crop.
        input_scale=max(self.project.settings.width/full_w,self.project.settings.height/full_h)
        w = source_w * input_scale * factor * width_factor * item.transform.scale
        h = source_h * input_scale * factor * width_factor * item.transform.effective_scale_y
        ax=item.transform.anchor_x*(item.transform.scale-1)*factor; ay=item.transform.anchor_y*(item.transform.effective_scale_y-1)*factor
        if item.retain_image_position:
            c=item.crop.clamped(); ax-=(c.x+c.width/2-.5)*w/c.width; ay-=(c.y+c.height/2-.5)*h/c.height
        return QRectF(frame_rect.x() + item.transform.x * frame_rect.width() - w / 2-ax,
                      frame_rect.y() + item.transform.y * frame_rect.height() - h / 2-ay, w, h)

    def _graphic_rect(self,item,frame_rect):
        from PySide6.QtGui import QPicture
        from .graphics import draw_graphic
        unrotated=copy.copy(item); unrotated.transform=copy.copy(item.transform); unrotated.transform.rotation=0
        picture=QPicture(); painter=QPainter(picture)
        try:return draw_graphic(painter,self.project,unrotated,frame_rect,self.project.playhead)
        finally:painter.end()

    def _transform_geometry(self, item: TimelineItem, target: QRectF):
        factor = self.composition_rect().width() / max(1, self.project.settings.width)
        anchor = target.center() + QPointF(item.transform.anchor_x * factor, item.transform.anchor_y * factor)
        if item.role=='graphic':
            frame=self.composition_rect()
            anchor=QPointF(frame.left()+item.transform.x*frame.width()+item.transform.anchor_x*factor,
                           frame.top()+item.transform.y*frame.height()+item.transform.anchor_y*factor)
        transform = QTransform()
        transform.translate(anchor.x(), anchor.y())
        transform.rotate(item.transform.rotation)
        transform.translate(-anchor.x(), -anchor.y())
        corners = [transform.map(point) for point in
                   (target.topLeft(), target.topRight(), target.bottomRight(), target.bottomLeft())]
        sides = [transform.map(point) for point in
                 (QPointF(target.center().x(), target.top()), QPointF(target.right(), target.center().y()),
                  QPointF(target.center().x(), target.bottom()), QPointF(target.left(), target.center().y()))]
        handle_distance = max(36.0, min(96.0, target.height() * .34))
        rotation_handle = transform.map(anchor + QPointF(0, -handle_distance))
        return anchor, corners, sides, rotation_handle, handle_distance

    def _draw_transform_box(self,painter,item,target):
        anchor,corners,sides,rotation_handle,rotation_radius=self._transform_geometry(item,target)
        painter.setPen(QPen(QColor("#dadde4"), 1))
        painter.setBrush(Qt.NoBrush); painter.drawPolygon(QPolygonF(corners))
        for index,corner in enumerate(corners):
            active=self.drag_item is item and self.drag_mode=="scale" and self.drag_handle==index
            painter.setPen(QPen(QColor("#3d8cff"), 1)); painter.setBrush(QColor("#3d8cff") if active else QColor("#f5f6fa"))
            painter.drawRect(QRectF(corner.x()-5, corner.y()-5, 10, 10))
        for index,side in enumerate(sides):
            active=self.drag_item is item and self.drag_mode in {"scale_x","scale_y"} and self.drag_handle==f"side-{index}"
            painter.setPen(QPen(QColor("#3d8cff"),1)); painter.setBrush(QColor("#3d8cff") if active else QColor("#f4f6f8")); painter.drawEllipse(side,4,4)
        if self.drag_item is item and self.drag_mode=="rotate":
            painter.setPen(QPen(QColor(221,225,232,175),1)); painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(anchor,rotation_radius,rotation_radius)
        painter.setPen(QPen(QColor("#d9dde5"),1)); painter.drawLine(anchor,rotation_handle)
        active_anchor=self.drag_item is item and self.drag_mode=="anchor"
        painter.setPen(QPen(QColor("#3d8cff"),2)); painter.setBrush(QColor("#3d8cff") if active_anchor else QColor("#f5f6fa")); painter.drawEllipse(anchor,6,6)
        active_rotation=self.drag_item is item and self.drag_mode=="rotate"
        painter.setBrush(QColor("#3d8cff") if active_rotation else QColor("#f5f6fa")); painter.drawEllipse(rotation_handle,5,5)
        # Thin shapes can overlap grips; keep the pressed corner visibly active.
        if self.drag_item is item and self.drag_mode=='scale' and isinstance(self.drag_handle,int):
            corner=corners[self.drag_handle]
            painter.setPen(QPen(QColor('#3d8cff'),1)); painter.setBrush(QColor('#3d8cff'))
            painter.drawRect(QRectF(corner.x()-5,corner.y()-5,10,10))

    def _prepare_layer_image(self, item: TimelineItem, layer_source: QImage, target: QRectF, frame_rect: QRectF) -> QImage:
        from .preview_raster import RasterContext, prepare_layer_image
        transport=getattr(self.window(),'transport',None)
        context=RasterContext(self.project, bool(transport and (transport.playing or transport.scrubbing)),
                              self.devicePixelRatioF(),self.effect_cache,self.crop_cache)
        return prepare_layer_image(context,item,layer_source,target,frame_rect)

    def frame_work(self, key, image):
        """Snapshot only supported static pixel filters on the GUI thread.

        Publish their results together with the raw frame, keeping duplicate
        crops synchronized. Animated/vision/transition paths retain their
        existing time-dependent renderer, rather than using stale effect data.
        """
        from types import SimpleNamespace
        from .preview_raster import RasterContext
        from .vision_effects import active
        from .tracking_effect import active as tracking_active
        from .visual_fx import evaluate_visual_fx
        project=self.project
        if not project or getattr(self,'caption_focus',False):return None
        requests=[]; rect=self.composition_rect()
        for track in project.video_tracks:
            item=self._active(track)
            if not item or self.active_frames.get(item.id)!=key:continue
            if item.keyframes or active(item) or tracking_active(item):continue
            if project.transition_at_time(track,project.playhead):continue
            if evaluate_visual_fx(item,project.playhead-item.start,project.settings.width,project.settings.height).is_active:continue
            if item.role!='background' and not self._has_pixel_effects(item):continue
            target=rect if item.role=='background' else self._layer_rect(item,image,rect,item.role=='facecam')
            requests.append((copy.deepcopy(item),QRectF(target),QRectF(rect)))
        if not requests:return None
        # These supported filters never need media/vision lookup.
        snapshot=SimpleNamespace(settings=copy.deepcopy(project.settings),playhead=project.playhead,
                                 media_by_id=lambda media_id: None)
        return RasterContext(snapshot,True,self.devicePixelRatioF()),requests

    def _draw_layer_item(self, painter: QPainter, item: TimelineItem, layer_source: QImage, target: QRectF,
                         frame_rect: QRectF, prepared_override: QImage | None = None) -> None:
        elapsed = self.project.playhead - item.start
        fade = min(1.0, max(0.0, elapsed / item.fade_in)) if item.fade_in else 1.0
        if item.fade_out:
            fade *= min(1.0, max(0.0, (item.duration - elapsed) / item.fade_out))
        painter.save()
        painter.setClipRect(frame_rect)
        painter.setOpacity(item.opacity / 100.0 * fade)
        modes = {"Add": QPainter.CompositionMode_Plus, "Multiply": QPainter.CompositionMode_Multiply, "Screen": QPainter.CompositionMode_Screen}
        painter.setCompositionMode(modes.get(item.composite_mode, QPainter.CompositionMode_SourceOver))
        direct_crop = prepared_override is None and item.role != 'background' and not self._has_pixel_effects(item)
        prepared = (prepared_override if prepared_override is not None else
                    layer_source if direct_crop else self._prepare_layer_image(item, layer_source, target, frame_rect))
        if item.role == "background":
            if item.keyframes:
                factor = frame_rect.width() / self.project.settings.width
                center = frame_rect.topLeft() + QPointF(item.transform.x * frame_rect.width(), item.transform.y * frame_rect.height())
                center -= QPointF(item.transform.anchor_x * (item.transform.scale - 1) * factor, item.transform.anchor_y * (item.transform.effective_scale_y - 1) * factor)
                anchor = QPointF(item.transform.anchor_x * factor, item.transform.anchor_y * factor)
                painter.translate(center + anchor)
                painter.rotate(item.transform.rotation)
                painter.translate(-anchor)
                painter.scale(item.transform.scale, item.transform.effective_scale_y)
                painter.translate(-frame_rect.center())
            painter.drawImage(frame_rect, prepared)
        else:
            factor = frame_rect.width() / self.project.settings.width
            pivot = target.center() + QPointF(item.transform.anchor_x * factor, item.transform.anchor_y * factor)
            painter.save()
            painter.setClipRect(frame_rect)
            painter.translate(pivot)
            painter.rotate(item.transform.rotation)
            painter.translate(target.center() - pivot)
            transform = QTransform()
            transform.rotate(item.transform.pitch, Qt.XAxis)
            transform.rotate(item.transform.yaw, Qt.YAxis)
            painter.setTransform(transform, True)
            local_target = QRectF(-target.width() / 2, -target.height() / 2, target.width(), target.height())
            if item.transform.shape == "circle":
                clip = QPainterPath()
                clip.addEllipse(local_target)
                painter.setClipPath(clip, Qt.IntersectClip)
            painter.scale(-1 if item.transform.flip_horizontal else 1, -1 if item.transform.flip_vertical else 1)
            if direct_crop:
                painter.drawImage(local_target, prepared, QRectF(self._source_rect(prepared,item.crop)))
            else:
                painter.drawImage(local_target, prepared)
            painter.restore()
        painter.restore()

    def _draw_layer_transition(self, painter: QPainter, track: str, trans, frame_rect: QRectF) -> None:
        from .transitions import composite_transition
        from .missing_media import unavailable
        item_a = self.project.item_by_id(trans.left_item_id) if trans.left_item_id else None
        item_b = self.project.item_by_id(trans.right_item_id) if trans.right_item_id else None
        if item_a and unavailable(self.project.media_by_id(item_a.media_id),item_a):item_a=None
        if item_b and unavailable(self.project.media_by_id(item_b.media_id),item_b):item_b=None

        from .native_animation import required,frame as native_frame
        if any(i and required(i) for i in (item_a,item_b)):
            def raster(item):
                if not item:return None
                t=min(item.duration-1/self.project.settings.fps,max(0,self.project.playhead-item.start))
                if required(item):return native_frame(self.project,item,max(0,t),(max(2,round(frame_rect.width())),max(2,round(frame_rect.height()))))
                from .keyframes import evaluated
                item=evaluated(item,max(0,t)); media=self.project.media_by_id(item.media_id)
                raw=self.still_cache.load(media.path) if media and media.kind=='image' else self.frames.get(self.active_frames.get(item.id),getattr(self,'fallback_frames',{}).get(item.id,QImage()))
                if raw.isNull():return None
                image=QImage(max(2,round(frame_rect.width())),max(2,round(frame_rect.height())),QImage.Format_RGBA8888); image.fill(Qt.transparent)
                p=QPainter(image); p.setRenderHints(QPainter.Antialiasing|QPainter.SmoothPixmapTransform); rect=QRectF(0,0,image.width(),image.height())
                try:self._draw_layer_item(p,item,raw,rect if item.role=='background' else self._layer_rect(item,raw,rect),rect)
                finally:p.end()
                return image
            painter.save(); painter.setClipRect(frame_rect)
            try:composite_transition(painter,frame_rect,raster(item_a),raster(item_b),trans,trans.progress(self.project.playhead))
            finally:painter.restore()
            return

        img_a = None
        target_a = None
        if item_a:
            from .keyframes import evaluated
            elapsed_a = min(item_a.duration, max(0.0, self.project.playhead - item_a.start))
            item_a = evaluated(item_a, elapsed_a)
            from .visual_fx import evaluate_visual_fx, apply_visual_fx_to_transform
            vfx_a = evaluate_visual_fx(item_a, elapsed_a, self.project.settings.width, self.project.settings.height)
            if vfx_a.is_active:
                item_a = copy.copy(item_a)
                item_a.transform = copy.copy(item_a.transform)
                apply_visual_fx_to_transform(item_a.transform, vfx_a)
            media_a = self.project.media_by_id(item_a.media_id)
            raw_a = self.still_cache.load(media_a.path) if media_a and media_a.kind == "image" else self.frames.get(self.active_frames.get(item_a.id), getattr(self, "fallback_frames", {}).get(item_a.id, QImage()))
            if not raw_a.isNull():
                target_a = frame_rect if item_a.role == "background" else self._layer_rect(item_a, raw_a, frame_rect, item_a.role == "facecam")
                img_a = self._prepare_layer_image(item_a, raw_a, target_a, frame_rect)

        img_b = None
        target_b = None
        if item_b:
            from .keyframes import evaluated
            elapsed_b = max(0.0, min(item_b.duration, self.project.playhead - item_b.start))
            item_b = evaluated(item_b, elapsed_b)
            from .visual_fx import evaluate_visual_fx, apply_visual_fx_to_transform
            vfx_b = evaluate_visual_fx(item_b, elapsed_b, self.project.settings.width, self.project.settings.height)
            if vfx_b.is_active:
                item_b = copy.copy(item_b)
                item_b.transform = copy.copy(item_b.transform)
                apply_visual_fx_to_transform(item_b.transform, vfx_b)
            media_b = self.project.media_by_id(item_b.media_id)
            raw_b = self.still_cache.load(media_b.path) if media_b and media_b.kind == "image" else self.frames.get(self.active_frames.get(item_b.id), getattr(self, "fallback_frames", {}).get(item_b.id, QImage()))
            if not raw_b.isNull():
                target_b = frame_rect if item_b.role == "background" else self._layer_rect(item_b, raw_b, frame_rect, item_b.role == "facecam")
                img_b = self._prepare_layer_image(item_b, raw_b, target_b, frame_rect)

        if not img_a and not img_b:
            return

        raw_p = trans.progress(self.project.playhead)
        p = raw_p

        ref_item = item_a if (item_a and (p < 0.5 or not item_b)) else (item_b or item_a)
        if not ref_item:
            return

        if target_a and target_b and target_a != target_b:
            target = QRectF(
                target_a.x() * (1.0 - p) + target_b.x() * p,
                target_a.y() * (1.0 - p) + target_b.y() * p,
                target_a.width() * (1.0 - p) + target_b.width() * p,
                target_a.height() * (1.0 - p) + target_b.height() * p,
            )
        else:
            target = target_a or target_b or frame_rect

        if ref_item.role == "background":
            painter.save()
            painter.setClipRect(frame_rect)
            composite_transition(painter, frame_rect, img_a, img_b, trans, raw_p)
            painter.restore()
        else:
            factor = frame_rect.width() / self.project.settings.width

            rot_a = item_a.transform.rotation if item_a else ref_item.transform.rotation
            rot_b = item_b.transform.rotation if item_b else ref_item.transform.rotation
            rot = rot_a * (1.0 - p) + rot_b * p

            anc_xa = item_a.transform.anchor_x if item_a else ref_item.transform.anchor_x
            anc_xb = item_b.transform.anchor_x if item_b else ref_item.transform.anchor_x
            anchor_x = anc_xa * (1.0 - p) + anc_xb * p

            anc_ya = item_a.transform.anchor_y if item_a else ref_item.transform.anchor_y
            anc_yb = item_b.transform.anchor_y if item_b else ref_item.transform.anchor_y
            anchor_y = anc_ya * (1.0 - p) + anc_yb * p

            pivot = target.center() + QPointF(anchor_x * factor, anchor_y * factor)

            painter.save()
            painter.setClipRect(frame_rect)

            opacity_a = item_a.opacity if item_a else 100.0
            opacity_b = item_b.opacity if item_b else 100.0
            painter.setOpacity((opacity_a * (1.0 - p) + opacity_b * p) / 100.0)

            modes = {"Add": QPainter.CompositionMode_Plus, "Multiply": QPainter.CompositionMode_Multiply, "Screen": QPainter.CompositionMode_Screen}
            painter.setCompositionMode(modes.get(ref_item.composite_mode, QPainter.CompositionMode_SourceOver))

            painter.translate(pivot)
            painter.rotate(rot)
            painter.translate(target.center() - pivot)

            transform = QTransform()
            pitch_a = item_a.transform.pitch if item_a else ref_item.transform.pitch
            pitch_b = item_b.transform.pitch if item_b else ref_item.transform.pitch
            yaw_a = item_a.transform.yaw if item_a else ref_item.transform.yaw
            yaw_b = item_b.transform.yaw if item_b else ref_item.transform.yaw
            transform.rotate(pitch_a * (1.0 - p) + pitch_b * p, Qt.XAxis)
            transform.rotate(yaw_a * (1.0 - p) + yaw_b * p, Qt.YAxis)
            painter.setTransform(transform, True)

            local_target = QRectF(-target.width() / 2, -target.height() / 2, target.width(), target.height())

            if ref_item.transform.shape == "circle":
                clip = QPainterPath()
                clip.addEllipse(local_target)
                painter.setClipPath(clip, Qt.IntersectClip)

            painter.scale(-1 if ref_item.transform.flip_horizontal else 1, -1 if ref_item.transform.flip_vertical else 1)

            painter.setClipRect(local_target, Qt.IntersectClip)

            composite_transition(painter, local_target, img_a, img_b, trans, raw_p)
            painter.restore()

    def set_theme(self, palette: dict):
        self._viewer_bg = palette.get("viewer_bg", "#191a1d")
        self._border_col = palette.get("border", "#000000")
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        viewer_bg = getattr(self, "_viewer_bg", None)
        if not viewer_bg:
            from .theme import get_active_theme_palette
            viewer_bg = get_active_theme_palette().get("viewer_bg", "#191a1d")
        painter.fillRect(self.rect(), QColor(viewer_bg))
        frame_rect = self.composition_rect()
        # The output raster is black, exactly like the exporter. This makes
        # letterboxing/pillarboxing in the program monitor truthful instead of
        # borrowing the surrounding dark-grey application chrome.
        border_col = getattr(self, "_border_col", None)
        if not border_col:
            from .theme import get_active_theme_palette
            border_col = get_active_theme_palette().get("border", "#000000")
        painter.setPen(QPen(QColor(border_col), 1))
        painter.setBrush(QColor("#000000"))
        painter.drawRect(frame_rect)
        if not self.project:
            return
        if getattr(self,'caption_focus',False):
            from .caption_focus import paint
            paint(self,painter,frame_rect); return
        if not self.project.timeline and not self.project.captions:
            painter.save(); painter.setClipRect(frame_rect,Qt.IntersectClip)
            center=frame_rect.center(); width=max(20,frame_rect.width()-20); text_size=max(8,min(11,frame_rect.width()/20)); icon_size=round(min(32,width/4))
            painter.drawPixmap(round(center.x()-icon_size/2),round(center.y()-80),lucide_icon("image-plus","@on_dark",icon_size).pixmap(icon_size,icon_size))
            painter.setPen(QColor("#c1cbd8")); painter.setFont(QFont("Segoe UI",round(text_size),QFont.DemiBold))
            painter.drawText(QRectF(center.x()-width/2,center.y()-40,width,55),Qt.AlignCenter|Qt.TextWordWrap,"Your next clip starts here")
            painter.setPen(QColor("#8190a3")); painter.setFont(QFont("Segoe UI",max(8,round(text_size-1))))
            painter.drawText(QRectF(center.x()-width/2,center.y()+20,width,65),Qt.AlignCenter|Qt.TextWordWrap,"Import media, then drag it onto the timeline\nCtrl+I")
            painter.restore()
            return
        source = self.frame; self.text_rects={}; overlay=None; vision_notice=''
        for track in self.project.video_tracks:
            if not self.project.track_states.get(track, {}).get("visible", True):
                continue
            trans = self.project.transition_at_time(track, self.project.playhead) if getattr(self.project, "transitions", None) else None
            if trans:
                self._draw_layer_transition(painter, track, trans, frame_rect)
                p_val = trans.progress(self.project.playhead)
                chosen_id = trans.right_item_id if p_val >= 0.5 and trans.right_item_id else (trans.left_item_id or trans.right_item_id)
                if chosen_id == self.selected_item_id and self.transform_controls_visible:
                    item_sel = self.project.item_by_id(chosen_id)
                    if item_sel and not item_sel.keyframes:
                        media_sel = self.project.media_by_id(item_sel.media_id)
                        img_sel = self.still_cache.load(media_sel.path) if media_sel and media_sel.kind == "image" else self.frames.get(self.active_frames.get(item_sel.id), getattr(self, "fallback_frames", {}).get(item_sel.id, QImage()))
                        t_sel = frame_rect if item_sel.role == "background" else self._layer_rect(item_sel, img_sel, frame_rect, item_sel.role == "facecam")
                        overlay = (item_sel, t_sel)
            else:
                item = self._active(track)
                if not item:
                    continue
                from .native_animation import required,draw_title
                if required(item):
                    from .graphics import draw_graphic
                    bounds=(draw_title(painter,self.project,item,frame_rect,self.project.playhead) if item.role=='title' else draw_graphic(painter,self.project,item,frame_rect,self.project.playhead))
                    if bounds:self.text_rects[(item.role,item.id)]=bounds
                    if bounds and item.role=='graphic' and item.id==self.selected_item_id and not item.keyframes:overlay=(item,self._graphic_rect(item,frame_rect))
                    continue
                from .keyframes import evaluated
                item = evaluated(item, self.project.playhead - item.start)
                from .visual_fx import evaluate_visual_fx, apply_visual_fx_to_transform
                vfx = evaluate_visual_fx(item, self.project.playhead - item.start, self.project.settings.width, self.project.settings.height)
                if vfx.is_active:
                    item = copy.copy(item); item.transform = copy.copy(item.transform)
                    apply_visual_fx_to_transform(item.transform, vfx)
                media = self.project.media_by_id(item.media_id)
                from .missing_media import unavailable
                if unavailable(media,item):continue
                image = self.still_cache.load(media.path) if media and media.kind == "image" else self.frames.get(self.active_frames.get(item.id), getattr(self, 'fallback_frames', {}).get(item.id, QImage()))
                if image.isNull():
                    continue
                target = frame_rect if item.role == "background" else self._layer_rect(item, image, frame_rect, item.role == "facecam")
                from .vision_effects import status as vision_status
                notice = vision_status(item, media, item.source_time(self.project.playhead))
                from .tracking_effect import status as tracking_status
                notice = tracking_status(item, media, item.source_time(self.project.playhead)) or notice
                if notice:
                    vision_notice = notice
                self._draw_layer_item(painter, item, image, target, frame_rect)
                if item.id == self.selected_item_id and self.transform_controls_visible and not item.keyframes:
                    overlay = (item, target)
        from .visuals import draw_caption
        for item in self.project.timeline:
            if item.role!="title" or item.track not in self.project.video_tracks or item.muted or not self.project.track_states.get(item.track,{}).get("visible",True) or not item.start<=self.project.playhead<item.start+item.duration:continue
            from .native_animation import required
            if required(item):continue
            from .native_animation import draw_title
            bounds=draw_title(painter,self.project,item,frame_rect,self.project.playhead); self.text_rects[("title",item.id)]=bounds
        from .graphics import draw_graphic
        for item in self.project.timeline:
            if item.role!="graphic" or item.track not in self.project.video_tracks or item.muted or not self.project.track_states.get(item.track,{}).get("visible",True) or not item.start<=self.project.playhead<item.start+item.duration:continue
            from .native_animation import required
            if required(item):continue
            bounds=draw_graphic(painter,self.project,item,frame_rect,self.project.playhead)
            if bounds:self.text_rects[("graphic",item.id)]=bounds
            if bounds and item.id==self.selected_item_id and not item.keyframes:
                overlay=(item,self._graphic_rect(item,frame_rect))
        for caption in sorted(self.project.captions, key=lambda c: c.start):
            if not self.project.track_states.get("subtitle_1",{}).get("visible",True) or not (caption.start <= self.project.playhead < caption.end):
                continue
            bounds=draw_caption(painter,self.project,caption,frame_rect); self.text_rects[("caption",caption.id)]=bounds
        if self.transform_controls_visible:
            if overlay:self._draw_transform_box(painter,*overlay)
            selected=self.text_rects.get(("title",self.selected_item_id)) or self.text_rects.get(("caption",self.selected_caption_id))
            if selected:self._draw_text_box(painter,selected)
        if vision_notice:
            painter.setPen(QColor('#ffdd88')); painter.setFont(QFont('Segoe UI',9)); painter.drawText(self.rect().adjusted(12,8,-12,-8),Qt.AlignBottom|Qt.AlignHCenter,vision_notice)
        win = self.window()
        transport = getattr(win, "transport", None)
        is_paused = transport is None or not getattr(transport, "playing", False)
        inspector = getattr(win, "inspector", None)
        inspector_toggle = getattr(win, "inspector_toggle", None)
        inspector_open = (inspector_toggle is None or inspector_toggle.isChecked())
        tabs = getattr(inspector, "tabs", None)
        effects_tab_active = (tabs is None) or (tabs.tabText(tabs.currentIndex()) == "Effects")
        timeline = getattr(win, "timeline", None)
        timeline_selected = (self.selected_item_id in getattr(timeline, "selected_ids", {self.selected_item_id})) if timeline else bool(self.selected_item_id)

        if is_paused and inspector_open and effects_tab_active and timeline_selected and self.selected_item_id:
            sel_item=self.project.item_by_id(self.selected_item_id)
            if sel_item and getattr(sel_item,"effects",None):
                vfx_fx=next((e for e in sel_item.effects if e.get("category")=="Visual FX" and e.get("enabled",True) and ("center_x" in e or "ken_burns_start_x" in e)),None)
                if vfx_fx:
                    fx=float(vfx_fx.get("center_x",vfx_fx.get("ken_burns_start_x",0.5)))
                    fy=float(vfx_fx.get("center_y",vfx_fx.get("ken_burns_start_y",0.5)))
                    cx=frame_rect.left()+fx*frame_rect.width(); cy=frame_rect.top()+fy*frame_rect.height()
                    painter.save(); painter.setRenderHint(QPainter.Antialiasing)
                    painter.setPen(QPen(QColor(61,140,255,180),1.5,Qt.DashLine)); painter.setBrush(QColor(61,140,255,25))
                    painter.drawEllipse(QPointF(cx,cy),16,16)
                    painter.setPen(QPen(QColor("#3d8cff"),1.5))
                    painter.drawLine(QPointF(cx-8,cy),QPointF(cx+8,cy))
                    painter.drawLine(QPointF(cx,cy-8),QPointF(cx,cy+8))
                    painter.restore()
        from pathlib import Path
        pending=next((self.project.media_by_id(i.media_id) for i in self.project.timeline if i.start<=self.project.playhead<i.start+i.duration and self.project.media_by_id(i.media_id) and self.project.media_by_id(i.media_id).compound and not Path(self.project.media_by_id(i.media_id).path).is_file()),None)
        if pending:
            message='Compound preview unavailable — right-click clip to retry' if pending.path in getattr(self,'compound_failures',set()) else 'Compound preview is preparing · '+pending.name
            painter.setPen(QColor('#ffdd88')); painter.setFont(QFont('Segoe UI',9)); painter.drawText(frame_rect.adjusted(8,8,-8,-8),Qt.AlignBottom|Qt.AlignHCenter|Qt.TextWordWrap,message)

    def _draw_text_box(self,painter,rect):
        painter.save(); painter.setPen(QPen(QColor("#50df74"),2)); painter.setBrush(Qt.NoBrush); painter.drawRect(rect)
        for index,point in enumerate(self._handles(rect)):
            active=self.drag_mode in {'headline_scale','title_scale'} and self.drag_handle==index
            painter.setBrush(QColor("#3d8cff") if active else QColor("#f5f6fa")); painter.setPen(QPen(QColor("#3d8cff") if active else QColor("#50df74"),1)); painter.drawRect(QRectF(point.x()-4,point.y()-4,8,8))
        painter.restore()
    def mousePressEvent(self, event):
        if event.button()==Qt.MiddleButton:
            self.pan_origin=event.position(); self.setCursor(Qt.ClosedHandCursor); return
        if event.button() != Qt.LeftButton or not self.project or self.read_only:
            return
        point = event.position()
        selected_title=self.project.item_by_id(self.selected_item_id)
        title_rect=self.text_rects.get(('title',self.selected_item_id))
        if (self.transform_controls_visible and selected_title and selected_title.role=='title'
                and title_rect
                and not self.project.track_states.get(selected_title.track,{}).get('locked')):
            nearby=[((point-QPointF(handle)).manhattanLength(),index) for index,handle in enumerate(self._handles(title_rect))]
            closest=min((entry for entry in nearby if entry[0]<=12),default=None)
            handle_index=closest[1] if closest else None
            if handle_index is not None:
                self.drag_handle=handle_index; self.setCursor(Qt.ArrowCursor)
                self.drag_text=('title',selected_title.id,selected_title.title_style)
                headline=selected_title.title_style.box_style=='headline'
                self.drag_mode='headline_scale' if headline else 'title_scale'; self.drag_origin=point.toPoint()
                self.drag_position=title_rect.center(); self.drag_scale=selected_title.title_style.zoom_x if headline else selected_title.title_style.size
                self.drag_distance=max(1.,math.hypot(point.x()-self.drag_position.x(),point.y()-self.drag_position.y()))
                self.update()
                return
        text_hit=next(((kind,item_id,rect) for (kind,item_id),rect in reversed(list(self.text_rects.items())) if kind!='graphic' and rect.adjusted(-5,-5,5,5).contains(point)),None)
        if text_hit:
            kind,item_id,_=text_hit
            if kind=="title":
                candidate=self.project.item_by_id(item_id)
                if candidate and self.project.track_states.get(candidate.track,{}).get('locked'):return
                item=self.project.item_by_id(item_id); self.selected_item_id=item_id; self.selected_caption_id=""; self.itemSelected.emit(item_id); style=item.title_style if item else None
            elif kind=="graphic":
                item=self.project.item_by_id(item_id); self.selected_item_id=item_id; self.selected_caption_id=""; self.itemSelected.emit(item_id)
                if item and self.transform_controls_visible:
                    self.drag_text=(kind,item_id,item.transform); self.drag_mode="graphic_move"; self.drag_origin=point.toPoint(); self.drag_position=(item.transform.x,item.transform.y)
                self.update(); return
            else:
                caption=next((c for c in self.project.captions if c.id==item_id),None); self.selected_caption_id=item_id; self.selected_item_id=""; self.captionSelected.emit(item_id); style=self.project.caption_style(caption) if caption else None
                owner=self.window()
                if caption and hasattr(owner,'timeline') and len(owner.timeline.selected_caption_ids)>1 and not caption.customize:
                    import copy
                    caption.style=copy.deepcopy(style); caption.customize=True; style=caption.style
            if style:
                if self.transform_controls_visible:
                    self.drag_text=(kind,item_id,style); self.drag_mode="text_move"; self.drag_origin=point.toPoint(); self.drag_position=(style.position_x,style.position_y)
                self.update(); return
        visible = self._visible_items()
        selected = next(((i, image, rect) for i, image, rect in visible if i.id == self.selected_item_id), None)
        if selected and selected[0].keyframes:selected=None
        if selected and self.transform_controls_visible:
            anchor,corners,sides,rotation_handle,_=self._transform_geometry(selected[0],selected[2])
            # Thin graphics can put a side grip inside another grip's hit radius.
            # The closest visible grip wins, rather than the first broad radius.
            grips=[((point-rotation_handle).manhattanLength(),16,'rotate','rotation'),
                   ((point-anchor).manhattanLength(),18,'anchor','anchor')]
            grips += [((point-h).manhattanLength(),14,'scale',n) for n,h in enumerate(corners)]
            grips += [((point-h).manhattanLength(),12,mode,f'side-{n}') for n,(h,mode) in enumerate(zip(sides,('scale_y','scale_x','scale_y','scale_x')))]
            nearest=min((g for g in grips if g[0]<=g[1]),key=lambda g:g[0],default=None)
            grip=(nearest[2],nearest[3]) if nearest else None
            if grip==('rotate','rotation'):
                self.drag_item=selected[0]; self.drag_mode="rotate"; self.drag_origin=point.toPoint(); self.drag_handle="rotation"; self.update(); return
            if grip==('anchor','anchor'):
                self.drag_item=selected[0]; self.drag_mode="anchor"; self.drag_origin=point.toPoint(); self.drag_anchor=(selected[0].transform.anchor_x,selected[0].transform.anchor_y); self.drag_handle="anchor"; self.update(); return
            for index,handle in enumerate(corners):
                if grip==('scale',index):
                    self.drag_item = selected[0]; self.drag_mode = "scale"; self.drag_origin = point.toPoint()
                    self.drag_handle = index
                    self.setCursor(Qt.ArrowCursor); self.update()
                    self.drag_scale = selected[0].transform.scale
                    self.drag_scale_y = selected[0].transform.effective_scale_y
                    self.drag_distance = max(1.0, math.hypot(point.x()-selected[2].center().x(), point.y()-selected[2].center().y()))
                    return
            side_modes=("scale_y","scale_x","scale_y","scale_x")
            for index,(handle,mode) in enumerate(zip(sides,side_modes)):
                if grip==(mode,f'side-{index}'):
                    self.setCursor(Qt.ArrowCursor)
                    angle=math.radians(-selected[0].transform.rotation); dx=point.x()-anchor.x(); dy=point.y()-anchor.y()
                    local_x=math.cos(angle)*dx-math.sin(angle)*dy; local_y=math.sin(angle)*dx+math.cos(angle)*dy
                    self.drag_item=selected[0]; self.drag_mode=mode; self.drag_handle=f"side-{index}"; self.drag_origin=point.toPoint(); self.drag_scale=selected[0].transform.scale; self.drag_scale_y=selected[0].transform.effective_scale_y; self.drag_distance=max(1,abs(local_x) if mode=="scale_x" else abs(local_y)); self.update(); return
        hit = next(((i,image,rect) for i,image,rect in reversed(visible)
                    if QPolygonF(self._transform_geometry(i,rect)[1]).containsPoint(point,Qt.OddEvenFill)),None)
        if not hit:
            return
        item = hit[0]
        self.selected_item_id = item.id; self.selected_layer = item.track
        self.itemSelected.emit(item.id); self.layerSelected.emit(item.track); self.update()
        if item.keyframes:
            owner=self.window()
            if hasattr(owner,'statusBar'):owner.statusBar().showMessage('Use Manage Keyframes to edit this animated clip’s transform.',4000)
            return
        if self.tool == "crop" and item.track in self.project.video_tracks:
            self.cropRequested.emit(item.id)
            return
        if not self.transform_controls_visible:
            return
        self.drag_item = item; self.drag_mode = "move"; self.drag_origin = point.toPoint()
        self.drag_position=(item.transform.x,item.transform.y)

    def mouseMoveEvent(self, event):
        if self.pan_origin is not None:
            self.view_pan+=event.position()-self.pan_origin; self.pan_origin=event.position(); self.update(); return
        if self.read_only or not self.transform_controls_visible:
            self.setCursor(Qt.ArrowCursor); return
        if not self.drag_origin or not self.project or (not self.drag_item and not self.drag_text):
            # Hover feedback makes resize affordances discoverable.
            point = event.position()
            title=self.project.item_by_id(self.selected_item_id) if self.project else None
            title_rect=self.text_rects.get(('title',self.selected_item_id))
            if (title and title.role=='title' and title_rect
                    and not self.project.track_states.get(title.track,{}).get('locked')
                    and any((point-QPointF(handle)).manhattanLength()<=12 for handle in self._handles(title_rect))):
                self.setCursor(Qt.ArrowCursor); return
            selected = next(((item,rect) for item,_,rect in self._visible_items() if item.id == self.selected_item_id),None)
            geometry=self._transform_geometry(*selected) if selected else None
            grip=None
            if geometry:
                hover_grips=[((point-geometry[3]).manhattanLength(),16,'rotate'),
                             ((point-geometry[0]).manhattanLength(),18,'anchor')]
                hover_grips += [((point-h).manhattanLength(),14,'resize') for h in geometry[1]]
                hover_grips += [((point-h).manhattanLength(),12,'resize') for h in geometry[2]]
                nearest=min((g for g in hover_grips if g[0]<=g[1]),key=lambda g:g[0],default=None)
                grip=nearest[2] if nearest else None
            if grip=='rotate':
                self.setCursor(Qt.CrossCursor)
            elif grip=='resize':
                self.setCursor(Qt.ArrowCursor)
            elif grip=='anchor' or geometry and QPolygonF(geometry[1]).containsPoint(point,Qt.OddEvenFill):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.CrossCursor if self.tool == "crop" else Qt.ArrowCursor)
            return
        frame_rect = self.composition_rect(); point = event.position(); item = self.drag_item
        if self.drag_mode=='headline_scale' and self.drag_text:
            kind,item_id,style=self.drag_text
            distance=math.hypot(point.x()-self.drag_position.x(),point.y()-self.drag_position.y())
            style.zoom_x=style.zoom_y=min(2.5,max(.2,self.drag_scale*distance/self.drag_distance))
            self.transformChanged.emit(item_id); self.update(); return
        if self.drag_mode=='title_scale' and self.drag_text:
            kind,item_id,style=self.drag_text
            distance=math.hypot(point.x()-self.drag_position.x(),point.y()-self.drag_position.y())
            style.size=min(200,max(8,self.drag_scale*distance/self.drag_distance))
            self.transformChanged.emit(item_id); self.update(); return
        if self.drag_mode=="text_move" and self.drag_text:
            kind,item_id,style=self.drag_text; style.position_x=self.drag_position[0]+(point.x()-self.drag_origin.x())/frame_rect.width(); style.position_y=self.drag_position[1]+(point.y()-self.drag_origin.y())/frame_rect.height()
            (self.transformChanged if kind=="title" else self.captionTransformChanged).emit(item_id); self.update(); return
        if self.drag_mode=="graphic_move" and self.drag_text:
            kind,item_id,transform=self.drag_text; transform.x=self.drag_position[0]+(point.x()-self.drag_origin.x())/frame_rect.width(); transform.y=self.drag_position[1]+(point.y()-self.drag_origin.y())/frame_rect.height()
            self.transformChanged.emit(item_id); self.update(); return
        if self.drag_mode == "move":
            item.transform.x=self.drag_position[0]+(point.x()-self.drag_origin.x())/frame_rect.width()
            item.transform.y=self.drag_position[1]+(point.y()-self.drag_origin.y())/frame_rect.height()
        elif self.drag_mode=="anchor":
            factor=max(.0001,frame_rect.width()/self.project.settings.width)
            item.transform.anchor_x=self.drag_anchor[0]+(point.x()-self.drag_origin.x())/factor; item.transform.anchor_y=self.drag_anchor[1]+(point.y()-self.drag_origin.y())/factor
        elif self.drag_mode=="rotate":
            visible_rect=next((rect for candidate,_,rect in self._visible_items() if candidate.id==item.id),None)
            if visible_rect:
                anchor=self._transform_geometry(item,visible_rect)[0]
                angle=math.degrees(math.atan2(point.y()-anchor.y(),point.x()-anchor.x()))+90
                item.transform.rotation=((angle+180)%360)-180
        elif self.drag_mode == "scale":
            visible_rect = next((rect for candidate, _, rect in self._visible_items() if candidate.id == item.id), None)
            if visible_rect:
                distance = math.hypot(point.x()-visible_rect.center().x(), point.y()-visible_rect.center().y())
                factor=distance/self.drag_distance; item.transform.scale=min(4,max(.05,self.drag_scale*factor)); item.transform.scale_y=min(4,max(.05,self.drag_scale_y*factor))
        elif self.drag_mode in {"scale_x","scale_y"}:
            visible_rect=next((rect for candidate,_,rect in self._visible_items() if candidate.id==item.id),None)
            if visible_rect:
                anchor=self._transform_geometry(item,visible_rect)[0]; angle=math.radians(-item.transform.rotation); dx=point.x()-anchor.x(); dy=point.y()-anchor.y()
                local_x=math.cos(angle)*dx-math.sin(angle)*dy; local_y=math.sin(angle)*dx+math.cos(angle)*dy
                distance=abs(local_x) if self.drag_mode=="scale_x" else abs(local_y); factor=distance/self.drag_distance
                if self.drag_mode=="scale_x":
                    if item.transform.scale_y is None:item.transform.scale_y=self.drag_scale_y
                    item.transform.scale=min(4,max(.05,self.drag_scale*factor))
                else:item.transform.scale_y=min(4,max(.05,self.drag_scale_y*factor))
        self.transformChanged.emit(item.id); self.update()

    def mouseReleaseEvent(self, _):
        if self.pan_origin is not None:self.pan_origin=None; self.setCursor(Qt.ArrowCursor); return
        if self.drag_item:self.interactionFinished.emit(self.drag_item.id)
        if self.drag_text:self.interactionFinished.emit(self.drag_text[1])
        self.drag_origin = None
        self.drag_item = None
        self.drag_text = None
        self.drag_mode = ""
        self.drag_handle = None
        self.update()

    def contextMenuEvent(self,event):
        if not self.project or self.read_only:return
        hit=next(((item,rect) for item,_,rect in reversed(self._visible_items())
                  if QPolygonF(self._transform_geometry(item,rect)[1]).containsPoint(QPointF(event.pos()),Qt.OddEvenFill)),None)
        item=hit[0] if hit else self.project.item_by_id(self.selected_item_id)
        menu=QMenu(self)
        if not item:
            menu.addAction("No layer at playhead").setEnabled(False); menu.exec(event.globalPos()); return
        self.selected_item_id=item.id; self.itemSelected.emit(item.id)
        transform=menu.addAction(lucide_icon("mouse-pointer-2"),"Transform"); crop=menu.addAction(lucide_icon("crop"),"Crop Source…")
        menu.addSeparator(); fit=menu.addAction("Fit to Output Frame"); flip_h=menu.addAction(lucide_icon("flip-horizontal-2"),"Flip Horizontal"); flip_v=menu.addAction(lucide_icon("flip-vertical-2"),"Flip Vertical"); reset=menu.addAction(lucide_icon("rotate-cw"),"Reset Transform")
        menu.addSeparator(); top=menu.addAction("Position to top")
        webcam=menu.addAction("Mark as webcam"); webcam.setCheckable(True); webcam.setChecked(item.is_webcam)
        below=menu.addAction("Position below webcam")
        below.setEnabled(any(i.id!=item.id and i.is_webcam for i,_,_ in self._visible_items()))
        chosen=menu.exec(event.globalPos())
        if chosen==transform:self.set_tool("select")
        elif chosen==crop:self.commandRequested.emit("crop",item.id)
        elif chosen==fit:self.commandRequested.emit("fit",item.id)
        elif chosen==flip_h:self.commandRequested.emit("flip_h",item.id)
        elif chosen==flip_v:self.commandRequested.emit("flip_v",item.id)
        elif chosen==reset:self.commandRequested.emit("reset",item.id)
        elif chosen==top:self.commandRequested.emit("position_top",item.id)
        elif chosen==webcam:self.commandRequested.emit("mark_webcam",item.id)
        elif chosen==below:self.commandRequested.emit("below_webcam",item.id)


class TimelineWidget(QAbstractScrollArea):
    itemSelected=Signal(str); trackSelected=Signal(str); playheadChanged=Signal(float); itemChanged=Signal(str)
    mediaDropped=Signal(str,str,float); commandRequested=Signal(str,object); bladeRequested=Signal(str,float)
    zoomChanged=Signal(float)
    LABEL_WIDTH=180; RULER_HEIGHT=32; VIDEO_GAP=26; TRACK_HEIGHT=39; AV_SEPARATOR=8

    def __init__(self):
        super().__init__(); self.project:Project|None=None; self.pixels_per_second=45.0
        self.selected_id=""; self.selected_track="video_1"; self.drag_mode=""; self.tool="select"
        self.waveforms:dict[str,list[float]]={}; self.drag_start=QPoint(); self.original=(0.0,0.0,0.0)
        self.drag_original_track=""
        self.setMinimumHeight(270); self.setMouseTracking(True); self.setAcceptDrops(True); self.viewport().setAcceptDrops(True); self.viewport().installEventFilter(self)
        self.viewport().setContextMenuPolicy(Qt.CustomContextMenu); self.viewport().customContextMenuRequested.connect(self._viewport_context_menu)
        self.setProperty("snapping",True)
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update); self.verticalScrollBar().valueChanged.connect(self.viewport().update)

    def tracks(self)->list[str]:
        if not self.project:return []
        return [*reversed(self.project.video_tracks),*self.project.audio_tracks]

    def set_tool(self,tool:str):self.tool=tool; self.viewport().setCursor(Qt.CrossCursor if tool=="blade" else Qt.ArrowCursor)
    def set_zoom(self,value:float,anchor_x:float|None=None):
        anchor_x=self.viewport().width()/2 if anchor_x is None else anchor_x; anchor=self.time_for_x(anchor_x); self.pixels_per_second=float(min(240,max(.6,value))); self._range(); self.horizontalScrollBar().setValue(round(anchor*self.pixels_per_second-anchor_x+self.LABEL_WIDTH)); self.viewport().update(); self.zoomChanged.emit(self.pixels_per_second)
    def set_project(self,project:Project):
        self.project=project; project.ensure_track_model()
        if self.selected_track not in self.tracks():self.selected_track=project.video_tracks[0]
        self._range(); self.viewport().update()
    def resizeEvent(self,event):
        super().resizeEvent(event); self._range()
    def _state(self,track:str)->dict:
        return self.project.track_states.setdefault(track,{"visible":True,"locked":False,"muted":False})
    def _range(self):
        duration=max(20,(self.project.duration if self.project else 0)+5)
        self.horizontalScrollBar().setRange(0,max(0,round(duration*self.pixels_per_second-self.viewport().width()+self.LABEL_WIDTH)))
        self.horizontalScrollBar().setPageStep(max(1,self.viewport().width()-self.LABEL_WIDTH))
        track_count=len(self.tracks()); content=self.VIDEO_GAP+track_count*self.TRACK_HEIGHT+self.AV_SEPARATOR
        available=max(1,self.viewport().height()-self.RULER_HEIGHT); self.verticalScrollBar().setRange(0,max(0,content-available)); self.verticalScrollBar().setPageStep(available)
    def x_for_time(self,value:float)->float:return self.LABEL_WIDTH+value*self.pixels_per_second-self.horizontalScrollBar().value()
    def time_for_x(self,x:float)->float:return max(0,(x-self.LABEL_WIDTH+self.horizontalScrollBar().value())/self.pixels_per_second)
    def _audio_top(self)->float:return self.RULER_HEIGHT+self.VIDEO_GAP+len(self.project.video_tracks)*self.TRACK_HEIGHT+self.AV_SEPARATOR-self.verticalScrollBar().value()
    def track_rect(self,track:str)->QRectF:
        if track in self.project.video_tracks:
            visual=list(reversed(self.project.video_tracks)); y=self.RULER_HEIGHT+self.VIDEO_GAP+visual.index(track)*self.TRACK_HEIGHT-self.verticalScrollBar().value()
        else:y=self._audio_top()+self.project.audio_tracks.index(track)*self.TRACK_HEIGHT
        return QRectF(0,y,self.viewport().width(),self.TRACK_HEIGHT)
    def track_at(self,pos)->str:
        return next((track for track in self.tracks() if self.track_rect(track).contains(pos)),"")
    def item_rect(self,item:TimelineItem)->QRectF:
        tr=self.track_rect(item.track); return QRectF(self.x_for_time(item.start),tr.y()+3,max(5,item.duration*self.pixels_per_second),tr.height()-6)
    def set_waveform(self,media_id:str,values:list[float]):self.waveforms[media_id]=values; self.viewport().update()
    def _track_label(self,track:str)->tuple[str,str]:
        if track in self.project.video_tracks:return f"V{self.project.video_tracks.index(track)+1}",self.project.track_names.get(track,"Video")
        return f"A{self.project.audio_tracks.index(track)+1}",self.project.track_names.get(track,"Audio")

    def paintEvent(self,_):
        p=QPainter(self.viewport()); p.setRenderHint(QPainter.Antialiasing); p.fillRect(self.viewport().rect(),QColor("#0e1115"))
        p.fillRect(QRect(0,0,self.LABEL_WIDTH,self.viewport().height()),QColor("#171a20")); p.fillRect(QRect(self.LABEL_WIDTH,0,self.viewport().width()-self.LABEL_WIDTH,self.RULER_HEIGHT),QColor("#14171c"))
        if not self.project:return
        duration=max(20,self.project.duration+5); step=1 if self.pixels_per_second>=35 else 5
        p.setFont(QFont("Cascadia Mono",8)); p.setPen(QColor("#626975"))
        for second in range(0,math.ceil(duration)+1,step):
            x=self.x_for_time(second)
            if self.LABEL_WIDTH<=x<=self.viewport().width():p.drawLine(round(x),22,round(x),self.viewport().height()); p.drawText(round(x)+4,15,f"{second//60:02d}:{second%60:02d}")
        p.save(); p.setClipRect(QRectF(0,self.RULER_HEIGHT,self.viewport().width(),self.viewport().height()-self.RULER_HEIGHT))
        # A deliberate empty band above the highest video track is both drop target and add-track context area.
        gap_y=self.RULER_HEIGHT-self.verticalScrollBar().value(); p.fillRect(QRectF(0,gap_y,self.viewport().width(),self.VIDEO_GAP),QColor("#11141a"))
        for caption in self.project.captions:
            rect=QRectF(self.x_for_time(caption.start),gap_y+5,max(7,(caption.end-caption.start)*self.pixels_per_second),self.VIDEO_GAP-10)
            p.setPen(Qt.NoPen); p.setBrush(QColor("#d9ff43")); p.drawRoundedRect(rect,3,3)
        p.fillRect(QRectF(0,self._audio_top()-self.AV_SEPARATOR,self.viewport().width(),self.AV_SEPARATOR),QColor("#080a0d"))
        p.setPen(QPen(QColor("#454c57"),1)); p.drawLine(0,round(self._audio_top()-self.AV_SEPARATOR/2),self.viewport().width(),round(self._audio_top()-self.AV_SEPARATOR/2))
        for index,track in enumerate(self.tracks()):
            rect=self.track_rect(track); selected=track==self.selected_track; is_audio=track in self.project.audio_tracks
            p.fillRect(rect,QColor("#101419" if index%2 else "#12161b")); p.fillRect(QRectF(0,rect.y(),self.LABEL_WIDTH,rect.height()),QColor("#252a32" if selected else "#1a1e24"))
            p.fillRect(QRectF(0,rect.y(),3,rect.height()),QColor("#43bd81" if is_audio else "#5296d5"))
            code,name=self._track_label(track); p.setPen(QColor("#f1f2f4" if selected else "#b4b9c2")); p.setFont(QFont("Segoe UI",8,QFont.DemiBold))
            p.drawText(QRectF(10,rect.y(),30,rect.height()),Qt.AlignCenter,code); p.drawText(QRectF(44,rect.y(),83,rect.height()),Qt.AlignVCenter,name)
            state=self._state(track); eye=lucide_icon("eye" if state.get("visible",True) else "eye-off","#9299a5",14).pixmap(14,14); lock=lucide_icon("lock","#d9ff43" if state.get("locked",False) else "#5a626e",14).pixmap(14,14)
            p.drawPixmap(QRectF(137,rect.center().y()-7,14,14).toRect(),eye); p.drawPixmap(QRectF(158,rect.center().y()-7,14,14).toRect(),lock)
            p.setPen(QColor("#252a31")); p.drawLine(0,round(rect.bottom()),self.viewport().width(),round(rect.bottom()))
        order=self.tracks()
        for item in sorted((i for i in self.project.timeline if i.track in order),key=lambda i:(order.index(i.track),i.start)):
            rect=self.item_rect(item)
            if rect.right()<self.LABEL_WIDTH or rect.left()>self.viewport().width():continue
            is_audio=item.track in self.project.audio_tracks; color=QColor("#3f986b" if is_audio else "#3f78a8")
            if item.role=="background":color=QColor("#3a4049")
            elif item.role=="facecam":color=QColor("#a54f79")
            color.setAlpha(235 if item.id==self.selected_id else 195); p.setBrush(color); p.setPen(QPen(color.lighter(145),2 if item.id==self.selected_id else 1)); p.drawRect(rect)
            media=self.project.media_by_id(item.media_id); samples=self.waveforms.get(item.media_id,[])
            if samples and rect.width()>18 and is_audio:
                from .waveforms import paint_waveform
                p.save(); p.setClipRect(rect.adjusted(1,1,-1,-1))
                paint_waveform(p,rect,samples,media,item,self.pixels_per_second,self.LABEL_WIDTH,self.viewport().width()); p.restore()
            p.setPen(QColor("#f5f7f8")); p.setFont(QFont("Segoe UI",8,QFont.DemiBold)); p.drawText(rect.adjusted(7,0,-6,0),Qt.AlignVCenter|Qt.TextSingleLine,media.name if media else "Offline media")
        p.restore(); x=self.x_for_time(self.project.playhead); p.setPen(QPen(QColor("#ff4d62"),2)); p.drawLine(round(x),0,round(x),self.viewport().height()); path=QPainterPath(); path.moveTo(x-6,0); path.lineTo(x+6,0); path.lineTo(x,8); path.closeSubpath(); p.fillPath(path,QColor("#ff4d62"))

    def mousePressEvent(self,event):
        if not self.project or event.button()!=Qt.LeftButton:return
        pos=event.position()
        if pos.y()<self.RULER_HEIGHT or abs(pos.x()-self.x_for_time(self.project.playhead))<7:
            self.drag_mode="playhead"; self.project.playhead=self.time_for_x(pos.x()); self.playheadChanged.emit(self.project.playhead); self.viewport().update(); return
        track=self.track_at(pos)
        if pos.x()<self.LABEL_WIDTH and track:
            self.selected_track=track; self.trackSelected.emit(track); state=self._state(track)
            if pos.x()>=154:state["locked"]=not state.get("locked",False)
            elif pos.x()>=132:
                state["visible"]=not state.get("visible",True)
                for item in self.project.timeline:
                    if item.track==track:item.muted=not state["visible"]
            self.viewport().update(); return
        hit=next((i for i in reversed(self.project.timeline) if i.track in self.tracks() and self.item_rect(i).contains(pos)),None)
        if hit and pos.x()>=self.LABEL_WIDTH:
            self.selected_track=hit.track; self.selected_id=hit.id; self.itemSelected.emit(hit.id)
            if self.tool=="blade":self.bladeRequested.emit(hit.id,self.time_for_x(pos.x())); return
            rect=self.item_rect(hit); edge=7; locked=self._state(hit.track).get("locked",False)
            self.drag_mode="" if locked else "trim_left" if pos.x()-rect.left()<edge else "trim_right" if rect.right()-pos.x()<edge else "move"; self.drag_start=pos.toPoint(); self.original=(hit.start,hit.duration,hit.in_point); self.drag_original_track=hit.track
        else:
            self.selected_id=""; self.selected_track=track or self.selected_track
            if track:self.trackSelected.emit(track)
            self.drag_mode="playhead"; self.project.playhead=self.time_for_x(pos.x()); self.playheadChanged.emit(self.project.playhead)
        self.viewport().update()
    def mouseMoveEvent(self,event):
        if not self.project or not self.drag_mode:return
        if self.drag_mode=="playhead":self.project.playhead=min(max(self.project.duration,0),self.time_for_x(event.position().x())); self.playheadChanged.emit(self.project.playhead); self.viewport().update(); return
        item=self.project.item_by_id(self.selected_id)
        if not item:return
        delta=(event.position().x()-self.drag_start.x())/self.pixels_per_second; start,duration,in_point=self.original
        if self.drag_mode=="move":
            candidate=max(0,start+delta)
            if self.property("snapping"):
                points=[0.0]+[value for other in self.project.timeline if other.id!=item.id for value in (other.start,other.start+other.duration)]
                nearest=min(points,key=lambda value:abs(value-candidate)); candidate=nearest if abs(nearest-candidate)<=8/self.pixels_per_second else candidate
            item.start=candidate; target=self.track_at(event.position())
            same_kind=(target in self.project.video_tracks)==(self.drag_original_track in self.project.video_tracks)
            if target and same_kind and not self._state(target).get("locked",False):item.track=target; self.selected_track=target
        elif self.drag_mode=="trim_left":change=max(-in_point,min(duration-.05,delta)); item.start=start+change; item.duration=duration-change; item.in_point=in_point+change
        else:item.duration=max(.05,duration+delta)
        self._range(); self.viewport().update()
    def mouseReleaseEvent(self,_):
        if self.selected_id and self.drag_mode not in {"","playhead"}:self.itemChanged.emit(self.selected_id)
        self.drag_mode=""
    def wheelEvent(self,event):
        if event.modifiers()&Qt.ControlModifier:
            self.set_zoom(self.pixels_per_second*(1.15 if event.angleDelta().y()>0 else .87),event.position().x())
        elif self.verticalScrollBar().maximum()>0 and not event.modifiers()&Qt.ShiftModifier:self.verticalScrollBar().setValue(self.verticalScrollBar().value()-event.angleDelta().y()); event.accept()
        else:self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()+(-event.angleDelta().y() if event.angleDelta().y() else -event.angleDelta().x())); event.accept()
    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat("application/x-kinetic-media-id"):event.acceptProposedAction()
    def dragMoveEvent(self,event):
        if event.mimeData().hasFormat("application/x-kinetic-media-id"):event.acceptProposedAction()
    def dropEvent(self,event):
        if not self.project:return
        media_id=bytes(event.mimeData().data("application/x-kinetic-media-id")).decode("utf-8"); track=self.track_at(event.position())
        media=self.project.media_by_id(media_id)
        if not track:track=self.project.audio_tracks[0] if media and media.kind=="audio" else self.project.video_tracks[-1]
        self.mediaDropped.emit(media_id,track,self.time_for_x(event.position().x())); event.acceptProposedAction()
    def eventFilter(self,watched,event):
        if watched is self.viewport() and event.type()==QEvent.DragLeave:self.dragLeaveEvent(event); return True
        if watched is self.viewport() and event.type() in {QEvent.DragEnter,QEvent.DragMove,QEvent.Drop}:
            if event.type()==QEvent.DragEnter:self.dragEnterEvent(event)
            elif event.type()==QEvent.DragMove:self.dragMoveEvent(event)
            elif event.type()==QEvent.Drop:self.dropEvent(event)
            # Our MIME was fully handled, including rejection (e.g. a locked
            # lane). Do not dispatch it a second time through Qt's model drops.
            return True
        return super().eventFilter(watched,event)
    def _viewport_context_menu(self,pos):
        event=QContextMenuEvent(QContextMenuEvent.Mouse,pos,self.viewport().mapToGlobal(pos)); self.contextMenuEvent(event)
    def contextMenuEvent(self,event):
        if not self.project:return
        pos=event.pos(); track=self.track_at(pos); hit=next((i for i in reversed(self.project.timeline) if i.track in self.tracks() and (self.visible_item_rect(i) if hasattr(self,"visible_item_rect") else self.item_rect(i)).contains(pos)),None); menu=QMenu(self)
        if hit and pos.x()>=self.LABEL_WIDTH:
            split=menu.addAction(lucide_icon("scissors"),"Split Clip"); lift=menu.addAction(lucide_icon("trash-2"),"Lift"); ripple=menu.addAction(lucide_icon("magnet"),"Ripple Delete"); menu.addSeparator(); move=menu.addMenu("Move Clip to Track")
            destinations=[]
            for destination in (self.project.audio_tracks if hit.track in self.project.audio_tracks else self.project.video_tracks):destinations.append((move.addAction(self._track_label(destination)[0]+"  "+self.project.track_names[destination]),destination))
            chosen=menu.exec(event.globalPos())
            if chosen==split:self.commandRequested.emit("split",hit.id)
            elif chosen==lift:self.commandRequested.emit("lift",hit.id)
            elif chosen==ripple:self.commandRequested.emit("ripple",hit.id)
            else:
                destination=next((value for action,value in destinations if chosen==action),"")
                if destination:self.commandRequested.emit("move_clip",(hit.id,destination))
            return
        if pos.x()>=self.LABEL_WIDTH and hasattr(self,"add_clipboard_actions"):self.add_clipboard_actions(menu,False)
        add_video=menu.addAction("Add Video Track"); add_audio=menu.addAction("Add Audio Track")
        duplicate=menu.addAction("Duplicate Layer") if track in self.project.video_tracks+self.project.audio_tracks else None
        if track:
            menu.addSeparator(); up=menu.addAction("Move Track Up"); down=menu.addAction("Move Track Down"); rename=menu.addAction("Rename Track…"); delete=menu.addAction(lucide_icon("trash-2"),"Delete Track")
        else:up=down=rename=delete=None
        menu.addSeparator(); empty=menu.addAction("Delete Empty Tracks"); chosen=menu.exec(event.globalPos())
        if chosen is None:return
        if chosen==add_video:self.commandRequested.emit("add_video",track)
        elif chosen==add_audio:self.commandRequested.emit("add_audio",None)
        elif duplicate is not None and chosen==duplicate:self.commandRequested.emit("duplicate_track",track)
        elif chosen==up:self.commandRequested.emit("move_track_up",track)
        elif chosen==down:self.commandRequested.emit("move_track_down",track)
        elif chosen==rename:self.commandRequested.emit("rename_track",track)
        elif chosen==delete:self.commandRequested.emit("delete_track",track)
        elif chosen==empty:self.commandRequested.emit("delete_empty_tracks",None)


class CropCanvas(QWidget):
    cropChanged = Signal(object)

    def __init__(self, image: QImage, crop: Crop):
        super().__init__(); self.image=image; self.crop=Crop(**crop.__dict__); self.origin=None; self.pan_origin=None
        self.view_zoom=1.; self.view_pan=QPointF(); self.mode=""; self.original=Crop(**crop.__dict__); self.handle=""
        self.setMinimumSize(720,405); self.setMouseTracking(True); self.setFocusPolicy(Qt.StrongFocus)

    def image_rect(self) -> QRectF:
        size=self.image.size(); size.scale(self.size()-QSize(24,24), Qt.KeepAspectRatio)
        width=size.width()*self.view_zoom; height=size.height()*self.view_zoom
        return QRectF((self.width()-width)/2+self.view_pan.x(),(self.height()-height)/2+self.view_pan.y(),width,height)

    def selection_rect(self):
        r=self.image_rect(); c=self.crop.clamped(); return QRectF(r.x()+c.x*r.width(),r.y()+c.y*r.height(),c.width*r.width(),c.height*r.height())

    def handles(self):
        s=self.selection_rect(); return {"tl":s.topLeft(),"t":QPointF(s.center().x(),s.top()),"tr":s.topRight(),"r":QPointF(s.right(),s.center().y()),"br":s.bottomRight(),"b":QPointF(s.center().x(),s.bottom()),"bl":s.bottomLeft(),"l":QPointF(s.left(),s.center().y())}

    def reset_view(self):self.view_zoom=1.; self.view_pan=QPointF(); self.update()

    def wheelEvent(self,event):
        old=self.view_zoom; self.view_zoom=max(.2,min(12.,old*(1.15 if event.angleDelta().y()>0 else 1/1.15)))
        factor=self.view_zoom/old; anchor=event.position(); center=QPointF(self.width()/2,self.height()/2)
        self.view_pan=anchor-center-(anchor-center-self.view_pan)*factor; self.update(); event.accept()

    def paintEvent(self, _):
        p=QPainter(self); p.fillRect(self.rect(),QColor("#090a0d")); rect=self.image_rect(); p.drawImage(rect,self.image)
        selection=self.selection_rect(); shade=QColor(0,0,0,150)
        p.fillRect(QRectF(rect.left(),rect.top(),rect.width(),max(0,selection.top()-rect.top())),shade)
        p.fillRect(QRectF(rect.left(),selection.bottom(),rect.width(),max(0,rect.bottom()-selection.bottom())),shade)
        p.fillRect(QRectF(rect.left(),selection.top(),max(0,selection.left()-rect.left()),selection.height()),shade)
        p.fillRect(QRectF(selection.right(),selection.top(),max(0,rect.right()-selection.right()),selection.height()),shade)
        p.setPen(QPen(QColor("#e87361"),2)); p.setBrush(Qt.NoBrush); p.drawRect(selection)
        for point in self.handles().values():p.setBrush(QColor("#f4f5f7")); p.setPen(QPen(QColor("#e87361"),1)); p.drawRect(QRectF(point.x()-5,point.y()-5,10,10))
        p.setPen(QColor("#fff")); p.drawText(selection.adjusted(8,8,-8,-8),Qt.AlignTop|Qt.AlignLeft,f"CROP  {self.crop.width*100:.1f}% × {self.crop.height*100:.1f}%")

    def mousePressEvent(self,event):
        if event.button()==Qt.MiddleButton:self.pan_origin=event.position(); self.setCursor(Qt.ClosedHandCursor); return
        if event.button()!=Qt.LeftButton or not self.image_rect().contains(event.position()):return
        point=event.position(); self.original=Crop(**self.crop.__dict__); self.origin=point
        self.handle=next((name for name,pos in self.handles().items() if (point-pos).manhattanLength()<14),"")
        full=self.crop.x<.001 and self.crop.y<.001 and self.crop.width>.998 and self.crop.height>.998
        self.mode="resize" if self.handle else "draw" if full or event.modifiers()&Qt.ShiftModifier or not self.selection_rect().contains(point) else "move"
    def mouseMoveEvent(self,event):
        if self.pan_origin is not None:self.view_pan+=event.position()-self.pan_origin; self.pan_origin=event.position(); self.update(); return
        if self.origin is None:return
        r=self.image_rect(); point=event.position(); dx=(point.x()-self.origin.x())/r.width(); dy=(point.y()-self.origin.y())/r.height(); c=Crop(**self.original.__dict__)
        if self.mode=="draw":
            a=QPointF(max(r.left(),min(r.right(),self.origin.x())),max(r.top(),min(r.bottom(),self.origin.y()))); b=QPointF(max(r.left(),min(r.right(),point.x())),max(r.top(),min(r.bottom(),point.y())))
            s=QRectF(a,b).normalized(); c=Crop((s.left()-r.left())/r.width(),(s.top()-r.top())/r.height(),s.width()/r.width(),s.height()/r.height())
        elif self.mode=="move":c.x+=dx; c.y+=dy; c.x=max(0,min(1-c.width,c.x)); c.y=max(0,min(1-c.height,c.y))
        else:
            left,top,right,bottom=c.x,c.y,c.x+c.width,c.y+c.height
            if "l" in self.handle:left=max(0,min(right-.005,left+dx))
            if "r" in self.handle:right=min(1,max(left+.005,right+dx))
            if "t" in self.handle:top=max(0,min(bottom-.005,top+dy))
            if "b" in self.handle:bottom=min(1,max(top+.005,bottom+dy))
            c=Crop(left,top,right-left,bottom-top)
        self.crop=c.clamped(); self.cropChanged.emit(self.crop); self.update()
    def mouseReleaseEvent(self,_):
        if self.pan_origin is not None:self.pan_origin=None; self.setCursor(Qt.ArrowCursor); return
        if self.origin is not None:self.cropChanged.emit(self.crop)
        self.origin=None; self.mode=""; self.handle=""

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MiddleButton:self.reset_view()


class CropDialog(QDialog):
    def __init__(self, image: QImage, crop: Crop, label: str, parent=None):
        super().__init__(parent); self.setWindowTitle(f"Frame source · {label}"); self.resize(860,580)
        layout=QVBoxLayout(self); head=QHBoxLayout(); title=QLabel(f"Draw, move or resize the <b>{label}</b> source region. Wheel zooms · middle drag pans."); head.addWidget(title); head.addStretch()
        fit=QPushButton("Fit"); reset=QPushButton("Reset Crop"); head.addWidget(fit); head.addWidget(reset); layout.addLayout(head)
        self.canvas=CropCanvas(image,crop); layout.addWidget(self.canvas,1)
        fit.clicked.connect(self.canvas.reset_view); reset.clicked.connect(lambda:(setattr(self.canvas,"crop",Crop()),self.canvas.cropChanged.emit(self.canvas.crop),self.canvas.update()))
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Save); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    @property
    def crop(self): return self.canvas.crop

    def set_image(self,image:QImage):
        if image and not image.isNull():self.canvas.image=image; self.canvas.update()


def extract_frame(path: str, at: float, ffmpeg: str = "ffmpeg") -> QImage:
    result=run_process([ffmpeg,"-hide_banner","-loglevel","error","-ss",f"{at:.4f}","-i",path,"-frames:v","1","-f","image2pipe","-vcodec","png","-"],capture_output=True)
    image=QImage(); image.loadFromData(result.stdout,"PNG"); return image
