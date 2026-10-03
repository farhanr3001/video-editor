"""Opt-in packaged MCP end-to-end test against an isolated editor profile."""
def run(output):
    import os,sys,json,threading,time,traceback,base64
    from pathlib import Path
    output=Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    os.environ['KINETIC_CUT_HOME']=str(output/'home'); os.environ['QT_QPA_PLATFORM']='offscreen'
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QImage,QColor,QFontDatabase
    from .ui import MainWindow
    from .theme import STYLESHEET
    from .assistant_client import Client
    app=QApplication([]); app.setStyle('Fusion'); app.setStyleSheet(STYLESHEET)
    for font in ('arial.ttf','arialbd.ttf','segoeui.ttf','segoeuib.ttf'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/font))
    window=MainWindow(); window.show(); window.autosave_timer.stop(); connection=window.assistant_connection
    connection.config['port']=0; connection.start(); connection.show()
    image=QImage(320,180,QImage.Format_RGBA8888); image.fill(QColor('#254357')); image.save(str(output/'source.png'))
    report={'frozen':bool(getattr(sys,'frozen',False))}; finished=threading.Event()
    def client_work():
        try:
            client=Client(connection.server.url,connection.config['token']); info=client.initialize('Codex MCP verification')
            report['server']=info['serverInfo']; report['tools']=[t['name'] for t in client.request('tools/list')['tools']]
            state=client.value('get_state'); initial=state['revision']
            result=client.value('apply_edits',revision=initial,operations=[dict(op='add',collection='timeline',values=dict(title_text='MCP connected',duration=1,fade_in=.2,fade_out=.2)),dict(op='settings',values=dict(width=320,height=180,fps=20))])
            changed=client.value('get_state'); assert changed['project']['timeline'][0]['title_text']=='MCP connected'
            client.value('history',direction='undo'); assert not client.value('get_state')['project']['timeline']
            client.value('history',direction='redo'); assert client.value('get_state')['project']['timeline']
            report['edit_undo_redo']=True
            client.value('seek',seconds=.5); time.sleep(.15)
            preview=client.call('get_preview'); (output/'mcp-preview.png').write_bytes(base64.b64decode(preview['content'][1]['data']))
            client.value('import_media',paths=[str(output/'source.png')])
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                jobs=client.value('get_jobs')['tasks']
                if jobs and jobs[-1]['state']!='Running':break
                time.sleep(.05)
            assert jobs[-1]['state']=='Complete',jobs
            state=client.value('get_state'); assert len(state['project']['media'])==1
            report['import_completed']=True
            target=output/f'mcp-render-{time.time_ns()}.mp4'
            client.value('queue_export',path=str(target),encoder='CPU',start=True)
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                jobs=client.value('get_jobs')['renders']
                if jobs[-1]['state'] not in {'Queued','Rendering'}:break
                time.sleep(.1)
            assert jobs[-1]['state']=='Complete',jobs
            assert target.stat().st_size>1000
            report['render_complete']=True
            ui=client.value('inspect_ui'); assert any(c['text']=='Connect to Codex' for c in ui['controls'])
            frame=client.call('get_preview',area='workspace'); (output/'mcp-workspace.png').write_bytes(base64.b64decode(frame['content'][1]['data']))
            report['passed']=True
        except Exception:report.update(passed=False,error=traceback.format_exc())
        finally:finished.set()
    thread=threading.Thread(target=client_work,daemon=True); thread.start()
    timer=QTimer(); timer.setInterval(40)
    def poll():
        if finished.is_set():
            timer.stop(); connection.dialog.grab().save(str(output/'mcp-panel.png'))
            (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); window.close(); app.exit(0 if report.get('passed') else 1)
    timer.timeout.connect(poll); timer.start(); QTimer.singleShot(90000,lambda:app.exit(2)); return app.exec()
