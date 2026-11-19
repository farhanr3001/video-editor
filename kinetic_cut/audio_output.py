"""Keep existing players on the output selected for this app by the OS."""
from PySide6.QtMultimedia import QAudioOutput as _QAudioOutput, QMediaDevices
from PySide6.QtCore import QCoreApplication


def system_output_devices():
    # Endpoint monitoring belongs to the application, not each short-lived
    # decoder. Cuts/moves must not register and tear down Windows device
    # notifications while replacing players.
    app = QCoreApplication.instance()
    devices = getattr(app, '_kinetic_output_devices', None)
    if devices is None:
        devices = QMediaDevices(app)
        app._kinetic_output_devices = devices
    return devices


class QAudioOutput(_QAudioOutput):
    """Follow Windows Volume Mixer changes without replacing the player.

    Qt resolves the process-default endpoint at construction, but an existing
    QAudioOutput retains that concrete device after the OS preference changes.
    QMediaDevices publishes both per-app routing and endpoint availability
    changes. Re-resolve only then; volume, mute, position and rate stay owned by
    the existing output/player. No polling or playback-clock work is needed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._devices = system_output_devices()
        self._devices.audioOutputsChanged.connect(self._follow_system_output)

    def _follow_system_output(self):
        device = QMediaDevices.defaultAudioOutput()
        if not device.isNull() and device.id() != self.device().id():
            self.setDevice(device)
