"""Modern Social Media Video & Audio Downloader Dialog matching mock UI design."""
from __future__ import annotations

from .theme_widgets import set_ui_style, set_ui_icon
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QThread, Signal, Slot, QObject, QByteArray, QSize, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QImage
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QProgressBar, QFrame, QWidget,
    QScrollArea, QMessageBox, QGraphicsDropShadowEffect
)

from .icons import lucide_icon, resource_path
from .config import DATA_DIR

PYTHON_BIN = r"C:\Python310\python.exe" if Path(r"C:\Python310\python.exe").exists() else sys.executable


def default_download_dir() -> Path:
    # Never put user downloads inside the replaceable PyInstaller bundle.
    if os.environ.get('KINETIC_CUT_HOME'):
        return DATA_DIR / 'downloads'
    return Path.home() / 'Downloads' / 'Kinetic Cut'


def video_download_format(target_res: str = "") -> tuple[str, str]:
    """Prefer edit-friendly AVC at equal size/FPS, retaining quality fallbacks.

    MP4 is a container, not a video codec: YouTube can put AV1 inside it.
    Sorting after resolution and frame rate avoids silently downgrading either
    just to avoid AV1. The existing selector still handles sites without AVC.
    """
    format_spec = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    if target_res and "x" in target_res:
        try:
            height = int(target_res.split("x")[-1].strip().split()[0])
            format_spec = f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best"
        except (TypeError, ValueError):
            pass
    return format_spec, "res,fps,hdr,vcodec:avc"


def format_duration(seconds: float | int | None) -> str:
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_views(count: int | None) -> str:
    if not count:
        return ""
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B views"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M views"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K views"
    return f"{count:,} views"


def format_subscribers(count: int | None) -> str:
    if not count:
        return ""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M subscribers"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K subscribers"
    return f"{count} subscribers"


def format_upload_date(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        # YYYYMMDD
        dt = datetime.strptime(date_str, "%Y%m%d")
        days = (datetime.now() - dt).days
        if days <= 0:
            return "today"
        if days == 1:
            return "yesterday"
        if days < 7:
            return f"{days} days ago"
        if days < 30:
            return f"{days // 7} weeks ago"
        if days < 365:
            return f"{days // 30} months ago"
        return f"{days // 365} years ago"
    except Exception:
        return ""


def find_cookie_file() -> Path | None:
    """Find an available cookies.txt file for YouTube authentication."""
    env_c = os.environ.get("YTDLP_COOKIES")
    if env_c and Path(env_c).is_file():
        return Path(env_c).resolve()

    candidates = [
        Path("cookies.txt"),
        Path("youtube_cookies.txt"),
        Path("assets/cookies.txt"),
        DATA_DIR / "cookies.txt",
        Path(os.environ.get("LOCALAPPDATA", "")) / "KineticCut" / "cookies.txt",
        Path.home() / "Downloads" / "cookies.txt",
        Path.home() / "cookies.txt",
    ]
    for p in candidates:
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p.resolve()
        except Exception:
            pass
    return None


def get_ytdlp_runtime_args(cookies_path: str = "") -> list[str]:
    """Return optimal yt-dlp arguments including JavaScript runtime solver and cookie authentication."""
    args = []

    # 1. Node.js runtime for JavaScript challenge solving
    node_bin = shutil.which("node")
    if not node_bin:
        default_node = Path(r"C:\Program Files\nodejs\node.exe")
        if default_node.exists():
            node_bin = str(default_node)
    if node_bin:
        args.extend(["--js-runtimes", f"node:{node_bin}", "--remote-components", "ejs:github"])

    # 2. Cookies authentication
    cookie_file = cookies_path or find_cookie_file()
    if cookie_file and Path(cookie_file).is_file():
        args.extend(["--cookies", str(cookie_file)])
    else:
        # Check if browser profile with cookies exists (Firefox on Windows)
        ff_dir = Path.home() / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
        if ff_dir.exists() and any(ff_dir.iterdir()):
            args.extend(["--cookies-from-browser", "firefox"])

    return args


def fetch_youtube_oembed(url: str) -> dict | None:
    """Fetch video title, author and thumbnail from YouTube official oEmbed endpoint without auth."""
    try:
        import urllib.parse
        import urllib.request
        oembed_url = "https://www.youtube.com/oembed?url=" + urllib.parse.quote(url, safe=":/?=") + "&format=json"
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "title": data.get("title") or "YouTube Video",
                "uploader": data.get("author_name") or "YouTube Creator",
                "duration": None,
                "thumbnail": data.get("thumbnail_url") or "",
                "extractor_key": "Youtube",
                "platform": "youtube",
                "is_sound_only": False,
                "formats": [
                    {"format_id": "best", "ext": "mp4", "height": 1080, "vcodec": "avc1", "acodec": "mp4a"}
                ]
            }
    except Exception:
        return None


def is_tiktok_sound_url(url: str) -> bool:
    u = url.lower().strip()
    return ("tiktok.com" in u or "douyin.com" in u) and "/music/" in u


