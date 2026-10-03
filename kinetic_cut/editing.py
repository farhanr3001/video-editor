"""Shared guard for edit commands exposed by menus, shortcuts and drag handlers."""
from functools import wraps


def edit_only(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        owner = getattr(self, "window", self)
        if callable(owner):
            owner = owner()
        if getattr(self, "read_only", False) or getattr(owner, "current_page", 0) != 0:
            return None
        if function.__name__ not in {'edit_caption','edit_title'} and hasattr(owner,'flush_text_edit'):owner.flush_text_edit()
        return function(self, *args, **kwargs)
    return guarded
