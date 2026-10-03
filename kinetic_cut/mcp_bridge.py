"""Stdio MCP bridge connecting Antigravity (and other stdio MCP hosts) to running Kinetic Cut."""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from .assistant import connection_settings


def send_mcp_request(url, token, payload, timeout=120):
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
    parsed = urllib.parse.urlsplit(url)
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'MCP-Protocol-Version': payload.get('params', {}).get('protocolVersion', '2025-11-25') if isinstance(payload.get('params'), dict) else '2025-11-25',
            'Host': parsed.netloc,
        },
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status == 200:
            raw = resp.read().decode('utf-8')
            return json.loads(raw)
        return None


def run_bridge():
    def _safe_write(data_dict):
        try:
            payload = (json.dumps(data_dict, ensure_ascii=False) + '\n').encode('utf-8')
            if hasattr(sys.stdout, 'buffer') and sys.stdout.buffer is not None:
                sys.stdout.buffer.write(payload)
                sys.stdout.buffer.flush()
            else:
                sys.stdout.write(json.dumps(data_dict, ensure_ascii=False) + '\n')
                sys.stdout.flush()
        except Exception:
            pass

    def _safe_readline():
        try:
            if hasattr(sys.stdin, 'buffer') and sys.stdin.buffer is not None:
                line_bytes = sys.stdin.buffer.readline()
                if not line_bytes:
                    return ''
                return line_bytes.decode('utf-8', errors='replace')
            return sys.stdin.readline()
        except Exception:
            return ''

    while True:
        try:
            line = _safe_readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            request = json.loads(line)
        except Exception:
            continue

        if not isinstance(request, dict):
            continue

        req_id = request.get('id')
        method = request.get('method', '')

        # Attempt to reach Kinetic Cut HTTP server
        max_attempts = 3 if method == 'initialize' else 1
        response = None
        last_error = None

        for attempt in range(max_attempts):
            try:
                config = connection_settings()
                port = int(config.get('port', 48765))
                token = config.get('token', '')
                url = f"http://127.0.0.1:{port}/mcp"

                response = send_mcp_request(url, token, request)
                last_error = None
                break
            except urllib.error.HTTPError as http_err:
                try:
                    err_body = http_err.read().decode('utf-8')
                    response = json.loads(err_body)
                    last_error = None
                except Exception:
                    last_error = f"HTTP {http_err.code}: {http_err.reason}"
                break
            except urllib.error.URLError as url_err:
                last_error = str(url_err.reason) if hasattr(url_err, 'reason') else str(url_err)
                if attempt < max_attempts - 1:
                    time.sleep(0.5)
            except Exception as exc:
                last_error = str(exc)
                break

        if response is not None:
            _safe_write(response)
        elif req_id is not None and last_error is not None:
            error_msg = (
                f"Kinetic Cut is not running or AI Assistant connection is disabled ({last_error}). "
                "Please launch Kinetic Cut and click 'Enable connection' in the AI Assistant panel."
            )
            err_resp = {
                'jsonrpc': '2.0',
                'id': req_id,
                'error': {
                    'code': -32000,
                    'message': error_msg
                }
            }
            _safe_write(err_resp)

    return 0


if __name__ == '__main__':
    sys.exit(run_bridge())
