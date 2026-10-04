"""Lightweight desktop bootstrap: show progress before loading the editor."""
import logging
import os
from logging.handlers import RotatingFileHandler
import sys
from PySide6.QtCore import Qt, QRectF, QEventLoop, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget, QMessageBox


class StartupSplash(QWidget):
    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setWindowTitle("Kinetic Cut — Loading")
        self.setFixedSize(740, 390)
        self.progress = 0
        self.stage = "Starting workspace"
        self.setAccessibleName("Kinetic Cut startup progress")

    def report(self, progress, stage):
        self.progress, self.stage = progress, stage
        self.setAccessibleDescription(f"{progress}% · {stage}")
        self.repaint()
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, 740, 390)
        gradient.setColorAt(0, QColor("#17212d"))
        gradient.setColorAt(1, QColor("#101318"))
        p.fillRect(self.rect(), gradient)
        # Original motion-strip artwork, painted at native display resolution.
        p.save()
        p.translate(520, 165)
        p.rotate(-24)
        for row, color in enumerate(("#557da2", "#719b8b", "#d37c69")):
            for col, width in enumerate((82, 110, 68, 94)):
                rect = QRectF(col*118-155, row*56-85, width, 38)
                shade = QColor(color); shade.setAlpha(80 + col*23)
                p.setPen(QPen(QColor("#48505a"), 1)); p.setBrush(shade)
                p.drawRoundedRect(rect, 4, 4)
                p.setPen(QPen(QColor(235, 241, 247, 40), 1))
                for i in range(7):
                    x = rect.left()+10+i*8
                    p.drawLine(int(x), int(rect.center().y()-4-i%3*3), int(x), int(rect.center().y()+4+i%3*3))
        p.restore()
        p.fillRect(QRectF(44, 50, 27, 4), QColor("#ed806f"))
        p.setPen(QColor("#e8edf3")); p.setFont(QFont("Segoe UI", 29, QFont.DemiBold))
        p.drawText(QRectF(44, 85, 440, 64), "Kinetic Cut")
        p.setPen(QColor("#aebac8")); p.setFont(QFont("Segoe UI", 11))
        p.drawText(QRectF(46, 152, 400, 30), "YOUR MOMENTS. READY TO SHARE.")
        p.setFont(QFont("Segoe UI", 10)); p.setPen(QColor("#d4dce6"))
        p.drawText(QRectF(46, 292, 600, 25), self.stage)
        p.setPen(QColor("#93a0ae")); p.drawText(QRectF(646, 292, 48, 25), Qt.AlignRight, f"{self.progress}%")
        p.fillRect(QRectF(46, 326, 648, 3), QColor("#303944"))
        p.fillRect(QRectF(46, 326, 648*self.progress/100, 3), QColor("#e47f6c"))
        p.setFont(QFont("Segoe UI", 8)); p.setPen(QColor("#8e9bab"))
        p.drawText(QRectF(46, 346, 600, 20), "EDIT  /  CAPTION  /  DELIVER")
        p.setPen(QPen(QColor("#39414b"), 1)); p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))


