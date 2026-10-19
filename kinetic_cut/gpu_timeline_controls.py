"""Small editing-only overlay; clip pixels/thumbnails/waves stay in the RHI.

Reuse the existing effect-duration and transition affordances so the native
surface does not remove controls or introduce a second set of hit targets.
"""
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QImage,QPainter,QColor,QPen,QRegion,QFontMetrics


def refresh(surface,area):
    t=surface.timeline;p=t.project
    signature=(p.__dict__.get('_edit_revision',0),t.viewport().size(),t.horizontalScrollBar().value(),t.pixels_per_second,
        t.video_scroll.value(),t.audio_scroll.value(),t.subtitle_scroll.value(),repr(t.section_track_heights),
        frozenset(t.selected_ids),frozenset(t.retime_ids),t.selected_id,t.selected_transition_id,t.drag_mode,
        t.tool,t.blade_hover_id,t.blade_hover_caption,t.blade_hover_time,repr(t.roll_hover),repr(t.effect_hover),
        repr(t.transition_hover),t._vfx_flash_item_id,t.provisional_track,repr(t._palette()))
    if not (t.selected_ids or t.selected_caption_ids or t.retime_ids or p.transitions
            or t.blade_hover_id or t.blade_hover_caption or t.roll_hover or t.effect_hover or t.transition_hover
            or t._vfx_flash_item_id or t.provisional_track):
        # Without editing affordances this contains only stationary dividers.
        # Navigation must not upload an otherwise empty viewport-sized image.
        signature=('dividers',t.viewport().size(),repr(t.section_track_heights),t.subtitle_extent,t.audio_extent,
                   repr(t._subtitle_divider_rect()),repr(t._av_divider_rect()),repr(t._palette()))
    if signature==getattr(surface,'_affordance_signature',None):return
    surface._affordance_signature=signature
    image=QImage(max(1,surface.view.width()),max(1,surface.view.height()),QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
    painter=QPainter(image);painter.setRenderHint(QPainter.Antialiasing)
    left=t.time_for_x(t.LABEL_WIDTH-2);right=t.time_for_x(t.viewport().width()+2)
    items=p.runtime_index.query('timeline',left,right)
    try:
        for item in items:
            selected=item.id in t.selected_ids
            retime=item.id in t.retime_ids and not t.read_only
            if not (selected or retime or item.id==t._vfx_flash_item_id or t.effect_hover and t.effect_hover[1]==item.id):continue
            rect=t.item_rect(item);section=t.section_rect(item.track)
            if not rect.intersects(section):continue
            painter.save();painter.setClipRect(section.intersected(QRectF(area)),Qt.IntersectClip)
            if retime:
                media=p.media_by_id(item.media_id)
                for box,label in ((QRectF(rect.x(),rect.top(),rect.width(),17),'×  Speed Change  '+(media.name if media else 'Offline')),
                                  (QRectF(rect.x(),rect.bottom()-21,rect.width(),21),f'{item.speed*100:g}%  ▾')):
                    painter.fillRect(box,QColor('#244157'));painter.setPen(QColor('#f4f4f4'));painter.drawText(box.adjusted(5,0,-5,0),Qt.AlignCenter,label)
            t._paint_vfx_overlays(painter,item,rect,selected)
            if item.id==t.selected_id and t.drag_mode in ('fade_in','fade_out'):
                box=QRectF(max(rect.left(),min(rect.right()-85,image.width()-90)),rect.bottom()-23,85,21)
                painter.fillRect(box,QColor('#111318'));painter.setPen(QColor('white'));painter.drawText(box,Qt.AlignCenter,f'{getattr(item,t.drag_mode):.2f} s')
            if t.effect_hover and t.effect_hover[1]==item.id:
                painter.fillRect(rect,QColor(172,181,194,115));painter.setPen(QPen(QColor('#dfe8f5'),2));painter.setBrush(Qt.NoBrush);painter.drawRoundedRect(rect.adjusted(1,1,-1,-1),3,3)
                box=rect.intersected(section).adjusted(5,3,-5,-3)
                if box.width()>60:
                    painter.fillRect(QRectF(box.left(),box.center().y()-10,box.width(),20),QColor(28,33,40,225));painter.setPen(QColor('white'));painter.drawText(box,Qt.AlignCenter,'+ '+t.effect_hover[0])
            painter.restore()
        painter.save();painter.setClipRect(QRectF(area))
        if t.tool=='blade' and t.blade_hover_time is not None:
            ids=t.expanded({t.blade_hover_id}) if t.linked_selection and t.blade_hover_id else {t.blade_hover_id}
            painter.setPen(QPen(QColor('#ff4f55'),2));x=t.x_for_time(t.blade_hover_time)
            rects=[t.item_rect(i).intersected(t.section_rect(i.track)) for i in items if i.id in ids and i.start<t.blade_hover_time<i.start+i.duration]
            rects.extend(t.caption_rect(c).intersected(t.section_rect('subtitle_1')) for c in p.runtime_index.query('captions',left,right) if c.id==t.blade_hover_caption)
            for rect in rects:
                if not rect.isEmpty():painter.drawLine(QPointF(x,rect.top()),QPointF(x,rect.bottom()))
        if t.effect_hover and t.effect_hover[2]:
            name,_,track,start=t.effect_hover;rect=t.track_rect(track);rect.setLeft(t.x_for_time(start));rect.setWidth(5*t.pixels_per_second)
            painter.save();painter.setClipRect(t.section_rect(track),Qt.IntersectClip);painter.fillRect(rect,QColor(196,181,136,90));painter.setPen(QPen(QColor('#dfd4b2'),2,Qt.DashLine));painter.setBrush(Qt.NoBrush);painter.drawRect(rect.adjusted(2,2,-2,-2));painter.drawText(rect.adjusted(8,0,-4,0),Qt.AlignVCenter,'+ '+name);painter.restore()
        t._paint_transition_overlays(painter,left,right,QRegion(image.rect()),image.width(),image.height())
        if t.roll_hover:
            a,b=t.roll_hover;rect=t.track_rect(a.track).intersected(t.section_rect(a.track));x=t.x_for_time(b.start)
            painter.save();painter.setClipRect(rect,Qt.IntersectClip);painter.fillRect(QRectF(x-4,rect.top()+3,8,max(0,rect.height()-6)),QColor(85,235,132,90));painter.setPen(QPen(QColor('#55eb84'),2))
            for delta in (-2,2):painter.drawLine(QPointF(x+delta,rect.top()+3),QPointF(x+delta,rect.bottom()-3))
            painter.restore()
        painter.restore()
        pal=t._palette()
        for rect in (t._subtitle_divider_rect(),t._av_divider_rect()):
            if not rect.isEmpty():
                painter.fillRect(rect,QColor(pal.get('timeline_divider','#0b0c0f')));painter.setPen(QColor(pal.get('border_subtle','#555860')));painter.drawLine(0,round(rect.center().y()),image.width(),round(rect.center().y()))
    finally:painter.end()
    if not hasattr(surface,'affordances'):
        surface.affordances=surface.create('GpuImage.qml');surface.affordances.setVisible(True);surface.affordances.setZ(100005)
    surface.affordances.setWidth(image.width());surface.affordances.setHeight(image.height())
    surface.images.put('affordances',image);surface._affordance_revision=getattr(surface,'_affordance_revision',0)+1
    surface.affordances.setProperty('source',f'image://prepared/affordances?v={surface._affordance_revision}')
