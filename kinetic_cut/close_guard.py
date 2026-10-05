"""Unsaved document protection before any editor shutdown actions."""
import json
from PySide6.QtWidgets import QApplication, QMessageBox
DIAGNOSTIC_CLEANUP = False


def document_key(project):
    data = project.to_dict()
    def clean(body):
        for field in ('modified_at', 'playhead', 'path'):
            body.pop(field, None)
        for media in body.get('media', []):
            media.pop('thumbnail', None)
            if media.get('compound'):
                media.pop('path', None)  # Regenerated preview, not the source.
                clean(media['compound'])
    clean(data)
    return json.dumps(data, sort_keys=True, default=str)


def mark_saved(window, document=None):
    window._saved_close_key = document_key(document or window.compounds.root())


def confirm_close(window):
    # Explicit fixture cleanup only; normal launches never set this property.
    if DIAGNOSTIC_CLEANUP or QApplication.instance().property('kineticTestDiscardUnsaved'):
        return True
    window.flush_text_edit()
    document = window.compounds.root()
    if not document.path and not (document.timeline or document.captions):
        return True
    if document.path and getattr(window, '_saved_close_key', None) == document_key(document):
        return True
    box = QMessageBox(window)
    box.setWindowTitle('Save changes before closing?')
    box.setIcon(QMessageBox.Warning)
    box.setText(f'Save changes to “{document.name}”?')
    box.setInformativeText('Your unsaved changes will be lost if you close without saving.')
    box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
    box.setDefaultButton(QMessageBox.Save)
    box.setEscapeButton(QMessageBox.Cancel)
    answer = box.exec()
    if answer == QMessageBox.Save:
        return bool(window.save_project())
    return answer == QMessageBox.Discard
