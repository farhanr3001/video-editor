"""Project timeline navigation and independent edit-history/view sessions."""
import copy
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QInputDialog,QMessageBox,QComboBox,QSizePolicy,QApplication
from .controls import SafeComboBox
from .theme_widgets import set_ui_style
from .project_timelines import IDENTITY_FIELDS,SHARED_FIELDS,inactive_media_ids,validated_name,default_name


class TimelineCombo(SafeComboBox):
    def __init__(self,window,create=False):
        super().__init__();self.window=window;self.can_create=create
        self.setObjectName('editTimelineSelector' if create else 'deliverTimelineSelector')
        self.setAccessibleName('Active timeline');self.setMinimumWidth(120)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);self.setMinimumContentsLength(12)
        self.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Fixed);self.setMaxVisibleItems(10)
        if create:self.setMaximumWidth(260)
        if create:self.setFixedHeight(32)
        set_ui_style(self,'QComboBox {combobox-popup:0;min-height:0px;}')
        self.currentIndexChanged.connect(self.changed)

    def changed(self,*_):
        controller=getattr(self.window,'timeline_sessions',None)
        if controller:controller.choose(self.currentData())

    def showPopup(self):
        # Position the real list, rather than Qt's temporary roll-animation
        # window. Restore the application preference immediately afterwards.
        animate=QApplication.isEffectEnabled(Qt.UI_AnimateCombo)
        QApplication.setEffectEnabled(Qt.UI_AnimateCombo,False)
        try:super().showPopup()
        finally:QApplication.setEffectEnabled(Qt.UI_AnimateCombo,animate)
        popup=self.view().window();below=self.mapToGlobal(QPoint(0,self.height()));available=self.screen().availableGeometry()
        above=self.can_create and bool(getattr(getattr(self.window,'timeline_workspace',None),'active',False))
        top=self.mapToGlobal(QPoint())
        height=min(popup.height(),max(24,top.y()-available.top() if above else available.bottom()-below.y()+1))
        popup.resize(max(self.width(),popup.width()),height)
        popup.move(max(available.left(),min(below.x(),available.right()-popup.width()+1)),top.y()-height if above else below.y())


