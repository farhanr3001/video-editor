"""Clip-local Custom Face authoring with exact-source scrubbing and guides."""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QSignalBlocker, QTimer
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QDialog, QDialogButtonBox,
                               QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QScrollArea, QSlider,
                               QSpinBox, QSplitter, QVBoxLayout, QWidget)

from .custom_face import CONTROLS, DEFAULTS, LIMITS, draw_guides, values
from .model import Project
from .theme_widgets import set_ui_style
from .vision_effects import frame_index, mesh_data
from .widgets import PreviewCanvas


class _ImageView(QWidget):
    def __init__(self):
        super().__init__()
        self.image = QImage()
        self.setMinimumSize(420, 280)

    def set_image(self, image):
        self.image = image
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if not self.image.isNull():
            size = self.image.size().scaled(self.size(), Qt.KeepAspectRatio)
            left = (self.width()-size.width())//2
            top = (self.height()-size.height())//2
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawImage(left,top,self.image.scaled(size,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        painter.end()


def _clock(seconds, fps):
    frames = round(max(0., seconds)*fps)
    return f'{frames//(fps*3600):02d}:{frames//(fps*60)%60:02d}:{frames//fps%60:02d}:{frames%fps:02d}'


def _decode_frame(path, kind, source_time, ffmpeg):
    if kind == 'image':
        image = QImage(path)
        if image.isNull():
            raise RuntimeError('The source image could not be opened.')
        return image.scaled(1280,1280,Qt.KeepAspectRatio,Qt.SmoothTransformation)
    from .process import run
    command = [ffmpeg,'-hide_banner','-loglevel','error','-ss',f'{source_time:.4f}',
               '-i',path,'-frames:v','1','-vf',
               'scale=1280:1280:force_original_aspect_ratio=decrease',
               '-f','image2pipe','-vcodec','png','-']
    result = run(command,capture_output=True,timeout=25)
    image = QImage()
    if result.returncode or not image.loadFromData(result.stdout,'PNG'):
        detail = result.stderr.decode(errors='replace')[-350:]
        raise RuntimeError('Could not decode this point of the clip. '+detail)
    return image


class CustomFaceDialog(QDialog):
    def __init__(self, window, media, item, analysis, existing=None):
        super().__init__(window)
        self.window_ = window
        self.media = copy.deepcopy(media)
        self.item = copy.deepcopy(item)
        self.analysis = copy.deepcopy(analysis)
        self.effect = copy.deepcopy(existing) if existing else {'name':'Custom Face','enabled':True}
        self.effect['morph'] = values(self.effect)
        try:
            self.effect['skin_strength'] = max(0, min(100, round(float(self.effect.get('skin_strength', 0)))))
        except (TypeError, ValueError, OverflowError):
            self.effect['skin_strength'] = 0
        colour = QColor(str(self.effect.get('skin_color', '#bd856b')))
        self.effect['skin_color'] = colour.name() if colour.isValid() else '#bd856b'
        self.fps = max(1,round(window.project.settings.fps))
        self.raw = QImage()
        self._preview_canvas = PreviewCanvas()
        self._preview_canvas.setParent(self)
        self._preview_canvas.hide()
        self._preview_canvas.set_project(Project(settings=copy.deepcopy(window.project.settings),
                                                 media=[self.media],timeline=[copy.deepcopy(self.item)]))
        self._closed = False
        self._decoding = False
        self._pending = None
        self._current = None
        self.setWindowTitle('Custom Face · '+media.name)
        self.setWindowModality(Qt.WindowModal)
        self.resize(1120,730)
        root = QVBoxLayout(self)
        title = QLabel('Custom Face')
        set_ui_style(title,'font-size:19px; font-weight:600;')
        root.addWidget(title)
        hint = QLabel('Scrub this clip, adjust facial features, and compare the original. Changes apply to this timeline clip only; Cancel leaves it untouched.')
        hint.setWordWrap(True)
        set_ui_style(hint,'color:@text_sub;')
        root.addWidget(hint)
        actions = QHBoxLayout()
        actions.addStretch()
        self.reset = QPushButton('Reset All')
        self.reset.setToolTip('Restore every facial feature and skin tint to its default value')
        self.reset.clicked.connect(self.reset_all)
        actions.addWidget(self.reset)
        root.addLayout(actions)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split,1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.view = _ImageView()
        left_layout.addWidget(self.view,1)
        playback = QHBoxLayout()
        self.before = QPushButton('Show original')
        self.before.setCheckable(True)
        self.before.toggled.connect(self.refresh_preview)
        playback.addWidget(self.before)
        self.guides = QCheckBox('Face guides')
        self.guides.setChecked(True)
        self.guides.toggled.connect(self.refresh_preview)
        playback.addWidget(self.guides)
        self.guide_group = QCheckBox('Selected feature only')
        self.guide_group.toggled.connect(self.refresh_preview)
        playback.addWidget(self.guide_group)
        playback.addStretch()
        left_layout.addLayout(playback)
        time_row = QHBoxLayout()
        self.time_label = QLabel()
        self.time_label.setMinimumWidth(110)
        time_row.addWidget(self.time_label)
        self.scrub = QSlider(Qt.Horizontal)
        self.scrub.setRange(0,max(0,round(item.duration*self.fps)))
        self.scrub.valueChanged.connect(self.seek)
        self.scrub.setObjectName('custom_face_scrubber')
        time_row.addWidget(self.scrub,1)
        self.end_label = QLabel(_clock(item.duration,self.fps))
        time_row.addWidget(self.end_label)
        left_layout.addLayout(time_row)
        self.feedback = QLabel('Loading source frame…')
        set_ui_style(self.feedback,'color:@text_sub;')
        left_layout.addWidget(self.feedback)
        split.addWidget(left)

        controls = QWidget()
        panel = QVBoxLayout(controls)
        self.rows = {}
        grouped = {}
        for key,label,section in CONTROLS:
            if section not in grouped:
                box = QGroupBox(section)
                layout = QFormLayout(box)
                reset_section = QPushButton('Reset '+section)
                reset_section.setToolTip('Restore the '+section.lower()+' sliders to zero')
                reset_section.clicked.connect(lambda _=False,s=section:self.reset_group(s))
                layout.addRow(reset_section)
                panel.addWidget(box)
                grouped[section] = layout
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0,0,0,0)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(*LIMITS[key])
            slider.setValue(round(self.effect['morph'][key]))
            spin = QSpinBox()
            spin.setRange(*LIMITS[key])
            spin.setSuffix(' %')
            spin.setValue(slider.value())
            spin.setFixedWidth(74)
            if key == 'eye_spacing':
                tip = 'Negative brings both eyes closer together; positive moves them farther apart.'
                slider.setToolTip(tip)
                spin.setToolTip(tip)
            slider.valueChanged.connect(lambda value,k=key:self.set_control(k,value))
            spin.valueChanged.connect(lambda value,k=key:self.set_control(k,value))
            row_layout.addWidget(slider,1)
            row_layout.addWidget(spin)
            grouped[section].addRow(label,row)
            self.rows[key] = (slider,spin,section)
        skin = QGroupBox('Skin colour')
        skin_form = QFormLayout(skin)
        self.color = QPushButton('Choose colour…')
        self.color.clicked.connect(self.pick_color)
        self.update_color_button()
        skin_form.addRow('Tint',self.color)
        self.skin_strength = QSlider(Qt.Horizontal)
        self.skin_strength.setRange(0,100)
        self.skin_strength.setValue(round(float(self.effect['skin_strength'])))
        self.skin_strength.valueChanged.connect(self.set_skin_strength)
        self.skin_value = QLabel(str(self.skin_strength.value())+' %')
        strength_row = QWidget()
        strength_layout = QHBoxLayout(strength_row)
        strength_layout.setContentsMargins(0,0,0,0)
        strength_layout.addWidget(self.skin_strength,1)
        strength_layout.addWidget(self.skin_value)
        skin_form.addRow('Strength',strength_row)
        reset_skin = QPushButton('Reset skin colour')
        reset_skin.clicked.connect(lambda:self.reset_group('Skin colour'))
        skin_form.addRow(reset_skin)
        panel.addWidget(skin)
        note = QLabel('Eye spacing: negative moves both eyes inward, positive moves them outward. Most features range from −100 to +100; nose size reaches +140 to prevent extreme warping. Skin tint covers the tracked face, not ears or neck, and is off at 0%. Tracking is hidden on frames where no face is detected.')
        note.setWordWrap(True)
        set_ui_style(note,'color:@text_sub;')
        panel.addWidget(note)
        panel.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumWidth(340)
        split.addWidget(scroll)
        split.setSizes([740,380])
        footer = QDialogButtonBox(QDialogButtonBox.Apply|QDialogButtonBox.Cancel)
        footer.button(QDialogButtonBox.Apply).setProperty('accent',True)
        footer.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        footer.rejected.connect(self.reject)
        root.addWidget(footer)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh_preview)
        self._decode_timer = QTimer(self)
        self._decode_timer.setSingleShot(True)
        self._decode_timer.timeout.connect(self.request_frame)
        self.finished.connect(self._finish)
        initial = max(0,min(self.scrub.maximum(),round((window.project.playhead-item.start)*self.fps)))
        self.scrub.setValue(initial)
        self.seek(initial)

    def _finish(self, _):
        self._closed=True
        self._preview_canvas.effect_cache.clear()
        self._preview_canvas.crop_cache.clear()
        self.window_.activateWindow()
        self.window_.timeline.viewport().setFocus()

    def set_control(self,key,value):
        slider,spin,_ = self.rows[key]
        with QSignalBlocker(slider):slider.setValue(value)
        with QSignalBlocker(spin):spin.setValue(value)
        self.effect['morph'][key]=value
        self._selected=key
        self._refresh_timer.start(20)

    def set_skin_strength(self,value):
        self.effect['skin_strength']=value
        self.skin_value.setText(str(value)+' %')
        self._selected='skin'
        self._refresh_timer.start(20)

    def update_color_button(self):
        color=QColor(self.effect['skin_color'])
        ink='#161616' if color.lightnessF()>.55 else '#ffffff'
        self.color.setStyleSheet(f'background:{color.name()}; color:{ink};')

    def pick_color(self):
        color=QColorDialog.getColor(QColor(self.effect['skin_color']),self,'Skin tint',
                                    QColorDialog.DontUseNativeDialog)
        if color.isValid():
            self.effect['skin_color']=color.name()
            self.update_color_button()
            if self.skin_strength.value()==0:
                self.skin_strength.setValue(50)
            self._refresh_timer.start(20)

    def reset_all(self):
        for section in ('Face','Eyes','Nose','Mouth','Skin colour'):
            self.reset_group(section)

    def reset_group(self,section):
        for key,_,group in CONTROLS:
            if group == section:
                self.set_control(key,DEFAULTS[key])
        if section == 'Skin colour':
            self.effect['skin_color'] = '#bd856b'
            self.update_color_button()
            self.skin_strength.setValue(0)
        self._refresh_timer.start(20)

    def seek(self,index):
        relative=index/self.fps
        self.time_label.setText(_clock(relative,self.fps))
        self._requested=index
        self._decode_timer.start(90)

    def request_frame(self):
        index=self._requested
        if self._decoding:
            self._pending=index
            return
        self._decoding=True
        self._current=index
        self.feedback.setText('Loading '+_clock(index/self.fps,self.fps)+'…')
        from .ui import Worker
        at=min(self.item.in_point+self.item.source_duration-1e-4,
               self.item.in_point+index/self.fps*self.item.speed)
        worker=Worker(_decode_frame,self.media.path,self.media.kind,at,
                      self.window_.settings.get('ffmpeg','ffmpeg'))
        worker.signals.result.connect(lambda image,n=index:self.frame_ready(n,image))
        worker.signals.error.connect(lambda detail,n=index:self.frame_error(n,detail))
        self.window_.start_worker(worker)

    def frame_ready(self,index,image):
        self._decoding=False
        if self._closed:
            return
        if index==self._requested:
            self.raw=image.convertToFormat(QImage.Format_RGBA8888)
            self._raw_index=index
            self.refresh_preview()
        if self._pending is not None and self._pending!=index:
            self._pending=None
            self.request_frame()
        else:
            self._pending=None

    def frame_error(self,index,detail):
        self._decoding=False
        if self._closed:
            return
        self.feedback.setText('Could not load this frame. Try another position in the clip.')
        if self._pending is not None and self._pending!=index:
            self._pending=None
            self.request_frame()

    def _framed_image(self, shown, mesh, detected):
        from .keyframes import evaluated
        from .visual_fx import evaluate_visual_fx, apply_visual_fx_to_transform
        project=self._preview_canvas.project
        project.playhead=self.item.start+shown/self.fps
        item=copy.deepcopy(self.item)
        item.effects=[copy.deepcopy(e) for e in item.effects if e.get('name')!='Custom Face']
        if not self.before.isChecked():
            effect=copy.deepcopy(self.effect)
            effect['analysis']=self.analysis
            effect['enabled']=True
            item.effects.append(effect)
        project.timeline=[item]
        item=evaluated(item,shown/self.fps)
        vfx=evaluate_visual_fx(item,shown/self.fps,project.settings.width,project.settings.height)
        if vfx.is_active:
            item=copy.copy(item)
            item.transform=copy.copy(item.transform)
            apply_visual_fx_to_transform(item.transform,vfx)
        width,height=max(1,project.settings.width),max(1,project.settings.height)
        scale=min(1.,900/max(width,height))
        output=QImage(max(1,round(width*scale)),max(1,round(height*scale)),
                      QImage.Format_ARGB32_Premultiplied)
        output.fill(Qt.black)
        frame_rect=QRectF(output.rect())
        canvas=self._preview_canvas
        target=(frame_rect if item.role=='background' else
                canvas._layer_rect(item,self.raw,frame_rect,item.role=='facecam'))
        prepared=canvas._prepare_layer_image(item,self.raw,target,frame_rect)
        if detected and self.guides.isChecked() and item.role!='background':
            prepared=prepared.copy()  # The raster cache must never retain guides.
            regions=None
            if self.guide_group.isChecked():
                section=self.rows.get(getattr(self,'_selected',''),(None,None,''))[2]
                regions={'Face':['Face'],'Eyes':['Left eye','Right eye'],
                         'Nose':['Nose'],'Mouth':['Mouth']}.get(section)
                if getattr(self,'_selected','')=='skin':regions=['Face']
            draw_guides(prepared,mesh,regions)
        painter=QPainter(output)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        canvas._draw_layer_item(painter,item,self.raw,target,frame_rect,prepared_override=prepared)
        painter.end()
        return output

    def refresh_preview(self):
        if self._closed or self.raw.isNull():
            return
        shown=getattr(self,'_raw_index',self.scrub.value())
        index=frame_index(self.analysis,self.item.in_point+shown/self.fps*self.item.speed)
        mesh=mesh_data(self.analysis['root'])[index]
        detected=bool(len(mesh) and mesh[0,0]==mesh[0,0])
        self.view.set_image(self._framed_image(shown,mesh,detected))
        self.feedback.setText('Face tracked · '+_clock(shown/self.fps,self.fps)
                              if detected else 'No face detected on this frame · effect hidden here')

    def result_effect(self):
        effect=copy.deepcopy(self.effect)
        effect['morph']=values(effect)
        effect['skin_strength']=max(0,min(100,int(effect['skin_strength'])))
        effect['skin_color']=QColor(effect['skin_color']).name()
        effect['analysis']=copy.deepcopy(self.analysis)
        effect['name']='Custom Face'
        effect['enabled']=True
        return effect
