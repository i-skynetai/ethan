"""Synthetic local request headers; no actual token or microphone is used."""
import os
import urllib.error
import unittest
from unittest.mock import patch
from ethan import cli, desktop, hands, local_auth, relay, voice

SYNTHETIC = "SYNTHETIC_CLIENT_ONLY_" * 3


class LocalCredentialTransport(unittest.TestCase):
    def test_loopback_header_no_proxy_no_redirect(self):
        with patch.dict(os.environ, {local_auth.ENV_NAME: SYNTHETIC, "HTTP_PROXY": "http://invalid.example"}), \
                patch.object(local_auth.urllib.request, "build_opener") as build:
            local_auth.request("http://127.0.0.1:8787/api/state", timeout=2)
            req = build.return_value.open.call_args.args[0]
            self.assertEqual(req.get_header("Authorization"), "Bearer " + SYNTHETIC)
            self.assertNotIn(SYNTHETIC, req.full_url)
            proxy, redirect = build.call_args.args
            self.assertEqual(proxy.proxies, {})
            self.assertIsNone(redirect.redirect_request(None, None, None, None, None, None))

    def test_bad_origins_refused_before_auth_or_network(self):
        for url in ("https://localhost/api/state", "http://evil.example/api/state", "http://127.0.0.1.evil/",
                    "http://u:p@localhost/", "http://localhost:0/", "http://localhost:65536/", "http://localhost/#token", "http://local\nhost/"):
            with self.subTest(url=url), patch.object(local_auth, "load") as load, \
                    patch.object(local_auth.urllib.request, "build_opener") as build:
                with self.assertRaises(ValueError):
                    local_auth.request(url)
                load.assert_not_called()
                build.assert_not_called()

    def test_desktop_unauthorized_service_never_spawns_duplicate(self):
        denied = urllib.error.HTTPError("http://localhost:8787/api/state", 401, "Unauthorized", {}, None)
        with patch.object(desktop, "browser_path", return_value="fixture-browser"), \
                patch.object(local_auth, "request", side_effect=denied), \
                patch.object(desktop.subprocess, "Popen") as spawn, patch("sys.stderr"):
            self.assertEqual(desktop.main(["--start-service"]), 1)
            spawn.assert_not_called()

    def test_desktop_invalid_auth_configuration_never_spawns(self):
        with patch.dict(os.environ, {local_auth.ENV_NAME: "invalid"}), \
                patch.object(desktop, "browser_path", return_value="fixture-browser"), \
                patch.object(desktop.subprocess, "Popen") as spawn, patch("sys.stderr"):
            self.assertEqual(desktop.main(["--start-service"]), 1)
            spawn.assert_not_called()

    def test_cli_get_and_post_use_same_local_guarded_transport(self):
        with patch.dict(os.environ, {local_auth.ENV_NAME: SYNTHETIC}), \
                patch.object(cli, "BASE", "http://localhost:8787"), \
                patch.object(local_auth.urllib.request, "build_opener") as build:
            build.return_value.open.return_value.__enter__.return_value.read.return_value = b'{}'
            self.assertEqual(cli.get("/api/state"), {})
            first = build.return_value.open.call_args.args[0]
            self.assertEqual(first.get_header("Authorization"), "Bearer " + SYNTHETIC)
            self.assertEqual(cli.post("/api/ask", {"text": "synthetic fixture"}), {})
            second = build.return_value.open.call_args.args[0]
            self.assertEqual(second.get_header("Authorization"), "Bearer " + SYNTHETIC)
            self.assertEqual(second.get_method(), "POST")
            self.assertNotIn(SYNTHETIC.encode(), second.data)

    def test_cli_refuses_401_without_claiming_service_is_stopped(self):
        denied = urllib.error.HTTPError("http://localhost:8787/api/state", 401, "Unauthorized", {}, None)
        with patch("sys.argv", ["ethan", "--status"]), patch.object(cli, "get", side_effect=denied):
            with self.assertRaises(SystemExit) as caught:
                cli.main()
            self.assertIn("authentication required", str(caught.exception))
            self.assertNotIn("not running", str(caught.exception))

    def test_cli_help_needs_no_token_or_service(self):
        with patch.dict(os.environ, {local_auth.ENV_NAME: "invalid"}), \
                patch("sys.argv", ["ethan", "--help"]), patch("builtins.print"), \
                patch.object(local_auth, "request") as request:
            cli.main()
            request.assert_not_called()

    def test_child_environment_strips_token_even_mixed_case(self):
        source = {local_auth.ENV_NAME: SYNTHETIC, local_auth.ENV_NAME.lower(): SYNTHETIC, "PATH": "fixture"}
        self.assertEqual(local_auth.child_environment(source), {"PATH": "fixture"})
        self.assertEqual(source[local_auth.ENV_NAME], SYNTHETIC)

    def test_harness_never_receives_bearer_even_as_misconfigured_kb_pat(self):
        with patch.dict(os.environ, {local_auth.ENV_NAME: SYNTHETIC}):
            env = hands.build_env({"sky": {"state_dir": "fixture-state"}}, {"pat_env": local_auth.ENV_NAME})
        self.assertNotIn(local_auth.ENV_NAME, env)
        self.assertNotIn(SYNTHETIC, env.values())

    def test_browser_strips_token_but_explicit_service_keeps_owner_configuration(self):
        with patch.dict(os.environ, {local_auth.ENV_NAME: SYNTHETIC}), \
                patch.object(desktop, "browser_path", return_value="fixture-browser"), \
                patch.object(desktop, "reachable", side_effect=[False, True]), \
                patch.object(desktop.subprocess, "Popen") as spawn, patch("builtins.print"):
            self.assertEqual(desktop.main(["--start-service"]), 0)
            service, browser = spawn.call_args_list
            self.assertEqual(service.kwargs["env"][local_auth.ENV_NAME], SYNTHETIC)
            self.assertNotIn(local_auth.ENV_NAME, browser.kwargs["env"])

    def test_speech_probe_and_capture_children_never_receive_bearer(self):
        with patch.dict(os.environ, {local_auth.ENV_NAME: SYNTHETIC}), \
                patch.object(voice, "_CAPS", None), patch.object(voice, "_powershell", return_value="fixture"), \
                patch.object(voice, "_args", return_value=["fixture"]), \
                patch.object(voice.subprocess, "run") as run:
            run.return_value.stdout = '{"supported":true,"detail":"synthetic"}'
            run.return_value.returncode = 0
            self.assertTrue(voice.capabilities()["supported"])
            self.assertNotIn(local_auth.ENV_NAME, run.call_args.kwargs["env"])
        for action in ("start", "wake-enable"):
            with self.subTest(action=action), patch.dict(os.environ, {local_auth.ENV_NAME: SYNTHETIC}), \
                    patch.object(voice, "_PROCESS", None), \
                    patch.object(voice, "_STATE", {"muted": False, "state": "idle", "wake_enabled": False}), \
                    patch.object(voice, "capabilities", return_value={"supported": True}), \
                    patch.object(voice, "_args", return_value=["fixture"]), \
                    patch.object(voice.threading, "Thread"), patch.object(voice.subprocess, "Popen") as spawn:
                voice.command(action)
                self.assertNotIn(local_auth.ENV_NAME, spawn.call_args.kwargs["env"])
                voice.command("cancel")

    def test_bridge_child_strips_bearer_and_preserves_its_other_environment(self):
        with patch.dict(os.environ, {local_auth.ENV_NAME: SYNTHETIC, "ETHAN_BRIDGE_DIR": "fixture-bridge",
                                     "UNCHANGED_FIXTURE": "kept"}), \
                patch.object(relay.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"state":"completed"}'
            self.assertEqual(relay._bridge("status", "fixture"), {"state": "completed"})
            env = run.call_args.kwargs["env"]
            self.assertNotIn(local_auth.ENV_NAME, env)
            self.assertEqual(env["UNCHANGED_FIXTURE"], "kept")
            self.assertIn("fixture-bridge", env["PYTHONPATH"])
            self.assertEqual(os.environ[local_auth.ENV_NAME], SYNTHETIC)
