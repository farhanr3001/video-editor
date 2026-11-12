"""Opt-in private native checks for effect gesture routing and linked audio UI."""
def run(output):
    import os,json,sys,copy,traceback,wave,math,struct
    from pathlib import Path
    from unittest.mock import patch
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(out/'home');os.environ['QT_QPA_PLATFORM']='windows' if os.name=='nt' else 'offscreen'
    from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QTimer,QEventLoop,QThreadPool
    from PySide6.QtGui import QMouseEvent,QDragEnterEvent,QDragMoveEvent,QDropEvent
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    from .model import Project,MediaItem,TimelineItem
    from . import effects_library as L
    from .effects import CATALOG,TITLES,GRAPHICS
    app=QApplication([]);app.setStyle('Fusion');app.setQuitOnLastWindowClosed(False);app.setProperty('kineticTestDiscardUnsaved',True)
    report=dict(passed=False,frozen=bool(getattr(sys,'frozen',False)),checks=[],catalogue_gestures=[],drops=[],os_pointer_control=False,drop_delivery='Qt drag/drop events on actual native editor widgets');window=None
    def wait(ms=30):
        loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
    def check(name,value):
        report['checks'].append(dict(name=name,passed=bool(value)));assert value,name
    def gesture(view,point,end=None):
        end=end or point+QPoint(0,28)
        for kind,pos,button,buttons in ((QEvent.MouseButtonPress,point,Qt.LeftButton,Qt.LeftButton),(QEvent.MouseMove,end,Qt.NoButton,Qt.LeftButton),(QEvent.MouseButtonRelease,end,Qt.LeftButton,Qt.NoButton)):
            app.sendEvent(view.viewport(),QMouseEvent(kind,QPointF(pos),QPointF(view.viewport().mapToGlobal(pos)),button,buttons,Qt.NoModifier))
    try:
        window=MainWindow();window.show();window.autosave_timer.stop();window.resize(1480,900);window.left_panels.select('Effects');wait(100)
        sound=out/'cue.wav'
        with wave.open(str(sound),'wb') as f:
            f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(b''.join(struct.pack('<h',round(math.sin(i*2*math.pi*220/16000)*3000)) for i in range(96000)))
        fixture=Project(media=[MediaItem('m',str(L.asset_directory()/'samples/moving-object.kcpreview'),'video','Moving sample',14,384,216,30),MediaItem('s',str(sound),'audio','Cue',6,has_audio=True)],timeline=[TimelineItem('v','m','video_1',0,3,link_id='pair'),TimelineItem('v2','m','video_1',3,3,in_point=3),TimelineItem('a','s','audio_1',0,3,link_id='pair',gain_db=-8)])
        def reset():
            window.set_project(copy.deepcopy(fixture));window.timeline.set_zoom(65);window.monitor_control.set_level(0);wait(35)
        reset();browser=window.effects_panel;view=browser.list;t=window.timeline
        def category(name):browser.categories.setCurrentItem(browser.categories.findItems(name,Qt.MatchExactly)[0]);wait(60)
        def target(name):
            if name in L.TRANSITION_SET:
                pos=QPoint(round(t.x_for_time(3)),round(t.track_rect('video_1').center().y()));valid=t.transition_target(name,QPointF(pos))
            else:
                audio=L.GROUPS[name]=='Audio';clip=window.project.item_by_id('a' if audio else 'v')
                pos=t.visible_item_rect(clip).center().toPoint();valid=t.effect_target(name,QPointF(pos))
            return pos,valid
        last=[];perform=[False]
        class Drag:
            def __init__(self,*_):pass
            def setPixmap(self,*_):pass
            def setMimeData(self,mime):self.mime=mime
            def exec(self,*_):
                name=bytes(self.mime.data('application/x-kinetic-effect')).decode();last.append(name)
                pos,valid=target(name);check(name+' compatible drop target',bool(valid))
                if name in L.TRANSITION_SET:check(name+' transition MIME',bytes(self.mime.data('application/x-kinetic-transition')).decode()==name)
                if perform[0]:
                    before=window.project.to_dict()
                    enter=QDragEnterEvent(pos,Qt.CopyAction,self.mime,Qt.LeftButton,Qt.NoModifier);app.sendEvent(t.viewport(),enter)
                    move=QDragMoveEvent(pos,Qt.CopyAction,self.mime,Qt.LeftButton,Qt.NoModifier);app.sendEvent(t.viewport(),move)
                    drop=QDropEvent(QPointF(pos),Qt.CopyAction,self.mime,Qt.LeftButton,Qt.NoModifier);app.sendEvent(t.viewport(),drop)
                    check(name+' timeline drop accepted',drop.isAccepted());check(name+' drop mutates project',before!=window.project.to_dict());report['drops'].append(name)
                return Qt.CopyAction if perform[0] else Qt.IgnoreAction
        with patch('kinetic_cut.workspace.QDrag',Drag),patch('kinetic_cut.feature_packs.available',return_value=True):
            category('All Effects')
            for mode in ('grid','list'):
                browser.set_view(mode);wait(60)
                check(mode+' drag enabled',view.dragEnabled() and not view.hasAutoScroll())
                for name in L.ALL_NAMES:
                    item=view.findItems(name,Qt.MatchExactly)[0];view.scrollToItem(item);app.processEvents()
                    r=view.visualItemRect(item);point=QPoint(r.left()+12,r.top()+15);before=view.verticalScrollBar().value()
                    gesture(view,point);check(mode+' '+name+' starts correct drag',last[-1]==name);check(mode+' '+name+' keeps scroll',view.verticalScrollBar().value()==before)
                    report['catalogue_gestures'].append(dict(mode=mode,name=name))
            perform[0]=True
            for name in ('Gaussian Blur','Directional Blur','Punch Zoom','Sepia','Fade In / Out','Text','Headline','Circle','Cross Dissolve'):
                reset();category('All Effects');browser.set_list();wait(60)
                item=view.findItems(name,Qt.MatchExactly)[0];view.scrollToItem(item);wait(30);before=view.verticalScrollBar().value();r=view.visualItemRect(item)
                gesture(view,QPoint(r.left()+12,r.top()+15));wait(50);check(name+' stays scrolled after placement',view.verticalScrollBar().value()==before)
            perform[0]=False
            for theme in ('default','final_cut_obsidian','ableton_gray'):
                window.apply_theme(theme,save=False)
                for size in ((1480,900),(1100,700)):
                    window.resize(*size);category('All Effects');wait(70);bar=view.verticalScrollBar();bar.setValue(bar.maximum()//2);before=bar.value()
                    category('Titles');category('All Effects');check(theme+str(size)+' category scroll restored',bar.value()==before)
                    nav=browser.categories;nav.verticalScrollBar().setValue(0);point=nav.visualItemRect(nav.item(0)).center();gesture(nav,point,QPoint(point.x(),nav.viewport().height()+50));wait(60)
                    check(theme+str(size)+' held category does not move',browser.category()=='All Effects' and nav.verticalScrollBar().value()==0)
                    browser.toggle_favourite('Punch Zoom') if 'Punch Zoom' not in browser.favourites else None
                    view.scrollToItem(view.findItems('Punch Zoom',Qt.MatchExactly)[0]);wait(30);browser.grab().save(str(out/f'effects-{theme}-{size[0]}.png'))
                    reset();window.link_toggle.setChecked(True);window.timeline.linked_selection=True;window.timeline.select_ids({'v','a'},'v');i=window.inspector;i.tabs.setCurrentIndex(1);wait(30)
                    check(theme+str(size)+' linked audio visible',i.audio.isVisible() and i.volume.spin.value()==-8)
                    i.volume.spin.setValue(-12);check(theme+str(size)+' linked audio edit only',window.project.item_by_id('a').gain_db==-12 and window.project.item_by_id('v').gain_db==0)
                    i.set_audio_levels({'audio_1':(.5,.25,False)});check(theme+str(size)+' linked audio meter','-6.0' in i.level_bars[0].format())
                    i.grab().save(str(out/f'linked-audio-{theme}-{size[0]}.png'))
                    window.link_toggle.click();window.refresh_inspector();check(theme+str(size)+' unlink selection hides audio',not i.audio.isVisible())
        check('all catalogue entries retained',len(L.ALL_NAMES)==195)
        check('blur category merged',CATALOG['Open FX / Blur']==['Gaussian Blur','Directional Blur','Radial Zoom Blur','Tilt Shift'] and 'Blur & Focus' not in CATALOG)
        report['passed']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        if window is not None:window.close()
        report['workers_finished']=QThreadPool.globalInstance().waitForDone(10000);wait(150)
        report['passed']=report['passed'] and report['workers_finished']
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(passed=report['passed'],error=report.get('error'),checks=len(report['checks']),gestures=len(report['catalogue_gestures']),drops=report['drops'])),flush=True)
    return 0 if report['passed'] else 1
