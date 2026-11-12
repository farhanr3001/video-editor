"""The visual library must preserve catalogue identity and editing semantics."""
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QApplication, QWidget

from kinetic_cut import effects_library as L
from kinetic_cut.effects import CATALOG, TITLES
from kinetic_cut.effects_browser import EffectsBrowser
from kinetic_cut.workspace import EffectList
from kinetic_cut.config import DEFAULT_SETTINGS, load_settings
from kinetic_cut.model import Project


class Owner(QWidget):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = copy.deepcopy(settings if settings is not None else DEFAULT_SETTINGS)
        self.project = Project(); self.applied = []
    def apply_effect(self, name): self.applied.append(('effect', name))
    def apply_transition(self, name): self.applied.append(('transition', name))


class EffectsLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.owner = Owner()
        self.browser = EffectsBrowser(self.owner, EffectList)
        self.browser.resize(460, 610); self.browser.show(); self.app.processEvents()

    def tearDown(self):
        self.browser.close(); self.owner.close()
        self.browser.deleteLater(); self.owner.deleteLater()
        self.app.sendPostedEvents(None, QEvent.DeferredDelete); self.app.processEvents()

    def category(self, name):
        matches = self.browser.categories.findItems(name, Qt.MatchExactly)
        self.assertEqual(len(matches), 1); self.browser.categories.setCurrentItem(matches[0])

    def names(self):
        return [self.browser.list.item(i).data(Qt.UserRole) for i in range(self.browser.list.count())
                if self.browser.list.item(i).data(Qt.UserRole)]

    def move_with_left_button(self,view,start,end):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent
        self.app.sendEvent(view.viewport(),QMouseEvent(QEvent.MouseButtonPress,QPointF(start),QPointF(view.viewport().mapToGlobal(start)),Qt.LeftButton,Qt.LeftButton,Qt.NoModifier))
        self.app.sendEvent(view.viewport(),QMouseEvent(QEvent.MouseMove,QPointF(end),QPointF(view.viewport().mapToGlobal(end)),Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        self.app.sendEvent(view.viewport(),QMouseEvent(QEvent.MouseButtonRelease,QPointF(end),QPointF(view.viewport().mapToGlobal(end)),Qt.LeftButton,Qt.NoButton,Qt.NoModifier))

    def settle(self):
        from PySide6.QtTest import QTest
        self.app.processEvents();QTest.qWait(60)

    def test_blurs_share_gaussian_category_without_losing_effects(self):
        self.assertNotIn('Blur & Focus',CATALOG)
        self.category('Open FX / Blur')
        self.assertEqual(self.names(),['Gaussian Blur','Directional Blur','Radial Zoom Blur','Tilt Shift'])

    def test_grid_and_list_drag_gestures_emit_every_catalogue_identity(self):
        from PySide6.QtCore import QPoint
        from kinetic_cut.transitions import TRANSITION_SET
        seen=[]
        class Drag:
            def __init__(self,*_):pass
            def setMimeData(self,mime):self.mime=mime
            def setPixmap(self,*_):pass
            def exec(self,*_):
                name=bytes(self.mime.data('application/x-kinetic-effect')).decode()
                seen.append(name)
                if name in TRANSITION_SET:self_test.assertEqual(bytes(self.mime.data('application/x-kinetic-transition')).decode(),name)
                return Qt.IgnoreAction
        self_test=self
        with patch('kinetic_cut.workspace.QDrag',Drag),patch('kinetic_cut.feature_packs.available',return_value=True):
            for mode in ('grid','list'):
                self.browser.set_view(mode);self.settle()
                self.assertTrue(self.browser.list.dragEnabled());self.assertFalse(self.browser.list.hasAutoScroll())
                for name in L.ALL_NAMES:
                    item=self.browser.list.findItems(name,Qt.MatchExactly)[0]
                    self.browser.list.scrollToItem(item);self.app.processEvents()
                    rect=self.browser.list.visualItemRect(item)
                    point=QPoint(rect.left()+12,rect.top()+15)
                    before=self.browser.list.verticalScrollBar().value()
                    self.move_with_left_button(self.browser.list,point,point+QPoint(0,30))
                    self.assertEqual(seen[-1],name)
                    self.assertEqual(self.browser.list.verticalScrollBar().value(),before)
        self.assertEqual(seen,list(L.ALL_NAMES)*2)

    def test_categories_do_not_sweep_select_or_autoscroll_while_held(self):
        from PySide6.QtCore import QPoint
        self.browser.resize(460,310);self.settle()
        view=self.browser.categories;view.verticalScrollBar().setValue(0)
        start=view.visualItemRect(view.item(0)).center()
        self.move_with_left_button(view,start,QPoint(start.x(),view.viewport().height()+40));self.settle()
        self.assertEqual(self.browser.category(),'All Effects');self.assertEqual(view.verticalScrollBar().value(),0)
        self.assertFalse(view.hasAutoScroll())

    def test_each_category_subsection_and_refresh_keeps_scroll_position(self):
        self.browser.resize(460,310);self.settle()
        for mode in ('grid','list'):
            self.browser.set_view(mode);self.settle()
            saved={}
            for category in ('All Effects','Visual FX','Video Transitions','Graphics'):
                self.category(category);self.settle();bar=self.browser.list.verticalScrollBar()
                bar.setValue(bar.maximum()//2);saved[category]=bar.value()
            for category,value in saved.items():
                self.category(category);self.settle();self.assertEqual(self.browser.list.verticalScrollBar().value(),value,category)
                self.browser.refresh();self.settle();self.assertEqual(self.browser.list.verticalScrollBar().value(),value,category)
        self.category('Visual FX');self.browser.subsections.setCurrentText('Zooms');self.settle()
        bar=self.browser.list.verticalScrollBar();bar.setValue(bar.maximum()//2);before=bar.value()
        self.browser.subsections.setCurrentText('Shakes');self.settle()
        self.browser.subsections.setCurrentText('Zooms');self.settle();self.assertEqual(bar.value(),before)

    def test_recent_reorder_after_drop_preserves_scroll(self):
        from PySide6.QtCore import QPoint
        for name in L.ALL_NAMES[:10]:self.browser.remember_used(name)
        self.category(L.RECENT);self.browser.resize(460,270);self.settle()
        view=self.browser.list;bar=view.verticalScrollBar();bar.setValue(bar.maximum()//2);before=bar.value()
        item=next(view.item(i) for i in range(view.count()) if view.visualItemRect(view.item(i)).intersects(view.viewport().rect()))
        class Drag:
            def __init__(self,*_):pass
            def setPixmap(self,*_):pass
            def setMimeData(self,m):self.name=bytes(m.data('application/x-kinetic-effect')).decode()
            def exec(drag,*_):self.browser.remember_used(drag.name);return Qt.CopyAction
        with patch('kinetic_cut.workspace.QDrag',Drag):
            point=view.visualItemRect(item).center();self.move_with_left_button(view,point,point+QPoint(0,30))
        self.settle();self.assertEqual(bar.value(),before)

    def test_favourite_uses_a_filled_star_instead_of_a_dot(self):
        from PySide6.QtGui import QImage,QPainter
        from PySide6.QtWidgets import QStyleOptionViewItem
        self.category('Transform');self.browser.toggle_favourite('Circle Facecam');self.settle()
        view=self.browser.list;index=view.model().index(0,0);rect=view.visualRect(index)
        image=QImage(view.viewport().size(),QImage.Format_ARGB32);image.fill(Qt.transparent)
        option=QStyleOptionViewItem();option.rect=rect;option.font=view.font()
        painter=QPainter(image);self.browser.delegate.paint(painter,option,index);painter.end()
        _,_,star=self.browser.delegate.geometry(rect.adjusted(1,1,-1,-1))
        gold=lambda color:color.red()>190 and color.green()>150 and color.blue()<175
        count=sum(gold(image.pixelColor(x,y)) for x in range(star.left()+4,star.right()-3) for y in range(star.top()+4,star.bottom()-3))
        self.assertGreater(count,50)

    def test_missing_optional_feature_prompts_without_starting_drag(self):
        self.category('Quality Enhancer');self.settle()
        with patch('kinetic_cut.feature_packs.available',return_value=False),patch('kinetic_cut.component_ui.offer',return_value=False) as offer,patch('kinetic_cut.workspace.QDrag') as drag:
            self.browser.list.startDrag(Qt.CopyAction)
        offer.assert_called_once();drag.assert_not_called()

    def test_all_catalogue_identities_and_order_are_retained(self):
        self.category('All Effects')
        expected = [name for names in CATALOG.values() for name in names]
        self.assertEqual(self.names(), expected)
        self.assertEqual(len(expected), len(set(expected)))
        self.assertEqual(self.browser.categories.item(0).text(), 'All Effects')
        self.assertEqual(self.browser.categories.item(1).text(), 'Titles')
        self.assertEqual(self.names()[-len(CATALOG['Graphics']):], CATALOG['Graphics'])

    def test_subsections_start_all_then_remember_independently(self):
        self.category('Visual FX')
        self.assertEqual(self.browser.subsections.currentData(), '')
        self.assertEqual(set(self.names()), set(CATALOG['Visual FX']))
        self.browser.subsections.setCurrentText('Camera Movement')
        expected = list(L.SUBSECTIONS['Visual FX']['Camera Movement'])
        self.assertEqual(self.names(), expected)
        self.category('Video Transitions')
        self.assertEqual(self.browser.subsections.currentData(), '')
        self.browser.subsections.setCurrentText('Dissolve')
        self.category('Visual FX')
        self.assertEqual(self.browser.subsections.currentText(), 'Camera Movement')
        self.assertEqual(self.names(), expected)
        self.assertEqual(load_settings()['effects_subsections']['Video Transitions'], 'Dissolve')

    def test_invalid_or_removed_subsection_falls_back_to_all(self):
        self.owner.settings['effects_subsections'] = {'Visual FX': 'Removed'}
        self.category('Visual FX')
        self.assertEqual(self.browser.subsections.currentData(), '')
        self.assertEqual(set(self.names()), set(CATALOG['Visual FX']))

    def test_search_finds_other_categories_without_changing_saved_category(self):
        self.category('Transform')
        self.browser.search.setText('wave distortion')
        self.assertEqual(self.names(), ['Wave Distortion'])
        self.assertEqual(self.owner.settings['effects_category'], 'Transform')
        self.browser.search.clear(); self.assertEqual(self.names(), ['Circle Facecam'])

    def test_favourites_toggle_and_recent_list_are_unique_and_bounded(self):
        self.browser.toggle_favourite('Punch Zoom'); self.category(L.FAVOURITES)
        self.assertEqual(self.names(), ['Punch Zoom'])
        self.browser.toggle_favourite('Punch Zoom'); self.assertEqual(self.names(), [])
        for name in L.ALL_NAMES[:15]: self.browser.remember_used(name)
        self.browser.remember_used(L.ALL_NAMES[9]); self.category(L.RECENT)
        self.assertEqual(len(self.names()), 10)
        self.assertEqual(self.names()[0], L.ALL_NAMES[9])
        self.assertEqual(len(set(self.names())), 10)
        self.assertEqual(load_settings()['effects_recent'], self.names())

    def test_details_state_survives_selection_category_and_recreation(self):
        before = self.owner.project.to_dict()
        if self.browser.details_collapsed: self.browser.toggle_details()
        self.browser.toggle_details(); self.assertTrue(self.browser.details_collapsed)
        self.category('Visual FX'); self.browser.list.setCurrentRow(2)
        self.assertTrue(self.browser.description.isHidden())
        other_owner = Owner(copy.deepcopy(self.owner.settings))
        other = EffectsBrowser(other_owner, EffectList)
        try:
            self.assertTrue(other.details_collapsed)
            self.assertTrue(other.description.isHidden())
            self.assertEqual(other.category(), 'Visual FX')
        finally: other.close(); other.deleteLater(); other_owner.deleteLater()
        self.assertEqual(self.owner.project.to_dict(), before)

    def test_titles_and_static_colours_never_offer_video_preview(self):
        self.assertFalse(set(TITLES) & L.ANIMATED_NAMES)
        self.assertFalse(set(CATALOG['Colour']) & L.ANIMATED_NAMES)
        self.assertFalse(set(CATALOG['Color Finishing']) & L.ANIMATED_NAMES)
        self.assertTrue({'Color Flash','Wave Distortion','Punch Zoom','Puzzle Assemble'} <= L.ANIMATED_NAMES)
        self.category('Titles')
        for i in range(self.browser.list.count()):
            self.browser.list.setCurrentRow(i)
            self.assertTrue(self.browser.preview_button.isHidden())

    def test_grid_and_list_keep_names_and_card_labels_inside_tiles(self):
        before = self.names()
        self.browser.set_list(); self.browser.layout_items()
        self.assertEqual(self.names(), before)
        self.browser.set_grid(); self.browser.resize(345, 520); self.app.processEvents(); self.browser.layout_items()
        self.assertEqual(self.names(), before)
        first = self.browser.list.item(0)
        rect = self.browser.list.visualItemRect(first).adjusted(1, 1, -1, -1)
        art, text, star = self.browser.delegate.geometry(rect)
        self.assertGreater(art.width(), 20)
        self.assertLessEqual(text.bottom(), rect.bottom()+1)

    def test_double_click_routes_to_existing_apply_functions(self):
        self.category('Visual FX')
        item = next(self.browser.list.item(i) for i in range(self.browser.list.count()) if self.browser.list.item(i).data(Qt.UserRole))
        self.browser._on_item_double_clicked(item)
        self.assertEqual(self.owner.applied[-1], ('effect', item.text()))
        self.category('Video Transitions')
        item = next(self.browser.list.item(i) for i in range(self.browser.list.count()) if self.browser.list.item(i).data(Qt.UserRole))
        self.browser._on_item_double_clicked(item)
        self.assertEqual(self.owner.applied[-1], ('transition', item.text()))

    def test_star_clicks_never_apply_or_start_a_preview(self):
        from PySide6.QtTest import QTest
        self.category('Transform'); self.browser.layout_items(); self.app.processEvents()
        item = self.browser.list.item(0)
        _, _, star = self.browser.delegate.geometry(self.browser.list.visualItemRect(item).adjusted(1, 1, -1, -1))
        QTest.mouseClick(self.browser.list.viewport(), Qt.LeftButton, pos=star.center())
        self.assertIn('Circle Facecam', self.browser.favourites)
        QTest.mouseDClick(self.browser.list.viewport(), Qt.LeftButton, pos=star.center())
        self.assertEqual(self.owner.applied, [])
        self.assertIsNone(self.browser.player)

    def test_usage_observer_ignores_failed_and_nonmutating_commands(self):
        self.owner.effects_panel = self.browser
        @L.remember_use()
        def command(owner, name, mutate=False, fail=False):
            if fail: raise ValueError('Rejected')
            if mutate: owner.project.touch()
            return 'same return value'
        self.assertEqual(command(self.owner, 'Punch Zoom'), 'same return value')
        self.assertEqual(self.browser.recent, [])
        with self.assertRaises(ValueError): command(self.owner, 'Punch Zoom', fail=True)
        self.assertEqual(self.browser.recent, [])
        command(self.owner, 'Punch Zoom', mutate=True)
        self.assertEqual(self.browser.recent, ['Punch Zoom'])

    def test_thumbnail_cache_is_bounded_and_browsing_never_allocates_a_player(self):
        for group in CATALOG: self.category(group)
        self.assertIsNone(self.browser.player)
        self.assertFalse(self.browser.playing_name)
        self.assertLessEqual(len(self.browser.delegate.thumbnails.images), self.browser.delegate.thumbnails.limit)

    def test_preference_write_failure_does_not_break_an_applied_edit(self):
        self.owner.effects_panel = self.browser
        @L.remember_use()
        def command(owner, name):
            owner.project.touch(); return 'applied'
        with patch('kinetic_cut.config.save_settings', side_effect=OSError('Read only')):
            self.assertEqual(command(self.owner, 'Punch Zoom'), 'applied')
        self.assertEqual(self.browser.recent, ['Punch Zoom'])

    def test_shipped_assets_cover_the_entire_catalogue_and_preview_policy(self):
        metadata = L.manifest()
        self.assertEqual(set(metadata), set(L.ALL_NAMES))
        total = 0
        for name, entry in metadata.items():
            with self.subTest(effect=name):
                path = L.asset_path(entry, 'thumbnail')
                self.assertIsNotNone(path); self.assertGreater(path.stat().st_size, 50)
                total += path.stat().st_size
                movie = L.asset_path(entry, 'preview')
                self.assertEqual(movie is not None, name in L.ANIMATED_NAMES)
                if movie: total += movie.stat().st_size
                self.assertNotIn('generated_images', str(entry))
        self.assertLess(total, 64*1024**2)

    def test_asset_paths_cannot_escape_the_library(self):
        self.assertIsNone(L.asset_path({'thumbnail':'../../private.png'}, 'thumbnail'))
        self.assertIsNone(L.asset_path({'thumbnail':str(Path.cwd()/'private.png')}, 'thumbnail'))

    def test_search_shares_category_and_view_row_without_redundant_heading(self):
        self.assertIs(self.browser.layout().itemAt(0).widget(), self.browser.splitter)
        search=self.browser.search; view=self.browser.grid_button
        self.assertEqual(search.parentWidget(),view.parentWidget())
        self.assertLessEqual(abs(search.geometry().center().y()-view.geometry().center().y()),1)
        self.assertLessEqual(search.width(),130)

    def test_narrowing_settles_without_scrollbar_resize_feedback(self):
        from PySide6.QtCore import QObject
        from PySide6.QtTest import QTest
        class Resizes(QObject):
            count=0
            def eventFilter(self,obj,event):
                if event.type()==QEvent.Resize:self.count+=1
                return False
        events=Resizes(); self.browser.list.viewport().installEventFilter(events)
        for category,width,height in (('Texture & Retro',520,300),('Texture & Retro',520,380),('Time & Speed',390,300),('Time & Speed',520,300)):
            self.category(category); self.browser.resize(width,height); QTest.qWait(170)
            events.count=0; before=self.browser.list.viewport().size(); QTest.qWait(250)
            self.assertEqual(events.count,0,(category,width,height))
            self.assertEqual(self.browser.list.viewport().size(),before)
            self.assertFalse(self.browser.layout_timer.isActive())


if __name__ == '__main__': unittest.main()
