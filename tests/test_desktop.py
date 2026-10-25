"""Desktop and local voice boundaries without opening browser, mic, or agents."""
import io
import json
from pathlib import Path
import subprocess
import tomllib
import unittest
from unittest import mock

from ethan import desktop, voice


class Desktop(unittest.TestCase):
    def test_voice_controls_start_muted_without_opening_audio(self):
        with mock.patch.object(voice, "_CAPS", {"supported": True, "detail": "installed"}), \
                mock.patch.object(voice.subprocess, "Popen") as spawn:
            self.assertTrue(voice.status()["muted"])
            spawn.assert_not_called()

    def test_packaging_keeps_hud_and_local_speech_assets(self):
        root = Path(__file__).resolve().parents[1]
        meta = tomllib.loads((root / "pyproject.toml").read_text())
        self.assertEqual(meta["project"]["scripts"]["ethan-desktop"], "ethan.desktop:main")
        self.assertEqual(meta["project"]["dependencies"], [])
        assets = meta["tool"]["setuptools"]["package-data"]["ethan"]
        for asset in ("windows_speech.ps1", "web/*.html", "web/*.css", "web/*.js"):
            self.assertIn(asset, assets)

    def test_hotkey_commands_are_local_voice_only(self):
        with mock.patch.object(desktop.urllib.request, "build_opener") as build:
            response = build.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b'{"state":"starting"}'
            self.assertEqual(desktop.voice_command("http://localhost:8787", "start")["state"], "starting")
            request = build.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "http://localhost:8787/api/voice/start")
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(request.data, b"{}")
            with self.assertRaises(ValueError):
                desktop.voice_command("http://evil.example", "start")
            with self.assertRaises(ValueError):
                desktop.voice_command("http://localhost", "ask")

    def test_desktop_rejects_remote_and_ambiguous_origins(self):
        for url in ("https://localhost/", "http://evil.example/", "http://127.0.0.1.evil/",
                    "http://u:p@localhost/", "http://localhost/x", "http://localhost/?x=y",
                    "http://localhost/#x", "http://localhost:0", "http://localhost:65536"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                desktop.local_url(url)
        self.assertEqual(desktop.local_url("http://127.0.0.1:8787"), "http://127.0.0.1:8787/")

    def test_missing_service_does_not_start_anything_implicitly(self):
        with mock.patch.object(desktop, "browser_path", return_value="edge.exe"), \
                mock.patch.object(desktop, "reachable", return_value=False), \
                mock.patch.object(desktop.subprocess, "Popen") as spawn, \
                mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(desktop.main([]), 1)
            spawn.assert_not_called()

    def test_existing_service_opens_only_browser_app_mode(self):
        with mock.patch.object(desktop, "browser_path", return_value="edge.exe"), \
                mock.patch.object(desktop, "reachable", return_value=True), \
                mock.patch.object(desktop.subprocess, "Popen") as spawn, \
                mock.patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(desktop.main([]), 0)
        self.assertEqual(spawn.call_count, 1)
        self.assertTrue(spawn.call_args.args[0][1].startswith("--app=http://127.0.0.1:"))

    def test_check_opens_neither_browser_nor_microphone(self):
        with mock.patch.object(desktop, "browser_path", return_value=None), \
                mock.patch.object(desktop, "reachable", return_value=False), \
                mock.patch.object(voice, "status", return_value={"supported": False, "state": "unavailable"}), \
                mock.patch.object(desktop.subprocess, "Popen") as spawn, \
                mock.patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(desktop.main(["--check"]), 0)
            self.assertIn("explicit local opt-in", json.loads(out.getvalue())["wake_word"])
            self.assertIn("hardware unverified", json.loads(out.getvalue())["wake_word"])
            spawn.assert_not_called()


class Voice(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(voice, "_CAPS", {"supported": True, "detail": "installed"}),
                        mock.patch.object(voice, "_PROCESS", None),
                        mock.patch.object(voice, "_STATE", {"state": "idle", "muted": False,
                                                          "transcript": "", "detail": "Microphone off"})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_status_never_opens_microphone(self):
        with mock.patch.object(voice.subprocess, "Popen") as spawn:
            self.assertEqual(voice.status()["state"], "idle")
            spawn.assert_not_called()

    def test_unsupported_or_muted_never_starts_capture(self):
        with mock.patch.object(voice.subprocess, "Popen") as spawn:
            voice.command("mute")
            voice.command("start")
            self.assertTrue(voice.status()["muted"])
            spawn.assert_not_called()
            with mock.patch.object(voice, "_CAPS", {"supported": False, "detail": "no recognizer"}):
                self.assertEqual(voice.command("start")["state"], "unavailable")
                spawn.assert_not_called()

    def test_cancel_discards_transcript_and_stops_only_owned_capture(self):
        process = mock.Mock()
        voice._PROCESS = process
        voice._STATE.update(state="listening", transcript="approve 3")
        result = voice.command("cancel")
        process.terminate.assert_called_once()
        self.assertEqual((result["state"], result["transcript"]), ("idle", ""))

    def test_stop_only_signals_capture_never_dispatches_text(self):
        process = mock.Mock()
        voice._PROCESS = process
        self.assertEqual(voice.command("stop")["state"], "transcribing")
        process.stdin.write.assert_called_once_with("stop\n")

    def test_recognized_text_stays_preview(self):
        process = mock.Mock(stdout=io.StringIO('{"state":"idle","transcript":"approve 123"}\n'),
                            stdin=io.StringIO())
        process.wait.return_value = 0
        voice._PROCESS = process
        voice._read(process)
        self.assertEqual(voice.status()["transcript"], "approve 123")
        self.assertEqual(voice.status()["state"], "idle")
        self.assertIsNone(voice._PROCESS)

    def test_bad_command_is_rejected(self):
        with self.assertRaises(ValueError):
            voice.command("approve")

    def test_probe_failure_is_reported_without_fallback(self):
        with mock.patch.object(voice, "_CAPS", None), mock.patch.object(voice, "_powershell", return_value="ps"), \
                mock.patch.object(voice, "_args", return_value=["ps"]), \
                mock.patch.object(voice.subprocess, "run", side_effect=subprocess.TimeoutExpired("ps", 1)):
            self.assertFalse(voice.capabilities()["supported"])
            self.assertIn("TimeoutExpired", voice.capabilities()["detail"])


if __name__ == "__main__":
    unittest.main()
