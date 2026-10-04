"""Isolated native update-dialog and menu layout verification."""
import json
import os
from pathlib import Path
import sys


def run(output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    os.environ['KINETIC_CUT_HOME'] = str(output/'home')
    from PySide6.QtWidgets import QApplication, QPushButton
    from .theme_widgets import apply_application_theme
    from .updates import Release
    from .update_ui import UpdateDialog
    from .version import VERSION
    app = QApplication.instance() or QApplication([])
    release = Release('9.9.9', '', 'a'*64, 21_113_218,
                      'Preview fixture: improvements to editing and application updates.\n'*25,
                      incremental=True)
    checks = []
    for theme in ('default', 'final_cut_obsidian', 'ableton_gray'):
        apply_application_theme(theme)
        cases = (('current', dict(state='current', message=f'Installed version: {VERSION}')),
                 ('checking', dict(state='checking', message='Contacting GitHub for the latest release…')),
                 ('error', dict(state='error', message='Check your connection and try again.\nThe server could not be reached.')),
                 ('available', dict(release=release, startup=True)))
        for state, options in cases:
            for width in (400, 510):
                dialog = UpdateDialog(None, **options)
                dialog.resize(width, dialog.height()); dialog.show(); app.processEvents()
                assert dialog.width() == width
                for button in dialog.findChildren(QPushButton):
                    assert button.isVisible() and dialog.rect().contains(button.geometry())
                assert dialog.heading.geometry().bottom() < dialog.detail.geometry().top()
                if state == 'current':
                    assert dialog.height() <= 150
                    assert dialog.detail.y() - dialog.heading.geometry().bottom() <= 14
                if state == 'available':
                    assert dialog.notes.isVisible() and dialog.notes.height() <= 140
                dialog.grab().save(str(output/f'{theme}-{state}-{width}.png'))
                checks.append(dict(theme=theme, state=state, width=width, height=dialog.height()))
                dialog.close(); dialog.deleteLater(); app.processEvents()
    from .ui import MainWindow
    window = MainWindow(); window.show(); app.processEvents()
    menus = {a.text():a.menu() for a in window.menuBar().actions()}
    assert set(menus) == {'File', 'Edit', 'Workflow'}
    assert [a.text() for a in menus['Workflow'].actions()] == ['Settings…']
    assert 'Collect project and media…' not in [a.text() for a in menus['File'].actions()]
    assert 'UI Themes…' in [a.text() for a in menus['File'].actions()]
    window.grab().save(str(output/'workspace.png'))
    window.close(); app.processEvents()
    report = dict(passed=True, frozen=bool(getattr(sys, 'frozen', False)), dialogs=checks,
                  menus={key:[a.text() for a in menu.actions()] for key, menu in menus.items()})
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0