def run(selftest_output=None, native_window_test=False):
    import threading,time,json
    from pathlib import Path
    started=time.monotonic(); audit=[]; beats=[]
    if selftest_output is not None:
        sys.addaudithook(lambda event,args:audit.append(str(args[1])) if event=='subprocess.Popen' else None)
    from .process import install_desktop_process_policy
    install_desktop_process_policy()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Kinetic Cut")
    app.setOrganizationName("Kinetic Cut")
    window_audit = None
    native_audit = None
    if selftest_output is not None:
        from .window_audit import WindowShowAudit
        window_audit = WindowShowAudit(app)
        if native_window_test and sys.platform == 'win32':
            from .window_audit import NativeWindowShowAudit
            native_audit = NativeWindowShowAudit()
    from PySide6.QtGui import QIcon
    from .icons import resource_path
    app.setWindowIcon(QIcon(str(resource_path("assets","kinetic-cut.svg"))))
    if sys.platform=="win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KineticCut.Editor")
    splash = StartupSplash()
    if window_audit is not None:window_audit.allow(splash)
    splash.show()
    splash.report(5, "Starting desktop services")
    from .config import DATA_DIR
    log_path = DATA_DIR / "application.log"
    handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    def report_exception(kind, error, traceback):
        logging.error("Application error", exc_info=(kind, error, traceback))
        QMessageBox.critical(app.activeWindow(), "Kinetic Cut", f"An unexpected error occurred. Your autosave is preserved.\n\n{error}\n\nDetails: {log_path}")
    sys.excepthook = report_exception
    loaded={}; ready=threading.Event()
    def import_modules():
        try:
            from .ui import MainWindow
            from .theme import STYLESHEET
            loaded.update(window=MainWindow,theme=STYLESHEET)
        except Exception:loaded['error']=sys.exc_info()
        finally:ready.set()
    splash.report(15, "Loading playback and rendering modules")
    # Imports are I/O-heavy and may load native DLLs. Keep them off the GUI
    # thread; construction of every widget still happens on the GUI thread.
    loader=threading.Thread(target=import_modules,name='KineticStartup',daemon=True)
    timer=QTimer(splash); timer.setInterval(40)
    def advance():
        beats.append(time.monotonic()-started)
        if not ready.is_set():
            splash.report(min(35,15+int((time.monotonic()-started)*5)),'Loading playback and rendering modules'); return
        timer.stop()
        try:
            from .config import load_settings
            from .theme import get_theme_stylesheet
            saved_theme = load_settings().get("ui_theme", "default")
            splash.report(38, "Applying workspace theme"); app.setStyle('Fusion'); app.setStyleSheet(get_theme_stylesheet(saved_theme))
            window=loaded['window'](startup_progress=splash.report); app._kinetic_window=window
            if window_audit is not None:window_audit.allow(window)
            splash.report(100,'Workspace ready'); window.show(); QTimer.singleShot(0,splash.close)
            # No networking during source/isolated diagnostics or normal editing.
            if getattr(sys, 'frozen', False) and selftest_output is None and not os.environ.get('KINETIC_CUT_HOME'):
                QTimer.singleShot(2500, lambda: window.check_for_updates(startup=True))
            if {'--enable-mcp','--connect-codex','--connect-antigravity'}.intersection(sys.argv):
                from .assistant import configure_startup_connection
                configure_startup_connection(window,sys.argv)
            if selftest_output is not None:
                def finish_test():
                    QApplication.processEvents()
                    native_startup = list(native_audit.events) if native_audit else []
                    # Windows injects input-indicator windows into this host's
                    # GUI processes. Record these separately; they are not Qt
                    # controls or editor-created subprocess windows.
                    input_indicators = [e for e in native_startup if e['window_class'] in ('UAC_InputIndicatorOverlayWnd', 'UAC Input Indicator')]
                    unexpected_native = [e for e in native_startup if e not in input_indicators and e['title'] not in ('Kinetic Cut', 'Kinetic Cut — Loading')]
                    exercised = []
                    if native_window_test:
                        from .startup_window_diagnostics import workflows
                        exercised = workflows(window, window_audit)
                    window.grab().save(str(Path(selftest_output)/'startup-workspace.png'))
                    report=dict(passed=not window_audit.unexpected and not unexpected_native,seconds=time.monotonic()-started,
                                event_loop_ticks=len(beats),subprocesses=audit,
                                window_shows=window_audit.events,unexpected_windows=window_audit.unexpected,
                                native_startup_shows=native_startup,unexpected_native_startup=unexpected_native,
                                platform_input_indicators=input_indicators,
                                native_window_test=native_window_test,workflows=exercised,
                                frozen=bool(getattr(sys,'frozen',False)))
                    if native_audit:native_audit.close()
                    (Path(selftest_output)/'report.json').write_text(json.dumps(report,indent=2)); window.close(); app.exit(0 if report['passed'] else 1)
                QTimer.singleShot(300,finish_test)
        except Exception:
            splash.close()
            if selftest_output is not None:
                import traceback
                (Path(selftest_output)/'report.json').write_text(json.dumps(dict(passed=False,error=traceback.format_exc()),indent=2)); app.exit(1)
            else:report_exception(*sys.exc_info()); app.exit(1)
    timer.timeout.connect(advance); timer.start(); loader.start()
    return app.exec()
