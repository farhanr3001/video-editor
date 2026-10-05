"""Persistent presets for the regular media inspector's Video tab."""
import copy
import json
import math
from PySide6.QtCore import QIODevice, QSaveFile
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QDialog, QDialogButtonBox, QLineEdit, QMessageBox, QSizePolicy)
from .controls import SafeComboBox
from .editing import edit_only
from .model import Crop, uid

KEY = 'video_inspector_presets'
HIDDEN_KEY = 'video_inspector_presets_hidden'
NUMBERS = {
    'position_x': (-10000, 10000), 'position_y': (-10000, 10000),
    'scale': (.01, 10), 'scale_y': (.01, 10), 'rotation': (-180, 180),
    'anchor_x': (-4000, 4000), 'anchor_y': (-4000, 4000),
    'pitch': (-80, 80), 'yaw': (-80, 80),
    'crop_left': (0, 8192), 'crop_right': (0, 8192),
    'crop_top': (0, 8192), 'crop_bottom': (0, 8192),
    'crop_softness': (0, 100), 'opacity': (0, 100), 'background_strength': (0, 100),
}
BOOLEANS = ('scale_linked', 'flip_horizontal', 'flip_vertical',
            'retain_image_position', 'background_enabled')
TRANSFORM = ('scale', 'scale_y', 'rotation', 'anchor_x', 'anchor_y', 'pitch', 'yaw',
             'scale_linked', 'flip_horizontal', 'flip_vertical')


def validate(values):
    if not isinstance(values, dict): raise ValueError('Invalid preset properties')
    result = {}
    for key, (low, high) in NUMBERS.items():
        value = values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Invalid preset value: ' + key)
        result[key] = max(low, min(high, float(value)))
    for key in BOOLEANS:
        if not isinstance(values.get(key), bool): raise ValueError('Invalid preset flag: ' + key)
        result[key] = values[key]
    if values.get('composite_mode') not in ('Normal', 'Add', 'Multiply', 'Screen'):
        raise ValueError('Invalid composite mode')
    result['composite_mode'] = values['composite_mode']
    return result


def compatible(project, item):
    media = project.media_by_id(item.media_id) if item else None
    return bool(item and item.track in project.video_tracks and
                item.role not in ('title', 'graphic') and media and media.kind in ('video', 'image'))


def capture(panel, item):
    values = {key: panel.property_value(item, key) for key in
              ('position_x', 'position_y', 'crop_left', 'crop_right', 'crop_top', 'crop_bottom')}
    values.update({key: getattr(item.transform, key) for key in TRANSFORM})
    values['scale_y'] = item.transform.effective_scale_y
    values.update(crop_softness=item.crop_softness, retain_image_position=item.retain_image_position,
                  composite_mode=item.composite_mode, opacity=item.opacity)
    background = next((e for e in item.effects if e.get('inspector_background_blur')), {})
    values.update(background_enabled=bool(background.get('enabled', False)),
                  background_strength=background.get('horizontal', 12.))
    return validate(values)


def apply(project, item, values):
    """Apply visible pixel values without inheriting the target's previous crop."""
    values = validate(values)
    item.transform = copy.deepcopy(item.transform)
    for key in TRANSFORM: setattr(item.transform, key, values[key])
    item.transform.x = .5 + values['position_x'] / project.settings.width
    item.transform.y = .5 - values['position_y'] / project.settings.height
    media = project.media_by_id(item.media_id)
    width, height = max(1, media.width), max(1, media.height)
    item.crop = Crop(values['crop_left'] / width, values['crop_top'] / height,
                     1 - (values['crop_left'] + values['crop_right']) / width,
                     1 - (values['crop_top'] + values['crop_bottom']) / height).clamped()
    for key in ('crop_softness', 'retain_image_position', 'composite_mode', 'opacity'):
        setattr(item, key, values[key])
    background = next((e for e in item.effects if e.get('inspector_background_blur')), None)
    if background is None and (values['background_enabled'] or values['background_strength'] != 12.):
        background = dict(name='Gaussian Blur', inspector_background_blur=True,
                          linked=True, border='Reflect', blend=100.)
        item.effects.append(background)
    if background is not None:
        background.update(enabled=values['background_enabled'], horizontal=values['background_strength'],
                          vertical=values['background_strength'])


class PresetNameDialog(QDialog):
    def __init__(self, parent, records):
        super().__init__(parent); self.setWindowTitle('Save video preset'); self.setMinimumWidth(320)
        self.records = records
        layout = QVBoxLayout(self); layout.addWidget(QLabel('Enter preset name'))
        self.name = QLineEdit(); self.name.setMaxLength(80); layout.addWidget(self.name)
        self.note = QLabel(); self.note.setWordWrap(True); layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save = buttons.button(QDialogButtonBox.Save)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.name.textChanged.connect(self.refresh); self.refresh()

    def refresh(self):
        name = self.name.text().strip()
        duplicate = any(r['name'].casefold() == name.casefold() for r in self.records)
        self.note.setText('A preset with that name already exists.' if duplicate else '')
        self.save.setEnabled(bool(name) and not duplicate)

    def accept(self):
        self.refresh()
        if self.save.isEnabled(): super().accept()


