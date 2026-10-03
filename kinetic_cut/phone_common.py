"""Small, dependency-free contracts shared by the UI and isolated USB helper."""
from __future__ import annotations

import posixpath
import re
import sys
from pathlib import Path


class PhoneError(RuntimeError):
    pass


class TransferCancelled(PhoneError):
    pass


def remote_path(path: str, root: str) -> str:
    if not isinstance(path, str) or any(ord(c) < 32 for c in path) or '\\' in path:
        raise PhoneError('Unsupported device path.')
    path = posixpath.normpath(path)
    root = posixpath.normpath(root)
    if not path.startswith('/') or (path != root and not path.startswith(root.rstrip('/') + '/')):
        raise PhoneError('The path is outside the selected storage location.')
    return path


def device_name(name: str) -> str:
    if not name or name in {'.', '..'} or '/' in name or '\\' in name or any(ord(c) < 32 for c in name):
        raise PhoneError('Unsupported file name.')
    return name


def local_name(name: str) -> str:
    device_name(name)
    if any(c in name for c in '<>:"|?*') or name.endswith((' ', '.')) or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', name, re.I):
        raise PhoneError('This phone filename cannot be saved on Windows. Rename it on the phone first.')
    return name


def helper_command() -> tuple[str, list[str]]:
    if getattr(sys, 'frozen', False):
        return sys.executable, ['--phone-worker']
    return sys.executable, [str(Path(__file__).resolve().parents[1] / 'main.py'), '--phone-worker']


def size_text(value: int) -> str:
    size = float(value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
