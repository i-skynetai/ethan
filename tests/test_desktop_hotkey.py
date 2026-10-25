"""Deterministic global shortcut checks: no real hotkey or microphone access."""
import ctypes
import unittest
from unittest import mock

from ethan import desktop


class Hotkey(unittest.TestCase):
    def run_hotkey(self, held=False, register=True):
        user32 = mock.Mock()
        user32.RegisterHotKey.return_value = register
        events = [True, False]

        def peek(message, *args):
            present = events.pop(0) if events else False
            if present:
                message._obj.message = 0x0312
            return present

        user32.PeekMessageW.side_effect = peek
        user32.GetAsyncKeyState.return_value = 0x8000 if held else 0
        with mock.patch.object(desktop.sys, 'platform', 'win32'), \
                mock.patch.object(ctypes, 'windll', mock.Mock(user32=user32), create=True), \
                mock.patch.object(desktop, 'voice_command', return_value={'state': 'listening'}) as command, \
                mock.patch.object(desktop.time, 'sleep', side_effect=KeyboardInterrupt), \
                mock.patch('builtins.print'):
            with self.assertRaises(KeyboardInterrupt if register else RuntimeError):
                desktop.global_ptt('http://localhost:8787/')
        return user32, command

    def test_release_stops_after_start_and_unregisters(self):
        api, command = self.run_hotkey()
        self.assertEqual([c.args[1] for c in command.call_args_list], ['start', 'stop'])
        api.UnregisterHotKey.assert_called_once_with(None, 1)

    def test_interruption_cancels_active_capture(self):
        api, command = self.run_hotkey(held=True)
        self.assertEqual([c.args[1] for c in command.call_args_list], ['start', 'cancel'])
        api.UnregisterHotKey.assert_called_once_with(None, 1)

    def test_registration_conflict_opens_no_microphone(self):
        api, command = self.run_hotkey(register=False)
        command.assert_not_called()
        api.UnregisterHotKey.assert_not_called()


if __name__ == '__main__':
    unittest.main()
