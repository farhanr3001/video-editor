"""Opt-in local editing trace. No input, transport or render behavior changes."""
import functools
import time
import weakref
from pathlib import Path

from PySide6.QtCore import QObject, QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer

from .activity_log import ActivityLog


class InteractionTrace(QObject):
    def __init__(self, window, directory):
        super().__init__(window)
        self.window = window
        self.log = ActivityLog(Path(directory) / 'editing-events.log', capacity=4096)
        self.until = 0.; self.closed = False; self.active = []; self.last_event = None
        self.wrapped = []; self.watched = {}; self.previous = time.monotonic()
        app = QApplication.instance()
        self.guard = getattr(app, '_kinetic_hang_watchdog', None)
        self.guard_timer = getattr(app, '_kinetic_hang_timer', None)
        self.guard_state = ((self.guard.timeout, self.guard.interval, self.guard.max_reports)
                            if self.guard else None)
        self.guard_interval = self.guard_timer.interval() if self.guard_timer else None
        if self.guard:
            self.guard.interval = .025; self.guard.max_reports = 24
        if self.guard_timer: self.guard_timer.setInterval(25)
        self.targets = [window.timeline.viewport()]
        surface = getattr(window.timeline, 'gpu', None)
        if surface: self.targets.extend((surface.view, surface.container))
        for target in self.targets: target.installEventFilter(self)
        for owner, names in ((window, ('model_changed', 'commit_history', 'refresh_inspector', 'autosave')),
                             (window.inspector, ('select',)),
                             (window.transport, ('sync', 'create_decoder', 'retire_decoder'))):
            for name in names: self.wrap(owner, name)
        self.watch_player(window.player)
        for player, _, _ in window.transport.decoders.values(): self.watch_player(player)
        self.timer = QTimer(self); self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(10); self.timer.timeout.connect(self.sample); self.timer.start()
        app.aboutToQuit.connect(self.stop)
        self.log.record('trace.ready', transport=False, rendering=False, input=False)

    def arm(self):
        self.until = time.monotonic() + 3.
        if self.guard:
            self.guard.timeout = .18; self.guard.deadline = 0.

    def watch_player(self, player):
        if not isinstance(player, QMediaPlayer): return
        known = self.watched.get(id(player))
        if known is not None and known() is player: return
        self.watched[id(player)] = weakref.ref(player); player.installEventFilter(self)

    def wrap(self, owner, name):
        original = getattr(owner, name)
        label = type(owner).__name__ + '.' + name
        @functools.wraps(original)
        def measured(*args, **kwargs):
            recording = not self.closed and time.monotonic() < self.until
            start = time.monotonic()
            if recording:
                self.active.append(label); self.log.record('work.begin', name=label)
            try:
                result = original(*args, **kwargs)
                if name == 'create_decoder':
                    decoder = owner.decoders.get(args[0]) if args else None
                    if decoder: self.watch_player(decoder[0])
                return result
            finally:
                if recording:
                    self.log.record('work.end', name=label, ms=round((time.monotonic()-start)*1000, 3))
                    self.active.pop()
        setattr(owner, name, measured)
        self.wrapped.append((owner, name, original, measured))

    def eventFilter(self, watched, event):
        if self.closed: return False
        kind = event.type()
        if watched in self.targets and kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            self.arm()
            self.log.record('input.press' if kind == QEvent.MouseButtonPress else 'input.release',
                            x=round(event.position().x(), 1), y=round(event.position().y(), 1))
        if time.monotonic() < self.until:
            player = isinstance(watched, QMediaPlayer)
            if ((player and kind in (QEvent.MetaCall, QEvent.DeferredDelete)) or
                    (watched in self.targets and kind in (QEvent.UpdateRequest, QEvent.Paint, QEvent.Expose))):
                self.last_event = (type(watched).__name__, int(kind), id(watched))
                self.log.record('qt.dispatch', receiver=self.last_event[0], event=int(kind), object=id(watched))
        return False

    def sample(self):
        now = time.monotonic(); delay = now-self.previous; self.previous = now
        if delay > .12 and now < self.until:
            self.log.record('gui.delay', ms=round(delay*1000, 2),
                            active=' > '.join(self.active), last_event=str(self.last_event))
        if self.guard and now >= self.until and self.guard.timeout != self.guard_state[0]:
            self.guard.timeout = self.guard_state[0]; self.guard.deadline = 0.

    def stop(self):
        if self.closed: return
        self.closed = True; self.timer.stop()
        import shiboken6
        for target in self.targets:
            if shiboken6.isValid(target): target.removeEventFilter(self)
        for ref in self.watched.values():
            player = ref()
            if player is not None and shiboken6.isValid(player): player.removeEventFilter(self)
        for owner, name, original, measured in reversed(self.wrapped):
            if getattr(owner, name) is measured: setattr(owner, name, original)
        if self.guard:
            self.guard.timeout, self.guard.interval, self.guard.max_reports = self.guard_state
            self.guard.deadline = 0.
        if self.guard_timer and shiboken6.isValid(self.guard_timer): self.guard_timer.setInterval(self.guard_interval)
        self.log.record('trace.stopped')
        # ActivityLog flushes at process exit, never in this GUI shutdown slot.


def install(window, directory):
    if not getattr(window, '_interaction_trace', None):
        window._interaction_trace = InteractionTrace(window, directory)
    return window._interaction_trace
