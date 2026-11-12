"""UI-only effect catalogue metadata and bounded library preferences.

No project edits, effect defaults or rendering algorithms live here. Bundled
samples are rendered ahead of time, so browsing never starts a render job.
"""
import functools
import hashlib
import json
from pathlib import Path

from .effects import CATALOG, FACE_FILTER_SUBSECTIONS, TITLES
from .visual_fx import VISUAL_FX_SET, VISUAL_FX_SUBSECTIONS
from .transitions import TRANSITION_SET, TRANSITION_SUBSECTIONS
from .creative_effects import ANIMATED
from .motion_presets import PRESETS
from .speed_presets import PRESETS as SPEEDS

FAVOURITES = 'Favourites'
RECENT = 'Recently used'
RECENT_LIMIT = 10
ALL_NAMES = tuple(dict.fromkeys(name for names in CATALOG.values() for name in names))
GROUPS = {name: group for group, names in CATALOG.items() for name in names}
SUBSECTIONS = {'Visual FX': VISUAL_FX_SUBSECTIONS,
               'Video Transitions': TRANSITION_SUBSECTIONS,
               'Face Filters': FACE_FILTER_SUBSECTIONS}
# A play button represents meaningful temporal behaviour, never a generic zoom.
ANIMATED_NAMES = (set(VISUAL_FX_SET) | set(TRANSITION_SET) | set(ANIMATED) |
                  set(PRESETS) | set(SPEEDS) |
                  {'Motion Composition', 'Timer / Countdown', 'Progress Bar',
                   'Object Tracking', 'Fade In / Out'}) - TITLES


def asset_key(name):
    return hashlib.sha256(name.encode('utf-8')).hexdigest()[:16]


def asset_directory():
    from .icons import resource_path
    return resource_path('assets', 'effects-library')


def manifest():
    try:
        data = json.loads((asset_directory() / 'manifest.json').read_text(encoding='utf-8'))
        return data.get('effects', {}) if data.get('schema') == 1 else {}
    except (OSError, ValueError, TypeError):
        return {}


def asset_path(entry, field):
    value = entry.get(field)
    if not isinstance(value, str) or not value:
        return None
    relative = Path(value)
    if relative.is_absolute() or '..' in relative.parts:
        return None
    path = asset_directory() / relative
    return path if path.is_file() else None


def unique_names(values, limit=None):
    if not isinstance(values, (list, tuple)):
        return []
    result = list(dict.fromkeys(value for value in values if isinstance(value, str) and value in GROUPS))
    return result[:limit] if limit is not None else result


def subsection(settings, category):
    saved = settings.get('effects_subsections', {})
    value = saved.get(category, '') if isinstance(saved, dict) else ''
    return value if value in SUBSECTIONS.get(category, {}) else ''


def used(window, name):
    panel = getattr(window, 'effects_panel', None)
    if panel is not None and isinstance(name, str) and name in GROUPS:
        panel.remember_used(name)


def remember_use(argument='name'):
    """Observe successful editor commands without changing their semantics.

    A failed validation, cancelled dialog or preview is not a recent use. The
    preference is recorded only after a real mutation, outside project history.
    """
    def decorate(function):
        index = function.__code__.co_varnames.index(argument) - 1
        @functools.wraps(function)
        def call(window, *args, **kwargs):
            project = getattr(window, 'project', None)
            before = (id(project), getattr(project, '_edit_revision', 0))
            result = function(window, *args, **kwargs)
            current = getattr(window, 'project', None)
            after = (id(current), getattr(current, '_edit_revision', 0))
            name = kwargs.get(argument, args[index] if index < len(args) else '')
            if project is current and before[1] != after[1]:
                used(window, name)
            return result
        return call
    return decorate
