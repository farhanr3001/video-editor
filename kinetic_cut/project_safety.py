"""Recoverable project versions and self-contained copies of source media."""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .model import Project


def version_folder(project_path: str | Path) -> Path:
    path = Path(project_path)
    return path.parent / ".KineticCut Versions" / path.name


def versions(project_path: str | Path) -> list[Path]:
    folder = version_folder(project_path)
    return sorted(folder.glob("*.kcut"), reverse=True) if folder.is_dir() else []


def preserve_version(project_path: str | Path, keep: int = 20) -> Path | None:
    """Copy the previous saved document before explicit overwrite, then prune ours."""
    source = Path(project_path)
    if not source.is_file():
        return None
    folder = version_folder(source)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    target = folder / f"{stamp}-{uuid.uuid4().hex[:6]}.kcut"
    pending = target.with_suffix(".pending")
    try:
        shutil.copy2(source, pending)
        # An unreadable previous save is not a useful recovery point.
        json.loads(pending.read_text(encoding="utf-8"))
        pending.replace(target)
    except Exception:
        pending.unlink(missing_ok=True)
        raise
    for old in versions(source)[max(1, keep):]:
        old.unlink(missing_ok=True)
    return target


def collect_project(project: Project, destination: str | Path, progress=None) -> Path:
    """Create a new project and local media folder; never mutate *project*.

    Destination must not exist, so a failed copy cannot damage existing work.
    Only complete projects receive the final .kcut file.
    """
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")
    snapshot = copy.deepcopy(project)
    sources: dict[str, Path] = {}
    references: list[tuple[dict, str]] = []

    def visit(body: dict):
        for media in body.get("media", []):
            nested = media.get("compound") or media.get("timeline_preset")
            if nested:
                visit(nested)
                # Compound render caches are regenerated for the portable copy.
                if media.get("compound"):media["path"] = ""
                media["thumbnail"] = ""
                if media.get("compound"):continue
            raw = media.get("path", "")
            if not raw:
                continue
            source = Path(raw)
            if not source.is_file():
                raise FileNotFoundError(f"Missing media: {source}")
            key = os.path.normcase(str(source.resolve()))
            sources[key] = source
            references.append((media, key))

    body = snapshot.to_dict()
    visit(body)
    destination.mkdir(parents=True)
    media_dir = destination / "Media"
    media_dir.mkdir()
    relocated: dict[str, Path] = {}
    try:
        total = len(sources)
        for index, (key, source) in enumerate(sources.items(), 1):
            if progress:
                progress((index - 1, total, source.name))
            # Stable unique names preserve familiar source names without collision.
            name = re.sub(r'[<>:"/\\|?*]', "_", source.name)
            target = media_dir / name
            if target.exists():
                target = media_dir / f"{source.stem}-{uuid.uuid5(uuid.NAMESPACE_URL, key).hex[:8]}{source.suffix}"
            shutil.copy2(source, target)
            relocated[key] = target
        for media, key in references:
            media["path"] = str(relocated[key].relative_to(destination))
            # Preserve small existing visual previews. An image's thumbnail may
            # be the source itself; reference the already copied source then.
            thumbnail = Path(media.get("thumbnail") or "")
            if thumbnail.is_file():
                if os.path.normcase(str(thumbnail.resolve())) == key:
                    media["thumbnail"] = media["path"]
                else:
                    thumb_dir = destination / "Thumbnails"
                    thumb_dir.mkdir(exist_ok=True)
                    thumb = thumb_dir / f"{uuid.uuid4().hex[:12]}{thumbnail.suffix}"
                    shutil.copy2(thumbnail, thumb)
                    media["thumbnail"] = str(thumb.relative_to(destination))
            else:
                media["thumbnail"] = ""
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", snapshot.name).strip() or "Project"
        output = destination / f"{safe_name}.kcut"
        body["path"] = str(output)
        body["portable_media"] = True
        pending = output.with_suffix(".kcut.pending")
        pending.write_text(json.dumps(body, indent=2), encoding="utf-8")
        pending.replace(output)
        if progress:
            progress((total, total, output.name))
        return output
    except Exception:
        # Leave partial copies recoverable for diagnostics; no .kcut is published.
        raise
