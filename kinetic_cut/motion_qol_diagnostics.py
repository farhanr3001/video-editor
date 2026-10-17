"""Disposable native input checks for motion dialog isolation and selection."""
def check(editor,window,settle):
    import copy
    from PySide6.QtCore import Qt,QPointF,QPoint,QMimeData
    from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDropEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPlainTextEdit,QPushButton
    from .effects import GRAPHICS
    d=editor; before=copy.deepcopy(d.scene); old_selection=set(d.selected_ids); old_id=d.node_id; history=window._history_index
    assert not hasattr(window,'keyframe_button')
    rect=d.preview.canvas_rect(); assert abs(rect.width()/rect.height()-window.project.settings.width/window.project.settings.height)<1e-8
    assert d.preview.safe_rect().center()==rect.center()
    assert all(not b.icon().isNull() for b in d.tree.parentWidget().findChildren(QPushButton))
    width,height=d.scene['canvas']
    d.scene['nodes']=[dict(id='left',kind='rectangle',x=width*.25,y=height*.3,width=width*.08,height=height*.05),dict(id='right',kind='rectangle',x=width*.7,y=height*.3,width=width*.08,height=height*.05)]
    d.node_id=''; d.selected_ids=set(); d.rebuild(); d.activateWindow(); d.preview.setFocus(); settle()
    p=d.preview; point=lambda x,y:p.from_scene(QPointF(x,y)).toPoint()
    QTest.mouseClick(p,Qt.LeftButton,Qt.NoModifier,point(width*.25,height*.3)); QTest.mouseClick(p,Qt.LeftButton,Qt.ControlModifier,point(width*.7,height*.3))
    assert d.selected_ids=={'left','right'} and len(d.tree.selectedItems())==2
    d.change('opacity',45); assert all(n['opacity']==45 for n in d.scene['nodes'])
    QTest.keyClick(p,Qt.Key_Z,Qt.ControlModifier); assert all(n.get('opacity',100)==100 for n in d.scene['nodes'])
    QTest.keyClick(p,Qt.Key_Z,Qt.ControlModifier|Qt.ShiftModifier); assert all(n['opacity']==45 for n in d.scene['nodes'])
    d.select_node('left'); d.node().update(scale=2,scale_y=3); d.refresh(); assert d.scale_link.isChecked()
    d.spins['scale'].stepBy(1); assert abs(d.node()['scale_y']-3.015)<1e-8
    QTest.keyClick(p,Qt.Key_Z,Qt.ControlModifier); assert d.node()['scale']==2 and d.node()['scale_y']==3
    d.scale_link.setChecked(False); d.spins['scale'].stepBy(1); assert d.node()['scale_y']==3
    d.select_node('left'); tree=d.tree; left=d._tree_items['left']; right=d._tree_items['right']
    QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.ControlModifier,tree.visualItemRect(right).center())
    QTest.mouseClick(tree.viewport(),Qt.LeftButton,Qt.ControlModifier,tree.visualItemRect(right).center())
    assert d.selected_ids=={'left'}; d.layer_name.setText('Renamed')
    assert left.text(0).startswith('Renamed') and not right.text(0).startswith('Renamed')
    QTest.mousePress(p,Qt.LeftButton,Qt.NoModifier,point(width*.12,height*.2)); QTest.mouseMove(p,point(width*.85,height*.4)); QTest.mouseRelease(p,Qt.LeftButton,Qt.NoModifier,point(width*.85,height*.4))
    assert d.selected_ids=={'left','right'} and p.drag is None
    QTest.keyClick(p,Qt.Key_Space); assert d.timer.isActive(); QTest.keyClick(p,Qt.Key_Space); assert not d.timer.isActive()
    d.select_node('left'); d.layer_name.setFocus(); settle(); assert d.layer_name.hasFocus()
    QTest.keyClick(d.layer_name,Qt.Key_Space); assert not d.timer.isActive()
    d.scene['nodes']=[dict(id='label',kind='text',text='EDIT ME',x=width/2,y=height*.3,font_size=width*.06)]
    d.selected_ids={'label'}; d.node_id='label'; d.rebuild(); settle()
    QTest.mouseDClick(p,Qt.LeftButton,Qt.NoModifier,point(width/2,height*.3)); edit=p.findChild(QPlainTextEdit); assert edit is not None
    edit.setPlainText('UPDATED'); QTest.keyClick(edit,Qt.Key_Return,Qt.ControlModifier); assert d.node()['text']=='UPDATED'
    QTest.keyClick(p,Qt.Key_Z,Qt.ControlModifier); assert d.node()['text']=='EDIT ME'
    assert window._history_index==history
    d.scene=before; d.node_id=old_id; d.selected_ids=old_selection; d._undo.clear(); d._redo.clear(); d.rebuild()
    return dict(scoped_shortcuts=True,typing_guard=True,multi_selection=True,marquee=True,bulk_property_undo=True,inline_text=True,project_aspect=True,centered_guide=True,toolbar_icons=True,keyframe_toolbar_removed=True,tree_deselect_name_edit=True,linked_scale=True)

