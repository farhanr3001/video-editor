"""Effects library UI. Static, bounded thumbnails; one silent GPU video on request."""
import math
from collections import OrderedDict

from PySide6.QtCore import Qt, QSize, QRect, QRectF, QEvent, QTimer, QUrl, Signal, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QIcon, QPolygonF
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QListView, QSplitter, QToolButton, QPushButton, QAbstractItemView,
    QStyledItemDelegate, QStyle, QSizePolicy)

from .controls import SafeComboBox
from .small_controls import PanelSearch
from .effects import CATALOG, CATEGORY_STYLE, DESCRIPTIONS, EFFECT_ICONS, TITLES
from .icons import lucide_icon
from .theme_widgets import ui_color, set_ui_style
from . import effects_library as library

NAME = Qt.UserRole
OPTIONAL = Qt.UserRole + 20
THUMBNAIL = Qt.UserRole + 31
FAVOURITE = Qt.UserRole + 32


class Search(PanelSearch):
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear(); self.dismissed.emit(); event.accept(); return
        super().keyPressEvent(event)

    def toggle(self):
        self.show(); self.setFocus(); self.selectAll()


class ThumbnailCache:
    limit = 48
    def __init__(self):
        self.images = OrderedDict()

    def get(self, path):
        if not path:
            return QPixmap()
        key = str(path)
        if key not in self.images:
            self.images[key] = QPixmap(key)
        self.images.move_to_end(key)
        while len(self.images) > self.limit:
            self.images.popitem(last=False)
        return self.images[key]


class CategoryList(QListWidget):
    """Categories activate on a click, never sweep-select or scroll on a hold."""
    def __init__(self):
        super().__init__(); self.setAutoScroll(False)
    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.LeftButton:event.accept(); return
        super().mouseMoveEvent(event)


class CategoryDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        rect = option.rect.adjusted(3, 1, -3, -1)
        if index.data(NAME) == '__heading__':
            painter.setPen(ui_color('text_sub'))
            font = QFont(option.font); font.setPointSizeF(max(7., font.pointSizeF()-1))
            painter.setFont(font)
            painter.drawText(rect.adjusted(8, 3, -4, 0), Qt.AlignLeft | Qt.AlignVCenter, index.data() or '')
            painter.restore(); return
        selected = bool(option.state & QStyle.State_Selected)
        if selected or option.state & QStyle.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(ui_color('bg_selected' if selected else 'bg_hover'))
            painter.drawRoundedRect(rect, 3, 3)
        if selected:
            painter.fillRect(QRect(rect.left(), rect.top()+5, 2, max(1, rect.height()-10)), ui_color('accent'))
        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon):
            icon.paint(painter, QRect(rect.left()+8, rect.center().y()-7, 14, 14), mode=QIcon.Selected if selected else QIcon.Normal)
        painter.setPen(ui_color('text_selected' if selected else 'text_sub'))
        text_rect = rect.adjusted(30, 0, -5, 0)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         option.fontMetrics.elidedText(index.data() or '', Qt.ElideRight, text_rect.width()))
        painter.restore()


