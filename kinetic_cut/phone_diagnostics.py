"""Isolated visual/process checks. Never transfers user media or claims hardware QA."""
def run(output):
    import json
    import os
    import sys
    import time
    from pathlib import Path
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    os.environ['KINETIC_CUT_HOME'] = str(output / 'home')
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase
    from .ui import MainWindow
    from .theme import STYLESHEET
    from .workspace import set_page
    from .phone_process import PhoneRequest, tool_path
    app = QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
    for font in ('arial.ttf', 'arialbd.ttf', 'segoeui.ttf', 'segoeuib.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / font))
    window = MainWindow(); window.resize(1500, 860); window.show(); window.autosave_timer.stop()
    page = window.phone_connect; page.loaded = True
    report = dict(frozen=bool(getattr(sys, 'frozen', False)), checks={}, hardware_transfer_tested=False)
    try:
        set_page(window, 2); app.processEvents()
        window.grab().save(str(output / 'iphone-page.png'))
        report['checks']['page_and_shortcuts'] = window.current_page == 2 and not window.shortcut_actions['play_pause'].isEnabled()
        report['checks']['iphone_capability_honesty'] = not page.mirror_button.isEnabled() and not page.send.isEnabled()
        page.platform = 'android'; page.platform_buttons['android'].setChecked(True); page.apply_platform_text()
        app.processEvents(); window.grab().save(str(output / 'android-page.png'))
        window.resize(1150, 700); app.processEvents(); window.grab().save(str(output / 'compact-page.png'))
        report['checks']['compact_file_controls'] = page.send.geometry().bottom() <= page.send.parentWidget().height()
        report['checks']['bundled_tools'] = all(Path(tool_path(window.settings, name)).is_file() for name in ('adb', 'scrcpy'))
        for platform in ('iphone', 'android'):
            result = []
            request = PhoneRequest(dict(platform=platform, op='discover', adb=tool_path(window.settings, 'adb')), page)
            request.finished.connect(lambda ok, value: result.append((ok, value))); request.start()
            deadline = time.monotonic() + 40
            while not result and time.monotonic() < deadline:
                app.processEvents(); time.sleep(.01)
            request.shutdown()
            report[platform + '_discovery'] = result
            # An actionable missing-driver error is valid; a missing packaged import/crash is not.
            report['checks'][platform + '_helper'] = bool(result) and (result[0][0] or 'Apple Mobile Device Service is unavailable' in str(result[0][1]))
        set_page(window, 0); app.processEvents()
        report['checks']['edit_restored'] = window.current_page == 0 and window.shortcut_actions['play_pause'].isEnabled()
        report['passed'] = all(report['checks'].values())
    except Exception:
        import traceback
        report['error'] = traceback.format_exc(); report['passed'] = False
    finally:
        window.close(); app.processEvents()
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1
