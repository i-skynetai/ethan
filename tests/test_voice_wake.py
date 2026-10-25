"""Wake control lifecycle with fake processes only; never opens audio hardware."""
import io
import unittest
from unittest.mock import Mock, patch
from ethan import voice


class OptionalLocalWake(unittest.TestCase):
    def setUp(self):
        self.original = dict(voice._STATE)
        self.original_process = voice._PROCESS
        voice._PROCESS = None
        voice._STATE.update(state="idle", muted=True, wake_enabled=False, transcript="")
        self.caps = patch.object(voice, "capabilities", return_value={"supported": True})
        self.caps.start()

    def tearDown(self):
        voice._STATE.clear()
        voice._STATE.update(self.original)
        voice._PROCESS = self.original_process
        self.caps.stop()

    def test_read_unmute_and_muted_enable_do_not_open_audio(self):
        with patch.object(voice.subprocess, "Popen") as spawn:
            self.assertFalse(voice.status()["wake_enabled"])
            voice.command("wake-enable")
            self.assertTrue(voice.status()["muted"])
            voice.command("unmute")
            spawn.assert_not_called()

    def test_explicit_enable_launches_only_owned_local_wake_mode(self):
        process = Mock()
        with patch.object(voice, "_args", return_value=["owned-local-wake"]) as args, \
                patch.object(voice.subprocess, "Popen", return_value=process) as spawn, \
                patch.object(voice.threading, "Thread"):
            voice.command("unmute")
            result = voice.command("wake-enable")
            self.assertTrue(result["wake_enabled"])
            args.assert_called_once_with("wake")
            spawn.assert_called_once()
            voice.command("wake-enable")
            self.assertEqual(spawn.call_count, 1)
            voice.command("mute")
            process.terminate.assert_called_once()
            self.assertFalse(voice.status()["wake_enabled"])
            self.assertTrue(voice.status()["muted"])

    def test_stop_while_waiting_disables_and_late_events_cannot_revive(self):
        process = Mock(stdout=io.StringIO('{"state":"listening","transcript":"approve 1"}\n'), stdin=io.StringIO())
        process.wait.return_value = 0
        voice._PROCESS = process
        voice._STATE.update(state="wake-listening", wake_enabled=True, muted=False)
        voice.command("stop")
        voice._read(process)
        self.assertIsNone(voice._PROCESS)
        self.assertFalse(voice.status()["wake_enabled"])
        self.assertEqual(voice.status()["transcript"], "")

    def test_triggered_dictation_is_preview_only_and_one_shot(self):
        process = Mock(stdout=io.StringIO(
            '{"state":"wake-listening"}\n{"state":"listening"}\n'
            '{"state":"idle","transcript":"approve 123"}\n'), stdin=io.StringIO())
        process.wait.return_value = 0
        voice._PROCESS = process
        voice._STATE.update(wake_enabled=True, muted=False)
        voice._read(process)
        self.assertEqual(voice.status()["transcript"], "approve 123")
        self.assertFalse(voice.status()["wake_enabled"])
        self.assertIsNone(voice._PROCESS)

    def test_unavailable_engine_never_starts_wake(self):
        with patch.object(voice, "capabilities", return_value={"supported": False, "detail": "not installed"}), \
                patch.object(voice.subprocess, "Popen") as spawn:
            voice.command("unmute")
            self.assertEqual(voice.command("wake-enable")["state"], "unavailable")
            spawn.assert_not_called()

    def test_timeout_or_failure_disables_without_rearming(self):
        for code, event in ((0, '{"state":"idle","transcript":"","detail":"Wake listening expired"}\n'),
                            (1, '{"state":"error","detail":"No microphone"}\n')):
            with self.subTest(code=code), patch.object(voice.subprocess, "Popen") as spawn:
                process = Mock(stdout=io.StringIO(event), stdin=io.StringIO())
                process.wait.return_value = code
                voice._PROCESS = process
                voice._STATE.update(state="wake-listening", wake_enabled=True, transcript="")
                voice._read(process)
                self.assertFalse(voice.status()["wake_enabled"])
                self.assertEqual(voice.status()["transcript"], "")
                self.assertEqual(voice.status()["state"], "error" if code else "idle")
                spawn.assert_not_called()