class TimelineSessions:
    def __init__(self,window):
        self.w=window;self.banks={};self.media_entry=[]

    def bound(self,reset=False):
        if reset:self.banks={};self.media_entry=copy.deepcopy(list(self.w.project.media))
        self.sync()

    def sync(self):
        w=self.w;inside=bool(getattr(getattr(w,'compounds',None),'stack',[]))
        for combo in (getattr(w,'timeline_selector',None),getattr(getattr(w,'delivery',None),'timeline_selector',None)):
            if combo is None:continue
            if inside:combo.setEnabled(False);combo.setToolTip('Return from the compound clip to switch project timelines.');continue
            combo.blockSignals(True);combo.clear()
            if combo.can_create:combo.addItem('Create new timeline…','__create__');combo.insertSeparator(combo.count())
            for row in w.project.timeline_choices():combo.addItem(row['name'],row['id'])
            if combo.can_create:combo.insertSeparator(combo.count());combo.addItem('Rename timeline…','__rename__')
            combo.setCurrentIndex(combo.findData(w.project.active_timeline_id));combo.blockSignals(False)
            combo.setEnabled((combo.can_create and w.current_page==0) or (not combo.can_create and bool(w.project.other_timelines)))
            combo.setToolTip(w.project.timeline_name if combo.can_create or w.project.other_timelines else 'Create another timeline in Edit to choose between timelines.')

    def choose(self,identifier):
        if not identifier:return
        if identifier=='__create__':self.sync();self.prompt_create();return
        if identifier=='__rename__':self.sync();self.prompt_rename();return
        if identifier!=self.w.project.active_timeline_id:self.switch(identifier)

    def prompt_create(self):
        name,ok=QInputDialog.getText(self.w,'Create new timeline','Name',text=default_name(self.w.project))
        if ok:
            try:self.create(name)
            except ValueError as error:QMessageBox.information(self.w,'Timeline',str(error))

    def prompt_rename(self):
        name,ok=QInputDialog.getText(self.w,'Rename timeline','Name',text=self.w.project.timeline_name)
        if ok:
            try:
                self.w.project.timeline_name=validated_name(self.w.project,name,self.w.project.active_timeline_id)
                self.w.model_changed();self.sync()
                if not self.w.delivery.name.isModified():self.w.delivery.timeline_changed()
            except ValueError as error:QMessageBox.information(self.w,'Timeline',str(error))

    def _publish_media_delta(self):
        """Other timelines' histories must retain assets imported outside them."""
        before={m.id:m for m in self.media_entry};after={m.id:m for m in self.w.project.media}
        changed={key for key in before.keys()|after.keys() if before.get(key)!=after.get(key)}
        if not changed:return
        published={key:copy.deepcopy(after[key]) for key in changed if key in after}
        for identifier,bank in self.banks.items():
            if identifier==self.w.project.active_timeline_id:continue
            for snapshot in bank['history']:
                media={m.id:m for m in snapshot.media};used={i.media_id for i in snapshot.timeline}
                for key in changed:
                    if key in after:
                        if key in media or key not in before:media[key]=published[key]
                    elif key in media and key not in used:media.pop(key)
                snapshot.media=list(media.values())

    def _view(self):
        w=self.w;t=w.timeline;d=w.delivery
        return dict(zoom=t.pixels_per_second,scroll=t.horizontalScrollBar().value(),
            sections={name:getattr(t,name+'_scroll').value() for name in ('video','audio','subtitle')},
            selected=set(t.selected_ids),primary=t.selected_id,captions=set(t.selected_caption_ids),caption=t.selected_caption,
            tool=t.tool,linked=t.linked_selection,snapping=w.snap_tool.isChecked(),rate=w.transport.rate,loop=w.transport.loop,
            file_name=d.name.text(),file_modified=d.name.isModified())

    def _leave(self):
        w=self.w;w.flush_text_edit();w.transport.pause();w.timeline.cancel_drag()
        self._publish_media_delta()
        self.banks[w.project.active_timeline_id]=dict(history=w._history,index=w._history_index,view=self._view())

    def create(self,name=''):
        if self.w.compounds.stack:raise ValueError('Return from the compound clip before creating a timeline.')
        candidate=copy.deepcopy(self.w.project);identifier=candidate.create_timeline(name)
        self._activate(candidate);return identifier

    def switch(self,identifier):
        if identifier==self.w.project.active_timeline_id:return False
        if self.w.compounds.stack:raise ValueError('Return from the compound clip before switching timelines.')
        candidate=copy.deepcopy(self.w.project);candidate.switch_timeline(identifier)
        self._activate(candidate);return True

    def _activate(self,candidate):
        w=self.w;self._leave();bank=self.banks.get(candidate.active_timeline_id)
        from .project_timelines import capture
        candidate.other_timelines=[capture(w.project) if row['id']==w.project.active_timeline_id else row for row in candidate.other_timelines]
        # Identity replacement also makes every existing asynchronous feature's
        # destination-project guard reject a late result from another timeline.
        w._switching_timeline=True
        try:w.set_project(candidate)
        finally:w._switching_timeline=False
        if bank:
            w._history=bank['history'];w._history_index=bank['index']
            shared={key:copy.deepcopy(getattr(candidate,key)) for key in SHARED_FIELDS+('other_timelines',)}
            for snapshot in w._history:
                for key,value in shared.items():setattr(snapshot,key,value)
        t=w.timeline;t.select_ids(set(),'');t.select_captions(set(),'');w.select_item('');w.inspector.select('')
        view=bank['view'] if bank else {}
        t.linked_selection=view.get('linked',True);w.link_toggle.setChecked(t.linked_selection)
        w.snap_tool.setChecked(view.get('snapping',True));t.setProperty('snapping',w.snap_tool.isChecked())
        w.set_timeline_tool(view.get('tool','select'));t.set_zoom(view.get('zoom',45));t.horizontalScrollBar().setValue(view.get('scroll',0))
        for name,value in view.get('sections',{}).items():getattr(t,name+'_scroll').setValue(value)
        w.transport.rate=view.get('rate',1.);w.transport.loop=view.get('loop',False);w.loop_button.setChecked(w.transport.loop)
        if view.get('captions'):t.select_captions(view['captions'],view.get('caption',''))
        elif view.get('selected'):t.select_ids(view['selected'],view.get('primary',''))
        w.delivery.timeline_changed(view);self.media_entry=copy.deepcopy(list(w.project.media));self.sync()
        w.autosave_debounce_timer.start() if hasattr(w,'autosave_debounce_timer') else None

    def restore(self,snapshot,current):
        restored=snapshot.active_snapshot()
        for key in SHARED_FIELDS+('active_timeline_id','timeline_number','other_timelines'):
            setattr(restored,key,copy.deepcopy(getattr(current,key)))
        needed=inactive_media_ids(current);present={m.id for m in restored.media}
        restored.media.extend(copy.deepcopy(m) for m in current.media if m.id in needed and m.id not in present)
        return restored
