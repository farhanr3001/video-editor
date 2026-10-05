"""Isolated native preset interactions and three-theme layout checks."""
def run(output):
    import copy, json, os, sys, traceback
    from pathlib import Path
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    os.environ['KINETIC_CUT_HOME'] = str(output/'home')
    os.environ['QT_QPA_PLATFORM'] = 'windows' if os.name == 'nt' else 'offscreen'
    report = dict(frozen=bool(getattr(sys, 'frozen', False)), screenshots=[])
    window = None; app = None
    try:
        from PySide6.QtCore import Qt, QTimer, QEvent, QThreadPool
        from PySide6.QtGui import QImage, QColor
        from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QVBoxLayout, QScrollArea
        from PySide6.QtTest import QTest
        from .model import Project, MediaItem, TimelineItem, Crop
        from .ui import MainWindow
        from .video_presets import KEY, HIDDEN_KEY, NUMBERS, capture, PresetNameDialog, VideoPresetStrip
        from .config import load_settings
        from .theme_widgets import apply_application_theme
        app = QApplication([]); app.setQuitOnLastWindowClosed(False); app.setStyle('Fusion')
        window = MainWindow(); window.autosave_timer.stop(); window.resize(1400, 850); window.show()
        fixture = output/'fixture.png'; image = QImage(1920, 1080, QImage.Format_RGB32)
        image.fill(QColor('#486e79')); image.save(str(fixture))
        p = Project(media=[MediaItem('m', str(fixture), 'image', 'Preset fixture', 20, 1920, 1080)],
                    timeline=[TimelineItem('v', 'm', 'video_1', 0, 2), TimelineItem('second', 'm', 'video_1', 3, 2)])
        window.set_project(p); window.timeline.select_ids({'v'}, 'v'); window.select_item('v')
        strip = window.inspector.video_presets
        item = p.item_by_id('v'); item.transform.scale = 1.908; item.transform.scale_y = 1.19
        item.transform.rotation = 11; item.crop = Crop(.1, .1, .7, .6); item.opacity = 83
        window.model_changed(); original = capture(window.inspector, item)
        def screenshot(widget, name):
            app.processEvents(); widget.grab().save(str(output/name)); report['screenshots'].append(name)
        def same_values(actual):
            assert actual.keys() == original.keys()
            for key in original:
                # Normalized crop round-trips can differ by a fraction of a
                # trillionth of a pixel. Test below display precision, not bits.
                if key in NUMBERS: assert abs(actual[key] - original[key]) < 1e-8, (key, actual[key], original[key])
                else: assert actual[key] == original[key], key
        for theme in ('default', 'final_cut_obsidian', 'ableton_gray'):
            apply_application_theme(theme)
            window.settings[KEY] = []; strip.reload(); app.processEvents()
            assert strip.combo.currentText() == 'No presets saved' and not strip.delete.isEnabled()
            def name():
                dialog = app.activeModalWidget(); assert isinstance(dialog, PresetNameDialog)
                screenshot(dialog, theme+'-name.png'); dialog.name.setText('Webcam crop')
                QTest.mouseClick(dialog.save, Qt.LeftButton)
            QTimer.singleShot(40, name); QTest.mouseClick(strip.save, Qt.LeftButton)
            assert strip.current()['name'] == 'Webcam crop'
            for width in (320, 440):
                # Size a second real control in its own fixture, rather than
                # changing the inspector's cached minimum width for a screenshot.
                host = QDialog(window); layout = QVBoxLayout(host); layout.setContentsMargins(0, 0, 0, 0)
                compact = VideoPresetStrip(window.inspector); layout.addWidget(compact)
                compact.reload(strip.current()['id']); host.setFixedWidth(width); host.show(); app.processEvents()
                for control in (compact.save, compact.delete, compact.combo):
                    rect = control.rect(); rect.moveTopLeft(control.mapTo(compact, rect.topLeft()))
                    assert compact.rect().contains(rect), (width, control.text() if hasattr(control, 'text') else 'combo')
                screenshot(compact, theme+'-strip-'+str(width)+'.png'); host.close(); host.deleteLater()
            screenshot(window.inspector, theme+'-inspector.png')
            area = window.inspector.video_stack.currentWidget()
            assert isinstance(area, QScrollArea)
            viewport = area.viewport()
            for control in (strip.save, strip.delete, strip.combo, window.inspector.zoom_x,
                            window.inspector.zoom_y, window.inspector.link, window.inspector.mode):
                left = control.mapTo(viewport, control.rect().topLeft()).x()
                assert 0 <= left and left + control.width() <= viewport.width(), (theme, left, control.width(), viewport.width())
            section = window.inspector.video_preset_section
            QTest.mouseClick(section.toggle, Qt.LeftButton); app.processEvents()
            assert strip.isHidden() and section.toggle.isVisible()
            screenshot(window.inspector, theme+'-hidden.png')
            QTest.mouseClick(section.toggle, Qt.LeftButton); app.processEvents()
            assert not strip.isHidden()
            def overwrite_cancel():
                dialog = app.activeModalWidget(); screenshot(dialog, theme+'-overwrite.png')
                assert {b.text().replace('&', '') for b in dialog.buttons()} == {'Overwrite', 'Save as new', 'Cancel'}
                next(b for b in dialog.buttons() if b.text().replace('&', '') == 'Cancel').click()
            QTimer.singleShot(40, overwrite_cancel); QTest.mouseClick(strip.save, Qt.LeftButton)
            def delete_cancel():
                dialog = app.activeModalWidget(); screenshot(dialog, theme+'-delete.png')
                dialog.button(QMessageBox.Cancel).click()
            QTimer.singleShot(40, delete_cancel); QTest.mouseClick(strip.delete, Qt.LeftButton)
            assert len(strip.records) == 1
        before = copy.deepcopy(p.timeline[1]); history = len(window._history)
        window.timeline.select_ids({'v', 'second'}, 'v'); window.select_item('v')
        strip.combo.setCurrentIndex(0)
        # Native dropdown selection; activated must also work for repeated choice.
        QTest.mouseClick(strip.combo, Qt.LeftButton); QTest.keyClick(strip.combo, Qt.Key_Down)
        QTest.keyClick(strip.combo, Qt.Key_Return); app.processEvents()
        report['dropdown_probe'] = dict(index=strip.combo.currentIndex(), expected=original,
                                       actual=capture(window.inspector, p.item_by_id('second')))
        same_values(capture(window.inspector, p.item_by_id('second')))
        assert len(window._history) == history + 1
        window.undo(); assert window.project.item_by_id('second') == before
        window.redo(); same_values(capture(window.inspector, window.project.item_by_id('second')))
        assert load_settings()[KEY][0]['name'] == 'Webcam crop'
        strip.reload(); assert strip.combo.currentIndex() == 1 and strip.delete.isEnabled()
        window.timeline.select_ids({'second'}, 'second'); window.select_item('second')
        assert strip.combo.currentIndex() == 1
        fresh = TimelineItem('unassigned', 'm', 'video_1', 6, 2)
        window.project.timeline.append(fresh)
        window.timeline.select_ids({'unassigned'}, 'unassigned'); window.select_item('unassigned')
        assert strip.combo.currentIndex() == 0 and not strip.delete.isEnabled()
        window.timeline.select_ids({'v'}, 'v'); window.select_item('v')
        assert strip.combo.currentIndex() == 1
        QTest.mouseClick(window.inspector.video_preset_section.toggle, Qt.LeftButton)
        assert load_settings()[HIDDEN_KEY] is True
        window.close(); app.processEvents(); window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.DeferredDelete); app.processEvents()
        window = MainWindow(); window.autosave_timer.stop()
        assert len(window.inspector.video_presets.records) == 1
        assert window.inspector.video_presets.combo.currentIndex() == 0
        assert not window.inspector.video_preset_section.toggle.isChecked()
        report.update(passed=True, native_dropdown_multi_apply=True, one_step_undo_redo=True,
                      persisted_on_reopen=True, hide_show_persisted=True, themes=3)
    except Exception:
        report.update(passed=False, error=traceback.format_exc())
    finally:
        if window: window.close()
        if app:
            QThreadPool.globalInstance().waitForDone(10000); app.processEvents()
            for widget in app.topLevelWidgets(): widget.close(); widget.deleteLater()
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete); app.processEvents()
        (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report.get('passed') else 1
