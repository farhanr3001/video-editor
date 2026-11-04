"""Motion asset picker: a thumbnail grid of built-in and saved assets; a play button on each card previews it once.

Used as the editor's Assets tab and as a floating picker window. Double-click (or Insert) adds an asset at the canvas
centre at the playhead; dragging a thumbnail onto the canvas drops it where it lands. Thumbnails and the play-button frames are
rendered on the GPU (motion_gpu_render.scene_image) and cached on disk, so the grid opens instantly after the first time.
"""
import hashlib
import json
from PySide6.QtCore import Qt, QSize, QTimer, QMimeData, Signal, QElapsedTimer, QRect, QPoint
from PySide6.QtGui import QImage, QPixmap, QIcon, QPainter, QColor, QPalette, QPolygon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox, QListWidget, QListWidgetItem, QPushButton,
                               QLabel, QDialog, QListView, QAbstractItemView, QStyledItemDelegate, QStyle)
from . import motion_assets as A

MIME = 'application/x-kinetic-motion-asset'
THUMB = QSize(152, 100)
THUMB_TIME = {'Sparkle burst': .3, 'Like burst': .42, 'Cursor click': .82, 'Typewriter line': .8, 'Search bar typing': .7, 'Laptop close': .7}
FRAMES = 30
VERSION = 3


def _key(asset, extra=''):
    data = json.dumps({k: asset.get(k) for k in ('nodes', 'size', 'backdrop', 'duration')}, sort_keys=True, default=str)
    return hashlib.sha1(('%d|%s|%s' % (VERSION, extra, data)).encode()).hexdigest()[:20]


def _cache():
    from .config import CACHE_DIR
    folder = CACHE_DIR / 'motion-assets'; folder.mkdir(parents=True, exist_ok=True); return folder


def render(asset, fraction, size=THUMB):
    """One framed frame of an asset as a QImage (GPU; painter fallback where Qt Quick is unavailable)."""
    from . import motion as M
    scene = M.validate(A.preview_scene(asset)); w, h = scene['canvas']; f = min(size.width() / w, size.height() / h)
    px = (max(2, round(w * f)), max(2, round(h * f))); t = asset.get('duration', 1.) * fraction
    try:
        from .motion_gpu_render import scene_image
        image = scene_image(scene, t, px, 30)
    except Exception:
        image = M.draw(scene, t, px, 30)
    canvas = QImage(size, QImage.Format_ARGB32_Premultiplied); canvas.fill(QColor(asset.get('backdrop', A.PAPER)))
    painter = QPainter(canvas); painter.drawImage((size.width() - image.width()) // 2, (size.height() - image.height()) // 2, image); painter.end()
    return canvas


def thumbnail(asset):
    path = _cache() / (_key(asset, 'thumb') + '.png')
    image = QImage(str(path)) if path.exists() else QImage()
    if image.isNull():
        image = render(asset, THUMB_TIME.get(asset['name'], .85))
        try: image.save(str(path))
        except Exception: pass
    return image


def frames(asset):
    """Preview frames, cached as one horizontal strip."""
    path = _cache() / (_key(asset, 'frames%d' % FRAMES) + '.png')
    strip = QImage(str(path)) if path.exists() else QImage()
    if strip.isNull() or strip.width() != THUMB.width() * FRAMES:
        strip = QImage(THUMB.width() * FRAMES, THUMB.height(), QImage.Format_ARGB32_Premultiplied); strip.fill(0)
        painter = QPainter(strip)
        for n in range(FRAMES): painter.drawImage(n * THUMB.width(), 0, render(asset, (n + .5) / FRAMES))
        painter.end()
        try: strip.save(str(path))
        except Exception: pass
    return [strip.copy(n * THUMB.width(), 0, THUMB.width(), THUMB.height()) for n in range(FRAMES)]


class AssetGrid(QListWidget):
    """Asset cards: thumbnail, name and a small play button (bottom right of the thumbnail) that plays the asset once.

    The cards are painted by one delegate; playing swaps the pixmap of a single card, so nothing is relaid out and
    there is no hover or tooltip behaviour at all (scrolling and moving the mouse never start work).
    """
    play_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode); self.setResizeMode(QListView.Adjust); self.setMovement(QListView.Static); self.setWrapping(True)
        self.setGridSize(QSize(THUMB.width() + 14, THUMB.height() + 34)); self.setUniformItemSizes(True); self.setSpacing(2)
        self.setDragEnabled(True); self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection); self.setObjectName('motion_asset_grid'); self.setAccessibleName('Motion assets')
        self.setItemDelegate(AssetDelegate(self)); self.pixmaps = {}; self.live = {}; self._press = None

    def mimeTypes(self): return [MIME]

    def mimeData(self, items):
        data = QMimeData()
        if items: data.setData(MIME, items[0].data(Qt.UserRole).encode('utf-8')); data.setText(items[0].data(Qt.UserRole))
        return data

    def play_button_at(self, pos):
        item = self.itemAt(pos)
        if item is not None and play_rect(self.visualItemRect(item)).contains(pos): return item
        return None

    def mousePressEvent(self, event):
        self._press = self.play_button_at(event.position().toPoint()) if event.button() == Qt.LeftButton else None
        if self._press is None: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is None: super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.play_button_at(event.position().toPoint()) is None: super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        item, self._press = self._press, None
        if item is not None:
            if self.play_button_at(event.position().toPoint()) is item: self.play_requested.emit(item.data(Qt.UserRole))
            return
        super().mouseReleaseEvent(event)


