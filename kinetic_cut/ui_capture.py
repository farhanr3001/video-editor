"""Explicit UI snapshots including independently presented native surfaces.

This readback is only for requested snapshots, never the playback paint path.
QWidget.grab cannot include embedded QQuickWindow child swap chains.
"""
from PySide6.QtCore import QPoint, QRectF
from PySide6.QtGui import QPainter


def capture(widget,surfaces=()):
    image=widget.grab().toImage()
    painter=None
    try:
        for surface in surfaces:
            if surface is None or surface.closed or not surface.container.isVisible():continue
            native=surface.view.grabWindow()
            if native.isNull():continue
            if painter is None:painter=QPainter(image)
            position=surface.container.mapTo(widget,QPoint())
            painter.drawImage(QRectF(position.x(),position.y(),surface.container.width(),surface.container.height()),native)
    finally:
        if painter:painter.end()
    return image