def resolve_tiktok_sound(url: str) -> dict:
    title = ""
    author = ""

    # 1. Fetch title and author from TikTok oEmbed if available
    try:
        import urllib.parse
        import urllib.request
        oembed_url = f"https://www.tiktok.com/oembed?url={urllib.parse.quote(url, safe=':/?=')}"
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_title = data.get("title", "")
            if raw_title.startswith("♬ "):
                raw_title = raw_title[2:].strip()
            title = raw_title
            author = data.get("author_name") or ""
    except Exception:
        pass

    if not title:
        m = re.search(r"/music/([^/?#]+)", url)
        if m:
            slug = m.group(1).split("-")[0]
            title = slug.replace("_", " ").title()

    # 2. Extract direct MP3 stream URL via ssstik.io
    audio_url = ""
    try:
        import base64
        import urllib.parse
        import urllib.request
        page_url = "https://ssstik.io/download-tiktok-mp3"
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        req_page = urllib.request.Request(page_url, headers={"User-Agent": ua})
        cookie_header = ""
        with urllib.request.urlopen(req_page, timeout=10) as resp:
            html_page = resp.read().decode("utf-8")
            cookie_headers = resp.headers.get_all("Set-Cookie")
            if cookie_headers:
                cookie_header = "; ".join([c.split(";")[0] for c in cookie_headers])

        m_tt = re.search(r"s_tt\s*=\s*'([^']+)'", html_page)
        s_tt = m_tt.group(1) if m_tt else ""

        post_url = "https://ssstik.io/abc?url=dl"
        post_headers = {
            "User-Agent": ua,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "HX-Request": "true",
            "HX-Trigger": "_gcaptcha_pt",
            "HX-Target": "target",
            "HX-Current-URL": page_url,
            "Referer": page_url,
            "Origin": "https://ssstik.io",
        }
        if cookie_header:
            post_headers["Cookie"] = cookie_header

        payload = urllib.parse.urlencode({
            "id": url,
            "locale": "en",
            "tt": s_tt,
        }).encode("utf-8")

        req_post = urllib.request.Request(post_url, data=payload, headers=post_headers)
        with urllib.request.urlopen(req_post, timeout=12) as resp:
            res_html = resp.read().decode("utf-8")

        direct_urls = re.findall(r'href="([^"]+)"[^>]*class="[^"]*download_link[^"]*"', res_html)
        for u in direct_urls:
            if "tiktokcdn" in u and u.endswith(".mp3"):
                audio_url = u
                break
            elif "tikcdn.io/ssstik/m/" in u:
                b64 = u.split("tikcdn.io/ssstik/m/")[-1]
                try:
                    decoded = base64.b64decode(b64).decode("utf-8", errors="ignore")
                    if decoded.startswith("http"):
                        audio_url = decoded
                        break
                except Exception:
                    pass
        if not audio_url and direct_urls:
            audio_url = direct_urls[0]
    except Exception:
        pass

    if not audio_url:
        raise ValueError("Could not resolve MP3 audio stream for this TikTok sound link.")

    return {
        "title": title or "TikTok Sound",
        "uploader": author or "",
        "duration": None,
        "thumbnail": "",
        "extractor_key": "TikTokSound",
        "platform": "tiktok",
        "is_sound_only": True,
        "audio_url": audio_url,
        "formats": [
            {"format_id": "mp3", "ext": "mp3", "vcodec": "none", "acodec": "mp3"}
        ]
    }


def detect_platform(url: str) -> str:
    u = url.lower().strip()
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u:
        return "instagram"
    if "twitter.com" in u or "x.com" in u:
        return "twitter"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return "generic"


class _FetchMetadataWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, url: str, cookies_path: str = ""):
        super().__init__()
        self.url = url
        self.cookies_path = cookies_path

    def run(self):
        try:
            if is_tiktok_sound_url(self.url):
                data = resolve_tiktok_sound(self.url)
                self.finished.emit(data)
                return

            cmd = [
                PYTHON_BIN, "-m", "yt_dlp",
                "--dump-single-json",
                "--no-warnings",
                "--no-playlist",
            ]
            cmd.extend(get_ytdlp_runtime_args(self.cookies_path))
            cmd.append(self.url)

            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            if res.returncode != 0 or not res.stdout.strip():
                err_msg = res.stderr.strip() or "Failed to fetch metadata for URL"
                # Fallback to official YouTube oEmbed if YouTube bot challenge encountered
                if "youtube.com" in self.url.lower() or "youtu.be" in self.url.lower():
                    oembed_data = fetch_youtube_oembed(self.url)
                    if oembed_data:
                        if "not a bot" in err_msg.lower() or "sign in" in err_msg.lower():
                            oembed_data["needs_cookies"] = True
                            oembed_data["bot_warning"] = "YouTube bot check detected. Use Cookies button to select cookies.txt."
                        self.finished.emit(oembed_data)
                        return

                self.error.emit(err_msg)
                return
            data = json.loads(res.stdout)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class _ThumbnailWorker(QThread):
    loaded = Signal(QPixmap)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            import urllib.request
            req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            img = QImage.fromData(data)
            if not img.isNull():
                self.loaded.emit(QPixmap.fromImage(img))
        except Exception:
            pass