def card_thumb(rect):
    return QRect(rect.left() + (rect.width() - THUMB.width()) // 2, rect.top() + 3, THUMB.width(), THUMB.height())


def play_rect(rect):
    thumb = card_thumb(rect); return QRect(thumb.right() - 25, thumb.bottom() - 25, 22, 22)


class AssetDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        grid = self.parent(); rect = option.rect; name = index.data(Qt.UserRole)
        painter.save(); painter.setRenderHint(QPainter.Antialiasing)
        selected = bool(option.state & QStyle.State_Selected)
        if selected: painter.fillRect(rect.adjusted(1, 1, -1, -1), option.palette.highlight())
        pixmap = grid.live.get(name) or grid.pixmaps.get(name)
        thumb = card_thumb(rect)
        if pixmap is not None: painter.drawPixmap(thumb, pixmap)
        painter.setPen(option.palette.color(QPalette.HighlightedText if selected else QPalette.Text))
        painter.drawText(QRect(rect.left() + 4, thumb.bottom() + 3, rect.width() - 8, rect.bottom() - thumb.bottom() - 3), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, index.data(Qt.DisplayRole))
        button = play_rect(rect); playing = name in grid.live
        painter.setPen(QColor(255, 255, 255, 110)); painter.setBrush(QColor(0, 0, 0, 150 if not playing else 210)); painter.drawEllipse(button); painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#ffffff'))
        if playing: painter.drawRect(button.adjusted(7, 7, -7, -7))
        else:
            cx, cy = button.center().x() + 1, button.center().y()
            painter.drawPolygon(QPolygon([QPoint(cx - 3, cy - 5), QPoint(cx - 3, cy + 5), QPoint(cx + 5, cy)]))
        painter.restore()

    def sizeHint(self, option, index): return self.parent().gridSize() - QSize(4, 4)


class AssetBrowser(QWidget):
    insert_requested = Signal(str)
    save_requested = Signal()

    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(6, 6, 6, 6); layout.setSpacing(6)
        top = QHBoxLayout(); self.search = QLineEdit(self); self.search.setPlaceholderText('Search assets'); self.search.setClearButtonEnabled(True)
        self.category = QComboBox(self); self.category.addItems(['All', *A.CATEGORIES])
        top.addWidget(self.search, 1); top.addWidget(self.category); layout.addLayout(top)
        self.grid = AssetGrid(self); layout.addWidget(self.grid, 1)
        self.hint = QLabel('Double-click to add at the playhead, or drag onto the canvas. The play button previews an asset once.', self); self.hint.setWordWrap(True); self.hint.setObjectName('motion_asset_hint')
        layout.addWidget(self.hint)
        buttons = QHBoxLayout()
        self.insert = QPushButton('Insert', self); self.save = QPushButton('Save selection as asset…', self); self.delete = QPushButton('Delete', self)
        for b in (self.insert, self.save, self.delete): buttons.addWidget(b)
        buttons.addStretch(1); layout.addLayout(buttons)
        self.search.textChanged.connect(self.filter); self.category.currentTextChanged.connect(self.filter)
        self.grid.itemDoubleClicked.connect(lambda item: self.insert_requested.emit(item.data(Qt.UserRole)))
        self.insert.clicked.connect(self.insert_current); self.save.clicked.connect(self.save_requested.emit); self.delete.clicked.connect(self.delete_current)
        self.grid.currentItemChanged.connect(self.selection_changed); self.grid.play_requested.connect(self.play)
        self.timer = QTimer(self); self.timer.setTimerType(Qt.PreciseTimer); self.timer.setInterval(16); self.timer.timeout.connect(self.step)
        self.clock = QElapsedTimer(); self.span = 1500; self.playing = None; self.frames = []; self.frame = -1
        self.assets = {}; self._loaded = False
        self.selection_changed(None)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded: self._loaded = True; QTimer.singleShot(0, self.reload)

    def hideEvent(self, event):
        self.stop(); super().hideEvent(event)

    def reload(self):
        self.stop()
        current = self.grid.currentItem().data(Qt.UserRole) if self.grid.currentItem() else None
        self.grid.clear(); self.assets = {}; self.grid.pixmaps = {}
        for entry in A.catalogue():
            item = QListWidgetItem(entry['name']); item.setData(Qt.UserRole, entry['name']); item.setData(Qt.UserRole + 1, entry['category'])
            item.setData(Qt.UserRole + 2, entry.get('description', '')); item.setSizeHint(self.grid.gridSize() - QSize(4, 4))
            self.grid.addItem(item)
            if entry['name'] == current: self.grid.setCurrentItem(item)
        self.filter(); QTimer.singleShot(0, self.load_thumbnails)

    def load_thumbnails(self):
        for row in range(self.grid.count()):
            name = self.grid.item(row).data(Qt.UserRole)
            try: asset = A.get(name); self.assets[name] = asset; self.grid.pixmaps[name] = QPixmap.fromImage(thumbnail(asset))
            except Exception: continue
        self.grid.viewport().update()

    def filter(self, *_):
        text = self.search.text().strip().lower(); category = self.category.currentText()
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            hidden = (category != 'All' and item.data(Qt.UserRole + 1) != category) or (text and text not in item.text().lower() and text not in str(item.data(Qt.UserRole + 2)).lower())
            item.setHidden(bool(hidden))

    def selection_changed(self, item, *_):
        self.insert.setEnabled(item is not None); self.delete.setEnabled(bool(item and item.data(Qt.UserRole + 1) == 'Mine'))

    def insert_current(self):
        item = self.grid.currentItem()
        if item: self.insert_requested.emit(item.data(Qt.UserRole))

    def delete_current(self):
        item = self.grid.currentItem()
        if item and item.data(Qt.UserRole + 1) == 'Mine' and A.delete(item.data(Qt.UserRole)): self.reload()

    def card_rect(self, name):
        for row in range(self.grid.count()):
            item = self.grid.item(row)
            if item.data(Qt.UserRole) == name: return self.grid.visualItemRect(item)
        return None

    def refresh(self, name):
        rect = self.card_rect(name)
        if rect is not None: self.grid.viewport().update(rect)
        else: self.grid.viewport().update()

    def play(self, name):
        """Play one asset once on its own card (pressing the button again restarts it). Only one card plays at a time."""
        self.stop(); asset = self.assets.get(name)
        if asset is None: return
        try: self.frames = [QPixmap.fromImage(f) for f in frames(asset)]
        except Exception: self.frames = []
        if not self.frames: return
        self.span = max(1000, min(4000, int(asset.get('duration', 1.5) * 1000)))
        self.playing = name; self.frame = -1; self.grid.live[name] = self.frames[0]; self.clock.start(); self.timer.start(); self.refresh(name)

    def step(self):
        if self.playing is None: self.timer.stop(); return
        index = int(self.clock.elapsed() / self.span * len(self.frames))
        if index >= len(self.frames): self.stop(); return
        if index != self.frame: self.frame = index; self.grid.live[self.playing] = self.frames[index]; self.refresh(self.playing)

    def stop(self):
        self.timer.stop(); name, self.playing, self.frames = self.playing, None, []
        self.grid.live.clear()
        if name: self.refresh(name)


class AssetPicker(QDialog):
    """Floating picker window that stays beside the Motion Composition editor while you drag assets onto the canvas."""
    def __init__(self, editor):
        super().__init__(editor, Qt.Tool)
        self.setWindowTitle('Motion assets'); self.resize(720, 560); self.setObjectName('motion_asset_picker')
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.browser = AssetBrowser(self); layout.addWidget(self.browser)
        self.browser.insert_requested.connect(editor.insert_asset); self.browser.save_requested.connect(editor.save_asset)
