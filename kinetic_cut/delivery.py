from __future__ import annotations

import http.server
import os
import shutil
import socket
from .process import run as run_process
import threading
from pathlib import Path
from urllib.parse import quote


def detect_adb_devices() -> list[str]:
    adb = shutil.which("adb")
    if not adb:
        return []
    result = run_process([adb, "devices"], capture_output=True, text=True)
    return [line.split()[0] for line in result.stdout.splitlines()[1:]
            if line.strip().endswith("device")]


def detect_mtp_devices() -> list[str]:
    if os.name != "nt":
        return []
    script = "$s=New-Object -ComObject Shell.Application; $s.Namespace(17).Items() | Where-Object {$_.IsFolder -and $_.Type -match 'Portable|Phone|Device'} | ForEach-Object {$_.Name}"
    result = run_process(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def send_adb(file_path: str, destination: str, device: str | None = None) -> str:
    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("ADB is not installed or not on PATH.")
    prefix = [adb] + (["-s", device] if device else [])
    run_process(prefix + ["shell", "mkdir", "-p", destination], check=True)
    run_process(prefix + ["push", file_path, destination.rstrip("/") + "/" + Path(file_path).name], check=True)
    return destination.rstrip("/") + "/" + Path(file_path).name


def send_mtp(file_path: str, device_name: str, folder_parts: list[str] | None = None) -> str:
    if os.name != "nt":
        raise RuntimeError("MTP delivery is currently available on Windows only.")
    folder_parts = folder_parts or ["Internal shared storage", "Movies", "KineticCut"]
    quoted_parts = ",".join("'" + part.replace("'", "''") + "'" for part in folder_parts)
    script = rf'''
param([string]$Source,[string]$Device)
$shell = New-Object -ComObject Shell.Application
$root = $shell.Namespace(17)
$node = $root.ParseName($Device)
if ($null -eq $node) {{ throw "Device not found: $Device" }}
$folder = $node.GetFolder
$parts = @({quoted_parts})
foreach ($part in $parts) {{
  $next = $folder.ParseName($part)
  if ($null -eq $next) {{
    $folder.NewFolder($part)
    Start-Sleep -Milliseconds 350
    $next = $folder.ParseName($part)
  }}
  if ($null -eq $next) {{ throw "Phone folder unavailable: $part" }}
  $folder = $next.GetFolder
}}
$folder.CopyHere($Source, 20)
Start-Sleep -Seconds 2
'''
    temp = Path(os.environ.get("TEMP", ".")) / "kinetic-cut-mtp.ps1"
    temp.write_text(script, encoding="utf-8")
    result = run_process(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", str(temp), file_path, device_name], capture_output=True, text=True)
    try:
        temp.unlink(missing_ok=True)
    except OSError:
        pass
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "MTP copy failed")
    return "/".join(folder_parts) + "/" + Path(file_path).name


class WirelessShare:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path).resolve()
        self.server: http.server.ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> str:
        file_path = self.file_path

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    page = ("<!doctype html><meta name=viewport content='width=device-width'>"
                            "<style>body{background:#111;color:#eee;font:18px system-ui;text-align:center;padding:12vh 20px}"
                            "a{display:inline-block;background:#ddff45;color:#111;padding:18px 28px;border-radius:12px;text-decoration:none;font-weight:800}</style>"
                            f"<h1>Kinetic Cut</h1><p>{file_path.name}</p><a href='/download'>Download video</a>")
                    data = page.encode()
                    self.send_response(200); self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
                elif self.path == "/download":
                    self.send_response(200); self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(file_path.name)}")
                    self.send_header("Content-Length", str(file_path.stat().st_size)); self.end_headers()
                    with file_path.open("rb") as source:
                        shutil.copyfileobj(source, self.wfile)
                else:
                    self.send_error(404)

            def log_message(self, *_):
                pass

        self.server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.connect(("8.8.8.8", 80)); host = sock.getsockname()[0]
            except OSError:
                host = socket.gethostbyname(socket.gethostname())
        return f"http://{host}:{self.server.server_port}/"

    def stop(self) -> None:
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.server = None
