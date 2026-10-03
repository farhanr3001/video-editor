"""MCP connection/status panel. Deliberately NOT an embedded AI chatbot."""
from .theme_widgets import set_ui_style
import json
import os
import secrets
import threading
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, Qt, QTimer
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QPlainTextEdit,QCheckBox,QMessageBox)
from .assistant_api import EditorAPI, TOOLS
from .assistant_server import MCPServer


def connection_file():
    from .config import CONFIG_DIR
    return CONFIG_DIR/'assistant-connection.json'


def connection_settings():
    path=connection_file()
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data.get('token'),str) and len(data['token'])>=32:return data
    except (OSError,ValueError,TypeError):pass
    return dict(token=secrets.token_urlsafe(32),port=48765)


def codex_snippet(url,token):
    return ('[mcp_servers.kinetic_cut]\nurl = '+json.dumps(url)+'\n'
            'http_headers = { Authorization = '+json.dumps('Bearer '+token)+' }\n'
            'startup_timeout_sec = 10\ntool_timeout_sec = 30\n')


def register_codex(url,token,path=None):
    """Preserve all unrelated configuration; backup before this one-server update."""
    import re
    path=Path(path) if path else Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml'
    path.parent.mkdir(parents=True,exist_ok=True)
    original=path.read_text(encoding='utf-8') if path.exists() else ''
    # Do not replace a similarly named plugin/table. Our generated table is flat.
    pattern=r'(?ms)^\[mcp_servers\.kinetic_cut\]\s*\n.*?(?=^\[|\Z)'
    if re.search(r'^\[mcp_servers\.kinetic_cut\.',original,re.M):
        raise ValueError('Existing nested Kinetic Cut configuration: use Copy MCP configuration and update it manually.')
    snippet=codex_snippet(url,token)
    updated=re.sub(pattern,lambda _:snippet+'\n',original,count=1) if re.search(pattern,original) else original.rstrip()+'\n\n'+snippet
    if updated==original:return str(path)
    if path.exists():
        backup=path.with_name('config.before-kinetic-cut-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)+'.toml')
        backup.write_text(original,encoding='utf-8')
    pending=path.with_name(path.name+'.kinetic-cut.tmp'); pending.write_text(updated,encoding='utf-8'); pending.replace(path)
    return str(path)


def antigravity_config(command=None, args=None, cwd=None):
    import sys
    if command is None:
        if getattr(sys, 'frozen', False):
            command = str(Path(sys.executable).resolve())
            args = ['--mcp-bridge']
            cwd = None
        else:
            project_dir = Path(__file__).resolve().parent.parent
            venv_py = project_dir / '.venv' / 'Scripts' / 'python.exe'
            command = str(venv_py.resolve()) if venv_py.exists() else str(Path(sys.executable).resolve())
            args = ['-m', 'kinetic_cut.mcp_bridge']
            cwd = str(project_dir)
    entry = {'command': command, 'args': args or []}
    if cwd:
        entry['cwd'] = cwd
    return entry


def antigravity_snippet(command=None, args=None, cwd=None):
    return json.dumps({'mcpServers': {'kinetic-cut': antigravity_config(command, args, cwd)}}, indent=2)


def register_antigravity(path=None, command=None, args=None, cwd=None):
    """Safely register Kinetic Cut in Antigravity mcp_config.json, preserving other servers."""
    targets = [Path(path)] if path else [
        Path.home() / '.gemini' / 'config' / 'mcp_config.json',
        Path.home() / '.gemini' / 'antigravity-ide' / 'mcp_config.json',
        Path(__file__).resolve().parent.parent / '.agents' / 'mcp_config.json',
    ]
    entry = antigravity_config(command, args, cwd)
    updated_paths = []
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            original = target.read_text(encoding='utf-8') if target.exists() else ''
            try:
                data = json.loads(original) if original.strip() else {}
            except Exception:
                data = {}
            if not isinstance(data, dict):
                data = {}
            servers = data.setdefault('mcpServers', {})
            servers['kinetic-cut'] = entry
            content = json.dumps(data, indent=2) + '\n'
            if content != original:
                if target.exists() and original.strip():
                    backup = target.with_name('mcp_config.before-kinetic-cut-' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3) + '.json')
                    backup.write_text(original, encoding='utf-8')
                pending = target.with_name(target.name + '.kinetic-cut.tmp')
                pending.write_text(content, encoding='utf-8')
                pending.replace(target)
            updated_paths.append(str(target))
        except Exception:
            pass
    return updated_paths[0] if updated_paths else str(targets[0])


