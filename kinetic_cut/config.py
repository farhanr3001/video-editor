from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from platformdirs import user_cache_dir, user_config_dir, user_data_dir
except ImportError:
    def _base(name: str) -> str:
        return str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / name)
    user_cache_dir = user_config_dir = user_data_dir = _base


APP_NAME = "KineticCut"
_override = os.environ.get("KINETIC_CUT_HOME")
DATA_DIR = Path(_override) / "data" if _override else Path(user_data_dir(APP_NAME))
CACHE_DIR = Path(_override) / "cache" if _override else Path(user_cache_dir(APP_NAME))
CONFIG_DIR = Path(_override) / "config" if _override else Path(user_config_dir(APP_NAME))
AUTOSAVE_PATH = DATA_DIR / "recovery.kcut"
SESSION_LOCK_PATH = DATA_DIR / "active_session.lock"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
TEMPLATES_PATH = DATA_DIR / "templates.json"
for directory in (DATA_DIR, CACHE_DIR, CONFIG_DIR, CACHE_DIR / "thumbs", CACHE_DIR / "proxies", CACHE_DIR / "tts"):
    directory.mkdir(parents=True, exist_ok=True)


DEFAULT_SHORTCUTS = {
    "import": "Ctrl+I", "save": "Ctrl+S", "export": "Ctrl+E",
    "play_pause": "Space", "shuttle_back": "J", "shuttle_stop": "K",
    "shuttle_forward": "L", "mark_in": "I", "mark_out": "O",
    "cut": "Ctrl+B", "delete": "Backspace", "ripple_delete": "Delete",
    "undo": "Ctrl+Z", "redo": "Ctrl+Shift+Z", "selection_mode": "A",
    "blade_mode": "B", "crop_selected": "C", "snapping": "N",
    "vertical_layout": "V", "captions": "G", "remove_silence": "Shift+S",
    "instant_package": "Ctrl+Shift+I",
    "retime_controls": "Ctrl+R",
}


DEFAULT_SETTINGS = {
    "ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "whisper_cli": "",
    "whisper_model": "base.en", "whisper_model_path": "", "caption_language": "en",
    "sfx_folder": "", "phone_folder": "/sdcard/Movies/KineticCut",
    "effects_category": "All Effects",
    "shortcuts": DEFAULT_SHORTCUTS,
}


def load_settings() -> dict:
    current = dict(DEFAULT_SETTINGS)
    current["shortcuts"] = dict(DEFAULT_SHORTCUTS)
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            current.update({k: v for k, v in saved.items() if k != "shortcuts"})
            current["shortcuts"].update(saved.get("shortcuts", {}))
            legacy = {"<Control-i>":"Ctrl+I","<Control-s>":"Ctrl+S","<Control-e>":"Ctrl+E",
                      "<space>":"Space","<Delete>":"Delete","<Shift-Delete>":"Shift+Delete",
                      "<Shift-s>":"Shift+S","<Control-Shift-i>":"Ctrl+Shift+I"}
            current["shortcuts"] = {k: legacy.get(v, v.upper() if len(v)==1 else v)
                                    for k,v in current["shortcuts"].items()}
            old_edit_defaults=(current["shortcuts"].get("cut"),current["shortcuts"].get("delete"),current["shortcuts"].get("ripple_delete"))
            if old_edit_defaults==("C","Delete","Shift+Delete"):
                current["shortcuts"].update(cut="Ctrl+B",delete="Backspace",ripple_delete="Delete")
        except (OSError, json.JSONDecodeError):
            pass
    return current


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def load_templates() -> list[dict]:
    try:
        return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def save_templates(templates: list[dict]) -> None:
    TEMPLATES_PATH.write_text(json.dumps(templates, indent=2), encoding="utf-8")
