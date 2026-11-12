"""Playable tracking workspace with direct frame corrections and marker styling."""
import copy
import time
from pathlib import Path
from types import SimpleNamespace
from PySide6.QtCore import Qt, QTimer, QUrl, QEvent, Slot
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoFrame
from PySide6.QtWidgets import QPushButton, QScrollArea, QSplitter, QLineEdit, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QMenu
from .tracking_dialog import LegacyTrackingDialog


class TrackingWorkspace(LegacyTrackingDialog):
    def __init__(self, window, media, item, existing=None):
        self.player = None
        self.playing = False
        self.surface = None
        self._correction_originals={}
        self._source_loaded = False
        self._seek_retry_at=0.
        self._seek_target=None
        self._seek_attempts=0
        self._frame_rows=[]
        self._primed=False
        self._paused_reseek_target=None
        self._frame_clock=None
        self._frame_clock_busy=False
        self._frame_clock_failed=False
        self._play_seek_pending=None
        self._editor_stamp=None
        self._playback_source=getattr(window,'proxies',{}).get(media.id,media.path)
        import threading
        from PySide6.QtWidgets import QDialog
        from .tracking_effect import default_effect,valid
        QDialog.__init__(self,window)
        self.window_=window;self.media=copy.deepcopy(media);self.item=copy.deepcopy(item)
        self.effect=copy.deepcopy(existing) if existing else default_effect()
        self.anchors=copy.deepcopy(self.effect.get('anchors',self.effect.get('analysis',{}).get('anchors',[])))
        self.cancel=threading.Event();self._closed=False;self._busy=False;self._decoding=False
        self.raw=QImage();self._shown_time=None
        self.dirty_track=not valid(self.effect,self.media);self.fps=max(1,window.project.settings.fps)
        self.base_analysis=copy.deepcopy(self.effect.get('analysis',{}))
        self.setWindowTitle('Object Tracking · '+media.name);self.setWindowModality(Qt.WindowModal)
        from .tracking_workspace_ui import build_workspace
        build_workspace(self)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.poll)
        from .quick_surface import enabled, Surface
        if enabled():
            self.surface = Surface(self.view, 'GpuTrackingMonitor.qml')
            self.surface.root.setProperty('aspect', max(1, media.width)/max(1, media.height))
            self.surface.root.setProperty('still', media.kind == 'image')
            self.video = self.surface.item('trackingVideo')
            texture_scale=min(1.,2048/max(1,media.width,media.height))
            self.video.setProperty('pixelWidth',max(2,round(media.width*texture_scale)))
            self.video.setProperty('pixelHeight',max(2,round(media.height*texture_scale)))
            self.sink = self.video.property('sink')
            self.sink.videoFrameChanged.connect(self.frame_arrived)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setMuted(True)
            self.audio.setVolume(getattr(window.transport,'monitor_gain',1.))
            self.player.setAudioOutput(self.audio)
            self.player.setVideoSink(self.sink)
            self.player.setPlaybackRate(item.speed)
            self.player.mediaStatusChanged.connect(self.loaded)
            self.player.errorOccurred.connect(lambda _, message:self.info.setText(message))
            from .media_source import set_media_source
            if media.kind == 'image':
                self.surface.item('trackingPhoto').setProperty('source', QUrl.fromLocalFile(media.path))
            else:set_media_source(self.player, QUrl.fromLocalFile(self._playback_source))
            placeholder_scale=min(1.,1024/max(1,media.width,media.height))
            self.view.image = QImage(max(1,round(media.width*placeholder_scale)),max(1,round(media.height*placeholder_scale)),QImage.Format_RGB32)
            self.view.image.fill(Qt.black)
            self.surface.geometry(self.view.rect())
            self.surface.container.show()
            self.timer.start()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        self.finished.connect(self.close_monitor)
        self.before.setChecked(False)
        self.view.setCursor(Qt.CrossCursor)
        if self.surface:
            self.surface.container.setCursor(Qt.CrossCursor)
            self.surface.view.setCursor(Qt.CrossCursor)
        self.refresh_anchors();self.set_busy(False)
        if not self.dirty_track:self.show_ready()
        start=max(0,min(item.duration,window.project.playhead-item.start))
        self.timeline.setValue(round(start*self.fps));self.seek(self.timeline.value())
        self.resize(1380,900)

    def analysis_item(self):
        item=copy.copy(self.item)
        item.in_point+=self.range_start.value()*item.speed
        item.duration=max(.001,self.range_end.value()-self.range_start.value())
        return item

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_responsive()
        self.sync_monitor_geometry()

    def sync_monitor_geometry(self):
        # Layout must never wait for decoder admission. A missed first frame
        # previously left the native window at its pre-layout320x220 size.
        if self.surface:self.surface.geometry(self.view.rect())

    def update_responsive(self,*_):
        if not hasattr(self,'_ui_cards'):return
        compact=self.height()<820
        expanded=self.guide_toggle.isChecked()
        self.guide.setVisible(expanded and not compact)
        self.guide_summary.setVisible(expanded and compact)
        self._ui_cards['status'].header.setVisible(not compact)

    def set_preview_tool(self,tool):
        self.view.set_tool(tool)
        self.sync_preview_cursor()
        self.refresh_preview()

    def sync_preview_cursor(self):
        if self.surface:
            self.surface.container.setCursor(self.view.cursor())
            self.surface.view.setCursor(self.view.cursor())

    def edit_marker_geometry(self,values):
        if self._busy:return
        self.marker_editor.apply_geometry(values)

    def range_changed(self,start_changed):
        from .object_tracking import MAX_ANALYSIS_DURATION
        limit=MAX_ANALYSIS_DURATION/max(.0001,self.item.speed)
        start,end=self.range_start.value(),self.range_end.value()
        step=min(.001,self.item.duration)
        if start_changed:
            if start>=end:end=min(self.item.duration,start+min(10,limit))
            if end<=start:start=max(0,end-step)
            end=min(end,start+limit)
        else:
            if end<=start:start=max(0,end-min(10,limit))
            if end<=start:end=min(self.item.duration,start+step)
            start=max(start,end-limit)
        for field,value in ((self.range_start,start),(self.range_end,end)):
            field.blockSignals(True);field.setValue(value);field.blockSignals(False)
        self.update_guidance()

    def update_guidance(self):
        if not hasattr(self,'range_hint'):return
        if self._busy:
            self.range_hint.setText('Analysing… Cancel keeps the clip unchanged.')
        else:
            self.range_hint.setText('Maximum 30 source seconds per analysis.')

    def loaded(self, status):
        if self._closed:return
        if status == QMediaPlayer.LoadedMedia and not self._source_loaded:
            self._source_loaded=True
            self.request_frame()

    def request_frame_clock(self):
        if not self.player or self.media.kind!='video' or self._frame_clock_busy or self._frame_clock_failed or self._closed:return
        at=self.source_time()
        if self._frame_clock and self._frame_clock['start']-1e-7<=at<=self._frame_clock['end']+1e-7:return
        from .tracking_clock import read_clock
        from .ui import Worker
        start=max(self.item.in_point,at-5.)
        end=min(self.item.in_point+self.item.source_duration,start+30.)
        self._frame_clock_busy=True
        worker=Worker(read_clock,self._playback_source,start,end)
        def done(clock):
            self._frame_clock_busy=False
            if self._closed:return
            self._frame_clock=clock
            if not self.playing:self.seek(self.timeline.value())
            self.request_frame_clock()
        def failed(_):
            self._frame_clock_busy=False
            self._frame_clock_failed=True
            # The original decoder/error path still works for metadata that
            # cannot be indexed. Do not create an unbounded retry worker.
        worker.signals.result.connect(done);worker.signals.error.connect(failed)
        self.window_.start_worker(worker)

    def frame_target(self):
        from .tracking_clock import frame_time
        return frame_time(self._frame_clock,self.source_time())

    @Slot(QVideoFrame)
    def frame_arrived(self,frame):
        if self._closed or not frame.isValid() or not self.player:return
        self._primed=True
        if self.playing:return
        # A16ms poll can miss the requested60fps frame during shader/layout
        # work. Stop the priming clock on its first notification, then seek
        # paused; the requested frame now remains available until GUI admission.
        self.player.pause()
        target=round(self.frame_target()*1000000)
        latest=self.sink.videoFrame()
        if not latest.isValid() or latest.endTime()<=target or latest.startTime()>target+1000:
            if self._paused_reseek_target!=target:
                self._paused_reseek_target=target
                self._decode_timer.start(0)

    def request_frame(self):
        if self.player:
            if self._closed or self.playing:return
            self._decoding=True
            if getattr(self,'video',None):self.video.setProperty('admitted',False)
            if getattr(self,'audio',None):self.audio.setMuted(True)
            target=round(self.frame_target()*1000)+1
            self._seek_attempts=self._seek_attempts+1 if target==self._seek_target else 1
            self._seek_target=target
            self._seek_retry_at=time.monotonic()
            self.player.setPosition(target)
            # Once primed, a paused Qt decoder can seek without advancing its
            # clock. Only prime/retry by playing, then pause at an admitted frame.
            if not self._primed:self.player.play()
            else:self.player.pause()
        else:super().request_frame()

    def toggle_play(self):
        if self._busy or not self.player or self.media.kind == 'image':return
        if not self.playing and self.timeline.value()==self.timeline.maximum():
            self.timeline.setValue(0)
            self._decode_timer.stop()
            self.player.setPosition(round(self.item.in_point*1000)+1)
        if not self.playing and (self._decode_timer.isActive() or not self.settled_frame()):
            # Play must consume the latest requested thumb, not cancel a seek
            # still waiting in the coalescing timer and resume an older clock.
            self.request_frame()
            self._play_seek_pending=round(self.frame_target()*1000000)
        self._decode_timer.stop()
        self.playing = not self.playing
        if self.playing:
            self.player.play()
        else:self.player.pause()
        self.play_button.setText('Pause' if self.playing else 'Play')

    def pause_for_edit(self):
        self._play_seek_pending=None
        if not self.playing:return
        self.playing=False
        if self.player:self.player.pause()
        self.play_button.setText('Play')

    def seek(self,index):
        self.pause_for_edit()
        self._paused_reseek_target=None
        if self.player:self.player.pause()
        if self.surface:self.video.setProperty('admitted',False)
        if self.player:self._decoding=True
        self.request_frame_clock()
        self.track_button.setEnabled(False);self.anchor_button.setEnabled(False);self.view.setEnabled(False)
        self.update_time_label()
        # Throttle, do not restart a debounce on each mouse move: long drags
        # still show fresh frames, and each request reads the latest thumb value.
        if not self._decode_timer.isActive():self._decode_timer.start(33)
        if hasattr(self,'marker_editor'):self.marker_editor.refresh()

    def update_time_label(self):
        self.time_label.setText(f'{self.timeline.value()/self.fps:.2f}s / {self.item.duration:.2f}s')

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape and hasattr(self,'preview_expand') and self.preview_expand.isChecked():
            self.preview_expand.setChecked(False);event.accept();return
        if not isinstance(self.focusWidget(),QLineEdit):
            if event.key()==Qt.Key_Space:
                self.toggle_play();event.accept();return
            if event.key() in (Qt.Key_Left,Qt.Key_Right):
                self.step(-1 if event.key()==Qt.Key_Left else 1);event.accept();return
        super().keyPressEvent(event)

    def eventFilter(self,obj,event):
        if obj is getattr(self,'view',None) and event.type() in (QEvent.Resize,QEvent.Show):self.sync_monitor_geometry()
        if obj is getattr(self,'anchor_list',None) and event.type()==QEvent.KeyPress and event.key()==Qt.Key_Space and event.modifiers()==Qt.NoModifier:
            self.toggle_play();event.accept();return True
        if hasattr(self,'anchor_list') and obj in (self.anchor_list,self.anchor_list.viewport()) and event.type()==QEvent.Wheel and self.selected_frame_times():
            self.timeline.navigate_frames(event.angleDelta().y());event.accept();return True
        if event.type()==QEvent.MouseButtonPress and self._frame_rows and hasattr(self,'marker_editor'):
            from PySide6.QtWidgets import QWidget
            if isinstance(obj,QWidget) and (obj is self or self.isAncestorOf(obj)):
                keep=(self.marker_panel,self.anchor_list,self.timeline,self.anchor_button,self.remove_frame_button,self.clear_button)
                keep_selection=any(obj is w or w.isAncestorOf(obj) for w in keep)
                if obj is self.view and self.view.selected():keep_selection=bool(self.view.hit(event.position(),self.view.selected()))
                if not keep_selection:self.clear_frame_selection()
        return super().eventFilter(obj,event)

    def step(self, delta):
        self.playing = False
        if self.player:self.player.pause()
        self.play_button.setText('Play')
        self.timeline.setValue(self.timeline.value()+delta)

    def poll(self):
        if self._closed:return
        self.sync_monitor_geometry()
        # Keep the decoder source fixed for this dialog's lifetime. Replacing
        # it mid-analysis blocks inside Qt's synchronous decoder teardown.
        if self.media.kind != 'image':
            frame = self.sink.videoFrame()
            if not frame.isValid():
                ready=self.player.mediaStatus() in (QMediaPlayer.LoadedMedia,QMediaPlayer.BufferedMedia)
                if ready and self._seek_attempts<3 and time.monotonic()-self._seek_retry_at>.3:
                    self.request_frame()
                return
            target=round(self.frame_target()*1000000)
            if not self.playing and (frame.endTime()<=target or frame.startTime()>target+1000):
                # Startup shader/layout work can outlast the first sought
                # frame. Retry that paused seek after the GUI has caught up.
                if time.monotonic()-self._seek_retry_at>.3:
                    self.player.pause()
                    if self._seek_attempts<3:self.request_frame()
                return
            if self.playing and self._play_seek_pending is not None:
                if frame.endTime()<=self._play_seek_pending:return
                self._play_seek_pending=None
            self._primed=True
            self.video.setProperty('admitted', True)
        if getattr(self,'audio',None):self.audio.setMuted(not self.playing)
        if self.playing and not self.timeline.isSliderDown():
            index = round((self.player.position()/1000-self.item.in_point)/self.item.speed*self.fps)
            self.timeline.blockSignals(True)
            self.timeline.setValue(index)
            self.timeline.blockSignals(False)
            if index >= self.timeline.maximum():self.step(0)
        elif self.player.playbackState() == QMediaPlayer.PlayingState:self.player.pause()
        self.raw = self.view.image
        self._shown_time = self.source_time()
        self._decoding = False
        from .object_tracking import sample
        point = sample(self.effect.get('analysis', {}), self.source_time())
        if point and self.view.drag_start is None:self.view.region = list(point['box'])
        self.update_time_label()
        if self._editor_stamp!=self.timeline.value():
            self._editor_stamp=self.timeline.value();self.marker_editor.refresh()
        self.refresh_preview()
        self.set_busy(self._busy)

    def refresh_preview(self, *_):
        if not self.surface:return super().refresh_preview()
        from .tracking_effect import render_effects, box_at, validate, effective_crop, _reference_box
        from .object_tracking import sample
        tracked=copy.copy(self.item)
        tracked.effects=[self.effect]
        self.view.crop=effective_crop(tracked,self.media,self.source_time()) if not self.before.isChecked() else self.item.crop
        crop=self.view.crop
        self.surface.root.setProperty('cropGuide',[crop.x,crop.y,crop.width,crop.height])
        markers = []
        gizmos=[]
        privacy_cover=False
        ready=bool(self.effect.get('analysis')) and not self.dirty_track
        draft_box=self.view.region if not ready and self.settled_frame() else None
        visible=ready or bool(draft_box)
        preview_effect=dict(self.effect)
        preview_effect['markers']=[dict(marker,_ui_marker_id=n) for n,marker in enumerate(self.marker_editor.markers)]
        for raw in render_effects(SimpleNamespace(effects=[preview_effect]),self.source_time()) if visible else []:
            protecting=False
            box = box_at(raw, self.media, self.item, self.source_time()) if ready else list(draft_box)
            point=sample(raw.get('analysis',{}),self.source_time())
            if raw.get('mode') in ('Blur','Pixelate','Censor Bar') and point and point['status']=='lost' and (raw.get('loss_policy')=='Full frame' or not raw.get('loss_reviewed')):
                box=None
            if box is None:
                if raw.get('mode') in ('Blur','Pixelate','Censor Bar'):
                    privacy_cover=True
                    protecting=True
                    raw=dict(raw,mode='Censor Bar',color='#000000',fill=True,padding=0,offset_x=0,offset_y=0,width=100,height=100,rotation=0,opacity=100)
                    box=[0,0,1,1]
                else:continue
            effect = validate(raw)
            x,y,w,h = box
            if ready and not effect['follow_scale']:w,h=_reference_box(effect['analysis'])[2:]
            w = w*effect['width']/100+2*effect['padding']/self.media.width
            h = h*effect['height']/100+2*effect['padding']/self.media.height
            scale = self.view.image_rect().width()/max(1,self.media.width)
            appearance={key:value for key,value in effect.items() if key not in ('analysis','anchors','markers','appearance_keys')}
            image_url=''
            if effect['image']:
                url=QUrl.fromLocalFile(effect['image'])
                try:url.setQuery('modified='+str(Path(effect['image']).stat().st_mtime_ns))
                except OSError:pass
                image_url=url.toString()
            marker=dict(appearance, x=x+box[2]/2+effect['offset_x']/self.media.width-w/2,
                y=y+box[3]/2+effect['offset_y']/self.media.height-h/2,w=w,h=h,
                opacity=effect['opacity']/100,stroke=effect['stroke_width']*scale,
                font_size=effect['font_size']*scale,arrow_length=effect['arrow_length']*scale,
                arrow_head=effect['arrow_head']*scale,blur=effect['blur']*scale,
                radius=effect['radius']*scale,label_padding=effect['label_padding']*scale,
                pixel_size=effect['pixel_size']*scale,image=image_url)
            markers.append(marker)
            if not protecting and effect['mode']!='Follow Crop':
                from .tracking_gizmo import marker_geometry
                keys=('offset_x','offset_y','width','height','rotation','padding','font_size','label_padding','arrow_length','arrow_head')
                gizmos.append(marker_geometry(marker,{k:effect[k] for k in keys},self.view.image_rect(),raw.get('_ui_marker_id',0)))
        self.view.gizmos=gizmos
        self.view.selected_index=max(0,self.marker_editor.picker.currentIndex())
        selected=self.view.selected()
        self.surface.root.setProperty('drawTarget',self.view.tool=='draw')
        self.surface.root.setProperty('showGizmo',self.view.tool=='transform' and selected is not None and not self.before.isChecked() and not self._busy)
        if selected:self.surface.root.setProperty('selection',{k:v for k,v in selected.items() if k not in ('props','mode')})
        self.surface.root.setProperty('region', self.view.region or [])
        if markers!=getattr(self,'_published_markers',None):
            self.surface.root.setProperty('markers', markers)
            self._published_markers=markers
        self.surface.root.setProperty('showMarkers', visible and not self.before.isChecked())
        if hasattr(self,'cover_notice'):
            self.cover_notice.setText('Untracked frame: privacy cover active.\nShow original to redraw the target.')
            self.cover_notice.setVisible(privacy_cover and not self.before.isChecked())

    def region_changed(self, region):
        if self.effect.get('analysis') and not self.dirty_track:
            self.add_anchor()
            self.refresh_preview()
        else:
            self.info.setText('Target selected. Click Analyse target.')
            self.set_busy(False)
            self.refresh_preview()
        if hasattr(self,'transform_tool'):
            (self.draw_tool if self.mode.currentText()=='Follow Crop' else self.transform_tool).setChecked(True)
        else:
            super().region_changed(region)
            self.info.setText('Target selected.')
            self.refresh_preview()

    def mode_changed(self, mode):
        if not hasattr(self,'marker_editor'):return
        from .tracking_effect import default_effect
        self.marker_editor.write(dict(mode=mode,loss_policy=default_effect(mode)['loss_policy']))
        self.effect['loss_reviewed']=False;self.loss_review.setChecked(False)
        self.marker_editor.refresh()
        if mode=='Follow Crop':self.draw_tool.setChecked(True)
        self.refresh_preview();self.set_busy(self._busy)

    def choose_image(self):
        super().choose_image()
        if hasattr(self,'marker_editor'):
            self.marker_editor.current()['image'] = self.effect.get('image','')
            if 'markers' in self.effect:self.refresh_preview()

    def add_anchor(self):
        analysis = self.effect.get('analysis')
        if not analysis or self.dirty_track:return super().add_anchor()
        if not self.view.region or not self.settled_frame():return
        stamp = self.source_time()
        frames = analysis['frames']
        if stamp not in self._correction_originals:
            self._correction_originals[stamp]=copy.deepcopy(next((f for f in frames if abs(f['time']-stamp)<1e-7),None))
        frames[:] = [frame for frame in frames if abs(frame['time']-stamp)>1e-7]
        frames.append(dict(time=stamp,box=list(self.view.region),confidence=1.,status='manual'))
        frames.sort(key=lambda frame:frame['time'])
        self.anchors = [a for a in self.anchors if abs(a['time']-stamp)>1e-7]
        self.anchors.append(dict(time=stamp,box=list(self.view.region)))
        self.anchors.sort(key=lambda a:a['time'])
        self.effect['anchors'] = copy.deepcopy(self.anchors)
        self.refresh_anchors()
        self.info.setText('Frame corrected. Apply saves your changes.')
        self.set_busy(False)

    def clear_anchors(self):
        if not self.base_analysis:return super().clear_anchors()
        self.effect['analysis'] = copy.deepcopy(self.base_analysis)
        self.effect['anchors'] = []
        self.anchors = []
        self.dirty_track = False
        self._correction_originals.clear()
        self.refresh_anchors()
        self.refresh_preview()
        self.set_busy(False)

    def refresh_anchors(self):
        from PySide6.QtWidgets import QTableWidgetItem
        selected={self._frame_rows[i.row()]['time'] for i in self.anchor_list.selectionModel().selectedRows() if i.row()<len(self._frame_rows)}
        records={f['time']:dict(f) for f in self.effect.get('analysis',{}).get('frames',[])}
        for a in self.anchors:records[a['time']]=dict(a,status='manual')
        self._frame_rows=[f for _,f in sorted(records.items()) if self.item.in_point-1e-7<=f['time']<=self.item.in_point+self.item.source_duration+1e-7]
        self.anchor_list.blockSignals(True)
        self.anchor_list.setRowCount(len(self._frame_rows))
        self.anchor_list.setHorizontalHeaderLabels(['Clip time','Target position'])
        for row,record in enumerate(self._frame_rows):
            stamp=(record['time']-self.item.in_point)/self.item.speed
            self.anchor_list.setItem(row,0,QTableWidgetItem(f'{stamp:.3f}s'))
            label={'manual':'Manual target','lost':'Lost — review'}.get(record.get('status'),'Analysed')
            self.anchor_list.setItem(row,1,QTableWidgetItem(label))
        self.anchor_list.blockSignals(False)
        self.timeline.set_keyframes([max(0,min(self.timeline.maximum(),round((a['time']-self.item.in_point)/self.item.speed*self.fps))) for a in self._frame_rows])
        self.select_frame_rows([i for i,f in enumerate(self._frame_rows) if f['time'] in selected])

    def selected_frame_times(self):
        return [self._frame_rows[i.row()]['time'] for i in self.anchor_list.selectionModel().selectedRows() if i.row()<len(self._frame_rows)]

    def clear_frame_selection(self):
        if self.anchor_list.selectionModel().selectedRows():self.anchor_list.clearSelection()

    def select_frame_rows(self,rows):
        from PySide6.QtCore import QItemSelectionModel
        model=self.anchor_list.selectionModel();self.anchor_list.blockSignals(True);model.clearSelection()
        for row in rows:
            if 0<=row<len(self._frame_rows):model.select(self.anchor_list.model().index(row,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
        self.anchor_list.blockSignals(False)
        if rows:self.anchor_list.scrollToItem(self.anchor_list.item(rows[-1],0))
        self.frame_selection_changed()

    def frame_selection_changed(self):
        rows=[i.row() for i in self.anchor_list.selectionModel().selectedRows()]
        self.timeline.set_selected(rows)
        self.update_frame_actions()
        if hasattr(self,'marker_editor'):self.marker_editor.refresh()

    def update_frame_actions(self):
        if hasattr(self,'remove_frame_button'):
            self.remove_frame_button.setEnabled(not self._busy and bool(self.anchor_list.selectionModel().selectedRows()))

    def seek_anchor(self,row,column=0):
        if not 0<=row<len(self._frame_rows):return
        self.timeline.setValue(round((self._frame_rows[row]['time']-self.item.in_point)/self.item.speed*self.fps))

    def select_saved_frame(self,row):
        self.select_frame_rows([row]);self.seek_anchor(row)
        self.timeline.setFocus(Qt.OtherFocusReason)

    def remove_selected_frames(self):
        if self._busy:return
        rows=sorted({i.row() for i in self.anchor_list.selectionModel().selectedRows()},reverse=True)
        if not rows:return
        stamps=[self._frame_rows[row]['time'] for row in rows]
        for marker in self.marker_editor.markers:
            if 'appearance_keys' in marker:marker['appearance_keys']=[k for k in marker['appearance_keys'] if k['time'] not in stamps]
        self.anchors=[a for a in self.anchors if a['time'] not in stamps]
        self.effect['anchors']=copy.deepcopy(self.anchors)
        analysis=self.effect.get('analysis')
        if analysis and len(stamps)==len(self._frame_rows):
            self.effect['analysis']={};self.dirty_track=True;self.view.region=None;analysis=None
        if analysis:
            for stamp in stamps:
                frames=analysis['frames']
                frames[:]=[f for f in frames if abs(f['time']-stamp)>1e-7]
                original=self._correction_originals.pop(stamp,None)
                if original:frames.append(original)
                if not frames:
                    self.effect['analysis']={};self.dirty_track=True;break
                # Deleting an endpoint correction must retain valid bounds.
                if not original and stamp in (analysis['source_start'],analysis['source_end']):
                    nearest=min(frames,key=lambda f:abs(f['time']-stamp))
                    replacement=dict(nearest,time=stamp)
                    if replacement['status']=='manual':replacement['status']='tracked'
                    frames.append(replacement)
                frames.sort(key=lambda f:f['time'])
            analysis['anchors']=[a for a in analysis.get('anchors',[]) if a['time'] not in stamps]
        if any(abs(self.source_time()-t)<.5/self.fps*self.item.speed for t in stamps):
            from .object_tracking import sample
            point=sample(self.effect.get('analysis',{}),self.source_time())
            self.view.region=list(point['box']) if point else None
        if not self.effect.get('analysis') and self.view.region is None:self.draw_tool.setChecked(True)
        self.refresh_anchors();self.refresh_preview();self.set_busy(False)
        self.info.setText('Selected frames removed. No reanalysis needed.' if not self.dirty_track else 'Saved targets removed.')

    def clear_target(self):
        if self._busy:return
        self.view.region=None
        self.draw_tool.setChecked(True)
        self.refresh_preview();self.view.update();self.set_busy(False)
        self.info.setText('Draw a box to choose a target.')

    def analysis_menu(self):
        menu=QMenu(self)
        def action(label,callback,enabled):
            entry=menu.addAction(label);entry.setEnabled(enabled);entry.triggered.connect(callback)
        selected=bool(self.anchor_list.selectionModel().selectedRows())
        action('Go to selected frame',lambda:self.select_saved_frame(self.anchor_list.selectionModel().selectedRows()[0].row()),selected and not self._busy)
        action('Save this frame',self.add_anchor,self.anchor_button.isEnabled())
        action('Remove selected frames',self.remove_selected_frames,selected and not self._busy)
        menu.addSeparator()
        action('Clear drawn box',self.clear_target,not self._busy and self.view.region is not None)
        action('Restore analysed track',self.clear_anchors,not self._busy and bool(self.base_analysis))
        action('Analyse target',self.track,self.track_button.isEnabled())
        return menu

    def track(self):
        self.playing = False
        if self.player:self.player.pause()
        # Automatic defaults follow source cadence and target size.
        self.sample_fps.setValue(min(15,max(1,self.media.fps or 15)))
        if self.view.region:self.search_radius.setValue(max(.08,min(.22,max(self.view.region[2:])*1.5)))
        self.confidence_threshold.setValue(.58)
        self._refresh_base=True
        super().track()

    def show_ready(self):
        if getattr(self,'_refresh_base',False):
            self.base_analysis=copy.deepcopy(self.effect.get('analysis',{}))
            self._refresh_base=False
        super().show_ready()
        self.refresh_anchors()
        self._status_detail=self.info.text()
        frames=self.effect.get('analysis',{}).get('frames',[])
        lost=sum(f.get('status')=='lost' for f in frames)
        self.info.setText(f'Tracking ready · {len(frames)-lost}/{len(frames)} followed.'+(f'\nReview {lost} lost samples.' if lost else ''))
        if hasattr(self,'transform_tool'):self.transform_tool.setChecked(True)

    def result_effect(self):
        effect = super().result_effect()
        if 'markers' in self.effect:
            effect['markers'] = copy.deepcopy(self.marker_editor.markers)
            # The existing inspector edits the first marker; keep its summary
            # fields in sync when another marker was selected in this dialog.
            effect.update({key:value for key,value in effect['markers'][0].items()
                           if key not in ('name','enabled','analysis','loss_reviewed','markers','anchors','appearance_keys')})
        return effect

    def close_monitor(self, *_):
        from PySide6.QtWidgets import QApplication
        QApplication.instance().removeEventFilter(self)
        self.timer.stop()
        if getattr(self,'audio',None):self.audio.setMuted(True)
        if self.player:self.player.stop(); self.player.setVideoSink(None)
        if self.surface:self.surface.close()

    def set_busy(self,busy):
        super().set_busy(busy)
        self.progress_bar.setVisible(busy)
        self.anchor_list.setEnabled(not busy)
        for name in ('range_start','range_end'):
            if hasattr(self,name):getattr(self,name).setEnabled(not busy)
        self.update_guidance()
        if hasattr(self,'marker_editor'):self.marker_editor.setEnabled(not busy)
        if hasattr(self,'clear_target_button'):self.clear_target_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy and bool(self.base_analysis))
        self.update_frame_actions()
        self.loss_review.setVisible(self.mode.currentText() in ('Blur','Pixelate','Censor Bar'))
        self.transform_tool.setEnabled(not busy and self.mode.currentText()!='Follow Crop')
        if self.mode.currentText()=='Follow Crop':self.draw_tool.setChecked(True)
        self.draw_tool.setEnabled(not busy)
        self.refresh_status_card()

    def refresh_status_card(self):
        if not hasattr(self,'status_badge'):return
        state='busy' if self._busy else 'ready' if not self.dirty_track and self.effect.get('analysis') else 'target'
        if state!=getattr(self,'_status_badge_state',None):
            from .theme_widgets import set_ui_icon
            icon,colour={'busy':('activity','@info'),'ready':('check','@success'),'target':('crosshair','@text_sub')}[state]
            set_ui_icon(self.status_badge,icon,colour,24)
            self._status_badge_state=state
        if self.playing!=getattr(self,'_play_icon_state',None):
            from .icons import lucide_icon
            self.play_button.setIcon(lucide_icon('pause' if self.playing else 'play'))
            self._play_icon_state=self.playing
        self.info.setToolTip(getattr(self,'_status_detail',self.info.text()) if self.info.text().startswith('Tracking ready') else self.info.text())