class AssistantConnection(QObject):
    requested=Signal(object)
    changed=Signal()
    def __init__(self,window):
        super().__init__(window); self.w=window; self.api=EditorAPI(window); self.server=None
        self.config=connection_settings(); self.client=''; self.last_seen=0.; self.activity=[]; self.pending=[]; self.lock=threading.Lock()
        self.requested.connect(self.execute,Qt.QueuedConnection); self.dialog=None; self.error=''
        self.badge_timer=QTimer(self); self.badge_timer.timeout.connect(self.refresh_button); self.badge_timer.start(5000)
        if window.settings.get('assistant_enabled',False):self.start()
    def note(self,message):
        self.activity.append(time.strftime('%H:%M:%S')+'  '+message); self.activity=self.activity[-100:]; self.changed.emit()
    @property
    def verified(self):return bool(self.server and self.client and self.last_seen and not self.error)
    def status_text(self):
        if self.error:return self.error
        if not self.server:return 'Connection disabled'
        if not self.verified:return 'Ready · Waiting for an MCP client to connect'
        age=max(0,int(time.time()-self.last_seen))
        return f'Client verified: {self.client} · Last request {age}s ago'+(' · Idle' if age>60 else '')
    def refresh_button(self):
        from .icons import lucide_icon
        button=getattr(self.w,'assistant_button',None)
        if button is None:return
        button.setIcon(lucide_icon('connection-check' if self.verified else 'sparkles','#58cf87' if self.verified else '#d8dae0',18))
        button.setProperty('clientVerified',self.verified)
        button.setToolTip('MCP connection setup/status — no built-in chatbot\n'+self.status_text())
        button.setAccessibleDescription(self.status_text())
    def start(self):
        if self.server:return
        try:
            self.server=MCPServer(self.dispatch,TOOLS,self.config['token'],int(self.config.get('port',48765)))
            self.config['port']=self.server.port
            connection_file().write_text(json.dumps(self.config,indent=2),encoding='utf-8')
            self.error=''; self.note('Local MCP connection enabled. Waiting for an assistant.')
        except OSError as error:
            if self.server:self.server.close(); self.server=None
            self.error='Could not start MCP. Another Kinetic Cut instance may be using the port. '+str(error); self.note(self.error)
    def stop(self):
        with self.lock:
            for request in self.pending:
                request['cancelled']=True; request['error']='MCP connection stopped'; request['event'].set()
        if self.server:self.server.close(); self.server=None
        self.client=''; self.last_seen=0.; self.note('MCP connection stopped.')
    def dispatch(self,name,args):
        request=dict(name=name,args=args,event=threading.Event(),deadline=time.monotonic()+8,cancelled=False)
        with self.lock:self.pending.append(request)
        self.requested.emit(request)
        if not request['event'].wait(10):
            request['cancelled']=True
            with self.lock:
                if request in self.pending:self.pending.remove(request)
            raise TimeoutError('Editor is busy. Request expired; inspect state before retrying.')
        if request.get('error'):raise ValueError(request['error'])
        return request.get('result')
    @Slot(object)
    def execute(self,request):
        try:
            if request['cancelled'] or time.monotonic()>request['deadline']:raise TimeoutError('Request expired before execution')
            self.last_seen=time.time()
            if request['name']=='_connected':
                self.client=str(request['args']['client'])[:100]; self.note('Handshake received from '+self.client); request['result']={}
            else:
                # Stateless clients can reuse their tool list after the editor
                # restarts. A valid authenticated request also verifies access.
                if not self.client:self.client='MCP client'
                self.note(request['name']); request['result']={} if request['name']=='_activity' else self.api.dispatch(request['name'],request['args'])
        except Exception as error:
            request['error']=str(error); self.note('Request failed: '+str(error)[:250])
        finally:
            with self.lock:
                if request in self.pending:self.pending.remove(request)
            request['event'].set()
    def show(self):
        if self.dialog is None:self.dialog=ConnectionDialog(self)
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()


def configure_startup_connection(window,arguments):
    """Command-line setup may enable/configure MCP, but never opens its panel."""
    if not {'--enable-mcp','--connect-codex','--connect-antigravity'}.intersection(arguments):return
    from .config import save_settings
    connection=window.assistant_connection; connection.start()
    if connection.server:
        window.settings['assistant_enabled']=True; save_settings(window.settings)
        if '--connect-codex' in arguments:
            register_codex(connection.server.url,connection.config['token'])
            connection.note('Codex configured. Reload MCP servers / restart Codex to load tools.')
        if '--connect-antigravity' in arguments:
            path=register_antigravity()
            connection.note('Antigravity configured ('+path+'). Reload MCP servers / restart Antigravity to load tools.')