class VideoPresetStrip(QWidget):
    def __init__(self, panel):
        super().__init__(panel); self.panel = panel; self.window = panel.window; self.records = []
        layout = QVBoxLayout(self); layout.setContentsMargins(8, 8, 8, 6); layout.setSpacing(5)
        buttons = QHBoxLayout(); buttons.setSpacing(6)
        self.save = QPushButton('Save preset'); self.delete = QPushButton('Delete preset')
        buttons.addWidget(self.save); buttons.addWidget(self.delete); layout.addLayout(buttons)
        self.combo = SafeComboBox(); self.combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.combo.setToolTip('Apply the preset to all selected, unlocked video/image clips.')
        layout.addWidget(self.combo)
        self.save.setToolTip('Save the inspected clip’s Video-tab settings.')
        self.save.clicked.connect(self.save_preset); self.delete.clicked.connect(self.delete_preset)
        self.combo.activated.connect(self.apply_selected)
        self.reload()

    def reload(self, selected=None):
        records = []
        raw = self.window.settings.get(KEY, [])
        if isinstance(raw, list):
            for record in raw[:200]:
                try:
                    name, identity = record['name'], record['id']
                    if not isinstance(name, str) or not name.strip() or len(name) > 80: continue
                    if not isinstance(identity, str) or not identity or len(identity) > 80: continue
                    if any(r['id'] == identity or r['name'].casefold() == name.strip().casefold() for r in records): continue
                    records.append(dict(id=identity, name=name.strip(), values=validate(record['values'])))
                except (KeyError, TypeError, ValueError): continue
        self.records = records
        self.combo.blockSignals(True); self.combo.clear()
        self.combo.addItem('No preset selected' if records else 'No presets saved', None)
        for record in records: self.combo.addItem(record['name'], record['id'])
        self.combo.setCurrentIndex(max(0, self.combo.findData(selected)))
        self.combo.blockSignals(False); self.refresh()

    def current(self):
        return next((r for r in self.records if r['id'] == self.combo.currentData()), None)

    def refresh(self):
        primary = self.window.project.item_by_id(self.panel.item_id)
        valid = compatible(self.window.project, primary)
        editable = getattr(self.window, 'current_page', 0) == 0
        self.save.setEnabled(valid and editable)
        self.combo.setEnabled(valid and editable and bool(self.records))
        self.delete.setEnabled(valid and editable and self.current() is not None)

    def save_preferences(self, changes):
        # Atomic feature-local preference save; do not truncate existing settings
        # or update the in-memory dropdown if the disk write fails.
        from .config import SETTINGS_PATH
        settings = dict(self.window.settings); settings.update(changes)
        content = json.dumps(settings, indent=2, ensure_ascii=False).encode('utf-8')
        file = QSaveFile(str(SETTINGS_PATH)); SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not file.open(QIODevice.WriteOnly): raise OSError(file.errorString())
        if file.write(content) != len(content):
            file.cancelWriting(); raise OSError(file.errorString())
        if not file.commit(): raise OSError(file.errorString())
        self.window.settings.update(changes)

    def persist(self, records, selected=None):
        self.save_preferences({KEY: records}); self.reload(selected)

    def expansion_changed(self, expanded):
        try: self.save_preferences({HIDDEN_KEY: not expanded})
        except OSError as error:
            section = self.panel.video_preset_section
            section.toggle.blockSignals(True); section.toggle.setChecked(not expanded)
            section.toggle.blockSignals(False); section._toggle(not expanded)
            QMessageBox.warning(self, 'Preset visibility could not be saved', str(error))

    def write(self, records, selected=None):
        try: self.persist(records, selected)
        except OSError as error:
            QMessageBox.warning(self, 'Preset could not be saved', str(error))
            return False
        return True

    @edit_only
    def save_preset(self):
        item = self.window.project.item_by_id(self.panel.item_id)
        if not compatible(self.window.project, item): return
        values = capture(self.panel, item); current = self.current()
        if current:
            dialog = QMessageBox(self); dialog.setWindowTitle('Save video preset')
            dialog.setText('Overwrite current preset?'); dialog.setInformativeText(current['name'])
            overwrite = dialog.addButton('Overwrite', QMessageBox.AcceptRole)
            new = dialog.addButton('Save as new', QMessageBox.ActionRole)
            dialog.addButton(QMessageBox.Cancel); dialog.exec()
            if dialog.clickedButton() is overwrite:
                records = copy.deepcopy(self.records)
                next(r for r in records if r['id'] == current['id'])['values'] = values
                self.write(records, current['id']); return
            if dialog.clickedButton() is not new: return
        if len(self.records) >= 200:
            QMessageBox.information(self, 'Video presets', 'Remove an unused preset before saving another.'); return
        dialog = PresetNameDialog(self, self.records)
        if dialog.exec() != QDialog.Accepted: return
        record = dict(id=uid(), name=dialog.name.text().strip(), values=values)
        self.write([*copy.deepcopy(self.records), record], record['id'])

    @edit_only
    def delete_preset(self):
        current = self.current()
        if current is None: return
        if QMessageBox.question(self, 'Delete video preset', 'Delete preset "' + current['name'] + '"?',
                                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes: return
        self.write([copy.deepcopy(r) for r in self.records if r['id'] != current['id']])

    @edit_only
    def apply_selected(self, index):
        self.combo.setCurrentIndex(index); self.refresh(); current = self.current()
        if current is None: return
        project = self.window.project
        targets = [item for item in self.panel.targets(False) if compatible(project, item)]
        if not targets: return
        values = validate(current['values'])
        for item in targets: apply(project, item, values)
        self.panel.changed.emit()