class _DownloadWorker(QThread):
    progress = Signal(float, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, url: str, mode: str, output_dir: Path, target_res: str = "", direct_audio_url: str = "", sound_title: str = "", cookies_path: str = ""):
        super().__init__()
        self.url = url
        self.mode = mode  # 'video' or 'audio'
        self.output_dir = output_dir
        self.target_res = target_res
        self.direct_audio_url = direct_audio_url
        self.sound_title = sound_title
        self.cookies_path = cookies_path
        self._proc = None
        self._cancelled = False

    def run(self):
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Direct audio stream download (e.g. TikTok Sound)
            if self.direct_audio_url:
                import urllib.request
                self.progress.emit(10.0, "Downloading TikTok MP3 sound...")
                clean_name = re.sub(r'[\\/*?:"<>|]', "", self.sound_title or "TikTok_Sound").strip() or "TikTok_Sound"
                target_file = self.output_dir / f"{clean_name}.mp3"
                req = urllib.request.Request(self.direct_audio_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                with urllib.request.urlopen(req, timeout=25) as resp:
                    total_len = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    with open(target_file, "wb") as f:
                        while True:
                            if self._cancelled:
                                return
                            chunk = resp.read(32768)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_len > 0:
                                pct = min(98.0, (downloaded / total_len) * 88.0 + 10.0)
                                self.progress.emit(pct, f"Downloading MP3... {pct:.1f}%")
                self.progress.emit(100.0, "Completed!")
                self.finished.emit(str(target_file.resolve()))
                return

            out_template = str(self.output_dir / "%(title).80s [%(id)s].%(ext)s")
            
            cmd = [PYTHON_BIN, "-m", "yt_dlp", "--newline", "--no-playlist"]
            cmd.extend(get_ytdlp_runtime_args(self.cookies_path))
            
            if self.mode == "audio":
                cmd.extend([
                    "-x", "--audio-format", "mp3",
                    "--audio-quality", "0",
                    "-o", out_template,
                    self.url
                ])
            else:
                # Video mode
                format_spec, format_sort = video_download_format(self.target_res)
                cmd.extend([
                    "-f", format_spec,
                    "-S", format_sort,
                    "--merge-output-format", "mp4",
                    "-o", out_template,
                    self.url
                ])
                
            self.progress.emit(5.0, "Starting download...")
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            
            final_file = None
            raw_output = []
            for line in iter(self._proc.stdout.readline, ""):
                if self._cancelled:
                    self._proc.terminate()
                    return
                line = line.strip()
                if not line:
                    continue
                raw_output.append(line)
                # Parse yt-dlp progress
                # [download]  45.2% of 12.34MiB at 3.45MiB/s ETA 00:03
                m = re.search(r"\[download\]\s+([\d\.]+)%", line)
                if m:
                    pct = float(m.group(1))
                    self.progress.emit(min(98.0, max(5.0, pct)), f"Downloading... {pct:.1f}%")
                elif "[Merger]" in line or "[ExtractAudio]" in line:
                    self.progress.emit(95.0, "Processing and converting media...")
                elif "[download] Destination:" in line:
                    dest_str = line.split("[download] Destination:")[-1].strip()
                    final_file = Path(dest_str)
                elif "has already been downloaded" in line:
                    dest_str = line.split("[download]")[-1].split("has already been downloaded")[0].strip()
                    final_file = Path(dest_str)

            self._proc.wait()
            if self._proc.returncode != 0:
                combined_err = " ".join(raw_output[-6:])
                if "not a bot" in combined_err.lower() or "sign in" in combined_err.lower():
                    self.error.emit("YouTube requires authentication ('Sign in to confirm you're not a bot'). Click 'Cookies' to select your cookies.txt file.")
                else:
                    self.error.emit(f"Download failed with exit code {self._proc.returncode}: {combined_err[:120]}")
                return

            # If final_file was not captured directly, find the newest file in output_dir
            if not final_file or not final_file.exists():
                files = list(self.output_dir.glob("*.mp3" if self.mode == "audio" else "*.mp4"))
                if files:
                    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                    final_file = files[0]

            if final_file and final_file.exists():
                self.progress.emit(100.0, "Completed!")
                self.finished.emit(str(final_file.resolve()))
            else:
                self.error.emit("Downloaded file could not be located.")
        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self._cancelled = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass


def download_media_synchronous(url: str, mode: str = "video", target_res: str = "", cookies_path: str | None = None, output_dir: Path | None = None) -> dict:
    """Download video or audio synchronously, return dictionary with file details."""
    dest_dir = output_dir if output_dir is not None else default_download_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Direct TikTok Sound resolution
    if is_tiktok_sound_url(url):
        data = resolve_tiktok_sound(url)
        audio_url = data.get("audio_url")
        sound_title = data.get("title", "TikTok_Sound")
        clean_name = re.sub(r'[\\/*?:"<>|]', "", sound_title).strip() or "TikTok_Sound"
        target_file = dest_dir / f"{clean_name}.mp3"
        import urllib.request
        req = urllib.request.Request(audio_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(target_file, "wb") as f:
            while True:
                chunk = resp.read(32768)
                if not chunk:
                    break
                f.write(chunk)
        return {
            "path": str(target_file.resolve()),
            "name": target_file.name,
            "title": sound_title,
            "mode": "audio",
            "size_bytes": target_file.stat().st_size,
        }

    # 2. General yt-dlp download (YouTube, Shorts, TikTok video, Instagram, Twitter)
    out_template = str(dest_dir / "%(title).80s [%(id)s].%(ext)s")
    cmd = [PYTHON_BIN, "-m", "yt_dlp", "--no-playlist"]
    cmd.extend(get_ytdlp_runtime_args(cookies_path or ""))

    if mode == "audio":
        cmd.extend([
            "-x", "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", out_template,
            url
        ])
    else:
        format_spec, format_sort = video_download_format(target_res)
        cmd.extend([
            "-f", format_spec,
            "-S", format_sort,
            "--merge-output-format", "mp4",
            "-o", out_template,
            url
        ])

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        err_out = proc.stderr.strip() or proc.stdout.strip()
        if "not a bot" in err_out.lower() or "sign in" in err_out.lower():
            raise ValueError(
                "YouTube bot verification required ('Sign in to confirm you're not a bot'). "
                "Please provide an exported cookies.txt file to download this video."
            )
        raise RuntimeError(f"Download failed: {err_out[-300:]}")

    # Find the downloaded file
    final_file = None
    for line in proc.stdout.splitlines():
        if "[download] Destination:" in line:
            final_file = Path(line.split("[download] Destination:")[-1].strip())
        elif "has already been downloaded" in line:
            final_file = Path(line.split("[download]")[-1].split("has already been downloaded")[0].strip())

    if not final_file or not final_file.exists():
        ext = "*.mp3" if mode == "audio" else "*.mp4"
        files = list(dest_dir.glob(ext))
        if files:
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            final_file = files[0]

    if not final_file or not final_file.exists():
        raise FileNotFoundError("Downloaded media file could not be located.")

    return {
        "path": str(final_file.resolve()),
        "name": final_file.name,
        "title": final_file.stem,
        "mode": mode,
        "size_bytes": final_file.stat().st_size,
    }


class MediaDownloaderDialog(QDialog):
    """Sleek, dark-themed social video & audio downloader dialog."""
    
    mediaDownloaded = Signal(str)

    def __init__(self, parent=None, initial_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Video Downloader · Kinetic Cut")
        self.setMinimumSize(740, 620)
        self.resize(760, 660)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._fetch_worker: _FetchWorker | None = None
        self._thumb_worker: _ThumbnailWorker | None = None
        self._download_worker: _DownloadWorker | None = None
        self.metadata: dict | None = None
        self.active_platform = "youtube"

        self._setup_ui()
        self._apply_theme()
        
        if initial_url:
            self.url_input.setText(initial_url)
            self._on_url_changed(initial_url)
            self._on_fetch_clicked()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        # 1. Header (Icon + Title + Subtitle)
        head_layout = QHBoxLayout()
        head_layout.setSpacing(14)
        
        icon_badge = QLabel()
        icon_badge.setFixedSize(42, 42)
        icon_badge.setAlignment(Qt.AlignCenter)
        icon_badge.setObjectName("headerIconBadge")
        set_ui_icon(icon_badge, 'download', '#ff5744', 26)
        head_layout.addWidget(icon_badge)

        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        title_lbl = QLabel("Video Downloader")
        title_lbl.setObjectName("headerTitle")
        sub_lbl = QLabel("Download videos or audio from social media platforms and use them in your projects.")
        sub_lbl.setObjectName("headerSubtitle")
        head_text.addWidget(title_lbl)
        head_text.addWidget(sub_lbl)
        head_layout.addLayout(head_text)
        head_layout.addStretch()
        root.addLayout(head_layout)

        # 2. Platform Selection Cards / Pills
        platforms_layout = QHBoxLayout()
        platforms_layout.setSpacing(10)

        self.platform_buttons = {}
        platform_configs = [
            ("youtube", "YouTube / Shorts", "youtube", "#ff0000"),
            ("tiktok", "TikTok", "tiktok", "#00f2fe"),
            ("instagram", "Instagram", "instagram", "#e1306c"),
            ("twitter", "Twitter / X", "twitter", "#ffffff"),
        ]
        for key, label, icon_name, icon_color in platform_configs:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("platformPill")
            btn.setIcon(lucide_icon(icon_name, icon_color, 18))
            btn.setIconSize(QSize(18, 18))
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, k=key: self._set_platform(k))
            platforms_layout.addWidget(btn)
            self.platform_buttons[key] = btn

        self.platform_buttons["youtube"].setChecked(True)
        root.addLayout(platforms_layout)

        # 3. URL Input Bar with Link icon & Fetch Button
        input_container = QFrame()
        input_container.setObjectName("inputContainer")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(12, 6, 8, 6)
        input_layout.setSpacing(10)

        link_icon = QLabel()
        set_ui_icon(link_icon, 'link', '#7d8597', 18)
        input_layout.addWidget(link_icon)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("urlInput")
        self.url_input.setPlaceholderText("https://www.youtube.com/... (videos or shorts), tiktok, instagram, x.com link")
        self.url_input.textChanged.connect(self._on_url_changed)
        self.url_input.returnPressed.connect(self._on_fetch_clicked)
        input_layout.addWidget(self.url_input, 1)

        # Clear button
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setObjectName("clearButton")
        self.clear_btn.setFixedSize(22, 22)
        self.clear_btn.setToolTip("Clear URL")
        self.clear_btn.clicked.connect(lambda: self.url_input.clear())
        input_layout.addWidget(self.clear_btn)

        # Cookies button
        self.cookies_btn = QPushButton("  Cookies")
        self.cookies_btn.setObjectName("cookiesButton")
        self.cookies_btn.setIcon(lucide_icon("key", "#a0aec0", 14))
        self.cookies_btn.setIconSize(QSize(14, 14))
        self.cookies_btn.setFixedHeight(36)
        self.cookies_btn.setToolTip("Select or configure cookies.txt file for YouTube authentication")
        self.cookies_btn.clicked.connect(self._select_cookie_file)
        if find_cookie_file():
            self.cookies_btn.setText("  Cookies (Active)")
            set_ui_style(self.cookies_btn, 'color: @success; border-color: @accent;')
        input_layout.addWidget(self.cookies_btn)

        self.fetch_btn = QPushButton("  Fetch")
        self.fetch_btn.setObjectName("fetchButton")
        self.fetch_btn.setIcon(lucide_icon("search", "#ffffff", 16))
        self.fetch_btn.setIconSize(QSize(16, 16))
        self.fetch_btn.setFixedHeight(36)
        self.fetch_btn.clicked.connect(self._on_fetch_clicked)
        input_layout.addWidget(self.fetch_btn)

        root.addWidget(input_container)

        # 4. Fetched Video Preview Card Container
        self.card = QFrame()
        self.card.setObjectName("previewCard")
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(18)

        # Left Column: Video Thumbnail with Duration badge
        thumb_container = QWidget()
        thumb_container.setFixedSize(180, 240)
        thumb_box = QVBoxLayout(thumb_container)
        thumb_box.setContentsMargins(0, 0, 0, 0)
        thumb_box.setSpacing(0)

        self.thumb_label = QLabel()
        self.thumb_label.setObjectName("thumbImage")
        self.thumb_label.setFixedSize(180, 240)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setText("No Preview")
        thumb_box.addWidget(self.thumb_label)

        # Overlaid duration badge
        self.dur_badge = QLabel("00:00", thumb_container)
        self.dur_badge.setObjectName("durationBadge")
        self.dur_badge.move(118, 208)
        self.dur_badge.setFixedSize(54, 22)
        self.dur_badge.setAlignment(Qt.AlignCenter)
        self.dur_badge.hide()

        card_layout.addWidget(thumb_container)

        # Right Column: Metadata & Format selection
        meta_layout = QVBoxLayout()
        meta_layout.setContentsMargins(0, 4, 0, 4)
        meta_layout.setSpacing(8)

        self.title_lbl = QLabel("Paste a social media link and click Fetch to preview media.")
        self.title_lbl.setObjectName("videoTitle")
        self.title_lbl.setWordWrap(True)
        meta_layout.addWidget(self.title_lbl)

        # Platform badge indicator
        self.platform_ind = QLabel("YouTube Shorts")
        self.platform_ind.setObjectName("platformIndicator")
        meta_layout.addWidget(self.platform_ind)

        # Author / Channel Row
        author_row = QHBoxLayout()
        author_row.setSpacing(8)
        self.author_avatar = QLabel()
        self.author_avatar.setFixedSize(24, 24)
        self.author_avatar.setPixmap(lucide_icon("circle", "#4a90e2", 20).pixmap(20, 20))
        self.author_lbl = QLabel("Author")
        self.author_lbl.setObjectName("authorName")
        self.subs_lbl = QLabel("• 0 subscribers")
        self.subs_lbl.setObjectName("authorSubs")
        author_row.addWidget(self.author_avatar)
        author_row.addWidget(self.author_lbl)
        author_row.addWidget(self.subs_lbl)
        author_row.addStretch()
        meta_layout.addLayout(author_row)

        # Views and Time stats
        self.stats_lbl = QLabel("0 views • recently")
        self.stats_lbl.setObjectName("statsText")
        meta_layout.addWidget(self.stats_lbl)

        meta_layout.addStretch()

        # Format / Resolution selectors in 2 columns
        selectors_layout = QHBoxLayout()
        selectors_layout.setSpacing(14)

        res_col = QVBoxLayout()
        res_col.setSpacing(4)
        res_title = QLabel("Resolution")
        res_title.setObjectName("formLabel")
        self.res_combo = QComboBox()
        self.res_combo.setObjectName("styledCombo")
        self.res_combo.addItems(["1080 × 1920 (Original)", "720 × 1280", "480 × 854", "Best Available"])
        res_col.addWidget(res_title)
        res_col.addWidget(self.res_combo)
        selectors_layout.addLayout(res_col, 1)

        fmt_col = QVBoxLayout()
        fmt_col.setSpacing(4)
        fmt_title = QLabel("Format")
        fmt_title.setObjectName("formLabel")
        self.fmt_combo = QComboBox()
        self.fmt_combo.setObjectName("styledCombo")
        self.fmt_combo.addItems(["MP4 (Video)", "MP3 (Audio)"])
        fmt_col.addWidget(fmt_title)
        fmt_col.addWidget(self.fmt_combo)
        selectors_layout.addLayout(fmt_col, 1)

        meta_layout.addLayout(selectors_layout)
        card_layout.addLayout(meta_layout, 1)

        root.addWidget(self.card, 1)

        # 5. Progress Bar & Status Line
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("downloadProgress")
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Ready")
        self.status_lbl.setObjectName("statusLabel")
        root.addWidget(self.status_lbl)

        # 6. Action Buttons (Dual Large Buttons: Download Video & Download MP3)
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(14)

        # Primary Coral-Red Download Video Button
        self.btn_download_video = QPushButton()
        self.btn_download_video.setObjectName("btnDownloadVideo")
        self.btn_download_video.setFixedHeight(58)
        self.btn_download_video.setEnabled(False)
        self.btn_download_video.clicked.connect(lambda: self._start_download("video"))
        
        btn_v_layout = QHBoxLayout(self.btn_download_video)
        btn_v_layout.setContentsMargins(16, 0, 16, 0)
        btn_v_layout.setSpacing(12)
        v_icon = QLabel()
        set_ui_icon(v_icon, 'download', None, 24)
        btn_v_layout.addWidget(v_icon)
        v_text_box = QVBoxLayout()
        v_text_box.setContentsMargins(0, 8, 0, 8)
        v_text_box.setSpacing(1)
        self.v_main_lbl = QLabel("Download Video")
        self.v_main_lbl.setObjectName("btnMainText")
        self.v_sub_lbl = QLabel("MP4 • 1080 × 1920")
        self.v_sub_lbl.setObjectName("btnSubTextLight")
        v_text_box.addWidget(self.v_main_lbl)
        v_text_box.addWidget(self.v_sub_lbl)
        btn_v_layout.addLayout(v_text_box)
        btn_v_layout.addStretch()

        actions_layout.addWidget(self.btn_download_video, 1)

        # Secondary Dark Download MP3 Button
        self.btn_download_audio = QPushButton()
        self.btn_download_audio.setObjectName("btnDownloadAudio")
        self.btn_download_audio.setFixedHeight(58)
        self.btn_download_audio.setEnabled(False)
        self.btn_download_audio.clicked.connect(lambda: self._start_download("audio"))

        btn_a_layout = QHBoxLayout(self.btn_download_audio)
        btn_a_layout.setContentsMargins(16, 0, 16, 0)
        btn_a_layout.setSpacing(12)
        a_icon = QLabel()
        set_ui_icon(a_icon, 'music-2', None, 22)
        btn_a_layout.addWidget(a_icon)
        a_text_box = QVBoxLayout()
        a_text_box.setContentsMargins(0, 8, 0, 8)
        a_text_box.setSpacing(1)
        self.a_main_lbl = QLabel("Download MP3")
        self.a_main_lbl.setObjectName("btnMainText")
        self.a_sub_lbl = QLabel("Audio Only • High Quality")
        self.a_sub_lbl.setObjectName("btnSubTextMuted")
        a_text_box.addWidget(self.a_main_lbl)
        a_text_box.addWidget(self.a_sub_lbl)
        btn_a_layout.addLayout(a_text_box)
        btn_a_layout.addStretch()

        actions_layout.addWidget(self.btn_download_audio, 1)

        root.addLayout(actions_layout)

    def _apply_theme(self):
        set_ui_style(self, '\n            QDialog {\n                background-color: @bg_panel;\n                color: @text_main;\n                font-family: \'Segoe UI\', Inter, sans-serif;\n            }\n            #headerTitle {\n                font-size: 20px;\n                font-weight: 700;\n                color: @text_main;\n            }\n            #headerSubtitle {\n                font-size: 12px;\n                color: @text_sub;\n            }\n            #platformPill {\n                background-color: @bg_panel;\n                border: 1px solid @border_subtle;\n                border-radius: 8px;\n                color: @text_main;\n                font-size: 13px;\n                font-weight: 600;\n                padding: 10px 14px;\n                text-align: center;\n            }\n            #platformPill:hover {\n                background-color: @bg_hover;\n                border-color: @border_subtle;\n            }\n            #platformPill:checked {\n                background-color: @bg_selected;\n                border: 2px solid @accent;\n                color: @text_selected;\n            }\n            #inputContainer {\n                background-color: @bg_panel;\n                border: 1px solid @border_subtle;\n                border-radius: 8px;\n            }\n            #urlInput {\n                background: transparent;\n                border: none;\n                color: @text_main;\n                font-size: 13px;\n                padding: 4px;\n            }\n            #urlInput:focus {\n                outline: none;\n            }\n            #clearButton {\n                background: transparent;\n                border: none;\n                color: @text_sub;\n                font-size: 12px;\n                font-weight: bold;\n                border-radius: 11px;\n            }\n            #clearButton:hover {\n                background-color: @bg_hover;\n                color: @text_main;\n            }\n            #cookiesButton {\n                background-color: @bg_panel;\n                border: 1px solid @border_subtle;\n                border-radius: 6px;\n                color: @text_sub;\n                font-size: 12px;\n                font-weight: 600;\n                padding: 0 12px;\n            }\n            #cookiesButton:hover {\n                background-color: @bg_hover;\n                color: @text_main;\n                border-color: @border_subtle;\n            }\n            #fetchButton {\n                background-color: @accent;\n                border: none;\n                border-radius: 6px;\n                color: @accent_text;\n                font-size: 13px;\n                font-weight: 700;\n                padding: 0 18px;\n            }\n            #fetchButton:hover {\n                background-color: @accent;\n            }\n            #fetchButton:pressed {\n                background-color: @accent;\n            }\n            #fetchButton:disabled {\n                background-color: @danger_bg;\n                color: @text_disabled;\n            }\n            #previewCard {\n                background-color: @bg_panel;\n                border: 1px solid @border_subtle;\n                border-radius: 12px;\n            }\n            #thumbImage {\n                background-color: @bg_panel;\n                border: 1px solid @border_subtle;\n                border-radius: 8px;\n                color: @text_sub;\n                font-size: 12px;\n            }\n            #durationBadge {\n                background-color: rgba(0, 0, 0, 0.78);\n                border-radius: 4px;\n                color: @text_main;\n                font-size: 11px;\n                font-weight: 700;\n            }\n            #videoTitle {\n                font-size: 15px;\n                font-weight: 700;\n                color: @text_main;\n                line-height: 1.3;\n            }\n            #platformIndicator {\n                color: @text_sub;\n                font-size: 12px;\n                font-weight: 600;\n            }\n            #authorName {\n                color: @text_main;\n                font-size: 12px;\n                font-weight: 600;\n            }\n            #authorSubs {\n                color: @text_sub;\n                font-size: 12px;\n            }\n            #statsText {\n                color: @text_sub;\n                font-size: 12px;\n            }\n            #formLabel {\n                color: @text_sub;\n                font-size: 11px;\n                font-weight: 600;\n                text-transform: uppercase;\n                letter-spacing: 0.5px;\n            }\n            #styledCombo {\n                background-color: @bg_panel;\n                border: 1px solid @border_subtle;\n                border-radius: 6px;\n                color: @text_main;\n                font-size: 12px;\n                padding: 6px 10px;\n                min-height: 24px;\n            }\n            #styledCombo:hover {\n                border-color: @border_subtle;\n            }\n            #downloadProgress {\n                background-color: @bg_panel;\n                border: none;\n                border-radius: 4px;\n            }\n            #downloadProgress::chunk {\n                background-color: @accent;\n                border-radius: 4px;\n            }\n            #statusLabel {\n                color: @info;\n                font-size: 12px;\n                font-weight: 600;\n            }\n            #btnDownloadVideo {\n                background-color: @accent;\n                border: none;\n                border-radius: 8px;\n            }\n            #btnDownloadVideo:hover {\n                background-color: @accent;\n            }\n            #btnDownloadVideo:pressed {\n                background-color: @accent;\n            }\n            #btnDownloadVideo:disabled {\n                background-color: @danger_bg;\n            }\n            #btnDownloadAudio {\n                background-color: @bg_panel;\n                border: 1px solid @border_subtle;\n                border-radius: 8px;\n            }\n            #btnDownloadAudio:hover {\n                background-color: @bg_hover;\n                border-color: @border_subtle;\n            }\n            #btnDownloadAudio:pressed {\n                background-color: @bg_panel;\n            }\n            #btnDownloadAudio:disabled {\n                background-color: @bg_panel;\n                border-color: @border_subtle;\n            }\n            #btnDownloadAudio[primarySound="true"] {\n                background-color: @accent;\n                border: none;\n            }\n            #btnDownloadAudio[primarySound="true"]:hover {\n                background-color: @accent;\n            }\n            #btnDownloadAudio[primarySound="true"]:pressed {\n                background-color: @accent;\n            }\n            #btnMainText {\n                color: @text_main;\n                font-size: 14px;\n                font-weight: 700;\n            }\n            #btnSubTextLight {\n                color: @text_main;\n                font-size: 11px;\n            }\n            #btnSubTextMuted {\n                color: @text_sub;\n                font-size: 11px;\n            }\n        ')

    def _set_platform(self, key: str):
        self.active_platform = key
        for k, btn in self.platform_buttons.items():
            btn.setChecked(k == key)

    def _on_url_changed(self, text: str):
        detected = detect_platform(text)
        if detected in self.platform_buttons:
            self._set_platform(detected)
        u = text.strip().lower()
        if u.startswith("http://") or u.startswith("https://"):
            self.btn_download_video.setEnabled(True)
            self.btn_download_audio.setEnabled(True)

    def _on_fetch_clicked(self):
        url = self.url_input.text().strip()
        if not url:
            self.status_lbl.setText("Please enter a valid video link.")
            return

        self.fetch_btn.setEnabled(False)
        self.status_lbl.setText("Fetching video information...")
        self.progress_bar.show()
        self.progress_bar.setValue(25)

        self._fetch_worker = _FetchMetadataWorker(url)
        self._fetch_worker.finished.connect(self._on_metadata_loaded)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    @Slot(dict)
    def _on_metadata_loaded(self, data: dict):
        self.fetch_btn.setEnabled(True)
        self.progress_bar.hide()
        self.metadata = data
        self.status_lbl.setText("Ready to download.")

        # Update preview card
        title = data.get("title") or "Untitled Video"
        self.title_lbl.setText(title)

        uploader = data.get("uploader") or data.get("channel") or "Unknown Creator"
        self.author_lbl.setText(uploader)

        subs = format_subscribers(data.get("channel_follower_count"))
        self.subs_lbl.setText(f"• {subs}" if subs else "")

        views = format_views(data.get("view_count"))
        age = format_upload_date(data.get("upload_date"))
        stats_str = f"{views} • {age}" if (views and age) else (views or age or "Recent")
        self.stats_lbl.setText(stats_str)

        dur = data.get("duration")
        if dur is not None:
            try:
                dur = float(dur)
            except (ValueError, TypeError):
                dur = None

        # Platform name
        extractor = str(data.get("extractor_key") or "").lower()
        if "tiktok" in extractor:
            self.platform_ind.setText("TikTok Video")
            self._set_platform("tiktok")
        elif "instagram" in extractor:
            self.platform_ind.setText("Instagram Reel")
            self._set_platform("instagram")
        elif "twitter" in extractor or "x" in extractor:
            self.platform_ind.setText("Twitter / X")
            self._set_platform("twitter")
        else:
            is_short = "/shorts/" in self.url_input.text().lower() or (dur is not None and dur <= 60)
            self.platform_ind.setText("YouTube Shorts" if is_short else "YouTube Video")
            self._set_platform("youtube")

        # Duration badge
        if dur is not None and dur > 0:
            self.dur_badge.setText(format_duration(dur))
            self.dur_badge.show()
        else:
            self.dur_badge.hide()

        # Handle Audio/Sound Only (e.g. TikTok Sound)
        if data.get("is_sound_only"):
            self.platform_ind.setText("TikTok Sound (MP3)")
            self._set_platform("tiktok")
            if uploader and uploader != "TikTok Sound":
                self.author_lbl.setText(uploader)
                self.author_lbl.show()
            else:
                self.author_lbl.setText("TikTok Sound")
            self.subs_lbl.setText("")
            self.stats_lbl.setText("Audio Only Sound • Direct MP3")
            self.dur_badge.setText("MP3")
            self.dur_badge.show()

            self.res_combo.clear()
            self.res_combo.addItem("N/A (Audio Only)")
            self.fmt_combo.clear()
            self.fmt_combo.addItem("MP3 (Audio Only)")

            self.btn_download_video.setEnabled(False)
            self.v_main_lbl.setText("No Video Available")
            self.v_sub_lbl.setText("Sound / MP3 Only")
            set_ui_style(self.v_sub_lbl, 'color: @text_sub;')

            self.btn_download_audio.setEnabled(True)
            self.btn_download_audio.setProperty("primarySound", True)
            self.btn_download_audio.style().unpolish(self.btn_download_audio)
            self.btn_download_audio.style().polish(self.btn_download_audio)
            self.a_main_lbl.setText("Download MP3")
            self.a_sub_lbl.setText("Audio Only • High Quality MP3")
            set_ui_style(self.a_sub_lbl, 'color: @text_main;')

            self.thumb_label.setPixmap(lucide_icon("music-2", "#ff5744", 48).pixmap(64, 64))
            return

        # Regular video setup
        self.btn_download_audio.setProperty("primarySound", False)
        self.btn_download_audio.style().unpolish(self.btn_download_audio)
        self.btn_download_audio.style().polish(self.btn_download_audio)
        self.v_main_lbl.setText("Download Video")
        set_ui_style(self.v_sub_lbl, 'color: @text_main;')
        set_ui_style(self.a_sub_lbl, 'color: @text_sub;')

        # Populate resolutions
        w = data.get("width")
        h = data.get("height")
        self.res_combo.clear()
        if w and h:
            self.res_combo.addItem(f"{w} × {h} (Original)")
            self.v_sub_lbl.setText(f"MP4 • {w} × {h}")
        else:
            is_short = "/shorts/" in self.url_input.text().lower()
            default_res = "1080 × 1920 (Original)" if is_short else "1920 × 1080 (Original)"
            self.res_combo.addItem(default_res)
            self.v_sub_lbl.setText(f"MP4 • {default_res.split()[0]} {default_res.split()[1]} {default_res.split()[2]}")

        for res_opt in ["1080p", "720p", "480p", "Best Available"]:
            if res_opt not in [self.res_combo.itemText(i) for i in range(self.res_combo.count())]:
                self.res_combo.addItem(res_opt)

        # Enable download buttons
        self.btn_download_video.setEnabled(True)
        self.btn_download_audio.setEnabled(True)

        if data.get("needs_cookies"):
            self.status_lbl.setText("⚠️ YouTube bot check detected. Use 'Cookies' button if download is blocked.")
            set_ui_style(self.status_lbl, 'color: @warning; font-size: 11px;')
        else:
            self.status_lbl.setText("✓ Media info fetched successfully.")
            set_ui_style(self.status_lbl, 'color: @success; font-size: 11px;')

        # Load Thumbnail
        thumb_url = data.get("thumbnail")
        if thumb_url:
            self.thumb_label.setText("Loading...")
            self._thumb_worker = _ThumbnailWorker(thumb_url)
            self._thumb_worker.loaded.connect(self._on_thumb_loaded)
            self._thumb_worker.start()
        else:
            self.thumb_label.setText("")
            self.thumb_label.setPixmap(lucide_icon("video", "#ff5744", 48).pixmap(56, 56))

    @Slot(QPixmap)
    def _on_thumb_loaded(self, pixmap: QPixmap):
        scaled = pixmap.scaled(180, 240, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        # Center crop to 180x240
        x = (scaled.width() - 180) // 2
        y = (scaled.height() - 240) // 2
        cropped = scaled.copy(max(0, x), max(0, y), 180, 240)
        self.thumb_label.setPixmap(cropped)

    @Slot(str)
    def _on_fetch_error(self, err_msg: str):
        self.fetch_btn.setEnabled(True)
        self.progress_bar.hide()
        url = self.url_input.text().strip()

        # Display fallback metadata so user can still click Download directly
        self.title_lbl.setText(url or "Media Ready to Download")
        self.author_lbl.setText("Direct download mode")
        self.subs_lbl.setText("")
        self.stats_lbl.setText("Ready to download")
        self.dur_badge.hide()

        self.res_combo.clear()
        if "/shorts/" in url.lower():
            self.res_combo.addItem("1080 × 1920 (Original)")
            self.v_sub_lbl.setText("MP4 • 1080 × 1920")
            self.platform_ind.setText("YouTube Shorts")
            self._set_platform("youtube")
        else:
            self.res_combo.addItem("1920 × 1080 (Original)")
            self.v_sub_lbl.setText("MP4 • 1920 × 1080")
            self.platform_ind.setText("Video / Audio")

        for res_opt in ["1080p", "720p", "480p", "Best Available"]:
            if res_opt not in [self.res_combo.itemText(i) for i in range(self.res_combo.count())]:
                self.res_combo.addItem(res_opt)

        self.btn_download_video.setEnabled(True)
        self.btn_download_audio.setEnabled(True)
        self.status_lbl.setText("Click 'Download Video' or 'Download MP3' to start download.")
        set_ui_style(self.status_lbl, 'color: @success; font-size: 11px;')
        self.thumb_label.setText("")
        self.thumb_label.setPixmap(lucide_icon("video", "#ff5744", 48).pixmap(56, 56))

    def _select_cookie_file(self) -> bool:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select cookies.txt for YouTube",
            str(Path.home() / "Downloads"),
            "Text Files (*.txt);;All Files (*)"
        )
        if path and Path(path).is_file():
            os.environ["YTDLP_COOKIES"] = str(Path(path).resolve())
            self.cookies_btn.setText("  Cookies (Active)")
            set_ui_style(self.cookies_btn, 'color: @success; border-color: @accent;')
            self.status_lbl.setText(f"✓ Using cookies: {Path(path).name}")
            return True
        return False

    def _start_download(self, mode: str):
        url = self.url_input.text().strip()
        if not url:
            return

        self._last_download_mode = mode
        self.btn_download_video.setEnabled(False)
        self.btn_download_audio.setEnabled(False)
        self.fetch_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(5)
        self.status_lbl.setText("Initializing download...")

        dest_dir = default_download_dir()
        target_res = self.res_combo.currentText()

        direct_audio_url = ""
        sound_title = ""
        if getattr(self, "metadata", None) and self.metadata.get("is_sound_only"):
            direct_audio_url = self.metadata.get("audio_url", "")
            sound_title = self.metadata.get("title", "")

        self._download_worker = _DownloadWorker(
            url, mode, dest_dir, target_res,
            direct_audio_url=direct_audio_url,
            sound_title=sound_title
        )
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    @Slot(float, str)
    def _on_download_progress(self, pct: float, msg: str):
        self.progress_bar.setValue(int(pct))
        self.status_lbl.setText(msg)

    @Slot(str)
    def _on_download_finished(self, file_path: str):
        self.progress_bar.setValue(100)
        self.status_lbl.setText(f"✓ Downloaded: {file_path}")
        if getattr(self, "metadata", None) and self.metadata.get("is_sound_only"):
            self.btn_download_video.setEnabled(False)
            self.btn_download_audio.setEnabled(True)
        else:
            self.btn_download_video.setEnabled(True)
            self.btn_download_audio.setEnabled(True)
        self.fetch_btn.setEnabled(True)

        self.mediaDownloaded.emit(file_path)

        if not getattr(self, "_headless", False):
            QMessageBox.information(
                self,
                "Download Complete",
                f"Downloaded to:\n\n{file_path}\n\nKinetic Cut is importing it into the Media Pool."
            )

    @Slot(str)
    def _on_download_error(self, err_msg: str):
        self.btn_download_video.setEnabled(True)
        self.btn_download_audio.setEnabled(True)
        self.fetch_btn.setEnabled(True)
        self.progress_bar.hide()
        if "not a bot" in err_msg.lower() or "sign in" in err_msg.lower():
            self.status_lbl.setText("⚠️ YouTube requires authentication. Click 'Cookies' to add cookies.txt.")
            if not getattr(self, "_headless", False):
                reply = QMessageBox.question(
                    self,
                    "YouTube Verification Required",
                    "YouTube blocked this download with a bot verification challenge ('Sign in to confirm you're not a bot').\n\n"
                    "Would you like to select your exported cookies.txt file to authenticate and download?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    if self._select_cookie_file():
                        self._start_download(getattr(self, "_last_download_mode", "video"))
        else:
            self.status_lbl.setText(f"Download error: {err_msg[:60]}")
            if not getattr(self, "_headless", False):
                QMessageBox.critical(self, "Download Error", f"Failed to download media:\n\n{err_msg}")

    def closeEvent(self, event):
        if self._download_worker and self._download_worker.isRunning():
            self._download_worker.cancel()
        super().closeEvent(event)
