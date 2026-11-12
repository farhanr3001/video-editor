"""Local tracking authoring layout and saved-frame scrubber affordances."""
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QPainter, QPolygonF, QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QStyle, QStyleOptionSlider, QAbstractItemView, QToolButton, QSplitter, QSizePolicy, QHeaderView)
from .controls import SafeSlider
from .icons import lucide_icon


from .tracking_timeline import TrackingScrubber


def build_workspace(dialog):
    """Construct one widget tree. No control is moved out of a legacy layout."""
    import math
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog,QProgressBar,QTableWidget,QButtonGroup,QMenu,QFrame
    from .tracking_design import TrackingCard,TrackingCheckBox,TrackingComboBox,STYLE,_button
    from .theme_widgets import set_ui_style,set_ui_icon
    from .controls import SafeDoubleSpinBox
    from .tracking_effect import MODES
    from .tracking_gizmo import TrackingRegionView
    from .tracking_markers import MarkerEditor
    dialog.setObjectName('trackingWorkspace')
    dialog.setMinimumSize(980,700)
    root=QVBoxLayout(dialog);root.setContentsMargins(12,8,12,8);root.setSpacing(8)
    parking=QWidget(dialog);parking.hide();dialog._hidden_controls=parking
    for name,low,high,value in [('sample_fps',1,60,15),('search_radius',.03,.5,.22),('confidence_threshold',.2,.95,.58)]:
        field=SafeDoubleSpinBox(parking);field.setRange(low,high);field.setValue(value)
        field.valueChanged.connect(dialog.analysis_setting_changed);setattr(dialog,name,field)
    toolbar=QWidget(dialog);toolbar.setProperty('trackingBody',True)
    top=QHBoxLayout(toolbar);top.setContentsMargins(6,0,6,4)
    icon=QLabel(toolbar);set_ui_icon(icon,'scan',size=24);top.addWidget(icon)
    title=QLabel('Object Tracking',toolbar);title.setObjectName('trackingTitle');top.addWidget(title)
    top.addStretch()
    dialog.source_label=QLabel(dialog.media.name,toolbar);dialog.source_label.setObjectName('trackingSource')
    dialog.source_label.setMaximumWidth(420);dialog.source_label.setMinimumWidth(0)
    dialog.source_label.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
    dialog.source_label.setToolTip(dialog.media.path);top.addWidget(dialog.source_label,1)
    dialog.marker_toggle=QToolButton(toolbar);dialog.marker_toggle.setText('Marker properties')
    dialog.marker_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    dialog.marker_toggle.setCheckable(True);dialog.marker_toggle.setChecked(True);top.addWidget(dialog.marker_toggle)
    root.addWidget(toolbar)
    dialog.splitter=QSplitter(Qt.Horizontal,dialog);root.addWidget(dialog.splitter,1)
    left=QWidget(dialog.splitter);left.setProperty('trackingBody',True);left.setMinimumWidth(285)
    left.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Ignored)
    dialog.analysis_panel=left
    column=QVBoxLayout(left);column.setContentsMargins(0,0,0,0);column.setSpacing(8)
    analysis=TrackingCard('Analysis','crosshair',left);column.addWidget(analysis)
    analysis.content.setContentsMargins(10,8,10,8);analysis.content.setSpacing(6)
    dialog.guide=QWidget(analysis.body);dialog.guide.setProperty('trackingBody',True)
    guide=QVBoxLayout(dialog.guide);guide.setContentsMargins(0,0,0,0);guide.setSpacing(4)
    steps=['<b>Draw target</b> — pause and drag a tight box.','<b>Click Analyse target</b> for the range below.',
           '<b>Review &amp; apply</b> — Draw target corrects a frame; Move/resize adjusts the marker.']
    dialog.guide.setAccessibleName(' '.join(steps))
    for n,text in enumerate(steps,1):
        line=QHBoxLayout();line.setSpacing(7)
        number=QLabel(str(n),dialog.guide);number.setProperty('trackingNumber',True)
        number.setFixedSize(22,22);number.setAlignment(Qt.AlignCenter)
        label=QLabel(text,dialog.guide);label.setWordWrap(True)
        line.addWidget(number,0,Qt.AlignTop);line.addWidget(label,1);guide.addLayout(line)
    analysis.content.addWidget(dialog.guide)
    dialog.guide_summary=QLabel('<b>1.</b> Pause and draw a tight box.<br><b>2.</b> Click Analyse target.<br><b>3.</b> Review, correct and Apply.',analysis.body)
    dialog.guide_summary.setWordWrap(True);dialog.guide_summary.hide();analysis.content.addWidget(dialog.guide_summary)
    dialog.guide_toggle=QToolButton(analysis);dialog.guide_toggle.setCheckable(True);dialog.guide_toggle.setChecked(True)
    dialog.guide_toggle.setArrowType(Qt.DownArrow);dialog.guide_toggle.setToolTip('Show or hide the guide')
    analysis.header_line.addWidget(dialog.guide_toggle)
    dialog.guide_toggle.toggled.connect(dialog.update_responsive)
    dialog.guide_toggle.toggled.connect(lambda shown:dialog.guide_toggle.setArrowType(Qt.DownArrow if shown else Qt.RightArrow))
    range_row=QHBoxLayout();range_row.setSpacing(5)
    start=min(max(0,dialog.window_.project.playhead-dialog.item.start),max(0,dialog.item.duration-10))
    from .object_tracking import MAX_ANALYSIS_DURATION
    limit=MAX_ANALYSIS_DURATION/max(.0001,dialog.item.speed)
    dialog.range_start=SafeDoubleSpinBox(analysis.body);dialog.range_end=SafeDoubleSpinBox(analysis.body)
    for field in (dialog.range_start,dialog.range_end):
        field.setDecimals(3);field.setRange(0,dialog.item.duration);field.setSuffix(' s');field.setMinimumWidth(75)
        field.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
    dialog.range_start.setValue(start);dialog.range_end.setValue(min(dialog.item.duration,start+min(10,limit)))
    range_row.addWidget(QLabel('From',analysis.body));range_row.addWidget(dialog.range_start,1)
    range_row.addWidget(QLabel('To',analysis.body));range_row.addWidget(dialog.range_end,1)
    analysis.content.addLayout(range_row)
    dialog.range_hint=QLabel('Maximum 30 source seconds.',analysis.body);dialog.range_hint.setObjectName('trackingBudget')
    dialog.range_hint.setWordWrap(True);analysis.content.addWidget(dialog.range_hint)
    dialog.track_button=QPushButton('Analyse target',analysis.body);_button(dialog.track_button,'play')
    dialog.track_button.setProperty('trackingPrimary',True);dialog.track_button.clicked.connect(dialog.track)
    analysis.content.addWidget(dialog.track_button)
    dialog.cancel_tracking=QPushButton('Cancel analysis',analysis.body);dialog.cancel_tracking.clicked.connect(lambda:dialog.cancel.set())
    analysis.content.addWidget(dialog.cancel_tracking)
    dialog.progress_bar=QProgressBar(analysis.body);dialog.progress_bar.setRange(0,100);analysis.content.addWidget(dialog.progress_bar)
    dialog.range_start.valueChanged.connect(lambda:dialog.range_changed(True));dialog.range_end.valueChanged.connect(lambda:dialog.range_changed(False))
    status=TrackingCard('Tracking status','activity',left);column.addWidget(status)
    status.content.setContentsMargins(10,6,10,6);status.content.setSpacing(4)
    row=QHBoxLayout();row.setSpacing(8)
    dialog.status_badge=QLabel(status.body);dialog.status_badge.setFixedSize(22,22);row.addWidget(dialog.status_badge,0,Qt.AlignTop)
    dialog.info=QLabel('Pause and draw a box to start.',status.body);dialog.info.setWordWrap(True);dialog.info.setMaximumHeight(36)
    row.addWidget(dialog.info,1);status.content.addLayout(row)
    dialog.cover_notice=QLabel(status.body);dialog.cover_notice.setWordWrap(True);dialog.cover_notice.setMaximumHeight(44)
    dialog.cover_notice.hide();status.content.addWidget(dialog.cover_notice)
    saved=TrackingCard('Saved frames','layers',left);column.addWidget(saved,1)
    saved.content.setContentsMargins(10,8,10,8);saved.content.setSpacing(5)
    dialog.anchor_list=QTableWidget(0,2,saved.body)
    dialog.anchor_list.setHorizontalHeaderLabels(['Clip time','Target'])
    dialog.anchor_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    dialog.anchor_list.verticalHeader().setDefaultSectionSize(26)
    dialog.anchor_list.setMinimumHeight(52);dialog.anchor_list.setAlternatingRowColors(True)
    dialog.anchor_list.setSelectionBehavior(QAbstractItemView.SelectRows)
    dialog.anchor_list.setSelectionMode(QAbstractItemView.ExtendedSelection);dialog.anchor_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
    dialog.anchor_list.cellClicked.connect(dialog.seek_anchor);dialog.anchor_list.installEventFilter(dialog);dialog.anchor_list.viewport().installEventFilter(dialog)
    dialog.anchor_list.itemSelectionChanged.connect(dialog.frame_selection_changed)
    saved.content.addWidget(dialog.anchor_list,1)
    dialog.anchor_button=QPushButton('Save frame',saved.body);_button(dialog.anchor_button,'plus');dialog.anchor_button.clicked.connect(dialog.add_anchor)
    dialog.remove_frame_button=QPushButton('Remove',saved.body);_button(dialog.remove_frame_button,'trash-2');dialog.remove_frame_button.clicked.connect(dialog.remove_selected_frames)
    row=QHBoxLayout();row.addWidget(dialog.anchor_button,1);row.addWidget(dialog.remove_frame_button,1);saved.content.addLayout(row)
    dialog.clear_target_button=QPushButton('Clear box',saved.body);_button(dialog.clear_target_button,'scan');dialog.clear_target_button.clicked.connect(dialog.clear_target)
    dialog.clear_button=QPushButton('Restore track',saved.body);_button(dialog.clear_button,'rotate-ccw');dialog.clear_button.clicked.connect(dialog.clear_anchors)
    dialog.clear_button.setToolTip('Restore analysed track and remove manual corrections')
    row=QHBoxLayout();row.addWidget(dialog.clear_target_button,1);row.addWidget(dialog.clear_button,1);saved.content.addLayout(row)
    dialog.loss_review=TrackingCheckBox('Lost frames reviewed',saved.body)
    dialog.loss_review.setChecked(dialog.effect.get('loss_reviewed',False));dialog.loss_review.toggled.connect(dialog.review_changed)
    saved.content.addWidget(dialog.loss_review)
    for widget in (left,dialog.anchor_list):
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(lambda p,w=widget:dialog.analysis_menu().exec((w.viewport() if w is dialog.anchor_list else w).mapToGlobal(p)))
    shortcut=QShortcut(QKeySequence.Delete,dialog.anchor_list);shortcut.setContext(Qt.WidgetWithChildrenShortcut)
    shortcut.activated.connect(dialog.remove_selected_frames);dialog._delete_frame_shortcut=shortcut

    center=TrackingCard('Preview','rectangle-horizontal',dialog.splitter);center.setMinimumWidth(260)
    center.content.setContentsMargins(8,0,8,8);center.content.setSpacing(6)
    dialog.view=TrackingRegionView(dialog.media,center.body);dialog.view.crop=dialog.item.crop
    dialog.view.regionChanged.connect(dialog.region_changed);dialog.view.regionStarted.connect(dialog.pause_for_edit)
    dialog.view.cursorChanged.connect(dialog.sync_preview_cursor)
    dialog.view.markerEdited.connect(dialog.edit_marker_geometry)
    dialog.view.markerSelected.connect(lambda index:dialog.marker_editor.picker.setCurrentIndex(index))
    center.content.addWidget(dialog.view,1)
    center.header_line.addWidget(QLabel('Fit',center))
    dialog.draw_tool=QToolButton(center);dialog.draw_tool.setCheckable(True);dialog.draw_tool.setText('Draw target')
    dialog.draw_tool.setIcon(lucide_icon('crosshair'));dialog.draw_tool.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    dialog.transform_tool=QToolButton(center);dialog.transform_tool.setCheckable(True);dialog.transform_tool.setText('Move/resize')
    dialog.transform_tool.setIcon(lucide_icon('move'));dialog.transform_tool.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    dialog.draw_tool.setToolButtonStyle(Qt.ToolButtonIconOnly);dialog.draw_tool.setToolTip('Draw target — redraw to correct tracking')
    dialog.transform_tool.setToolButtonStyle(Qt.ToolButtonIconOnly);dialog.transform_tool.setToolTip('Move, resize or rotate the selected marker')
    tools=QButtonGroup(dialog);tools.setExclusive(True);tools.addButton(dialog.draw_tool);tools.addButton(dialog.transform_tool)
    dialog.draw_tool.setChecked(True);dialog._tracking_tools=tools
    dialog.draw_tool.toggled.connect(lambda checked:dialog.set_preview_tool('draw' if checked else 'transform'))
    center.header_line.addWidget(dialog.draw_tool);center.header_line.addWidget(dialog.transform_tool)
    dialog.preview_expand=QToolButton(center);dialog.preview_expand.setCheckable(True)
    dialog.preview_expand.setIcon(lucide_icon('maximize-2'));dialog.preview_expand.setToolTip('Expand preview');center.header_line.addWidget(dialog.preview_expand)
    dialog.timeline=TrackingScrubber(center.body)
    dialog.timeline.setRange(0,max(1,math.ceil(dialog.item.duration*dialog.fps)-1))
    dialog.timeline.fps=dialog.fps
    dialog.timeline.valueChanged.connect(dialog.seek)
    dialog.timeline.framesSelected.connect(dialog.select_frame_rows)
    dialog.timeline.scrubStarted.connect(dialog.pause_for_edit)
    dialog.time_label=QLabel(center.body)
    dialog.time_label.setMinimumWidth(120);dialog.time_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
    row=QHBoxLayout();row.addWidget(dialog.timeline,1);center.content.addLayout(row)
    row=QHBoxLayout()
    for icon,factor,title in [('zoom-out',1/1.5,'Zoom out timeline'),('zoom-in',1.5,'Zoom in timeline')]:
        button=QToolButton(center.body);button.setIcon(lucide_icon(icon));button.setToolTip(title)
        button.clicked.connect(lambda _,f=factor:dialog.timeline.zoom_by(f));row.addWidget(button)
    row.addStretch();row.addWidget(dialog.time_label);center.content.addLayout(row)
    transport=QHBoxLayout();dialog.transport_controls=transport
    dialog.play_button=QPushButton('Play',center.body);_button(dialog.play_button,'play');dialog.play_button.clicked.connect(dialog.toggle_play)
    transport.addWidget(dialog.play_button,1)
    for title,delta,icon in [('Previous frame',-1,'chevron-left'),('Next frame',1,'chevron-right')]:
        button=QPushButton(center.body);button.setToolTip(title);button.setIcon(lucide_icon(icon));button.setFixedWidth(36)
        button.clicked.connect(lambda _,d=delta:dialog.step(d));transport.addWidget(button)
    dialog.before=TrackingCheckBox('Show original',center.body);dialog.before.toggled.connect(dialog.refresh_preview);transport.addWidget(dialog.before)
    center.content.addLayout(transport)
    dialog._decode_timer=QTimer(dialog);dialog._decode_timer.setSingleShot(True);dialog._decode_timer.timeout.connect(dialog.request_frame)
    dialog.mode=TrackingComboBox(dialog)
    dialog.mode.addItems(MODES);dialog.mode.setCurrentText(dialog.effect.get('mode','Censor Bar'))
    right=TrackingCard('Marker properties','crosshair',dialog.splitter);right.setMinimumWidth(295)
    right.content.setContentsMargins(0,0,0,0)
    dialog.marker_editor=MarkerEditor(dialog);dialog.image_form=dialog.marker_editor.form;dialog.image_button=dialog.marker_editor.image_button
    dialog.mode.currentTextChanged.connect(dialog.mode_changed)
    scroll=QScrollArea(right.body);scroll.setWidgetResizable(True);scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(dialog.marker_editor);right.content.addWidget(scroll)
    dialog.marker_panel=right
    dialog.marker_editor.picker.currentIndexChanged.connect(dialog.refresh_preview)
    dialog.splitter.setStretchFactor(0,0);dialog.splitter.setStretchFactor(1,1);dialog.splitter.setStretchFactor(2,0)
    dialog.splitter.setSizes([320,660,340])
    def show_properties(shown):
        if not shown:dialog._marker_panel_width=right.width()
        right.setVisible(shown)
        if shown:
            sizes=dialog.splitter.sizes();total=sum(sizes);width=getattr(dialog,'_marker_panel_width',320)
            dialog.splitter.setSizes([sizes[0],max(260,total-sizes[0]-width),width])
        dialog.marker_toggle.setArrowType(Qt.DownArrow if shown else Qt.UpArrow)
        description='Hide marker properties' if shown else 'Show marker properties'
        dialog.marker_toggle.setAccessibleName(description);dialog.marker_toggle.setToolTip(description)
    dialog.marker_toggle.toggled.connect(show_properties);show_properties(True)
    def expand_preview(expanded):
        if expanded:
            dialog._preview_panel_state=(left.isVisible(),right.isVisible(),dialog.splitter.sizes());left.hide();right.hide()
        else:
            a,b,sizes=dialog._preview_panel_state;left.setVisible(a);right.setVisible(b);dialog.splitter.setSizes(sizes)
        dialog.marker_toggle.setEnabled(not expanded)
        dialog.preview_expand.setToolTip('Restore panels' if expanded else 'Expand preview')
    dialog.preview_expand.toggled.connect(expand_preview)
    footer=QFrame(dialog);footer.setObjectName('trackingFooter');line=QHBoxLayout(footer)
    line.setContentsMargins(8,8,8,0);line.addStretch()
    dialog.cancel_button=QPushButton('Cancel',footer);dialog.cancel_button.clicked.connect(dialog.reject)
    dialog.apply_button=QPushButton('Apply',footer);dialog.apply_button.setProperty('trackingPrimary',True);dialog.apply_button.clicked.connect(dialog.accept)
    for button in (dialog.cancel_button,dialog.apply_button):button.setMinimumWidth(90);line.addWidget(button)
    root.addWidget(footer)
    dialog._ui_cards={'analysis':analysis,'status':status,'saved':saved,'preview':center,'properties':right}
    set_ui_style(dialog,STYLE)
