"""Small, authenticated, loopback-only Streamable HTTP MCP transport.

No model, subprocess, web framework or network listener is loaded until enabled.
Requests cross to Qt through a queued signal; network threads never touch widgets.
"""
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSIONS = ('2025-03-26', '2025-06-18', '2025-11-25')
INSTRUCTIONS = ('Kinetic Cut controls the running local editor. Start with get_state and '
    'get_capabilities. Use revision-checked apply_edits for atomic undoable changes. '
    'Time is in seconds; crop/position coordinates are normalized. Import/render '
    'return jobs: poll get_jobs. Read preview frames to verify edits. Do not claim '
    'a render succeeded until its state is Complete. Source files are never deleted '
    'by timeline edits. UI controls can open dialogs; inspect_ui exposes those too.')


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class MCPServer:
    def __init__(self, dispatch, tools, token, port=48765):
        self.dispatch = dispatch
        self.tools = tools
        self.token = token
        self.server = LocalServer(('127.0.0.1', port), self.handler())
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': .1}, daemon=True,
                                       name='KineticMCP')
        self.thread.start()

    @property
    def url(self):return f'http://127.0.0.1:{self.port}/mcp'

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=1)

    def handler(self):
        bridge = self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup(); self.connection.settimeout(10)
            def log_message(self, *args):pass  # Never log tokens or media contents.
            def reply(self, status, value=None):
                data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8') if value is not None else b''
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if data:self.wfile.write(data)
            def authorized(self):
                if self.path != '/mcp':self.reply(404); return False
                if self.headers.get('Host') not in {f'127.0.0.1:{bridge.port}', f'localhost:{bridge.port}'}:
                    self.reply(403); return False
                origin = self.headers.get('Origin')
                if origin and origin not in {f'http://127.0.0.1:{bridge.port}', f'http://localhost:{bridge.port}'}:
                    self.reply(403); return False
                if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+bridge.token):
                    self.reply(401); return False
                if self.headers.get('MCP-Protocol-Version', VERSIONS[0]) not in VERSIONS:
                    self.reply(400, {'error':'Unsupported MCP protocol version'}); return False
                return True
            def do_GET(self):
                if self.authorized():self.reply(405)  # JSON responses, no SSE stream.
            def do_DELETE(self):
                if self.authorized():self.reply(405)  # Stateless transport.
            def do_POST(self):
                if not self.authorized():
                    try:
                        length = int(self.headers.get('Content-Length', '0'))
                        if 0 < length <= 4_000_000:self.rfile.read(length)
                    except Exception:pass
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 4_000_000:self.reply(413); return
                    if not self.headers.get('Content-Type', '').startswith('application/json'):
                        self.reply(415); return
                    request = json.loads(self.rfile.read(length))
                    if not isinstance(request, dict) or request.get('jsonrpc') != '2.0':raise ValueError('Expected JSON-RPC 2.0 object')
                    method = request.get('method', '')
                    params = request.get('params') or {}
                    if not isinstance(params, dict):raise ValueError('params must be an object')
                except (ValueError, OSError) as error:
                    self.reply(400, {'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':str(error)}}); return
                if 'id' not in request:self.reply(202); return
                result = None; error = None
                try:
                    if method == 'initialize':
                        version = params.get('protocolVersion')
                        result = {'protocolVersion': version if version in VERSIONS else VERSIONS[-1],
                                  'capabilities':{'tools':{'listChanged':False}},
                                  'serverInfo':{'name':'Kinetic Cut','version':'1.0.0'},
                                  'instructions':INSTRUCTIONS}
                        bridge.dispatch('_connected', {'client':params.get('clientInfo', {}).get('name','MCP client')})
                    elif method == 'ping':bridge.dispatch('_activity',{}); result = {}
                    elif method == 'tools/list':bridge.dispatch('_activity',{}); result = {'tools':bridge.tools}
                    elif method == 'tools/call':
                        name = params.get('name'); arguments = params.get('arguments') or {}
                        if name not in {t['name'] for t in bridge.tools}:raise ValueError('Unknown tool')
                        if not isinstance(arguments, dict):raise ValueError('arguments must be an object')
                        try:
                            value = bridge.dispatch(name, arguments)
                            result = value if isinstance(value, dict) and '_mcp_content' in value else {'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False,allow_nan=False)}]}
                            if '_mcp_content' in result:result = {'content':result['_mcp_content']}
                        except Exception as exc:
                            result = {'isError':True,'content':[{'type':'text','text':str(exc)}]}
                    else:error = {'code':-32601,'message':'Method not found'}
                except Exception as exc:error = {'code':-32602,'message':str(exc)}
                try:self.reply(200, {'jsonrpc':'2.0','id':request['id'], **({'error':error} if error else {'result':result})})
                except (BrokenPipeError, ConnectionResetError, OSError):pass
        return Handler