def graphics_drop(window):
    import copy
    from PySide6.QtCore import Qt,QPoint,QPointF,QMimeData
    from PySide6.QtGui import QDragEnterEvent,QDragMoveEvent,QDropEvent
    from .effects import GRAPHICS
    original=window.project; before=copy.deepcopy(original); window.set_project(copy.deepcopy(before)); timeline=window.timeline; result=[]
    for name in GRAPHICS:
        rect=timeline.track_rect(window.project.video_tracks[0]); point=QPoint(round(timeline.x_for_time(2)),round(rect.center().y()))
        mime=QMimeData(); mime.setData('application/x-kinetic-effect',name.encode())
        enter=QDragEnterEvent(point,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); timeline.dragEnterEvent(enter); assert enter.isAccepted(),name
        move=QDragMoveEvent(point,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); timeline.dragMoveEvent(move); assert move.isAccepted(),name
        drop=QDropEvent(QPointF(point),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier); timeline.dropEvent(drop); assert drop.isAccepted(),name
        window.undo(); assert window._history_key(window.project)==window._history_key(before),name; result.append(name)
    window.set_project(original)
    return result

def fades(window,out,settle):
    from PySide6.QtCore import Qt,QPoint
    from PySide6.QtTest import QTest
    from .model import Project,TimelineItem
    project=Project(timeline=[TimelineItem('graphic','','video_1',0,3,role='graphic',graphic_type='Rectangle',fade_in=.5,fade_out=.5),TimelineItem('media','','video_2',0,3,fade_in=.5,fade_out=.5),TimelineItem('audio','','audio_1',0,3,role='audio',fade_in=.5,fade_out=.5)])
    project.video_tracks=['video_1','video_2']; window.set_project(project); t=window.timeline; t.pixels_per_second=100
    t.select_ids(set()); assert not window.retime_button.isEnabled() and window.retime_button.toolTip()=='Select a media clip to re-time first.'
    t.select_ids({'graphic'},'graphic'); assert window.retime_button.isEnabled()
    QTest.mouseClick(window.retime_button,Qt.LeftButton); assert t.retime_ids=={'graphic'}
    window.shortcut_actions['retime_controls'].trigger(); assert not t.retime_ids
    t.select_ids(set()); assert not window.retime_button.isEnabled()
    captures=[]
    for theme in ('default','final_cut_obsidian','ableton_gray'):
        window.apply_theme(theme,save=False); t.select_ids({i.id for i in project.timeline},'graphic'); t.viewport().update(); settle()
        path=out/f'fade-handles-{theme}.png'; assert t.grab().save(str(path)); captures.append(path.name)
        assert window.grab().save(str(out/f'timeline-tools-{theme}.png'))
        t.select_ids(set()); settle(); assert not window.retime_button.isEnabled()
        assert window.grab().save(str(out/f'timeline-tools-disabled-{theme}.png'))
    item=project.timeline[0]; item.fade_in=0; t.selected_ids={item.id}; t.selected_id=item.id; t.viewport().update(); settle()
    r=t.item_rect(item); point=QPoint(round(r.left()+5),round(r.top()+5))
    QTest.mousePress(t.viewport(),Qt.LeftButton,Qt.NoModifier,point); assert t.drag_mode=='fade_in'
    QTest.mouseMove(t.viewport(),point); assert item.fade_in==0
    QTest.mouseMove(t.viewport(),point+QPoint(20,0)); assert abs(item.fade_in-.2)<.015,item.fade_in
    QTest.mouseRelease(t.viewport(),Qt.LeftButton,Qt.NoModifier,point+QPoint(20,0))
    # Exercise actual inspector input and preview overlay painting in the native
    # packaged editor, with disposable images and a separate two-layer project.
    from PySide6.QtGui import QImage,QColor
    from .model import MediaItem,Transform
    image_path=out/'multi-transform.png'; image=QImage(320,180,QImage.Format_ARGB32); image.fill(QColor('#446688')); assert image.save(str(image_path))
    media=MediaItem('multi',str(image_path),'image','fixture',30,320,180)
    project=Project(media=[media],timeline=[TimelineItem('first','multi','video_1',0,4,transform=Transform(.3,.5,1,scale_y=2)),TimelineItem('second','multi','video_2',0,4,transform=Transform(.7,.5,2,scale_y=3))])
    project.video_tracks=['video_1','video_2']; window.set_project(project)
    window.timeline.select_ids({'first','second'},'first'); panel=window.inspector; panel.select('first'); row=panel.zoom_x
    a,b=project.timeline; row.spin.stepBy(1); assert abs(a.transform.scale-1.01)<1e-8 and abs(b.transform.scale-2.01)<1e-8
    assert abs(a.transform.scale_y/a.transform.scale-2)<1e-8 and abs(b.transform.scale_y/b.transform.scale-1.5)<1e-8
    QTest.mouseDClick(row.spin.lineEdit(),Qt.LeftButton); QTest.keyClicks(row.spin,'3'); QTest.keyClick(row.spin,Qt.Key_Return)
    assert abs(a.transform.scale-3)<1e-8 and abs(b.transform.scale-3)<1e-8
    project.settings.width=640; project.settings.height=360
    a.transform.scale=.35; a.transform.scale_y=.4; b.transform.scale=.45; b.transform.scale_y=.5
    b.keyframes={'rotation':[dict(time=0,value=0),dict(time=4,value=10)]}
    panel.select('first')
    preview=window.preview; preview.transform_controls_visible=True; drawn=set(); original=preview._draw_transform_box
    def record(painter,item,target):drawn.add(item.id); return original(painter,item,target)
    preview._draw_transform_box=record
    try:
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            window.apply_theme(theme,save=False); drawn.clear(); preview.update(); settle(); assert preview.grab().save(str(out/f'multi-transform-{theme}.png'))
            assert drawn=={'first','second'},drawn
    finally:del preview._draw_transform_box
    return dict(relative_multi_inspector=True,typed_exact_multi_inspector=True,all_selected_transform_boxes=True,round_handles=True,curved_guides=True,grab_offset_preserved=True,retime_button_matches_shortcut=True,disabled_retime_tooltip=True,theme_captures=captures)