class ConnectionDialog(QDialog):
    def __init__(self,connection):
        super().__init__(connection.w); self.c=connection; self.setWindowTitle('AI Assistant — MCP Connection'); self.resize(640,540)
        root=QVBoxLayout(self)
        title=QLabel('Connect your AI assistant to Kinetic Cut'); set_ui_style(title, 'font-size:17px;font-weight:600'); root.addWidget(title)
        intro=QLabel('This is a connection panel, not a built-in chatbot. Keep Kinetic Cut open and give editing instructions in Antigravity, Codex, or another MCP-compatible assistant.'); intro.setWordWrap(True); root.addWidget(intro)
        status_row=QHBoxLayout(); self.status_icon=QLabel(); status_row.addWidget(self.status_icon)
        self.status=QLabel(); self.status.setWordWrap(True); status_row.addWidget(self.status,1); root.addLayout(status_row)
        self.address=QLabel(); self.address.setTextInteractionFlags(Qt.TextSelectableByMouse); root.addWidget(self.address)
        
        row=QHBoxLayout(); self.toggle=QPushButton(); self.toggle.clicked.connect(self.toggle_connection); row.addWidget(self.toggle)
        install_ag=QPushButton('Connect to Antigravity'); install_ag.clicked.connect(self.install_antigravity); row.addWidget(install_ag)
        install=QPushButton('Connect to Codex'); install.clicked.connect(self.install); row.addWidget(install)
        root.addLayout(row)

        copy_row=QHBoxLayout()
        copy_ag=QPushButton('Copy Antigravity JSON'); copy_ag.clicked.connect(self.copy_antigravity); copy_row.addWidget(copy_ag)
        copy_button=QPushButton('Copy Codex TOML'); copy_button.clicked.connect(self.copy_config); copy_row.addWidget(copy_button)
        root.addLayout(copy_row)

        self.auto=QCheckBox('Enable this connection whenever Kinetic Cut opens'); self.auto.setChecked(connection.w.settings.get('assistant_enabled',False)); self.auto.toggled.connect(self.automatic); root.addWidget(self.auto)
        guide=QLabel('1. Enable the connection above.\n2. Choose Connect to Antigravity (or Connect to Codex), or copy the configuration into your MCP client.\n3. Reload MCP servers / restart the client if needed, then ask it to inspect Kinetic Cut.\n\nThe status below shows a real handshake and recent tool activity. A configuration entry alone does not mean an assistant is connected.'); guide.setWordWrap(True); root.addWidget(guide)
        privacy=QLabel('Local access only. Tools can edit the project and use editor controls; timeline edits are undoable. Preview images and project information requested by your assistant are shared with that assistant.'); privacy.setWordWrap(True); root.addWidget(privacy)
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); root.addWidget(self.log,1)
        close=QPushButton('Close'); close.clicked.connect(self.close); root.addWidget(close,0,Qt.AlignRight)
        connection.changed.connect(self.refresh); self.timer=QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1000); self.refresh()
    def refresh(self):
        c=self.c
        from .icons import lucide_icon
        self.status_icon.setPixmap(lucide_icon('connection-check','#58cf87',22).pixmap(22,22)); self.status_icon.setVisible(c.verified)
        self.status.setText(c.status_text()); set_ui_style(self.status, 'color:@success' if c.verified else '')
        c.refresh_button(); self.address.setText(c.server.url if c.server else f"http://127.0.0.1:{c.config['port']}/mcp")
        self.toggle.setText('Disconnect' if c.server else 'Enable connection')
        content='\n'.join(c.activity)
        if self.log.toPlainText()!=content:self.log.setPlainText(content); self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
    def toggle_connection(self):self.c.stop() if self.c.server else self.c.start()
    def automatic(self,enabled):
        from .config import save_settings
        self.c.w.settings['assistant_enabled']=enabled; save_settings(self.c.w.settings)
    def install_antigravity(self):
        self.c.start()
        if not self.c.server:return
        try:
            path=register_antigravity(); self.auto.setChecked(True)
            self.c.note('Antigravity configuration saved. Reload MCP servers or restart Antigravity to load tools.')
            QMessageBox.information(self,'MCP configured','Kinetic Cut was added to Antigravity!\n\nConfiguration written to:\n'+path+'\n\nTo use it:\n1. Reload MCP servers or restart Antigravity IDE.\n2. Ask the agent in Antigravity to inspect or edit your Kinetic Cut project!')
        except Exception as error:QMessageBox.warning(self,'Connection setup',str(error))
    def install(self):
        self.c.start()
        if not self.c.server:return
        try:
            path=register_codex(self.c.server.url,self.c.config['token']); self.auto.setChecked(True)
            self.c.note('Codex configuration saved. Reload MCP servers or restart Codex to load the tools.')
            QMessageBox.information(self,'MCP configured','Kinetic Cut was added to Codex.\n\nReload MCP servers or restart Codex, then ask it to inspect Kinetic Cut.\n\nConfiguration: '+path)
        except Exception as error:QMessageBox.warning(self,'Connection setup',str(error))
    def copy_antigravity(self):
        self.c.start()
        QApplication.clipboard().setText(antigravity_snippet())
        self.c.note('Antigravity MCP configuration copied to clipboard.')
    def copy_config(self):
        self.c.start()
        if self.c.server:
            QApplication.clipboard().setText(codex_snippet(self.c.server.url,self.c.config['token'])); self.c.note('MCP configuration copied. Treat the local access token as private.')
