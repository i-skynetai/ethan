"""Recognized output credentials are withheld before durable sinks; fake data only."""
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from ethan import hands, redact, store, util


class OutputProtection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"ETHAN_STATE_DIR": self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        db = patch.object(store, "_DB", None)
        db.start()
        self.addCleanup(db.stop)
        self.addCleanup(lambda: store._DB.close() if store._DB else None)
        self.secret = "sk-" + "FAKEOUTPUTONLY" * 3

    def test_whole_output_withheld_clean_unchanged(self):
        clean = "Reviewed three files; no issues."
        self.assertEqual(redact.gate_output(clean), (clean, []))
        safe, kinds = redact.gate_output("Result contains " + self.secret)
        self.assertIn("openai-key", kinds)
        self.assertIn("Output withheld", safe)
        self.assertNotIn(self.secret, safe)

    def test_multiline_and_unfinished_private_key_never_reach_stream_sinks(self):
        for end in ("-----END PRIVATE KEY-----\n", ""):
            with self.subTest(end=end):
                stream = redact.OutputStream()
                emitted = "".join(stream.feed(line) for line in (
                    "normal before\n", "-----BEGIN PRIVATE KEY-----\n", "FAKE_PRIVATE_BODY\n", end))
                self.assertIn("normal before", emitted)
                self.assertNotIn("FAKE_PRIVATE_BODY", emitted)
                self.assertEqual(stream.kinds, {"private-key"})

    def test_second_unfinished_block_stays_suppressed(self):
        stream = redact.OutputStream()
        stream.feed("-----BEGIN PRIVATE KEY-----first-----END PRIVATE KEY----- -----BEGIN PRIVATE KEY-----\n")
        self.assertEqual(stream.feed("SECOND_FAKE_PRIVATE_BODY\n"), "")
        self.assertTrue(stream.private)

    def test_clean_hand_result_is_unchanged(self):
        process = Mock(stdout=io.StringIO("Clean review result\n"), returncode=0)
        process.wait.return_value = 0
        path = Path(self.temp.name) / "clean.log"
        with patch.object(hands, "cfg", return_value={}), \
                patch.object(hands, "sky_bin", return_value="fake-sky"), \
                patch.object(hands, "build_command", return_value=["fake-sky", "<brief>"]), \
                patch.object(hands, "build_env", return_value={}), \
                patch.object(hands, "_log_path", return_value=str(path)), \
                patch.object(hands.subprocess, "Popen", return_value=process):
            result = hands.run("codex", "review")
        self.assertTrue(result["ok"])
        self.assertEqual(result["out"], "Clean review result")
        self.assertIn("Clean review result", path.read_text(encoding="utf-8"))

    def test_message_reply_task_and_relay_sinks_never_keep_detected_output(self):
        tid = store.add_task("test", "review", None, "codex", "review")
        store.finish_task(tid, "done", self.secret)
        store.remember("test", "assistant", self.secret)
        store.add_reply("test", self.secret)
        rid = store.add_relay("test", "console", "review", "review-only")
        store.update_relay(rid, state="completed", result=self.secret)
        self.assertEqual(store.task(tid)["state"], "failed")
        self.assertEqual(store.relay(rid)["state"], "failed")
        dump = "\n".join(store.db().iterdump())
        self.assertNotIn(self.secret, dump)
        self.assertIn("Output withheld", dump)

    def test_diagnostics_are_protected_in_sink_and_stdout(self):
        with patch.object(util, "sink", []) as sink:
            util.log("provider failed: " + self.secret)
            self.assertNotIn(self.secret, "".join(sink))
        with patch.object(util, "sink", None), patch("sys.stdout", new=io.StringIO()) as out:
            util.log(self.secret)
            self.assertNotIn(self.secret, out.getvalue())

    def test_diagnostic_private_block_across_calls_is_suppressed(self):
        with patch.object(util, "_LOG_OUTPUT", None), patch.object(util, "sink", []) as sink:
            util.log("-----BEGIN PRIVATE KEY-----")
            util.log("FAKE_PRIVATE_BODY")
            util.log("-----END PRIVATE KEY-----")
            util.log("normal diagnostic")
            self.assertNotIn("FAKE_PRIVATE_BODY", "".join(sink))
            self.assertIn("normal diagnostic", sink)

    def test_fake_hand_stdout_is_filtered_before_log_and_result(self):
        path = Path(self.temp.name) / "run.log"
        for stdout in ("answer " + self.secret + "\n",
                       "-----BEGIN PRIVATE KEY-----\nFAKE_PRIVATE_BODY\n-----END PRIVATE KEY-----\n"):
            with self.subTest(stdout=stdout):
                process = Mock(stdout=io.StringIO(stdout), returncode=0)
                process.wait.return_value = 0
                with patch.object(hands, "cfg", return_value={}), \
                        patch.object(hands, "sky_bin", return_value="fake-sky"), \
                        patch.object(hands, "build_command", return_value=["fake-sky", "<brief>"]), \
                        patch.object(hands, "build_env", return_value={}), \
                        patch.object(hands, "_log_path", return_value=str(path)), \
                        patch.object(hands.subprocess, "Popen", return_value=process):
                    result = hands.run("codex", "review")
                self.assertFalse(result["ok"])
                self.assertIn("Output withheld", result["out"])
                persisted = path.read_text(encoding="utf-8") + repr(result)
                self.assertNotIn(self.secret, persisted)
                self.assertNotIn("FAKE_PRIVATE_BODY", persisted)