class EffectDelegate(QStyledItemDelegate):
    favourite_clicked = Signal(str)
    def __init__(self, browser):
        super().__init__(browser.list)
        self.browser = browser
        self.thumbnails = ThumbnailCache()

    def geometry(self, rect, header=False):
        if header:
            return QRect(), QRect(), QRect()
        if self.browser.display_mode == 'list':
            art = QRect(rect.left()+6, rect.top()+6, 51, 31)
            text = QRect(art.right()+9, rect.top()+4, max(1, rect.width()-96), rect.height()-8)
            star = QRect(rect.right()-29, rect.center().y()-13, 26, 26)
        else:
            art = QRect(rect.left()+1, rect.top()+1, rect.width()-2,
                        self.browser.art_height(rect.width()))
            text = QRect(rect.left()+7, art.bottom()+2, rect.width()-14, 30)
            star = QRect(art.right()-27, art.top()+4, 24, 24)
        return art, text, star

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(1, 1, -1, -1)
        name = index.data(NAME)
        if not name:
            painter.setPen(ui_color('text_sub'))
            font = QFont(option.font); font.setBold(True); painter.setFont(font)
            painter.drawText(rect.adjusted(5, 0, -5, 0), Qt.AlignLeft | Qt.AlignVCenter, index.data() or '')
            painter.restore(); return
        selected = bool(option.state & QStyle.State_Selected)
        painter.setBrush(ui_color('bg_surface'))
        painter.setPen(QPen(ui_color('accent' if selected else 'border_subtle'), 1))
        painter.drawRoundedRect(QRectF(rect), 4, 4)
        art, text, star = self.geometry(rect)
        pixmap = self.thumbnails.get(index.data(THUMBNAIL))
        if not pixmap.isNull():
            scaled = pixmap.scaled(art.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.save(); painter.setClipRect(art)
            painter.drawPixmap(art.center().x()-scaled.width()//2, art.center().y()-scaled.height()//2, scaled)
            painter.restore()
        else:
            painter.fillRect(art, ui_color('bg_input'))
            icon = index.data(Qt.DecorationRole)
            if isinstance(icon, QIcon):
                side = min(30, art.height()-6)
                icon.paint(painter, QRect(art.center().x()-side//2, art.center().y()-side//2, side, side))
        painter.setPen(ui_color('text_main'))
        if self.browser.display_mode == 'list':
            first = QRect(text.left(), text.top(), text.width(), max(17, text.height()//2))
            painter.drawText(first, Qt.AlignLeft | Qt.AlignVCenter,
                             option.fontMetrics.elidedText(name, Qt.ElideRight, first.width()))
            painter.setPen(ui_color('text_sub'))
            font = QFont(option.font); font.setPointSizeF(max(7., font.pointSizeF()-1)); painter.setFont(font)
            painter.drawText(text.adjusted(0, text.height()//2, 0, 0), Qt.AlignLeft | Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(library.GROUPS.get(name, ''), Qt.ElideRight, text.width()))
        else:
            painter.drawText(text, Qt.AlignLeft | Qt.AlignVCenter,
                             option.fontMetrics.elidedText(name, Qt.ElideRight, text.width()))
        favourite = bool(index.data(FAVOURITE))
        if self.browser.display_mode == 'grid':
            painter.setPen(Qt.NoPen); painter.setBrush(QColor(24, 28, 34, 205)); painter.drawRoundedRect(star, 3, 3)
            colour = '#e4c38b' if favourite else '#e2e5eb'
        else:
            colour = ui_color('accent' if favourite else 'text_sub').name()
        if favourite:
            painter.setBrush(QColor(colour)); painter.setPen(Qt.NoPen)
            center=QRectF(star).center()
            painter.drawPolygon(QPolygonF([QPointF(center.x()+math.cos(-math.pi/2+i*math.pi/5)*(7.5 if i%2==0 else 3.4),
                                                  center.y()+math.sin(-math.pi/2+i*math.pi/5)*(7.5 if i%2==0 else 3.4)) for i in range(10)]))
        else:
            lucide_icon('star', colour, 15).paint(painter, star.adjusted(5, 5, -5, -5))
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton and index.data(NAME):
            _, _, star = self.geometry(option.rect.adjusted(1, 1, -1, -1))
            if star.contains(event.position().toPoint()):
                self.favourite_clicked.emit(index.data(NAME)); return True
        return super().editorEvent(event, model, option, index)


class EffectsBrowser(QWidget):
    catalog = CATALOG
    def __init__(self, window, list_type):
        super().__init__()
        self.window = window
        self.assets = library.manifest()
        self.view_mode = window.settings.get('effects_view', 'grid')
        if self.view_mode not in ('grid', 'list'): self.view_mode = 'grid'
        self.display_mode = self.view_mode
        self.favourites = library.unique_names(window.settings.get('effects_favourites', []))
        self.recent = library.unique_names(window.settings.get('effects_recent', []), library.RECENT_LIMIT)
        self.details_collapsed = bool(window.settings.get('effects_details_collapsed', True))
        self.player = None; self.video = None; self.playing_name = ''; self._ready = False
        self._scroll_positions={}; self._view_key=None; self._restoring_scroll=False; self._pending_scroll=None
        self.setObjectName('effectsBrowser')
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(4)
        self.search = Search(); self.search.setAccessibleName('Search all effects')
        self.search.setPlaceholderText('Search…'); self.search.setClearButtonEnabled(True)
        self.search.setToolTip('Search all effects · Escape clears')
        self.search.setMinimumWidth(58); self.search.setMaximumWidth(130)
        split = QSplitter(Qt.Horizontal, self); self.splitter = split
        self.categories = CategoryList(); self.categories.setAccessibleName('Effect categories')
        self.categories.setMinimumWidth(96); self.categories.setMaximumWidth(172)
        self.categories.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.categories.setItemDelegate(CategoryDelegate(self.categories))
        names = ['All Effects', 'Titles', *[n for n in CATALOG if n != 'Titles']]
        insertion = names.index('Video Transitions')+1
        names[insertion:insertion] = [library.FAVOURITES, library.RECENT]
        for name in names:
            section = {'Open FX / Blur': 'TOOLS', 'Light & Color': 'STYLE & FINISH', 'Audio': 'AUDIO & GRAPHICS'}.get(name)
            if section:
                header = QListWidgetItem(section); header.setData(NAME, '__heading__')
                header.setFlags(Qt.NoItemFlags); header.setSizeHint(QSize(120, 25))
                self.categories.addItem(header)
            symbol = {'All Effects': 'layers', library.FAVOURITES: 'star', library.RECENT: 'history'}.get(name, CATEGORY_STYLE.get(name, ('layers', ''))[0])
            entry = QListWidgetItem(lucide_icon(symbol), name); entry.setSizeHint(QSize(130, 30)); entry.setToolTip(name)
            self.categories.addItem(entry)
        remembered = window.settings.get('effects_category', 'All Effects')
        if remembered == 'Blur & Focus':remembered = 'Open FX / Blur'
        self.categories.setCurrentItem(self.categories.findItems(remembered if remembered in names else 'All Effects', Qt.MatchExactly)[0])
        body = QWidget(); column = QVBoxLayout(body); column.setContentsMargins(7, 3, 5, 0); column.setSpacing(4)
        bar = QHBoxLayout(); self.category_label = QLabel(); self.category_label.setMinimumWidth(0)
        self.category_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.count_label = QLabel(); bar.addWidget(self.category_label, 1); bar.addWidget(self.count_label)
        bar.addWidget(self.search, 1)
        self.grid_button = self._button('layout-grid', 'Card view', self.set_grid)
        self.list_button = self._button('list', 'List view', self.set_list)
        for button in (self.grid_button, self.list_button): button.setCheckable(True); bar.addWidget(button)
        column.addLayout(bar)
        self.subsections = SafeComboBox(); self.subsections.setAccessibleName('Effect subsection')
        self.subsections.setMinimumWidth(0); column.addWidget(self.subsections)
        self.list = list_type(); self.list.window_ = window; self.list.visual_library = True
        self.list.setAccessibleName('Effects library'); self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMovement(QListView.Static); self.list.setResizeMode(QListView.Adjust)
        self.list.setUniformItemSizes(False); self.list.setWordWrap(False)
        self.delegate = EffectDelegate(self); self.list.setItemDelegate(self.delegate)
        self.delegate.favourite_clicked.connect(self.toggle_favourite)
        column.addWidget(self.list, 1)
        split.addWidget(self.categories); split.addWidget(body); split.setStretchFactor(1, 1)
        split.setSizes([136, 294]); root.addWidget(split, 1)
        self.details = QWidget(); details_layout = QVBoxLayout(self.details); details_layout.setContentsMargins(8, 6, 8, 6); details_layout.setSpacing(4)
        line = QHBoxLayout(); line.setSpacing(5)
        self.effect_name = QLabel(''); self.effect_name.setMinimumWidth(0); self.effect_name.setWordWrap(True)
        line.addWidget(self.effect_name, 1)
        self.preview_button = QPushButton('Preview'); self.preview_button.setIcon(lucide_icon('play')); self.preview_button.setAccessibleName('Preview selected effect')
        self.preview_button.clicked.connect(self.preview); line.addWidget(self.preview_button)
        self.collapse_button = self._button('chevron-down', 'Collapse effect details', self.toggle_details); line.addWidget(self.collapse_button)
        details_layout.addLayout(line)
        self.description = QLabel(); self.description.setWordWrap(True); self.description.setMinimumWidth(0)
        self.description.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        details_layout.addWidget(self.description); root.addWidget(self.details)
        self.hint = QLabel('Drag onto a clip · double-click to apply'); self.hint.setWordWrap(True)
        self.hint.setContentsMargins(8, 1, 8, 5); root.addWidget(self.hint)
        set_ui_style(self.description, 'color: @text_sub;')
        set_ui_style(self.hint, 'color: @text_sub; font-size: 10px;')
        set_ui_style(self.count_label, 'color: @text_sub;')
        set_ui_style(self.details, 'QWidget#effectsDetails { border-top: 1px solid @border_subtle; background: @bg_panel; }')
        self.details.setObjectName('effectsDetails')
        self.layout_timer = QTimer(self); self.layout_timer.setSingleShot(True); self.layout_timer.setInterval(35); self.layout_timer.timeout.connect(self.layout_items)
        self.scroll_restore_timer=QTimer(self); self.scroll_restore_timer.setSingleShot(True); self.scroll_restore_timer.timeout.connect(self._restore_scroll)
        self.list.viewport().installEventFilter(self); self.list.installEventFilter(self)
        self.categories.currentTextChanged.connect(self._category_changed)
        self.search.textChanged.connect(self.refresh); self.search.dismissed.connect(self.list.setFocus)
        self.subsections.currentIndexChanged.connect(self._subsection_changed)
        self.list.currentItemChanged.connect(self._selection_changed)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list.verticalScrollBar().valueChanged.connect(self.stop_preview)
        self.list.verticalScrollBar().valueChanged.connect(self._remember_scroll)
        from .component_ui import events
        events().changed.connect(self.refresh)
        self._ready = True; self._configure_subsections(); self._apply_details_state(); self.refresh()

    def _button(self, icon, tip, callback):
        button = QToolButton(); button.setIcon(lucide_icon(icon)); button.setToolTip(tip); button.setAccessibleName(tip)
        button.setAutoRaise(True); button.setFixedSize(26, 26); button.clicked.connect(callback); return button

    def save_preference(self, key, value):
        if self.window.settings.get(key) == value: return
        self.window.settings[key] = value
        from .config import save_settings
        try: save_settings(self.window.settings)
        except OSError:
            import logging
            logging.warning('Could not save effects library preferences', exc_info=True)

    def category(self):
        item = self.categories.currentItem()
        return item.text() if item else 'All Effects'

    def _configure_subsections(self):
        self.subsections.blockSignals(True); self.subsections.clear()
        category = self.category(); groups = library.SUBSECTIONS.get(category, {})
        self.subsections.addItem('All '+category.lower(), '')
        for name in groups: self.subsections.addItem(name, name)
        saved = library.subsection(self.window.settings, category)
        self.subsections.setCurrentIndex(max(0, self.subsections.findData(saved)))
        self.subsections.setVisible(bool(groups) and not self.search.text().strip())
        self.subsections.blockSignals(False)

    def _category_changed(self, category):
        if not self._ready: return
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self.save_preference('effects_category', category)
        self._configure_subsections(); self.refresh()

    def _subsection_changed(self, _):
        if not self._ready: return
        saved = self.window.settings.get('effects_subsections', {})
        saved = dict(saved) if isinstance(saved, dict) else {}
        saved[self.category()] = self.subsections.currentData() or ''
        self.save_preference('effects_subsections', saved); self.refresh()

    def toggle_search(self): self.search.toggle()
    def set_grid(self): self.set_view('grid')
    def set_list(self): self.set_view('list')
    def set_view(self, view):
        self._remember_scroll(); self.view_mode = view; self.save_preference('effects_view', view); self.stop_preview(); self.refresh()

    def toggle_details(self):
        self.details_collapsed = not self.details_collapsed
        self.save_preference('effects_details_collapsed', self.details_collapsed); self._apply_details_state()

    def _apply_details_state(self):
        self.description.setVisible(not self.details_collapsed)
        self.collapse_button.setIcon(lucide_icon('chevron-up' if self.details_collapsed else 'chevron-down'))
        tip = 'Expand effect details' if self.details_collapsed else 'Collapse effect details'
        self.collapse_button.setToolTip(tip); self.collapse_button.setAccessibleName(tip)

    def toggle_favourite(self, name):
        if name in self.favourites: self.favourites.remove(name)
        else: self.favourites.append(name)
        self.save_preference('effects_favourites', list(self.favourites))
        if self.category() == library.FAVOURITES: self.refresh()
        else:
            for row in range(self.list.count()):
                item = self.list.item(row)
                if item.data(NAME) == name: item.setData(FAVOURITE, name in self.favourites)
            self.list.viewport().update()

    def remember_used(self, name):
        if name not in library.GROUPS: return
        self.recent = library.unique_names([name, *self.recent], library.RECENT_LIMIT)
        self.save_preference('effects_recent', list(self.recent))
        if self.category() == library.RECENT: self.refresh()

    def _entries(self):
        category = self.category(); query = self.search.text().strip().casefold()
        if query:
            # Search is global, with clean section headings for the current
            # grouped category retained when it contains every match.
            matches = [n for n in library.ALL_NAMES if query in n.casefold()]
            if category in library.SUBSECTIONS and all(library.GROUPS[n] == category for n in matches):
                return self._group_entries(category, matches, '')
            return [(n, True) for n in matches]
        if category == library.RECENT: return [(n, True) for n in self.recent]
        if category == library.FAVOURITES: return [(n, True) for n in library.ALL_NAMES if n in self.favourites]
        if category == 'All Effects': return [(n, True) for n in library.ALL_NAMES]
        members = CATALOG.get(category, [])
        return self._group_entries(category, members, self.subsections.currentData() or '')

    def _group_entries(self, category, members, selected):
        groups = library.SUBSECTIONS.get(category)
        if not groups: return [(n, True) for n in members]
        result = []
        for heading, names in groups.items():
            if selected and selected != heading: continue
            matching = [n for n in names if n in members]
            if not matching: continue
            result.append((heading, False)); result.extend((n, True) for n in matching)
        return result

    def refresh(self, *_):
        if not self._ready: return
        self.stop_preview()
        self._remember_scroll()
        self._view_key=(self.category(),self.subsections.currentData() or '',self.search.text().strip().casefold(),self.view_mode)
        self._pending_scroll=(self._view_key,self._scroll_positions.get(self._view_key,0))
        self._restoring_scroll=True
        previous = self.list.currentItem().data(NAME) if self.list.currentItem() else ''
        self.list.blockSignals(True); self.list.clear(); selected = None; first = None; count = 0
        from .feature_packs import effect_component, available
        for name, effect in self._entries():
            if not effect:
                item = QListWidgetItem(name); item.setData(NAME, ''); item.setFlags(Qt.NoItemFlags)
                self.list.addItem(item); continue
            count += 1; group = library.GROUPS[name]
            symbol, colour = CATEGORY_STYLE[group]; symbol = EFFECT_ICONS.get(name, symbol)
            item = QListWidgetItem(lucide_icon(symbol, colour), name); item.setData(NAME, name)
            item.setData(FAVOURITE, name in self.favourites)
            entry = self.assets.get(name, {}); thumbnail = library.asset_path(entry, 'thumbnail')
            item.setData(THUMBNAIL, str(thumbnail) if thumbnail else '')
            tip = DESCRIPTIONS.get(name, '')
            if name in library.TRANSITION_SET: tip += '\nDrag onto a cut or clip end, or double-click to apply.'
            elif group in ('Titles', 'Graphics'): tip += '\nDrag onto a video track, or double-click to insert.'
            else: tip += '\nDrag onto a compatible clip, or double-click to apply.'
            item.setToolTip(tip); self.list.addItem(item)
            key = effect_component(name)
            if key and not available(key):
                item.setData(OPTIONAL, key)
                row = QWidget(); row_layout = QVBoxLayout(row); row_layout.setContentsMargins(5, 0, 5, 5); row_layout.setSpacing(0)
                row_layout.addStretch(1)
                button = QPushButton('Download'); button.setIcon(lucide_icon('download')); button.setToolTip('View size and install this optional feature')
                button.clicked.connect(lambda checked=False, k=key: self.download_component(k)); row_layout.addWidget(button)
                self.list.setItemWidget(item, row)
            if first is None: first = item
            if name == previous: selected = item
        self.list.setCurrentItem(selected or first); self.list.blockSignals(False)
        self.category_label.setText('Search results' if self.search.text().strip() else self.category())
        self.category_label.setToolTip(self.category_label.text()); self.count_label.setText(str(count))
        self.subsections.setVisible(bool(library.SUBSECTIONS.get(self.category())) and not self.search.text().strip())
        self.layout_items(); self._selection_changed(); self.scroll_restore_timer.start(0)

    def layout_items(self):
        if not self._ready: return
        self.grid_button.setChecked(self.view_mode == 'grid'); self.list_button.setChecked(self.view_mode == 'list')
        # Reserve a stable scrollbar gutter even while the scrollbar is hidden.
        # Its appearance must not change card heights and make it disappear
        # again at the next layout pass (a continuous 14px resize loop).
        width = max(80, self.list.maximumViewportSize().width() -
                    self.list.style().pixelMetric(QStyle.PM_ScrollBarExtent, None, self.list))
        # Keep the chosen layout preference, but never clip away an effect's
        # name in a short dock. Very short panes temporarily use readable rows.
        self.display_mode = 'list' if self.view_mode == 'grid' and self.list.viewport().height() < 88 else self.view_mode
        grid = self.display_mode == 'grid'
        mode = QListView.IconMode if grid else QListView.ListMode
        flow = QListView.LeftToRight if grid else QListView.TopToBottom
        changed = self.list.viewMode() != mode
        if changed: self.list.setViewMode(mode)
        if self.list.flow() != flow: self.list.setFlow(flow); changed = True
        if self.list.isWrapping() != grid: self.list.setWrapping(grid); changed = True
        if not self.list.gridSize().isEmpty(): self.list.setGridSize(QSize()); changed = True
        if self.list.spacing() != (5 if grid else 2): self.list.setSpacing(5 if grid else 2); changed = True
        columns = max(1, min(4, (width+5)//110))
        tile_width = max(70, (width-(columns+1)*5-4)//columns) if grid else max(60, width-8)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if not item.data(NAME):
                hidden = self.list.viewport().height() < 190
                if item.isHidden() != hidden: item.setHidden(hidden); changed = True
                size = QSize(max(40, width-14), 23)
            else:
                height = (self.art_height(tile_width)+34) if grid else 46
                if item.data(OPTIONAL): height += 29
                size = QSize(tile_width, height)
            if item.sizeHint() != size: item.setSizeHint(size); changed = True
        # Static/IconMode resets Qt's drag mode. Re-enable after each layout change.
        self.list.setDragDropMode(QAbstractItemView.DragOnly); self.list.setDragEnabled(True); self.list.setAutoScroll(False)
        if changed: self.list.doItemsLayout(); self.list.viewport().update()
        if self._pending_scroll is not None:
            self.list.verticalScrollBar().setValue(self._pending_scroll[1])

    def _remember_scroll(self,*_):
        if self._view_key is not None and not self._restoring_scroll:
            self._scroll_positions[self._view_key]=self.list.verticalScrollBar().value()

    def _restore_scroll(self):
        if self._pending_scroll is None:return
        key,value=self._pending_scroll; self._pending_scroll=None
        if key==self._view_key:
            self.list.doItemsLayout(); self.list.verticalScrollBar().setValue(value)
            self._scroll_positions[key]=self.list.verticalScrollBar().value()
        self._restoring_scroll=False

    def art_height(self, width):
        return max(30, min(100, round((width-2)*9/16), self.list.viewport().height()-45))

    def _selection_changed(self, *_):
        self.stop_preview()
        item = self.list.currentItem(); name = item.data(NAME) if item else ''
        self.effect_name.setText(name or 'No matching effects')
        self.description.setText(DESCRIPTIONS.get(name, ''))
        temporal = name in library.ANIMATED_NAMES and library.asset_path(self.assets.get(name, {}), 'preview') is not None
        self.preview_button.setVisible(temporal); self.preview_button.setEnabled(temporal)
        if name in library.TRANSITION_SET: hint = 'Drag onto a cut or clip end · double-click to apply'
        elif name in TITLES or library.GROUPS.get(name) == 'Graphics': hint = 'Drag onto a video track · double-click to insert'
        else: hint = 'Drag onto a clip · double-click to apply'
        self.hint.setText(hint); self._apply_details_state()

    def _on_item_double_clicked(self, item):
        name = str(item.data(NAME) or '')
        if not name: return
        from .feature_packs import effect_component, available
        key = effect_component(name)
        if key and not available(key):
            from .component_ui import offer
            if not offer(self.window, key): return
        if name in library.TRANSITION_SET and hasattr(self.window, 'apply_transition'):
            self.window.apply_transition(name)
        else: self.window.apply_effect(name)

    def download_component(self, key):
        from .component_ui import offer
        offer(self.window, key); self.refresh()

    def preview(self):
        item = self.list.currentItem(); name = item.data(NAME) if item else ''
        if name == self.playing_name: self.stop_preview(); return
        if name not in library.ANIMATED_NAMES: return
        path = library.asset_path(self.assets.get(name, {}), 'preview')
        if path is None: return
        self.stop_preview()
        if self.player is None:
            from PySide6.QtMultimedia import QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget
            self.player = QMediaPlayer(self)
            self.video = QVideoWidget(self.list.viewport()); self.video.setAspectRatioMode(Qt.KeepAspectRatio)
            self.video.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.player.setVideoOutput(self.video)
            self.player.mediaStatusChanged.connect(self._media_status)
            self.player.errorOccurred.connect(self.stop_preview)
        self.list.scrollToItem(item, QAbstractItemView.EnsureVisible)
        art, _, _ = self.delegate.geometry(self.list.visualItemRect(item).adjusted(1, 1, -1, -1))
        self.video.setGeometry(art); self.video.show(); self.video.raise_()
        self.playing_name = name; self.preview_button.setText('Stop'); self.preview_button.setIcon(lucide_icon('square'))
        self.player.setSource(QUrl.fromLocalFile(str(path))); self.player.play()

    def _media_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status in (QMediaPlayer.EndOfMedia, QMediaPlayer.InvalidMedia): self.stop_preview()

    def stop_preview(self, *_):
        self.playing_name = ''
        if self.player is not None:
            self.player.stop()
            if not self.player.source().isEmpty(): self.player.setSource(QUrl())
        if self.video is not None: self.video.hide()
        if hasattr(self, 'preview_button'):
            self.preview_button.setText('Preview'); self.preview_button.setIcon(lucide_icon('play'))

    def eventFilter(self, obj, event):
        if hasattr(self, 'list') and obj in (self.list, self.list.viewport()):
            if obj is self.list.viewport() and event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick) and event.button() == Qt.LeftButton:
                index = self.list.indexAt(event.position().toPoint())
                if index.isValid() and index.data(NAME):
                    _, _, star = self.delegate.geometry(self.list.visualRect(index).adjusted(1, 1, -1, -1))
                    if star.contains(event.position().toPoint()):
                        if event.type() == QEvent.MouseButtonRelease: self.toggle_favourite(index.data(NAME))
                        event.accept(); return True
            if event.type() == QEvent.Resize and self._ready:
                self.stop_preview(); self.layout_timer.start()
            elif event.type() in (QEvent.Hide, QEvent.Wheel): self.stop_preview()
        return super().eventFilter(obj, event)

    def hideEvent(self, event): self.stop_preview(); super().hideEvent(event)
    def closeEvent(self, event): self.stop_preview(); super().closeEvent(event)
