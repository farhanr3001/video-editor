"""Remove app-owned data, retaining Power Bin metadata and referenced sources."""
import json
import os
from pathlib import Path


def referenced_paths(value):
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'path' and isinstance(item, str) and item:
                result.add(Path(item).resolve())
            else:result.update(referenced_paths(item))
    elif isinstance(value, list):
        for item in value:result.update(referenced_paths(item))
    return result


def cleanup(roots, power_path):
    roots = sorted(set(Path(root).resolve() for root in roots), key=lambda p: len(p.parts))
    roots = [root for index, root in enumerate(roots) if not any(root.is_relative_to(p) for p in roots[:index])]
    power_path = Path(power_path).resolve()
    protected = {power_path, power_path.with_suffix('.tmp')}
    if power_path.is_file():
        # Stop rather than guess at references when personal metadata is unreadable.
        protected.update(referenced_paths(json.loads(power_path.read_text(encoding='utf-8'))))
    deleted = 0
    for root in roots:
        if not root.is_dir() or root.is_symlink():continue
        for directory, folders, files in os.walk(root, topdown=False, followlinks=False):
            for name in files:
                path = Path(directory) / name
                if path.resolve() in protected or not path.resolve().is_relative_to(root):continue
                # Directory junctions are not descended into by os.walk.
                path.unlink(); deleted += 1
            for name in folders:
                path = Path(directory) / name
                if path.is_symlink() or not path.resolve().is_relative_to(root):continue
                try:path.rmdir()
                except OSError:pass
        try:root.rmdir()
        except OSError:pass
    return {'deleted_files': deleted, 'power_bin_preserved': power_path.is_file()}


def run():
    from .config import DATA_DIR, CACHE_DIR, CONFIG_DIR
    try:
        cleanup((DATA_DIR, CACHE_DIR, CONFIG_DIR), DATA_DIR / 'powerbins.json')
        return 0
    except (OSError, ValueError):
        return 1
