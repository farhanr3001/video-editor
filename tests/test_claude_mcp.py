"""Claude setup preservation and actual stdio -> authenticated editor tool flow."""
import concurrent.futures,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QEvent,QEventLoop,QThreadPool,QTimer
from PySide6.QtWidgets import QApplication,QMessageBox,QPushButton
from kinetic_cut.assistant import claude_config,claude_snippet,claude_code_command,register_claude,configure_startup_connection
from kinetic_cut.assistant_api import revision

class ClaudeSetupTests(unittest.TestCase):
    def test_merge_backup_idempotence_and_malformed_preservation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'claude_desktop_config.json'
            original={'preferences':{'language':'en'},'mcpServers':{'other':{'command':'keep-me'}}}
            p.write_text(json.dumps(original),encoding='utf-8')
            register_claude(p,command='C:/Apps/Kinetic Cut/KineticCut.exe',args=['--mcp-bridge'])
            data=json.loads(p.read_text(encoding='utf-8'));self.assertEqual(data['preferences'],original['preferences']);self.assertEqual(data['mcpServers']['other'],original['mcpServers']['other'])
            self.assertEqual(data['mcpServers']['kinetic-cut']['args'],['--mcp-bridge'])
            backups=list(p.parent.glob('*.before-kinetic-cut-*.json'));self.assertEqual(len(backups),1);self.assertEqual(json.loads(backups[0].read_text(encoding='utf-8')),original)
            register_claude(p,command='C:/Apps/Kinetic Cut/KineticCut.exe',args=['--mcp-bridge']);self.assertEqual(len(list(p.parent.glob('*.before-kinetic-cut-*.json'))),1)
            for bad in ['{bad','[]','{"mcpServers":[]}']:
                p.write_text(bad,encoding='utf-8')
                with self.assertRaises(ValueError):register_claude(p)
                self.assertEqual(p.read_text(encoding='utf-8'),bad)
    def test_windows_default_and_absolute_source_or_frozen_commands(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,APPDATA=d):
            p=Path(register_claude(command='worker',args=['--mcp-bridge']))
            self.assertEqual(p,Path(d)/'Claude/claude_desktop_config.json')
        entry=claude_config();self.assertTrue(Path(entry['command']).is_absolute());self.assertNotIn('cwd',entry)
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable','C:/Editor/KineticCut.exe'):
            entry=claude_config();self.assertEqual(entry['args'],['--mcp-bridge'])
        snippet=json.loads(claude_snippet('worker',['--mcp-bridge']));self.assertEqual(snippet['mcpServers']['kinetic-cut']['command'],'worker')
        command=claude_code_command("C:/O'Brien/Editor.exe",['--mcp-bridge'])
        self.assertIn('--scope user kinetic-cut',command);self.assertIn("O''Brien",command)

class ClaudeLiveTests(unittest.TestCase):
    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.app=QApplication.instance();self.w=MainWindow();self.w.autosave_timer.stop();self.c=self.w.assistant_connection;self.c.config['port']=0;self.c.start();self.assertIsNotNone(self.c.server)
    def tearDown(self):
        self.c.stop();self.w.close();QThreadPool.globalInstance().waitForDone(10000);self.w.deleteLater();self.app.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents()
    def test_buttons_registration_copy_and_headless_startup(self):
        self.c.show();self.app.processEvents();dialog=self.c.dialog
        buttons={b.text():b for b in dialog.findChildren(QPushButton)}
        self.assertIn('Connect to Claude Desktop',buttons);self.assertIn('Copy Claude Code command',buttons)
        with patch('kinetic_cut.assistant.register_claude',return_value='test-config') as reg,patch.object(QMessageBox,'information'),patch('kinetic_cut.config.save_settings'):
            buttons['Connect to Claude Desktop'].click();reg.assert_called_once();self.assertTrue(dialog.auto.isChecked())
        buttons['Copy Claude Desktop JSON'].click();self.assertIn('kinetic-cut',json.loads(QApplication.clipboard().text())['mcpServers'])
        buttons['Copy Claude Code command'].click();self.assertTrue(QApplication.clipboard().text().startswith('claude mcp add-json '))
        with patch('kinetic_cut.assistant.register_claude',return_value='test-config') as reg,patch('kinetic_cut.config.save_settings'):
            configure_startup_connection(self.w,['--connect-claude']);reg.assert_called_once()
        self.assertFalse(self.c.verified)
    def test_real_stdio_handshake_edit_preview_undo_and_exit(self):
        entry=claude_config();worker=os.environ.get('KINETIC_MCP_TEST_WORKER')
        command=[worker,'--mcp-bridge'] if worker else [entry['command'],*entry['args']]
        def req(i,m,p=None):return dict(jsonrpc='2.0',id=i,method=m,params=p or {})
        messages=[req(1,'initialize',dict(protocolVersion='2025-11-25',clientInfo=dict(name='Claude Desktop',version='test'),capabilities={})),dict(jsonrpc='2.0',method='notifications/initialized'),req(2,'tools/list'),req(3,'tools/call',dict(name='apply_edits',arguments=dict(revision=revision(self.w.project),operations=[dict(op='add',collection='timeline',values=dict(title_text='Claude ✓',duration=1))]))),req(4,'tools/call',dict(name='get_preview',arguments={})),req(5,'tools/call',dict(name='history',arguments=dict(direction='undo')))]
        payload=('\n'.join(json.dumps(v,ensure_ascii=False) for v in messages)+'\n').encode('utf-8')
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            future=pool.submit(subprocess.run,command,input=payload,capture_output=True,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            loop=QEventLoop();timer=QTimer();timer.timeout.connect(lambda:loop.quit() if future.done() else None);timer.start(5);QTimer.singleShot(45000,loop.quit);loop.exec();timer.stop();result=future.result(timeout=1)
        self.assertEqual(result.returncode,0,result.stderr.decode('utf-8',errors='replace'))
        rows=[json.loads(line) for line in result.stdout.splitlines()];self.assertEqual([v['id'] for v in rows],[1,2,3,4,5]);self.assertTrue(all('result' in row for row in rows),rows)
        self.assertEqual(rows[0]['result']['serverInfo']['name'],'Kinetic Cut');self.assertEqual(self.c.client,'Claude Desktop');self.assertTrue(self.c.verified)
        self.assertIn('apply_edits',{v['name'] for v in rows[1]['result']['tools']})
        self.assertFalse(rows[2]['result'].get('isError'));self.assertEqual(rows[3]['result']['content'][1]['type'],'image');self.assertFalse(rows[4]['result'].get('isError'));self.assertFalse(self.w.project.timeline)

if __name__=='__main__':unittest.main()
