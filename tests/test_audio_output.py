import ast
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, QCoreApplication, QEvent
import shiboken6

from kinetic_cut.audio_output import QAudioOutput


class AudioOutputTests(TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])

    def test_route_change_updates_only_device_and_preserves_controls(self):
        output = QAudioOutput()
        output.setVolume(.37)
        output.setMuted(True)
        target = Mock()
        target.isNull.return_value = False
        target.id.return_value = b'new-headphones'
        with patch('kinetic_cut.audio_output.QMediaDevices.defaultAudioOutput', return_value=target), patch.object(output, 'setDevice') as change:
            output._devices.audioOutputsChanged.emit()
            change.assert_called_once_with(target)
        self.assertAlmostEqual(output.volume(), .37, places=5)
        self.assertTrue(output.isMuted())

    def test_same_or_missing_device_does_not_reopen_output(self):
        output = QAudioOutput()
        with patch.object(output, 'setDevice') as change:
            with patch('kinetic_cut.audio_output.QMediaDevices.defaultAudioOutput', return_value=output.device()):
                output._devices.audioOutputsChanged.emit()
            target = Mock(); target.isNull.return_value = True
            with patch('kinetic_cut.audio_output.QMediaDevices.defaultAudioOutput', return_value=target):
                output._devices.audioOutputsChanged.emit()
            change.assert_not_called()

    def test_route_listener_is_owned_and_destroyed_with_output(self):
        parent = QObject(); output = QAudioOutput(parent); devices = output._devices
        self.assertEqual(devices.parent(), output)
        parent.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertFalse(shiboken6.isValid(output))
        self.assertFalse(shiboken6.isValid(devices))

    def test_every_audible_player_uses_system_following_output(self):
        root = Path(__file__).resolve().parents[1] / 'kinetic_cut'
        consumers = []
        for path in root.glob('*.py'):
            if path.stem == 'audio_output': continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            uses = any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'QAudioOutput' for node in ast.walk(tree))
            if uses:
                consumers.append(path.stem)
                self.assertTrue(any(isinstance(node, ast.ImportFrom) and node.module == 'audio_output' and any(alias.name == 'QAudioOutput' for alias in node.names) for node in ast.walk(tree)), path.name)
        self.assertIn('transport', consumers)
        self.assertIn('tts_dialogue_dialog', consumers)
        self.assertEqual(len(consumers), 9)