def drop_workflow(out):
    """Small isolated native visual/placement check; never saves owner projects."""
    import os,json,copy,sys
    os.environ['KINETIC_CUT_HOME']=str(out/'home'); os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt,QPoint,QPointF,QEventLoop,QTimer,QThreadPool
    from .ui import MainWindow
    from .model import Project,TimelineItem
    from .motion_editor import MotionEditor
    app=QApplication([]); app.setQuitOnLastWindowClosed(False); app.setProperty('kineticTestDiscardUnsaved',True)
    w=MainWindow(); w.autosave_timer.stop(); w.resize(1400,900); w.show()
    scene=dict(canvas=[1080,1920],nodes=[dict(id='g',name='Product card',kind='group'),dict(id='c',name='Card background',kind='rectangle',parent='g'),dict(id='h',name='Heading',kind='group'),dict(id='d',name='Title',kind='text',parent='h'),dict(id='x',name='Watch image',kind='rectangle')])
    item=TimelineItem('fixture','','video_1',0,4,role='graphic',graphic_type='Motion Composition',graphic_data={'scene':scene}); w.set_project(Project(timeline=[item])); original=copy.deepcopy(w.project.to_dict())
    def settle():
        loop=QEventLoop();QTimer.singleShot(100,loop.quit);loop.exec()
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),themes=[])
    try:
        for theme in ('default','final_cut_obsidian','ableton_gray'):
            w.apply_theme(theme,save=False); d=MotionEditor(w,item);d.resize(1180,820);d.show();d.select_node('x');settle();tree=d.tree
            for mode in ('inside','after','outdent','root'):
                row=d._tree_items['g' if mode in ('inside','after') else 'c'];rect=tree.visualItemRect(row)
                point=rect.center() if mode=='inside' else QPoint(rect.center().x(),rect.bottom()-1) if mode=='after' else QPoint(1,rect.bottom()-1) if mode=='outdent' else QPoint(10,tree.viewport().height()-5)
                plan=tree.drop_plan(point);assert plan is not None;tree.drop_preview=plan;tree.viewport().update();settle()
                assert tree.grab().save(str(out/f'{theme}-{mode}.png'))
            tree.clear_drop_preview();rect=tree.visualItemRect(d._tree_items['g']);point=rect.center();before=copy.deepcopy(d.scene)
            class Drop:
                accepted=False
                def source(s):return tree
                def position(s):return QPointF(point)
                def ignore(s):s.accepted=False
                def acceptProposedAction(s):s.accepted=True
            event=Drop();tree.dropEvent(event);assert event.accepted and d.node()['parent']=='g'
            point=QPoint(1,tree.visualItemRect(d._tree_items['c']).bottom()-1);tree.dropEvent(event)
            assert event.accepted and not d.node().get('parent')
            assert [n['id'] for n in d.scene['nodes']]==['g','c','x','h','d']
            d.local_history(-1);assert d.node()['parent']=='g';d.local_history(-1);assert d.scene==before
            current=w.project.to_dict(); expected=copy.deepcopy(original)
            current.pop('modified_at',None); expected.pop('modified_at',None)  # Existing autosave timestamp, not a document edit.
            assert current==expected;d.reject();report['themes'].append(theme)
        report.update(passed=True,visual_targets=True,group_and_root=True,whole_branch_order=True,local_undo=True,owner_project_unchanged=True)
    except Exception:
        import traceback
        report['error']=traceback.format_exc()
    finally:
        w.close();QThreadPool.globalInstance().waitForDone(10000);app.processEvents();(out/'report.json').write_text(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1
