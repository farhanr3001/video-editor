"""Build Windows' multi-resolution application icon from the source SVG."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image

root=Path(__file__).resolve().parents[1]
image=QImage(256,256,QImage.Format_RGBA8888); image.fill(Qt.transparent)
painter=QPainter(image); painter.setRenderHint(QPainter.Antialiasing)
QSvgRenderer(str(root/"assets/kinetic-cut.svg")).render(painter); painter.end()
bitmap=Image.frombytes("RGBA",(256,256),bytes(image.constBits()))
bitmap.save(root/"assets/kinetic-cut.ico",sizes=[(n,n) for n in (16,24,32,48,64,128,256)])
