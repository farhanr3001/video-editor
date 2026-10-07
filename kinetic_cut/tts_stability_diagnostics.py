"""Native TTS close/cancel endurance using isolated delayed-service fixtures."""
from __future__ import annotations

import gc
import json
import os
import sys
import threading
import time
import weakref
from pathlib import Path
from unittest.mock import patch


def run(output_dir):
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ["KINETIC_CUT_HOME"] = str(output / "home")
    from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QWidget
    from .dialog_jobs import active_dialog_threads, cancel_dialog_threads, wait_dialog_threads
    from .theme_widgets import apply_application_theme
    from .tts_dialog import TTSDialog
    from .tts_dialogue_dialog import TTSDialogueDialog
    import psutil

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    owner = QWidget()
    owner.setAttribute(Qt.WA_DontShowOnScreen)
    owner.show()
    process = psutil.Process()
    report = {"frozen": bool(getattr(sys, "frozen", False)), "platform": QApplication.platformName(),
              "scope": "Native delayed-service lifecycle fixtures; no external speech service/model download", "cases": []}
    workers = []
    deliveries = []

    def settle(until, timeout=4):
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(5)
        deadline = time.monotonic() + timeout
        timer.timeout.connect(lambda: loop.quit() if until() or time.monotonic() >= deadline else None)
        timer.start()
        loop.exec()
        timer.stop()
        if not until():raise AssertionError("A TTS thread did not settle")

    def sample():
        return {"rss_bytes": process.memory_info().rss, "handles": process.num_handles() if os.name == "nt" else process.num_fds(),
                "native_threads": process.num_threads(), "active_popup_jobs": len(active_dialog_threads())}

    try:
        for theme in ("default", "final_cut_obsidian", "ableton_gray"):
            apply_application_theme(theme)
            for kind, dialog_type in (("dialogue", TTSDialogueDialog), ("voiceover", TTSDialog)):
                function = "synthesize_dialogue_batches" if kind == "dialogue" else "synthesize_speech"
                module = "tts_dialogue_dialog" if kind == "dialogue" else "tts_dialog"
                release = threading.Event()
                started = threading.Event()
                def delayed(**kwargs):
                    started.set()
                    release.wait(3)
                    return "late-discarded.mp3"
                with patch(f"kinetic_cut.{module}.{function}", delayed):
                    dialog = dialog_type(owner, "This deliberately pending speech job can be cancelled safely.\n\nThe editor must remain open.")
                    dialog.setAttribute(Qt.WA_DontShowOnScreen)
                    dialog.show()
                    dialog.speechGenerated.connect(deliveries.append)
                    dialog.grab().save(str(output / f"{theme}-{kind}-ready.png"))
                    dialog._on_generate_clicked()
                    settle(started.is_set)
                    dialog.grab().save(str(output / f"{theme}-{kind}-generating.png"))
                    assert dialog.cancel_btn.isEnabled()
                    worker = dialog._generate_worker if kind == "dialogue" else dialog._active_worker
                    workers.append(weakref.ref(worker)); del worker
                    began = time.monotonic()
                    dialog.close()
                    elapsed = (time.monotonic() - began) * 1000
                    assert elapsed < 200 and active_dialog_threads()
                    dialog.deleteLater()
                    app.processEvents()
                    release.set()
                    settle(lambda: not active_dialog_threads())
                    report["cases"].append({"theme": theme, "kind": kind, "cancel_enabled": True,
                                           "x_close_ms": elapsed, "survived_closed_popup": True})
        gc.collect()
        report["before_endurance"] = sample()
        begin = time.monotonic()
        report["endurance_cycles"] = 60
        for index in range(report["endurance_cycles"]):
            kind = "dialogue" if index % 2 == 0 else "voiceover"
            module = "tts_dialogue_dialog" if kind == "dialogue" else "tts_dialog"
            function = "synthesize_dialogue_batches" if kind == "dialogue" else "synthesize_speech"
            dialog_type = TTSDialogueDialog if kind == "dialogue" else TTSDialog
            release = threading.Event()
            started = threading.Event()
            def delayed(**kwargs):
                started.set()
                release.wait(3)
                if index % 5 == 0:raise RuntimeError("Late canceled service failure")
                return "late-discarded.mp3"
            with patch(f"kinetic_cut.{module}.{function}", delayed):
                dialog = dialog_type(owner, "Repeated speech cancellation.")
                # close() on a never-shown QDialog does not enter its normal
                # rejection route. Exercise actual visible-dialog semantics
                # without flashing hundreds of test popups on the desktop.
                dialog.setAttribute(Qt.WA_DontShowOnScreen)
                dialog.show()
                dialog.speechGenerated.connect(deliveries.append)
                dialog._on_generate_clicked()
                dialog._on_generate_clicked()  # Repeated click is ignored while busy.
                settle(started.is_set)
                worker = dialog._generate_worker if kind == "dialogue" else dialog._active_worker
                workers.append(weakref.ref(worker)); del worker
                if index % 3 == 0:dialog.reject()
                elif index % 3 == 1:QTest.keyClick(dialog, Qt.Key_Escape)
                else:dialog.close()
                dialog.deleteLater()
                app.processEvents()
                release.set()
                settle(lambda: not active_dialog_threads())
        # A stopped native thread can still have its queued retirement and
        # deleteLater events pending. Drain those explicit Qt ownership events
        # before measuring Python retention, just as the outer app loop does.
        def released():
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            gc.collect()
            return all(ref() is None for ref in workers)
        settle(released)
        report["after_endurance"] = sample()
        report["endurance_seconds"] = time.monotonic() - begin
        report["late_insertions"] = len(deliveries)
        report["retained_workers"] = sum(ref() is not None for ref in workers)
        assert report["late_insertions"] == 0
        assert report["retained_workers"] == 0
        assert report["after_endurance"]["active_popup_jobs"] == 0
        report["passed"] = True
    except Exception as err:
        report["passed"] = False
        report["error"] = repr(err)
        from .dialog_jobs import _retained
        report["pending_lifetime_holders"] = len(_retained)
        report["worker_referrers"] = [
            {"worker_type": type(ref()).__name__,
             "referrers": [type(parent).__name__ + (":" + str([key for key, value in parent.items() if value is ref()]) if isinstance(parent, dict) else "")
                           for parent in gc.get_referrers(ref())]}
            for ref in workers if ref() is not None]
    finally:
        cancel_dialog_threads()
        report["threads_drained"] = wait_dialog_threads()
        owner.close()
        owner.deleteLater()
        app.processEvents()
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report.get("passed") and report["threads_drained"] else 1
