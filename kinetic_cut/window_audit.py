"""Diagnostic observer: catch even fleeting top-level widget shows."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QWidget


class WindowShowAudit(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.allowed = []
        self.events = []
        app.installEventFilter(self)

    def allow(self, widget):
        self.allowed.append(widget)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Show and isinstance(watched, QWidget) and watched.isWindow():
            self.events.append(dict(widget=type(watched).__name__, title=watched.windowTitle(),
                                    expected=any(watched is item for item in self.allowed)))
        return False

    @property
    def unexpected(self):
        return [event for event in self.events if not event['expected']]


class NativeWindowShowAudit:
    """Windows event hook, rather than polling that can miss short flashes."""
    def __init__(self):
        import ctypes
        import os
        from ctypes import wintypes
        self.events = []
        self.foreign_events = []
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.SetWinEventHook.restype = wintypes.HANDLE
        self.user32.GetAncestor.restype = wintypes.HWND
        callback = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD,
            wintypes.HWND, wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
        self.user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD,
            wintypes.HMODULE, callback, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        self.user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        def shown(hook, event, hwnd, object_id, child_id, thread_id, timestamp):
            if object_id != 0 or child_id != 0 or not hwnd:return
            if self.user32.GetAncestor(hwnd, 2) != hwnd:return
            # The SHOW notification remains evidence even if HIDE has already
            # happened by callback dispatch; do not filter by current visibility.
            title = ctypes.create_unicode_buffer(512); kind = ctypes.create_unicode_buffer(256)
            self.user32.GetWindowTextW(hwnd, title, len(title))
            self.user32.GetClassNameW(hwnd, kind, len(kind))
            pid = wintypes.DWORD(); self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            record = dict(hwnd=int(hwnd), pid=pid.value, title=title.value, window_class=kind.value)
            (self.events if pid.value == os.getpid() else self.foreign_events).append(record)
        self.callback = callback(shown)
        self.hook = self.user32.SetWinEventHook(0x8002, 0x8002, None, self.callback, os.getpid(), 0, 0)
        if not self.hook:raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.hook:self.user32.UnhookWinEvent(self.hook); self.hook = None
