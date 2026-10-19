"""Retain the editor's existing ruler, clock and pointed cursor pixels.

Only these small UI textures use the original painter. Clip/video composition
remains native; navigation never rebuilds a full timeline raster.
"""
import math
from collections import OrderedDict
from fractions import Fraction
from types import SimpleNamespace
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QFont, QColor, QRegion


def image_for(timeline,width,height,draw):
    ratio=timeline.devicePixelRatioF()
    image=QImage(max(1,math.ceil(width*ratio)),max(1,math.ceil(height*ratio)),QImage.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio);image.fill(Qt.transparent)
    painter=QPainter(image)
    try:draw(painter)
    finally:painter.end()
    return image


def cursor_image(timeline):
    x=timeline.x_for_time(timeline.project.playhead)
    def draw(painter):
        painter.translate(9-round(x),0)
        timeline._paint_playhead(painter)
    return image_for(timeline,18,timeline.viewport().height(),draw)


class RulerCache:
    """Small overscanned original-pixel strips; scroll copies, never relayouts."""
    limit=8*1024*1024
    def __init__(self,timeline):
        self.timeline=timeline;self.entries=OrderedDict();self.bytes=0;self.renders=0
    def image(self,palette,width,height):
        t=self.timeline;ratio=t.devicePixelRatioF();scroll=t.horizontalScrollBar().value();pps=t.pixels_per_second
        if math.ceil(3*width*ratio)*math.ceil(height*ratio)*4>self.limit:
            return image_for(t,width,height,lambda p:t._paint_ruler(p,palette,width,QRegion(0,0,width,height)))
        denominator=Fraction(ratio).limit_denominator(64).denominator
        # Identical physical-pixel phase is required for fractional DPI glyphs.
        phase=scroll%denominator;key=(width,height,pps,repr(palette),ratio,phase)
        cached=self.entries.get(key)
        if not cached or not (cached[0]<=scroll and scroll+width<=cached[0]+cached[2]):
            pad=math.ceil(width/denominator)*denominator;base=max(phase,scroll-pad);span=3*width
            layout=SimpleNamespace(LABEL_WIDTH=t.LABEL_WIDTH,RULER_HEIGHT=t.RULER_HEIGHT,pixels_per_second=pps,
                horizontalScrollBar=lambda:SimpleNamespace(value=lambda:base),
                time_for_x=lambda x:max(0,(x-t.LABEL_WIDTH+base)/pps))
            strip=image_for(t,span,height,lambda p:type(t)._paint_ruler(layout,p,palette,span,QRegion(0,0,span,height)))
            if cached:self.bytes-=cached[1].sizeInBytes()
            cached=(base,strip,span);self.entries[key]=cached;self.bytes+=strip.sizeInBytes();self.renders+=1
        self.entries.move_to_end(key)
        while self.bytes>self.limit and len(self.entries)>1:
            _,old=self.entries.popitem(last=False);self.bytes-=old[1].sizeInBytes()
        image=cached[1].copy(round((scroll-cached[0])*ratio),0,math.ceil(width*ratio),math.ceil(height*ratio));image.setDevicePixelRatio(ratio)
        painter=QPainter(image)
        try:
            painter.fillRect(QRectF(0,0,t.LABEL_WIDTH+1,t.RULER_HEIGHT+1),QColor(palette.get('timeline_ruler_bg','#26272c')))
            painter.fillRect(QRectF(0,0,t.LABEL_WIDTH-2,t.RULER_HEIGHT),QColor(palette.get('timeline_header_bg','#202126')))
            painter.fillRect(QRectF(t.LABEL_WIDTH-2,0,3,t.RULER_HEIGHT+1),QColor(palette.get('timeline_divider','#0b0c0e')))
        finally:painter.end()
        return image


def refresh(surface,palette):
    t=surface.timeline;ratio=t.devicePixelRatioF()
    def texture(name,image,x,y,width,height,z):
        node=getattr(surface,name,None)
        if node is None:
            node=surface.create('GpuImage.qml');node.setVisible(True);node.setZ(z);setattr(surface,name,node)
        node.setX(x);node.setY(y);node.setWidth(width);node.setHeight(height)
        serial=getattr(surface,'_chrome_serial',0)+1;surface._chrome_serial=serial
        surface.images.put(name,image);node.setProperty('source',f'image://prepared/{name}?v={serial}')
        return node
    width=surface.view.width();height=t.RULER_HEIGHT+1
    signature=(width,t.pixels_per_second,t.horizontalScrollBar().value(),repr(palette),ratio)
    if signature!=getattr(surface,'_ruler_signature',None):
        surface._ruler_signature=signature
        if not hasattr(surface,'_ruler_cache'):surface._ruler_cache=RulerCache(t)
        image=surface._ruler_cache.image(palette,width,height)
        texture('ruler_texture',image,0,0,width,height,1000010)
    stamp=t._timecode(t.project.playhead)
    signature=(stamp,repr(palette),ratio,t.LABEL_WIDTH,t.RULER_HEIGHT)
    if signature!=getattr(surface,'_clock_signature',None):
        surface._clock_signature=signature
        def clock(painter):
            painter.setPen(QColor(palette.get('timeline_text','#eef0f3')))
            painter.setFont(QFont('Segoe UI',13,QFont.DemiBold))
            painter.drawText(QRectF(8,0,t.LABEL_WIDTH-16,t.RULER_HEIGHT),Qt.AlignCenter,stamp)
        image=image_for(t,t.LABEL_WIDTH,t.RULER_HEIGHT,clock)
        texture('clock_texture',image,0,0,t.LABEL_WIDTH,t.RULER_HEIGHT,1000011)
    x=t.x_for_time(t.project.playhead)
    signature=(x-round(x),t.viewport().height(),ratio,x>=t.LABEL_WIDTH)
    if signature!=getattr(surface,'_cursor_signature',None):
        surface._cursor_signature=signature
        texture('cursor_texture',cursor_image(t),round(x)-9,0,18,t.viewport().height(),1000012)
    surface.cursor_texture.setX(round(x)-9);surface.cursor_texture.setVisible(x>=t.LABEL_WIDTH)
