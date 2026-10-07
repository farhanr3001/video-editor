import unittest
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (QApplication, QLabel, QPushButton, QWidget,
                              QVBoxLayout, QListView, QTreeView, QTableView,
                              QTreeWidget, QHeaderView)
from kinetic_cut.theme import PALETTES, get_active_theme_palette
from kinetic_cut.theme_widgets import apply_application_theme, set_ui_style, set_ui_icon
from kinetic_cut.icons import lucide_icon

app = QApplication.instance() or QApplication([])

def luminance(hex_color):
    c = QColor(hex_color)
    def linear(v):
        return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
    return sum(linear(v)*k for v,k in zip(c.getRgbF()[:3], (.2126,.7152,.0722)))

def contrast(a,b):
    x,y = sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)

class ThemeContrastTests(unittest.TestCase):
    def tearDown(self):
        apply_application_theme('default')

    def test_theme_changes_repaint_item_views_and_their_headers(self):
        # Qt item views also provide update(QModelIndex). A full application
        # theme refresh must reach them without selecting that indexed overload.
        owner=QWidget(); layout=QVBoxLayout(owner)
        views=[QListView(),QTreeView(),QTableView(),QTreeWidget(),QHeaderView(Qt.Horizontal)]
        for view in views:layout.addWidget(view)
        try:
            for theme in ('ableton_gray','final_cut_obsidian','default'):
                apply_application_theme(theme)
                app.processEvents()
                self.assertEqual(app.property('kineticTheme'),theme)
                self.assertEqual(app.palette().color(QPalette.Text),QColor(PALETTES[theme]['text_main']))
                self.assertTrue(all(view.parent() is owner for view in views))
        finally:
            owner.close(); owner.deleteLater()
            app.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()

    def test_light_text_and_status_roles_are_readable(self):
        p=PALETTES['ableton_gray']
        for fg in ('text_main','text_sub','info','success','warning','danger'):
            for bg in ('bg_main','bg_panel','bg_surface','bg_input','bg_hover'):
                self.assertGreaterEqual(contrast(p[fg],p[bg]),4.5,(fg,bg))
        self.assertGreaterEqual(contrast(p['text_selected'],p['bg_selected']),4.5)
        self.assertGreaterEqual(contrast(p['accent_text'],p['accent']),4.5)

    def test_retired_themes_fall_back_safely(self):
        for key in ('studio_light','premiere_slate','avid_pewter','unknown'):
            self.assertEqual(get_active_theme_palette(key)['id'],'default')

    def test_local_style_roundtrip_and_new_dialog_controls(self):
        label=QLabel('Status')
        set_ui_style(label,'color:@success; background:@bg_panel;')
        initial=label.styleSheet()
        apply_application_theme('ableton_gray')
        self.assertIn(PALETTES['ableton_gray']['success'],label.styleSheet())
        new_label=QLabel('New')
        set_ui_style(new_label,'color:@text_main;')
        self.assertIn('#101010',new_label.styleSheet())
        apply_application_theme('default')
        self.assertEqual(label.styleSheet(),initial)
        label.close(); new_label.close()

    def test_existing_icons_recolour_and_label_pixmaps_refresh(self):
        apply_application_theme('default')
        icon=lucide_icon('wand-sparkles','#8ba2bd')
        old=icon.pixmap(QSize(24,24)).toImage()
        label=QLabel(); set_ui_icon(label,'wand-sparkles','#8ba2bd',24)
        apply_application_theme('ableton_gray')
        light=icon.pixmap(QSize(24,24)).toImage()
        self.assertNotEqual(old,light)
        self.assertEqual(label.pixmap().toImage(),light)
        selected=icon.pixmap(QSize(24,24),QIcon.Selected).toImage()
        self.assertNotEqual(selected,light)
        apply_application_theme('default')
        self.assertEqual(icon.pixmap(QSize(24,24)).toImage(),old)
        label.close()

    def test_content_colour_swatch_is_never_recoloured(self):
        button=QPushButton(); button.setStyleSheet('background:#ff00ff;color:#ffffff;')
        for theme in PALETTES:
            apply_application_theme(theme)
            self.assertEqual(button.styleSheet(),'background:#ff00ff;color:#ffffff;')
        button.close()

    def test_qt_palette_selection_and_tooltips(self):
        for theme,p in PALETTES.items():
            apply_application_theme(theme)
            self.assertEqual(app.palette().color(QPalette.HighlightedText),QColor(p['text_selected']))
            self.assertEqual(app.palette().color(QPalette.ToolTipText),QColor(p['text_main']))

    def test_static_arrow_assets_follow_theme(self):
        from kinetic_cut.controls import SafeDoubleSpinBox
        widget=SafeDoubleSpinBox()
        apply_application_theme('ableton_gray')
        self.assertIn('spin-up-dark.svg',widget.styleSheet())
        apply_application_theme('default')
        self.assertIn('spin-up.svg',widget.styleSheet())
        widget.close()

    def test_selected_inspector_tab_keeps_dark_ink_on_light_surface(self):
        apply_application_theme('ableton_gray')
        icon=lucide_icon('layers','@tab_icon')
        self.assertEqual(icon.pixmap(QSize(20,20),QIcon.Normal,QIcon.Off).toImage(),
                         icon.pixmap(QSize(20,20),QIcon.Normal,QIcon.On).toImage())

    def test_icon_rasters_are_cached_and_navigation_assets_exist(self):
        from kinetic_cut.icons import _icon_raster
        icon=lucide_icon('chevron-left')
        self.assertFalse(icon.isNull())
        icon.pixmap(QSize(20,20))
        before=_icon_raster.cache_info().hits
        icon.pixmap(QSize(20,20))
        self.assertGreater(_icon_raster.cache_info().hits,before)
