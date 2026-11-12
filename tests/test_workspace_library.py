"""The full-width timeline and shared library move widgets, never project data."""
import copy
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPoint, QEvent
from PySide6.QtWidgets import QApplication
from kinetic_cut.ui import MainWindow
from kinetic_cut.workspace import set_page
from kinetic_cut.config import DEFAULT_SETTINGS


class WorkspaceLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.load = patch('kinetic_cut.ui.load_settings', return_value=self.settings); self.load.start()
        self.w = MainWindow(); self.w.show(); self.app.processEvents()

    def tearDown(self):
        self.w.close(); self.w.deleteLater(); self.app.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents(); self.load.stop()

    def test_timeline_spans_below_library_preview_and_inspector_at_all_sizes(self):
        for width, height in ((1100,700),(1480,900),(1920,1080)):
            self.w.resize(width,height); self.app.processEvents()
            timeline = self.w.timeline.parentWidget()
            self.assertEqual(timeline.width(), self.w.center_split.width())
            self.assertEqual(timeline.mapTo(self.w.centralWidget(),QPoint()).x(), 0)
            self.assertGreaterEqual(timeline.mapTo(self.w.centralWidget(),QPoint()).y(), self.w.workspace_split.height())
            self.assertEqual(self.w.left_stack.parentWidget(), self.w.workspace_split)
            self.assertEqual(self.w.viewer_split.parentWidget(), self.w.workspace_split)

    def test_default_upper_panes_keep_room_for_library_and_preview(self):
        self.w.resize(1480,900); self.app.processEvents()
        width=self.w.workspace_split.width()
        for pane in (self.w.left_stack,):
            self.assertGreater(pane.width(),width*.27)
            self.assertLess(pane.width(),width*.39)
        self.assertGreater(self.w.preview.parentWidget().width(),width*.25)
        self.assertGreater(self.w.workspace_split.height(),self.w.timeline.parentWidget().height()*1.5)
        self.assertFalse(self.w.viewer_split.handle(1).isEnabled())
        self.assertEqual(self.w.right_stack.width(),350)

    def test_inspector_remains_original_fixed_width_when_resizing_or_moving_splitters(self):
        for width,height in ((1100,700),(1480,900),(1920,1080)):
            self.w.resize(width,height); self.app.processEvents()
            for left in (320,465,520):
                self.w.workspace_split.setSizes([left,width-left]); self.app.processEvents()
                for position in (100,700):
                    self.w.viewer_split.moveSplitter(position,1); self.app.processEvents()
                    self.assertEqual(self.w.right_stack.width(),350)
                    self.assertEqual(self.w.right_stack.minimumWidth(),350)
                    self.assertEqual(self.w.right_stack.maximumWidth(),350)
                    self.assertFalse(self.w.viewer_split.handle(1).isEnabled())
                    self.assertTrue(self.w.workspace_split.handle(1).isEnabled())
        for page in (1,0):
            set_page(self.w,page); self.app.processEvents()
            self.assertEqual(self.w.right_stack.width(),350)
            self.assertFalse(self.w.viewer_split.handle(1).isEnabled())

    def test_pane_headers_share_one_aligned_bottom_edge(self):
        library=self.w.left_panels.header; viewer=self.w.viewer_header
        tabs=self.w.inspector.tabs.tabBar()
        def bottom(widget):return widget.mapTo(self.w.centralWidget(),QPoint(0,widget.height())).y()
        self.assertEqual(bottom(library),bottom(viewer))
        self.assertEqual(bottom(library),bottom(tabs))
        for button in self.w.left_panels.buttons.values():
            self.assertEqual(bottom(button),bottom(viewer))

    def test_commands_share_the_library_header_and_inspector_follows_assistant(self):
        from PySide6.QtWidgets import QLabel
        header=self.w.left_panels.header
        for action in self.w.edit_actions:
            self.assertEqual(action.parentWidget(),header)
            self.assertEqual(action.height(),header.height())
        self.assertEqual([action.text() for action in self.w.edit_actions],['Generate Captions','Generate TTS Dialogue','Download Media'])
        self.assertEqual(self.w.header_actions_layout.itemAt(0).widget(),self.w.assistant_button)
        self.assertEqual(self.w.header_actions_layout.itemAt(1).widget(),self.w.inspector_toggle)
        self.assertEqual(self.w.center_split.mapTo(self.w.centralWidget(),QPoint()).y(),0)
        self.assertNotIn('Media Pool',[label.text() for label in self.w.media_panel.findChildren(QLabel)])
        self.assertFalse(self.w.media_panel.source_tabs.drawBase())
        self.assertFalse(self.w.inspector.tabs.tabBar().drawBase())

    def test_gallery_card_geometry_is_fixed_across_sources_and_item_counts(self):
        from dataclasses import asdict
        from kinetic_cut.model import MediaItem
        from kinetic_cut.pool_tools import set_view
        from PySide6.QtWidgets import QStyleOptionViewItem
        panel=self.w.media_panel; set_view(panel,False,False)
        sizes=[]
        for count in (1,4,17):
            media=[MediaItem('sample'+str(n),'missing'+str(n)+'.png','image','A long sample media name '+str(n)) for n in range(count)]
            self.w.project.media=media; panel.folder='project'; panel.refresh(); self.app.processEvents()
            sizes.append(panel.grid.itemDelegate().sizeHint(QStyleOptionViewItem(),panel.grid.model().index(0,0)))
            panel.power.data={'folders':['Master','Master/References'],'media':[{'folder':'Master','media':asdict(m)} for m in media]}
            panel.folder='Master'; panel.refresh(); self.app.processEvents()
            for i in range(panel.grid.count()):sizes.append(panel.grid.itemDelegate().sizeHint(QStyleOptionViewItem(),panel.grid.model().index(i,0)))
        self.assertTrue(all(size==sizes[0] for size in sizes))
        self.assertEqual(sizes[0].width(),98); self.assertEqual(sizes[0].height(),82)

    def test_gallery_fits_three_fixed_columns_in_screenshot_width(self):
        from dataclasses import asdict
        from kinetic_cut.model import MediaItem
        from kinetic_cut.pool_tools import set_view, GALLERY_CARD, GALLERY_ART
        panel=self.w.media_panel; self.w.left_panels.select('Media')
        set_view(panel,False,False); panel.grid.setFixedWidth(320)
        media=[MediaItem('dense'+str(n),'missing'+str(n)+'.png','image','Sample '+str(n)) for n in range(9)]
        self.w.project.media=media
        panel.power.data={'folders':['Master','Master/References'],'media':[{'folder':'Master','media':asdict(m)} for m in media]}
        for folder in ('project','Master'):
            panel.folder=folder; panel.refresh(); panel.grid.doItemsLayout(); self.app.processEvents()
            rects=[panel.grid.visualItemRect(panel.grid.item(n)) for n in range(4)]
            self.assertEqual([r.top() for r in rects[:3]],[rects[0].top()]*3)
            self.assertGreater(rects[3].top(),rects[0].top())
            self.assertEqual(panel.grid.gridSize(),GALLERY_CARD)
            self.assertEqual(panel.grid.iconSize(),GALLERY_ART)
            self.assertTrue(all(r.width()<=GALLERY_CARD.width() for r in rects))

    def test_complete_command_titles_retain_visible_header_icons(self):
        for action in self.w.edit_actions:
            image=action.grab().toImage(); center=image.width()//2
            colors={image.pixelColor(x,y).rgba() for x in range(center-8,center+9) for y in range(9,27)}
            self.assertGreater(len(colors),2,action.text())

    def test_tabs_expose_existing_media_and_catalogue_without_mutation(self):
        revision = self.w.project._edit_revision
        lib = self.w.left_panels
        self.assertEqual(list(lib.buttons),['Media','Effects'])
        lib.buttons['Effects'].click(); self.app.processEvents()
        for category in ('Audio','Titles','Video Transitions','Graphics'):
            self.w.effects_panel.categories.setCurrentItem(self.w.effects_panel.categories.findItems(category,Qt.MatchExactly)[0])
            self.assertEqual(lib.stack.currentWidget(), self.w.effects_panel)
            self.assertEqual(self.w.effects_panel.category(), category)
        lib.buttons['Media'].click(); self.app.processEvents()
        self.assertEqual(lib.stack.currentWidget(), self.w.media_panel)
        self.assertEqual(self.w.project._edit_revision, revision)

    def test_effect_category_and_subsection_survive_media_tab_switch(self):
        lib=self.w.left_panels; lib.select('Effects')
        self.w.effects_panel.categories.setCurrentItem(self.w.effects_panel.categories.findItems('Visual FX',Qt.MatchExactly)[0])
        self.w.effects_panel.subsections.setCurrentText('Zooms')
        lib.select('Media'); lib.select('Effects')
        self.assertEqual(self.w.effects_panel.category(),'Visual FX')
        self.assertEqual(self.w.effects_panel.subsections.currentText(),'Zooms')

    def test_power_bins_are_separate_and_remember_their_folder_within_session(self):
        panel=self.w.media_panel; panel.power.data['folders'].append('Master/Test')
        panel.source_tabs.setCurrentIndex(1)
        self.assertEqual(panel.folder,'Master'); self.assertEqual(panel.navigation_split.currentIndex(),1)
        panel.folder='Master/Test'; panel.refresh()
        panel.source_tabs.setCurrentIndex(0); self.assertEqual(panel.folder,'project')
        panel.source_tabs.setCurrentIndex(1); self.assertEqual(panel.folder,'Master/Test')
        panel.folder='project'; panel.refresh(); self.assertEqual(panel.source_tabs.currentIndex(),0)

    def test_deliver_and_return_preserve_the_library_tab_and_editor_tools(self):
        self.w.left_panels.select('Effects')
        self.w.effects_panel.categories.setCurrentItem(self.w.effects_panel.categories.findItems('Titles',Qt.MatchExactly)[0])
        set_page(self.w,1); self.app.processEvents()
        self.assertEqual(self.w.left_stack.currentWidget(),self.w.delivery.settings)
        self.assertEqual(self.w.left_stack.width(),360)
        self.assertTrue(self.w.timeline.read_only)
        set_page(self.w,0); self.app.processEvents()
        self.assertEqual(self.w.left_stack.currentWidget(),self.w.left_panels)
        self.assertEqual(self.w.left_panels.active,'Effects')
        self.assertEqual(self.w.effects_panel.category(),'Titles')
        self.assertFalse(self.w.timeline.read_only)

    def test_inspector_visibility_never_changes_timeline_width(self):
        width=self.w.timeline.width()
        self.w.inspector_toggle.setChecked(False); self.app.processEvents()
        self.assertFalse(self.w.right_stack.isVisible()); self.assertEqual(self.w.timeline.width(),width)
        self.w.inspector_toggle.setChecked(True); self.app.processEvents(); self.assertTrue(self.w.right_stack.isVisible())

    def test_timeline_successful_transition_use_reaches_library_history(self):
        from kinetic_cut.transitions import TRANSITION_NAMES
        name=TRANSITION_NAMES[0]
        self.w.timeline.effectUsed.emit(name)
        self.assertEqual(self.w.effects_panel.recent[0], name)

    def test_previous_effect_category_is_the_initial_effects_tab_destination(self):
        from kinetic_cut.workspace_library import LibraryPanel
        from PySide6.QtWidgets import QWidget
        from kinetic_cut.effects_browser import EffectsBrowser
        from kinetic_cut.workspace import EffectList
        self.w.settings.pop('library_effects_category',None)
        self.w.settings['effects_category']='Open FX / Blur'
        browser=EffectsBrowser(self.w,EffectList); media=QWidget()
        library=LibraryPanel(self.w,media,browser)
        library.select('Effects')
        self.assertEqual(browser.category(),'Open FX / Blur')
        library.select('Media'); library.select('Effects')
        self.assertEqual(browser.category(),'Open FX / Blur')
        library.deleteLater()


if __name__=='__main__': unittest.main()
